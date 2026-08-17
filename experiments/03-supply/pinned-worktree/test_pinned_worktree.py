"""pinned-worktree · 依赖指向一份钉住的 git 工作副本，换 tag 即换版本

档次 ① ｜ 性质 🔬 发现型 ｜ 状态 ✅ 已实测 ｜ 3 条用例 ｜ 不需要 web

## 判定

- **依赖指向一份钉在 tag 上的 git 工作副本，插件照常加载——跟普通的
  junction 没有区别，只是它认的是 tag 不是 HEAD。** 另一个跟着 HEAD 走的副本
  此刻在第二版，被钉住的这份仍然报第一版。证据：
  `test_a_pinned_copy_is_just_a_dependency`
- **`git checkout <新 tag>` 换掉插件跑的代码，进程 pid 一动不动。** 发一次版
  就是在钉住的那个副本里切一次 tag：旧的条目被拆掉（`DISPOSED`）、新的挂上
  （`ACTIVE`），走的是热重载那条路，不是重启；别的条目不受牵连。证据：
  `test_b_checkout_swaps_the_version_in_place`
- **跟着 HEAD 走的那个副本随便改、提交、打 tag，钉住的这份纹丝不动。** 两个
  工作副本各有一份文件，互不干扰——这正是「写到一半的东西不会被实例吃进去」
  的由来。证据：`test_d_the_dev_copy_moves_on_alone`

## 观测方法

`git worktree` 能给同一个仓开出第二个工作副本，两个副本各自有一份文件、互不
干扰；让第二个副本钉在一个 tag 上（不跟着 HEAD 走），profile 的依赖指向它。
于是开发副本里怎么改都行，实例看到的永远是那个 tag 上的内容；发一次版就是在
第二个副本里 `git checkout <新 tag>`——文件一变，hmr 照旧把插件重新加载一遍，
实例不重启。

判据落在插件自己上报的三个字段（版本 / 招呼语 / 入口）上，三个字段来自三个不同
的文件——换版本只改了一半的话，这里立刻能看出来。事件流里还看 `status` 事件
的 `ACTIVE`/`DISPOSED` 计数，判「热重载」还是「重启」：pid 不变 + 旧条目走过
`DISPOSED` 才是热重载。

## 没覆盖到的

- 一次 `checkout` 同时落下好几个文件，hmr 会不会把它们合并成一次重新加载
  ——这是同一组 `reload-debounce` 项要验的，本项不涉及
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import pytest
from lab import (
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    TESTHOME_ROOT,
    Instance,
    LabError,
    LabHome,
    LabProfile,
    of_kind,
    read_events,
    reports,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"

#: 教学插件的两个版本。整个目录就是一个包——包名 `greeter`，入口 index.js，
#: 另外两个文件各只导出一个常量。换版本时四个文件（含 package.json）一起变。
FIXTURES = Path(__file__).resolve().parent / "fixtures"

PKG = "greeter"

TAG_V1, TAG_V2, TAG_V3 = "v1.0.0", "v2.0.0", "v3.0.0"

#: 插件在每个版本里会说的话。三个字段来自三个不同的文件——只换了一半的话
#: 这里会露出来（比如版本是新的、入口还是旧的）。
SAID_V1 = {"版本": "1.0.0", "招呼语": "早上好", "入口": "第一版"}
SAID_V2 = {"版本": "2.0.0", "招呼语": "晚上好", "入口": "第二版"}


# ── git ─────────────────────────────────────────────────────────────────────


def _inside_fake_home(path: Path) -> bool:
    """这条路径是不是在假 home 里面。整个实验只在假 home 里建仓、开副本、切
    tag——项目仓库本身绝不能被碰到。"""
    try:
        return path.resolve().is_relative_to(TESTHOME_ROOT.resolve())
    except OSError:
        return False


def git(cwd: Path, *args: str) -> str:
    """在 `cwd` 这个仓里跑一条 git 命令，返回标准输出。

    工作目录必须在假 home 里，否则拒绝执行；不读本机的 git 配置（把两个配置
    文件指向一个不存在的路径），实验结果不受跑它的人配了什么影响——比如
    `core.autocrlf` 会改写 checkout 出来的文件内容，钩子脚本还能在提交时插一脚。
    """
    if not _inside_fake_home(cwd):
        raise LabError(f"git 的工作目录不在假 home 里，拒绝执行：{cwd}")

    nowhere = str(TESTHOME_ROOT / "no-such-git-config")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": nowhere, "GIT_CONFIG_SYSTEM": nowhere}
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )
    if proc.returncode != 0:
        raise LabError(f"git {' '.join(args)} 失败（退出码 {proc.returncode}）：\n{proc.stdout}\n{proc.stderr}")
    return (proc.stdout or "").strip()


def copy_version(src: Path, dest: Path) -> None:
    """把某一版的全部文件铺进目录（覆盖同名的）。"""
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        shutil.copy2(f, dest / f.name)


@dataclass
class Repo:
    """假 home 里的一个 git 仓：一个跟着 HEAD 的工作副本 + 若干钉在 tag 上的副本。"""

    dev: Path
    """跟着 HEAD 的那个副本。"""

    def pin(self, name: str, tag: str) -> Path:
        """开一个钉在 `tag` 上的工作副本，返回它的目录。

        `--detach` 是明写的：这个副本不跟任何分支，只钉在那个 tag 上。
        """
        dest = self.dev.parent / name
        if not _inside_fake_home(dest):
            raise LabError(f"工作副本的落点不在假 home 里，拒绝创建：{dest}")
        git(self.dev, "worktree", "add", "--detach", str(dest), tag)
        return dest

    def head_of(self, copy: Path) -> str:
        return git(copy, "rev-parse", "--short", "HEAD")


@pytest.fixture(scope="module")
def repo(lab_home: LabHome) -> Iterator[Repo]:
    """建一个仓，提交两版、各打一个 tag。整个过程全在假 home 里。

    做完之后：仓里有 v1.0.0 和 v2.0.0 两个 tag，跟着 HEAD 的那个副本停在第二版。
    """
    dev = lab_home.root / "repo"
    dev.mkdir(parents=True, exist_ok=True)

    git(dev, "init", "-b", "main")
    git(dev, "config", "user.name", "lab")
    git(dev, "config", "user.email", "lab@example.invalid")
    git(dev, "config", "core.autocrlf", "false")

    copy_version(FIXTURES / "v1", dev)
    git(dev, "add", "-A")
    git(dev, "commit", "-m", "第一版")
    git(dev, "tag", TAG_V1)

    copy_version(FIXTURES / "v2", dev)
    git(dev, "add", "-A")
    git(dev, "commit", "-m", "第二版")
    git(dev, "tag", TAG_V2)

    yield Repo(dev=dev)


# ── 实例 ────────────────────────────────────────────────────────────────────

BASE = """- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'
      config:
        root: ['{root}']
        ignored: ['**/node_modules']
        debounce: {debounce}

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100

- insert:
    - id: greeter
      name: {pkg}
"""


def build(lab_home: LabHome, name: str, pinned: Path, *, debounce: int = 100) -> tuple[LabProfile, Path]:
    """搭一个实例：依赖指向钉在 tag 上的那个副本。

    跟普通的 junction 一模一样，只是链接的目标是一个工作副本而不是源码目录
    ——从 profile 的角度看，那就是个普通的包。

    hmr 那条要写两个键：

      * `root` 指向那个副本——它不在 profile 目录里面，不写就盯不到
      * `ignored` 也得明写。hmr 判断一个文件要不要忽略，看的是它**相对 profile
        目录**的那条路径；副本在 profile 目录外面，那条路径以 `..` 开头，而
        Windows 上它整条都不含 `/`，于是默认忽略名单里的 `**/.*`（忽略点开头
        的东西）退化成「以点开头就忽略」，把整个副本连人带马吃掉。名单里去掉
        那一条，副本里的文件才看得见。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = BASE.format(
        timer=PKG_TIMER,
        hmr=PKG_HMR,
        root=pinned.as_posix(),
        debounce=debounce,
        out=json.dumps(events.as_posix()),
        pkg=PKG,
    )
    profile = lab_home.make_profile(name, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    profile.link_plugin(PKG, pinned)
    return profile, events


def said(path: Path) -> list[dict]:
    """插件说过的话，按时间顺序。每条都是那三个字段。"""
    return [e["data"] for e in reports(read_events(path), who="greeter") if e.get("data")]


def wait_until_said(inst: Instance, path: Path, *, count: int, timeout: float = 40.0) -> list[dict]:
    """等插件说到第 `count` 次为止——验「该发生的事」用轮询。"""
    got: list[dict] = []

    def enough() -> bool:
        nonlocal got
        got = said(path)
        return len(got) >= count or not inst.alive()

    # 等不到也不在这里判死：拿到几条就返回几条，由调用方的断言给出人话的失败信息
    with suppress(AssertionError):
        inst.wait_for(enough, timeout=timeout, interval=0.3, what=f"插件说满 {count} 次")
    return got


def boot_and_wait_first(inst: Instance, events_path: Path, expect: dict) -> None:
    """等实例起来、插件说完第一句，再多留一秒让启动那一阵彻底走完（不影响判定，
    只是让时间线看得清）。"""
    first = wait_until_said(inst, events_path, count=1)
    assert first == [expect], f"实例起来后插件该说一次话（{expect}），实际 {first}：\n{inst.logs()}"
    Instance.settle(1.0)


# ── 时间线 ──────────────────────────────────────────────────────────────────


def hot_timeline(events: list[dict]) -> str:
    """标准那几类照旧，另把 hmr 自己发的事件也留下——一次 checkout 落下好几个
    文件，这里能一眼数出 hmr 报了几次重新加载。"""
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
        elif kind == "status":
            who = e.get("id") or f"({e.get('name')})"
            rows.append(f"  {ms}  {kind:<10} {str(who):<16} {e.get('from')} → {e.get('to')}")
        else:
            row = timeline([e])
            if row:
                rows.append(row)
    return "\n".join(rows)


def reload_count(events: list[dict]) -> int:
    return len(of_kind(events, "hmr-reload"))


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_a_pinned_copy_is_just_a_dependency(lab_home: LabHome, repo: Repo, launch):
    """依赖指向工作副本，插件照常加载——跟普通的 link 没有区别。

    顺带证明了它认的是 tag 不是 HEAD：此刻跟着 HEAD 的那个副本已经在第二版了，
    实例说的仍然是第一版。
    """
    pinned = repo.pin("pinned-a", TAG_V1)
    profile, events_path = build(lab_home, "a-pinned", pinned)

    inst = launch(profile, wait_http=False)
    got = wait_until_said(inst, events_path, count=1)

    print("\n══ 依赖指向钉在 tag 上的工作副本 ═════════════════════════")
    print(f"  跟着 HEAD 的副本   {repo.dev}  →  HEAD {repo.head_of(repo.dev)}（第二版）")
    print(f"  钉在 tag 上的副本  {pinned}  →  {TAG_V1}")
    print(f"  profile 的依赖     {PKG} → 钉在 tag 上的那个副本")
    print(f"\n  插件说的：{got}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [SAID_V1], f"插件该报第一版（{SAID_V1}），实际 {got}"
    assert repo.head_of(repo.dev) != repo.head_of(pinned), "两个副本此刻不该停在同一个提交上"


def test_b_checkout_swaps_the_version_in_place(lab_home: LabHome, repo: Repo, launch):
    """`git checkout <新 tag>` → 插件跑新代码，进程 pid 一动不动。

    发一次版就是在钉住的那个副本里切一次 tag：四个文件同时被换掉，hmr 把这一批
    当成一次改动，插件重新加载一遍。
    """
    pinned = repo.pin("pinned-b", TAG_V1)
    profile, events_path = build(lab_home, "b-checkout", pinned)

    inst = launch(profile, wait_http=False)
    boot_and_wait_first(inst, events_path, SAID_V1)
    pid_before = inst.proc.pid

    # ── 发版就这一条命令 ──
    git(pinned, "checkout", TAG_V2)

    got = wait_until_said(inst, events_path, count=2)
    Instance.settle(3.0)  # 万一还有第二拨重新加载，留足时间让它冒出来
    events = read_events(events_path)

    print("\n══ 在钉住的副本里切到新 tag ══════════════════════════════")
    print(hot_timeline(events))
    print(f"\n  插件说过的话：{said(events_path)}")
    print(f"  hmr 报的重新加载次数：{reload_count(events)}")
    print(f"  进程 pid：{pid_before} → {inst.proc.pid}")

    assert inst.alive(), f"实例应当一直活着——换版本不是重启：\n{inst.logs()}"
    assert inst.proc.pid == pid_before, "pid 不该变"
    assert got == [SAID_V1, SAID_V2], f"该说两次、第二次是新 tag 上的内容，实际 {got}"

    # 换版本走的是热重载那条路：旧的拆掉、新的挂上，都在同一条事件流里
    states = [e.get("to") for e in events if e.get("kind") == "status" and e.get("id") == "greeter"]
    assert states.count("ACTIVE") == 2, f"应当有两次 ACTIVE（旧的一次、新的一次），实际 {states}"
    assert "DISPOSED" in states, f"旧的那个应当被拆掉，实际走过 {states}"

    # 别的条目不受牵连
    for other in ("timer", "hmr", "lab-recorder"):
        other_states = [e.get("to") for e in events if e.get("kind") == "status" and e.get("id") == other]
        assert "DISPOSED" not in other_states, f"{other} 不该被牵连，却走过 {other_states}"


def test_d_the_dev_copy_moves_on_alone(lab_home: LabHome, repo: Repo, launch):
    """跟着 HEAD 的那个副本随便改，钉在 tag 上的这个纹丝不动。

    两个工作副本各有一份文件。在第一个副本里改代码、提交、再打个 tag，实例那边
    什么都不会发生——这正是「写到一半的东西不会被实例吃进去」的由来。
    """
    pinned = repo.pin("pinned-d", TAG_V1)
    profile, events_path = build(lab_home, "d-independent", pinned)

    inst = launch(profile, wait_http=False)
    boot_and_wait_first(inst, events_path, SAID_V1)

    pinned_before = {f.name: f.read_text(encoding="utf-8") for f in sorted(pinned.glob("*.js"))}
    pinned_head = repo.head_of(pinned)

    # 在跟着 HEAD 的那个副本里放开手改：三个文件全动，提交，再打个 tag
    (repo.dev / "version.js").write_text('export const version = "3.0.0";\n', encoding="utf-8")
    (repo.dev / "greeting.js").write_text('export const greeting = "改到一半";\n', encoding="utf-8")
    (repo.dev / "index.js").write_text("// 改到一半，连语法都不完整 export function apply(\n", encoding="utf-8")
    git(repo.dev, "add", "-A")
    git(repo.dev, "commit", "-m", "第三版（还在改）")
    git(repo.dev, "tag", TAG_V3)

    Instance.settle(15.0)  # 「什么都不该发生」：固定长等待
    pinned_after = {f.name: f.read_text(encoding="utf-8") for f in sorted(pinned.glob("*.js"))}

    print("\n══ 一个副本随便改，另一个纹丝不动 ═══════════════════════")
    print(hot_timeline(read_events(events_path)))
    print(f"\n  跟着 HEAD 的副本  HEAD {repo.head_of(repo.dev)}（第三版，index.js 连语法都是坏的）")
    print(
        f"  钉在 tag 上的副本  HEAD {repo.head_of(pinned)}  ·  改动 {git(pinned, 'status', '--porcelain') or '（无）'}"
    )
    print(f"  插件说过的话：{said(events_path)}")

    assert inst.alive(), f"实例应当活着——另一个副本里的半成品碰不到它：\n{inst.logs()}"
    assert pinned_after == pinned_before, "钉在 tag 上的那个副本的文件不该有任何变化"
    assert repo.head_of(pinned) == pinned_head, "钉住的副本不该跟着动"
    assert git(pinned, "status", "--porcelain") == "", "钉住的副本应当是干净的"
    assert said(events_path) == [SAID_V1], f"插件不该被惊动，实际说过 {said(events_path)}"
