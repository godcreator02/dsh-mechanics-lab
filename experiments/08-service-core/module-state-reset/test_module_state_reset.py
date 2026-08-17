"""module-state-reset · 重载是卸载 + 重装，不是「换掉一个函数、保住状态」

档次 ③ ｜ 性质 🔬 ｜ 状态 ✅ ｜ 1 条用例 ｜ 不需要 web

## 判定

- **热重载之后，模块顶层的状态归零。** 插件模块顶层有 `let loads = 0`，每次
  `apply` 把它加一并报出来。重载会把整个模块重新求值，那一行也重跑，于是计数器
  回到 0、apply 之后报 1——两次都报 **1**，不是 1 和 2。已验：
  `test_reload_wipes_module_level_state`（判定原样取自
  `experiments/chx_hmr_across_junction/test_chx_hmr_across_junction.py` 的
  `test_reload_wipes_module_level_state`，第 ⑬ 条）

  实际含义：**热重载是卸载 + 重装，不是「换掉一个函数、保住状态」。** 插件里的
  内存状态（计数器、缓存、连接池、订阅）在每次热重载时全部丢失。要保住得自己
  安排——挪进一个不被重载的 service，或者在 dispose 里存出去、apply 里恢复。

## 观测方法

判定挂在两个信号上：**代码里的字面量**（版本号 `第一版`→`第二版`，确认重载确实
发生过、新代码生效了）与**模块顶层计数器**（确认状态有没有被保住）。两者独立
上报，互不干扰——版本变了不代表状态被保住，这正是本项要拆穿的地方。

本项没有沿用来源用例的 junction / bundle 装法——那套装置在验的是「代码从哪落地、
hmr 够不够得着」（归 `05-reload` 的覆盖范围），跟「重载之后模块状态归不归零」是
两件独立的事。本项用最简单的落地形态：插件代码直接摆在 profile 目录里，条目用
相对路径引用，`hmr` 的 `root` 盯着 `['.']`——把变量收窄到「模块顶层状态在重载
前后变没变」这一件事本身。

## 没覆盖到的

**对照（未在本项装置里重复验）**：同一个模块被两个条目挂着时，两次 apply
共享**同一个**模块实例，这个数会数到 2（模块没换）。同一个计数器，两种现象
分得开——数到 2 说明模块没换，停在 1 说明模块是新的。这条对照原本与本判定
一起从 `chx_hmr_across_junction` 的第 ⑩ 条与第 ⑬ 条捆绑验证，本项只取第 ⑬ 条，
第 ⑩ 条（重载的单位是插件而不是条目）归 `05-reload/reload-unit`，那边有独立用例。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lab import LAB_ROOT, Instance, LabHome, LabProfile, read_events, reports  # noqa: E402

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

FIRST, SECOND = "第一版", "第二版"

PATCH = """
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100

    - id: counter
      name: ./counter.mjs
"""


def build(lab_home: LabHome, label: str) -> tuple[LabProfile, Path]:
    """搭一个实例：一个带模块顶层计数器的插件，代码放在 profile 目录里。

    走最简单的落地形态（代码直接摆 profile 目录，条目用相对路径引用）—— junction
    与 bundle 自注册那套装法不影响本项要验的判定，那是 `05-reload` 的覆盖范围。
    """
    events = lab_home.root / f"events-{label}.jsonl"
    profile = lab_home.make_minimal_profile(
        label, patch=PATCH.format(out=json.dumps(events.as_posix())), hmr_root=["."]
    )
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(FIXTURES / "counter.mjs", profile.dir / "counter.mjs")
    return profile, events


def said_versions(events: list[dict]) -> list[str]:
    return [e["data"]["版本"] for e in reports(events, who="counter") if (e.get("data") or {}).get("版本")]


def said_loads(events: list[dict]) -> list[int]:
    return [e["data"]["载入次数"] for e in reports(events, who="counter") if "载入次数" in (e.get("data") or {})]


def wait_said(inst: Instance, path: Path, *, count: int, timeout: float = 40.0) -> list[str]:
    """等条目报到第 `count` 版为止——验「应该发生的事」用轮询，比死等快也更稳。"""
    deadline = time.monotonic() + timeout
    got: list[str] = []
    while time.monotonic() < deadline:
        got = said_versions(read_events(path))
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


def edit_code(index_js: Path) -> None:
    """把插件代码里的「第一版」改成「第二版」——在编辑器里改一行就是这个动作。"""
    text = index_js.read_text(encoding="utf-8")
    assert FIRST in text, f"前提：{index_js} 里本来写着{FIRST}"
    index_js.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


def test_reload_wipes_module_level_state(lab_home: LabHome, launch):
    """热重载之后，模块顶层的状态**归零**。

    重载会把整个模块重新求值，`let loads = 0` 那一行也重跑，于是计数器回到 0、
    apply 之后报 1。所以两次都报 **1**，而不是 1 和 2。

    实际含义：热重载是**卸载 + 重装**，不是「换掉一个函数、保住状态」。插件里的
    内存状态（计数器、缓存、连接池、订阅）在每次热重载时全部丢失。要保住得自己
    安排——挪进一个不被重载的 service，或者在 dispose 里存出去、apply 里恢复。
    """
    profile, events_path = build(lab_home, "wipe")
    counter_js = profile.dir / "counter.mjs"

    inst = launch(profile, wait_http=False)
    first = wait_said(inst, events_path, count=1)
    assert first == [FIRST], f"实例起来后插件该报一次版本，实际 {first}：\n{inst.logs()}"
    time.sleep(1.0)

    edit_code(counter_js)
    got = wait_said(inst, events_path, count=2, timeout=25.0)

    events = read_events(events_path)
    loads = said_loads(events)

    print("\n══ 重载之后模块顶层的计数器 ═══════════════════════════")
    print(f"  插件报过的版本：　{got}")
    print(f"  模块顶层计数器：　{loads}")
    print("  （报 [1, 1] = 模块被重新求值、旧状态没了；报 [1, 2] = 同一个模块实例又跑了一次）")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"该热重载，实际 {got}"
    assert loads == [1, 1], f"重载应当把模块顶层状态清掉，实际 {loads}"
