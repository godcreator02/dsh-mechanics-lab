"""假 home 与 profile 的供给。

铁律（写在最前面，改这个文件前先读）：
  1. 一切只发生在假 home 里，绝不碰 ~/.dsh —— 那是用户的生产 home，主实例挂着分发线
  2. 每个实验一个独立 home，物理隔离，不靠纪律
  3. 删目录时逐层拆 junction，绝不跟着链接走
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# ── 路径常量 ────────────────────────────────────────────────────────────────

LAB_ROOT = Path(__file__).resolve().parent.parent.parent
EXPERIMENTS_DIR = LAB_ROOT / "experiments"
TESTHOME_ROOT = LAB_ROOT / ".testhome"
RESULTS_DIR = LAB_ROOT / "results"

#: 本机上可能有别的东西在跑的端口，任何情况下都不许碰
FORBIDDEN_PORTS = (3080, 3239, 3733)

#: 本箱可用端口。上下界都是硬的——3080 与 3100 以上都可能被别的进程占着
LAB_PORT_RANGE = range(3090, 3100)

#: 每个 profile 默认叠的 bundle。dsh-base 是所有 profile 的共同底座；
#: dsh-web-app 只有需要 HTTP 观测面时才要，它很重（几十个条目），
#: 不需要就别加 —— 启动快一大截。
BUNDLE_BASE = "@deepseek-ai/dsh-base"
BUNDLE_WEB = "@deepseek-ai/dsh-web-app"

#: 插件系统的两个基础设施包。它们住在 dsh 的安装目录里，**不在 profile 的
#: node_modules 下** —— 但照样能用裸包名引用：裸包名以 dsh 安装目录为锚
#: （profile-boot 把自己的 package.json 当 `bareModuleBaseUrl` 传给 boot），
#: 而不是以 profile 为锚。L0 实测。
PKG_TIMER = "@deepseek-ai/cordis-plugin-timer"
PKG_HMR = "@deepseek-ai/cordis-plugin-hmr"


class LabError(RuntimeError):
    """实验台自己的错误，区别于被测系统的错误。"""


# ── dsh 部署定位 ────────────────────────────────────────────────────────────

_dsh_bin_cache: Path | None = None


def dsh_bin() -> Path:
    """定位 dsh 部署的 `bin.js`。

    解析顺序：`$LAB_DSH_BIN` > 扫 npx 缓存取最新的一份。

    npx 缓存那条是常规情形——`npx @deepseek-ai/dsh` 跑过之后它就在那儿。
    环境变量留给「dsh 装在别处」的部署，本实验台不猜别的位置。
    """
    global _dsh_bin_cache
    if _dsh_bin_cache is not None:
        return _dsh_bin_cache

    env = os.environ.get("LAB_DSH_BIN")
    if env and Path(env).exists():
        _dsh_bin_cache = Path(env)
        return _dsh_bin_cache

    npx_root = Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
    if npx_root.is_dir():
        found = [
            p
            for d in npx_root.iterdir()
            if (p := d / "node_modules/@deepseek-ai/dsh/lib/bin.js").exists()
        ]
        if found:
            _dsh_bin_cache = max(found, key=lambda p: p.stat().st_mtime)
            return _dsh_bin_cache

    raise LabError("找不到 dsh 部署的 bin.js —— 设 $DSHW_DSH_BIN 指过去")


# ── junction 安全删除 ───────────────────────────────────────────────────────


def rmtree_safe(path: Path) -> None:
    """删目录树，遇到 junction / symlink 只拆链接本身，绝不跟进去。

    为什么不用 shutil.rmtree：profile 的 node_modules 里全是指向插件源码和 npx
    缓存的 junction，rmtree 有跟进去删目标内容的历史问题 —— 那会删掉真东西。

    Windows 细节：
      * os.rmdir() 作用在一个目录重解析点（junction）上，只删链接、不碰目标内容
      * Path.is_dir() 对 junction 也返回 True（它会解析），所以**必须先判 is_junction**
      * Path.is_junction() 是 Python 3.12 才有的，本项目钉 3.12.10，可以直接用
    """
    if not path.exists() and not path.is_symlink():
        return
    if path.is_junction() or path.is_symlink():
        path.rmdir() if path.is_dir() else path.unlink()
        return

    for child in path.iterdir():
        if child.is_junction() or child.is_symlink():
            child.rmdir() if child.is_dir() else child.unlink()
        elif child.is_dir():
            rmtree_safe(child)
        else:
            child.chmod(0o600)  # node_modules 里可能有只读文件
            child.unlink()
    path.rmdir()


def make_junction(link: Path, target: Path) -> None:
    """建一个目录 junction。

    用 mklink /J 而不是 os.symlink：symlink 在 Windows 上需要开发者模式或管理员
    权限，junction 不需要。生产环境里 pnpm 的 hoisted linker 对 link: 依赖建的
    也正是顶层直接 junction（已对照真实 profile 验证过），两者等价。
    """
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_junction():
        rmtree_safe(link)
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target.resolve())],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise LabError(f"建 junction 失败 {link} -> {target}:\n{result.stdout}\n{result.stderr}")


# ── profile ─────────────────────────────────────────────────────────────────


@dataclass
class LabProfile:
    """一个 profile：既是 Node 包，也是一套组合配方。"""

    home: LabHome
    name: str

    @property
    def dir(self) -> Path:
        return self.home.root / "profiles" / self.name

    @property
    def patch_path(self) -> Path:
        """活层。被 watcher 监听，改动秒级热重放。"""
        return self.dir / "cordis.patch.yml"

    def write_patch(self, content: str) -> None:
        """写活层。

        顶层必须是 YAML 数组 —— 空内容要写成 []，只剩注释会让 dsh 启动报错。
        """
        stripped = "\n".join(
            line for line in content.splitlines() if line.strip() and not line.strip().startswith("#")
        )
        self.patch_path.write_text(content if stripped else "[]\n", encoding="utf-8")

    def read_patch(self) -> str:
        return self.patch_path.read_text(encoding="utf-8")

    def link_plugin(self, package_name: str, source: Path) -> None:
        """把一个插件包 link 进这个 profile。

        同时做两件事，缺一不可：
          * 写 package.json 的 dependencies（`link:` 协议）—— 与生产供给形态一致
          * 在 node_modules 建 junction —— Node 的模块解析只看这个，不看 dependencies

        绝不走 `dsh plugin add`：那条命令装完会对账，凡声明了 dsh.bundle 的包会被
        自动追加进 dsh.profile.bundles，于是 bundle 层和活层同 id 双挂，挂载期抛
        duplicate loader entry id，整次热重放事务回滚。
        """
        manifest = json.loads((self.dir / "package.json").read_text(encoding="utf-8"))
        manifest.setdefault("dependencies", {})[package_name] = f"link:{source.resolve().as_posix()}"
        (self.dir / "package.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        make_junction(self.dir / "node_modules" / package_name, source)


# ── home ────────────────────────────────────────────────────────────────────


@dataclass
class LabHome:
    """一个独立的假 DSH home。每个实验一个，物理隔离。"""

    label: str
    root: Path = field(init=False)

    def __post_init__(self) -> None:
        self.root = TESTHOME_ROOT / self.label
        (self.root / "profiles").mkdir(parents=True, exist_ok=True)
        (self.root / "logs").mkdir(parents=True, exist_ok=True)

    @property
    def patch_path(self) -> Path:
        """home 级 patch 层（$DSH_HOME/cordis.patch.yml）。

        优先级压过每个 profile 自己的活层，对本 home 下所有 profile 同时生效。
        这一层是 L7 的实验对象 —— 也正是每个实验必须用独立 home 的头号理由。
        """
        return self.root / "cordis.patch.yml"

    def write_home_patch(self, content: str) -> None:
        self.patch_path.write_text(content, encoding="utf-8")

    def clear_home_patch(self) -> None:
        self.patch_path.unlink(missing_ok=True)

    def env(self) -> dict[str, str]:
        """给子进程用的环境。

        DSH_HOME 经 env 传给子进程，**不改当前进程的环境变量** —— 不存在"忘了恢复"
        的窗口，这是整个实验台的安全边界。
        """
        return {**os.environ, "DSH_HOME": str(self.root)}

    def make_profile(
        self,
        name: str,
        *,
        bundles: list[str] | None = None,
        patch: str = "",
        web: bool = False,
    ) -> LabProfile:
        """建一个裸 profile。

        只写两个文件：
          package.json      —— dsh.profile.bundles 名单，bundle 层从这里来
          cordis.patch.yml  —— 活层

        cordis.yml 不用建：profile-boot 每次启动都会把它重写成空数组 []（防止
        loader 的 tree write-back 把已组合的行烤进文件，导致下次启动 insert 翻倍）。

        绝不叫 `web` —— 那是官方主 profile 的名字。
        """
        if name == "web":
            raise LabError("profile 不许叫 web —— 那是官方主 profile 的名字")

        if bundles is None:
            bundles = [BUNDLE_BASE, BUNDLE_WEB] if web else [BUNDLE_BASE]

        profile = LabProfile(home=self, name=name)
        profile.dir.mkdir(parents=True, exist_ok=True)
        (profile.dir / "package.json").write_text(
            json.dumps(
                {
                    "name": f"dsh-profile-{name}",
                    "private": True,
                    "dsh": {"profile": {"bundles": bundles}},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        profile.write_patch(patch)
        return profile

    def make_minimal_profile(
        self,
        name: str,
        *,
        patch: str = "",
        hmr_root: list[str] | None = None,
    ) -> LabProfile:
        """L0 定出的最小基线：**一个 bundle 都不叠**。

        「能跑起实验的最小插件集合」这个问题，L0 给出的答案是**空集**：
        插件系统的基础设施不由 bundle 提供，而是框架自带的。空树启动后，
        进程里已经有三个条目，全都不在任何 patch 文件里：

            cordis:include  树根。整棵配方树挂在它下面，boot 期就在
            timer           兜底补的。hmr 硬依赖它
            hmr             兜底补的，`root: []`

        兜底的判定条件是 **hmr 服务在不在**（`ctx.get("hmr") === void 0`），
        不是「hmr 条目在不在」—— 所以条目写了但没激活（比如 disabled），
        框架照样会再补一个。

        这条基线相比 `dsh-base`（78 个条目）的好处是决定性的：启动快一截，
        事件流从几百条降到十几条，且流里剩下的每一条都跟被测对象有关。

        Args:
            patch: 追加的活层内容。会拼在基础设施条目**之后** —— 活层是
                YAML 数组，可以有多个 `- insert:` 块，各块独立生效。
            hmr_root: 不传（默认）就用框架兜底那个 `root: []` 的 hmr ——
                够用来监听 patch 文件，但**不监听代码文件**，改插件源码不会
                热重载。要测代码热重载就传监听目录，那时自挂的 timer+hmr
                会让服务提前就位，兜底自然不触发。
        """
        infra = ""
        if hmr_root is not None:
            roots = json.dumps(hmr_root)
            infra = f"""# 自挂基础设施：接管框架兜底，好给 hmr 一个真的 watch root
- insert:
    - id: timer
      name: '{PKG_TIMER}'

    - id: hmr
      name: '{PKG_HMR}'
      config:
        root: {roots}
        debounce: 100

"""
        return self.make_profile(name, bundles=[], patch=infra + patch)

    def clean(self) -> None:
        """删掉整个 home。"""
        if "dsh-mechanics-lab" not in str(self.root):
            raise LabError(f"home 路径不对劲，拒绝删：{self.root}")
        rmtree_safe(self.root)
