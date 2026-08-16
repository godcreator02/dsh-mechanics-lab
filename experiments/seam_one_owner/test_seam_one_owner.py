"""seam · 一个名字一个主人

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/seam_one_owner/ -n 0 -s

前面每一步里，你写的插件都在**用**别人提供的东西（`inject` 那一行）。
这一步反过来：你自己提供一个东西，让别的插件来用。

提供有两种写法——把一个普通对象挂到某个名字上，或者继承框架的服务基类。
本文件把两种写法摆在一起，问同一个问题：

    两个插件想占同一个名字，会怎样？

写法不同，答案会不会不同？
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
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 两种写法各一个文件，做的事完全一样，只是占名的写法不同
BARE = "bare-owner.mjs"
KLASS = "class-owner.mjs"

#: 撞车时框架说的那句话。**两种写法共用这一个常量**——本实验的核心判定就是
#: 「换了写法，这句一字不差」，所以它必须是同一份字面量，不能各写各的。
COLLIDE = 'service "labSeat" has been registered at'

RECORDER = """
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
"""

OWNER = """
- insert:
    - id: {id}
      name: ./{plugin}
      config:
        名字: {name}
        我是谁: {who}
        见证: {witness}
"""


def build(
    lab_home: LabHome, label: str, owners: list[tuple[str, str, str]]
) -> tuple[LabProfile, Path, dict[str, Path]]:
    """搭一个实例：基础设施 + 采集器 + 若干个「想占名字的插件」。

    `owners` 每项是（条目 id，插件文件，它想占的名字）。

    返回（profile，事件流路径，各条目的见证文件）。见证文件由插件自己写，
    **只在占名成功之后才写** —— 所以它在不在，就是「占上了没有」的判据。
    """
    events = lab_home.root / f"events-{label}.jsonl"
    patch = RECORDER.format(out=json.dumps(events.as_posix()))

    witnesses: dict[str, Path] = {}
    plugins: set[str] = set()
    for entry_id, plugin, name in owners:
        witness = lab_home.root / f"witness-{label}-{entry_id}.json"
        witnesses[entry_id] = witness
        plugins.add(plugin)
        patch += OWNER.format(
            id=entry_id,
            plugin=plugin,
            name=json.dumps(name, ensure_ascii=False),
            who=json.dumps(entry_id, ensure_ascii=False),
            witness=json.dumps(witness.as_posix()),
        )

    profile = lab_home.make_minimal_profile(label, patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    for plugin in plugins:
        shutil.copy2(FIXTURES / plugin, profile.dir / plugin)
    return profile, events, witnesses


def settle(inst: Instance, timeout: float = 25.0) -> None:
    """等进程尘埃落定：死了就返回，一直活着就等满。

    这一步不预设「该不该死」——两种结局都要如实记录，所以既不能只轮询死亡，
    也不能只固定等待。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)


def collisions(logs: str) -> list[str]:
    """日志里跟「这个名字已经有主了」有关的那几句，去重保序。"""
    keep = [
        line.strip()
        for line in logs.splitlines()
        if "has been registered" in line or "did not activate" in line or "failed to load" in line
    ]
    return list(dict.fromkeys(keep))


def show(inst: Instance, events_path: Path, witnesses: dict[str, Path]) -> list[str]:
    """把现场原样打出来，返回日志里的判词。"""
    logs = inst.logs(tail=100)
    lines = collisions(logs)

    print(f"进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    print("谁占上了名字（见证文件在不在）：")
    for entry_id, witness in witnesses.items():
        got = witness.exists()
        body = json.loads(witness.read_text(encoding="utf-8")) if got else None
        detail = json.dumps(body, ensure_ascii=False) if body else ""
        print(f"    {entry_id:<12} {'✅ 占上了' if got else '❌ 没占上'}   {detail}")
    print("日志里的判词：")
    for line in lines or ["（一句都没有，下面是完整日志）"]:
        print(f"    {line}")
    if not lines:
        print(logs)

    events = read_events(events_path)
    print(f"事件流：{len(events)} 条；出现过的条目 {sorted(entry_ids(events))}")
    for entry_id in witnesses:
        print(f"  {entry_id} 走过的状态：{states_of(events, entry_id) or '（一条都没有）'}")
    served = [e for e in of_kind(events, "service") if str(e.get("serviceName", "")).startswith("labSeat")]
    print("服务出现 / 撤销：")
    for e in served or []:
        print(
            f"    {e['ms']:8.1f}ms  {e['serviceName']:<12} {'出现' if e.get('present') else '撤销'}  由 {e.get('who')}"
        )
    if not served:
        print("    （一条都没有）")
    return lines


def occupants(witnesses: dict[str, Path]) -> list[str]:
    """真正占上名字的那些条目 id。"""
    return [entry_id for entry_id, witness in witnesses.items() if witness.exists()]


# ── 判定 1 · 两个裸做法抢同一个名字 ─────────────────────────────────────────


def test_two_bare_owners_collide(lab_home: LabHome, launch):
    """两个插件都用最短的那种写法，去占同一个名字。

    观察三件事：谁占上了、日志说了什么、整个实例还活不活。
    """
    profile, events_path, witnesses = build(
        lab_home, "bare-vs-bare", [("裸甲", BARE, "labSeat"), ("裸乙", BARE, "labSeat")]
    )

    inst = launch(profile, wait_http=False)
    settle(inst)

    print("\n══ 两个裸做法抢同一个名字 ═══════════════════════════════")
    lines = show(inst, events_path, witnesses)
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    got = occupants(witnesses)
    events = read_events(events_path)
    loser = next(entry_id for entry_id in witnesses if entry_id not in got)

    assert len(got) == 1, f"该恰好有一个占上、另一个占不上，实际占上的是 {got}"
    assert any(COLLIDE in line for line in lines), f"该报「这个名字已经有主了」：{lines}"
    assert "FAILED" in states_of(events, loser), f"没占上的那个该走到 FAILED，实际 {states_of(events, loser)}"
    assert not inst.alive() and inst.proc.returncode == 1, "启动期撞车该拖垮整个实例"


# ── 判定 2 · 换一种写法，还是抢不到 ─────────────────────────────────────────


def test_bare_and_class_collide_too(lab_home: LabHome, launch):
    """一个用裸做法、一个用服务基类，去占同一个名字。

    **这条用例回答的是：独占是不是服务基类那种写法特有的？**

    如果两种写法各有各的地盘，这里就该两个都占上；
    如果它们共用同一条通道，那结果该跟判定 1 一模一样。
    """
    profile, events_path, witnesses = build(
        lab_home, "bare-vs-class", [("裸的", BARE, "labSeat"), ("基类的", KLASS, "labSeat")]
    )

    inst = launch(profile, wait_http=False)
    settle(inst)

    print("\n══ 裸做法 vs 服务基类，抢同一个名字 ═════════════════════")
    lines = show(inst, events_path, witnesses)
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    got = occupants(witnesses)
    events = read_events(events_path)
    loser = next(entry_id for entry_id in witnesses if entry_id not in got)

    assert len(got) == 1, f"换了写法也该只有一个占上，实际占上的是 {got}"
    # 判定 1 用的是同一个 COLLIDE 常量 —— 两种写法撞出**一模一样**的那句话，
    # 就是「两条写法共用同一条注册通道」的直接证据
    assert any(COLLIDE in line for line in lines), f"该报出跟判定 1 一字不差的那句：{lines}"
    assert "FAILED" in states_of(events, loser), f"没占上的那个该走到 FAILED，实际 {states_of(events, loser)}"
    assert not inst.alive() and inst.proc.returncode == 1, "启动期撞车该拖垮整个实例"


# ── 判定 3 · 对照：各占各的名字 ─────────────────────────────────────────────


def test_different_names_both_live(lab_home: LabHome, launch):
    """同样是两个插件、同样是两种写法，只把名字改成不一样的。

    这条把病因钉死：撞车的原因是**名字相同**，不是「有两个提供者」，
    也不是「两种写法混用」。
    """
    profile, events_path, witnesses = build(
        lab_home, "no-collision", [("裸的", BARE, "labSeatA"), ("基类的", KLASS, "labSeatB")]
    )

    inst = launch(profile, wait_http=False)
    ok = inst.wait_for(
        lambda: all(w.exists() for w in witnesses.values()), timeout=40.0, what="两个见证文件都出现（说明两边都占上了）"
    )
    time.sleep(2.0)  # 让采集器把事件刷完

    print("\n══ 各占各的名字 ═════════════════════════════════════════")
    show(inst, events_path, witnesses)
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    assert ok, f"两个插件该都占上：\n{inst.logs(tail=80)}"
    assert inst.alive(), f"实例该照常活着：\n{inst.logs(tail=80)}"
    assert sorted(occupants(witnesses)) == ["基类的", "裸的"], "两个都该占上"
    events = read_events(events_path)
    assert reports(events, who="裸的"), "裸做法那个该说过话"
    assert reports(events, who="基类的"), "基类那个该说过话"
