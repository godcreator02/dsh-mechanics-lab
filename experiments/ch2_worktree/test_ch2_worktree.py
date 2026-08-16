"""第 11 项 · 换个 tag 就换个版本，进程不重启

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/ch2_worktree/ -n 0 -s

第 9 项里，把包 link 进 profile 之后，「换版本」等于去那个包的目录里改文件。
可那个目录同时也是你写代码的地方 —— 写到一半的东西会立刻被实例吃进去。

这一项是一套通用的做法，把两件事分开：

  * `git worktree` 能给同一个仓开出**第二个工作副本**，两个副本各自有一份文件，
    互不干扰
  * 让第二个副本**钉在一个 tag 上**（不跟着 HEAD 走），profile 的依赖指向它

于是你在第一个副本里怎么改都行，实例看到的永远是那个 tag 上的内容。发一次版
就是在第二个副本里 `git checkout <新 tag>` —— 文件一变，hmr 照旧把插件重新加载
一遍，实例不重启。

这一项要看的重点在第 3 条判定：**一次 checkout 会同时改好几个文件**，
hmr 到底把它们当成一次改动，还是几次。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import (  # noqa: E402
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

#: 教学插件的两个版本。整个目录就是一个包 —— 包名 `greeter`，入口 index.js，
#: 另外两个文件各只导出一个常量。换版本时四个文件（含 package.json）一起变。
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 包名。profile 的依赖写这个名字，patch 里的 `name` 也写这个名字。
PKG = "greeter"

TAG_V1, TAG_V2, TAG_V3 = "v1.0.0", "v2.0.0", "v3.0.0"

#: 插件在每个版本里会说的话。三个字段来自三个不同的文件 —— 只换了一半的话
#: 这里会露出来（比如版本是新的、入口还是旧的）。
SAID_V1 = {"版本": "1.0.0", "招呼语": "早上好", "入口": "第一版"}
SAID_V2 = {"版本": "2.0.0", "招呼语": "晚上好", "入口": "第二版"}

#: 一次 checkout 落下的文件数。判定「几次重载」时拿它作参照。
FILES_PER_CHECKOUT = 4


# ── git ─────────────────────────────────────────────────────────────────────


def _inside_fake_home(path: Path) -> bool:
    """这条路径是不是在假 home 里面。

    整个实验只在假 home 里建仓、开副本、切 tag —— 项目仓库本身绝不能被碰到。
    每条 git 命令的工作目录与每个新副本的落点都过一遍这个判定。
    """
    try:
        return path.resolve().is_relative_to(TESTHOME_ROOT.resolve())
    except OSError:
        return False


def git(cwd: Path, *args: str) -> str:
    """在 `cwd` 这个仓里跑一条 git 命令，返回标准输出。

    两处刻意的做法：

      * **工作目录必须在假 home 里**，否则直接拒绝执行
      * **不读本机的 git 配置**（把两个配置文件指向一个不存在的路径），
        实验结果不受跑它的人配了什么影响 —— 比如 `core.autocrlf` 会改写
        checkout 出来的文件内容，钩子脚本还能在提交时插一脚
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
    """跟着 HEAD 的那个副本 —— 平时改代码就在这里。"""

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
    """搭一个实例：依赖指向**钉在 tag 上的那个副本**。

    跟第 9 项的 link 一模一样，只是链接的目标是一个工作副本而不是源码目录 ——
    从 profile 的角度看，那就是个普通的包。

    hmr 那条要写两个键：

      * `root` 指向那个副本 —— 它不在 profile 目录里面，不写就盯不到
      * `ignored` 也得明写。hmr 判断一个文件要不要忽略，看的是它**相对 profile
        目录**的那条路径；副本在 profile 目录外面，那条路径以 `..` 开头，而
        Windows 上它整条都不含 `/`，于是默认忽略名单里的 `**/.*`（忽略点开头的
        东西）退化成「以点开头就忽略」，把整个副本连人带马吃掉。名单里去掉那一
        条，副本里的文件才看得见。
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
    """等插件说到第 `count` 次为止 —— 验「应该发生的事」用轮询。"""
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
    """等实例起来、插件说完第一句，再多留一秒让启动那一阵彻底走完。

    多留这一秒是为了看得清：不留的话启动和后面那拨事件在时间线上挤在一起。
    判定不依赖它。
    """
    first = wait_until_said(inst, events_path, count=1)
    assert first == [expect], f"实例起来后插件该说一次话（{expect}），实际 {first}：\n{inst.logs()}"
    Instance.settle(1.0)


# ── 时间线 ──────────────────────────────────────────────────────────────────


def hot_timeline(events: list[dict]) -> str:
    """这一项专用的时间线：标准那几类照旧，另把 hmr 自己发的事件也留下。

    `timeline()` 默认不显示 hmr 那几类，而这一项要看的恰恰是它们 —— 一次 checkout
    落下好几个文件，这里能一眼数出 hmr 报了几次重新加载。
    """
    rows = []
    for e in events:
        kind = str(e.get("kind"))
        # 列宽跟 `timeline()` 对齐，两边的行才排得成一张表
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


def at_of(event: dict) -> datetime:
    """一条事件的墙上时钟时刻 —— 用来跟用例这边的时间点对齐。

    事件流里的 `ms` 是相对采集器挂载时刻的，跟用例这边的时间对不上；`at` 是
    绝对时刻，同一台机器上直接可比。
    """
    return datetime.fromisoformat(str(event["at"]))


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_a_pinned_copy_is_just_a_dependency(lab_home: LabHome, repo: Repo, launch):
    """判定 1 · 依赖指向工作副本，插件照常加载 —— 跟普通的 link 没有区别。

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
    """判定 2、3 · `git checkout <新 tag>` → 插件跑新代码，进程 pid 一动不动。

    这是这一项的核心：**发一次版就是在钉住的那个副本里切一次 tag**。四个文件
    同时被换掉，hmr 把这一批当成一次改动，插件重新加载一遍。
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

    assert inst.alive(), f"实例应当一直活着 —— 换版本不是重启：\n{inst.logs()}"
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


@pytest.mark.parametrize("debounce", [100, 1000])
def test_c_one_checkout_is_one_reload(lab_home: LabHome, repo: Repo, launch, debounce: int):
    """判定 3 · 一次 checkout 换掉四个文件，hmr 只重新加载一次。

    这条是这一项最值钱的：换版本跟第 5 项那种「改一行」不一样，一次落下的是一批
    文件。要是 hmr 把这批拆成几次重新加载，中间就会出现「一部分文件是新的、
    另一部分还是旧的」那种半截状态 —— 插件说的三个字段来自三个不同的文件，
    真出现半截状态，这里立刻能看出来。

    合并成一次靠的是 hmr 的 `debounce`：文件一变先攒着，攒到这么多毫秒没有新的
    变动了才真去重新加载。checkout 落四个文件只要几毫秒，所以默认的 100 毫秒就
    足够把它们收成一批。两个档位一起跑，看得出这个窗口是真在起作用：**窗口拉到
    十倍，重新加载还是一次，只是晚了将近一秒才发生**。
    """
    pinned = repo.pin(f"pinned-c-{debounce}", TAG_V1)
    profile, events_path = build(lab_home, f"c-once-{debounce}", pinned, debounce=debounce)

    inst = launch(profile, wait_http=False)
    boot_and_wait_first(inst, events_path, SAID_V1)

    git(pinned, "checkout", TAG_V2)
    done = datetime.now(UTC)  # checkout 落完盘的时刻，用来量「等了多久才重新加载」

    wait_until_said(inst, events_path, count=2)
    Instance.settle(8.0)  # 「不该再有第二次」：固定长等待，不许轮询提前退出
    events = read_events(events_path)
    got = said(events_path)
    waited = [(at_of(e) - done).total_seconds() * 1000 for e in of_kind(events, "hmr-reload")]

    print(f"\n══ 一次换掉四个文件，重新加载几次（debounce {debounce}ms）══")
    print(hot_timeline(events))
    print(f"\n  这次 checkout 落下的文件数：{FILES_PER_CHECKOUT}")
    print(f"  hmr 报的重新加载次数：{reload_count(events)}")
    print(f"  checkout 落完盘之后 {' / '.join(f'{w:.0f}ms' for w in waited)} 才重新加载")
    print(f"  插件说过的话：{got}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert reload_count(events) == 1, f"一次 checkout 该只重新加载一次，实际 {reload_count(events)} 次"
    assert got == [SAID_V1, SAID_V2], f"插件该只多说一次话，实际 {got}"
    # 没有半截状态：每一次说的三个字段都来自同一版
    assert all(d in (SAID_V1, SAID_V2) for d in got), f"出现了几个文件是新的、几个还是旧的的半截状态：{got}"
    # 合并窗口就是 debounce 说的那么长：等待时间随它一起走
    assert waited[0] >= debounce * 0.8, f"重新加载来得比 debounce（{debounce}ms）还早：{waited[0]:.0f}ms"


def test_d_the_dev_copy_moves_on_alone(lab_home: LabHome, repo: Repo, launch):
    """判定 4 · 跟着 HEAD 的那个副本随便改，钉在 tag 上的这个纹丝不动。

    两个工作副本各有一份文件。在第一个副本里改代码、提交、再打个 tag，实例那边
    什么都不会发生 —— 这正是「写到一半的东西不会被实例吃进去」的由来。
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

    assert inst.alive(), f"实例应当活着 —— 另一个副本里的半成品碰不到它：\n{inst.logs()}"
    assert pinned_after == pinned_before, "钉在 tag 上的那个副本的文件不该有任何变化"
    assert repo.head_of(pinned) == pinned_head, "钉住的副本不该跟着动"
    assert git(pinned, "status", "--porcelain") == "", "钉住的副本应当是干净的"
    assert said(events_path) == [SAID_V1], f"插件不该被惊动，实际说过 {said(events_path)}"
