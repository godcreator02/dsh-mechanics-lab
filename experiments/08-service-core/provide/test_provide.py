"""provide · 第一次站到另一侧：自己提供一个服务

档次 ③ ｜ 性质 🔬 ｜ 状态 ✅ ｜ 2 条用例 ｜ 不需要 web

## 判定

- **两种写法都能提供，使用方那侧看不出区别。** 裸对象（`ctx.provide("名字", 对象)`）
  和服务基类（`class X extends Service`）各自占上名字、都出现在事件流的「服务出现」里，
  使用方 `inject` 两个都拿到，用法都是 `ctx.名字.方法()`。使用方从代码上分辨不出对面
  是哪种写法。已验：`test_both_styles_provide_and_are_used_the_same`
- **基类那条路多给的是「知道谁在调我」。** 两个服务对象里的方法一字不差，都是报出
  此刻手上那份 ctx 属于哪个条目；两边也都自己存了一份 ctx。裸对象报出的永远是它自己
  （提供方），服务基类报出的是调用方——框架把服务交到调用方手上时，会把方法里的那份
  ctx 换成调用方的，裸对象没有这个待遇。已验：`test_class_style_sees_the_caller`

  `docs/official/zh/glossary.md:9` 规定 Service Definition 必须是 Cordis `Service`
  而非 TypeScript `interface`，但没有讲这条要求换来了什么——这条判定是实测答案。

## 观测方法

装置：一个实例里三个条目——两个提供方各占一个名字（`labBare` / `labKlass`），一个
使用方同时 `inject` 两个，向它们问同一个问题。事件流里的「服务出现/撤销」与 fiber
状态跳变判「起没起来」；见证文件（只在 apply 跑完、拿到服务之后才写）判「跑没跑完」。
两者独立，`ok` 判据靠见证文件，别的信号（服务出现、状态）用来交叉核实，不单独作为
判据。

下一项 `one-owner` 从这里立起来的两种提供写法出发，问「两个插件想占同一个名字会
怎样」。本项判定二（服务里的 ctx 属于谁）是再下一项 `registry` 的地基。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lab import (  # noqa: E402
    LAB_ROOT,
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

PLUGINS = ("bare-provider.mjs", "class-provider.mjs", "consumer.mjs")

PATCH = """
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100

    - id: 裸提供方
      name: ./bare-provider.mjs
      config:
        见证: {w_bare}

    - id: 基类提供方
      name: ./class-provider.mjs
      config:
        见证: {w_class}

    - id: 使用方
      name: ./consumer.mjs
      config:
        见证: {w_user}
"""


def build(lab_home: LabHome, label: str) -> tuple[LabProfile, Path, dict[str, Path]]:
    """搭一个实例：两个提供方 + 一个使用方。"""
    events = lab_home.root / f"events-{label}.jsonl"
    witnesses = {name: lab_home.root / f"witness-{label}-{name}.json" for name in ("裸提供方", "基类提供方", "使用方")}
    patch = PATCH.format(
        out=json.dumps(events.as_posix()),
        w_bare=json.dumps(witnesses["裸提供方"].as_posix()),
        w_class=json.dumps(witnesses["基类提供方"].as_posix()),
        w_user=json.dumps(witnesses["使用方"].as_posix()),
    )
    profile = lab_home.make_minimal_profile(label, patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    for plugin in PLUGINS:
        shutil.copy2(FIXTURES / plugin, profile.dir / plugin)
    return profile, events, witnesses


# ── 判定 1 · 两种写法都能提供，使用方那侧用法一样 ───────────────────────────


def test_both_styles_provide_and_are_used_the_same(lab_home: LabHome, launch):
    """两个提供方各占一个名字，一个使用方同时 `inject` 两个。

    重点看使用方那侧：拿到手之后，两种写法的用法有没有区别。
    """
    profile, events_path, witnesses = build(lab_home, "both")

    inst = launch(profile, wait_http=False)
    ok = inst.wait_for(
        lambda: witnesses["使用方"].exists(), timeout=40.0, what="使用方的见证文件出现（说明它拿到服务并跑完了）"
    )
    time.sleep(2.0)  # 让采集器把事件刷完

    events = read_events(events_path)
    answer = json.loads(witnesses["使用方"].read_text(encoding="utf-8")) if ok else {}

    print("\n══ 两种写法，同一个使用方 ═══════════════════════════════")
    print(f"进程还活着？ {inst.alive()}")
    for name, witness in witnesses.items():
        print(f"    {name:<8} {'✅' if witness.exists() else '❌'}")
    print(f"\n使用方拿到的答案：\n{json.dumps(answer, ensure_ascii=False, indent=2)}")
    print(f"\n服务出现：{[(e['serviceName'], e.get('who')) for e in of_kind(events, 'service') if e.get('present')]}")
    print(f"使用方走过的状态：{states_of(events, '使用方')}")
    print("\n完整时间线：")
    print(timeline(events))

    assert ok, f"使用方该拿到两个服务并跑完：\n{inst.logs(tail=80)}"
    assert inst.alive(), f"实例该照常活着：\n{inst.logs(tail=80)}"
    assert answer["裸对象"]["写法"] == "裸对象", "使用方该看得见裸对象那份"
    assert answer["服务基类"]["写法"] == "服务基类", "使用方该看得见基类那份"
    assert "ACTIVE" in states_of(events, "使用方"), "使用方该跑到 ACTIVE"
    provided = {e["serviceName"] for e in of_kind(events, "service") if e.get("present")}
    assert {"labBare", "labKlass"} <= provided, f"两个服务都该出现过：{sorted(provided)}"


# ── 判定 2 · 基类那条路多给了什么：服务里的 ctx 属于调用方 ───────────────────


def test_class_style_sees_the_caller(lab_home: LabHome, launch):
    """同一个方法体，问同一个问题：「此刻我手上这份 ctx 属于谁？」

    两个服务对象里那个方法**一字不差**，两边也都自己存了一份 ctx。
    所以答案要是不同，差别就只可能来自框架交接服务的方式。

    这条判定的分量：**「知道谁在调我」是 registry 那种安排的地基**——
    往表里塞东西时要把表项的寿命挂到注册方身上，前提就是能认出注册方是谁。
    """
    profile, events_path, witnesses = build(lab_home, "who")

    inst = launch(profile, wait_http=False)
    ok = inst.wait_for(lambda: witnesses["使用方"].exists(), timeout=40.0, what="使用方的见证文件出现")
    assert ok, f"使用方该跑完：\n{inst.logs(tail=80)}"
    time.sleep(2.0)

    answer = json.loads(witnesses["使用方"].read_text(encoding="utf-8"))
    caller = answer["我是"]
    bare_sees = answer["裸对象"]["它看见谁"]
    klass_sees = answer["服务基类"]["它看见谁"]

    print("\n══ 服务里的那份 ctx，到底属于谁 ═════════════════════════")
    print(f"  调用它们的是：{caller}")
    print(f"  {'写法':<8}{'它报出的条目':<14}{'等于调用方吗'}")
    print(f"  {'裸对象':<8}{str(bare_sees):<14}{bare_sees == caller}")
    print(f"  {'服务基类':<8}{str(klass_sees):<14}{klass_sees == caller}")
    print("\n完整时间线：")
    print(timeline(read_events(events_path)))

    assert caller == "使用方", f"调用方该是使用方那个条目：{caller}"
    assert bare_sees == "裸提供方", f"裸对象手上那份 ctx 该一直是它自己的：{bare_sees}"
    assert klass_sees == caller, f"基类那份 ctx 该被换成调用方的：{klass_sees}"
    assert bare_sees != klass_sees, "两种写法在这个问题上该给出不同答案"
    assert reports(read_events(events_path), who="使用方"), "使用方该说过话"
    assert {"裸提供方", "基类提供方", "使用方"} <= entry_ids(read_events(events_path))
