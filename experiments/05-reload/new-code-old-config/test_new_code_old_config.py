"""new-code-old-config · 代码路径与配置路径互不相通

档次 ① ｜ 性质 🔬 ｜ 状态 ✅ ｜ 1 条用例 ｜ 不需要 web

## 判定

- **同一时刻改代码又改配方，拿到的是新代码配旧配方。** 代码热重载走
  `registry.plugin(plugin, oldFiber._config, ...)`——明写着沿用旧 fiber 的
  config，所以新代码拿到的是上一程那份配方。
- **bundle 层的 config 是冷的，而且是「看见了没人管」不是「没人看见」。**
  `composeLive()` 里 `composed.bundlePatches` 是 boot 时 `loadProfile()` 读好
  的常量数组，只有 profile 活层和 home 层每次重读盘；那份 patch 文件落在
  watch 范围内时，事件流里确实有 `hmr-change` 点名它，但它不是任何 include
  的 filename、也不在 `loadCache` 里，掉进「只发个事件」的分支。
- **重启之后两笔改动才一起生效**，坐实了「冷」而不是「丢了」：新进程重新
  `loadProfile()`。

`test_code_reload_keeps_the_old_config`

## 观测方法

插件把「代码里那句版本」与「config 里那句版本」拆成两个字段一起上报
（`said_pairs`），一次读出配对，来路一眼分得开。`hmr-change` 事件里按
`cordis.patch.yml` 过滤，确认 watcher 确实看见了 bundle 层配方文件的变化；
`hmr-reload` 的条数用来确认「配方那次不产生重载」——只有代码那次触发了一次
重载。
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
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    of_kind,
    read_events,
    reports,
    rmtree_safe,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
PKG_NAME = "hmr-linked"

FIRST, SECOND = "第一版", "第二版"
CFG_FIRST, CFG_SECOND = "配置第一版", "配置第二版"

BASE = """- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'
      config:
        root: ['.']
        debounce: 100

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
"""


def copy_package(dest: Path) -> Path:
    """把教学插件那个包拷一份到指定落点，用例只改这份拷贝，仓库里的源保持原样。"""
    if dest.exists():
        rmtree_safe(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / PKG_NAME, dest)
    return dest


def build(lab_home: LabHome, name: str) -> tuple[LabProfile, Path, Path]:
    """搭一个 profile：源码挪进 profile 目录里面（`root: ['.']` 就够罩住它、
    包里的 patch 文件也在同一目录下），条目由包自己那份 patch 生。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    profile_dir = lab_home.root / "profiles" / name
    pkg_dir = copy_package(profile_dir / "src" / PKG_NAME)

    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    profile = lab_home.make_profile(name, bundles=[PKG_NAME], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    profile.link_plugin(PKG_NAME, pkg_dir)

    return profile, events, pkg_dir / "index.js"


def edit_code(index_js: Path) -> None:
    text = index_js.read_text(encoding="utf-8")
    assert FIRST in text, f"前提：{index_js} 里本来写着{FIRST}"
    index_js.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


def edit_bundle_config(pkg_dir: Path) -> Path:
    """把包里那份 patch 的 config 从「配置第一版」改成「配置第二版」——跟
    `edit_code` 是两个不同的动作：那个改代码，这个改配方。
    """
    patch = pkg_dir / "cordis.patch.yml"
    text = patch.read_text(encoding="utf-8")
    assert CFG_FIRST in text, f"前提：{patch} 里本来写着{CFG_FIRST}"
    patch.write_text(text.replace(CFG_FIRST, CFG_SECOND), encoding="utf-8")
    return patch


def said_pairs(events: list[dict]) -> list[tuple[str, str | None]]:
    """插件每次报出的（代码里那个版本, config 里那个版本），按时间顺序。"""
    out = []
    for e in reports(events, who="greeter"):
        data = e.get("data") or {}
        if data.get("版本"):
            out.append((data["版本"], data.get("配置版本")))
    return out


def wait_said(inst: Instance, path: Path, *, count: int, timeout: float = 40.0) -> list[tuple[str, str | None]]:
    deadline = time.monotonic() + timeout
    got: list[tuple[str, str | None]] = []
    while time.monotonic() < deadline:
        got = said_pairs(read_events(path))
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


def test_code_reload_keeps_the_old_config(lab_home: LabHome, launch):
    """同一时刻改代码 + 改包里那份 patch 的 config——拿到的是新代码配旧配方。

    一次改两处，一次读结果：代码里那句「第一版」→「第二版」，包里那份 patch
    的 `config.版本`「配置第一版」→「配置第二版」。三条判定挤在这一条用例里：

      * 代码路径不换 config，新代码拿到的是上一程那份配方
      * bundle 层的 config 是冷的：`composeLive()` 里 `composed.bundlePatches`
        是 boot 时读好的常量数组，只有 profile 活层和 home 层每次重读盘
      * watcher 看见了那个 patch 文件（它落在 watch 范围内），但没有任何
        后续——它不是任何 include 的 filename，也不在 `loadCache` 里

    最后重启一次坐实「冷」而不是「丢了」：新进程重新 `loadProfile()`，两个
    新值这才一起生效。
    """
    profile, events_path, index_js = build(lab_home, "cfgcold")
    pkg_dir = index_js.parent

    inst = launch(profile, wait_http=False)
    first = wait_said(inst, events_path, count=1)
    assert first == [(FIRST, CFG_FIRST)], f"起手该是代码第一版配配方第一版，实际 {first}：\n{inst.logs()}"
    time.sleep(1.0)

    # ── 同一时刻，两处各改一笔 ──────────────────────────────────────────────
    edit_code(index_js)
    edit_bundle_config(pkg_dir)

    wait_said(inst, events_path, count=2, timeout=25.0)
    Instance.settle(5.0)  # 再多坐一会儿：万一配方那笔走的是另一条更慢的路

    events = read_events(events_path)
    pairs = said_pairs(events)
    seen_patch = [e for e in of_kind(events, "hmr-change") if "cordis.patch.yml" in str(e.get("url"))]

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert pairs == [(FIRST, CFG_FIRST), (SECOND, CFG_FIRST)], f"该是「新代码 + 旧配方」，实际 {pairs}"
    assert seen_patch, "那份 patch 文件在 watch 范围内，watcher 该报出它的变化"
    assert len(of_kind(events, "hmr-reload")) == 1, "只该有一次重载（代码那次），配方那次不产生重载"

    # ── 重启：新进程重新 loadProfile()，配方那笔这才生效 ────────────────────
    inst.stop()
    events_path.replace(events_path.with_name(events_path.stem + "-run1.jsonl"))
    inst = launch(profile, wait_http=False)
    after = wait_said(inst, events_path, count=1)

    assert inst.alive(), f"重启后实例应当活着：\n{inst.logs()}"
    assert after == [(SECOND, CFG_SECOND)], f"重启后两笔改动该一起生效，实际 {after}"
