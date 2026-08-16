"""L8 · 层级：谁在子树里、谁不在。

`loader.entries()` 是扁平遍历（自己 + 所有嵌套子树），光看那个列表分不出层级。
L0 已经用普查员的 `parent` 字段把最小环境的树立住了：

    根组
    ├─ include (cordis:include)    ← 树根，配方装在它的 config.patches 里
    │   └─ 配方里的条目…            ⊂include
    ├─ timer  ← 兜底补的，与 include **平级**
    └─ hmr    ← 同上

本课在这个地基上补三件事：

  1. `cordis:group`（第二个内置插件）怎么造出嵌套子树——group 里的条目
     `parent` 是不是指向 group、层级深度能不能嵌套、`loader.entries()`
     会不会把它们一起摊平列出来。
  2. 禁用的向下传播：祖先被禁用则本条目不运行，但 `group` 自己是例外
     （源码 `entry.ts` 的 `_disabled()`：`if (options.group) return false`）。
  3. 服务隔离（`isolate`）：结构层面之外，正面验一次「两个组各自看到自己的
     服务实例、互不影响」。

全部用例复用 L0 的普查手法：`ctx.get("loader")` + 遍历 `loader.entries()`，
不预设答案，先打印树的形状，再断言。观测点绝不抛错，拿不到就如实记 null。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lab import Instance, LabHome

#: 拉起后观察多久再拍 settle 快照。普查员自己延后 CENSUS_DELAY_MS 拍第二张，
#: 这里要留够余量——组里的条目也要走一遍 apply，比单个条目略慢。
OBSERVE = 6.0
CENSUS_DELAY_MS = 2500


# ── 辅助 ────────────────────────────────────────────────────────────────────


def census_patch(entry_id: str, out: Path, *, delay_ms: int = CENSUS_DELAY_MS, extra: str = "") -> str:
    """挂一个普查员 + extra 原样追加的活层。"""
    return f"""# L8 活层
- insert:
    - id: {entry_id}
      name: l08-census
      config:
        out: {json.dumps(out.as_posix())}
        delayMs: {delay_ms}
{extra}"""


def watch(inst: Instance, seconds: float = OBSERVE) -> dict:
    """看着实例跑一段时间，如实记录发生了什么，不做任何断言。"""
    deadline = time.monotonic() + seconds
    died_at = None
    while time.monotonic() < deadline:
        if not inst.alive():
            died_at = round(seconds - (deadline - time.monotonic()), 2)
            break
        time.sleep(0.25)
    return {
        "alive": inst.alive(),
        "died_at": died_at,
        "exit_code": inst.proc.returncode,
        "logs": inst.logs(tail=40),
    }


def read_census(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
    """从最后一次 apply 往前找某一张快照——理由与 L0 相同，重挂后前一轮过时。"""
    if not census:
        return None
    for record in reversed(census):
        for snap in record.get("snapshots", []):
            if snap.get("phase") == name:
                return snap
    return None


def entries_by_id(snap: dict) -> dict[str, dict]:
    return {e["id"]: e for e in (snap.get("entries") or []) if e.get("id")}


def depth_of(by_id: dict[str, dict], entry: dict) -> int:
    """沿 parent 链往上数，数到根组（parent 为 None）为止。

    这就是本课要证明的事本身：`loader.entries()` 平铺的列表里没有这个信息，
    depth 完全是从 `parent` 字段重新走出来的。
    """
    depth = 0
    parent_id = entry.get("parent")
    seen: set[str] = set()
    while parent_id is not None and parent_id not in seen:
        seen.add(parent_id)
        depth += 1
        parent = by_id.get(parent_id)
        parent_id = parent.get("parent") if parent else None
    return depth


def show_tree(snap: dict | None, title: str) -> None:
    """打印一张真实的树形图——缩进由 parent 链的深度决定，不是列表顺序。"""
    print(f"\n  ── {title} ──")
    if snap is None:
        print("    （没有这张快照）")
        return
    entries = snap.get("entries")
    if entries is None:
        print("    条目：拿不到 loader")
        return
    by_id = entries_by_id(snap)
    for e in entries:
        depth = depth_of(by_id, e)
        indent = "    " * depth
        state = "无 fiber" if not e["hasFiber"] else f"state={e['fiberState']}"
        flags = []
        if e.get("group"):
            flags.append("group")
        if e.get("disabled"):
            flags.append("disabled(原文)")
        flag = f" [{', '.join(flags)}]" if flags else ""
        parent = f"  ⊂{e['parent']}" if e.get("parent") else ""
        print(f"    {indent}· id={e['id']!s:<20} {e['name']!s:<38} {state}{flag}{parent}")


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_group_builds_nested_subtree(lab_home: LabHome, fixtures_dir: Path, launch):
    """① group 怎么造出嵌套子树。

    结构：

        include
        └─ outer-group (group)
           ├─ leaf-1
           └─ inner-group (group)
              └─ leaf-2

    要验的判定：
      * `outer-group` / `inner-group` 的 `parent` 都是 `include`
        —— 不对，`inner-group` 的 parent 应当是 `outer-group`（它嵌套在里面）
      * `leaf-1` 的 parent 是 `outer-group`，`leaf-2` 的 parent 是 `inner-group`
      * `loader.entries()` 把三层深的 `leaf-2` 和顶层的 `census` 摊在同一个
        列表里——「扁平遍历」不是一句空话，深度必须靠 parent 链自己算出来
    """
    census_out = lab_home.root / "census-nesting.json"
    profile = lab_home.make_minimal_profile("nesting", patch=census_patch("census", census_out, extra="""
    - id: outer-group
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      config:
        - id: leaf-1
          name: l08-leaf
        - id: inner-group
          name: '@deepseek-ai/cordis-plugin-group'
          group: true
          config:
            - id: leaf-2
              name: l08-leaf
"""))
    profile.link_plugin("l08-census", fixtures_dir / "l08-census")
    profile.link_plugin("l08-leaf", fixtures_dir / "l08-leaf")

    inst = launch(profile, wait_http=False)
    got = watch(inst)
    if not got["alive"]:
        print(got["logs"])

    census = read_census(census_out)
    settle_snap = phase(census, "settle")
    show_tree(settle_snap, "outer-group ⊃ {leaf-1, inner-group ⊃ leaf-2}")

    assert settle_snap is not None and settle_snap.get("entries") is not None, (
        f"普查员没能拍到 settle 快照：\n{got['logs']}"
    )
    by_id = entries_by_id(settle_snap)

    for expect_id in ("include", "census", "outer-group", "inner-group", "leaf-1", "leaf-2"):
        assert expect_id in by_id, f"树里缺条目 {expect_id}：{sorted(by_id)}"

    assert by_id["outer-group"]["parent"] == "include", "outer-group 应当直接挂在 include 子树里"
    assert by_id["leaf-1"]["parent"] == "outer-group", "leaf-1 应当是 outer-group 的孩子"
    assert by_id["inner-group"]["parent"] == "outer-group", (
        "inner-group 嵌套写在 outer-group 的 config 里，parent 应当是 outer-group"
    )
    assert by_id["leaf-2"]["parent"] == "inner-group", "leaf-2 应当是 inner-group 的孩子，不是 outer-group 的"

    # 深度必须严格递增：include(0 层起点) < outer-group < leaf-1 == inner-group < leaf-2
    d_outer = depth_of(by_id, by_id["outer-group"])
    d_leaf1 = depth_of(by_id, by_id["leaf-1"])
    d_inner = depth_of(by_id, by_id["inner-group"])
    d_leaf2 = depth_of(by_id, by_id["leaf-2"])
    print(f"\n  深度：outer-group={d_outer}  leaf-1={d_leaf1}  inner-group={d_inner}  leaf-2={d_leaf2}")
    assert d_leaf1 == d_inner == d_outer + 1, "leaf-1 和 inner-group 都是 outer-group 的直接孩子，深度应当相等"
    assert d_leaf2 == d_inner + 1, "leaf-2 比它的父 inner-group 深一层"

    # group 条目自己也在 loader.entries() 的那份扁平列表里，跟它的孩子没有
    # 任何列表位置上的区分——分不出层级正是「扁平遍历」这句话的意思。
    flat_ids = [e["id"] for e in settle_snap["entries"]]
    assert flat_ids.index("outer-group") < len(flat_ids), "group 条目本身也出现在同一份扁平列表里"
    print(f"  扁平列表里的出场顺序：{flat_ids}")
    print("  → 三层深的 leaf-2 和顶层的 census 摊在同一个列表里，没有 parent 字段分不出谁在谁下面")


@pytest.mark.parametrize(
    "kind, tag, extra, group_id, child_id",
    [
        (
            "group 自己不受 disabled 影响，孩子却因它而停",
            "group",
            """
    - id: disabled-group
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      disabled: true
      config:
        - id: child-under-disabled
          name: l08-leaf
""",
            "disabled-group",
            "child-under-disabled",
        ),
        (
            "对照组：普通条目被禁用，自己就真的不激活",
            "plain",
            """
    - id: disabled-plain
      name: l08-leaf
      disabled: true
""",
            None,
            "disabled-plain",
        ),
    ],
)
def test_disabled_propagation(
    lab_home: LabHome, fixtures_dir: Path, launch, kind: str, tag: str, extra: str, group_id: str | None, child_id: str
):
    """② 禁用的向下传播，以及 group 的例外。

    源码 `entry.ts` 的 `_disabled()` 沿父链向上追溯：任一祖先被禁用，本条目
    就不运行。但开头有一条例外：`if (options.group) return false`——
    **group 自己的 `disabled` 原文对它自己的激活没有任何效力**。

    这条例外不代表「disabled 在 group 里失效」——它只是不影响 group **自己**。
    `group` 的 `Service.init` 无论如何都会跑 `this.update(this.config)` 去
    创建/更新孩子，而孩子在自己的 `_disabled()` 里会往上走一层，查到
    **父条目（也就是这个 group）的 options.disabled**，那里读到的是原文
    `true`——于是孩子照样被拦下。「自己不受影响」和「孩子受影响」同时成立，
    这条判定的分量就在这个反直觉的组合里。

    对照组用一个不带 group 的普通条目验证默认行为：正常情况下 `disabled: true`
    确实会让条目自己不激活——group 是**例外**，不是「disabled 不管用了」。
    """
    census_out = lab_home.root / f"census-disabled-{tag}.json"
    profile = lab_home.make_minimal_profile(
        f"disabled{tag}", patch=census_patch(f"census-{tag}", census_out, extra=extra)
    )
    profile.link_plugin("l08-census", fixtures_dir / "l08-census")
    profile.link_plugin("l08-leaf", fixtures_dir / "l08-leaf")

    inst = launch(profile, wait_http=False)
    got = watch(inst)
    if not got["alive"]:
        print(got["logs"])

    census = read_census(census_out)
    settle_snap = phase(census, "settle")
    show_tree(settle_snap, kind)

    assert settle_snap is not None and settle_snap.get("entries") is not None, (
        f"{kind}：普查员没能拍到 settle 快照\n{got['logs']}"
    )
    by_id = entries_by_id(settle_snap)

    if group_id is not None:
        assert group_id in by_id, f"{kind}：树里找不到 {group_id}"
        group_entry = by_id[group_id]
        print(f"\n  {group_id}：disabled(原文)={group_entry['disabled']}  hasFiber={group_entry['hasFiber']}"
              f"  fiberState={group_entry['fiberState']}")
        assert group_entry["disabled"] is True, "前提：group 自己的 options.disabled 原文确实是 true"
        assert group_entry["hasFiber"] is True and group_entry["fiberState"] == 2, (
            "group 自己应当照样激活（ACTIVE）——写了 disabled 对它自己没有效力"
        )

        assert child_id in by_id, f"{kind}：树里找不到孩子 {child_id}（连条目本身都没建出来）"
        child_entry = by_id[child_id]
        print(f"  {child_id}：hasFiber={child_entry['hasFiber']}  fiberState={child_entry['fiberState']}")
        assert child_entry["hasFiber"] is False, (
            "孩子应当因为父 group 被禁用而从未激活——它自己的 options.disabled 是 false，"
            "但沿父链查到 group 的 disabled=true"
        )
    else:
        assert child_id in by_id, f"{kind}：树里找不到 {child_id}"
        plain_entry = by_id[child_id]
        print(f"\n  {child_id}：disabled(原文)={plain_entry['disabled']}  hasFiber={plain_entry['hasFiber']}")
        assert plain_entry["disabled"] is True, "前提：这个条目自己就写了 disabled: true"
        assert plain_entry["hasFiber"] is False, (
            "对照组：普通条目被禁用，自己就真的不会激活——默认行为，不是例外"
        )


def test_isolate_gives_each_group_its_own_service_instance(lab_home: LabHome, fixtures_dir: Path, launch):
    """③ 服务隔离：两个组各自看到自己的服务实例，互不影响。

    官方文档 `zh/user/develop/framework/service.md:113` 讲了：同一个服务可以
    有多个实例，不同插件组看到不同实例——写法是给 `cordis:group` 的条目加
    `isolate: { <服务名>: true }`。

    源码侧（`cordis-plugin-loader/src/config/isolate.ts`）：`isolate: true`
    给这个条目建一个 `LocalRealm`（以条目自己的 id 为后缀），组内 `ctx.provide`
    落进那个 realm 专属的 symbol，组外看不见、组间也互相看不见。

    实验：两个组都提供同一个服务名 `labFlavor`，值不同（vanilla / chocolate）。
    组内各挂一个消费者，`inject` 硬依赖 `labFlavor` 并把看到的值写进见证文件。
    如果隔离生效，两份见证应当各自对应各自组里的值，不串。
    """
    census_out = lab_home.root / "census-isolate.json"
    witness_a = lab_home.root / "witness-flavor-a.json"
    witness_b = lab_home.root / "witness-flavor-b.json"

    profile = lab_home.make_minimal_profile("isolate", patch=census_patch("census", census_out, extra=f"""
    - id: group-a
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      isolate:
        labFlavor: true
      config:
        - id: flavor-a
          name: lab-flavor
          config:
            value: vanilla
        - id: taster-a
          name: lab-flavor-taster
          config:
            witness: {json.dumps(witness_a.as_posix())}

    - id: group-b
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      isolate:
        labFlavor: true
      config:
        - id: flavor-b
          name: lab-flavor
          config:
            value: chocolate
        - id: taster-b
          name: lab-flavor-taster
          config:
            witness: {json.dumps(witness_b.as_posix())}
"""))
    profile.link_plugin("l08-census", fixtures_dir / "l08-census")
    profile.link_plugin("lab-flavor", fixtures_dir / "lab-flavor")
    profile.link_plugin("lab-flavor-taster", fixtures_dir / "lab-flavor-taster")

    inst = launch(profile, wait_http=False)

    def both_witnesses() -> bool:
        return witness_a.exists() and witness_b.exists()

    try:
        inst.wait_for(both_witnesses, timeout=15.0, what="两个 taster 都写出见证文件")
    except AssertionError as exc:
        got = watch(inst, seconds=0.1)  # 只是取一下 alive/日志，不再等
        print(f"\n等待失败：{exc}")
        print(f"进程还活着？ {inst.alive()}")
        print(inst.logs())
        raise

    # 顺带看一眼普查员这边的树形图——两个组、各自一份 flavor + taster。
    # 普查员自己的 settle 快照要等它的 delayMs（独立于 taster 的见证文件），
    # 轮询等它出现；这只是装饰性的展示，等不到不影响上面已经做完的断言。
    def census_settled() -> dict | None:
        return phase(read_census(census_out), "settle")

    try:
        settle_snap = inst.wait_for(census_settled, timeout=10.0, what="普查员的 settle 快照")
    except AssertionError:
        settle_snap = None
    show_tree(settle_snap, "group-a{flavor-a, taster-a} / group-b{flavor-b, taster-b}")

    data_a = json.loads(witness_a.read_text(encoding="utf-8"))
    data_b = json.loads(witness_b.read_text(encoding="utf-8"))
    print(f"\n  group-a 的 taster 看到：{data_a}")
    print(f"  group-b 的 taster 看到：{data_b}")

    assert data_a["sawValue"] == "vanilla", f"group-a 应当只看到自己组里的 vanilla，实际 {data_a}"
    assert data_b["sawValue"] == "chocolate", f"group-b 应当只看到自己组里的 chocolate，实际 {data_b}"
    print("  → 隔离生效：两组各自看到自己的服务实例，没有互相覆盖")
