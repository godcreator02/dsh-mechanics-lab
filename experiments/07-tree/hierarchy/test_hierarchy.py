"""hierarchy · 树的归属由 config 的嵌套结构决定，不由写在哪个 patch 文件决定

档次 ② ｜ 性质 🔬 ｜ 状态 ✅ ｜ 1 条用例 ｜ 不需要 web

发现型：官方 `docs/official` 对「树怎么长出来」没有专门篇目——`user/develop/`
只讲怎么写插件，不讲框架怎么装配运行时的条目树，所以本项先如实记录观测到的
形状，再下判定。

## 判定

- **`cordis:group`（内置插件 `@deepseek-ai/cordis-plugin-group`）是运行时
  造出嵌套子树的写法。** `group: true` 的条目激活时，`Service.init`
  无条件跑 `this.update(this.config)`，把 `config` 数组里的每一项都
  创建成一个真的子条目，父指针指向 group 自己（用条目 id，不是
  `cordis:group` 这个 name）。已实测，`test_group_builds_nested_subtree`。
- **父指针跟着 config 的嵌套结构走，不跟着「写在哪个 patch 文件里」走。**
  `inner-group` 嵌套写在 `outer-group` 的 config 数组里，它的 `parent`
  就是 `outer-group`，不是顶层的 `include`——这是 group 与「活层里平铺
  一堆 `- insert:`」的本质区别：后者所有条目的 `parent` 都是 `include`，
  前者的 `parent` 由写在哪一层 config 决定。已实测。
- **`loader.entries()` 的扁平列表不带层级信息，深度必须沿 `parent`
  链自己算。** 三层深的 `leaf-2` 和顶层的 `census` 摆在同一份列表里，
  列表位置本身分不出谁在谁下面。已实测。

## 观测方法

`fixtures/tree-census` 拉起后 `ctx.get("loader")`，遍历 `loader.entries()`，
记录每个条目的 `id / name / parent / group / disabled / hasFiber /
fiberState`，settle 快照里断言。深度不是普查员算的——普查员只记录每个
条目自己的 `parent`，深度由测试代码里的 `depth_of()` 沿 `parent` 链自己
走出来，这正是本项要证明的事本身：这条信息不在 `loader.entries()`
本身，必须重新算。
"""

from __future__ import annotations

import json
from pathlib import Path

from lab import LabHome


def census_patch(entry_id: str, out: Path, *, delay_ms: int = 2500, extra: str = "") -> str:
    return f"""# hierarchy 活层
- insert:
    - id: {entry_id}
      name: tree-census
      config:
        out: {json.dumps(out.as_posix())}
        delayMs: {delay_ms}
{extra}"""


def read_census(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
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
    """沿 `parent` 链往上数，数到根组（`parent` 为 None）为止.

    这就是本用例要证明的事本身：`loader.entries()` 平铺的列表里没有这个
    信息，深度完全是从 `parent` 字段重新走出来的。
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
        flag = " [group]" if e.get("group") else ""
        parent = f"  ⊂{e['parent']}" if e.get("parent") else ""
        print(f"    {indent}· id={e['id']!s:<20} {e['name']!s:<38} {state}{flag}{parent}")


def test_group_builds_nested_subtree(lab_home: LabHome, fixtures_dir: Path, launch):
    """`cordis:group` 嵌套写法造出的父指针，跟着 config 的嵌套结构走。

    结构：

        include
        └─ outer-group (group)
           ├─ leaf-1
           └─ inner-group (group)
              └─ leaf-2

    断言三件事：
      * `outer-group` 的 `parent` 是 `include`，`inner-group` 的 `parent`
        是 `outer-group`（它嵌套写在 `outer-group` 的 config 里，不是顶层）
      * `leaf-1` 与 `inner-group` 深度相同（都是 `outer-group` 的直接孩子），
        `leaf-2` 比它们深一层——深度完全由 `depth_of()` 沿 `parent` 链算出
      * 扁平列表把三层深的 `leaf-2` 和顶层的 `census` 摆在同一份列表里，
        列表位置本身不带层级信息
    """
    census_out = lab_home.root / "census-nesting.json"
    profile = lab_home.make_minimal_profile(
        "hierarchy",
        patch=census_patch(
            "census",
            census_out,
            extra="""
    - id: outer-group
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      config:
        - id: leaf-1
          name: tree-leaf
        - id: inner-group
          name: '@deepseek-ai/cordis-plugin-group'
          group: true
          config:
            - id: leaf-2
              name: tree-leaf
""",
        ),
    )
    profile.link_plugin("tree-census", fixtures_dir / "tree-census")
    profile.link_plugin("tree-leaf", fixtures_dir / "tree-leaf")

    inst = launch(profile, wait_http=False)
    settle_snap = inst.wait_for(lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照")
    show_tree(settle_snap, "outer-group ⊃ {leaf-1, inner-group ⊃ leaf-2}")

    by_id = entries_by_id(settle_snap)
    for expect_id in ("include", "census", "outer-group", "inner-group", "leaf-1", "leaf-2"):
        assert expect_id in by_id, f"树里缺条目 {expect_id}：{sorted(by_id)}"

    assert by_id["outer-group"]["parent"] == "include", "outer-group 应当直接挂在 include 子树里"
    assert by_id["leaf-1"]["parent"] == "outer-group", "leaf-1 应当是 outer-group 的孩子"
    assert by_id["inner-group"]["parent"] == "outer-group", (
        "inner-group 嵌套写在 outer-group 的 config 里，parent 应当是 outer-group"
    )
    assert by_id["leaf-2"]["parent"] == "inner-group", "leaf-2 应当是 inner-group 的孩子，不是 outer-group 的"

    d_outer = depth_of(by_id, by_id["outer-group"])
    d_leaf1 = depth_of(by_id, by_id["leaf-1"])
    d_inner = depth_of(by_id, by_id["inner-group"])
    d_leaf2 = depth_of(by_id, by_id["leaf-2"])
    print(f"\n  深度：outer-group={d_outer}  leaf-1={d_leaf1}  inner-group={d_inner}  leaf-2={d_leaf2}")
    assert d_leaf1 == d_inner == d_outer + 1, "leaf-1 和 inner-group 都是 outer-group 的直接孩子，深度应当相等"
    assert d_leaf2 == d_inner + 1, "leaf-2 比它的父 inner-group 深一层"

    flat_ids = [e["id"] for e in settle_snap["entries"]]
    print(f"\n  扁平列表里的出场顺序：{flat_ids}")
    assert "leaf-2" in flat_ids and "census" in flat_ids, "三层深的 leaf-2 与顶层的 census 应当出现在同一份扁平列表里"
