"""L7 · 配方 ≠ 树：`include` 与幽灵条目

L0 已经立住「运行时的树比配方多三个条目」这件事，本课把它展开成四件事：

  ① `include` 不只是一个条目——整个配方装在它的 `config.patches` 里。
     由此推出「配方热重放」在实现上就是「改 include 这一个条目的 config」，
     这是 L14 的地基，必须在这里坐实。
  ② 兜底判的是「服务」不是「条目」，而且关不掉。L0 已经验过，本课在自己的
     环境里复核一次（跨课重复是特性，见 CLAUDE.md）。
  ③ 幽灵条目的 id 每次启动都不一样，只能认 name 不能认 id——后面所有课
     写断言的硬约束。
  ④ L0 记下但没坐实的一个观察：兜底创建 timer/hmr 会不会触发一次整树刷新、
     把普查员自己重挂了？测出来是它就是发现，测不出来就如实记录「未复现」。

全部不需要 web，观测手段是 `fixtures/l07-census`——从 L0 的普查员拷来改造，
多了两件事：能读 `include` 条目自己的 `config.patches`（摘要形式，见 fixture
里的注释），以及一张可选的第三快照（`settle2`），用来在没有 web 服务的情况下
验证「活层文件改了之后，配方跟着变没变」。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab import PKG_HMR, PKG_TIMER, Instance, LabHome, LabProfile, dump_config


# ── 辅助 ────────────────────────────────────────────────────────────────────


def census_patch(
    out: Path,
    *,
    delay_ms: int = 2000,
    delay_ms2: int | None = None,
    extra: str = "",
) -> str:
    """只挂一个普查员的活层。extra 原样追加（同一个 insert 列表里的更多条目）。"""
    lines = [
        "# L7 活层",
        "- insert:",
        "    - id: census",
        "      name: l07-census",
        "      config:",
        f"        out: {json.dumps(out.as_posix())}",
        f"        delayMs: {delay_ms}",
    ]
    if delay_ms2 is not None:
        lines.append(f"        delayMs2: {delay_ms2}")
    text = "\n".join(lines) + "\n"
    return text + extra if extra else text


def read_census(path: Path) -> list[dict] | None:
    """读普查文件：历次 apply 的记录列表（照抄 l00-census 的读法）。"""
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
    """取某一张快照，从最后一次 apply 往前找（照抄 l00-census）。"""
    if not census:
        return None
    for record in reversed(census):
        for snap in record.get("snapshots", []):
            if snap.get("phase") == name:
                return snap
    return None


def applies(census: list[dict] | None) -> int:
    return 0 if census is None else len(census)


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


def ghost_entries(snap: dict | None) -> dict[str, str]:
    """兜底补的 timer/hmr：`{包名后缀: id}`。只认根组（parent is None）的那些——
    L0 已验：兜底的 timer/hmr 跟 include 平级，不在它的子树里。
    """
    if snap is None or snap.get("entries") is None:
        return {}
    out: dict[str, str] = {}
    for e in snap["entries"]:
        name = e.get("name") or ""
        if e.get("parent") is not None:
            continue
        for pkg in ("plugin-timer", "plugin-hmr"):
            if name.endswith(pkg):
                out[pkg] = e.get("id")
    return out


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
    """建一个「profile 层 + home 层各埋一个可辨认标记」的 profile，① 的两个用例共用。"""
    lab_home.write_home_patch(
        """# L7 home 层标记
- insert:
    - id: home-marker
      name: l07-marker-home
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
      name: l07-marker-profile
      disabled: true
{profile_markers}""",
        ),
    )
    profile.link_plugin("l07-census", fixtures_dir / "l07-census")
    return profile


# ── ① include 持有完整配方 ──────────────────────────────────────────────────


def test_include_config_holds_full_recipe(lab_home: LabHome, fixtures_dir: Path, launch):
    """①-静态：profile 活层 + home 层各埋一个标记，两个都要出现在 include 的
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
    settle = inst.wait_for(
        lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照"
    )
    show_entries(settle, "settle：静态构成")

    inc = find_entry(settle, name="cordis:include")
    assert inc is not None, "树里应该有 cordis:include 条目"
    assert inc["includePatches"]["present"], "include 条目应该有 config.patches"

    ids = include_patch_ids(settle)
    print(f"\n  include.config.patches 里的 id：{ids}")
    for expect in ("census", "home-marker", "profile-marker"):
        assert expect in ids, f"{expect} 应该出现在 include 的 config.patches 里，实际 {ids}"


def test_recipe_hot_reload_updates_include_config(lab_home: LabHome, fixtures_dir: Path, launch):
    """①-动态：boot 之后活着改 profile 活层文件、多插一个标记，看第二张快照里
    `include` 的 `config.patches` 有没有跟着变。

    源码依据（`watchUserPatches` 的回调，`dsh-app-boot` `lib/index.js:766`）：

        const register = hmr.registerConfig(filename, async () => {
          const { patches: _previousPatches, ...includeConfig } = entry.options.config;
          const patches = compose(loadOptionalPatches(binName, filename) ?? []);
          await entry.update({ config: { ...includeConfig, patches } });
        });

    这就是「配方热重放」的实现：重新 compose 出 patches，然后**改 include 这一个
    条目的 config**。本课只坐实到「亲眼看见那个数组变了」——不追 fiber 状态
    （那是 L14 的事）。
    """
    census_out = lab_home.root / "census-recipe-hot.json"
    profile = _recipe_profile(
        lab_home, fixtures_dir, "recipe-hot", census_out, delay_ms=2000, delay_ms2=8000
    )

    inst = launch(profile, wait_http=False)
    settle = inst.wait_for(
        lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照"
    )
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
      name: l07-marker-profile
      disabled: true

    - id: profile-marker-2
      name: l07-marker-profile-2
      disabled: true
""",
        )
    )
    print("  活层文件已改动，多插了 profile-marker-2，等第二张快照…")

    settle2 = inst.wait_for(
        lambda: phase(read_census(census_out), "settle2"), timeout=20.0, what="settle2 快照"
    )
    show_entries(settle2, "settle2：改动之后")
    ids_after = include_patch_ids(settle2)
    print(f"\n  改动之后 include.config.patches 里的 id：{ids_after}")

    assert "profile-marker-2" in ids_after, (
        "活层文件改了之后，include 的 config.patches 应该跟着更新——"
        "这就是『配方热重放＝改 include 的 config』"
    )
    for expect in ("census", "home-marker", "profile-marker"):
        assert expect in ids_after, f"{expect} 改动之后不该消失，实际 {ids_after}"


# ── ③ include 是树上唯一不来自 patch 文件的 entry ────────────────────────────


def test_include_is_the_only_ghost(lab_home: LabHome, fixtures_dir: Path, launch):
    """基线显式带上 timer / hmr 之后，树上还剩几个 entry 是 patch 文件里没有的？

    **答案是一个：`cordis:include`。**

    这跟「差三个」那种形态的区别不只是数量。timer / hmr 之所以曾经也算 ghost，
    只是因为把 `dsh-base` 拿掉之后没人声明它们、框架的 fallback 补了上来——
    那是实验台减噪造出来的人工场景，真实部署里 base 的 patch 头两条就是它们。

    而 `include` 是**结构性**的：不管 config 怎么写它都在，因为**整份 effective
    config 就装在它的 `config.patches` 里**——它要是出现在自己装的那份 config 里，
    才是自指。所以「effective config ≠ entry tree」这条判定的干净形态就是它。
    """
    census_out = lab_home.root / "census-only-ghost.json"
    profile = lab_home.make_minimal_profile("only-ghost", patch=census_patch(census_out))
    profile.link_plugin("l07-census", fixtures_dir / "l07-census")

    dumped = dump_config(lab_home, profile.name)
    recipe_ids = {e.get("id") for e in dumped.entries if isinstance(e, dict)}
    print(f"\n  effective config 里的 id（{len(recipe_ids)} 个）：{sorted(recipe_ids)}")

    inst = launch(profile, wait_http=False)
    settle = inst.wait_for(
        lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照"
    )
    show_entries(settle, "entry tree")

    tree_ids = {e["id"] for e in settle["entries"]}
    ghosts = tree_ids - recipe_ids
    print(f"\n  树上有、config 里没有的 id：{sorted(ghosts)}")

    assert ghosts == {"include"}, (
        f"预期只剩 include 一个，实际 {sorted(ghosts)}——"
        "多出来的说明基线没把基础设施带全，或者框架又补了别的"
    )
    # 反过来也要成立：config 里的每一行都在树上找得到，没有谁被悄悄丢掉
    assert recipe_ids <= tree_ids, (
        f"config 里有、树上没有的：{sorted(recipe_ids - tree_ids)}"
    )
