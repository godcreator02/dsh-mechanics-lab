"""待归位 · 拆的时候它正忙着

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/chx_reload_while_busy/ -n 0 -s

前面所有关于热重载的实验，插件都是「apply 里说句话就完事」——**没事可做的东西，
拆了重建当然平安无事**。这一项问的是真实插件才会遇到的那个问题：

    它正干着一件要跑好几秒的活儿，这时候你改了它的代码，会怎样？

三条判定：

1. 那件进行中的活儿，**被中断还是跑完了**
2. **清理写对 vs 写漏**：同一个插件两个版本，只差一段 `ctx.effect`，
   热重载时的行为完全不同——写漏那版会**两份并存**
3. 调用方看到的是什么：服务撤销与重建之间有没有一段拿不到的窗口

## 整个实验的地基：实例标记

每个插件在 `apply` 里生成一个只属于**这一次挂载**的标记，之后每条上报都带着它。
于是「重载之后收到带旧标记的上报」就是硬证据——旧的那份还在跑。

没有这个标记，「两份并存」和「一份正常跑」在事件流里长得一模一样。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import (  # noqa: E402
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    of_kind,
    read_events,
    reports,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 干活的那个插件要跑多久（跟 fixture 里的常量对齐）。5 秒是故意的——
#: 留足窗口让测试代码从容地在它干到一半时改文件。
干活毫秒 = 5000

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


def build(lab_home: LabHome, name: str, *, 版本: str) -> tuple[LabProfile, Path]:
    """搭一个实例。`版本` 决定用清理写对的那份还是写漏的那份。

    两份 fixture 都拷成 `worker.mjs` —— 条目那一行完全一样，
    换的只是文件内容，这样两组的唯一变量就是「清理有没有写对」。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    profile = lab_home.make_profile(
        name,
        bundles=[],
        patch=BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix())),
    )
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(FIXTURES / f"busy-{版本}.mjs", profile.dir / "worker.mjs")
    shutil.copy2(FIXTURES / "watcher.mjs", profile.dir / "watcher.mjs")
    return profile, events


def wait_for_report(
    inst: Instance, path: Path, note: str, *, timeout: float = 40.0
) -> dict | None:
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


def 改一行(profile: LabProfile) -> None:
    """把 worker.mjs 里的「第一版」改成「第二版」，触发热重载。

    只改这一处字面量，逻辑一个字不动——变量控制在「代码变了」这一件事上。
    """
    p = profile.dir / "worker.mjs"
    p.write_text(p.read_text(encoding="utf-8").replace("第一版", "第二版"), encoding="utf-8")


def 标记们(events: list[dict], note: str) -> list[str]:
    """某一句上报出现过的所有标记，按时间顺序。"""
    return [
        e["data"]["标记"]
        for e in reports(events)
        if e.get("note") == note and isinstance(e.get("data"), dict) and e["data"].get("标记")
    ]


@pytest.mark.parametrize("版本", ["clean", "leaky"])
def test_what_happens_to_the_work_in_flight(lab_home: LabHome, launch, 版本: str):
    """干到一半被重载，那件活儿怎么样了。

    两个版本跑同一套流程，差别只在插件里那段 `ctx.effect` 有没有写。
    **不预设答案**——把「谁说过话、带什么标记」如实打出来，判定写在最后。
    """
    profile, events_path = build(lab_home, 版本, 版本=版本)
    inst = launch(profile, wait_http=False)

    开工 = wait_for_report(inst, events_path, "开始干活")
    assert 开工 is not None, f"它没能开始干活：\n{inst.logs()}"
    旧标记 = 开工["data"]["标记"]
    print(f"\n══ {版本} · 它开始干活了（标记 {旧标记}，要干 {干活毫秒}ms）══")

    # 等它干到一半再动手——不能等它干完
    time.sleep(干活毫秒 / 1000 / 2)
    print(f"  干到一半，现在改它的代码…")
    改一行(profile)

    # 等到「原本那件活儿早该干完」之后再看，才判得出它到底完没完
    time.sleep(干活毫秒 / 1000 + 3.0)
    events = read_events(events_path)

    print(timeline(events, kinds=("report", "status")))

    上任 = 标记们(events, "我上任了")
    干完 = 标记们(events, "干完了")
    print(f"\n  上任过的标记：{上任}")
    print(f"  报过「干完了」的：{干完 or '（一个都没有）'}")
    print(f"  旧那份还在不在：{'在——' + 旧标记 + ' 干完了' if 旧标记 in 干完 else '不在'}")

    # 拆一个正忙的条目，框架等不等它？从 UNLOADING 到 DISPOSED 的耗时说了算
    def 状态时刻(to: str) -> float | None:
        for e in of_kind(events, "status"):
            if e.get("id") == "worker" and e.get("to") == to:
                return float(e["ms"])
        return None

    起拆, 拆完 = 状态时刻("UNLOADING"), 状态时刻("DISPOSED")
    if 起拆 is not None and 拆完 is not None:
        print(f"  拆它花了：{拆完 - 起拆:.1f}ms（那件活儿要跑 {干活毫秒}ms）")
        assert 拆完 - 起拆 < 干活毫秒 / 2, (
            f"拆掉花了 {拆完 - 起拆:.0f}ms —— 框架好像在等那件没干完的活儿"
        )

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert len(上任) >= 2, f"应当有过两次上任（重载前后各一次），实际 {上任}"
    assert 上任[0] == 旧标记, "第一次上任的标记应当就是开工那次的"
    assert 上任[1] != 旧标记, "重载之后应当是**新的一份**上任，标记该变"

    # ── 这一项的核心对照：同一个插件，只差一段 ctx.effect ──────────────
    if 版本 == "clean":
        assert 旧标记 not in 干完, (
            f"清理写对，旧的那份却还是把活干完了——`ctx.effect` 注册的取消没生效：{干完}"
        )
        assert "我被拆了，定时器一并取消" in [e.get("note") for e in reports(events)], (
            "没看到 disposer 说话——它可能根本没被调用"
        )
    else:
        assert 旧标记 in 干完, (
            f"清理写漏，却没留下幽灵？预期旧标记 {旧标记} 在拆掉之后照样报「干完了」，实际 {干完}"
        )


def test_the_leaky_one_leaves_a_ghost(lab_home: LabHome, launch):
    """清理写漏的那版：拆掉之后旧的定时器**照样触发**——两份并存。

    这是这一项最要紧的一条。症状不是报错，是「看起来一切正常」。
    """
    profile, events_path = build(lab_home, "leaky-ghost", 版本="leaky")
    inst = launch(profile, wait_http=False)

    开工 = wait_for_report(inst, events_path, "开始干活")
    assert 开工 is not None, f"它没能开始干活：\n{inst.logs()}"
    旧标记 = 开工["data"]["标记"]

    time.sleep(干活毫秒 / 1000 / 2)
    改一行(profile)
    time.sleep(干活毫秒 / 1000 + 3.0)

    events = read_events(events_path)
    干完 = 标记们(events, "干完了")

    print("\n══ 清理写漏的那版 ══════════════════════════════════════")
    print(f"  开工时的标记：{旧标记}")
    print(f"  报过「干完了」的标记：{干完 or '（一个都没有）'}")
    # 旧的那份是什么时候被判定为拆完的，它又是什么时候说的话
    拆完时刻 = next(
        (float(e["ms"]) for e in of_kind(events, "status")
         if e.get("id") == "worker" and e.get("to") == "DISPOSED"),
        None,
    )
    幽灵说话 = next(
        (float(e["ms"]) for e in reports(events)
         if e.get("note") == "干完了" and (e.get("data") or {}).get("标记") == 旧标记),
        None,
    )

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert 旧标记 in 干完, (
        f"清理写漏却没留下幽灵？预期旧标记 {旧标记} 在拆掉之后照样报「干完了」，实际 {干完}"
    )
    assert 拆完时刻 is not None and 幽灵说话 is not None
    print(f"  旧的那份被判定拆完：{拆完时刻:.1f}ms")
    print(f"  它却在这时候还说了话：{幽灵说话:.1f}ms")
    print(f"  → **拆完之后又活了 {幽灵说话 - 拆完时刻:.0f}ms**，事件流里两个标记并存")
    assert 幽灵说话 > 拆完时刻, (
        "幽灵那句话应当出现在「拆完」之后——否则它只是拆之前的正常收尾，算不上幽灵"
    )


def test_what_the_caller_sees(lab_home: LabHome, launch):
    """旁观者在重载前后拿到的服务对象。

    它每秒查一次、如实上报：服务在不在、在的话是哪一份。
    重载那一瞬有没有一段拿不到的窗口，这里能看出来。
    """
    profile, events_path = build(lab_home, "seen", 版本="clean")
    inst = launch(profile, wait_http=False)

    开工 = wait_for_report(inst, events_path, "开始干活")
    assert 开工 is not None, f"它没能开始干活：\n{inst.logs()}"

    time.sleep(干活毫秒 / 1000 / 2)
    改一行(profile)
    time.sleep(干活毫秒 / 1000 + 3.0)

    events = read_events(events_path)
    查询 = [e for e in reports(events, who="watcher") if e.get("note") == "查了一次"]

    print("\n══ 旁观者每秒查一次，看到的是 ══════════════════════════")
    for e in 查询:
        d = e.get("data") or {}
        print(
            f"  {float(e['ms']):9.1f}ms  第 {d.get('第几次')} 次："
            f"{'拿到 ' + str(d.get('拿到谁')) if d.get('服务在吗') else '没拿到'}"
        )

    拿到过的 = [
        (e["data"] or {}).get("拿到谁") for e in 查询 if (e["data"] or {}).get("服务在吗")
    ]
    没拿到几次 = sum(1 for e in 查询 if not (e["data"] or {}).get("服务在吗"))
    不同的份 = sorted({x for x in 拿到过的 if x})
    print(f"\n  查到过的份：{不同的份}")
    print(f"  有几次没拿到：{没拿到几次}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert 查询, "旁观者一次都没查过——它可能自己就没跑起来"


def test_reload_does_not_hang_the_tree(lab_home: LabHome, launch):
    """重载一个正忙的插件，会不会把整棵树拖住。

    判据不用等谁说话：**别的条目还动不动**。旁观者每秒报一次，
    如果重载期间它照常在报，说明树没被卡住。
    """
    profile, events_path = build(lab_home, "nohang", 版本="clean")
    inst = launch(profile, wait_http=False)

    开工 = wait_for_report(inst, events_path, "开始干活")
    assert 开工 is not None, f"它没能开始干活：\n{inst.logs()}"

    time.sleep(干活毫秒 / 1000 / 2)
    改一行(profile)
    改动时刻 = time.monotonic()
    time.sleep(6.0)

    events = read_events(events_path)
    重载 = of_kind(events, "hmr-reload")
    查询 = [e for e in reports(events, who="watcher") if e.get("note") == "查了一次"]

    print("\n══ 重载期间树卡住了吗 ══════════════════════════════════")
    print(f"  hmr 报的重载次数：{len(重载)}")
    print(f"  旁观者一共查了：{len(查询)} 次")
    print(f"  实例还活着：{inst.alive()}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert len(查询) >= 3, (
        f"旁观者只查了 {len(查询)} 次——它每秒一次，跑了十来秒却这么少，"
        "说明重载期间有东西被拖住了"
    )
