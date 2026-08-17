"""self-registration · 包自注册要两样齐备

档次 ① ｜ 性质 🔬 发现型 ｜ 状态 ✅ 已实测 ｜ 2 条用例 ｜ 不需要 web

## 判定

- **包自注册需要两个条件同时成立：包里声明 `dsh.bundle.patch`，且包名进了
  profile 的 `dsh.profile.bundles` 名单。** 两样齐备时，profile 自己那份活层
  patch 文件里一个字都不用写，包自己那份 `cordis.patch.yml` 里 insert 的条目
  就会出现在树上、`apply` 会跑、`config` 会送达。证据：
  `test_a_package_mounts_itself`
- **缺一样，什么都不会发生。** 同一个包，同样建好目录 junction，只要没有被列进
  `dsh.profile.bundles`、活层也没手写 `insert`，条目就不存在——包目录里那份
  `cordis.patch.yml` 没人会去读它。证据：
  `test_the_package_alone_registers_nothing`（负对照）

## 观测方法

判据落在插件自己上报的内容上（`ctx.labObserver`）：条目在不在树上、走过哪些
状态、说过什么话。两条用例用两个不同的教学插件——`ch2-greeter`（正例：进了
bundles 名单）与 `ch2-courier`（负例：只 link 不装）——都只声明 `dsh.bundle`、
不声明别的，避免混进无关变量。
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from lab import (
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    entry_ids,
    read_events,
    reports,
    rmtree_safe,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

GREETER_PKG = "ch2-greeter"
COURIER_PKG = "ch2-courier"
COURIER = FIXTURES / "courier"

#: 三条基础设施条目，原样带过来。
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


def new_profile(lab_home: LabHome, label: str, *, bundles: list[str], live_extra: str = "") -> tuple[LabProfile, Path]:
    events = lab_home.root / f"events-{label}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix())) + live_extra
    profile = lab_home.make_profile(label, bundles=bundles, patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    return profile, events


def copy_greeter(lab_home: LabHome) -> Path:
    """把 ch2-greeter 拷一份到假 home 里——仓库里 `fixtures/ch2-greeter/` 那份是
    源，从头到尾保持原样。"""
    dest = lab_home.root / "pkg" / GREETER_PKG
    if dest.exists():
        rmtree_safe(dest)
    shutil.copytree(FIXTURES / GREETER_PKG, dest)
    return dest


def said_versions(events: list[dict], who: str) -> list[str]:
    return [e["data"]["版本"] for e in reports(events, who=who) if e.get("data")]


def wait_said(inst: Instance, path: Path, who: str, *, count: int = 1, timeout: float = 40.0) -> list[str]:
    """等某个条目报到第 `count` 次为止——验「该发生的事」用轮询。"""
    deadline = time.monotonic() + timeout
    got: list[str] = []
    while time.monotonic() < deadline:
        got = said_versions(read_events(path), who)
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


# ── 用例 1 · 包自注册（两个条件同时成立）────────────────────────────────────


def test_a_package_mounts_itself(lab_home: LabHome, launch):
    """profile 那份 patch 文件里没有一个字提到这个插件——只有 timer、hmr、观察器
    那三条。唯一做的事是把包名写进 `dsh.profile.bundles` 名单。然后条目
    `greeter` 就在树上了、`apply` 跑了、`config` 也收到了。

    那条 insert 是包自己写的，写在它自己那份 `cordis.patch.yml` 里。
    """
    pkg = copy_greeter(lab_home)
    profile, events_path = new_profile(lab_home, "selfmount", bundles=[GREETER_PKG])
    profile.link_plugin(GREETER_PKG, pkg)

    inst = launch(profile, wait_http=False)
    got = wait_said(inst, events_path, "greeter")

    events = read_events(events_path)
    print("\n══ 包把自己挂上去了 ══════════════════════════════════════")
    print("  profile 那份 patch 文件（活层）写了什么：只有 timer / hmr / 观察器")
    print(f"  package.json 的 bundle 名单：{[GREETER_PKG]}")
    print("  包自己那份 cordis.patch.yml：- insert: [{ id: greeter, name: ch2-greeter, config: {版本: 第一版} }]")
    print(f"  它说过的话：{got}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "greeter" in entry_ids(events), "包自己那份 patch 写的条目应当出现在树上"
    assert got == ["第一版"], f"它该报出包里写的那一版，实际 {got}"


# ── 用例 2 · 负对照：包摆在那儿，不装也不写，什么都不会发生 ─────────────────


def test_the_package_alone_registers_nothing(lab_home: LabHome, launch):
    """同一个包、同样建好目录链接，只是没跑安装命令、也没手写 `insert`——条目
    就不存在。自注册靠的是「装」这个动作，不是「包目录里躺着一份 patch 文件」。
    """
    profile, events_path = new_profile(lab_home, "notinstalled", bundles=[])
    profile.link_plugin(COURIER_PKG, COURIER)
    assert (COURIER / "cordis.patch.yml").exists(), "前提：包里确实带着那份 patch 文件"

    inst = launch(profile, wait_http=False)

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)
        if reports(read_events(events_path), who="courier"):
            break

    # 验「不该发生」：固定等一段，不能轮询提前退出
    Instance.settle(10.0)
    events = read_events(events_path)

    print("\n══ 包在，但既没装、也没手写那一条 ════════════════════════")
    print(f"  实例还活着？    {inst.alive()}")
    print(f"  树上的条目：    {sorted(entry_ids(events))}")
    print(f"  它说的话：      {[e.get('note') for e in reports(events, who='courier')] or '（一句都没有）'}")
    manifest = json.loads((profile.dir / "package.json").read_text(encoding="utf-8"))
    print(f"  那份名单：      dsh.profile.bundles = {manifest['dsh']['profile']['bundles']}")

    assert inst.alive(), f"实例应当照常活着——少挂一个插件不是错误\n{inst.logs()}"
    assert "courier" not in entry_ids(events), f"它不该出现在树上：{sorted(entry_ids(events))}"
    assert not reports(events, who="courier"), "它不该说话——包里那份 patch 文件没人读"
