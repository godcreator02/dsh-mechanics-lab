"""第 3 步 · 给它传配置

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/step3_pass_config/ -n 0 -s

第 2 步那个插件只会说一句固定的话。这一步在它的条目上写 `config`，
让它把收到的东西原样报出来 —— 于是「写进去的」和「收到的」摆在同一条
事件流里，一眼能对。
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
    read_events,
    reports,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
ECHO = Path(__file__).resolve().parent / "fixtures" / "echo.mjs"

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


def build(lab_home: LabHome, name: str, *, config_block: str) -> tuple[LabProfile, Path]:
    """搭一个实例，`config_block` 原样拼进你那条条目底下。

    传空字符串就是「这条条目上一个 config 都不写」。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    patch += f"""
- insert:
    - id: echo
      name: ./echo.mjs
{config_block}"""
    profile = lab_home.make_profile(name, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(ECHO, profile.dir / "echo.mjs")
    return profile, events


def wait_for_echo(inst: Instance, path: Path, *, timeout: float = 40.0) -> list[dict]:
    """等到 echo 那条把话说出来为止。

    等的是**它自己的上报**，不是事件总数 —— 那才是这一步要看的东西。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        said = reports(read_events(path), who="echo")
        if said:
            return said
        if not inst.alive():
            break
        time.sleep(0.3)
    return reports(read_events(path), who="echo")


def only_report(said: list[dict]) -> dict:
    assert said, "echo 没说话 —— 它的 apply 可能压根没跑"
    return said[0]["data"]


def test_what_you_write_is_what_it_gets(lab_home: LabHome, launch):
    """写什么收什么：键名、值、类型一个不差，中文键也一样。"""
    profile, events_path = build(
        lab_home,
        "plain",
        config_block="""      config:
        问候语: 你好
        重试次数: 3
        啰嗦: true
""",
    )

    inst = launch(profile, wait_http=False)
    said = wait_for_echo(inst, events_path)

    print("\n══ 写进去的 vs 收到的 ════════════════════════════════════")
    print(timeline(read_events(events_path), kinds=("report",)))

    got = only_report(said)
    assert got["类型"] == "object"
    assert got["内容"] == {"问候语": "你好", "重试次数": 3, "啰嗦": True}


def test_nested_shapes_survive(lab_home: LabHome, launch):
    """嵌套对象、数组、null、小数原样送达 —— 写 config 不用迁就任何形状。"""
    profile, events_path = build(
        lab_home,
        "nested",
        config_block="""      config:
        服务器:
          主机: 127.0.0.1
          端口: 3090
        名单: [甲, 乙]
        空值: null
        小数: 3.14
""",
    )

    inst = launch(profile, wait_http=False)
    said = wait_for_echo(inst, events_path)

    got = only_report(said)
    print("\n══ 嵌套结构 ═════════════════════════════════════════════")
    print(f"  {json.dumps(got['内容'], ensure_ascii=False)}")

    assert got["内容"] == {
        "服务器": {"主机": "127.0.0.1", "端口": 3090},
        "名单": ["甲", "乙"],
        "空值": None,
        "小数": 3.14,
    }


@pytest.mark.parametrize(
    "kind, block",
    [
        ("一个 config 都不写", ""),
        (
            "键名拼错了",
            """      cofnig:
        问候语: 你好
""",
        ),
    ],
)
def test_missing_config_is_undefined(lab_home: LabHome, launch, kind: str, block: str):
    """没写 config、和把键名拼错 —— **两种情况的结果完全一样**。

    插件照常跑起来，第二个参数是 `undefined`，全程没有任何报错或警告。
    这是这一步最该记住的一条：拼错了没人会告诉你。
    """
    tag = "empty" if not block else "typo"
    profile, events_path = build(lab_home, tag, config_block=block)

    inst = launch(profile, wait_http=False)
    said = wait_for_echo(inst, events_path)

    got = only_report(said)
    print(f"\n══ {kind} ══════════════════════════════════════")
    print(f"  插件收到的类型：{got['类型']}    内容：{got['内容']}")

    assert inst.alive(), f"实例应当照常活着 —— 没有 config 不是错误：\n{inst.logs()}"
    assert got["类型"] == "undefined", f"预期 undefined，实际 {got}"
