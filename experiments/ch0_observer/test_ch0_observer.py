"""0-2 · 探查器：它凭什么能看见整棵树，它看不见什么

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/ch0_observer/ -n 0 -s

后面每一项的结论都由同一台仪器给出——采集器 `lab-recorder`。所以先把这台仪器
本身查一遍：它能看见什么、看不见什么。看不清这两条，后面所有页面的数据都要打问号。

三件事，一次运行同时给出：

1. **它听得见别人。** 事件流里不止有采集器自己，还有旁边那个陪衬插件，
   以及几十个采集器根本没写进 patch 文件的条目
2. **它自己也在树上。** 它没有特权：占一个条目位，自己也走状态、也被自己记下来
3. **它的能力上限**：睁眼之前的事一概没有。事件流第一批是起点快照——
   快照里凡是已经动过的条目，它们那几跳谁也补不回来。采集器自己就是其中之一
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import (  # noqa: E402
    LAB_ROOT,
    Instance,
    LabHome,
    entry_ids,
    of_kind,
    read_events,
    reports,
    start_instance,
    states_of,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
NEIGHBOR = Path(__file__).resolve().parent / "fixtures" / "neighbor.mjs"

#: 框架自带的条目里挑几个当样本 —— 它们一个字都没出现在下面这份 patch 文件里
FRAMEWORK_SAMPLE = {"timer", "hmr"}

#: patch 文件里只写两条：仪器，和一个给仪器看的陪衬。
#: 实例里其余几十条都是框架自带的，我们没写过它们。
PATCH = """# 0-2 · 一台仪器 + 一个陪衬
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100

    - id: neighbor
      name: ./neighbor.mjs
"""


@pytest.fixture(scope="module")
def observed(lab_home: LabHome) -> Iterator[list[dict]]:
    """跑一个实例，把采集器落下的整条事件流交给下面三个用例。

    三条判定读**同一次运行**：它们讲的是同一台仪器的三个侧面，
    分三次跑反而要解释「为什么这次和那次数不一样」。
    """
    events_path = lab_home.root / "events.jsonl"
    profile = lab_home.make_profile("observer", patch=PATCH.format(out=json.dumps(events_path.as_posix())))
    profile.link_plugin("lab-recorder", OBSERVER)
    # 陪衬插件就是放进 profile 目录的一个文件，用例用 copy2，读者手动拷，动作一样
    shutil.copy2(NEIGHBOR, profile.dir / "neighbor.mjs")

    inst = start_instance(profile, wait_http=False)
    try:
        events = _wait_until_settled(inst, events_path)
        assert inst.alive(), f"实例应当活着，却退了：\n{inst.logs()}"
        assert events, f"采集器一个字都没写出来：\n{inst.logs()}"
        yield events
    finally:
        inst.stop()


def _wait_until_settled(inst: Instance, path: Path, *, timeout: float = 90.0) -> list[dict]:
    """等到这一轮该记的都记完了。

    等的是**内容**不是文件存在也不是条数：采集器一挂载就先写一个空文件，
    条数则随框架自带条目的多少浮动。判据取三条硬信号——起点快照拍完、
    陪衬插件说了话、陪衬插件走到 ACTIVE。
    """
    deadline = time.monotonic() + timeout
    events: list[dict] = []
    while time.monotonic() < deadline:
        events = read_events(path)
        if (
            of_kind(events, "snapshot")
            and reports(events, who="neighbor")
            and "ACTIVE" in states_of(events, "neighbor")
        ):
            time.sleep(0.5)  # 给 flush 定时器留一拍，把尾巴带上
            return read_events(path)
        if not inst.alive():
            break
        time.sleep(0.3)
    return events


def snapshot_by_id(events: list[dict]) -> dict[str, dict]:
    """起点快照：条目 id → 那一条快照记录。"""
    return {e["id"]: e for e in of_kind(events, "snapshot") if e.get("id")}


def reached_active(events: list[dict], entry_id: str) -> bool:
    return "ACTIVE" in states_of(events, entry_id)


def test_it_hears_everyone_not_just_itself(observed: list[dict]):
    """它听得见别人——旁边那条，以及几十条我们根本没写过的。

    这是整套观测方案的地基：仪器要是只听得见自己那一摊，
    后面每一项的数据都只能说明「采集器怎么样」，说明不了「实例里发生了什么」。
    """
    ids = entry_ids(observed)
    written_by_us = {"lab-recorder", "neighbor"}
    others = ids - written_by_us

    print("\n══ 采集器听见了谁 ════════════════════════════════════════")
    print(f"事件总数：{len(observed)}      涉及条目：{len(ids)}")
    print(f"我们写进 patch 文件的：{sorted(written_by_us)}")
    print(f"我们没写、照样被听见的：{len(others)} 条")
    print(f"  样本（前 20 条）：{sorted(others)[:20]}")

    said = [e.get("note") for e in reports(observed, who="neighbor")]
    print(f"\n陪衬插件走过的状态：{states_of(observed, 'neighbor')}")
    print(f"陪衬插件说的话：      {said}")

    assert "neighbor" in ids, f"平级那条该被听见，实际 {sorted(ids)}"
    assert "ACTIVE" in states_of(observed, "neighbor"), (
        f"该记到平级那条的状态迁移，实际只有 {states_of(observed, 'neighbor')}"
    )
    assert said, "平级那条说的话没进事件流 —— 上报口没打通"
    assert ids >= FRAMEWORK_SAMPLE, f"框架自带的 {sorted(FRAMEWORK_SAMPLE)} 都该被听见，实际 {sorted(ids)}"
    assert len(others) >= 20, f"只听见 {len(others)} 条我们没写过的 —— 那说明它听的范围有限，观测方案的地基不成立"


def test_it_is_an_ordinary_entry(observed: list[dict]):
    """它自己也在树上，没有特权。

    两处硬证据：
      * 起点快照里有它自己一条，而且那一刻它是 LOADING —— 快照正是在它
        自己的 apply 里拍的，它跟别人受同样的加载规则约束
      * 它随后自己走到 ACTIVE，这一跳同样被它自己记了下来
    """
    snap = snapshot_by_id(observed)
    mine = snap.get("lab-recorder")
    walked = states_of(observed, "lab-recorder")

    print("\n══ 采集器自己在树上的样子 ════════════════════════════════")
    print(f"起点快照里的自己：{json.dumps(mine, ensure_ascii=False)}")
    print(f"它自己走过的状态：{walked}")

    assert mine is not None, f"快照里该有它自己，实际快照条目 {sorted(snap)[:20]}"
    assert mine.get("to") == "LOADING", f"拍快照那一刻它自己应当是 LOADING，实际 {mine.get('to')}"
    assert "ACTIVE" in walked, f"它自己走到 ACTIVE 这一跳该被记下，实际 {walked}"


def test_it_cannot_see_anything_before_it_opened_its_eyes(observed: list[dict]):
    """它看不见自己挂载之前的历史——那部分是**丢的**，不是没发生。

    事件流第一条就是「采集开始」，紧接着是起点快照：每个条目在它睁眼那一刻
    各自是什么样。**起点是确切的，起点之前的过程没有。**

    快照直接把丢的那部分指出来了——凡是快照时已经在 LOADING 的条目，
    它们进 LOADING 那一跳发生在采集器睁眼之前，事件流里只剩最后一跳
    `→ ACTIVE`。采集器自己就是这样的条目之一：**它连自己的出生都没记全。**

    对照组在同一份数据里：睁眼时还没建起来的条目，整条链一跳不缺。
    """
    snaps = snapshot_by_id(observed)
    # 睁眼那一刻已经在半路上的（进了 LOADING）：进 LOADING 那一跳没人看见
    mid_flight = sorted(i for i, e in snaps.items() if e.get("to") == "LOADING")
    # 睁眼那一刻还没建起来的：整条链都在采集器眼皮底下走
    not_born_yet = sorted(i for i, e in snaps.items() if not e.get("to"))

    print("\n══ 采集器睁眼之前的历史 ══════════════════════════════════")
    print(f"事件流第一条：{observed[0].get('kind')} · {observed[0].get('note')}")

    print(f"\n起点快照共 {len(snaps)} 个条目：")
    print(f"  还没建起来  {len(not_born_yet):>3} 个   → 整条链都会被记下")
    print(f"  已在半路上  {len(mid_flight):>3} 个   → {sorted(mid_flight)}")

    print("\n睁眼时已在半路上的，事件流里只剩最后一跳：")
    for i in mid_flight:
        print(f"  {i:<16} 快照时 {snaps[i]['to']:<8} 事件流里记到 {states_of(observed, i)}")
    print("\n对照——睁眼时还没建起来的，整条链一跳不缺：")
    for i in ["neighbor", *(x for x in not_born_yet if reached_active(observed, x))][:4]:
        print(f"  {i:<16} 快照时 {snaps[i].get('to') or '还没建起来':<8} 事件流里记到 {states_of(observed, i)}")

    assert observed[0].get("kind") == "recorder", f"第一条该是采集器自己的开场白，实际 {observed[0]}"
    assert "采集开始" in str(observed[0].get("note")), f"开场白该说明「本行之前未被记录」，实际 {observed[0]}"
    assert "lab-recorder" in mid_flight, (
        f"采集器自己就该在半路上那一档（拍快照时它正在自己的 apply 里），实际 {mid_flight}"
    )
    for i in mid_flight:
        assert "LOADING" not in states_of(observed, i), (
            f"{i} 睁眼时已经在 LOADING，那一跳不可能被记到，实际 {states_of(observed, i)}"
        )
    # 反过来：睁眼后才建起来的条目，进 LOADING 那一跳一条都不能少
    late = [i for i in not_born_yet if reached_active(observed, i)]
    assert len(late) >= 20, f"睁眼后才建起来并跑到 ACTIVE 的条目太少（{len(late)}），对照组不成立"
    assert all("LOADING" in states_of(observed, i) for i in late), (
        f"睁眼后才建起来的条目该整条链都在，缺了的：{[i for i in late if 'LOADING' not in states_of(observed, i)]}"
    )
    assert snaps["neighbor"].get("to") != "ACTIVE", f"陪衬插件该在快照之后才跑起来，实际快照里就是 {snaps['neighbor']}"
    assert states_of(observed, "neighbor") == ["LOADING", "ACTIVE"], (
        f"陪衬插件整条链都该在，实际 {states_of(observed, 'neighbor')}"
    )
