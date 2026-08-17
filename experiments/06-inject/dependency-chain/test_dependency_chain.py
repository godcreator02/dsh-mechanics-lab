"""dependency-chain · 依赖怎么在链上传递

档次 ② ｜ 性质 🔬 发现型 ｜ 状态 ✅ 已验 ｜ 2 条用例 ｜ 不需要 web

同样是 lab-registry ← lab-alpha ← lab-beta 这条链（`lab-alpha` 依赖
`labRegistry`，`lab-beta` 依赖 `labRegistry` 与 `labAlpha` 两个）。这一项关心的
不是顺序（那是 activation-order 的事），是**残缺链条的下场**。

## 判定

- **`inject` 是全有全无，不是「拿到几个算几个」。** 只禁用依赖链中段
  （`lab-alpha`），根服务 `labRegistry` 还在，`lab-beta` 依然缺一个
  `labAlpha`——照样不 apply。`test_missing_middle_breaks_only_second_level`
  已验证：账本里没有任何登记（连 alpha 自己都没登记过），`lab-beta` 的见证
  文件永不出现
- **等待中的条目不是「没被创建」，它确实停在 PENDING。** 挂上采集器直接看
  fiber 状态：`lab-alpha` 的第一份快照就是 `PENDING`，而且它禁用掉的提供者
  `labRegistry` 全程没有出现在服务列表里——`test_pending_dependent_seen_through_recorder`
  把「等不到」从推断变成了直接观测

## 观测方法

见证文件与账本落盘判「apply 到底跑没跑」；第二个用例额外挂 `lab-recorder`
（`observatory/lab-recorder`，本仓公共采集器，按路径 link 进 profile，不算本项
fixtures）——它监听 `internal/status` 事件自动记录每个条目的 fiber 状态迁移，
读它写的 `events.jsonl`，按条目 id 过滤出 `snapshot` / `service` 两类事件，是
本仓唯一能直接看到 fiber 内部状态的手段，比等结果去反推靠谱。它同时对外
`ctx.provide("labObserver", ...)`（`observatory/lab-recorder/index.js:153`），
给被观测的插件一个主动上报的入口；本项两条用例都没用到这个主动上报口，只用它
自动记录的 fiber 状态流，纯被动观测就够。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from lab import LAB_ROOT, read_events

pytestmark = pytest.mark.instance

RECORDER = LAB_ROOT / "observatory" / "lab-recorder"


def _entry(entry_id: str, name: str, *, disabled: bool = False, config: dict | None = None) -> str:
    lines = [f"    - id: {entry_id}", f"      name: {name}"]
    if disabled:
        lines.append("      disabled: true")
    if config:
        lines.append("      config:")
        lines += [f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items()]
    return "\n".join(lines)


def _patch(*entries: str) -> str:
    return "# dependency-chain 活层\n- insert:\n" + "\n\n".join(entries) + "\n"


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


def test_missing_middle_breaks_only_second_level(lab_home, fixtures_dir, launch):
    """只禁用中段 alpha：根服务还在，beta 缺的只是 labAlpha——依赖是全有全无。

    「不该发生的事」用固定长等待断言，不用轮询提前退出。
    """
    profile = lab_home.make_minimal_profile("missing-middle")
    _link_chain(profile, fixtures_dir)
    ledger = lab_home.root / "ledger.json"
    w_beta = lab_home.root / "w-beta.json"

    profile.write_patch(
        _patch(
            _entry("lab-registry", "lab-registry", config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha", disabled=True),
            _entry("lab-beta", "lab-beta", config={"witness": w_beta.as_posix()}),
        )
    )

    inst = launch(profile, wait_http=False)
    try:
        book = _wait_json(ledger)  # 根还在，账本（起码那份空账本）该出现
        time.sleep(10.0)
        assert not w_beta.exists(), "拿到了 labRegistry、缺 labAlpha——beta 不该 apply"
    finally:
        inst.stop()

    assert book["entries"] == [], "没有人往账本里登记过——alpha 被禁用，beta 没拿全依赖"


def test_pending_dependent_seen_through_recorder(lab_home, fixtures_dir, launch):
    """挂上采集器，直接看等待中的依赖方的 fiber 状态与服务列表。

    禁用根服务的提供者，lab-alpha 永远等不到 labRegistry。看两件事：
      * lab-alpha 走过 PENDING 快照（不是「没被创建过」）
      * labRegistry 从未出现在采集器记录的、真正「present」的服务列表里
    """
    profile = lab_home.make_minimal_profile("pending-observed")
    _link_chain(profile, fixtures_dir)
    profile.link_plugin("lab-recorder", RECORDER)

    events = lab_home.root / "events.jsonl"
    ledger = lab_home.root / "ledger.json"

    profile.write_patch(
        _patch(
            _entry("lab-recorder", "lab-recorder", config={"out": events.as_posix(), "flushMs": 100}),
            _entry("lab-registry", "lab-registry", disabled=True, config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha"),
        )
    )

    inst = launch(profile, wait_http=False)
    try:
        time.sleep(6.0)
    finally:
        inst.stop()
        time.sleep(1.0)

    rows = read_events(events)
    assert rows, "采集器没写出事件"
    mine = [e for e in rows if e.get("id") == "lab-alpha"]
    assert mine, "采集器该记到 lab-alpha 的事件"

    snapshots = [e for e in mine if e["kind"] == "snapshot"]
    assert snapshots and snapshots[0].get("to") == "PENDING", f"lab-alpha 该停在 PENDING：{snapshots}"

    provided = {e.get("serviceName") for e in rows if e["kind"] == "service" and e.get("present")}
    assert "labRegistry" not in provided, "提供者被禁用，labRegistry 不该出现在服务列表里"
