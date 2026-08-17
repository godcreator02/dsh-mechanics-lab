"""boot-audit · boot 末尾的普查

档次 ③ ｜ 性质 🔬 发现型 ＋ ⚠️ 矫正型 ｜ 状态 ✅ 已验 ｜ 用例 3 条 ｜ 不需要 web

## 判定

- **boot 末尾有一次性的普查，非 ACTIVE 一律抛错，PENDING 无条件致命。**
  `dsh-app-boot` 的 `assertEntriesActivated` 在 `boot()` 返回前审计每一个未
  disabled 的条目，只要有一个不是 ACTIVE 就抛错：

  ```js
  if (state === FIBER_PENDING) {
    const missing = Object.keys(fiber.inject).filter(s => fiber.ctx.get(s) === undefined)
    failures.push(`${name}: pending (waiting for ${subject}: ${missing.join(", ")})`)
  }
  ```

  抛错之后整棵树被 `ctx.fiber.dispose()` 回滚，进程以退出码 1 退出。
  证据：`test_hard_dependency_never_satisfied`。

- **审计不区分「差点有」和「压根没有」。** 依赖一个提供者被禁用的服务，
  跟依赖一个从没被任何条目声明过的服务名，走到同一个结局——同样的判词
  句式、同样的退出码 1、同样的状态序列 `PENDING → UNLOADING → DISPOSED`。
  证据：`test_pending_dependent_dies_with_the_tree[provider-disabled]` /
  `[never-exists]`。

- **这次审计只做一次，只在 boot 期。** boot 之后靠热重放新加的条目卡在
  PENDING 不会杀进程——那是另一套路径，见 `pending-timing`（无用例，
  本项的这段判定就是它引用的那半边结论）。

- **⚠️ 矫正点，本组的核心产出。** 官方文档只描述了运行期的等待：
  `docs/official/zh/user/develop/framework/service.md:32` 原话是「如果服务
  还没准备好，你的插件会等着，不会执行」——这句话没错，但**只对运行期
  成立**。boot 期的等待有一个文档没写的硬上限：`boot()` 返回前的这次
  审计，等不到就无条件杀掉整个进程，不是「一直等」。

## 观测方法

- **致命判定不能靠 `except LabError`。** `start_instance(wait_http=False)`
  立即返回、不做存活检查，那个 `except` 永远不会触发，用例会安静通过却
  没在测它自称在测的东西。必须自己固定等一段时间再看 `inst.alive()`。
  这个坑在 L0、L9 都实际踩过一次，本组几乎每条用例都要判启动失败，
  绕不开它。
- **状态链 `PENDING → UNLOADING → DISPOSED` 极易读反。** 销毁它的不是
  「等超时放弃」，是 boot 失败后 `ctx.fiber.dispose()` 的整树回滚——它是
  失败的**证据**，不是失败之外另发生的一件事。同一份观测数据，因为缺了
  「进程还活着吗」这一个最粗的对照，能读出完全相反的结论。
- 判词走 stderr、混在 `inst.logs()` 里，抓取用子串匹配
  `"pending (waiting" in line or "did not activate" in line`。

## 没覆盖到的

- boot 期审计对「曾经 ACTIVE 过又被 dispose」这类中间态是否有特殊处理，
  没有实验覆盖——本项的两个变体都是「从未激活过」的条目。
"""

from __future__ import annotations

import json
import time

import pytest
from lab import LAB_ROOT

RECORDER = LAB_ROOT / "observatory" / "lab-recorder"
PLUGINS = ("lab-registry", "lab-alpha")


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _entry(entry_id: str, name: str, *, disabled: bool = False, inject=None, config: dict | None = None) -> str:
    lines = [f"    - id: {entry_id}", f"      name: {name}"]
    if disabled:
        lines.append("      disabled: true")
    if inject is not None:
        lines.append(f"      inject: {json.dumps(inject)}")
    if config:
        lines.append("      config:")
        lines += [f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items()]
    return "\n".join(lines)


def _patch(*entries: str) -> str:
    return "# 09 boot-audit 活层\n- insert:\n" + "\n\n".join(entries) + "\n"


def _watch(inst, seconds: float) -> dict:
    """看着实例跑一段时间，如实记录死没死、退出码、日志。不做任何断言。"""
    deadline = time.monotonic() + seconds
    died_at = None
    while time.monotonic() < deadline:
        if not inst.alive():
            died_at = round(seconds - (deadline - time.monotonic()), 2)
            break
        time.sleep(0.25)
    return {"alive": inst.alive(), "died_at": died_at, "exit_code": inst.proc.returncode, "logs": inst.logs(tail=60)}


# ── 用例 1 · 硬依赖一个从不存在的服务 ───────────────────────────────────────


def test_hard_dependency_never_satisfied(lab_home, fixtures_dir, launch):
    """一个条目硬依赖 `definitelyNotAService`（谁都不提供），boot 审计判它死刑。

    普查员在 apply 当下拍一张快照，证明这一刻服务表里只有 `loader`——
    审计发生之前，framework 自带的 timer/hmr 还没轮到；needy 那条永远
    没有 apply 过（见证文件不出现）。
    """
    census_out = lab_home.root / "census.json"
    witness = lab_home.root / "needy-witness.json"
    profile = lab_home.make_minimal_profile(
        "audit-hard-dep",
        patch=f"""# boot-audit 用例 1
- insert:
    - id: census
      name: l00-census
      config:
        out: {json.dumps(census_out.as_posix())}
        delayMs: 2000

    - id: needy
      name: l00-needy
      config:
        witness: {json.dumps(witness.as_posix())}
""",
    )
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.link_plugin("l00-needy", fixtures_dir / "l00-needy")

    inst = launch(profile, wait_http=False)
    got = _watch(inst, seconds=20.0)

    print(f"\n进程还活着？ {got['alive']}（退出码 {got['exit_code']}，死于 +{got['died_at']}s）")
    print(f"needy 的 apply 被调用过吗？ {witness.exists()}（预期 False——服务永远等不到）")

    logs = got["logs"]
    verdict = [ln for ln in logs.splitlines() if "did not activate" in ln or "pending (waiting" in ln]
    print(f"日志里的审计判词：{verdict or '（没找到）'}")
    if not verdict:
        print(logs)

    assert not witness.exists(), "硬依赖没满足，apply 不该被调用"
    assert not got["alive"], "boot 末尾的审计应当让启动失败——PENDING 无条件致命"
    assert got["exit_code"] == 1, f"预期退出码 1，实际 {got['exit_code']}"
    assert verdict, f"日志里该有审计判词：\n{logs}"


# ── 用例 2 · 两种「永远满足不了」的写法，boot 的结局一样吗 ─────────────────


@pytest.mark.parametrize(
    ("variant", "service_name"),
    [("提供者被禁用", "labRegistry"), ("服务名从不存在", "从来没有人提供过这个服务")],
    ids=["provider-disabled", "never-exists"],
)
def test_pending_dependent_dies_with_the_tree(lab_home, fixtures_dir, launch, variant, service_name):
    """依赖一个「提供者被禁用」的服务，跟依赖一个「压根没人声明过」的服务名，
    boot 的结局是不是一样。

    两个变体在同一个环境下跑，条目级 `inject` 直接点名要等的服务。装上
    观测台看 fiber 的完整一生：`PENDING → UNLOADING → DISPOSED`，销毁时刻
    落在 boot 审计之后，不是「等超时」。
    """
    tag = "dis" if service_name == "labRegistry" else "never"
    profile = lab_home.make_profile(f"audit-unsat-{tag}")
    for name in PLUGINS:
        profile.link_plugin(name, fixtures_dir / name)
    profile.link_plugin("lab-recorder", RECORDER)

    events = lab_home.root / f"events-{tag}.jsonl"
    ledger = lab_home.root / f"ledger-{tag}.json"

    entries = [
        _entry("lab-recorder", "lab-recorder", config={"out": events.as_posix(), "flushMs": 100}),
        _entry("lab-alpha", "lab-alpha", inject=[service_name]),
    ]
    if service_name == "labRegistry":
        entries.insert(1, _entry("lab-registry", "lab-registry", disabled=True, config={"ledger": ledger.as_posix()}))

    profile.write_patch(_patch(*entries))

    inst = launch(profile, wait_http=False)
    time.sleep(5)
    alive = inst.alive()
    logs = inst.logs(tail=40)
    exit_code = inst.proc.returncode
    inst.stop()
    time.sleep(1)

    print(f"\n  [{variant}] → {'启动成功' if alive else '启动失败'}（退出码 {exit_code}）")
    verdicts = dict.fromkeys(
        ln.strip() for ln in logs.splitlines() if "pending (waiting" in ln or "did not activate" in ln
    )
    for line in verdicts:
        print("    " + line)

    if events.exists():
        rows = [json.loads(ln) for ln in events.read_text(encoding="utf-8").splitlines() if ln.strip()]
        mine = [e for e in rows if e.get("id") == "lab-alpha"]
        for e in mine:
            if e.get("kind") == "status":
                print(f"    +{e['ms']:8.3f}ms  {e['from']:>9} → {e['to']}")

    assert not alive, "boot 末尾的审计应当让启动失败，跟等不到的原因（禁用/不存在）无关"
    assert exit_code == 1, f"预期退出码 1，实际 {exit_code}"
    assert verdicts, f"日志里没找到审计判词：\n{logs}"
