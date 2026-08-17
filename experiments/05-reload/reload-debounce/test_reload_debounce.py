"""reload-debounce · 一次 checkout 只重新加载一次

档次 ② ｜ 性质 🔬 ｜ 状态 ✅ ｜ 1 条用例（跑两个 debounce 档位） ｜ 不需要 web

## 判定

- **一次 checkout 换掉四个文件，hmr 只重新加载一次**，不会出现「一部分文件
  是新的、另一部分还是旧的」的半截状态——插件一次上报的三个字段来自三个
  不同文件，真出现半截状态会立刻露馅。
- **合并靠的是 `debounce`**：文件一变先攒着，攒到这么多毫秒没有新的变动了
  才真去重新加载。checkout 落四个文件只要几毫秒，默认 100ms 就足够收成一批；
  把窗口拉到十倍（1000ms），重新加载次数还是一次，只是整体推迟了将近一秒——
  这条证明窗口是真的在起作用，不是巧合。

`test_c_one_checkout_is_one_reload`（`@pytest.mark.parametrize("debounce",
[100, 1000])`）

## 观测方法

`hmr-reload` 事件的条数直接判「重新加载了几次」；插件上报的三个字段
（版本/招呼语/入口）必须整体属于 `SAID_V1` 或 `SAID_V2` 其中一组，出现不属于
任一组的组合就是半截状态。`at` 字段（墙上时钟绝对时刻）与 checkout 落盘
时刻相减，量出「等了多久才重新加载」，用来验证这个延迟确实随 `debounce`
的档位变化。

工作副本在 profile 目录外面，hmr 的 `ignored` 必须显式重述、去掉默认的
`**/.*`——这条坑与其机制（Windows 上向上走的相对路径被隐藏文件规则误伤）
详见 ignore-rules 项，本项 `build()` 里直接按验过的配置写死，不重新论证。
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

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
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

PKG = "greeter"
TAG_V1, TAG_V2 = "v1.0.0", "v2.0.0"

SAID_V1 = {"版本": "1.0.0", "招呼语": "早上好", "入口": "第一版"}
SAID_V2 = {"版本": "2.0.0", "招呼语": "晚上好", "入口": "第二版"}

#: 一次 checkout 落下的文件数（index.js / version.js / greeting.js / package.json）。
FILES_PER_CHECKOUT = 4


# ── git ─────────────────────────────────────────────────────────────────────


def _inside_fake_home(path: Path) -> bool:
    """这条路径是不是在假 home 里面。整个实验只在假 home 里建仓、开副本、切
    tag——项目仓库本身绝不能被碰到。
    """
    try:
        return path.resolve().is_relative_to(TESTHOME_ROOT.resolve())
    except OSError:
        return False


def git(cwd: Path, *args: str) -> str:
    """在 `cwd` 这个仓里跑一条 git 命令。工作目录必须在假 home 里，否则拒绝
    执行；不读本机的 git 配置（`core.autocrlf` 会改写 checkout 出来的文件
    内容，钩子脚本还能在提交时插一脚）。
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
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.iterdir()):
        shutil.copy2(f, dest / f.name)


@dataclass
class Repo:
    """假 home 里的一个 git 仓：一个跟着 HEAD 的工作副本 + 若干钉在 tag 上的副本。"""

    dev: Path

    def pin(self, name: str, tag: str) -> Path:
        """开一个钉在 `tag` 上的工作副本（`--detach`，不跟任何分支）。"""
        dest = self.dev.parent / name
        if not _inside_fake_home(dest):
            raise LabError(f"工作副本的落点不在假 home 里，拒绝创建：{dest}")
        git(self.dev, "worktree", "add", "--detach", str(dest), tag)
        return dest


@pytest.fixture(scope="module")
def repo(lab_home: LabHome) -> Iterator[Repo]:
    """建一个仓，提交两版、各打一个 tag。整个过程全在假 home 里。"""
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

    hmr 那条要写两个键：`root` 指向那个副本（不在 profile 目录里面，不写就
    盯不到）；`ignored` 也得明写去掉 `**/.*`——副本在 profile 目录外面，
    默认忽略名单里那条会把整个副本连人带马吃掉（机制见 ignore-rules 项）。
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
    return [e["data"] for e in reports(read_events(path), who="greeter") if e.get("data")]


def wait_until_said(inst: Instance, path: Path, *, count: int, timeout: float = 40.0) -> list[dict]:
    got: list[dict] = []

    def enough() -> bool:
        nonlocal got
        got = said(path)
        return len(got) >= count or not inst.alive()

    with suppress(AssertionError):
        inst.wait_for(enough, timeout=timeout, interval=0.3, what=f"插件说满 {count} 次")
    return got


def boot_and_wait_first(inst: Instance, events_path: Path, expect: dict) -> None:
    first = wait_until_said(inst, events_path, count=1)
    assert first == [expect], f"实例起来后插件该说一次话（{expect}），实际 {first}：\n{inst.logs()}"
    Instance.settle(1.0)


def reload_count(events: list[dict]) -> int:
    return len(of_kind(events, "hmr-reload"))


def at_of(event: dict) -> datetime:
    """一条事件的墙上时钟时刻——事件流里的 `ms` 是相对采集器挂载时刻的，跟
    用例这边的时间点对不上，`at` 是绝对时刻，同一台机器上直接可比。
    """
    return datetime.fromisoformat(str(event["at"]))


@pytest.mark.parametrize("debounce", [100, 1000])
def test_c_one_checkout_is_one_reload(lab_home: LabHome, repo: Repo, launch, debounce: int):
    """一次 checkout 换掉四个文件，hmr 只重新加载一次，不出现半截状态。

    合并成一次靠的是 `debounce`：checkout 落四个文件只要几毫秒，默认 100ms
    就足够把它们收成一批。两个档位一起跑，看得出这个窗口是真在起作用——
    窗口拉到十倍，重新加载还是一次，只是晚了将近一秒才发生。
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

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert reload_count(events) == 1, f"一次 checkout 该只重新加载一次，实际 {reload_count(events)} 次"
    assert got == [SAID_V1, SAID_V2], f"插件该只多说一次话，实际 {got}"
    # 没有半截状态：每一次说的三个字段都来自同一版
    assert all(d in (SAID_V1, SAID_V2) for d in got), f"出现了几个文件是新的、几个还是旧的的半截状态：{got}"
    # 合并窗口就是 debounce 说的那么长：等待时间随它一起走
    assert waited and waited[0] >= debounce * 0.8, f"重新加载来得比 debounce（{debounce}ms）还早：{waited}"
