"""duplicate-id-timing · 同一个 id 被两处同时 insert，三种撞法一堵墙、两个时机两种下场

档次 ③ ｜ 性质 🔬 发现型 ｜ 状态 ✅ 已验 ｜ 用例 4 条 ｜ 不需要 web

本组最值钱的一组对照：同一个错误（两处 patch 用同一个 `id` `insert` 同一批
条目），查重发生在同一个函数里，但**触发这次查重的时机不同，下场完全不同**。

## 判定

- **查重的位置：`cordis-plugin-loader` 的 `EntryGroup.update()`，循环在
  `try` 块之外。**

  ```js
  for (const options of config) {
    const id = this.tree.ensureId(options)
    if (seen.has(id)) throw new TypeError(`duplicate loader entry id: ${id}`)
    seen.add(id)
  }
  ```

  `applyEntryPatches`（`cordis-plugin-include`）本身不去重——它只在
  `insert` 时往索引里登记，从不检查冲突。所以静态 dump 能看到两条同 id
  的条目原样存在（`test_duplicate_id_within_one_layer_kills_boot` 先验证
  这一点：2 条，不是 1 条）。冲突留到 `EntryGroup.update()` 才现形，
  **抛错时一个 `create()` 都没调用过**——不是「先挂后回滚」，是「整批
  提前拒绝」。

- **撞车有三种形态，共同判定是同一条：boot 期查重发生在创建任何条目之前，
  整个进程死掉，这跟「哪两处 patch 文件」无关。**

  - 同一层内两次 `insert`——同一份活层 patch，两个 `insert` 块。证据：
    `test_duplicate_id_within_one_layer_kills_boot`。
  - 跨层撞车——bundle 层（包自带的 `cordis.patch.yml`） + 活层。证据：
    `test_duplicate_id_across_bundle_and_live_layer_kills_boot`。
  - 跨处撞车——活层内部两处不同的 patch 文件：profile 那份（管这一个
    profile） + home 那份（`$DSH_HOME/cordis.patch.yml`，管这个 home 下
    每一个 profile）。证据：
    `test_duplicate_id_across_profile_and_home_layer_kills_boot`。

  三种写法触发同一段查重循环、同一句判词 `duplicate loader entry id: <id>`、
  同一个退出码 1——查重不管撞车的两边来自哪一层、哪一处文件，只看合成数组
  里 id 有没有重复。

- **boot 期：致命，整个进程退出。** 这段查重循环是首次 `EntryGroup.update()`
  的一部分（挂载 `include` 子树时，`Group` 的 `Service.init` 里
  `await this.update(this.config)`）。抛错之后 `assertEntriesActivated`
  自然通不过，`boot()` 直接失败，整棵树被 `ctx.fiber.dispose()` 回滚，
  进程以退出码 1 退出。这不是「回滚」，是那次 `update` 从未成功过。

- **运行期：被兜住，实例继续健康。** 同样是 `EntryGroup.update()`，但这次
  是热重放触发的那次调用，被 `refreshConfig` 的 try/catch 兜着：记两条
  warn、发一个 `hmr/config-update-failed` 事件，**不回滚也不退出**。
  原条目的状态序列停在 `['LOADING', 'ACTIVE']`，连 `DISPOSED` 都没有——
  整次更新回滚，原条目毫发无损。撞完之后再改一次代码，照样热重载。
  证据：`test_duplicate_id_added_while_running_is_rolled_back`。

- **为什么下场不同：boot 期没有「上一个好状态」可退。** 运行期撞车时，
  实例手上有一份挂载完好的旧树，失败的配置更新可以整体作废、退回那份
  旧树；boot 期第一次挂载就撞车，没有旧树可退，只能让整个 `boot()`
  失败，进程退出。**「致不致命」这个问题必须先问「什么时候」。**

## 观测方法

- **致命判定不能靠 `except LabError`**——`start_instance(wait_http=False)`
  立即返回、不做存活检查。用固定等待（15 秒）之后看 `inst.alive()`。
- **验证不该发生的事用固定长等待，不能轮询提前退出**——运行期那条用例
  验「实例不该被拖垮」，`Instance.settle(15.0)` 之后才读事件流。
- 运行期的判定要看**状态序列有没有 `DISPOSED`**，而不是只看「进程活着」
  ——进程活着不代表这次更新没伤到旧条目，`states_of(events, "greeter")`
  给的是直接证据。
- **撞完之后还得验健康**：只验「进程没死」不够，一次失败的配置更新如果
  让代码热重载这条路悄悄坏掉，那比直接退出还糟——所以撞车之后接着改
  一次代码，看它还认不认。
- **跨处撞车**同样只能用固定长等待（15 秒）判「起不来」，跟另两种形态的
  判定手法一致；home 层的 patch 写完必须在用例结束时清掉——`lab_home`
  是模块级夹具，home 层对整个 home 生效，留着会串进同模块下一条用例。

## 旧实现的取舍

`duplicate-id-timing` 的 boot 侧曾经散在五份独立实现（`l05`、`l06`、
`ch2_bundle_vs_live`、`step7`、`step8`）。按「同一层内撞车」「跨层撞车」
「跨处撞车」三种形态归了三类，各选一份：

- **同一层内两次 `insert`** → 选 `l05` 的
  `test_duplicate_id_at_boot_is_fatal`。唯一带着「查重在 `try` 块之外、
  抛错时一个 `create()` 都没调用过」这条机制解释、并且先用静态 dump
  证明「两条都原样进了合成数组」再验挂载期致命——两段证据链完整。
  `step8` 的 `test_inserting_the_same_id_twice` 是同一场景的更薄实现
  （没有静态 dump 那一半），判定强度更弱。
- **跨层撞车（bundle 层 + 活层）** → 选 `ch2_bundle_vs_live` 的
  `test_same_id_in_both_layers_will_not_start`。跟 `l06` 的
  `test_duplicate_id_across_bundle_and_live_layer_kills_boot` 是同一个
  判定，但 `l06` 需要叠 `dsh-base + dsh-web-app`（`BUNDLE_WEB`），启动
  慢一大截；`ch2_bundle_vs_live` 版本不需要 web bundle，判定强度相同、
  开销小得多。
- **跨处撞车（profile 层 patch + home 层 patch）** → 选 `step7` 的
  `test_same_id_in_both_places_will_not_start`。原判在
  `step7_more_than_one_place`（讲「配置不止一处」的那一课），后来裁定
  它验的其实是撞车的第三种形态——boot 期查重不管撞车的两边来自哪两处
  patch 文件，跟前两种形态共享同一次判定，归进本组。

运行期那一侧只有一份实现：`chx_hmr_across_junction` 的 ⑪
（`test_duplicate_id_added_while_running`），原样搬入，改成
`test_duplicate_id_added_while_running_is_rolled_back`。

## 没覆盖到的

- 三层同时撞同一个 id（bundle 层 + profile 活层 + home 活层）没有实验
  覆盖——现有证据只覆盖两层两两组合。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lab import (  # noqa: E402
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    dump_config,
    of_kind,
    read_events,
    reports,
    states_of,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 「验证不该发生的事」用的固定等待——不能轮询提前退出，那只能证明
#: 「此刻还没发生」，证明不了「不会发生」。
SETTLE = 15.0


def _watch_alive(inst: Instance, seconds: float) -> dict:
    deadline = time.monotonic() + seconds
    died_at = None
    while time.monotonic() < deadline:
        if not inst.alive():
            died_at = round(seconds - (deadline - time.monotonic()), 2)
            break
        time.sleep(0.25)
    return {"alive": inst.alive(), "died_at": died_at, "exit_code": inst.proc.returncode, "logs": inst.logs(tail=60)}


# ── boot 期 · 同一层内两次 insert 同一个 id ─────────────────────────────────


def test_duplicate_id_within_one_layer_kills_boot(lab_home: LabHome, launch):
    """两个独立的 `- insert:` 块（都不带 id，都追加进根组），块里的条目 id
    相同——静态 dump 应当能看到两条同 id 的条目（`applyEntryPatches` 不去重），
    冲突要挂载才现形：boot 期查重命中，进程直接死掉。
    """
    w1 = lab_home.root / "w-dup-1.json"
    w2 = lab_home.root / "w-dup-2.json"
    profile = lab_home.make_minimal_profile(
        "dup-one-layer",
        patch=f"""# 用例 1：同一层内，两个 insert 块用了同一个 id
- insert:
    - id: dup
      name: lab-patch
      config:
        witness: {json.dumps(w1.as_posix())}
- insert:
    - id: dup
      name: lab-patch
      config:
        witness: {json.dumps(w2.as_posix())}
""",
    )
    profile.link_plugin("lab-patch", FIXTURES / "lab-patch")

    dump = dump_config(lab_home, profile.name)
    dup_entries = [e for e in dump.entries if isinstance(e, dict) and e.get("id") == "dup"]
    print(f"\n  静态 dump 里 id=dup 的条目数：{len(dup_entries)}（预期 2——applyEntryPatches 不去重）")
    assert len(dup_entries) == 2, "两个 insert 块都该原样进了组合数组——冲突要留到挂载期才现形"

    inst = launch(profile, wait_http=False)
    got = _watch_alive(inst, seconds=15.0)

    print(f"\n  进程还活着？ {got['alive']}（退出码 {got['exit_code']}，死于 +{got['died_at']}s）")
    hit = [ln for ln in got["logs"].splitlines() if "duplicate loader entry id" in ln]
    print(f"  日志里的判词：{hit or '（没找到，看完整日志）'}")
    if not hit:
        print(got["logs"])

    assert not got["alive"], "boot 期撞见同 id 双挂载应当致命——进程不该活下来"
    assert not w1.exists() and not w2.exists(), "查重在创建任何条目之前，两条都不该 apply 过"
    assert hit, f"预期日志里有 'duplicate loader entry id'：\n{got['logs']}"


# ── boot 期 · bundle 层与活层撞同一个 id ────────────────────────────────────


def test_duplicate_id_across_bundle_and_live_layer_kills_boot(lab_home: LabHome, launch):
    """撞车的两边一边在包里（bundle 层的 `cordis.patch.yml`）、一边在你手上
    （活层）——同一堵墙，只是这次两边来路不同。查重不管条目来自哪一层，
    合成数组里出现同 id 就死。
    """
    profile = lab_home.make_profile(
        "dup-cross-layer",
        bundles=["ch2-greeter"],
        patch="""# 用例 2：活层也 insert 一个同 id 的条目——跟 bundle 层的那个撞车
- insert:
    - id: greeter
      name: ch2-greeter
      config:
        版本: 活层写的
""",
    )
    profile.link_plugin("ch2-greeter", FIXTURES / "ch2-greeter")
    profile.link_plugin("lab-recorder", OBSERVER)

    inst = launch(profile, wait_http=False)
    got = _watch_alive(inst, seconds=15.0)

    print(f"\n  进程还活着？ {got['alive']}（退出码 {got['exit_code']}，死于 +{got['died_at']}s）")
    hit = [ln for ln in got["logs"].splitlines() if "duplicate loader entry id" in ln]
    print(f"  日志里的判词：{hit or '（没找到，看完整日志）'}")
    if not hit:
        print(got["logs"])

    assert not got["alive"], "bundle 层与活层撞同一个 id，boot 期同样致命"
    assert any("greeter" in ln for ln in hit), f"判词该点名撞车的那个 id：{hit}"


# ── boot 期 · 活层内部两处 patch 文件（profile 层 / home 层）撞同一个 id ────


def test_duplicate_id_across_profile_and_home_layer_kills_boot(lab_home: LabHome, launch):
    """撞车的第三种形态：两边都在活层，只是分属两处不同的 patch 文件——
    profile 那份只管这一个 profile，home 那份（`$DSH_HOME/cordis.patch.yml`）
    管这个 home 下的每一个 profile。两处拼起来是两个条目，不是一个被另一个
    改掉，id 撞了照样致命——跟前两种形态共享同一次判定：查重不管撞车的两边
    来自哪一层、哪一处文件。

    home 层是模块级夹具、对整个假 home 生效，用完必须清掉，否则会串进
    同模块下一条用例——`finally` 里 `clear_home_patch()` 保证这一点。
    """
    w_profile = lab_home.root / "w-profile-place.json"
    w_home = lab_home.root / "w-home-place.json"
    try:
        profile = lab_home.make_minimal_profile(
            "dup-cross-place",
            patch=f"""# 用例 3：profile 那处写了一个 id=dup 的条目
- insert:
    - id: dup
      name: lab-patch
      config:
        witness: {json.dumps(w_profile.as_posix())}
""",
        )
        profile.link_plugin("lab-patch", FIXTURES / "lab-patch")
        lab_home.write_home_patch(f"""# home 那处（$DSH_HOME/cordis.patch.yml）写了同一个 id
- insert:
    - id: dup
      name: lab-patch
      config:
        witness: {json.dumps(w_home.as_posix())}
""")

        inst = launch(profile, wait_http=False)
        got = _watch_alive(inst, seconds=15.0)

        print(f"\n  进程还活着？ {got['alive']}（退出码 {got['exit_code']}，死于 +{got['died_at']}s）")
        hit = [ln for ln in got["logs"].splitlines() if "duplicate loader entry id" in ln]
        print(f"  日志里的判词：{hit or '（没找到，看完整日志）'}")
        if not hit:
            print(got["logs"])

        assert not got["alive"], "profile 层与 home 层撞同一个 id，boot 期同样致命"
        assert not w_profile.exists() and not w_home.exists(), "查重在创建任何条目之前，两条都不该 apply 过"
        assert hit, f"预期日志里有 'duplicate loader entry id'：\n{got['logs']}"
        assert any("dup" in ln for ln in hit), f"判词该点名撞车的那个 id：{hit}"
    finally:
        lab_home.clear_home_patch()


# ── 运行期 · 同 id 是运行中才加进去的 ───────────────────────────────────────


def _build_bundle_nested(lab_home: LabHome, name: str) -> tuple[LabProfile, Path, Path]:
    """把 hmr-linked 包拷进 `<profile>/src/hmr-linked`（落在 `root: ['.']`
    范围内，不用扩 hmr 的 watch root），bundle 名单里挂它，条目由包自己那份
    patch 生。返回 (profile, events 路径, index.js 路径)。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    profile_dir = lab_home.root / "profiles" / name
    pkg_dir = profile_dir / "src" / "hmr-linked"
    pkg_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURES / "hmr-linked", pkg_dir)

    patch = f"""- insert:
    - id: timer
      name: '{PKG_TIMER}'

    - id: hmr
      name: '{PKG_HMR}'
      config:
        root: ['.']
        debounce: 100

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {json.dumps(events.as_posix())}
        flushMs: 100
"""
    profile = lab_home.make_profile(name, bundles=["hmr-linked"], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    profile.link_plugin("hmr-linked", pkg_dir)
    return profile, events, pkg_dir / "index.js"


def test_duplicate_id_added_while_running_is_rolled_back(lab_home: LabHome, launch):
    """进程已经起来了，这时往活层加一条跟 bundle 层同 id 的——走的是完全
    不同的一条路（配置路径，被 `refreshConfig` 的 try/catch 兜着）：不回滚
    也不退出，只是这一次更新整体作废。

    三件事要验：进程还活着吗、原来那个条目遭殃了吗、撞完之后这个实例还
    健康吗（代码热重载还能不能用）——最后一条最要紧，一次失败的配置更新
    如果让整棵树处于半死状态，那比直接退出还糟。
    """
    profile, events_path, index_js = _build_bundle_nested(lab_home, "dup-while-running")

    inst = launch(profile, wait_http=False)
    inst.wait_for(lambda: reports(read_events(events_path), who="greeter"), timeout=40.0, what="greeter 报第一版")
    time.sleep(1.0)

    # ── 运行时往活层追加一条同 id 的 ────────────────────────────────────────
    profile.write_patch(
        profile.read_patch()
        + """
- insert:
    - id: greeter
      name: hmr-linked
      config:
        版本: 活层撞车
"""
    )
    Instance.settle(SETTLE)

    mid = read_events(events_path)
    failed = of_kind(mid, "hmr-failed")
    reported = [e["data"].get("版本") for e in reports(mid, who="greeter")]

    print("\n══ 运行中往活层加一条同 id 的 ═══════════════════════════")
    print(f"  进程还活着？　　{inst.alive()}")
    print(f"  hmr-failed 事件：{len(failed)} 条")
    for e in failed:
        print(f"    {Path(str(e.get('filename'))).name} → {e.get('error')}")
    print(f"  greeter 报过的版本：{reported}")
    print(f"  它走过的状态：{states_of(mid, 'greeter')}")

    assert inst.alive(), f"配置更新失败不该拖垮进程：\n{inst.logs()}"
    assert failed, "该发一个 hmr/config-update-failed 事件"
    assert any("duplicate" in str(e.get("error", "")).lower() for e in failed), (
        f"判词该点名 id 重复，实际 {[e.get('error') for e in failed]}"
    )
    assert reported == ["代码第一版"], "原来那条不该被换成活层撞车那份 config"
    assert "DISPOSED" not in states_of(mid, "greeter"), "整次更新应当回滚，原来那条不该被拆掉"

    # ── 撞完之后，这个实例还健康吗：改代码看还认不认 ────────────────────────
    text = index_js.read_text(encoding="utf-8")
    assert "代码第一版" in text, "前提：index.js 里本来写着代码第一版"
    index_js.write_text(text.replace("代码第一版", "代码第二版"), encoding="utf-8")

    inst.wait_for(
        lambda: len(reports(read_events(events_path), who="greeter")) >= 2, timeout=25.0, what="greeter 重新报出第二版"
    )

    after = read_events(events_path)
    reported_after = [e["data"].get("版本") for e in reports(after, who="greeter")]
    print("\n══ 撞车之后再改一次代码 ══════════════════════════════════")
    print(f"  greeter 报过的版本：{reported_after}")

    assert inst.alive(), f"实例应当仍然活着：\n{inst.logs()}"
    assert reported_after == ["代码第一版", "代码第二版"], (
        f"一次失败的配置更新不该弄坏代码热重载，实际 {reported_after}"
    )
