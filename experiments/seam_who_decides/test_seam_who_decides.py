"""seam · 使用方能不能跑起来，谁说了算

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/seam_who_decides/ -n 0 -s

前三项读下来，很容易得出这么个印象：**独占式**的提供方缺席，使用方就卡住、
整个实例陪葬；**注册表式**的表是空的，使用方照样活。好像命运是由「怎么安排多个
实现」决定的。

这一项拆穿它。

三个用例共用同一个使用方文件，一个字都不改；换的只是对面那个名册。
而两份名册之间只差一个方法。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import LAB_ROOT, Instance, LabHome, LabProfile, read_events, states_of, timeline  # noqa: E402

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

PLUGINS = ("roster-loose.mjs", "roster-strict.mjs", "roster-user.mjs")

LOOSE = "roster-loose.mjs"
STRICT = "roster-strict.mjs"

PATCH = """
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100

    - id: 名册
      name: ./{roster}
      config:
        预置: {preset}

    - id: 使用方
      name: ./roster-user.mjs
      config:
        见证: {witness}
"""


def build(lab_home: LabHome, label: str, roster: str, preset: list[str]) -> tuple[LabProfile, Path, Path]:
    """搭一个实例：一份名册 + 那个从不改动的使用方。"""
    events = lab_home.root / f"events-{label}.jsonl"
    witness = lab_home.root / f"witness-{label}.json"
    patch = PATCH.format(
        out=json.dumps(events.as_posix()),
        roster=roster,
        preset=json.dumps(preset, ensure_ascii=False),
        witness=json.dumps(witness.as_posix()),
    )
    profile = lab_home.make_minimal_profile(label, patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    for plugin in PLUGINS:
        shutil.copy2(FIXTURES / plugin, profile.dir / plugin)
    return profile, events, witness


def settle(inst: Instance, timeout: float = 25.0) -> None:
    """等进程尘埃落定：死了就返回，一直活着就等满。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)


def verdicts(logs: str) -> list[str]:
    """日志里点名的那几句，去重保序。"""
    keep = [line.strip() for line in logs.splitlines() if "pending (waiting" in line or "did not activate" in line]
    return list(dict.fromkeys(keep))


def show(inst: Instance, events_path: Path, witness: Path) -> None:
    print(f"进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    print(f"使用方跑了吗（见证文件）：{'✅ 跑了' if witness.exists() else '❌ 没跑'}")
    if witness.exists():
        print(f"    {witness.read_text(encoding='utf-8')}")
    lines = verdicts(inst.logs(tail=80))
    print("日志里的判词：")
    for line in lines or ["（一句都没有）"]:
        print(f"    {line}")
    events = read_events(events_path)
    print(f"名册走过的状态：{states_of(events, '名册') or '（一条都没有）'}")
    print(f"使用方走过的状态：{states_of(events, '使用方') or '（一条都没有）'}")


# ── 判定 1 · 严格版 + 空表：使用方卡住，整个实例陪葬 ─────────────────────────


def test_strict_and_empty_kills_the_instance(lab_home: LabHome, launch):
    """名册占住了名字、对象也造出来了，但它说自己「表空就不算可用」。

    使用方于是拿不到 —— 下场跟「压根没人提供这个名字」一样：停在 PENDING，
    boot 走完点名，整个实例起不来。

    **但判词不一样，而且是往难查的方向不一样。** 没人提供时框架点得出名字
    （`waiting for service: 那个名字`）；判据否决时它只会说
    `waiting for services: unknown` —— 名字确实被占着，审计那一侧看不出缺谁。
    """
    profile, events_path, witness = build(lab_home, "strict-empty", STRICT, [])

    inst = launch(profile, wait_http=False)
    settle(inst)

    print("\n══ 严格版 + 空表 ════════════════════════════════════════")
    show(inst, events_path, witness)
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    events = read_events(events_path)
    lines = verdicts(inst.logs(tail=80))

    assert not inst.alive(), f"该起不来：\n{inst.logs(tail=60)}"
    assert inst.proc.returncode == 1, f"该是退出码 1，实际 {inst.proc.returncode}"
    assert not witness.exists(), "使用方的 apply 一次都不该跑"
    assert any("pending (waiting for services: unknown)" in line for line in lines), (
        f"判据否决造成的 PENDING，判词里报不出服务名（这正是它难查的地方）：{lines}"
    )
    assert not any("labRoster" in line for line in lines), (
        f"判词里不该出现服务名 —— 名字确实被占着，审计那侧看不出缺谁：{lines}"
    )
    assert "ACTIVE" in states_of(events, "名册"), (
        f"名册自己该是活的 —— 卡住使用方的不是「名册没起来」：{states_of(events, '名册')}"
    )


# ── 判定 2 · 严格版 + 表里有东西：使用方照常跑 ──────────────────────────────


def test_strict_with_rows_runs_fine(lab_home: LabHome, launch):
    """同一份严格名册，只让它开张时表里就有一行。

    判据这回答「可用」，使用方立刻拿得到。**说明卡住它的从来不是「严格」这个
    写法本身，是那一刻判据给出的答案。**
    """
    profile, events_path, witness = build(lab_home, "strict-filled", STRICT, ["先来的"])

    inst = launch(profile, wait_http=False)
    ok = inst.wait_for(lambda: witness.exists(), timeout=40.0, what="使用方跑完")
    time.sleep(2.0)

    print("\n══ 严格版 + 表里有一行 ══════════════════════════════════")
    show(inst, events_path, witness)
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    assert ok, f"使用方该照常跑：\n{inst.logs(tail=80)}"
    assert inst.alive(), f"实例该照常活着：\n{inst.logs(tail=80)}"
    body = json.loads(witness.read_text(encoding="utf-8"))
    assert body["表里"] == ["先来的"], f"使用方该看得见表里那一行：{body}"
    assert "ACTIVE" in states_of(read_events(events_path), "使用方"), "使用方该跑到 ACTIVE"


# ── 判定 3 · 宽松版 + 空表：同样是空表，这回使用方活了 ───────────────────────


def test_loose_and_empty_runs_fine(lab_home: LabHome, launch):
    """跟判定 1 摆在一起看：**表同样是空的，使用方也同样一个字没改。**

    唯一的差别是名册那边少写了一个判据方法。少了它，框架不再问「你现在算可用吗」，
    名字占上了就当可用 —— 使用方照常跑到 ACTIVE，拿到一张空表。

    所以「使用方能不能跑起来」不由「独占还是注册表」决定，
    由**那一刻的可用性判据**决定。前三项看到的差别，根子在这儿。
    """
    profile, events_path, witness = build(lab_home, "loose-empty", LOOSE, [])

    inst = launch(profile, wait_http=False)
    ok = inst.wait_for(lambda: witness.exists(), timeout=40.0, what="使用方跑完")
    time.sleep(2.0)

    print("\n══ 宽松版 + 空表 ════════════════════════════════════════")
    show(inst, events_path, witness)
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    assert ok, f"使用方该照常跑：\n{inst.logs(tail=80)}"
    assert inst.alive(), f"实例该照常活着：\n{inst.logs(tail=80)}"
    body = json.loads(witness.read_text(encoding="utf-8"))
    assert body["表里"] == [], f"它拿到的该是一张空表：{body}"
    assert "ACTIVE" in states_of(read_events(events_path), "使用方"), "使用方该跑到 ACTIVE"
