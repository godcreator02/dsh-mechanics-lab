"""recipe-vs-tree · 配方 ≠ 运行时的树

档次 ② ｜ 性质 🔬 ｜ 状态 ✅ ｜ 1 条用例 ｜ 不需要 web

发现型：DSH 的官方 `user/develop/` 只讲怎么写插件，不讲框架怎么把配方组装成
运行时的条目树，本组没有官方文档可对照，所以先如实拍下树的真实形状，再下判定。

## 判定

- **运行时的条目树比 `--dump-config` 算出来的配方恰好多一个条目：
  `cordis:include`。** 反过来也成立——配方里写的每一条都能在树上找到，
  没有谁被悄悄丢掉。已实测，`test_include_is_the_only_ghost`。
- **`include` 是结构性的差异，不是基线漏配。** 它是 `dsh-app-boot`
  `mountRootInclude()` 在 boot 期现造的树根，`config` 里装着
  `{ path, patches }`——`patches` 就是四层（bundle 层 / profile 活层 /
  home 层 / overlay）拼接后的完整配方，原样塞进这一个条目的 config 里。
  它不可能同时出现在自己装的那份配方中，否则就是自指。这条推论待验的
  另一半——「活层文件改了之后，`include.config.patches` 是不是真的跟着
  变」——由 `../../04-replay/replay-mechanism` 直接断言，不在本项范围内。
  **这条推论是 04-replay 组的地基：整个配方装在 include 这一个条目的
  config 里，所以「配方热重放」在实现上就是「改 include 这一个条目的
  config」。**

## 写断言的硬约束

**幽灵条目的 id 每次启动都不一样，只能认 name 不能认 id。** 本项用
`make_minimal_profile` 显式声明 `timer` / `hmr`（固定 id），刻意避开框架
的兜底路径——兜底创建的 timer/hmr 才会带随机 id（那条行为归
`00-base/framework-fallback`，本项不重复）。`include` 例外：它的 id
固定是字面量 `"include"`，不受这条约束影响，本项的断言可以放心认它的 id。
但凡是要断言「框架自己补出来的、没有被 patch 文件显式声明」的条目，
一律只能靠 `name` 后缀匹配，不能靠 `id` 相等。

## 观测方法

`fixtures/tree-census` 是普查员：拉起实例后 `ctx.get("loader")`，遍历
`loader.entries()`，把每个条目的 `id / name / parent / disabled /
hasFiber / fiberState` 记下来，拍两张快照（apply 当下的 `boot`，延后
2 秒的 `settle`）。跟 `dump_config()` 算出来的 effective config 做 id
集合的差集比较。

选这个信号的理由：树是运行时对象图，配方是静态解析结果，两者唯一能
安全比较的公共面就是条目 id 集合——比较其它字段（比如 fiber 状态）没有
配方那边的对应物。

## 没覆盖到的

`recipe-vs-tree` 只验证了 boot 之后的静态形状（树比配方多一个 `include`）。
`include.config.patches` 本身在热重放时是否真的更新，由 04-replay 组验证，
不在本项内重复。
"""

from __future__ import annotations

import json
from pathlib import Path

from lab import LabHome, dump_config


def census_patch(out: Path, *, delay_ms: int = 2000) -> str:
    return f"""# recipe-vs-tree 活层
- insert:
    - id: census
      name: tree-census
      config:
        out: {json.dumps(out.as_posix())}
        delayMs: {delay_ms}
"""


def read_census(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
    """取某一张快照，从最后一次 apply 往前找——重挂后前一轮的快照已过时。"""
    if not census:
        return None
    for record in reversed(census):
        for snap in record.get("snapshots", []):
            if snap.get("phase") == name:
                return snap
    return None


def show_entries(snap: dict | None, title: str) -> None:
    print(f"\n  ── {title} ──")
    if snap is None:
        print("    （没有这张快照）")
        return
    entries = snap.get("entries")
    if entries is None:
        print("    条目：拿不到 loader")
        return
    for e in entries:
        state = "无 fiber" if not e["hasFiber"] else f"state={e['fiberState']}"
        under = f"  ⊂{e['parent']}" if e.get("parent") else ""
        print(f"    · id={e['id']!s:<16} {e['name']!s:<32} {state}{under}")


def test_include_is_the_only_ghost(lab_home: LabHome, fixtures_dir: Path, launch):
    """树比配方恰好多一个条目，且那个条目一定是 `include`。

    合并自旧两份实现（`l07::test_include_is_the_only_ghost`、
    `l00::test_effective_config_vs_entry_tree`）——两处用不同的最小环境各自
    验了同一件事：`--dump-config` 算出来的 id 集合，跟运行时 `loader.entries()`
    的 id 集合相减，差集恰好是 `{"include"}`，且方向反过来也要成立（配方里
    写的每一条都能在树上找到，没有谁被悄悄丢掉）。

    `include` 是结构性的差异，不是基线凑巧漏了什么：不管 config 怎么写、
    带不带任何 bundle，它都在——因为整份 effective config 就装在它的
    `config.patches` 里，它不可能同时出现在自己装的那份 config 中。
    """
    census_out = lab_home.root / "census.json"
    profile = lab_home.make_minimal_profile("recipe-vs-tree", patch=census_patch(census_out))
    profile.link_plugin("tree-census", fixtures_dir / "tree-census")

    dumped = dump_config(lab_home, profile.name)
    recipe_ids = set(dumped.ids())
    print(f"\n  effective config 里的 id（{len(recipe_ids)} 个）：{sorted(recipe_ids)}")

    inst = launch(profile, wait_http=False)
    settle = inst.wait_for(lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照")
    show_entries(settle, "运行时的条目树")

    tree_ids = {e["id"] for e in settle["entries"]}
    ghosts = tree_ids - recipe_ids
    print(f"\n  树上有、配方里没有的 id：{sorted(ghosts)}")

    assert ghosts == {"include"}, (
        f"预期只差 include 一个，实际 {sorted(ghosts)}——多出来的说明基线没把基础设施带全，或者框架又补了别的"
    )
    assert recipe_ids <= tree_ids, f"配方里有、树上没有的：{sorted(recipe_ids - tree_ids)}"
