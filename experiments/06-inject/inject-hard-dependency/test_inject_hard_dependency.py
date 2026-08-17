"""inject-hard-dependency · inject 是硬依赖，不是软等待

档次 ① ｜ 性质 📗 复述型 ｜ 状态 ✅ 已验 ｜ 3 条用例 ｜ 不需要 web

三个教学插件构成本项的测试面：`lab-registry` 提供 `labRegistry`；`lab-alpha` 在
代码里声明 `export const inject = ["labRegistry"]` 依赖它；`lab-open` 是对照
插件，代码里不声明 inject，运行时按需 `ctx.get()`。

## 判定

- **`inject` 声明的服务不到位，`apply` 根本不执行。** 不是「apply 了但拿到
  undefined」，是压根没 apply——官方文档已写明这条契约
  （`docs/official/zh/user/develop/framework/service.md:32`："框架保证：在 apply
  执行时，inject 声明的服务已经全部就绪。如果服务还没准备好，你的插件会等着，
  不会执行"），`test_provider_disabled_blocks_apply` 与
  `test_service_with_no_provider_blocks_apply_and_kills_boot` 两条路径
  （提供者被禁用 / 服务连提供者条目都没有）都验证了这条
- **等不到的下场很硬：那个条目永远停在 PENDING，boot 末尾的审计判它失败，
  整个实例起不来。** 这条外部事实由 `test_service_with_no_provider_blocks_apply_and_kills_boot`
  直接观测（`inst.alive()` 为假、退出码非 0、日志里有点名 `labRegistry` 的
  pending 判词）。boot 审计本身的机制（为什么 PENDING 无条件致命、这个判定
  跟具体是哪种「等不到」无关）归 `09-boot-vs-runtime/boot-audit`，这里不重复论证
- **不声明 `inject` 就不受这条契约约束：它不排队，直接跑。** `lab-open` 不写
  `inject`，代码里按需 `ctx.get()`，`apply` 不等任何人——`test_without_inject_
  declaration_runs_regardless` 验证的是「服务从头到尾都不存在」这个确定性场景：
  没有任何提供者条目，`ctx.get()` 只能拿到 `undefined`，这条必然成立。这把病因
  钉死：卡住依赖方的是**声明**（`inject` 数组），不是「服务碰巧不存在」这个事实
  本身。`lab-open` 是本项自己写的一份最小对照插件——不是因为找不到能复用的现成
  插件，是因为这条测试轴（声明不声明 inject）跟依赖链上挂采集器看 fiber 状态
  （`dependency-chain` 在用的那套）是两件不相关的事，一份只落见证文件的最小插件
  就够撑住这条轴，没必要接 `lab-recorder`
  ⚠️ **但「不声明 inject 能不能拿到已存在的服务」不是确定性问题，是竞态。**
  `site/never-ran.html` 的对照组实录过一次：`labObserver` 服务 2.2ms 才 ready，
  同一时刻不声明 inject 的插件 2.3ms 就已经 apply 完、拿到的是 `false`（原文：
  「看时间线，它在 2.3 ms 就跑完了，而观察器的服务 2.2 ms 才刚出现——不排队就
  没人保证服务在不在」）。两个时间点相差 0.1ms、谁先谁后没有保证——不声明
  inject 的插件不排队，它 apply 的时机只取决于自己在树里挂载的早晚，跟目标
  服务的 provider 有没有先就位完全无关。所以准确的表述是：**不声明 inject 时，
  拿不拿得到某个服务，取决于该服务的 provider 就位与这个插件自己 apply 的
  时序谁先谁后，而这个先后没有任何保证**——本项 `test_without_inject_
  declaration_runs_regardless` 只覆盖了「服务永远不存在」这一种确定性情形，
  没有覆盖「服务存在但时序竞争」这一种，见「## 没覆盖到的」

## 观测方法

信号是见证文件：插件在 `apply()` 里落盘，文件存在与否是硬事实，不靠日志
（日志会被吞、被缓冲）。「服务没到位」是「该发生的事没发生」，只能用足够长的
固定等待（10 秒起）断言，不能用轮询提前退出——轮询只能证明「此刻还没发生」。

## 已知的坑

`start_instance(wait_http=False)` 立即返回，不做任何存活检查；启动失败也不抛
`LabError`。判断「这次启动失败了」必须自己等一等再看 `inst.alive()` /
`inst.proc.returncode`，`try/except LabError` 永远不会触发——那样写出来的用例
表面在测「启动失败」，实际测的是空气，而且会安静地通过。
`test_service_with_no_provider_blocks_apply_and_kills_boot` 按正确写法实现，
细节见其自身 docstring。

## 没覆盖到的

- **⚠️ 待验 · 不声明 inject 时「能不能拿到已存在的服务」是竞态，本项没有用例覆盖这个场景。**
  证据是观察式的，来自 `site/never-ran.html` 的对照组：`labObserver` 服务 2.2ms
  才 ready，不声明 inject 的插件 2.3ms 已经 apply 完并取到 `false`——两个时间点
  只差 0.1ms，没有排队机制保证谁先谁后。本项 `test_without_inject_declaration_
  runs_regardless` 只验了「provider 从未存在」这一种确定性情形（`ctx.get()`
  必然拿到 `undefined`，不依赖时序），没有设计「provider 存在、跟不声明 inject
  的插件的 apply 时刻赛跑」这种用例——这需要能控制两者的相对时序（比如故意
  让 provider 慢启动）才能稳定复现，目前没有这样的用例，只是从旧证据搬运过来
  的观察，不进「## 判定」。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.instance


def _entry(entry_id: str, name: str, *, disabled: bool = False, config: dict | None = None) -> str:
    lines = [f"    - id: {entry_id}", f"      name: {name}"]
    if disabled:
        lines.append("      disabled: true")
    if config:
        lines.append("      config:")
        lines += [f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items()]
    return "\n".join(lines)


def _patch(*entries: str) -> str:
    return "# inject-hard-dependency 活层\n- insert:\n" + "\n\n".join(entries) + "\n"


def _wait_json(path: Path, *, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.3)
    raise AssertionError(f"等了 {timeout}s，见证文件仍未出现：{path}")


def test_provider_disabled_blocks_apply(lab_home, fixtures_dir, launch):
    """提供者条目还在，只是被禁用——依赖方等不到服务，apply 不执行。

    只断言「不该发生的事」，用固定长等待（10 秒）而不是轮询提前退出——
    轮询只能证明「此刻还没发生」，证明不了「不会发生」。
    """
    profile = lab_home.make_minimal_profile("provider-disabled")
    profile.link_plugin("lab-registry", fixtures_dir / "lab-registry")
    profile.link_plugin("lab-alpha", fixtures_dir / "lab-alpha")
    ledger = lab_home.root / "ledger.json"
    witness = lab_home.root / "w-alpha.json"

    profile.write_patch(
        _patch(
            _entry("lab-registry", "lab-registry", disabled=True, config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha", config={"witness": witness.as_posix()}),
        )
    )

    inst = launch(profile, wait_http=False)
    try:
        time.sleep(10.0)
        assert not witness.exists(), "见证文件不该出现——lab-alpha 不该 apply 过"
        assert not ledger.exists(), "提供者被禁用，账本也不该出现"
    finally:
        inst.stop()


def test_service_with_no_provider_blocks_apply_and_kills_boot(lab_home, fixtures_dir, launch):
    """服务连一个提供者条目都没有——依赖方永远等不到，整棵实例最终启动失败。

    判断启动失败必须自己 poll `inst.alive()`，不能靠 `except LabError`——
    见模块 docstring「已知的坑」。
    """
    profile = lab_home.make_minimal_profile("no-provider-at-all")
    profile.link_plugin("lab-alpha", fixtures_dir / "lab-alpha")
    witness = lab_home.root / "w-alpha-noprovider.json"

    profile.write_patch(_patch(_entry("lab-alpha", "lab-alpha", config={"witness": witness.as_posix()})))

    inst = launch(profile, wait_http=False)
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)
    logs = inst.logs(tail=60)
    inst.stop()

    assert not inst.alive(), f"实例居然活着 —— 那 PENDING 就不是致命的了：\n{logs}"
    assert inst.proc.returncode != 0, "启动失败该有个非 0 的退出码"
    assert not witness.exists(), "apply 不该跑过，见证文件不该出现"

    verdicts = [ln.strip() for ln in logs.splitlines() if "pending (waiting" in ln or "did not activate" in ln]
    assert verdicts, f"日志里该有 boot 审计的判词：\n{logs}"
    assert any("labRegistry" in ln for ln in verdicts), f"判词该点名 labRegistry：{verdicts}"


def test_without_inject_declaration_runs_regardless(lab_home, fixtures_dir, launch):
    """不声明 inject 的插件不等：服务压根不存在，它照样 apply，取到的是 undefined。

    这条把病因钉死：卡住依赖方的是**等**（inject 声明），不是「服务不存在」这个
    事实本身——同一个缺失的服务，不声明就不受它影响。
    """
    profile = lab_home.make_minimal_profile("no-inject-control")
    profile.link_plugin("lab-open", fixtures_dir / "lab-open")
    witness = lab_home.root / "w-open.json"

    profile.write_patch(_patch(_entry("lab-open", "lab-open", config={"witness": witness.as_posix()})))

    inst = launch(profile, wait_http=False)
    try:
        body = _wait_json(witness)
        assert inst.alive(), "不声明 inject 不该导致启动失败"
    finally:
        inst.stop()

    assert body["gotRegistry"] is False, "这个实例里没有任何人提供 labRegistry，ctx.get 该拿到 undefined"
