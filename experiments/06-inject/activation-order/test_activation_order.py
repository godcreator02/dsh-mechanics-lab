"""activation-order · 书写顺序不决定加载顺序

档次 ① ｜ 性质 🔬 发现型 ｜ 状态 ✅ 已验 ｜ 2 条用例 ｜ 不需要 web

三个教学插件构成一条依赖链：

    lab-registry  ←  lab-alpha  ←  lab-beta
    提供 labRegistry   登记 + 提供       登记（要两个服务）
    （不依赖任何人）    labAlpha

`lab-registry` 提供的账本每登记一笔就整份落盘，落盘顺序就是真实的 apply
先后——拿它当时钟用，不用另外拼事件流时间戳。

## 判定

- **加载顺序由服务可用性驱动，不由 patch 文件里的行序决定。** 依赖链正着写
  （registry → alpha → beta）与倒着写（beta → alpha → registry），实际 apply
  顺序完全一样——`test_dependency_chain_applies_in_service_order` /
  `test_write_order_does_not_decide_load_order` 已验证，账本文件记下的落盘
  顺序就是真实 apply 先后；正着写时还额外验证了 beta 真的拿到了 alpha 提供的
  labAlpha
- **依据在 `EntryGroup.update()`：所有条目走 `Promise.allSettled(config.map(...))`
  并发创建**，谁先 apply 由服务就位顺序决定，不是遍历顺序。`dsh-base` 的 patch
  文件里有原话 *"Row order carries no load semantics (activation is
  service-availability driven)"*，这里是它的直接实测印证
- 这条**官方文档没有写明**（`docs/official/` 的 service.md 只说明依赖满足才
  执行，没有提"书写顺序无效"这件事），属于实测发现，不是文档复述

## 观测方法

信号是账本文件：`lab-registry` 提供的账本每登记一笔就整份落盘，落盘顺序即
真实 apply 先后，比拼事件流时间戳更直接——账本内容本身就是时钟。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.instance


def _entry(entry_id: str, name: str, *, config: dict | None = None) -> str:
    lines = [f"    - id: {entry_id}", f"      name: {name}"]
    if config:
        lines.append("      config:")
        lines += [f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items()]
    return "\n".join(lines)


def _patch(*entries: str) -> str:
    return "# activation-order 活层\n- insert:\n" + "\n\n".join(entries) + "\n"


def _wait_json(path: Path, *, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.3)
    raise AssertionError(f"等了 {timeout}s，见证文件仍未出现：{path}")


def _link_chain(profile, fixtures_dir: Path) -> None:
    for name in ("lab-registry", "lab-alpha", "lab-beta"):
        profile.link_plugin(name, fixtures_dir / name)


def test_dependency_chain_applies_in_service_order(lab_home, fixtures_dir, launch):
    """正着写依赖链，账本记下的真实 apply 顺序满足依赖：alpha 先于 beta。"""
    profile = lab_home.make_minimal_profile("forward-order")
    _link_chain(profile, fixtures_dir)
    ledger = lab_home.root / "ledger.json"
    w_beta = lab_home.root / "w-beta.json"

    profile.write_patch(
        _patch(
            _entry("lab-registry", "lab-registry", config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha"),
            _entry("lab-beta", "lab-beta", config={"witness": w_beta.as_posix()}),
        )
    )

    inst = launch(profile, wait_http=False)
    try:
        beta = _wait_json(w_beta)
        book = _wait_json(ledger)
    finally:
        inst.stop()

    who = [e["who"] for e in book["entries"]]
    assert who == ["lab-alpha", "lab-beta"], f"账本顺序不对：{who}"
    assert beta["gotRegistry"] is True and beta["gotAlpha"] is True, "beta 该拿到两个依赖"


def test_write_order_does_not_decide_load_order(lab_home, fixtures_dir, launch):
    """依赖链倒着写（beta → alpha → registry），实际 apply 顺序不变。"""
    profile = lab_home.make_minimal_profile("reverse-order")
    _link_chain(profile, fixtures_dir)
    ledger = lab_home.root / "ledger.json"
    w_beta = lab_home.root / "w-beta.json"

    profile.write_patch(
        _patch(
            _entry("lab-beta", "lab-beta", config={"witness": w_beta.as_posix()}),
            _entry("lab-alpha", "lab-alpha"),
            _entry("lab-registry", "lab-registry", config={"ledger": ledger.as_posix()}),
        )
    )

    inst = launch(profile, wait_http=False)
    try:
        _wait_json(w_beta)
        book = _wait_json(ledger)
    finally:
        inst.stop()

    who = [e["who"] for e in book["entries"]]
    assert who == ["lab-alpha", "lab-beta"], f"倒着写之后顺序变了：{who}"
