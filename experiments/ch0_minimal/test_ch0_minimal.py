"""0-3 · 最小实例：一个实例的下限

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/ch0_minimal/ -n 0 -s

一个 DSH 实例最少要有什么？答案是两条：`timer` 和 `hmr`。
这一项把这个下限钉死——两条都在，实例活；只写 `hmr` 一条，实例根本起不来，
日志会点名说它在等谁。

采集器照旧挂着（后面每一项都靠它看结果），但这一项要看的是**被测对象**：
patch 文件里那两条，少一条会怎样。
"""

from __future__ import annotations

import json
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
    entry_ids,
    read_events,
    states_of,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"

#: 最小实例的全部家当。这两条是被测对象。
MINIMAL = """# 一个实例最少需要的两条
- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'
"""

#: 对照组：故意只写 hmr，看会怎样
ONLY_HMR = """# 故意只写一条
- insert:
    - id: hmr
      name: '{hmr}'
"""

#: 仪器。它不是这一项的教学内容，是装好的设备。
OBSERVER_ENTRY = """
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
"""


def with_observer(patch: str, events_path: Path) -> str:
    """把采集器那一条拼在给定 patch 后面。

    patch 文件是 YAML 数组、允许多个 `- insert:` 块，所以直接拼字符串就行——
    不用解析，也不用改前面那段。
    """
    return patch.format(timer=PKG_TIMER, hmr=PKG_HMR) + OBSERVER_ENTRY.format(out=json.dumps(events_path.as_posix()))


def wait_for_events(inst: Instance, path: Path, *, least: int = 5, timeout: float = 40.0) -> list[dict]:
    """等采集器把事件刷出来。

    等的是**事件条数**而不是文件存在：采集器一挂载就先写一个空文件，
    文件在了不代表已经记到东西。
    """
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


def test_two_entries_make_an_instance(lab_home: LabHome, launch):
    """两条就够——实例活着，而且你能看见里面发生了什么。

    判定三条：
      * 进程活着（不是起来就退）
      * 事件流里 `timer` / `hmr` 都到场了
      * 整棵树就这么几条，多一条都说明有东西没数清楚
    """
    events_path = lab_home.root / "events.jsonl"
    profile = lab_home.make_profile("minimal", bundles=[], patch=with_observer(MINIMAL, events_path))
    profile.link_plugin("lab-recorder", OBSERVER)

    inst = launch(profile, wait_http=False)
    events = wait_for_events(inst, events_path)

    print("\n══ 一个最小实例里发生了什么 ══════════════════════════════")
    print(timeline(events))

    ids = entry_ids(events)
    print(f"\n树上的条目：{sorted(ids)}")
    for eid in sorted(ids):
        walked = states_of(events, eid)
        print(f"  {eid:<16} 走过的状态：{walked or '（采集器睁眼前就走完了）'}")

    assert inst.alive(), f"实例应当活着，却退了：\n{inst.logs()}"
    assert {"timer", "hmr"} <= ids, f"timer 与 hmr 都该在树上，实际 {sorted(ids)}"
    # 一个最小实例就这四条：
    #   timer / hmr    你写进 patch 文件的两条，就是本项的被测对象
    #   lab-recorder   仪器，也是你写进 patch 文件的
    #   include        **框架自己放的**，你没写过它 —— 它总在，且不归你管
    assert ids == {"timer", "hmr", "lab-recorder", "include"}, f"预期只有那四条，实际 {sorted(ids)}"

    # timer 先 ACTIVE，hmr 才开始 LOADING —— 两条的先后在时间线上直接看得到
    def first_ms(entry_id: str, to: str) -> float | None:
        for e in events:
            if e.get("kind") == "status" and e.get("id") == entry_id and e.get("to") == to:
                return float(e["ms"])
        return None

    timer_active, hmr_loading = first_ms("timer", "ACTIVE"), first_ms("hmr", "LOADING")
    if timer_active is not None and hmr_loading is not None:
        print(f"\ntimer 变 ACTIVE：{timer_active:.1f}ms    hmr 才开始 LOADING：{hmr_loading:.1f}ms")
        assert timer_active <= hmr_loading, "hmr 应当等 timer 就位之后才开始加载，时间线却反过来了"


def test_hmr_alone_will_not_start(lab_home: LabHome, launch):
    """只写 hmr 一条：实例根本起不来，日志点名缺了 timer。

    这条撑住本项唯一的判定——**那两条是捆绑的**，不是「写上更好」。
    """
    events_path = lab_home.root / "events-only-hmr.jsonl"
    profile = lab_home.make_profile("only-hmr", bundles=[], patch=with_observer(ONLY_HMR, events_path))
    profile.link_plugin("lab-recorder", OBSERVER)

    inst = launch(profile, wait_http=False)

    # 验「不该活着」：等一段固定时间，不能轮询提前退出
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)

    logs = inst.logs()
    print("\n══ 只写 hmr 一条会怎样 ═══════════════════════════════════")
    print(f"进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    verdict = [ln for ln in logs.splitlines() if "waiting for service" in ln]
    print(f"日志里的判词：{verdict or '（没找到，看完整日志）'}")
    if not verdict:
        print(logs)

    assert not inst.alive(), "只有 hmr 的实例居然活着——那 timer 就不是必需的了"
    assert verdict, f"应当有 waiting for service 的判词：\n{logs}"
    assert any("timer" in ln for ln in verdict), f"判词该点名 timer：{verdict}"
