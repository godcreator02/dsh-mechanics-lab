"""supply-x-activation · 供给 / 激活 / 版本钉法，三条正交轴

档次 ② ｜ 性质 🔬 发现型 + ⚠️ 矫正型 ｜ 状态 ✅ 已实测 ｜ 3 条用例 ｜ 不需要 web

## 判定

- **「把插件接进来」不是一个动作，是三个正交的动作。** **供给**——`name` 怎么被
  resolve 成一个真实文件（相对路径 / junction（link: 到一个包）/ 钉了 tag 的
  git 工作副本）；**激活**——条目怎么进树（bundle 层自注册，即包自己声明
  `dsh.bundle`、且被列进 profile 的 `dsh.profile.bundles` / 活层 `insert`）；
  **版本钉法**——换一版时动哪个文件（改插件代码本身 / 改 bundle 自己的 patch /
  换 git tag，即 worktree checkout）。三条轴自由组合，六种形态是这三条轴挑出来
  的组合：

  | 形态 | 供给 | 激活 |
  |------|------|------|
  | A | 相对路径 | 活层 insert |
  | B | junction | 活层 insert |
  | C | junction | bundle 层自注册 |
  | D | junction（声明了 bundle，但没进名单） | 活层 insert |
  | E | git 工作副本（钉 tag） | 活层 insert |
  | F | git 工作副本（钉 tag） | bundle 层自注册 |

  本项用 A/B/C/D 加 E 横向对照，证据：`test_six_routes_all_land`。A/B/C/D 的
  源码是仓库里现成的 fixtures；E/F 没有对应的 fixtures 目录——它们要的是
  「两个版本 + 两个 tag」，这种东西没法用一份静态文件表达，由本文件自己在一个
  临时 git 仓库（落在假 home 里，见 `make_git_worktree`）写出两版内容、打好
  tag，再 `git worktree add` 出一份工作副本当插件的供给源。
- **供给方式不影响热不热，激活方式才影响。** 相对路径 / junction / git 工作
  副本三种供给在「改代码」这件事上表现完全一致——hmr 一律看得到、一律热重载。
  证据：`test_all_routes_reload_on_code_change`
- **声明了 `dsh.bundle` 不等于会自动生效。** 形态 D 的包也声明了
  `dsh.bundle.patch`、内容跟形态 C 一模一样，但因为没被列进
  `dsh.profile.bundles` 名单，那份 patch（`层版本: d-r1-NEVER-APPLIED`）在整条
  事件流里出现 0 次。证据：`test_six_routes_all_land` 的负面断言
- **一次 `git checkout` 能让供给轴和激活轴分道扬镳。** 形态 F（git 工作副本供给
  + bundle 层自注册）里，一次 `checkout` 同时换了代码文件和 bundle 自己的
  patch 文件；15 秒内代码轴热了（`代码版本` 变成新值），bundle 轴纹丝不动
  （`层版本` 还是旧值）；重启之后 bundle 轴才跟上。观察式：先如实记录 checkout
  之后实际发生了什么，再下断言。证据：
  `test_checkout_moves_code_but_not_the_bundle_layer`

⚠️ **官方文档枚举的是常见组合，三条轴一乘能看出还有别的格子**——形态 D
（声明了 `dsh.bundle` 却没进名单）与形态 F（git 工作副本供给 + bundle 层自
注册）都是枚举容易漏掉的格子，其中形态 D 恰恰是日常最常用的形态之一
（`docs/official/zh/user/develop/basic/publish.md` 讲了两种 manifest 与层顺序，
没有拆出这三条轴）。

## 观测方法

每个教学插件 `apply` 时上报同一个结构：`{ 形态, 代码版本, 层版本 }`。
`代码版本` 是模块顶层常量——供给轴的读数（它变了说明模块被重新 `import`）；
`层版本` 从 `config` 读——激活轴的读数（它变了说明配方重新算过）。两个读数在
同一条记录里，才能看清「一个变了另一个没变」这种分道扬镳。

⚠️ **每个插件的真身都落在 profile 目录里面**（B/C/D 拷贝过去，E/F 的 git 工作
副本直接建在里面），hmr 只配一条 root：`['.']`。这不是图省事，是实测踩出来的
——把工作副本放在 profile 外、另给 hmr 开一条指向它的绝对路径 root，那两个
形态一个 hmr 事件都收不到（hmr 的 watcher 把 chokidar 的 `cwd` 设成 profile
目录，`ignored` 判定走 `relative(profile, path)`，落在外面的路径算出来是以
`..` 起头、不含 `/` 的相对路径）；同一次跑里落在 profile 里的形态全部正常
热重载。详见 `make_git_worktree` 的 docstring。

跨两程的用例（checkout 用例）重启前必须把 `events.jsonl` 挪走：采集器每次
挂载会把它清空重写，但旧进程死掉到新进程写第一行之间有个窗口，这期间轮询会
读到上一程的残留、把「上一程说过的话」当成「这一程已经说了」。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from lab import (
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabError,
    LabHome,
    LabProfile,
    read_events,
    reports,
    states_of,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 形态 × 三轴（版本观测值现场取，这里只放静态的三列）
AXES: dict[str, tuple[str, str, str]] = {
    "A": ("相对路径（profile 目录里的文件）", "活层 insert", "改文件"),
    "B": ("junction（link: 到一个包）", "活层 insert", "改文件"),
    "C": ("junction（link: 到一个包）", "bundle 层自注册", "改文件 / 改 bundle 自己的 patch（冷）"),
    "D": ("junction（声明了 dsh.bundle，但没进名单）", "活层 insert", "改文件"),
    "E": ("git 工作副本（钉 tag）", "活层 insert", "改文件"),
}


# ── 基础设施 patch 块 ─────────────────────────────────────────────────────────


def infra_patch(hmr_roots: list[str], events_path: Path) -> str:
    """timer + hmr + lab-recorder 三条。本项要自己控制 `dsh.profile.bundles`
    （形态 C/F 靠它自注册），所以不走 `make_minimal_profile`，自己拼一份。"""
    roots = json.dumps(hmr_roots)
    return f"""# 基础设施：显式带上，不依赖框架的 fallback
- insert:
    - id: timer
      name: '{PKG_TIMER}'

    - id: hmr
      name: '{PKG_HMR}'
      config:
        root: {roots}
        debounce: 100

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {json.dumps(events_path.as_posix())}
        flushMs: 100
"""


def provision(profile: LabProfile, route_name: str) -> Path:
    """把 `fixtures/<route_name>` 整个拷贝一份到 profile 目录*里面*，返回新路径。

    两个理由缺一不可：

      1. 不弄脏仓库——用例后面无论怎么改代码、改 bundle 自己的 patch，
         动的都是这份拷贝，`fixtures/` 目录永远保持它被交付时的样子。
      2. 落点必须在 profile 目录里面——hmr 的默认 `ignored` 名单里有
         `**/node_modules`，junction 那一层本身就是死路；而真身如果落在
         profile 目录外，即使单独给它开一条绝对路径 root 也收不到变更事件
         （实测，见 `make_git_worktree`）。放在 profile 目录里面搭
         `root: ['.']` 的顺风车是唯一走得通的那条——本项六个形态无一例外。
    """
    dest = profile.dir / route_name
    shutil.copytree(FIXTURES / route_name, dest)
    return dest


# ── E / F 的插件源码：由本文件自己写进一个临时 git 仓库 ───────────────────────


def plugin_source(letter: str, code_version: str) -> str:
    """跟 fixtures 里 A/B/C/D 那几个插件同一个写法，只是形态字母和版本号是参数。"""
    return (
        'export const inject = ["labObserver"];\n'
        f'const CODE_VERSION = "{code_version}";\n'
        "export function apply(ctx, config) {\n"
        "  const say = ctx.labObserver.for(ctx);\n"
        f'  say("我上树了", {{ 形态: "{letter}", 代码版本: CODE_VERSION, 层版本: config?.层版本 ?? null }});\n'
        "}\n"
    )


def package_json(name: str, *, bundle_patch: str | None = None) -> str:
    manifest: dict = {
        "name": name,
        "version": "0.0.0",
        "private": True,
        "type": "module",
        "exports": {".": "./index.js"},
    }
    if bundle_patch:
        manifest["dsh"] = {"bundle": {"patch": bundle_patch}}
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def route_e_files(code_version: str) -> dict[str, str]:
    """形态 E：跟 B 一样是纯包，不声明 `dsh.bundle`——只能靠活层 insert 激活。"""
    return {"package.json": package_json("route-e"), "index.js": plugin_source("E", code_version)}


def route_f_files(code_version: str, layer_version: str) -> dict[str, str]:
    """形态 F：声明 `dsh.bundle.patch`，跟 route-c 是同一个写法——只是供给轴
    换成了 git 工作副本。"""
    return {
        "package.json": package_json("route-f", bundle_patch="./cordis.patch.yml"),
        "index.js": plugin_source("F", code_version),
        "cordis.patch.yml": (
            f"- insert:\n    - id: route-f\n      name: route-f\n      config:\n        层版本: {layer_version}\n"
        ),
    }


def run_git(args: list[str], cwd: Path) -> None:
    """跑一条 git 命令。失败直接抛，把 stderr 带上。"""
    try:
        subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise LabError(f"git {' '.join(args)}（{cwd}）失败：\n{exc.stdout}\n{exc.stderr}") from exc


def _write_files(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _init_git_repo(gitsrc: Path) -> None:
    gitsrc.mkdir(parents=True)
    run_git(["init", "-b", "main"], gitsrc)
    # 只设本仓库的身份，不碰全局配置；顺手关掉 gpg 签名，免得机器全局开了签名
    # 却没配 key，一个纯粹用来演示热重载的临时仓库没必要跟着报错。
    run_git(["config", "user.email", "lab@dsh-mechanics-lab.local"], gitsrc)
    run_git(["config", "user.name", "lab"], gitsrc)
    run_git(["config", "commit.gpgsign", "false"], gitsrc)


def _commit_tag(gitsrc: Path, files: dict[str, str], tag: str) -> None:
    _write_files(gitsrc, files)
    run_git(["add", "-A"], gitsrc)
    run_git(["commit", "-m", tag], gitsrc)
    run_git(["tag", tag], gitsrc)


def make_git_worktree(gitsrc: Path, pinned: Path, files_v1: dict[str, str]) -> Path:
    """建一个最小 git 仓库（落在假 home 里）、打一个 `v1` tag、check 出一份
    worktree，返回 worktree 目录——这就是插件的供给源。

    ⚠️ **`pinned` 必须落在 profile 目录里面**（见本项 README「hmr 只认 watch
    root 覆盖到的文件」一节）：hmr 的 watcher 把 chokidar 的 `cwd` 设成 profile
    目录、`ignored` 判定走 `relative(profile, path)`，落在 profile 外的目录
    即使写进 `config.root` 也收不到变更事件。对照实测：同一套用例，工作副本
    放 profile 外时 E 和 F 一个 hmr 事件都没有、放进来则全部正常热重载，
    其余条件不变。

    主仓库（`gitsrc`）反过来要留在 profile 外：它带一整个 `.git` 目录，扫进
    watch root 纯属给 chokidar 添负担；worktree 那边只有一个指向主仓库的
    `.git` 文件，很轻。

    只负责「供给轴 = 钉 tag 的 git 工作副本」这一件事，不涉及版本钉法——那是
    调用方的事：`test_all_routes_reload_on_code_change` 直接改 worktree 里的
    文件；只有 `test_checkout_moves_code_but_not_the_bundle_layer` 才走
    「整仓库另打一个 tag、checkout 切过去」这条路，见
    `make_git_worktree_two_versions`。
    """
    _init_git_repo(gitsrc)
    _commit_tag(gitsrc, files_v1, "v1")
    run_git(["worktree", "add", str(pinned), "v1"], gitsrc)
    return pinned


def make_git_worktree_two_versions(
    gitsrc: Path, pinned: Path, files_v1: dict[str, str], files_v2: dict[str, str]
) -> tuple[Path, Path]:
    """跟 `make_git_worktree` 一样（`pinned` 落点的约束同样适用），但额外打好
    `v2` tag——给 checkout 切版本这条路用。
    返回 `(主仓库目录, 起初钉在 v1 的 worktree 目录)`。
    """
    _init_git_repo(gitsrc)
    _commit_tag(gitsrc, files_v1, "v1")
    _commit_tag(gitsrc, files_v2, "v2")
    run_git(["worktree", "add", str(pinned), "v1"], gitsrc)
    return gitsrc, pinned


def bump_code_version(path: Path, old: str, new: str) -> None:
    """字符串替换——这就是「在编辑器里改一行」这个动作。"""
    text = path.read_text(encoding="utf-8")
    assert old in text, f"前提：{path} 里本该写着 {old!r}"
    path.write_text(text.replace(old, new), encoding="utf-8")


# ── 观测辅助 ───────────────────────────────────────────────────────────────────


def said(events_path: Path, entry_id: str) -> list[dict]:
    """某个条目上报过的 `data`，按时间顺序。"""
    return [e["data"] for e in reports(read_events(events_path), who=entry_id) if e.get("data")]


def wait_for_all(inst: Instance, events_path: Path, ids: list[str], *, timeout: float = 30.0) -> dict[str, list[dict]]:
    """等一串条目全都至少说过一次话——验「该发生的事」用轮询，比死等快也更稳。"""

    def check() -> dict[str, list[dict]] | None:
        got = {i: said(events_path, i) for i in ids}
        return got if all(got.values()) else None

    return inst.wait_for(check, timeout=timeout, what=f"{ids} 全都说过话")


def wait_for_count(
    inst: Instance, events_path: Path, entry_id: str, *, count: int, timeout: float = 30.0
) -> list[dict]:
    """等某个条目说满 `count` 次话。"""

    def check() -> list[dict] | None:
        got = said(events_path, entry_id)
        return got if len(got) >= count else None

    return inst.wait_for(check, timeout=timeout, what=f"{entry_id} 说满 {count} 次话")


def print_hmr_timeline(events: list[dict]) -> None:
    """跟 `timeline()` 一样，但把 hmr 自己发的三类事件也留下——本项要看的
    恰恰是它们夹在插件说话之间的位置。"""
    rows = []
    for e in events:
        kind = str(e.get("kind"))
        ms = f"{e.get('ms', 0):8.1f}ms"
        if kind == "hmr-change":
            rows.append(f"  {ms}  {kind:<10} {'':<16} 文件变了：{Path(str(e.get('url'))).name}")
        elif kind == "hmr-reload":
            files = [Path(str(f)).name for f in (e.get("files") or [])]
            rows.append(f"  {ms}  {kind:<10} {'':<16} 重新加载了 {e.get('count')} 个：{files}")
        elif kind == "hmr-failed":
            rows.append(f"  {ms}  {kind:<10} {'':<16} 失败：{e.get('error')}")
        else:
            row = timeline([e])
            if row:
                rows.append(row)
    print("\n".join(rows))


# ── 搭台 ───────────────────────────────────────────────────────────────────────


def build_five_routes(lab_home: LabHome, label: str) -> dict:
    """搭一个同时挂 A/B/C/D/E 五种形态的 profile。

    返回一个 dict：`profile` / `events_path` / `code_files`（每个形态代码文件
    的路径，供用例原地改 `CODE_VERSION`）/ `pinned_e`（E 的 git 工作副本目录）。
    """
    events_path = lab_home.root / f"events-{label}.jsonl"
    live_insert = """- insert:
    - id: route-a
      name: ./route-a.mjs

    - id: route-b
      name: route-b

    - id: route-d
      name: route-d
      config:
        层版本: d-live1

    - id: route-e
      name: route-e
      config:
        层版本: e-live1
"""
    # hmr 只给一条 root：profile 目录自己。E 的 git 工作副本就建在这个目录*里面*，
    # 搭这条 root 的顺风车——落在外面的 root 收不到变更事件，见 `make_git_worktree`。
    profile = lab_home.make_profile(label, bundles=["route-c"], patch=infra_patch(["."], events_path) + live_insert)
    profile.link_plugin("lab-recorder", OBSERVER)

    # 主仓库留在 profile 外（带整个 .git，不该扫进 watch root），工作副本落在里面。
    pinned_e = make_git_worktree(lab_home.root / f"{label}-e-git", profile.dir / "route-e-src", route_e_files("e-v1"))

    plugin_a = profile.dir / "route-a.mjs"
    shutil.copy2(FIXTURES / "route-a.mjs", plugin_a)

    route_b_dir = provision(profile, "route-b")
    profile.link_plugin("route-b", route_b_dir)

    route_c_dir = provision(profile, "route-c")
    profile.link_plugin("route-c", route_c_dir)

    route_d_dir = provision(profile, "route-d")
    profile.link_plugin("route-d", route_d_dir)

    profile.link_plugin("route-e", pinned_e)

    return {
        "profile": profile,
        "events_path": events_path,
        "pinned_e": pinned_e,
        "code_files": {
            "route-a": plugin_a,
            "route-b": route_b_dir / "index.js",
            "route-c": route_c_dir / "index.js",
            "route-d": route_d_dir / "index.js",
            "route-e": pinned_e / "index.js",
        },
    }


def build_f_only(lab_home: LabHome, label: str) -> dict:
    """单独一个 profile，只装形态 F：git 工作副本供给 + bundle 层自注册。
    活层什么都不写——route-f 完全靠 bundle 自己那份 patch 上树。
    """
    events_path = lab_home.root / f"events-{label}.jsonl"
    # 同 `build_five_routes`：root 只给 profile 目录自己，工作副本建在它里面。
    profile = lab_home.make_profile(label, bundles=["route-f"], patch=infra_patch(["."], events_path))
    profile.link_plugin("lab-recorder", OBSERVER)

    gitsrc, pinned_f = make_git_worktree_two_versions(
        lab_home.root / f"{label}-f-git",
        profile.dir / "route-f-src",
        route_f_files("f-v1", "f-r1"),
        route_f_files("f-v2", "f-r2"),
    )
    profile.link_plugin("route-f", pinned_f)

    return {"profile": profile, "events_path": events_path, "gitsrc": gitsrc, "pinned_f": pinned_f}


# ── 用例 1 · 六种形态里，这一条挂 A/B/C/D/E 五种 ───────────────────────────────


def test_six_routes_all_land(lab_home: LabHome, launch):
    """五种供给 × 激活组合能不能真的把插件送上树。

    形态 A/B/D/E 走的是活层 insert，形态 C 完全不同——它靠「包自己声明了
    `dsh.bundle` + 被列进 profile 的 `dsh.profile.bundles`」这两个条件同时
    成立，在 boot 阶段自注册进配方，活层这边什么都不用写。

    最要紧的负面断言在最后：D 的包里也声明了 `dsh.bundle`，内容跟 C 一模一样，
    但因为没被列进 bundles 名单，那份 patch（`层版本: d-r1-NEVER-APPLIED`）
    在任何一条事件里都不该出现——「声明了」不等于「会自动生效」。
    """
    built = build_five_routes(lab_home, "landing")
    profile, events_path = built["profile"], built["events_path"]
    ids = list(built["code_files"])

    inst = launch(profile, wait_http=False)
    landed = wait_for_all(inst, events_path, ids, timeout=30.0)
    events = read_events(events_path)

    print("\n══ 五种形态，三条轴上的取值 ══════════════════════════════")
    print(f"  {'形态':<4}{'供给':<44}{'激活':<18}{'版本钉法':<32}{'代码版本':<10}层版本")
    for letter, entry_id in zip("ABCDE", ids, strict=True):
        supply, activation, pin = AXES[letter]
        data = landed[entry_id][-1]
        layer = data.get("层版本")
        layer_text = layer if layer is not None else "—"
        print(f"  {letter:<4}{supply:<44}{activation:<18}{pin:<32}{data['代码版本']:<10}{layer_text}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    for letter, entry_id in zip("ABCDE", ids, strict=True):
        assert landed[entry_id][-1]["形态"] == letter, f"{entry_id} 该报形态 {letter}，实际 {landed[entry_id][-1]}"
        assert "ACTIVE" in states_of(events, entry_id), f"{entry_id} 该走到 ACTIVE，实际 {states_of(events, entry_id)}"

    never_applied = [e for e in reports(events) if (e.get("data") or {}).get("层版本") == "d-r1-NEVER-APPLIED"]
    print(f"\nd-r1-NEVER-APPLIED 出现过几次：{len(never_applied)}（该是 0）")
    assert not never_applied, f"D 那份「声明了但没进名单」的 bundle patch 不该被读到，实际出现：{never_applied}"


# ── 用例 2 · 改代码这件事上，三种供给形态表现一致 ──────────────────────────────


def test_all_routes_reload_on_code_change(lab_home: LabHome, launch):
    """逐个把五个插件的 `CODE_VERSION` 从 `x-v1` 改成 `x-v2`。

    改的都是插件的真身所在文件——A 是拷进 profile 目录的文件本身，B/C/D 是
    拷进 profile 目录的包副本，E 是 git 工作副本里的文件。三种供给形态在
    「改代码」这件事上表现完全一致：hmr 一律能看到、一律热重载，不需要重启。
    这条用例建立的正是这个对照：供给轴的取值不影响热不热，热不热由 hmr 的
    `root` 有没有盯到那个目录决定。
    """
    built = build_five_routes(lab_home, "reload")
    profile, events_path, code_files = built["profile"], built["events_path"], built["code_files"]
    ids = list(code_files)

    inst = launch(profile, wait_http=False)
    first = wait_for_all(inst, events_path, ids, timeout=30.0)

    print("\n══ 起初五条都说了各自的 v1 ═══════════════════════════════")
    for entry_id in ids:
        letter = entry_id.split("-")[1]
        data = first[entry_id][-1]
        print(f"  {entry_id}: {data}")
        assert data["代码版本"] == f"{letter}-v1", f"{entry_id} 首次该说 {letter}-v1，实际 {data}"

    print("\n══ 逐个改代码，逐个等它重新说话 ══════════════════════════")
    for entry_id, path in code_files.items():
        letter = entry_id.split("-")[1]
        bump_code_version(path, f"{letter}-v1", f"{letter}-v2")
        got = wait_for_count(inst, events_path, entry_id, count=2, timeout=20.0)
        print(f"  {entry_id} 改代码后说的第二句：{got[-1]}")
        assert got[-1]["代码版本"] == f"{letter}-v2", f"{entry_id} 该说到新代码，实际 {got[-1]}"
        assert inst.alive(), f"{entry_id} 改完代码后实例不该死——热重载不是重启：\n{inst.logs()}"

    print("\n══ 完整时间线（含 hmr 自己发的事件）══════════════════════")
    print_hmr_timeline(read_events(events_path))


# ── 用例 3 · 一次 checkout，供给轴和激活轴分道扬镳 ─────────────────────────────


def test_checkout_moves_code_but_not_the_bundle_layer(lab_home: LabHome, launch):
    """形态 F：git 工作副本供给 + bundle 层自注册。一次 `git checkout v2` 同时
    改了两样东西——`index.js` 的 `CODE_VERSION`（供给轴）和
    `cordis.patch.yml` 的 `层版本`（激活轴）。

    写成观察式：先如实记录 checkout 之后实际发生了什么，再下断言。
    """
    built = build_f_only(lab_home, "checkout")
    profile, events_path = built["profile"], built["events_path"]
    pinned_f = built["pinned_f"]

    inst = launch(profile, wait_http=False)
    first = inst.wait_for(lambda: said(events_path, "route-f"), timeout=30.0, what="route-f 上树说话")
    print(f"\n══ checkout 之前 ═════════════════════════════════════════\n  route-f：{first[-1]}")
    assert first[-1]["代码版本"] == "f-v1", f"起初该是 f-v1，实际 {first[-1]}"
    assert first[-1]["层版本"] == "f-r1", f"起初该是 f-r1，实际 {first[-1]}"

    run_git(["checkout", "v2"], pinned_f)

    # 观察式：不用会抛异常的 wait_for——不管它有没有重新说话，都要把观察到的
    # 原样记下来。用轮询而不是死等，是因为「有没有重新说话」这半边是「该发生
    # 的事」，轮询更快也更稳；15s 封顶，超时就是「观察到没有再说话」这个结果本身。
    deadline = time.monotonic() + 15.0
    got = list(first)
    while time.monotonic() < deadline:
        got = said(events_path, "route-f")
        if len(got) > len(first):
            break
        time.sleep(0.3)

    events = read_events(events_path)
    hmr_seen = [e for e in events if str(e.get("kind", "")).startswith("hmr")]
    print("\n══ git checkout v2 之后（观察，不预设结论）══════════════")
    print(f"  route-f 说过几次话：checkout 前 {len(first)} 次 → 此刻 {len(got)} 次")
    print(f"  route-f 最新一句：{got[-1] if got else '（没有新的一句）'}")
    print(f"  实例还活着？{inst.alive()}")
    print(f"  hmr 相关事件：{[e.get('kind') for e in hmr_seen]}")
    for e in hmr_seen:
        print(f"    {e}")

    assert inst.alive(), f"checkout 不该弄死实例：\n{inst.logs()}"
    assert len(got) > len(first), f"预期供给轴的文件变了、hmr 该重新加载，实测 checkout 后 15s 内一句新话都没说：{got}"

    observed_code_version = got[-1]["代码版本"]
    observed_layer_version = got[-1]["层版本"]
    print(f"\n实测：代码版本 = {observed_code_version!r}，层版本 = {observed_layer_version!r}")
    assert observed_code_version == "f-v2", f"预期供给轴热了、代码版本该变成 f-v2，实测 {observed_code_version!r}"
    assert observed_layer_version == "f-r1", (
        f"预期 bundle 层是 boot 时的闭包快照、不会因为磁盘文件变了就重读，"
        f"层版本该仍是 f-r1，实测 {observed_layer_version!r}"
    )

    # ── 重启，确认 bundle 层最终确实吃到了 v2（不是永远读不到，只是不会热） ────
    inst.stop()
    events_path.replace(events_path.with_name(events_path.stem + "-before-restart.jsonl"))
    inst = launch(profile, wait_http=False)
    restarted = inst.wait_for(lambda: said(events_path, "route-f"), timeout=30.0, what="重启后 route-f 说话")
    print(f"\n══ 重启后 ═══════════════════════════════════════════════\n  route-f：{restarted[-1]}")
    assert restarted[-1]["层版本"] == "f-r2", f"重启后该读到新的 bundle 层，实测 {restarted[-1]}"
    assert restarted[-1]["代码版本"] == "f-v2", f"重启后代码版本也该是 f-v2，实测 {restarted[-1]}"
