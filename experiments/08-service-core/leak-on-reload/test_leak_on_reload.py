"""leak-on-reload · 清理写漏的那版，重载之后旧的副作用照样触发，两份并存

档次 ③ ｜ 性质 🔬 ｜ 状态 ✅ ｜ 1 条用例 ｜ 不需要 web

## 判定

- **清理写漏的那版，拆掉之后旧的定时器照样触发——两份并存。** 插件起了一个 5 秒的
  定时器却没把取消动作登记给 `ctx.effect`；干到一半时热重载它（改一个字面量触发），
  新的一份立刻上任，但旧的那个定时器没人管，照样在原定时间触发「干完了」。这句话
  出现在该条目被判定 `DISPOSED` **之后**——不是拆之前的正常收尾，是拆完之后又活了
  一段时间的幽灵。已验：`test_the_leaky_one_leaves_a_ghost`

  这是这一项最要紧的一条：**症状不是报错，是「看起来一切正常」。** 事件流里两个
  标记并存，实例照常活着，日志里没有任何异常提示——不靠实例标记去分辨新旧两份，
  这个现象根本发现不了。

## 观测方法

真实插件不是「apply 里说句话就完事」——它可能正干着一件要跑好几秒的活儿，清理没写
对（没把取消动作登记给 `ctx.effect`）时那个没人管的副作用会怎样，就是本项要看的。

每个插件在 `apply` 里生成一个只属于**这一次挂载**的标记，之后每条上报都带着它。
「重载之后收到带旧标记的上报」就是硬证据——旧的那份还在跑。没有这个标记，「两份
并存」和「一份正常跑」在事件流里长得一模一样，是错的信号会把幽灵漏掉。

判定同时钉死两个时间点：条目状态跳到 `DISPOSED` 的时刻，与幽灵那句「干完了」出现
的时刻——后者必须晚于前者，否则只是拆之前的正常收尾，算不上幽灵。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lab import LAB_ROOT, PKG_HMR, PKG_TIMER, Instance, LabHome, LabProfile, of_kind, read_events, reports  # noqa: E402

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 干活的那个插件要跑多久（跟 fixture 里的常量对齐）。5 秒是故意的——
#: 留足窗口让测试代码从容地在它干到一半时改文件。
BUSY_MS = 5000

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
"""


def build(lab_home: LabHome, name: str) -> tuple[LabProfile, Path]:
    """搭一个实例：清理写漏那版的干活插件。"""
    events = lab_home.root / f"events-{name}.jsonl"
    profile = lab_home.make_profile(
        name, bundles=[], patch=BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    )
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(FIXTURES / "busy-leaky.mjs", profile.dir / "worker.mjs")
    return profile, events


def wait_for_report(inst: Instance, path: Path, note: str, *, timeout: float = 40.0) -> dict | None:
    """等某一句上报出现。

    等的是**事件流里真的出现了那句话**，不是 sleep 猜时间——
    「它开始干活了没有」只有它自己说了才算数。
    """
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
    """把 worker.mjs 里的「第一版」改成「第二版」，触发热重载。

    只改这一处字面量，逻辑一个字不动——变量控制在「代码变了」这一件事上。
    """
    p = profile.dir / "worker.mjs"
    p.write_text(p.read_text(encoding="utf-8").replace("第一版", "第二版"), encoding="utf-8")


def markers_of(events: list[dict], note: str) -> list[str]:
    """某一句上报出现过的所有标记，按时间顺序。"""
    return [
        e["data"]["标记"]
        for e in reports(events)
        if e.get("note") == note and isinstance(e.get("data"), dict) and e["data"].get("标记")
    ]


def test_the_leaky_one_leaves_a_ghost(lab_home: LabHome, launch):
    """清理写漏的那版：拆掉之后旧的定时器**照样触发**——两份并存。

    这是这一项最要紧的一条。症状不是报错，是「看起来一切正常」。
    """
    profile, events_path = build(lab_home, "leaky-ghost")
    inst = launch(profile, wait_http=False)

    start_report = wait_for_report(inst, events_path, "开始干活")
    assert start_report is not None, f"它没能开始干活：\n{inst.logs()}"
    old_marker = start_report["data"]["标记"]

    time.sleep(BUSY_MS / 1000 / 2)
    edit_one_line(profile)
    time.sleep(BUSY_MS / 1000 + 3.0)

    events = read_events(events_path)
    finished = markers_of(events, "干完了")

    print("\n══ 清理写漏的那版 ══════════════════════════════════════")
    print(f"  开工时的标记：{old_marker}")
    print(f"  报过「干完了」的标记：{finished or '（一个都没有）'}")
    # 旧的那份是什么时候被判定为拆完的，它又是什么时候说的话
    disposed_at = next(
        (float(e["ms"]) for e in of_kind(events, "status") if e.get("id") == "worker" and e.get("to") == "DISPOSED"),
        None,
    )
    ghost_spoke_at = next(
        (
            float(e["ms"])
            for e in reports(events)
            if e.get("note") == "干完了" and (e.get("data") or {}).get("标记") == old_marker
        ),
        None,
    )

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert old_marker in finished, (
        f"清理写漏却没留下幽灵？预期旧标记 {old_marker} 在拆掉之后照样报「干完了」，实际 {finished}"
    )
    assert disposed_at is not None and ghost_spoke_at is not None
    print(f"  旧的那份被判定拆完：{disposed_at:.1f}ms")
    print(f"  它却在这时候还说了话：{ghost_spoke_at:.1f}ms")
    print(f"  → **拆完之后又活了 {ghost_spoke_at - disposed_at:.0f}ms**，事件流里两个标记并存")
    assert ghost_spoke_at > disposed_at, "幽灵那句话应当出现在「拆完」之后——否则它只是拆之前的正常收尾，算不上幽灵"
