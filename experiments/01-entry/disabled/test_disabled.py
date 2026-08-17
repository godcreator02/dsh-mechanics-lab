"""disabled · 不挂载，不是删除

档次 ① ｜ 性质 📗 复述型 + 🔬 发现型（`!!js` 求值现状） ｜ 状态 ✅ ｜ 6 条用例（4 个参数化） ｜ 不需要 web

## 判定

- **`disabled: true` 的条目仍在组合树里，只是 `apply` 不执行。** dump 看得见、
  patch 还能按 id 定位它——已实测（`test_disabled_keeps_entry_in_tree_but_skips_apply`）。
  禁用是可逆的，删除不是：删掉条目之后 patch 再改它只会得到
  `patch: entry "xxx" not found` 的警告然后静默跳过（这条属于 02-recipe 的
  `override-semantics`，本项不复述）
- **「写了但关掉」≠「压根不写那一条」。** 前者在树上（采集器拍得到、有快照，
  但没有 fiber）；后者连拍都拍不到。两边一样的地方是都一句话没说，光看
  「跑没跑」分不出这两种——已实测
  （`test_disabled_entry_stays_in_tree_without_fiber`、
  `test_disabled_differs_from_absent_entry`）。把 `disabled: true` 那一行去掉重起，
  条目就恢复正常（`test_removing_disabled_flag_restores_apply`）
- **`disabled` 可以写 `!!js` 表达式，在条目激活时才求值，不在 dump 时。**
  两个角度都验过：按平台条件禁用（本机 win32，两个变体结果相反）
  （`test_disabled_platform_conditional_expression`）；以及对照官方
  postmortem 0002 记录过的历史 bug——`Entry.disabled` 曾经直接读
  `entry.options.disabled` 从不插值，`!!js` 表达式解析成对象、对象恒真，
  受影响插件永远判定为禁用。当前 `cordis-plugin-loader/src/config/entry.ts`
  的 `disabledOf()` 会对表达式求值（`!!js false` 与 `!!js true` 结果相反）——
  已实测，postmortem 描述的 bug 在当前版本不复现
  （`test_disabled_boolean_expression_matches_current_behavior`）

## 观测方法

两类信号，看能不能靠 apply 有没有跑分出结论：

- **能**：见证文件够了（静态语义那条、两个 `!!js` 求值角度）——`disabled: true`
  时 apply 不跑，见证文件不出现；跑了就出现
- **不能**：见证文件只能证明「跑了没有」，证明不了「树上还在不在」「有没有
  fiber」。判「在不在树上」「有没有 fiber」这几条，改用
  `observatory/lab-recorder`：它能看到条目的快照（`hasFiber`、`disabled`
  标记）和状态迁移。「别的条目动了、这条没动」是「它没动」的必要对照——
  单看一张快照分不出「还没轮到」和「不会有」，因为采集器睁眼那一刻别的条目
  也可能还没建 fiber

## 没覆盖到的

`disabled` 沿父链向上传播（祖先禁用则本条目不运行，`group` 自己不受影响）
属于 02-recipe/07-tree 的树形结构问题，本项只验单个条目自身的 `disabled`。
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from lab import LAB_ROOT, dump_config, entry_ids, of_kind, read_events, reports, states_of, timeline

pytestmark = pytest.mark.instance

RECORDER = LAB_ROOT / "observatory" / "lab-recorder"


# ── 辅助：静态 + 见证文件那三条，走 lab-entry ────────────────────────────────


def _insert(entry_id: str, name: str, *, extra_lines: str = "", config: dict) -> str:
    body = "\n".join(f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items())
    extra = "\n".join(f"      {line}" for line in extra_lines.splitlines() if line.strip())
    return f"""# disabled 活层
- insert:
    - id: {entry_id}
      name: {name}
{extra + chr(10) if extra else ""}      config:
{body}
"""


def _wait_for_file(path: Path, *, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.3)
    raise AssertionError(f"等了 {timeout}s，见证文件仍未出现：{path}")


def _assert_never_applies(witness: Path, *, seconds: float = 12.0) -> None:
    """验证 apply 不会执行。固定长等待，不能轮询提前退出——
    提前退出只能证明「此刻还没发生」，证明不了「不会发生」。
    """
    time.sleep(seconds)
    assert not witness.exists(), f"apply 竟然执行了：{witness}"


def test_disabled_keeps_entry_in_tree_but_skips_apply(lab_home, fixtures_dir, launch):
    """`disabled: true` 是「不挂载」，不是「删掉」。

    条目仍然在组合树里（dump 看得见、patch 还能按 id 定位它），只是 apply
    不执行。禁用是可逆的，删除不是。
    """
    profile = lab_home.make_minimal_profile("static-off")
    profile.link_plugin("lab-entry", fixtures_dir / "lab-entry")
    witness = lab_home.root / "w-disabled.json"
    profile.write_patch(
        _insert("lab-entry", "lab-entry", extra_lines="disabled: true", config={"witness": witness.as_posix()})
    )

    dump = dump_config(lab_home, profile.name)
    entry = dump.require("lab-entry")  # ← 还在树里
    assert entry["disabled"] is True

    inst = launch(profile, wait_http=False)
    try:
        _assert_never_applies(witness)
    finally:
        inst.stop()
    print("\n  条目在组合树里、disabled=True，apply 未执行——禁用 ≠ 删除")


@pytest.mark.parametrize(
    ("variant", "expr", "should_load"),
    [
        ("条件成立 → 禁用", "process.platform === 'win32'", False),
        ("条件不成立 → 照常加载", "process.platform === 'linux'", True),
    ],
    ids=["expr-true", "expr-false"],
)
def test_disabled_platform_conditional_expression(lab_home, fixtures_dir, launch, variant, expr, should_load):
    """`disabled` 可以写 `!!js` 表达式，激活时求值，用平台条件验证。

    DSH 的 patch 方言：`!!js` 标量不在解析时求值，而是延迟到条目激活时、在该
    条目自己的上下文里算。官方 `dsh-base` 就用这招做平台条件禁用。本机是
    win32，两个变体预期正好相反——这比断言一个死值更能证明表达式真的被求值了。
    静态 dump 里保留的是表达式原文，不是求值结果。
    """
    tag = "t" if should_load else "f"
    profile = lab_home.make_minimal_profile(f"expr-{tag}")
    profile.link_plugin("lab-entry", fixtures_dir / "lab-entry")
    witness = lab_home.root / f"w-expr-{tag}.json"
    profile.write_patch(
        _insert("lab-entry", "lab-entry", extra_lines=f"disabled: !!js {expr}", config={"witness": witness.as_posix()})
    )

    dump = dump_config(lab_home, profile.name)
    assert dump.require("lab-entry")["disabled"] == expr, "dump 应保留表达式原文，不是求值结果"

    inst = launch(profile, wait_http=False)
    try:
        if should_load:
            got = _wait_for_file(witness)
            assert got["platform"] == "win32"
            print(f"\n  [{variant}] 表达式 `{expr}` → 加载了（本机 win32）")
        else:
            _assert_never_applies(witness)
            print(f"\n  [{variant}] 表达式 `{expr}` → 未加载（本机 win32）")
    finally:
        inst.stop()


@pytest.mark.parametrize(
    ("expr", "should_load"), [("false", True), ("true", False)], ids=["expr-false-loads", "expr-true-disabled"]
)
def test_disabled_boolean_expression_matches_current_behavior(lab_home, fixtures_dir, launch, expr, should_load):
    """`!!js` 表达式当前是否真的被求值，对照官方 postmortem 0002 记录过的旧 bug。

    postmortem 0002 记的根因是：`Entry.disabled` 直接读 `entry.options.disabled`，
    从不对它插值——`!!js` 表达式解析成一个对象，对象恒真，所以受影响的插件
    永远被判定为「禁用」，不管表达式写的是什么。

    但当前 `cordis-plugin-loader/src/config/entry.ts` 的 `disabledOf()`：

        return isJsExpr(options.disabled)
          ? Boolean(this.evaluate(options.disabled.__jsExpr))
          : Boolean(options.disabled)

    ——会对 `!!js` 表达式求值。`!!js false` 和 `!!js true` 都是「语法合法的表达式
    对象」：如果 postmortem 描述的 bug 仍在，两者都应该恒真（永不加载）；如果
    已经修复，两者的加载结果应该相反。这条直接对照验证当前行为。
    """
    tag = "t" if should_load else "f"
    witness = lab_home.root / f"w-jsdisabled-{tag}.json"
    profile = lab_home.make_minimal_profile(
        f"jsdisabled-{tag}",
        patch=f"""# disabled 用例：!!js 表达式当前会不会被求值
- insert:
    - id: probe
      name: lab-entry
      disabled: !!js {expr}
      config:
        witness: {json.dumps(witness.as_posix())}
""",
    )
    profile.link_plugin("lab-entry", fixtures_dir / "lab-entry")

    inst = launch(profile, wait_http=False)
    try:
        if should_load:
            got = _wait_for_file(witness)
            print(f"\n  !!js {expr} → 加载了：{got['marker']}")
        else:
            _assert_never_applies(witness)
            print(f"\n  !!js {expr} → 未加载（12s 内没写见证文件）")
    finally:
        inst.stop()


# ── 辅助：观察器版本那三条，走 lab-recorder + worker.mjs ─────────────────────


def _worker_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "worker.mjs"


def _build_with_recorder(lab_home, fixtures_dir: Path, tag: str, *, entry: str):
    """搭一个实例：timer/hmr（基线自带）+ lab-recorder + 给定的 worker 那一段。

    `entry` 传空字符串就是「patch 文件里压根没有 worker 那一条」。
    """
    events = lab_home.root / f"events-{tag}.jsonl"
    patch = f"""- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {json.dumps(events.as_posix())}
        flushMs: 100
{entry}"""
    profile = lab_home.make_minimal_profile(tag, patch=patch)
    profile.link_plugin("lab-recorder", RECORDER)
    shutil.copy2(_worker_path(fixtures_dir), profile.dir / "worker.mjs")
    return profile, events


ENABLED = """
- insert:
    - id: worker
      name: ./worker.mjs
      config:
        班次: 早班
"""

DISABLED = """
- insert:
    - id: worker
      name: ./worker.mjs
      disabled: true
      config:
        班次: 早班
"""


def _wait_for_events(inst, path: Path, *, least: int = 4, timeout: float = 40.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    events: list[dict] = []
    while time.monotonic() < deadline:
        events = read_events(path)
        if len(events) >= least:
            return events
        if not inst.alive():
            break
        time.sleep(0.3)
    return events


def _snapshot_of(events: list[dict], entry_id: str) -> dict | None:
    for e in of_kind(events, "snapshot"):
        if e.get("id") == entry_id:
            return e
    return None


def test_disabled_entry_stays_in_tree_without_fiber(lab_home, fixtures_dir, launch):
    """写了 `disabled: true`：那一条还在树上，但没有 fiber，一句话没说。

    四项一起看才完整：采集器睁眼时拍得到它（它确实在树上）；但它没有 fiber；
    没有任何状态变化；apply 没跑，所以一句话都没说。单看快照那一张分不出
    结果——采集器睁眼时 timer 也可能还没建 fiber——所以同时验「timer 后来
    真的动了」，否则「worker 没动」也可能只是采集器没记上。
    """
    profile, events_path = _build_with_recorder(lab_home, fixtures_dir, "off", entry=DISABLED)

    inst = launch(profile, wait_http=False)
    events = _wait_for_events(inst, events_path)
    time.sleep(8.0)  # 验「不该发生」：固定长等待，不能一看没有就下结论
    events = read_events(events_path)

    print("\n══ 写了 disabled: true ══")
    print(timeline(events))

    shot = _snapshot_of(events, "worker")

    assert inst.alive(), f"实例应当照常活着——关掉一条不是错误：\n{inst.logs()}"
    assert shot is not None, f"它应当还在树上（采集器该拍到它），实际树上是 {sorted(entry_ids(events))}"
    assert shot.get("disabled") is True, f"这一条该被标成关掉的，实际快照是 {shot}"
    assert shot.get("hasFiber") is False, f"关掉的条目不该有 fiber，实际快照是 {shot}"
    assert shot.get("to") is None, f"没有 fiber 就没有状态可言，实际快照是 {shot}"
    assert states_of(events, "worker") == [], f"关掉的条目不该有任何状态变化，实际走了 {states_of(events, 'worker')}"
    assert not reports(events, who="worker"), "它说话了——那 apply 就是跑了，没关掉"
    assert "ACTIVE" in states_of(events, "timer"), "连 timer 都没走状态——那说明采集器没记，不能拿来判 worker"


def test_disabled_differs_from_absent_entry(lab_home, fixtures_dir, launch):
    """「写了但关掉」 vs 「压根不写那一条」——两者不是一回事。

    不写：它不在树上，采集器连拍都拍不到。写了但关掉：它在树上，采集器拍得到，
    只是没有 fiber。两边一样的地方是都一句话没说，所以光看「跑没跑」分不出这
    两种情况，得看它在不在树上。
    """
    off_profile, off_events = _build_with_recorder(lab_home, fixtures_dir, "off-cmp", entry=DISABLED)
    absent_profile, absent_events = _build_with_recorder(lab_home, fixtures_dir, "absent", entry="")

    off = launch(off_profile, wait_http=False)
    absent = launch(absent_profile, wait_http=False)
    _wait_for_events(off, off_events)
    _wait_for_events(absent, absent_events)
    time.sleep(8.0)

    off_ev, absent_ev = read_events(off_events), read_events(absent_events)

    assert off.alive() and absent.alive(), "两个实例都该活着"

    # 写了但关掉：在树上
    assert _snapshot_of(off_ev, "worker") is not None, "写了 disabled 的那条应当还在树上"
    assert "worker" in entry_ids(off_ev), "写了 disabled 的那条应当出现在事件流里"

    # 压根不写：不在树上，连名字都不出现
    assert _snapshot_of(absent_ev, "worker") is None, "没写那一条，采集器不该拍到它"
    assert "worker" not in entry_ids(absent_ev), (
        f"没写那一条，它不该出现在事件流里，实际 {sorted(entry_ids(absent_ev))}"
    )

    # 两边一样的地方：都没跑
    assert not reports(off_ev, who="worker"), "关掉的那条不该说话"
    assert not reports(absent_ev, who="worker"), "没挂的那条不该说话"
    assert states_of(off_ev, "worker") == states_of(absent_ev, "worker") == []
    print("\n  两边都没跑；区别在「在不在树上」")


def test_removing_disabled_flag_restores_apply(lab_home, fixtures_dir, launch):
    """把 `disabled: true` 那一行去掉重起，它就照常跑了。

    这条和 disabled 那条用的 patch 文件只差这一行，连 config 都一模一样——
    所以跑没跑的差别只能是这一行造成的。
    """
    profile, events_path = _build_with_recorder(lab_home, fixtures_dir, "on", entry=ENABLED)

    inst = launch(profile, wait_http=False)
    _wait_for_events(inst, events_path)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline and not reports(read_events(events_path), who="worker"):
        if not inst.alive():
            break
        time.sleep(0.3)
    events = read_events(events_path)

    said = reports(events, who="worker")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said, "去掉那一行它就该跑起来，却一句话没说"
    assert said[0]["note"] == "我跑起来了"
    assert said[0]["data"] == {"收到的config": {"班次": "早班"}}, f"config 该照常送达，实际 {said[0]['data']}"
    assert "ACTIVE" in states_of(events, "worker"), (
        f"它该有 fiber、该走到 ACTIVE，实际走了 {states_of(events, 'worker')}"
    )
    print("\n  去掉 disabled: true → 照常跑起来，走到 ACTIVE")
