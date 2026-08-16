"""第 4 步 · 临时关掉它

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/step4_disable_it/ -n 0 -s

第 2 步把插件挂上去了，第 3 步给它传了 config。现在想让它**这次先别跑** ——
不用把那一条从 patch 文件里删掉，加一行 `disabled: true` 就行。

这一步只看一件事：加了这一行之后，那一条到底还在不在、跑没跑。
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
    of_kind,
    read_events,
    reports,
    states_of,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
WORKER = Path(__file__).resolve().parent / "fixtures" / "worker.mjs"

#: 前三步立起来的那三条，原样带过来
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

#: 你写的那条 —— 照常挂上
ENABLED = """
- insert:
    - id: worker
      name: ./worker.mjs
      config:
        班次: 早班
"""

#: 一模一样的一条，只多了 `disabled: true` 这一行
DISABLED = """
- insert:
    - id: worker
      name: ./worker.mjs
      disabled: true
      config:
        班次: 早班
"""


def build(lab_home: LabHome, tag: str, *, entry: str) -> tuple[LabProfile, Path]:
    """搭一个实例：前三步那三条 + 给定的那一段。

    `entry` 传空字符串就是「patch 文件里压根没有 worker 那一条」。
    三种情况除了这一段之外**完全相同** —— 插件文件照样放进 profile 目录。
    """
    events = lab_home.root / f"events-{tag}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    profile = lab_home.make_profile(tag, bundles=[], patch=patch + entry)
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(WORKER, profile.dir / "worker.mjs")
    return profile, events


def wait_for_events(inst: Instance, path: Path, *, least: int = 8, timeout: float = 40.0) -> list[dict]:
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


def snapshot_of(events: list[dict], entry_id: str) -> dict | None:
    """采集器睁眼时给某个条目拍的那一张。拍不到就是 None。"""
    for e in of_kind(events, "snapshot"):
        if e.get("id") == entry_id:
            return e
    return None


def describe(events: list[dict], entry_id: str) -> str:
    """把「这一条现在什么样」的几项摆出来，三个用例共用同一套说法。"""
    shot = snapshot_of(events, entry_id)
    said = [e.get("note") for e in reports(events, who=entry_id)]
    return "\n".join(
        [
            f"  采集器睁眼时拍到它？ {'拍到了' if shot else '没拍到——它不在树上'}",
            f"    └ 快照里的 disabled：{shot.get('disabled') if shot else '—'}",
            f"    └ 那一刻有 fiber 吗？{shot.get('hasFiber') if shot else '—'}"
            + (f"（此刻状态 {shot.get('to')}）" if shot and shot.get("to") else ""),
            f"  它走过的状态：       {states_of(events, entry_id) or '（一次都没变过）'}",
            f"  它说的话：           {said or '（一句都没有）'}",
        ]
    )


def test_disabled_entry_stays_but_never_runs(lab_home: LabHome, launch):
    """写了 `disabled: true`：那一条还在树上，但没有 fiber，一句话没说。

    这是第 4 步的主判定。四项一起看才完整：
      * 采集器睁眼时**拍得到它** —— 它确实在树上
      * 但它**没有 fiber**
      * 没有任何状态变化
      * `apply` 没跑，所以一句话都没说

    ⚠️ 单看快照那一张分不出结果：采集器睁眼时 timer 和 hmr 也都还没有 fiber。
    真正分得出的是后面 —— 那两条陆续走起了状态，这一条从头到尾一动不动。
    所以用例同时验「别人动了」，否则「它没动」也可能只是采集器没记。
    """
    profile, events_path = build(lab_home, "off", entry=DISABLED)

    inst = launch(profile, wait_http=False)
    events = wait_for_events(inst, events_path)
    # 验「不该发生」：再固定等一段，不能一看到没有就下结论
    time.sleep(8.0)
    events = read_events(events_path)

    print("\n══ 写了 disabled: true ═══════════════════════════════════")
    print(timeline(events))
    print("\n那一条现在什么样：")
    print(describe(events, "worker"))

    # 采集器睁眼那一刻 timer 和 hmr 也都还没建 fiber —— 光看那一张快照分不出
    # 「还没轮到」和「不会有」。分得出的是后面：别人陆续有了状态，它一直没有。
    print("\n  同一张快照里，谁后来真的动起来了：")
    for eid in sorted(entry_ids(events)):
        walked = states_of(events, eid)
        print(f"    {eid:<14} {walked or '（一次都没变过）'}")

    shot = snapshot_of(events, "worker")

    assert inst.alive(), f"实例应当照常活着 —— 关掉一条不是错误：\n{inst.logs()}"
    assert shot is not None, f"它应当还在树上（采集器该拍到它），实际树上是 {sorted(entry_ids(events))}"
    assert shot.get("disabled") is True, f"这一条该被标成关掉的，实际快照是 {shot}"
    assert shot.get("hasFiber") is False, f"关掉的条目不该有 fiber，实际快照是 {shot}"
    assert shot.get("to") is None, f"没有 fiber 就没有状态可言，实际快照是 {shot}"
    assert states_of(events, "worker") == [], f"关掉的条目不该有任何状态变化，实际走了 {states_of(events, 'worker')}"
    assert not reports(events, who="worker"), "它说话了 —— 那 apply 就是跑了，没关掉"
    # 反面保险：别的条目确实动了，「它没动」才说明得了问题
    assert "ACTIVE" in states_of(events, "timer"), "连 timer 都没走状态 —— 那说明采集器没记，不能拿来判 worker"


def test_disabled_differs_from_not_writing_it(lab_home: LabHome, launch):
    """「写了但关掉」 vs 「压根不写那一条」—— 两者不是一回事。

    * 不写：它**不在树上**，采集器连拍都拍不到
    * 写了但关掉：它**在树上**，采集器拍得到，只是没有 fiber

    两边一样的地方是：都一句话没说。所以光看「跑没跑」分不出这两种情况，
    得看它在不在树上。
    """
    off_profile, off_events = build(lab_home, "off-cmp", entry=DISABLED)
    absent_profile, absent_events = build(lab_home, "absent", entry="")

    off = launch(off_profile, wait_http=False)
    absent = launch(absent_profile, wait_http=False)
    wait_for_events(off, off_events)
    wait_for_events(absent, absent_events)
    time.sleep(8.0)

    off_ev, absent_ev = read_events(off_events), read_events(absent_events)

    print("\n══ 写了但关掉 ═══════════════════════════════════════════")
    print(f"  树上的条目：{sorted(entry_ids(off_ev))}")
    print(describe(off_ev, "worker"))
    print("\n══ 压根不写那一条 ═══════════════════════════════════════")
    print(f"  树上的条目：{sorted(entry_ids(absent_ev))}")
    print(describe(absent_ev, "worker"))
    print("\n  → 两边都没跑；区别在「在不在树上」")

    assert off.alive() and absent.alive(), "两个实例都该活着"

    # 写了但关掉：在树上
    assert snapshot_of(off_ev, "worker") is not None, "写了 disabled 的那条应当还在树上"
    assert "worker" in entry_ids(off_ev), "写了 disabled 的那条应当出现在事件流里"

    # 压根不写：不在树上，连名字都不出现
    assert snapshot_of(absent_ev, "worker") is None, "没写那一条，采集器不该拍到它"
    assert "worker" not in entry_ids(absent_ev), (
        f"没写那一条，它不该出现在事件流里，实际 {sorted(entry_ids(absent_ev))}"
    )

    # 两边一样的地方：都没跑
    assert not reports(off_ev, who="worker"), "关掉的那条不该说话"
    assert not reports(absent_ev, who="worker"), "没挂的那条不该说话"
    assert states_of(off_ev, "worker") == states_of(absent_ev, "worker") == []


def test_remove_the_line_and_it_runs_again(lab_home: LabHome, launch):
    """把 `disabled: true` 那一行去掉重起，它就照常跑了。

    这一条和上面那条用的 patch 文件**只差这一行**，连 config 都一模一样 ——
    所以跑没跑的差别只能是这一行造成的。
    """
    profile, events_path = build(lab_home, "on", entry=ENABLED)

    inst = launch(profile, wait_http=False)
    events = wait_for_events(inst, events_path)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline and not reports(read_events(events_path), who="worker"):
        if not inst.alive():
            break
        time.sleep(0.3)
    events = read_events(events_path)

    print("\n══ 去掉那一行之后 ═══════════════════════════════════════")
    print(timeline(events))
    print("\n那一条现在什么样：")
    print(describe(events, "worker"))

    said = reports(events, who="worker")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said, "去掉那一行它就该跑起来，却一句话没说"
    assert said[0]["note"] == "我跑起来了"
    assert said[0]["data"] == {"收到的config": {"班次": "早班"}}, f"config 该照常送达，实际 {said[0]['data']}"
    assert "ACTIVE" in states_of(events, "worker"), (
        f"它该有 fiber、该走到 ACTIVE，实际走了 {states_of(events, 'worker')}"
    )
