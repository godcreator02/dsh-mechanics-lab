"""L9 · 服务与 inject

见同目录 README.md。一句话：谁提供服务、谁依赖它、依赖没到位时会怎样。

三个教学插件构成一条依赖链：

    lab-registry  ←  lab-alpha  ←  lab-beta
     提供 labRegistry   登记 + 提供      登记（要两个服务）
     （不依赖任何人）    labAlpha
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lab import LAB_ROOT, LabError, dump_config

pytestmark = pytest.mark.instance

PLUGINS = ("lab-registry", "lab-alpha", "lab-beta")
RECORDER = LAB_ROOT / "observatory" / "lab-recorder"


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _entry(entry_id: str, name: str, *, disabled: bool = False, inject=None, config: dict | None = None) -> str:
    """拼一个活层条目。inject 传 list 时写成条目级 inject 字段。"""
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
    return "# L9 实验活层\n- insert:\n" + "\n\n".join(entries) + "\n"


def _link_all(profile, fixtures_dir: Path) -> None:
    for name in PLUGINS:
        profile.link_plugin(name, fixtures_dir / name)


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


def _boot_should_fail(launch, profile) -> str:
    """预期启动失败，返回错误全文。成功启动反而是断言失败。"""
    try:
        inst = launch(profile, wait_http=False)
    except LabError as exc:
        return str(exc)
    inst.stop()
    raise AssertionError("预期启动失败，实例却起来了")


# ── 用例 1 · 依赖满足：三个都加载，账本顺序满足依赖 ─────────────────────────


def test_dependency_chain_loads_in_service_order(lab_home, fixtures_dir, launch):
    """依赖都满足时三个插件都 apply，且**账本顺序必然满足依赖链**。

    账本每登记一笔就落盘，所以它记下的是真实的 apply 先后：
    registry 先提供服务，alpha 才可能登记；alpha 提供 labAlpha 之后，beta 才可能登记。
    """
    profile = lab_home.make_profile("l09-chain")
    _link_all(profile, fixtures_dir)
    ledger = lab_home.root / "ledger.json"
    w_alpha = lab_home.root / "w-alpha.json"
    w_beta = lab_home.root / "w-beta.json"

    profile.write_patch(
        _patch(
            _entry("lab-registry", "lab-registry", config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha", config={"witness": w_alpha.as_posix(), "note": "第一层消费者"}),
            _entry("lab-beta", "lab-beta", config={"witness": w_beta.as_posix()}),
        )
    )

    inst = launch(profile, wait_http=False)
    try:
        beta = _wait_json(w_beta)  # beta 最后 apply，它到了说明全链通了
        book = _wait_json(ledger)
    finally:
        inst.stop()

    who = [e["who"] for e in book["entries"]]
    assert who == ["lab-alpha", "lab-beta"], f"账本顺序不对：{who}"

    # beta 拿到了 alpha 提供的服务 —— 二级依赖真的通了
    assert beta["alphaMarker"] == "lab-alpha-v1"
    assert "alpha 在这儿" in json.dumps(book, ensure_ascii=False)

    # alpha 登记前账本还是空的，beta 登记前已经有 alpha —— 先后关系被钉死
    alpha = _wait_json(w_alpha)
    assert alpha["gotRegistry"] is True
    assert beta["gotRegistry"] is True and beta["gotAlpha"] is True
    assert alpha["ledgerBefore"] == []
    assert [e["who"] for e in beta["ledgerBefore"]] == ["lab-alpha"]

    gap = book["entries"][1]["ms"] - book["entries"][0]["ms"]
    print(f"\n  账本顺序：{who}")
    print(f"  alpha 登记时账本为空；beta 登记时已有 alpha，间隔 {gap:.3f}ms")


# ── 用例 2 · 根提供者缺席 → 整个实例起不来 ──────────────────────────────────


def test_missing_provider(lab_home, fixtures_dir, launch):
    """把提供方禁用，依赖方会怎样？

    两种可能，见证文件能把它们分开：

      * **硬依赖** → 依赖方根本不 apply，见证文件不出现
      * **软依赖** → 依赖方照常 apply，只是 `ctx.get` 拿到 undefined
        （见证文件出现且 `gotRegistry: false`）

    还有第三个维度：实例本身起不起得来。之前用一个**根本不存在的服务名**做实验时，
    boot 会 fail-loud 报 `did not activate`；这里换成「服务名存在但提供者被禁用」，
    结果未必一样。
    """
    profile = lab_home.make_profile("l09-noroot")
    _link_all(profile, fixtures_dir)
    ledger = lab_home.root / "ledger-noroot.json"
    w_alpha = lab_home.root / "w-alpha-noroot.json"

    profile.write_patch(
        _patch(
            _entry("lab-registry", "lab-registry", disabled=True, config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha", config={"witness": w_alpha.as_posix()}),
            _entry("lab-beta", "lab-beta"),
        )
    )

    try:
        inst = launch(profile, wait_http=False)
    except LabError as exc:
        err = str(exc)
        pending = dict.fromkeys(ln.strip() for ln in err.splitlines() if "pending (waiting" in ln)
        print("\n  实例**启动失败**，报错点名：")
        for line in pending:
            print("    " + line)
        assert not w_alpha.exists(), "启动都失败了，依赖方不该 apply 过"
        return

    # 实例起来了 —— 那依赖方到底 apply 没有？
    try:
        time.sleep(12)  # 「验证什么都不该发生」用固定长等待
        assert not ledger.exists(), "提供方被禁用，账本不该存在"
        if w_alpha.exists():
            got = json.loads(w_alpha.read_text(encoding="utf-8"))
            print(f"\n  实例照常启动；lab-alpha **apply 了**，gotRegistry={got['gotRegistry']}")
            print("    → inject 在这里表现为**软依赖**：没拦住 apply")
            assert got["gotRegistry"] is False
        else:
            print("\n  实例照常启动；lab-alpha **没有 apply**（见证文件不存在）")
            print("    → inject 拦住了它，但没有 pending 条目导致 boot 失败")
    finally:
        inst.stop()


# ── 用例 3 · 中段缺席 → 只有二级依赖倒下 ────────────────────────────────────


def test_missing_middle_breaks_only_second_level(lab_home, fixtures_dir, launch):
    """只禁用中段 alpha：根还在，所以 beta 缺的只是 `labAlpha` 这一个服务。

    关心两件事：
      1. beta 会不会 apply（跟上一个用例同样的软／硬依赖问题）
      2. 根服务还在时，beta 能不能拿到 `labRegistry`——即**部分依赖满足**时的行为
    """
    profile = lab_home.make_profile("l09-nomid")
    _link_all(profile, fixtures_dir)
    ledger = lab_home.root / "ledger-nomid.json"
    w_beta = lab_home.root / "w-beta-nomid.json"

    profile.write_patch(
        _patch(
            _entry("lab-registry", "lab-registry", config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha", disabled=True),
            _entry("lab-beta", "lab-beta", config={"witness": w_beta.as_posix()}),
        )
    )

    try:
        inst = launch(profile, wait_http=False)
    except LabError as exc:
        pending = dict.fromkeys(ln.strip() for ln in str(exc).splitlines() if "pending (waiting" in ln)
        print("\n  实例**启动失败**，报错点名：")
        for line in pending:
            print("    " + line)
        assert not any("lab-alpha:" in ln for ln in pending), "被禁用的条目不该算作 pending"
        return

    try:
        time.sleep(12)
        book = _wait_json(ledger, timeout=5)  # 根还在，账本文件应该被创建
        if w_beta.exists():
            got = json.loads(w_beta.read_text(encoding="utf-8"))
            print(f"\n  实例照常启动；lab-beta apply 了：gotRegistry={got['gotRegistry']}  gotAlpha={got['gotAlpha']}")
            print(f"    账本：{[e['who'] for e in book['entries']]}")
        else:
            print("\n  实例照常启动；lab-beta **没有 apply**")
            print(f"    账本：{[e['who'] for e in book['entries']]}")
    finally:
        inst.stop()


# ── 用例 4 · 两种 inject 写法的关系 ─────────────────────────────────────────


def test_entry_level_inject_vs_code_level(lab_home, fixtures_dir, launch):
    """条目上的 `inject` 与插件代码里的 `export const inject`，是覆盖还是合并？

    做法：alpha 代码里声明了 `["labRegistry"]`，条目上写 `inject: []`（空）。

      * 覆盖 → alpha 不再等 labRegistry，可能在服务就位前 apply → `ctx.get` 拿到
        undefined → 插件自己抛错 → FAILED → boot 失败
      * 合并／条目级被忽略 → 一切照常

    两种结果都记录下来，实测说了算。
    """
    profile = lab_home.make_profile("l09-inject")
    _link_all(profile, fixtures_dir)
    ledger = lab_home.root / "ledger-inject.json"

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
        print("\n  条目级 inject: [] → 启动失败，说明它**覆盖**了代码里的声明：")
        print("    " + "\n    ".join(str(exc).splitlines()[:6]))
        return
    try:
        book = _wait_json(ledger, timeout=20)
        who = [e["who"] for e in book["entries"]]
        assert who == ["lab-alpha"]
        print("\n  条目级 inject: [] → 照常加载，说明它**没有削弱**代码里的声明")
        print(f"    账本：{who}")
    finally:
        inst.stop()


# ── 用例 5 · 书写顺序倒过来，照常加载 ───────────────────────────────────────


def test_write_order_does_not_decide_load_order(lab_home, fixtures_dir, launch):
    """把依赖链**倒着写**（beta → alpha → registry），加载结果完全一样。

    `dsh-base` 的 patch 文件里有原话：*"Row order carries no load semantics
    (activation is service-availability driven)"*，而 `EntryGroup.update()`
    的实现是 `Promise.allSettled(config.map(...))` —— 所有条目**并发创建**。

    L4 会把这条深入展开，这里先钉一个最直接的证据。
    """
    profile = lab_home.make_profile("l09-reverse")
    _link_all(profile, fixtures_dir)
    ledger = lab_home.root / "ledger-reverse.json"
    w_beta = lab_home.root / "w-beta-reverse.json"

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
    print(f"\n  条目倒着写（beta→alpha→registry），实际 apply 顺序仍是：{who}")


# ── 用例 6 · 装上观测台，看等待中的依赖方到底处于什么状态 ───────────────────


def test_pending_dependent_seen_through_recorder(lab_home, fixtures_dir, launch):
    """依赖方没 apply 的时候，它的 fiber 到底存不存在、是什么状态？

    这个用例存在的理由是一处**实验之间的矛盾**：

      * 早先用一个**从不存在的服务名**（`inject: ["压根不存在的服务"]`）时，
        boot 直接 fail-loud：`dsh: 1 entry did not activate ... pending`
      * 本课把 `labRegistry` 的提供者禁用掉——服务同样永远不会出现——
        实例却**照常启动**，依赖方只是安静地不 apply

    两者本质相同、结果不同，说明我们对「boot 期 PENDING 致命」的理解有缺口。
    挂上采集器直接看 fiber 状态，比继续猜快得多。
    """
    profile = lab_home.make_profile("l09-observed")
    _link_all(profile, fixtures_dir)
    profile.link_plugin("lab-recorder", RECORDER)

    events = lab_home.root / "events.jsonl"
    ledger = lab_home.root / "ledger-observed.json"

    profile.write_patch(
        _patch(
            _entry("lab-recorder", "lab-recorder", config={"out": events.as_posix(), "flushMs": 100}),
            _entry("lab-registry", "lab-registry", disabled=True, config={"ledger": ledger.as_posix()}),
            _entry("lab-alpha", "lab-alpha"),
        )
    )

    inst = launch(profile, wait_http=False)
    try:
        time.sleep(6)
    finally:
        inst.stop()
        time.sleep(1)

    assert events.exists(), "采集器没写出事件"
    rows = [json.loads(ln) for ln in events.read_text(encoding="utf-8").splitlines() if ln.strip()]
    mine = [e for e in rows if e.get("id") == "lab-alpha"]

    print("\n  lab-alpha 的全部事件：")
    for e in mine:
        if e["kind"] == "status":
            print(f"    +{e['ms']:8.3f}ms  {e['from']:>9} → {e['to']}")
        elif e["kind"] == "snapshot":
            print(
                f"    +{e['ms']:8.3f}ms  snapshot  fiberState={e.get('to')}  "
                f"hasFiber={e.get('hasFiber')}  disabled={e.get('disabled')}"
            )
        else:
            print(f"    +{e['ms']:8.3f}ms  {e['kind']}  uid={e.get('uid')}")
    if not mine:
        print("    （一个事件都没有——连 fiber 都没被创建过）")

    # 服务事件里应该没有 labRegistry（提供者被禁用了）
    provided = {e.get("serviceName") for e in rows if e["kind"] == "service" and e.get("present")}
    assert "labRegistry" not in provided
    print(f"\n  labRegistry 从未出现在服务列表里（共 {len(provided)} 个服务）")


# ── 用例 7 · 隔离变量：服务名从不存在时，只叠 dsh-base 会失败吗 ─────────────


@pytest.mark.parametrize(
    ("variant", "service_name"),
    [("提供者被禁用", "labRegistry"), ("服务名从不存在", "从来没有人提供过这个服务")],
    ids=["provider-disabled", "never-exists"],
)
def test_boot_outcome_for_unsatisfiable_inject(lab_home, fixtures_dir, launch, variant, service_name):
    """两种「依赖永远满足不了」的写法，boot 的结局一样吗？

    这个用例是为了解一处矛盾：早先在一个**叠了 dsh-web-app** 的 profile 上，
    `inject` 一个从不存在的服务名会让 boot 直接 fail-loud；而本课**只叠 dsh-base**
    时，依赖方却只是被静静 DISPOSED 掉，实例照常启动。

    两次差了两个变量：**服务名是否有（被禁用的）提供者**，以及 **bundle 组合**。
    这里把前一个变量单独拎出来测——两个变体都在只叠 dsh-base 的同一环境下跑。

    ⚠️ **本用例第一版有个实验设计缺陷，结论整个是反的**（L0 复核时发现）：

    它靠 `except LabError` 判断启动失败，但 `start_instance(wait_http=False)`
    **立即返回、不做任何存活检查**，那个 except 永远不会触发。于是两个变体都
    打印「启动成功」，进而得出「只叠 dsh-base 时 PENDING 不致命」的错误结论，
    再进而把差异归因到 bundle 组合。

    真相（L0 从源码 + 实测两头确认）：`assertEntriesActivated` 在 boot 末尾审计，
    PENDING **无条件致命**。而本用例事件流里那条 `PENDING → UNLOADING → DISPOSED`
    恰恰是审计失败后 `boot()` 的 catch 里 `ctx.fiber.dispose()` 整棵树的痕迹——
    **它一直是启动失败的证据，被读成了「照常启动」。**

    现在改成直接看进程死没死。
    """
    tag = "dis" if service_name == "labRegistry" else "never"
    profile = lab_home.make_profile(f"l09-unsat-{tag}")
    _link_all(profile, fixtures_dir)
    profile.link_plugin("lab-recorder", RECORDER)

    events = lab_home.root / f"events-{tag}.jsonl"
    ledger = lab_home.root / f"ledger-{tag}.json"

    entries = [
        _entry("lab-recorder", "lab-recorder", config={"out": events.as_posix(), "flushMs": 100}),
        # 用条目级 inject 直接指定要等的服务名（用例 4 已证实它不会削弱代码里的声明）
        _entry("lab-alpha", "lab-alpha", inject=[service_name]),
    ]
    if service_name == "labRegistry":
        entries.insert(1, _entry("lab-registry", "lab-registry", disabled=True, config={"ledger": ledger.as_posix()}))

    profile.write_patch(_patch(*entries))

    inst = launch(profile, wait_http=False)
    time.sleep(5)
    alive = inst.alive()
    logs = inst.logs(tail=30)
    inst.stop()
    time.sleep(1)

    print(f"\n  [{variant}] → **{'启动成功' if alive else '启动失败'}**（退出码 {inst.proc.returncode}）")
    verdicts = dict.fromkeys(
        ln.strip() for ln in logs.splitlines() if "pending (waiting" in ln or "did not activate" in ln
    )
    for line in verdicts:
        print("    " + line)

    if events.exists():
        rows = [json.loads(ln) for ln in events.read_text(encoding="utf-8").splitlines() if ln.strip()]
        mine = [e for e in rows if e.get("id") == "lab-alpha"]
        for e in mine:
            if e["kind"] == "status":
                print(f"    +{e['ms']:8.3f}ms  {e['from']:>9} → {e['to']}")
            elif e["kind"] == "snapshot":
                print(f"    +{e['ms']:8.3f}ms  snapshot fiberState={e.get('to')}")

    assert not alive, (
        "预期 boot 末尾的审计让启动失败。它居然活着——那说明 assertEntriesActivated "
        "有 L0 还没发现的放行条件，记进 DRAFT.md"
    )
    assert verdicts, f"启动是失败了，但日志里没找到审计判词：\n{logs}"
