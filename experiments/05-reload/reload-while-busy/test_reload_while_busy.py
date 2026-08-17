"""reload-while-busy · 重载撞上一件正干着的活儿

档次 ② ｜ 性质 🔬 ｜ 状态 ✅ ｜ 3 条用例（其一跑 clean/leaky 两个参数） ｜ 不需要 web

## 判定

- **拆一个正忙的条目，框架不等它干完。** `UNLOADING → DISPOSED` 的耗时远
  小于那件活儿的总时长——`test_what_happens_to_the_work_in_flight`
- **清理写对的那份，disposer 会被调用，旧标记不会再出现在「干完了」里；
  清理写漏的那份，旧标记照样出现**——两份并存的完整证据（拆完之后又活了
  多久、时间线怎么读）在 08 组 leak-on-reload 项，本项只覆盖「进行中的活儿
  被不被中断」这一半。
- **旁观者在重载前后都能查到服务**，没有出现「一次都没查到」的异常静默。
  `test_what_the_caller_sees`
- **重载一个正忙的插件不会把整棵树拖住**：旁观者（不受影响的旁路条目）
  在重载期间照常每秒上报。`test_reload_does_not_hang_the_tree`

## 观测方法

每个插件在 `apply` 里生成一个只属于这一次挂载的标记，之后每条上报都带着它
——「重载之后收到带旧标记的上报」是硬证据，没有这个标记的话「两份并存」和
「一份正常跑」在事件流里长得一模一样。「进行中的活儿有没有被中断」看它
是否报出「干完了」；「框架等不等它」看 `UNLOADING → DISPOSED` 这段状态转移
花了多久，跟活儿本身的总时长比。

## 没覆盖到的

清理写漏那版「拆完之后又活了多久」的完整时间线证据（幽灵说话的时刻晚于
判定拆完的时刻）单独归 08 组 leak-on-reload 项，不在本项重复。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lab import LAB_ROOT, PKG_HMR, PKG_TIMER, Instance, LabHome, LabProfile, of_kind, read_events, reports  # noqa: E402

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 干活的那个插件要跑多久（跟 fixture 里的常量对齐）。5 秒是故意的——
#: 留足窗口让测试代码从容地在它干到一半时改文件。
WORK_MS = 5000

BASE = """- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'
      config:
        root: ['.']

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100

    - id: worker
      name: ./worker.mjs

    - id: watcher
      name: ./watcher.mjs
      config:
        每隔毫秒: 1000
"""


def build(lab_home: LabHome, name: str, *, version: str) -> tuple[LabProfile, Path]:
    """搭一个实例。`version` 决定用清理写对的那份还是写漏的那份。

    两份 fixture 都拷成 `worker.mjs`——条目那一行完全一样，换的只是文件
    内容，这样两组的唯一变量就是「清理有没有写对」。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    profile = lab_home.make_profile(
        name, bundles=[], patch=BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    )
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(FIXTURES / f"busy-{version}.mjs", profile.dir / "worker.mjs")
    shutil.copy2(FIXTURES / "watcher.mjs", profile.dir / "watcher.mjs")
    return profile, events


def wait_for_report(inst: Instance, path: Path, note: str, *, timeout: float = 40.0) -> dict | None:
    """等某一句上报出现——等的是事件流里真的出现了那句话，不是 sleep 猜时间。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for e in reports(read_events(path)):
            if e.get("note") == note:
                return e
        if not inst.alive():
            return None
        time.sleep(0.2)
    return None


def edit_one_line(profile: LabProfile) -> None:
    """把 worker.mjs 里的「第一版」改成「第二版」，触发热重载。只改这一处
    字面量，逻辑一个字不动——变量控制在「代码变了」这一件事上。
    """
    p = profile.dir / "worker.mjs"
    p.write_text(p.read_text(encoding="utf-8").replace("第一版", "第二版"), encoding="utf-8")


def marks_of(events: list[dict], note: str) -> list[str]:
    """某一句上报出现过的所有标记，按时间顺序。"""
    return [
        e["data"]["标记"]
        for e in reports(events)
        if e.get("note") == note and isinstance(e.get("data"), dict) and e["data"].get("标记")
    ]


@pytest.mark.parametrize("version", ["clean", "leaky"])
def test_what_happens_to_the_work_in_flight(lab_home: LabHome, launch, version: str):
    """干到一半被重载，那件活儿怎么样了。

    两个版本跑同一套流程，差别只在插件里那段 `ctx.effect` 有没有写：
      * **清理写对**——旧标记不该出现在「干完了」里，disposer 该说过话
      * **清理写漏**——旧标记该出现在「干完了」里，两份并存留下痕迹
        （这一版更完整的证据在 leak-on-reload 项）

    另外拆一个正忙的条目，框架等不等它——`UNLOADING → DISPOSED` 的耗时
    应当远小于那件活儿的总时长。
    """
    profile, events_path = build(lab_home, version, version=version)
    inst = launch(profile, wait_http=False)

    started = wait_for_report(inst, events_path, "开始干活")
    assert started is not None, f"它没能开始干活：\n{inst.logs()}"
    old_mark = started["data"]["标记"]

    # 等它干到一半再动手——不能等它干完
    time.sleep(WORK_MS / 1000 / 2)
    edit_one_line(profile)

    # 等到「原本那件活儿早该干完」之后再看，才判得出它到底完没完
    time.sleep(WORK_MS / 1000 + 3.0)
    events = read_events(events_path)

    took_over = marks_of(events, "我上任了")
    finished = marks_of(events, "干完了")

    def status_at(to: str) -> float | None:
        for e in of_kind(events, "status"):
            if e.get("id") == "worker" and e.get("to") == to:
                return float(e["ms"])
        return None

    unload_at, dispose_at = status_at("UNLOADING"), status_at("DISPOSED")
    if unload_at is not None and dispose_at is not None:
        assert dispose_at - unload_at < WORK_MS / 2, (
            f"拆掉花了 {dispose_at - unload_at:.0f}ms——框架好像在等那件没干完的活儿"
        )

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert len(took_over) >= 2, f"应当有过两次上任（重载前后各一次），实际 {took_over}"
    assert took_over[0] == old_mark, "第一次上任的标记应当就是开工那次的"
    assert took_over[1] != old_mark, "重载之后应当是新的一份上任，标记该变"

    if version == "clean":
        assert old_mark not in finished, f"清理写对，旧的那份却还是把活干完了——ctx.effect 注册的取消没生效：{finished}"
        assert "我被拆了，定时器一并取消" in [e.get("note") for e in reports(events)], (
            "没看到 disposer 说话——它可能根本没被调用"
        )
    else:
        assert old_mark in finished, (
            f"清理写漏，却没留下幽灵？预期旧标记 {old_mark} 在拆掉之后照样报「干完了」，实际 {finished}"
        )


def test_what_the_caller_sees(lab_home: LabHome, launch):
    """旁观者在重载前后拿到的服务对象。

    它每秒查一次、如实上报：服务在不在、在的话是哪一份。重载那一瞬有没有
    一段拿不到的窗口，这里能看出来。
    """
    profile, events_path = build(lab_home, "seen", version="clean")
    inst = launch(profile, wait_http=False)

    started = wait_for_report(inst, events_path, "开始干活")
    assert started is not None, f"它没能开始干活：\n{inst.logs()}"

    time.sleep(WORK_MS / 1000 / 2)
    edit_one_line(profile)
    time.sleep(WORK_MS / 1000 + 3.0)

    events = read_events(events_path)
    queries = [e for e in reports(events, who="watcher") if e.get("note") == "查了一次"]

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert queries, "旁观者一次都没查过——它可能自己就没跑起来"


def test_reload_does_not_hang_the_tree(lab_home: LabHome, launch):
    """重载一个正忙的插件，会不会把整棵树拖住。

    判据不用等谁说话：别的条目还动不动。旁观者每秒报一次，如果重载期间它
    照常在报，说明树没被卡住。
    """
    profile, events_path = build(lab_home, "nohang", version="clean")
    inst = launch(profile, wait_http=False)

    started = wait_for_report(inst, events_path, "开始干活")
    assert started is not None, f"它没能开始干活：\n{inst.logs()}"

    time.sleep(WORK_MS / 1000 / 2)
    edit_one_line(profile)
    time.sleep(6.0)

    events = read_events(events_path)
    queries = [e for e in reports(events, who="watcher") if e.get("note") == "查了一次"]

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert len(queries) >= 3, (
        f"旁观者只查了 {len(queries)} 次——它每秒一次，跑了十来秒却这么少，说明重载期间有东西被拖住了"
    )
