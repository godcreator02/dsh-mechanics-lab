"""replay-mechanism · 配方热重放改的是哪一个条目

档次 ① ｜ 性质 🔬 ｜ 状态 ✅ ｜ 2 条用例 ｜ 不需要 web

## 判定

- **「配方」不是抽象说法，是 `cordis:include` 这一个条目自己持有的
  `config.patches` 数组。** 四层（bundle 层 / profile 活层 / home 层 /
  `--patch` overlay）拼接后的完整 patch 列表，boot 时原样塞进这一个条目的
  `config` 里。证据：`test_include_config_holds_full_recipe`，源码出处
  `dsh-app-boot` `lib/index.js` 的 `mountRootInclude()`：

      const rootInclude = {
        id: "include", name: "cordis:include",
        config: { path: …/cordis.yml, patches: [...patches] }
      }

  `patches` 就是四层拼接后的那份完整列表，原样塞进这一个条目的 config 里。
- **配方热重放 = 重新 compose 出 `patches`、`entry.update({config})` 改
  `include` 这一个条目的 config。** 没有「遍历整棵树逐个比对」发生在这一层。
  证据：`test_recipe_hot_reload_updates_include_config`，源码出处
  `watchUserPatches` 的回调，`dsh-app-boot` `lib/index.js:766`：

      const register = hmr.registerConfig(filename, async () => {
        const { patches: _previousPatches, ...includeConfig } = entry.options.config;
        const patches = compose(loadOptionalPatches(binName, filename) ?? []);
        await entry.update({ config: { ...includeConfig, patches } });
      });

## 观测方法

普查员（`fixtures/replay-recipe-census`）在每张快照里，如果当前条目恰好是
`cordis:include`，额外把它的 `config.patches` 摘出来——不整体
`JSON.stringify`（条目 `config` 里可能有 `!!js` 表达式，直接序列化容易失真甚至
抛错），只取「这条 patch 操作是 insert 还是 override、涉及哪些 id/name」的摘要，
足够拿来对账「配方里写的东西是不是真的出现在 `include` 身上」。

信号精确落在 `include` 这一个条目上：

- 用例一是静态对照——profile 活层与 home 层各埋一个标记，检查两个标记是否都
  出现在 `include.config.patches` 里
- 用例二是动态对照——boot 之后活着改 profile 活层文件，比较改动前后两张快照
  （`settle` / `settle2`）里 `include.config.patches` 的差异；`settle2` 是普查员
  提供的第三张可选快照，不用起 web 服务、纯靠 apply 内部的两个 `setTimeout`
  错开时间点，测试代码在两次快照之间去改活层文件

拿 `census` 这个无关条目的状态判断「重放发生没发生」是错的（它本来就不该被
重挂，得到恒真结果）——本项两条用例都只看 `include` 自己的字段，没有这个坑。

## 没覆盖到的

`include.config` 变了之后，`entry.update()` 会不会动到 fiber、条目级 diff
具体 diff 在哪一层、没被改动的条目会不会也跟着被摸一遍——本项只坐实到
「`include.config.patches` 这个数组变了」，没有正面验证 diff 算法本身。
同组 `replay-granularity`（⬜）是这条线索该继续挖的地方，见其模块 docstring。
"""

from __future__ import annotations

import json
from pathlib import Path

from lab import LabHome, LabProfile

# ── 辅助 ────────────────────────────────────────────────────────────────────


def census_patch(out: Path, *, delay_ms: int = 2000, delay_ms2: int | None = None, extra: str = "") -> str:
    """只挂一个普查员的活层。extra 原样追加（同一个 insert 列表里的更多条目）。"""
    lines = [
        "- insert:",
        "    - id: census",
        "      name: replay-recipe-census",
        "      config:",
        f"        out: {json.dumps(out.as_posix())}",
        f"        delayMs: {delay_ms}",
    ]
    if delay_ms2 is not None:
        lines.append(f"        delayMs2: {delay_ms2}")
    text = "\n".join(lines) + "\n"
    return text + extra if extra else text


def read_census(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
    """取某一张快照，从最后一次 apply 往前找。"""
    if not census:
        return None
    for record in reversed(census):
        for snap in record.get("snapshots", []):
            if snap.get("phase") == name:
                return snap
    return None


def find_entry(snap: dict | None, *, name: str | None = None, id_: str | None = None) -> dict | None:
    if snap is None or snap.get("entries") is None:
        return None
    for e in snap["entries"]:
        if name is not None and e.get("name") != name:
            continue
        if id_ is not None and e.get("id") != id_:
            continue
        return e
    return None


def include_patch_ids(snap: dict | None) -> list[str]:
    """把 include 条目 config.patches 摘要里所有操作涉及的 id/name 拍平成一份列表。"""
    inc = find_entry(snap, name="cordis:include")
    if inc is None:
        return []
    summary = (inc.get("includePatches") or {}).get("summary") or []
    ids: list[str] = []
    for op in summary:
        if op.get("op") == "insert":
            ids.extend(x for x in (op.get("ids") or []) if x)
        elif op.get("op") == "override" and op.get("id"):
            ids.append(op["id"])
    return ids


def show_entries(snap: dict | None, title: str) -> None:
    print(f"\n  ── {title} ──")
    if snap is None:
        print("    （没有这张快照）")
        return
    on = [k for k, v in snap["services"].items() if v]
    print(f"    服务：{', '.join(on) if on else '（一个都没有）'}")
    entries = snap.get("entries")
    if entries is None:
        print("    条目：拿不到 loader")
        return
    for e in entries:
        state = "无 fiber" if not e["hasFiber"] else f"state={e['fiberState']}"
        flag = " [disabled]" if e["disabled"] else ""
        under = f"  ⊂{e['parent']}" if e.get("parent") else ""
        print(f"    · id={e['id']!s:<16} {e['name']!s:<32} {state}{flag}{under}")
        inc = e.get("includePatches")
        if inc is not None:
            print(f"        config.patches：present={inc['present']} count={inc['count']}")
            for op in inc.get("summary") or []:
                print(f"          - {op}")


def _recipe_profile(
    lab_home: LabHome,
    fixtures_dir: Path,
    name: str,
    out: Path,
    *,
    delay_ms: int = 2000,
    delay_ms2: int | None = None,
    profile_markers: str = "",
) -> LabProfile:
    """建一个「profile 层 + home 层各埋一个可辨认标记」的 profile，两条用例共用。"""
    lab_home.write_home_patch(
        """- insert:
    - id: home-marker
      name: replay-marker-home
      disabled: true
"""
    )
    profile = lab_home.make_minimal_profile(
        name,
        patch=census_patch(
            out,
            delay_ms=delay_ms,
            delay_ms2=delay_ms2,
            extra=f"""
    - id: profile-marker
      name: replay-marker-profile
      disabled: true
{profile_markers}""",
        ),
    )
    profile.link_plugin("replay-recipe-census", fixtures_dir / "replay-recipe-census")
    return profile


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_include_config_holds_full_recipe(lab_home: LabHome, fixtures_dir: Path, launch):
    """profile 活层 + home 层各埋一个标记，两个都要出现在 `include` 的
    `config.patches` 里——证明「配方」不是抽象说法，是这个条目实实在在持有的数据。

    源码依据（`dsh-app-boot` `mountRootInclude()`）：

        const rootInclude = {
          id: "include", name: "cordis:include",
          config: { path: …/cordis.yml, patches: [...patches] }
        }

    `patches` 就是四层（bundle 层 / profile 活层 / home 层 / overlay）拼接后的
    那份完整列表，原样塞进这一个条目的 config 里。
    """
    census_out = lab_home.root / "census-recipe-static.json"
    profile = _recipe_profile(lab_home, fixtures_dir, "recipe-static", census_out)

    inst = launch(profile, wait_http=False)
    settle = inst.wait_for(lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照")
    show_entries(settle, "settle：静态构成")

    inc = find_entry(settle, name="cordis:include")
    assert inc is not None, "树里应该有 cordis:include 条目"
    assert inc["includePatches"]["present"], "include 条目应该有 config.patches"

    ids = include_patch_ids(settle)
    print(f"\n  include.config.patches 里的 id：{ids}")
    for expect in ("census", "home-marker", "profile-marker"):
        assert expect in ids, f"{expect} 应该出现在 include 的 config.patches 里，实际 {ids}"


def test_recipe_hot_reload_updates_include_config(lab_home: LabHome, fixtures_dir: Path, launch):
    """boot 之后活着改 profile 活层文件、多插一个标记，看第二张快照里 `include`
    的 `config.patches` 有没有跟着变。

    源码依据（`watchUserPatches` 的回调，`dsh-app-boot` `lib/index.js:766`）：

        const register = hmr.registerConfig(filename, async () => {
          const { patches: _previousPatches, ...includeConfig } = entry.options.config;
          const patches = compose(loadOptionalPatches(binName, filename) ?? []);
          await entry.update({ config: { ...includeConfig, patches } });
        });

    这就是「配方热重放」的实现：重新 compose 出 patches，然后**改 include 这一个
    条目的 config**。本用例只坐实到「亲眼看见那个数组变了」——不追 fiber 状态
    （fiber 动没动、条目级 diff diff 在哪一层，是 `replay-granularity` 的问题）。
    """
    census_out = lab_home.root / "census-recipe-hot.json"
    profile = _recipe_profile(lab_home, fixtures_dir, "recipe-hot", census_out, delay_ms=2000, delay_ms2=8000)

    inst = launch(profile, wait_http=False)
    settle = inst.wait_for(lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照")
    ids_before = include_patch_ids(settle)
    print(f"\n  改动前 include.config.patches 里的 id：{ids_before}")
    assert "profile-marker-2" not in ids_before, "前提：改动前不该有这个标记"

    # 活着改 profile 活层：多插一个标记
    profile.write_patch(
        census_patch(
            census_out,
            delay_ms=2000,
            delay_ms2=8000,
            extra="""
    - id: profile-marker
      name: replay-marker-profile
      disabled: true

    - id: profile-marker-2
      name: replay-marker-profile-2
      disabled: true
""",
        )
    )
    print("  活层文件已改动，多插了 profile-marker-2，等第二张快照…")

    settle2 = inst.wait_for(lambda: phase(read_census(census_out), "settle2"), timeout=20.0, what="settle2 快照")
    show_entries(settle2, "settle2：改动之后")
    ids_after = include_patch_ids(settle2)
    print(f"\n  改动之后 include.config.patches 里的 id：{ids_after}")

    assert "profile-marker-2" in ids_after, (
        "活层文件改了之后，include 的 config.patches 应该跟着更新——这就是『配方热重放＝改 include 的 config』"
    )
    for expect in ("census", "home-marker", "profile-marker"):
        assert expect in ids_after, f"{expect} 改动之后不该消失，实际 {ids_after}"
