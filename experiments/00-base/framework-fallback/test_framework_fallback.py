"""framework-fallback · 兜底补 timer/hmr：判服务不判条目，而且关不掉

档次 ① ｜ 性质 🔬 ｜ 状态 ⚠️ 部分（结构性判定待验，见下） ｜ 1 条用例 ｜ 不需要 web

## 判定

- **判据是服务在不在，不是条目写没写。** 源码（`@deepseek-ai/dsh` 的
  `lib/profile-boot-*.js`，`boot()` 返回之后、`watchUserPatches()` 之前）：

  ```js
  if (ctx.get("hmr") === void 0) {
    if (ctx.get("timer") === void 0) await ctx.loader.create({ name: "@deepseek-ai/cordis-plugin-timer" })
    await ctx.loader.create({ name: "@deepseek-ai/cordis-plugin-hmr", config: { root: [] } })
  }
  ```

  查的是 `ctx.get("hmr")`（hmr **服务**），不是「有没有一个 id 叫 hmr 的条目」。
  **待验**——用例 `test_neither_declared_gets_both_supplied_at_root`。
- **补的条目落在根组、id 随机，跟 patch 文件写出来的条目形态不同。**
  `ctx.loader.create()` 不传 `id` 时走 `EntryTree.ensureId()`
  （`cordis-plugin-loader/src/config/tree.ts:66-69`），落到
  `Math.random().toString(16).slice(2, 10)`；`create()` 的 `parent` 参数默认
  `null`，落在根组、跟 `include` 平级（对照 `baseline-profile`：patch 文件写出
  的条目全在 `include` 子树里）。**待验**，同一用例。
- **没有配置开关能关掉它。** 整段逻辑无条件执行，判据只有 `ctx.get("hmr")`
  这一个条件，没有任何可以传参禁用的分支。**这一条本项没有用例覆盖**——
  从源码读到「没有分支」这件事本身就难以用一次实测直接证伪，只能算源码引用。

## 观测方法

`fixtures/base-census` 同 `minimal-profile`/`baseline-profile`：直接读
`loader.entries()`，拍两张快照。本项的 patch 里**完全不提** timer/hmr，
只挂普查员自己——这是触发兜底的前提，用例开头会先断言 patch 内容里确实没有
这两个包名。

## 没覆盖到的

⚠️ **这条机制在项目历史上一直只有源码引用支撑，没有配套用例**：
`l00_minimal_environment`、`l07_recipe_vs_tree` 两处 README 都明确写「本实验台
的用例不覆盖它」，`make_minimal_profile()` 甚至特意显式声明 timer/hmr 用来
**避开**触发它。搬迁取材表把本项列为有来源，但那两处来源实际只是对这条机制的
**叙述**（docstring/README 里的历史记录），不是可断言的用例本体。

本项的 `test_neither_declared_gets_both_supplied_at_root` 是这条判定第一次配上
可跑的验证，基于对源码的精确定位（含具体调用点与随机 id 生成逻辑）编写，但
**搬迁过程中没有条件实跑确认**（纪律禁止跑 pytest）。状态标"部分"，判定标"待验"，
而不是直接标"已验"——留给下一次真正跑这一组时坐实或推翻。「没有开关能关掉」
这一句目前只是源码引用，没有对应断言，也没有编造用例去凑。
"""

from __future__ import annotations

import json
from pathlib import Path

from lab import LabHome


def census_patch(out: Path, *, delay_ms: int = 3000) -> str:
    """只挂普查员一条，**完全不提 timer/hmr**——这是触发兜底的前提。"""
    return f"""# 完全不声明 timer/hmr，只有普查员自己
- insert:
    - id: census
      name: base-census
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
        under = f"  ⊂{e['parent']}" if e.get("parent") else "  （根组）"
        print(f"    · id={e['id']!s:<16} {e['name']!s:<32} {state}{under}")


def test_neither_declared_gets_both_supplied_at_root(lab_home: LabHome, fixtures_dir: Path, launch):
    """patch 里一个字都不提 timer/hmr：框架在 boot() 返回之后补一份，落在根组、id 随机。

    只做结构性断言（存在、跟 include 平级、id 不是我们熟悉的 'timer'/'hmr'）——
    不断言 fiber 是否已经 ACTIVE，避免把「创建」和「激活时机」这两件事混成一次
    可能随机失败的断言。
    """
    census_out = lab_home.root / "census-fallback.json"
    profile = lab_home.make_profile("no-infra", bundles=[], patch=census_patch(census_out))
    profile.link_plugin("base-census", fixtures_dir / "base-census")

    for pkg in ("@deepseek-ai/cordis-plugin-timer", "@deepseek-ai/cordis-plugin-hmr"):
        assert pkg not in profile.read_patch(), f"前提被破坏：{pkg} 不该出现在 patch 里"

    inst = launch(profile, wait_http=False)
    settle = inst.wait_for(lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照")
    show_entries(settle, "完全没声明 timer/hmr 时的树")

    assert inst.alive(), f"实例应当活着，却退了：\n{inst.logs()}"

    entries = settle["entries"]
    timer_e = next((e for e in entries if (e["name"] or "").endswith("cordis-plugin-timer")), None)
    hmr_e = next((e for e in entries if (e["name"] or "").endswith("cordis-plugin-hmr")), None)

    assert timer_e is not None, f"框架应当补一个 timer，实际条目：{[e['name'] for e in entries]}"
    assert hmr_e is not None, f"框架应当补一个 hmr，实际条目：{[e['name'] for e in entries]}"
    print(f"\n补的 timer：id={timer_e['id']} state={timer_e['fiberState']}")
    print(f"补的 hmr：  id={hmr_e['id']} state={hmr_e['fiberState']}")

    assert timer_e["parent"] is None, f"补的 timer 应当落在根组、跟 include 平级，实际 ⊂{timer_e['parent']}"
    assert hmr_e["parent"] is None, f"补的 hmr 应当落在根组、跟 include 平级，实际 ⊂{hmr_e['parent']}"
    assert timer_e["id"] != "timer", "补的 id 应当是随机字符串，不是我们自己惯用的 'timer'"
    assert hmr_e["id"] != "hmr", "补的 id 应当是随机字符串，不是我们自己惯用的 'hmr'"
