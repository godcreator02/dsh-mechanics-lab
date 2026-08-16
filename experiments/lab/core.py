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

#: 一切运行产物的收口。整个目录 gitignore —— 里面的东西**全部可以重跑再生**，
#: 所以进 git 的只有源（实验代码、教学插件、文档），不含任何一次运行的结果。
#: 根目录因此一眼分得清「哪些是源、哪些是产物」。
OUT_DIR = LAB_ROOT / "out"

#: 假 DSH home 的根，每个实验在下面占一个子目录。跑某一课时先整个清掉再重建，
#: 跑完留着供排查。**这是实验台的安全边界**：`DSH_HOME` 只会指向这下面，
#: 绝不指向 `~/.dsh`。
TESTHOME_ROOT = OUT_DIR / "testhome"

#: 每次运行的观测产物归档。留档是为了跑完能翻（并行之后终端输出交错，
#: 看这里比看 scrollback 靠谱），不是为了长期保存证据 —— 证据的归宿是
#: 各课 README 里的结论，不是原始 json 躺在仓库里。
RESULTS_DIR = OUT_DIR / "results"

#: 本机上可能有别的东西在跑的端口，任何情况下都不许碰
FORBIDDEN_PORTS = (3080, 3239, 3733)

#: 本箱可用端口。上下界都是硬的——3080 与 3100 以上都可能被别的进程占着
LAB_PORT_RANGE = range(3090, 3100)

#: 每个 profile 默认叠的 bundle。dsh-base 是所有 profile 的共同底座；
#: dsh-web-app 只有需要 HTTP 观测面时才要，它很重（几十个条目），
#: 不需要就别加 —— 启动快一大截。
BUNDLE_BASE = "@deepseek-ai/dsh-base"
BUNDLE_WEB = "@deepseek-ai/dsh-web-app"

#: 插件系统的两个基础设施包，基线一律显式写进 patch（见 `make_minimal_profile`）。
#: 它们**不在 profile 自己的 node_modules 下**，但照样能用裸包名引用 —— 靠的是
#: 标准 Node parent-walk：profile 目录往上一层就是 `$DSH_HOME/profiles/node_modules`，
#: 那是 dsh 的 `healScaffoldModuleFallback` 每次 prepareProfile 时幂等维护的
#: 符号链接农场。不存在什么特殊锚点（L0 实测 + 顺调用链核实）。
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
        """后面所有课的基线：**不叠任何 bundle，但显式带上 timer 与 hmr**。

        不叠 bundle 是为了去噪声——`dsh-base` 那 78 个 entry 里只有两个跟插件
        系统本身有关（就是 timer 和 hmr），其余 76 个全是业务线，会往事件流里
        灌几百条与被测对象无关的事件。

        **但基础设施要自己显式带上**，理由是它更贴近真实：`dsh-base` 的 patch
        头两条就是 timer 和 hmr，所以任何真实部署里它们都在。把 base 拿掉是为了
        减噪，不是为了模拟「没有它们」——那个场景现实中不存在。

        显式带上还有两个直接好处：

          * **树的形状完全可预测**，id 是这里给的（`timer` / `hmr`），
            断言可以认 id
          * **不触发框架的 fallback**（`boot()` 返回后判 `ctx.get("hmr")` 那段），
            也就没有随机 id 的 entry 混进树里

        树上唯一不来自 patch 文件的 entry 因此只剩 `cordis:include`——它是树根，
        整份 effective config 装在它的 `config.patches` 里。

        Args:
            patch: 追加的 user patch layer 内容。会拼在基础设施两条**之后**——
                patch 文件是 YAML 数组，可以有多个 `- insert:` 块，各块独立生效。
            hmr_root: hmr 的 watch root，默认 `[]`。空 root 够监听 patch 文件
                （那是按精确路径注册的，与 root 无关），但**不监听代码文件**。
                要测代码热重载就传监听目录。
        """
        roots = json.dumps(hmr_root if hmr_root is not None else [])
        infra = f"""# 基础设施：显式带上，不依赖框架的 fallback
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
        """删掉整个 home。

        护栏判的是「是不是 `TESTHOME_ROOT` 的真子目录」，不是字符串包含 ——
        这个函数会递归删目录，判据必须是结构上的，不能靠路径里碰巧有某个词。
        """
        if self.root.resolve().parent != TESTHOME_ROOT.resolve():
            raise LabError(
                f"home 不在 {TESTHOME_ROOT} 下面，拒绝删：{self.root}"
            )
        rmtree_safe(self.root)
