"""inject-field · 条目级 `inject` 与代码级声明的关系

档次 ② ｜ 性质 🔬 发现型 ｜ 状态 ✅ ｜ 1 条用例 ｜ 不需要 web

## 判定

- **条目上的 `inject` 是补充，不是覆盖。** `lab-alpha` 代码里声明了
  `export const inject = ["labRegistry"]`，条目上再写 `inject: []`（空）：
  组合树里条目的 `inject` 确实是 `[]`（`--dump-config` 可见），但插件**照常
  等到服务就位才 apply**——已实测（`test_entry_level_inject_is_additive_not_override`）。
  想靠条目级 `inject` 绕开代码里的依赖声明是行不通的。两种可能的结局本来都
  留了后路：覆盖的话 alpha 会在服务就位前 apply、`ctx.get` 拿到 `undefined`；
  合并／条目级被忽略的话，一切照常。实测是后者

## 观测方法

账本（`labRegistry` 提供的对象）每登记一笔就整份落盘，所以见证文件里的顺序
就是真实的 apply 先后。判定「alpha 有没有等到服务」看的是账本里到底出现没
出现这一笔，不是看进程死没死——如果条目级 `inject` 真的覆盖了代码声明，
alpha 会在服务就位前尝试 `ctx.get("labRegistry")` 拿到 `undefined`，插件对此
不抛错、如实记录（`gotRegistry: false`），这样才能把「inject 没满足 → 根本
没 apply」和「apply 了但服务是 undefined」这两种不同现象分开，不会因为探针
自己在观测点抛错而把两者混成同一个失败结果。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from lab import LabError, dump_config

pytestmark = pytest.mark.instance


def _entry(entry_id: str, name: str, *, inject=None, config: dict | None = None) -> str:
    lines = [f"    - id: {entry_id}", f"      name: {name}"]
    if inject is not None:
        lines.append(f"      inject: {json.dumps(inject)}")
    if config:
        lines.append("      config:")
        lines += [f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items()]
    return "\n".join(lines)


def _patch(*entries: str) -> str:
    return "# inject-field 活层\n- insert:\n" + "\n\n".join(entries) + "\n"


def _wait_json(path: Path, *, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.3)
    raise AssertionError(f"等了 {timeout}s，文件仍未出现：{path}")


def test_entry_level_inject_is_additive_not_override(lab_home, fixtures_dir, launch):
    """条目上的 `inject` 与插件代码里的 `export const inject`，是覆盖还是合并？

    做法：alpha 代码里声明了 `["labRegistry"]`，条目上写 `inject: []`（空）。
    两种结果都记录下来，实测说了算——本用例断言的是实测到的那一种（合并/
    条目级被忽略），如果框架行为变了，这条用例会先失败，而不是悄悄接受新行为。
    """
    profile = lab_home.make_profile("inject-additive")
    profile.link_plugin("lab-registry", fixtures_dir / "lab-registry")
    profile.link_plugin("lab-alpha", fixtures_dir / "lab-alpha")
    ledger = lab_home.root / "ledger.json"

    profile.write_patch(
        _patch(
            _entry("lab-registry", "lab-registry", config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha", inject=[]),
        )
    )

    dump = dump_config(lab_home, profile.name)
    assert dump.require("lab-alpha")["inject"] == [], "条目级 inject 应原样进组合树"

    try:
        inst = launch(profile, wait_http=False)
    except LabError as exc:
        raise AssertionError(f"预期条目级 inject: [] 不会削弱代码里的声明、应当照常启动，实际启动失败：{exc}") from exc

    try:
        book = _wait_json(ledger, timeout=20)
    finally:
        inst.stop()

    who = [e["who"] for e in book["entries"]]
    assert who == ["lab-alpha"], f"预期账本只有 lab-alpha 登记一笔，实际 {who}"
    print("\n  条目级 inject: [] → 照常加载，账本记着 alpha 等到服务就位才登记")
    print(f"  账本：{who}")
