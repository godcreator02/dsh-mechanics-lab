"""第 8 步 · 改别人已经挂上的条目

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/step8_change_an_existing_entry/ -n 0 -s

前七步在 patch 文件里写的一直是 `- insert:` —— **加一条**。这一步用另一种写法：

    - id: speaker          ← 顶格一条，不带 insert
      config: ...

它不加新的，而是**改前面已经存在的那一条**。同一个 patch 文件里两种写法并排放着，
差别只在有没有 `insert` 这个词。

本步的四个用例把这种写法的四种结果摆齐：改得掉什么、改到不存在的 id 会怎样、
`insert` 两次同一个 id 会怎样、以及能不能用它把一个条目关掉。
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
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
SPEAKER = Path(__file__).resolve().parent / "fixtures" / "speaker.mjs"

#: 第 1 步立起来的那三条，原样带过来
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

#: 先按前七步的老办法把 speaker 挂上，写两个 config 键，好看清后面改动了什么
MOUNTED = """
- insert:
    - id: speaker
      name: ./speaker.mjs
      config:
        台词: 原来的台词
        音量: 3
"""

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def build(lab_home: LabHome, name: str, *, tail: str) -> tuple[LabProfile, Path]:
    """搭一个实例，`tail` 原样接在 patch 文件后面。

    patch 文件是 YAML 数组，条目按写下的顺序一条条处理 —— 所以「改已有条目」
    的那一条必须写在**它要改的那条后面**，直接拼字符串就行。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix())) + tail
    profile = lab_home.make_profile(name, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(SPEAKER, profile.dir / "speaker.mjs")
    return profile, events


def wait_for_speaker(inst: Instance, path: Path, *, timeout: float = 40.0) -> list[dict]:
    """等到 speaker 自己把话说出来为止。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        said = reports(read_events(path), who="speaker")
        if said:
            return said
        if not inst.alive():
            break
        time.sleep(0.3)
    return reports(read_events(path), who="speaker")


def wait_for_events(inst: Instance, path: Path, *, least: int = 5, timeout: float = 40.0) -> list[dict]:
    """等观察器把事件刷出来 —— 用于「speaker 不该说话」那类用例的起跑线。"""
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


def only_report(said: list[dict]) -> dict:
    assert said, "speaker 没说话 —— 它的 apply 可能压根没跑"
    return said[0]["data"]


def log_lines(inst: Instance, needle: str) -> list[str]:
    """从实例的完整日志里挑出带某个词的行（去掉颜色码）。

    读的是**整份**日志文件，不是 `inst.logs()` 的末尾几行 —— 启动早期的判词
    很容易被后面的输出挤出去。
    """
    hits = []
    for path in (inst.err_log, inst.out_log):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            plain = _ANSI.sub("", line).strip()
            if needle in plain:
                hits.append(plain)
    return hits


def test_bare_id_changes_the_entry_that_is_already_there(lab_home: LabHome, launch):
    """不带 `insert` 的那条改掉了前面那条的 `config` —— speaker 报出来的是新值。

    顺带看清一件很要紧的事：`config` 是**整个换掉**的。前面写了两个键，
    改的时候只写了一个，另一个就没了 —— 不是把新键并进旧的里面。
    """
    profile, events_path = build(
        lab_home,
        "override",
        tail=MOUNTED
        + """
- id: speaker
  config:
    台词: 改过的台词
""",
    )

    inst = launch(profile, wait_http=False)
    said = wait_for_speaker(inst, events_path)
    events = read_events(events_path)

    print("\n══ 前面挂一条，后面改一条 ════════════════════════════════")
    print(timeline(events, kinds=("report",)))

    got = only_report(said)
    print("\n  patch 里先写的：  {'台词': '原来的台词', '音量': 3}")
    print("  后面那条改成：    {'台词': '改过的台词'}")
    print(f"  speaker 实际收到：{json.dumps(got['内容'], ensure_ascii=False)}")
    print(f"  speaker 一共说了几句：{len(said)}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got["内容"] == {"台词": "改过的台词"}, f"应当收到改过之后的 config，实际 {got['内容']}"
    assert len(said) == 1, f"speaker 只该有一份、说一句 —— 说了 {len(said)} 句就说明它被挂了不止一次"


def test_changing_an_id_that_is_not_there(lab_home: LabHome, launch):
    """把 id 打错一个字母：那一条作废，同一个文件里其余的照常生效，**而且没有任何提示**。

    三条摆在一起 —— 挂上 speaker、改一个不存在的 `speakr`、再改一次 speaker。
    读者最想知道的是中间那条的下场：它不会变成一个新条目，也不会让实例起不来，
    日志里更是一个字都没有。跟第 3 步「config 键名拼错」一样，**打错了没人会告诉你**。

    （日志空白这条另外验过一次：把实例换成带全套官方条目的那种，日志同样是空的
    —— 所以「什么都不说」不是这个最小实例特有的。）
    """
    profile, events_path = build(
        lab_home,
        "typo",
        tail=MOUNTED
        + """
- id: speakr
  config:
    台词: 这条打空了

- id: speaker
  config:
    台词: 后面这条照样生效
""",
    )

    inst = launch(profile, wait_http=False)
    said = wait_for_speaker(inst, events_path)
    events = read_events(events_path)

    got = only_report(said)
    ids = sorted(entry_ids(events))
    noise = log_lines(inst, "speakr") + log_lines(inst, "patch")

    print("\n══ 改一个不存在的 id ═════════════════════════════════════")
    print(f"  实例还活着？        {inst.alive()}")
    print(f"  出现过的条目：      {ids}")
    print(f"  speaker 收到的：    {json.dumps(got['内容'], ensure_ascii=False)}")
    print(f"  日志里说了什么：    {noise or '（一个字都没有）'}")

    assert inst.alive(), f"实例应当照常活着 —— 打空一条不是致命错误：\n{inst.logs()}"
    assert "speakr" not in ids, f"打错的那个 id 不该凭空变成一个条目，实际 {ids}"
    assert got["内容"] == {"台词": "后面这条照样生效"}, f"同一个文件里后面那条该照常生效，实际 {got['内容']}"
    assert not noise, f"这一条是悄悄作废的，日志里不该有任何提示，实际 {noise}"


def test_inserting_the_same_id_twice(lab_home: LabHome, launch):
    """`insert` 两次同一个 id：实例**根本起不来**。

    容易想成「后面那条盖掉前面那条」或者「两份一起跑」 —— 都不是。
    `insert` 只管加，加出两条一样的 id，启动时直接判死。
    """
    profile, events_path = build(
        lab_home,
        "twice",
        tail="""
- insert:
    - id: speaker
      name: ./speaker.mjs
      config:
        台词: 第一次

- insert:
    - id: speaker
      name: ./speaker.mjs
      config:
        台词: 第二次
""",
    )

    inst = launch(profile, wait_http=False)

    # 验「不该活着」：等一段固定时间，不能轮询提前退出
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)

    verdict = log_lines(inst, "duplicate")
    said = reports(read_events(events_path), who="speaker")

    print("\n══ insert 两次同一个 id ══════════════════════════════════")
    print(f"  进程还活着？        {inst.alive()}（退出码 {inst.proc.returncode}）")
    print(f"  speaker 说过话吗？  {len(said)} 句")
    print(f"  日志里的判词：      {verdict or '（没找到，看完整日志）'}")
    if not verdict:
        print(inst.logs())

    assert not inst.alive(), "两条同 id 的居然跑起来了 —— 那这个写法就不是判死"
    assert verdict, f"应当有一句点名重复 id 的判词：\n{inst.logs()}"
    assert any("speaker" in line for line in verdict), f"判词该点名 speaker：{verdict}"
    assert not said, "实例都没起来，speaker 不该说过话"


def test_bare_id_can_switch_disabled_on(lab_home: LabHome, launch):
    """`disabled` 也改得掉：前面挂上的那条，后面一条就能把它关掉。

    这一步不用回去改前面那条 —— 前面那行原样留着，关不关由后面那条说了算。
    """
    profile, events_path = build(
        lab_home,
        "switch-off",
        tail=MOUNTED
        + """
- id: speaker
  disabled: true
""",
    )

    inst = launch(profile, wait_http=False)
    wait_for_events(inst, events_path, least=5)

    # 验「不该发生」：固定等一段，不能轮询提前退出
    Instance.settle(10.0)
    events = read_events(events_path)
    said = reports(events, who="speaker")

    print("\n══ 后面一条把它关掉 ══════════════════════════════════════")
    print(f"  实例还活着？        {inst.alive()}")
    print(f"  出现过的条目：      {sorted(entry_ids(events))}")
    print(f"  speaker 说的话：    {[e.get('note') for e in said] or '（一句都没有）'}")

    assert inst.alive(), f"实例应当照常活着 —— 关掉一个条目不是错误：\n{inst.logs()}"
    assert not said, f"speaker 已经被关掉了，不该说话：{said}"
