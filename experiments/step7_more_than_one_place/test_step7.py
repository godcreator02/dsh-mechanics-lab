"""第 7 步 · 配置不止一处

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/step7_more_than_one_place/ -n 0 -s

前六步一直在改同一个文件：profile 目录里的那个 patch 文件。它不是唯一的一处。

home 目录里还有一个 `cordis.patch.yml`（就是 `$DSH_HOME/cordis.patch.yml`）。
两处各是一**层**：profile 那层只管自己这个 profile，home 那层管这个 home 下的
**每一个** profile。实例启动时把两层拼起来，profile 那层在前、home 那层在后。

这一步验四件事：

1. 只在 home 那处写的条目，照样挂上、照样跑、照样收到自己那份 `config`
2. home 那处写一次，这个 home 下每个 profile 都吃到
3. 两处写的是不同的 `id`，两条都在，各收各的 `config`
4. 两处写的是**同一个 `id`** —— 那是两个条目，不是一个，实例直接起不来

判据全部落在**插件自己报出来的 `config` 内容**上：写进哪个文件是我们做的事，
收到什么是它说的事，两边摆在一起才叫对上了。
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
    entry_ids,
    read_events,
    reports,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
REPORTER = Path(__file__).resolve().parent / "fixtures" / "reporter.mjs"

#: 前几步立起来的三条，原样带过来。它们写在 **profile 那处**。
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


@pytest.fixture(autouse=True)
def _clean_home_patch(lab_home: LabHome):
    """每个用例跑完把 home 那处清空。

    home 那层对整个 home 生效，一个用例留下的内容会直接串进下一个用例——
    这也正是这一步必须用自己的假 home 的理由。
    """
    yield
    lab_home.clear_home_patch()


def build(lab_home: LabHome, name: str, *, profile_extra: str = "") -> tuple[LabProfile, Path]:
    """搭一个 profile：基础三条 +（可选）写在 profile 那处的条目。

    home 那处由各用例自己写（`lab_home.write_home_patch`），因为它不属于任何一个
    profile —— 那正是这一步要讲的事。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    profile = lab_home.make_profile(name, bundles=[], patch=patch + profile_extra)
    profile.link_plugin("lab-recorder", OBSERVER)
    # 插件文件拷进 profile 目录。注意：home 那处写的条目也用 `./reporter.mjs`
    # 找它 —— `name` 是相对**这个 profile 的目录**去找的，跟条目写在哪一层无关
    shutil.copy2(REPORTER, profile.dir / "reporter.mjs")
    return profile, events


def wait_said(inst: Instance, path: Path, who: str, *, timeout: float = 40.0) -> list[dict]:
    """等某个条目把自己收到的 config 报出来。

    等的是**它自己的上报**，不是事件总数 —— 那才是这一步的判据。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        said = reports(read_events(path), who=who)
        if said:
            return said
        if not inst.alive():
            break
        time.sleep(0.3)
    return reports(read_events(path), who=who)


def got_config(said: list[dict], who: str) -> dict | None:
    assert said, f"{who} 没说话 —— 它的 apply 可能压根没跑"
    return said[0]["data"]["内容"]


def test_the_other_place_works_the_same(lab_home: LabHome, launch):
    """条目写在 home 那处，跟写在 profile 那处一样好使。

    profile 那处一个字都没多写，条目照样挂上、`apply` 照样跑、`config` 照样送到。
    """
    profile, events_path = build(lab_home, "home-side")
    lab_home.write_home_patch("""# 这是 home 那处：$DSH_HOME/cordis.patch.yml
- insert:
    - id: in-home
      name: ./reporter.mjs
      config:
        出处: home 那处
""")

    inst = launch(profile, wait_http=False)
    said = wait_said(inst, events_path, "in-home")

    print("\n══ 条目写在 home 那处 ════════════════════════════════════")
    print(f"  文件：{lab_home.patch_path}")
    print("  profile 那处写了什么：只有 timer / hmr / 观察器 —— 没有 in-home")
    print(timeline(read_events(events_path), kinds=("report",)))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "in-home" in entry_ids(read_events(events_path)), "home 那处写的条目应当出现在树上"
    assert got_config(said, "in-home") == {"出处": "home 那处"}


def test_the_home_place_hits_every_profile(lab_home: LabHome, launch):
    """home 那处写一次，这个 home 下**每个** profile 都吃到。

    这是两处最大的差别，也是它被叫做「一层」的原因：它不属于任何一个 profile。
    两个 profile 各自跑一个实例，各自有自己的观察器、自己的事件流，但两边都能
    看到同一条 —— 而且收到的 `config` 是同一份。
    """
    lab_home.write_home_patch("""- insert:
    - id: in-home
      name: ./reporter.mjs
      config:
        出处: home 那处
""")
    first, first_events = build(lab_home, "twin-a")
    second, second_events = build(lab_home, "twin-b")

    inst_a = launch(first, wait_http=False)
    inst_b = launch(second, wait_http=False)
    said_a = wait_said(inst_a, first_events, "in-home")
    said_b = wait_said(inst_b, second_events, "in-home")

    print("\n══ home 那处写一次，两个 profile 都吃到 ══════════════════")
    print(f"  profile {first.name} 收到：{got_config(said_a, 'in-home')}")
    print(f"  profile {second.name} 收到：{got_config(said_b, 'in-home')}")

    assert inst_a.alive() and inst_b.alive(), f"两个实例都该活着：\n{inst_a.logs()}\n{inst_b.logs()}"
    assert got_config(said_a, "in-home") == {"出处": "home 那处"}
    assert got_config(said_b, "in-home") == {"出处": "home 那处"}


def test_two_places_two_entries(lab_home: LabHome, launch):
    """两处各写一条、`id` 不同 —— 两条都在，各收各的。

    两层是**拼**在一起的，不是二选一：profile 那处写的不会因为 home 那处也写了
    东西就消失。
    """
    profile, events_path = build(
        lab_home,
        "both-sides",
        profile_extra="""
- insert:
    - id: in-profile
      name: ./reporter.mjs
      config:
        出处: profile 那处
""",
    )
    lab_home.write_home_patch("""- insert:
    - id: in-home
      name: ./reporter.mjs
      config:
        出处: home 那处
""")

    inst = launch(profile, wait_http=False)
    said_profile = wait_said(inst, events_path, "in-profile")
    said_home = wait_said(inst, events_path, "in-home")

    print("\n══ 两处各写一条 ══════════════════════════════════════════")
    print(timeline(read_events(events_path), kinds=("report",)))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got_config(said_profile, "in-profile") == {"出处": "profile 那处"}
    assert got_config(said_home, "in-home") == {"出处": "home 那处"}


def test_same_id_in_both_places_will_not_start(lab_home: LabHome, launch):
    """两处写了**同一个 `id`** —— 实例起不来。

    这是「配置不止一处」最容易踩的那一脚：你在 home 那处加了一条，忘了 profile
    那处早就有个同名的。两层拼起来之后那是**两个条目**，不是一个被另一个改掉，
    于是 `id` 撞了，进程当场退出，日志里点名是哪个 `id`。

    所以没有「谁说了算」这回事：两处都写同一个 `id`，谁都不算数，实例根本起不来。
    """
    profile, events_path = build(
        lab_home,
        "same-id",
        profile_extra="""
- insert:
    - id: both
      name: ./reporter.mjs
      config:
        出处: profile 那处
""",
    )
    lab_home.write_home_patch("""- insert:
    - id: both
      name: ./reporter.mjs
      config:
        出处: home 那处
""")

    inst = launch(profile, wait_http=False)

    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)

    logs = inst.logs()
    verdict = [ln.strip() for ln in logs.splitlines() if "duplicate loader entry id" in ln]

    print("\n══ 两处写了同一个 id ═════════════════════════════════════")
    print(f"  进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    print(f"  日志里的判词：{verdict[0] if verdict else '（没找到，看完整日志）'}")
    print(f"  它说过话吗：{[e.get('data') for e in reports(read_events(events_path), who='both')] or '一句都没有'}")
    if not verdict:
        print(logs)

    assert not inst.alive(), "两处同一个 id 居然起来了 —— 那它们就被当成一个条目了"
    assert verdict, f"日志里应当有 duplicate loader entry id 的判词：\n{logs}"
    assert any("both" in ln for ln in verdict), f"判词该点名撞车的那个 id：{verdict}"
    assert not reports(read_events(events_path), who="both"), "进程都没起来，它不该说过话"
