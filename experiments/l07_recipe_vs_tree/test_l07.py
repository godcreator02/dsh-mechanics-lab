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

from lab import PKG_HMR, PKG_TIMER, Instance, LabHome, LabProfile


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


# ── ② 兜底判服务不判条目，关不掉 ─────────────────────────────────────────────


def test_fallback_creates_even_when_disabled(lab_home: LabHome, fixtures_dir: Path, launch):
    """② 方向 A：写进活层再 disabled——服务仍然是 undefined，框架照样另造一份。

    L0 已经把这条钉死了（`l00_minimal_environment/test_l00.py::test_infra_cannot_be_opted_out`），
    这里在 L7 自己的环境里复核一次：跨课重复是特性，本课的结论不依赖去读 L0 的产出。
    """
    census_out = lab_home.root / "census-fallback-disabled.json"
    profile = lab_home.make_minimal_profile(
        "fallback-disabled",
        patch=census_patch(
            census_out,
            extra="""
    - id: my-hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      disabled: true
""",
        ),
    )
    profile.link_plugin("l07-census", fixtures_dir / "l07-census")

    inst = launch(profile, wait_http=False)
    settle = inst.wait_for(
        lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照"
    )
    show_entries(settle, "禁用之后")

    hmr_entries = [e for e in settle["entries"] if (e["name"] or "").endswith("plugin-hmr")]
    print(f"\n  hmr 条目：{[(e['id'], e['disabled']) for e in hmr_entries]}")
    assert len(hmr_entries) == 2, f"禁用不该关掉服务，框架应该另造一份，实际 {hmr_entries}"
    live = [e for e in hmr_entries if not e["disabled"]]
    assert len(live) == 1, "应该恰好有一个没被禁用的（框架补的那份）"
    assert settle["services"]["hmr"], "hmr 服务应当照样在"


def test_fallback_skips_when_own_hmr_active(lab_home: LabHome, fixtures_dir: Path, launch):
    """② 方向 B：自己挂一个**激活**的 hmr（不禁用）——服务已经在了，框架不再补。

    对照 A：唯一的差别是这次没有 `disabled: true`。落点完全相反，
    印证兜底判的确实是 `ctx.get("hmr") === void 0`（服务），不是「条目存不存在」。
    """
    census_out = lab_home.root / "census-fallback-active.json"
    profile = lab_home.make_minimal_profile(
        "fallback-active",
        patch=census_patch(
            census_out,
            extra=f"""
    - id: my-timer
      name: '{PKG_TIMER}'

    - id: my-hmr
      name: '{PKG_HMR}'
      config:
        root: []
""",
        ),
    )
    profile.link_plugin("l07-census", fixtures_dir / "l07-census")

    inst = launch(profile, wait_http=False)
    settle = inst.wait_for(
        lambda: phase(read_census(census_out), "settle"), timeout=20.0, what="settle 快照"
    )
    show_entries(settle, "自带激活的 hmr")

    hmr_entries = [e for e in settle["entries"] if (e["name"] or "").endswith("plugin-hmr")]
    print(f"\n  hmr 条目：{[e['id'] for e in hmr_entries]}")
    assert len(hmr_entries) == 1, f"服务已经在了，框架不该再补，实际 {hmr_entries}"
    assert hmr_entries[0]["id"] == "my-hmr"


# ── ③ 幽灵条目 id 不稳定，只能认 name ────────────────────────────────────────


def test_ghost_ids_differ_names_stable(lab_home: LabHome, fixtures_dir: Path, launch):
    """③ 幽灵条目的 id 每次启动都不一样，只能认 name 不能认 id。

    源码依据：兜底那两句 `ctx.loader.create({ name: … })` **没传 id**——id 由
    loader 自动生成。跑两个完全独立的最小 profile（配方一模一样，只有名字不同），
    各自读一次 settle 快照，比对兜底补的 timer/hmr：id 应该不同，
    name（包名后缀）应该一样。这是后面所有课写断言时的硬约束。
    """
    runs: dict[str, dict[str, str]] = {}
    for label in ("ghosta", "ghostb"):
        out = lab_home.root / f"census-ghost-{label}.json"
        profile = lab_home.make_minimal_profile(label, patch=census_patch(out))
        profile.link_plugin("l07-census", fixtures_dir / "l07-census")
        inst = launch(profile, wait_http=False)
        settle = inst.wait_for(
            lambda o=out: phase(read_census(o), "settle"), timeout=20.0, what="settle 快照"
        )
        show_entries(settle, f"{label} 的 settle 快照")
        runs[label] = ghost_entries(settle)
        print(f"\n  {label} 的幽灵条目：{runs[label]}")

    for pkg in ("plugin-timer", "plugin-hmr"):
        id_a, id_b = runs["ghosta"].get(pkg), runs["ghostb"].get(pkg)
        assert id_a and id_b, f"两次启动都应该有 {pkg} 的幽灵条目"
        assert id_a != id_b, f"{pkg} 的幽灵条目 id 应该每次都不一样，两次却都是 {id_a}"
    print("\n  → id 不稳定，只能认 name（包名后缀）")


# ── ④ 未坐实的观察：兜底会不会触发一次整树刷新 ──────────────────────────────


def test_ghost_creation_does_not_lose_settle_snapshot(lab_home: LabHome, fixtures_dir: Path, launch):
    """④ L0 记下但没坐实的一个观察：兜底创建 timer/hmr 会不会触发一次整树刷新，
    把普查员自己重挂了、导致 settle 快照被覆盖？

    **L0 的假说**：`loader.create()` 会 `tree.write()`，而那正是 include 的
    `config.path`（`cordis.yml`），于是触发一次整树刷新。

    **本课多读了一层源码**（`cordis-plugin-loader/src/index.ts`），假说的因果链
    在源头上就不成立：

        export class Loader extends EntryTree {
          …
          write() {
            // Loader's root tree is in-memory; writes are no-ops.
          }
        }

        export class Include extends EntryTree {
          …
          write() {
            this.context.emit('loader/config-update')
            return this.writeFile(this.root.data)   // 只有这里真的落盘
          }
        }

    兜底的 `ctx.loader.create()` 落在**根**这棵树（`Loader` 自己）上——timer/hmr
    跟 include 平级，L0 已经验过——而根树的 `write()` 明确是空操作、注释原文
    写着 "Loader's root tree is in-memory; writes are no-ops."。只有 `Include`
    自己的树（对应某个 `cordis:include` 条目的子树）落盘时才会真的 `writeFile`。
    兜底创建 timer/hmr 压根碰不到磁盘文件，所谓「写回 cordis.yml 触发整树刷新」
    这条因果链源头上就断了。

    这一跑仍然去实测——源码分析可能漏看了别的路径，而且这条判定的分量
    值得多一次交叉验证。用 l07-census 的 `applyIndex`/多条 record 数组
    直接看「普查员在观察窗口内被 apply 了几次」。**测出来是它就是发现，
    测不出来就如实记录「未复现」，不硬凑。**
    """
    census_out = lab_home.root / "census-refresh.json"
    profile = lab_home.make_minimal_profile(
        "refresh", patch=census_patch(census_out, delay_ms=800, delay_ms2=6000)
    )
    profile.link_plugin("l07-census", fixtures_dir / "l07-census")

    inst = launch(profile, wait_http=False)
    settle2 = inst.wait_for(
        lambda: phase(read_census(census_out), "settle2"), timeout=20.0, what="settle2 快照"
    )
    census = read_census(census_out)
    n = applies(census)
    print(f"\n  普查员在观察窗口内被 apply 了 {n} 次")
    for i, record in enumerate(census or []):
        phases_seen = [s["phase"] for s in record.get("snapshots", [])]
        print(f"    record[{i}]：applyIndex={record.get('applyIndex')}，拍到的快照={phases_seen}")

    if n > 1:
        print(
            "\n  → 复现了！被重挂过——这是一个真正的发现，"
            "跟源码读出来的判断相反，要在 README 里正面记下、同步 DRAFT.md。"
        )
    else:
        print(
            "\n  → 未复现（跟 L0 两次复跑的结果一致）。结合上面的源码证据，"
            "现在有理由认为不是『还没抓到』，是『这条因果链本身大概率不存在』——"
            "L0 那次 settle 丢失更可能是旧版工具自己的缺陷（record 建在 apply 里、"
            "被覆盖），不是框架触发了整树刷新。"
        )

    # 不对 n 的具体值做强断言——这一课的任务是如实记录，不是硬凑绿灯。
    assert census is not None, "普查员至少应该被加载一次"
    assert n >= 1, "至少应该有一条 apply 记录"
    assert phase(census, "boot") is not None, "boot 快照应该拿得到"
    assert settle2 is not None, "settle2 快照应该拿得到"
