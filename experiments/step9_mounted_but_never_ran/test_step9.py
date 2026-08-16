"""第 9 步 · 挂上了但没执行

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/step9_mounted_but_never_ran/ -n 0 -s

第 5 步查的是「挂不上」——`name` 指不到东西，条目根本没进树。这一步是另一种：
条目在树上、`name` 也确实指到了那个文件，它却从来没跑过。

原因就是从第 2 步起每个插件都写着、却一直没解释的那一行：

    export const inject = ["labObserver"];

`inject` 声明的是**服务**：这个插件要用的东西，得由别人先提供出来。框架的做法是
**等** —— 服务没到齐，`apply` 就一次都不调用，那个条目停在 `PENDING` 上。

而等不到的下场很硬：boot 走完会点名还停在 `PENDING` 的条目，**整个实例起不来**。
第 1 步「只写 hmr 不写 timer」看到的就是这套机制的另一张脸，本文件把两者摆在一起对。
"""

from __future__ import annotations

import json
import re
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
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 前几步立起来的那三条，原样带过来
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

#: 第 1 步那个对照：故意只写 hmr、不写 timer
ONLY_HMR = """- insert:
    - id: hmr
      name: '{hmr}'

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
"""


def build(lab_home: LabHome, label: str, plugin: str) -> tuple[LabProfile, Path, Path]:
    """搭一个实例：框架三条 + 你写的那条。

    返回（profile，事件流路径，见证文件路径）。见证文件由插件自己写，
    只要它出现就说明 `apply` 跑过 —— 这一步不能只靠事件流判定，理由见插件源码。
    """
    events = lab_home.root / f"events-{label}.jsonl"
    witness = lab_home.root / f"witness-{label}.json"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    patch += f"""
- insert:
    - id: mine
      name: ./{plugin}
      config:
        见证: {json.dumps(witness.as_posix())}
"""
    profile = lab_home.make_profile(label, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(FIXTURES / plugin, profile.dir / plugin)
    return profile, events, witness


def wait_for_death(inst: Instance, timeout: float = 40.0) -> None:
    """等实例死。

    「该发生的事」用轮询等——比死等快，而且真不发生时照样会等满 timeout。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)


def verdicts(logs: str) -> list[str]:
    """从日志里挑出点名的那几句，去重保序。"""
    keep = [line.strip() for line in logs.splitlines() if "pending (waiting" in line or "did not activate" in line]
    return list(dict.fromkeys(keep))


def show(inst: Instance, events_path: Path, witness: Path) -> list[str]:
    """把一次启动失败的现场原样打出来，返回日志判词。"""
    logs = inst.logs(tail=80)
    lines = verdicts(logs)

    print(f"进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    print("日志里的判词：")
    for line in lines or ["（一句都没有，下面是完整日志）"]:
        print(f"    {line}")
    if not lines:
        print(logs)
    print(f"见证文件在不在：{witness.exists()}")

    events = read_events(events_path)
    print(f"事件流：{len(events)} 条；出现过的条目 {sorted(entry_ids(events))}")
    print(f"  mine 走过的状态：{states_of(events, 'mine') or '（一条都没有）'}")
    return lines


# ── 判定 1 · inject 一个永远不会出现的服务 ──────────────────────────────────


def test_waiting_for_a_service_that_never_comes(lab_home: LabHome, launch):
    """`inject` 里多写一个没人提供的服务，这条就永远不跑，而且拖垮整个实例。

    三条判定：
      * `apply` 一次都没跑 —— 见证文件不存在
      * 实例起不来 —— 进程退出，退出码非 0
      * 日志点名了那个等不到的服务
    """
    profile, events_path, witness = build(lab_home, "locked", "locked.mjs")

    inst = launch(profile, wait_http=False)
    wait_for_death(inst)

    print("\n══ inject 了一个没人提供的服务 ═══════════════════════════")
    lines = show(inst, events_path, witness)
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    assert not inst.alive(), f"实例居然活着 —— 那 PENDING 就不是致命的了：\n{inst.logs(tail=60)}"
    assert inst.proc.returncode != 0, "启动失败该有个非 0 的退出码"
    assert not witness.exists(), "见证文件出现了 —— 那 apply 其实跑过，判定整个反了"
    assert not reports(read_events(events_path), who="mine"), "没跑的插件不该说话"
    assert lines, f"日志里该点名等不到的服务：\n{inst.logs(tail=60)}"
    assert any("开锁服务" in line for line in lines), f"判词该点名「开锁服务」：{lines}"


# ── 判定 2 · 跟第 1 步那句话是同一个机制 ────────────────────────────────────


#: 判词的句式：`<等的人>: pending (waiting for service: <等的东西>)`
#: 前半截是那条条目的 `name`，不是它的 id —— 排错时按 name 去 patch 文件里找。
PENDING_LINE = re.compile(r"^(?P<who>.+): pending \(waiting for service: (?P<what>.+)\)$")


def test_same_verdict_as_step1(lab_home: LabHome, launch):
    """第 1 步「只写 hmr 不写 timer」，跟这一步是同一句判词、同一个机制。

    两次的差别只在**谁在等谁**：
      * 第 1 步：框架自带的 `hmr` 等 `timer`，而你没把 timer 写进去
      * 第 9 步：你写的插件等 `开锁服务`，而那个服务没有任何人提供

    等的人是谁、等的是不是框架自带的东西，判词一个字都不区分——
    句式一样、下场一样（整个实例起不来，退出码 1）。
    """
    profile_a, events_a, witness_a = build(lab_home, "cmp-mine", "locked.mjs")
    inst_a = launch(profile_a, wait_http=False)
    wait_for_death(inst_a)
    print("\n══ 第 9 步：你写的插件等一个没人提供的服务 ═══════════════")
    lines_a = show(inst_a, events_a, witness_a)

    events_b = lab_home.root / "events-cmp-hmr.jsonl"
    profile_b = lab_home.make_profile(
        "cmp-hmr", bundles=[], patch=ONLY_HMR.format(hmr=PKG_HMR, out=json.dumps(events_b.as_posix()))
    )
    profile_b.link_plugin("lab-recorder", OBSERVER)
    inst_b = launch(profile_b, wait_http=False)
    wait_for_death(inst_b)
    print("\n══ 第 1 步：只写 hmr、不写 timer ═════════════════════════")
    lines_b = verdicts(inst_b.logs(tail=80))
    print(f"进程还活着？ {inst_b.alive()}（退出码 {inst_b.proc.returncode}）")
    for line in lines_b or ["（一句都没有）"]:
        print(f"    {line}")

    def parse(lines: list[str]) -> list[re.Match]:
        return [m for line in lines if (m := PENDING_LINE.match(line))]

    def summary(lines: list[str]) -> list[str]:
        """去掉那句 pending，剩下的收尾判词。数字抹掉，只留句式。"""
        rest = [line for line in lines if not PENDING_LINE.match(line)]
        return sorted(dict.fromkeys(re.sub(r"\d+", "…", line) for line in rest))

    got_a, got_b = parse(lines_a), parse(lines_b)
    print("\n══ 两句判词拆开看 ════════════════════════════════════════")
    print(f"  {'':<8}{'谁在等（它的 name）':<36}{'等的是哪个服务'}")
    for tag, matches in (("第 9 步", got_a), ("第 1 步", got_b)):
        for m in matches:
            print(f"  {tag:<8}{m['who']:<36}{m['what']}")
    print("\n收尾判词（数字抹掉之后）：")
    print(f"  第 9 步：{summary(lines_a)}")
    print(f"  第 1 步：{summary(lines_b)}")

    assert not inst_b.alive(), "只写 hmr 的实例该起不来（第 1 步的判定）"
    assert inst_a.proc.returncode == inst_b.proc.returncode == 1, (
        f"两边该是同一个退出码：{inst_a.proc.returncode} / {inst_b.proc.returncode}"
    )
    assert got_a and got_b, f"两边都该有 pending 那句判词：{lines_a} / {lines_b}"
    assert [m["what"] for m in got_a] == ["开锁服务"], "第 9 步等的该是「开锁服务」"
    assert [m["what"] for m in got_b] == ["timer"], "第 1 步等的该是 timer"
    assert summary(lines_a) == summary(lines_b), (
        f"收尾判词该完全一样，是同一个机制：\n  {summary(lines_a)}\n  {summary(lines_b)}"
    )


# ── 判定 3 · 对照组：不声明就不等，它照样跑 ─────────────────────────────────


def test_without_inject_it_runs(lab_home: LabHome, launch):
    """同一个插件，去掉 `inject` 那一行、改成运行时 `ctx.get` 取——它跑起来了。

    这条把病因钉死：卡住它的是**等**，不是「找不到那个文件」（那是第 5 步的事）。
    `开锁服务` 在这个实例里同样一个都不存在，插件却照跑，只是取到的是空。

    代价一并看到了：不声明就没人替你排队，`apply` 跑的那一刻服务在不在全凭运气
    —— 见证文件里连观察器都可能是空的。`inject` 换来的正是「等到就位再跑」。
    """
    profile, events_path, witness = build(lab_home, "unlocked", "unlocked.mjs")

    inst = launch(profile, wait_http=False)
    got = inst.wait_for(lambda: witness.exists(), timeout=40.0, what="见证文件出现（说明 apply 跑了）")
    assert got

    time.sleep(2.0)  # 让采集器把事件刷完
    events = read_events(events_path)
    said = reports(events, who="mine")
    body = json.loads(witness.read_text(encoding="utf-8"))

    print("\n══ 去掉 inject 那一行之后 ════════════════════════════════")
    print(f"进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    print(f"见证文件：{json.dumps(body, ensure_ascii=False)}")
    print(f"它说的话：{[e.get('note') for e in said] or '（一句都没有）'}")
    print(f"它走过的状态：{states_of(events, 'mine') or '（采集器睁眼前就走完了）'}")
    print("\n完整时间线：")
    print(timeline(events))

    assert inst.alive(), f"实例应当照常活着：\n{inst.logs(tail=60)}"
    assert body["跑了"] is True, "见证文件在，内容却不对"
    assert body["拿到开锁服务"] is False, "居然取到了「开锁服务」—— 那这个实例里有人提供它，对照就不成立了"
    assert "mine" in entry_ids(events), f"它该在树上：{sorted(entry_ids(events))}"
    assert "ACTIVE" in states_of(events, "mine"), f"它该跑到 ACTIVE，实际走过 {states_of(events, 'mine')}"
