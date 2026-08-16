"""seam · 想让多个实现并存，那就别让它们争名字

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/seam_registry/ -n 0 -s

上一项立住了一条铁律：一个名字只有一个主人，第二个来占的当场失败。
那想让多个实现并存怎么办？

办法不是去打破那条铁律，是**绕开**它：只让一个插件去占名字，别人往它肚子里的
那张表塞。从头到尾没人跟谁争。

这一项要看的是绕开之后，事情跟独占那边差在哪——尤其是**表空的时候**。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import LAB_ROOT, LabHome, LabProfile, entry_ids, of_kind, read_events, states_of, timeline  # noqa: E402

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

PLUGINS = ("roster.mjs", "contributor.mjs", "roster-user.mjs")

HEAD = """
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100

    - id: 名册
      name: ./roster.mjs
      config:
        见证: {w_roster}

    - id: 使用方
      name: ./roster-user.mjs
      config:
        见证: {w_user}
"""

CONTRIBUTOR = """
    - id: {id}
      name: ./contributor.mjs
      config:
        我叫: {name}
"""

#: 禁用一个已经挂上的条目：**保留原来的 insert 块，另起一个裸 id 块覆盖它**。
#: 换成裸 id 去改 insert 出来的条目是「覆盖已有条目」语义——目标存在才生效。
DISABLE = """
- id: {id}
  disabled: true
"""


def build(lab_home: LabHome, label: str, contributors: list[str]) -> tuple[LabProfile, Path, dict[str, Path]]:
    """搭一个实例：名册 + 使用方 + 若干注册方。"""
    events = lab_home.root / f"events-{label}.jsonl"
    witnesses = {name: lab_home.root / f"witness-{label}-{name}.json" for name in ("名册", "使用方")}

    patch = HEAD.format(
        out=json.dumps(events.as_posix()),
        w_roster=json.dumps(witnesses["名册"].as_posix()),
        w_user=json.dumps(witnesses["使用方"].as_posix()),
    )
    for name in contributors:
        patch += CONTRIBUTOR.format(id=name, name=json.dumps(name, ensure_ascii=False))

    profile = lab_home.make_minimal_profile(label, patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    for plugin in PLUGINS:
        shutil.copy2(FIXTURES / plugin, profile.dir / plugin)
    return profile, events, witnesses


def tables(events_path: Path) -> list[list[str]]:
    """使用方报过的那一串表快照，按时间先后。"""
    return [
        e.get("data") or []
        for e in of_kind(read_events(events_path), "report")
        if e.get("who") == "使用方" and e.get("note") == "表里现在有"
    ]


def latest_table(events_path: Path) -> list[str]:
    """使用方最近一次报出的表内容。一次都没报过就是空列表。"""
    got = tables(events_path)
    return got[-1] if got else []


def show(inst, events_path: Path, witnesses: dict[str, Path]) -> None:
    print(f"进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    for name, witness in witnesses.items():
        body = json.loads(witness.read_text(encoding="utf-8")) if witness.exists() else None
        detail = json.dumps(body, ensure_ascii=False) if body else ""
        print(f"    {name:<8} {'✅' if witness.exists() else '❌'}  {detail}")
    events = read_events(events_path)
    print(f"事件流：{len(events)} 条；出现过的条目 {sorted(entry_ids(events))}")
    print(f"使用方走过的状态：{states_of(events, '使用方') or '（一条都没有）'}")
    print(f"名册走过的状态：{states_of(events, '名册') or '（一条都没有）'}")
    snaps = tables(events_path)
    head = f"{snaps[:3]}{' …' if len(snaps) > 3 else ''}"
    print(f"使用方报过的表快照（{len(snaps)} 次）：{head} → 最后一次 {snaps[-1] if snaps else None}")


# ── 判定 1 · 两个注册方并存，谁也不撞谁 ─────────────────────────────────────


def test_two_contributors_coexist(lab_home: LabHome, launch):
    """两个插件往同一张表里各塞一行。

    对照上一项：那边两个插件抢同一个名字，一个当场失败、整个实例陪葬；
    这边两个插件往同一张表里塞，两个都活。
    """
    profile, events_path, witnesses = build(lab_home, "two", ["贡献甲", "贡献乙"])

    inst = launch(profile, wait_http=False)
    ok = inst.wait_for(
        lambda: sorted(latest_table(events_path)) == ["贡献乙", "贡献甲"], timeout=40.0, what="表里出现两行"
    )
    time.sleep(1.0)

    print("\n══ 两个注册方并存 ═══════════════════════════════════════")
    show(inst, events_path, witnesses)
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    assert ok, f"表里该有两行：\n{inst.logs(tail=80)}"
    assert inst.alive(), f"实例该照常活着：\n{inst.logs(tail=80)}"
    assert {"贡献甲", "贡献乙"} <= entry_ids(read_events(events_path)), "两个注册方都该在树上"


# ── 判定 2 · 一个注册方都没有，使用方照样活 ─────────────────────────────────


def test_empty_table_still_activates(lab_home: LabHome, launch):
    """把注册方全撤掉，只剩名册和使用方。

    **这是注册表式跟独占式最要紧的一处分别。**

    独占式那边，提供方缺席等于名字没人占，使用方 `inject` 不到就停在 PENDING，
    启动期还会拖垮整个实例。这边名字有人占着（名册自己），只是表是空的——
    使用方照常跑到 ACTIVE，什么都察觉不到。
    """
    profile, events_path, witnesses = build(lab_home, "empty", [])

    inst = launch(profile, wait_http=False)
    ok = inst.wait_for(lambda: witnesses["使用方"].exists(), timeout=40.0, what="使用方 apply 跑完")
    time.sleep(2.0)

    events = read_events(events_path)
    body = json.loads(witnesses["使用方"].read_text(encoding="utf-8")) if ok else {}

    print("\n══ 一个注册方都没有 ═════════════════════════════════════")
    show(inst, events_path, witnesses)
    print("\n完整时间线：")
    print(timeline(events))

    assert ok, f"使用方该照常跑完：\n{inst.logs(tail=80)}"
    assert inst.alive(), f"实例该照常活着——表空不是错误：\n{inst.logs(tail=80)}"
    assert body["apply时表里"] == [], f"表该是空的：{body}"
    assert "ACTIVE" in states_of(events, "使用方"), f"使用方该跑到 ACTIVE，实际 {states_of(events, '使用方')}"
    assert latest_table(events_path) == [], "表该一直是空的"


# ── 判定 3 · 注册方下线，只少它那一行 ───────────────────────────────────────


def test_contributor_leaves_only_removes_its_row(lab_home: LabHome, launch):
    """实例跑着的时候，把其中一个注册方禁用掉。

    要同时看两件事：
      * **该变的变了**：表里少了它那一行（用轮询等——该发生的事）
      * **不该变的没变**：名册和使用方的状态序列一个字都没多
        （它们的 fiber 要是被重挂了，序列里会多出 UNLOADING）
    """
    profile, events_path, witnesses = build(lab_home, "leave", ["贡献甲", "贡献乙"])

    inst = launch(profile, wait_http=False)
    assert inst.wait_for(
        lambda: sorted(latest_table(events_path)) == ["贡献乙", "贡献甲"], timeout=40.0, what="表里先出现两行"
    ), f"起手该有两行：\n{inst.logs(tail=80)}"

    before_user = states_of(read_events(events_path), "使用方")
    before_roster = states_of(read_events(events_path), "名册")
    print("\n══ 禁用「贡献乙」之前 ═══════════════════════════════════")
    print(f"  表里：{latest_table(events_path)}")
    print(f"  使用方状态：{before_user}")
    print(f"  名册状态：{before_roster}")

    profile.write_patch(profile.read_patch() + DISABLE.format(id="贡献乙"))

    ok = inst.wait_for(lambda: latest_table(events_path) == ["贡献甲"], timeout=30.0, what="表里只剩「贡献甲」")
    time.sleep(1.5)

    events = read_events(events_path)
    after_user = states_of(events, "使用方")
    after_roster = states_of(events, "名册")

    print("\n══ 禁用「贡献乙」之后 ═══════════════════════════════════")
    print(f"  表里：{latest_table(events_path)}")
    print(f"  使用方状态：{after_user}   {'没动' if after_user == before_user else '⚠️ 变了'}")
    print(f"  名册状态：{after_roster}   {'没动' if after_roster == before_roster else '⚠️ 变了'}")
    print(f"  贡献乙状态：{states_of(events, '贡献乙')}")
    print("\n表快照的变化：")
    for snap in tables(events_path):
        print(f"    {snap}")

    assert ok, f"表里该只剩一行：\n{inst.logs(tail=80)}"
    assert inst.alive(), f"实例该照常活着：\n{inst.logs(tail=80)}"
    assert after_user == before_user, f"使用方不该被碰：{before_user} → {after_user}"
    assert after_roster == before_roster, f"名册不该被碰：{before_roster} → {after_roster}"
    assert "DISPOSED" in states_of(events, "贡献乙"), f"下线的该是贡献乙自己：{states_of(events, '贡献乙')}"
