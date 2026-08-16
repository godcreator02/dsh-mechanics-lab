"""第 2 步 · 把自己写的东西挂上去

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/step2_mount_your_plugin/ -n 0 -s

第 1 步的实例里只有框架自己的东西。这一步往里加一个**你写的插件**，
再从事件流里看它是不是真的跑了。

插件就一个文件（`fixtures/hello.mjs`），全部内容是：声明要用观察器、
在 `apply` 里说一句话。没有 package.json，没有构建，没有依赖安装。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import (  # noqa: E402
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    entry_ids,
    read_events,
    reports,
    states_of,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
HELLO = Path(__file__).resolve().parent / "fixtures" / "hello.mjs"

#: 第 1 步立起来的那三条，原样带过来
BASE = """- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
"""

#: 你写的那条 —— 就多这一段
YOURS = """
- insert:
    - id: hello
      name: ./hello.mjs
"""


def build(lab_home: LabHome, name: str, *, mount_yours: bool) -> tuple[LabProfile, Path]:
    """搭一个实例：框架三条 +（可选）你写的那条。

    插件是**放进 profile 目录的一个文件**，`name` 写 `./hello.mjs` 相对路径
    —— 不用 link、不用包名。仪器（lab-recorder）仍然 link，它是装好的设备，
    不是这一步的教学内容。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    if mount_yours:
        patch += YOURS
    profile = lab_home.make_profile(name, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    # 插件文件拷进 profile 目录 —— 读者手动放文件，用例用 copy2，动作一样
    shutil.copy2(HELLO, profile.dir / "hello.mjs")
    return profile, events


def wait_for_events(
    inst: Instance, path: Path, *, least: int = 5, timeout: float = 40.0
) -> list[dict]:
    deadline = time.monotonic() + timeout
    events: list[dict] = []
    while time.monotonic() < deadline:
        events = read_events(path)
        if len(events) >= least:
            return events
        if not inst.alive():
            break
        time.sleep(0.3)
    return events


def test_your_plugin_runs_and_says_so(lab_home: LabHome, launch):
    """挂上那一条，插件就跑了 —— 它自己说的话进了同一条事件流。"""
    profile, events_path = build(lab_home, "mine", mount_yours=True)

    inst = launch(profile, wait_http=False)
    events = wait_for_events(inst, events_path, least=8)

    print("\n══ 加了你写的插件之后 ════════════════════════════════════")
    print(timeline(events))

    said = reports(events, who="hello")
    print(f"\n你的插件说的话：{[e.get('note') for e in said]}")
    print(f"它走过的状态：{states_of(events, 'hello')}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "hello" in entry_ids(events), (
        f"树上应当有你写的那条，实际 {sorted(entry_ids(events))}"
    )
    assert said, "插件的 apply 没说话 —— 它可能压根没被调用"
    assert said[0]["note"] == "我的 apply 被调用了"


def test_apply_runs_while_loading(lab_home: LabHome, launch):
    """插件说话的那一刻它还在 LOADING —— apply 跑在「加载中」，不是「加载完」。

    这条不用额外做实验：事件流里 `report` 与 `status` 共用一套时间轴，
    先后关系直接读得出来。
    """
    profile, events_path = build(lab_home, "timing", mount_yours=True)

    inst = launch(profile, wait_http=False)
    events = wait_for_events(inst, events_path, least=8)

    said = reports(events, who="hello")
    active = [
        e
        for e in events
        if e.get("kind") == "status" and e.get("id") == "hello" and e.get("to") == "ACTIVE"
    ]
    assert said and active, f"该有的事件没齐：说话 {len(said)} 条、ACTIVE {len(active)} 条"

    say_ms, active_ms = float(said[0]["ms"]), float(active[0]["ms"])
    print("\n══ apply 跑在什么时候 ════════════════════════════════════")
    print(f"  插件说话：      {say_ms:8.1f}ms")
    print(f"  它变 ACTIVE：   {active_ms:8.1f}ms")
    print("  → apply 跑完了，这个条目才被标记为 ACTIVE")

    assert say_ms < active_ms, "插件说话应当早于它变 ACTIVE —— apply 是在 LOADING 期跑的"


def test_without_the_entry_nothing_runs(lab_home: LabHome, launch):
    """对照组：文件原样放着、不加那一条，插件就完全不存在。

    这条排除「它是自己被扫到的」这种可能 —— 挂载只认 patch 里写没写。
    """
    profile, events_path = build(lab_home, "unmounted", mount_yours=False)
    assert (profile.dir / "hello.mjs").exists(), "前提：文件确实放在那儿了"

    inst = launch(profile, wait_http=False)
    wait_for_events(inst, events_path, least=5)

    # 验「不该发生」：固定等一段，不能轮询提前退出
    time.sleep(6.0)
    events = read_events(events_path)

    print("\n══ 文件在、但没写那一条 ══════════════════════════════════")
    print(f"树上的条目：{sorted(entry_ids(events))}")
    said = [e.get("note") for e in reports(events, who="hello")]
    print(f"它说的话：{said or '（一句都没有）'}")

    assert inst.alive(), "实例应当照常活着 —— 少挂一个插件不是错误"
    assert "hello" not in entry_ids(events), "没写那一条，它不该出现在树上"
    assert not reports(events, who="hello"), "没挂上却说话了？那它是从别处被加载的"
