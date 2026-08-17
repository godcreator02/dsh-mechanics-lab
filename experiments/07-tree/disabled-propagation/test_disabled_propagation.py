"""disabled-propagation · 禁用沿父链向下传播，group 自己免疫

档次 ② ｜ 性质 🔬 ｜ 状态 ✅ ｜ 2 条用例（parametrize） ｜ 不需要 web

发现型：官方 `docs/official` 对本机制没有专门篇目。源码
`cordis-plugin-loader/src/config/entry.ts` 的 `_disabled()`：

    private _disabled(options: EntryOptions) {
      // group is always enabled
      if (options.group) return false
      if (this.disabledOf(options)) return true
      let entry = this.parent.ctx.fiber.entry
      while (entry) {
        if (this.disabledOf(entry.options)) return true
        entry = entry.parent.ctx.fiber.entry
      }
      return false
    }

普通条目沿父链一路往上查，任一祖先的 `disabled` 求值为真就不激活。但函数
开头有一句短路：条目自己若是 group（`options.group` 为真），直接返回
`false`，后面的判断根本不看——**group 自己不受 `disabled` 影响**。

## 判定

- **`disabled: true` 的默认行为是沿父链向上查：任一祖先被禁用，本条目
  就不运行。** 对照组实测：普通条目自己写 `disabled: true`，自己就不
  激活（`hasFiber=False`）。已实测。
- **`cordis:group` 条目自己免疫这条规则。** 上面 `_disabled()` 开头短路：
  `if (options.group) return false`——group 自己的 `disabled` 原文不管
  写了什么，都不影响它自己的激活。已实测：`disabled-group` 自己
  `hasFiber=True`、`fiberState=2`（ACTIVE），尽管它的 `options.disabled`
  原文是 `true`。
- **这条例外只保护 group 自己，不保护它的孩子。** 孩子在自己的
  `_disabled()` 里沿父链往上走一层查到的正是这个 group 的 `options`，
  那里的 `disabled` 读到的是原文 `true`，孩子照样被拦下（无 fiber）。
  已实测。「group 自己不受影响」和「它的孩子受影响」同时成立——不是
  矛盾，是同一段代码里两个分支各自生效的结果。

## 观测方法

`fixtures/tree-census` 拉起后遍历 `loader.entries()`，记录每个条目
`disabled`（自己声明的原文，不是沿父链算出来的有效值）、`group`、
`hasFiber`、`fiberState`。两个字段必须分开记：`disabled` 原文与「是否
真的激活」合成一个字段就验不出「原文写了 disabled 但自己照样激活」这个
反直觉组合。

对照组（普通条目被禁用）是必需的，不是装饰——只测 group 变体会把
「group 自己不受影响」误读成「disabled 在这个场景失效了」；两相对照
才看得清那是**例外**，不是默认行为的改变。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lab import LabHome


def census_patch(entry_id: str, out: Path, *, delay_ms: int = 2500, extra: str = "") -> str:
    return f"""# disabled-propagation 活层
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
          name: tree-leaf
""",
            "disabled-group",
            "child-under-disabled",
        ),
        (
            "对照组：普通条目被禁用，自己就真的不激活",
            "plain",
            """
    - id: disabled-plain
      name: tree-leaf
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
    """两个变体：group 自身写 `disabled: true`，与不带 group 的普通条目对照。

    变体 A（group）：`disabled-group` 应当 `hasFiber=True`、`fiberState=2`
    （ACTIVE）——尽管它自己的 `options.disabled` 原文就是 `true`；它的孩子
    `child-under-disabled` 应当从未被初始化（无 fiber）。

    变体 B（对照组，普通条目）：`disabled-plain` 自己写了 `disabled: true`，
    应当自己就不激活——这是默认行为，group 才是例外，不是「disabled 在
    group 语境下失效了」。
    """
    census_out = lab_home.root / f"census-{tag}.json"
    profile = lab_home.make_minimal_profile(
        f"disabled-propagation-{tag}", patch=census_patch(f"census-{tag}", census_out, extra=extra)
    )
    profile.link_plugin("tree-census", fixtures_dir / "tree-census")
    profile.link_plugin("tree-leaf", fixtures_dir / "tree-leaf")

    inst = launch(profile, wait_http=False)
    settle_snap = inst.wait_for(lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照")
    by_id = entries_by_id(settle_snap)

    if group_id is not None:
        assert group_id in by_id, f"{kind}：树里找不到 {group_id}"
        group_entry = by_id[group_id]
        print(
            f"\n  {group_id}：disabled(原文)={group_entry['disabled']}  hasFiber={group_entry['hasFiber']}"
            f"  fiberState={group_entry['fiberState']}"
        )
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
        assert plain_entry["hasFiber"] is False, "对照组：普通条目被禁用，自己就真的不会激活——默认行为，不是例外"
