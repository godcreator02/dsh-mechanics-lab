"""layer-stack · 四层 patch 怎么叠出生效配置

档次 ① ｜ 性质 📗 复述型 ｜ 状态 ✅ 已验 ｜ 8 条用例 ｜ 不需要 web

⚠️ **标题「四层」是文档层面的说法，源码层面实际是五层——第五层见「## 没覆盖到的」，
本项零用例覆盖它。** 判定小节里的「四层」判词本身没错（对照的就是官方文档那四条），
但不要拿它当「配方总共几层」的答案。

## 判定

- **四层顺序：bundle → profile 活层 → home 层 → `--patch` overlay，逐层组合在空根之上，同 id 一层
  比一层新。** `docs/official/zh/user/develop/basic/publish.md:112-119`——

      生效配置在空根之上按以下顺序逐层组合：
      1. profile 的 `dsh.profile.bundles` 列表所列的各个组合包 patch，按列表顺序
      2. profile 自己的 `cordis.patch.yml`
      3. home 级的 `$DSH_HOME/cordis.patch.yml`——各 profile 共享的机器本地偏好
      4. 每个 `--patch <path>` overlay，按 argv 顺序

  `docs/official/zh/architecture.md:27` 独立表述、措辞不同、意思一致，互相印证。
  `test_four_layers_identifiable` / `test_same_id_layers_precedence` 已实测坐实
- **home 层文件不存在，等价于「没有这层」，正常启动。** 源码 `loadOptionalPatches` 遇 ENOENT 返回
  `undefined`。`test_home_layer_missing_equals_no_layer` 已实测
- **home 层内容非法（顶层不是数组）fail loud，报错文本固定。** ⚠️ 出处是源码 JSDoc
  （`dsh-app-boot/lib/index.js:786-787` 一带），不是文档正文，引用时不能写成「文档说」。
  `test_home_layer_illegal_content_fails_loud` 已实测
- **`--patch` 多个 overlay 按 argv 顺序、后者胜出。** 与 `publish.md:112-119` 第 4 条一致。
  `test_overlay_order_by_argv` 已实测
- **运行期改 `--patch` overlay 文件，热重放拾不拾得到——这条判定归 `04-replay/cold-surfaces`，
  不在本项重复。**
- **home 层写一次，对该 home 下每个 profile 同时生效；两处写不同 id 时两条并存、各收各的 config。**
  `test_the_other_place_works_the_same` / `test_the_home_place_hits_every_profile` /
  `test_two_places_two_entries` 已实测

## 观测方法

四层怎么叠是配方层面的事——`--dump-config` 秒级返回，不用起进程，比拉一个真实例便宜得多。八个用例里
只有两类必须拉真进程：`test_home_layer_missing_equals_no_layer`（dump 不报错证明不了「能正常启动、
能活着」）、以及 home 层对多 profile 生效的那组三条（config 内容不是 dump 能替代的，条目自己报出来
的内容才是判据）。

**独立 home 的必要性**：本项的实验对象就是 home 级 patch 文件——那一层对本 home 下所有 profile 同时
生效。`lab_home` fixture 本身是模块级独立 home，但同一个模块内的多个用例仍然共享同一个 home，所以
模块内另加了一个 `_clean_home_patch` autouse fixture：每个用例跑完自动清掉 home 层，防止一个用例
留下的 home patch 泄漏进下一个用例。

`DumpResult.source_of()` 只认「紧邻上方那一行来源注释」——dump 输出的 `# ==` 来源注释按连续同源的
条目块标一次，不是每条都标。测来源的条目都摆在各自 patch 文件的第一条，同块里的后续条目（`shared` /
`order-test`）只用 `config_of()` 判定，不测它们的 `source_of()`。

## 没覆盖到的

- **⚠️ 待验 · 框架自己还叠第五层内置 overlay，优先级压过 `--patch`，本项零用例覆盖。**
  源码坐实：`dsh` 包没有 `src/`，读的是 `<npx 缓存>/node_modules/@deepseek-ai/dsh/lib/
  profile-boot-*.js` 里的 `composeProfile()`（约 166-198 行）。`allPatches()`
  （约 146-154 行）拼最终栈用的是 `[...bundlePatches, ...profile.patches, ...homePatches,
  ...composed.overlays]`——最后这个 `overlays` 不是 argv `--patch` 原始列表本身，是
  `composeProfile()` 里另算出来的 `composedOverlays`：先复制一份 argv overlay，再在
  它*后面*追加框架自己的两条内置补丁（第 178-190 行）。追加在后就是优先级更高，
  所以这两条能压过 `--patch`、home、profile、bundle 全部四层，包括同 id 覆盖。
  两条各有前置条件，不是无条件生效：
  - `agent-presets` 补丁（179-188 行）只在四层组合出的 `rows`（不含内置补丁自己）
    里已经存在 `id: agent-presets` 的条目时才追加，内容是把 `config.roots` 强制
    合入 `{ path: SHIPPED_PRESET_ROOT, trust: "system" }`（`SHIPPED_PRESET_ROOT` 是
    随安装分发、`profile-boot` 模块同级的 `config/agent-presets/` 目录，86 行），
    其余原有 config 保留
  - telemetry 补丁（189-190 行，`resolveTelemetryPatch` 120-125 行）只在 `rows` 里
    已存在 `id: session-telemetry-otel` 的条目、**且** `process.env.DSH_TELEMETRY_DISABLED`
    非空字符串时才追加，固定内容 `{ id: "session-telemetry-otel", disabled: true }`——
    任意非空值（含 `'0'`）都算禁用，源码注释原话「a privacy switch prefers
    off-by-mistake over on-by-mistake」
  **「四层」这句话本身站不住**：官方文档 `publish.md:112-119` 只写了四层，那是文档的
  简化，不是全部——源码里货真价实叠了五层，第五层不受任何 patch 文件控制、只受「组合树
  里有没有对应 id 的条目」和「环境变量」驱动。本项目至今没有用例验证过「已有
  `agent-presets` 条目时它的 `roots` 真被强制改写」或「`DSH_TELEMETRY_DISABLED` 真能盖过
  已声明的 `disabled: false`」，这条只是源码读到、没有实测坐实，标 ⚠️ 待验，不进「## 判定」。
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from lab import (
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabError,
    LabHome,
    LabProfile,
    dump_config,
    entry_ids,
    read_events,
    reports,
    timeline,
)

BUNDLE_NAME = "l04-bundle-a"
OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
REPORTER = Path(__file__).resolve().parent / "fixtures" / "reporter.mjs"


# ── 辅助 ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_home_patch(lab_home: LabHome):
    """每个用例跑完自动清掉 home 层活层——它是本项的实验对象，泄漏到下一个
    用例会很难查。
    """
    yield
    lab_home.clear_home_patch()


def make_layer_profile(lab_home: LabHome, fixtures_dir: Path, name: str, *, profile_patch: str = "") -> LabProfile:
    """建一个叠了 `l04-bundle-a` 的 profile——四层里的「第 1 层」由它提供。"""
    profile = lab_home.make_profile(name, bundles=[BUNDLE_NAME], patch=profile_patch)
    profile.link_plugin(BUNDLE_NAME, fixtures_dir / BUNDLE_NAME)
    return profile


def same_path(actual: str | None, expected: Path) -> bool:
    """路径比较走 `Path.resolve()`，不直接比字符串——dump 输出里的路径分隔符
    未必跟我们自己拼的 `Path` 对象一致。
    """
    return actual is not None and Path(actual).resolve() == expected.resolve()


# ── 用例：四层来源与优先级 ───────────────────────────────────────────────────


def test_four_layers_identifiable(lab_home: LabHome, fixtures_dir: Path):
    """四层各插一条互不重名的标记条目，`--dump-config` 的来源注释应该能认出
    每一条各自来自哪一层——对应官方原文第 1～4 条。
    """
    profile = make_layer_profile(
        lab_home,
        fixtures_dir,
        "identify",
        profile_patch="""# 第 2 层：profile 自己的活层
- insert:
    - id: from-profile
      name: l04-bundle-a
      config:
        layer: profile
""",
    )
    lab_home.write_home_patch("""# 第 3 层：home 级活层
- insert:
    - id: from-home
      name: l04-bundle-a
      config:
        layer: home
""")
    overlay = lab_home.root / "overlay-identify.yml"
    overlay.write_text(
        """# 第 4 层：--patch overlay
- insert:
    - id: from-overlay
      name: l04-bundle-a
      config:
        layer: overlay
""",
        encoding="utf-8",
    )

    dumped = dump_config(lab_home, profile.name, patch_files=(overlay,))

    print(f"\n组合树共 {len(dumped.entries)} 个条目：{dumped.ids()}")
    expect_ids = ["from-bundle", "from-profile", "from-home", "from-overlay"]
    for entry_id in expect_ids:
        print(f"  {entry_id:<14} 来源 = {dumped.source_of(entry_id)}")
        assert entry_id in dumped.ids(), f"{entry_id} 应当出现在组合树里"

    assert dumped.source_of("from-bundle") == BUNDLE_NAME, "第 1 层（bundle 层）的来源应当是包名"
    assert same_path(dumped.source_of("from-profile"), profile.patch_path), (
        "第 2 层（profile 活层）的来源应当是它自己 cordis.patch.yml 的绝对路径"
    )
    assert same_path(dumped.source_of("from-home"), lab_home.patch_path), (
        "第 3 层（home 层）的来源应当是 home 级 cordis.patch.yml 的绝对路径"
    )
    assert same_path(dumped.source_of("from-overlay"), overlay), "第 4 层（overlay）的来源应当是 --patch 指向的文件路径"
    print("\n  → 四层各自的来源与文档描述一致：包名 / profile 活层路径 / home 层路径 / overlay 路径")


def test_same_id_layers_precedence(lab_home: LabHome, fixtures_dir: Path):
    """同一个 id 在四层各出现一次、值不同——不只测终点（overlay 胜出），
    每加一层都要跟着变一次，才算真的验证了「层级」而不是只验证了「结果」。

    官方原文 `:123`：「后应用的层按行胜出」。id 用 `shared`：bundle 层的
    `cordis.patch.yml` 已经用 `- insert:` 建出它（见
    `fixtures/l04-bundle-a/cordis.patch.yml`）；profile / home / overlay
    三层各用裸 `- id:` 覆盖语义顶掉它——覆盖语义本身是 `override-semantics`
    项的判定，这里只是借用它把「层级」这件事本身做得看得见。
    """
    profile = make_layer_profile(lab_home, fixtures_dir, "precedence")

    dumped = dump_config(lab_home, profile.name)
    print(f"\n只有 bundle 层：shared.config = {dumped.config_of('shared')}")
    assert dumped.config_of("shared").get("layer") == "bundle"

    profile.write_patch("""# 第 2 层覆盖 shared
- id: shared
  name: l04-bundle-a
  config:
    layer: profile
""")
    dumped = dump_config(lab_home, profile.name)
    print(f"叠上 profile 层后：shared.config = {dumped.config_of('shared')}")
    assert dumped.config_of("shared").get("layer") == "profile"

    lab_home.write_home_patch("""# 第 3 层覆盖 shared
- id: shared
  name: l04-bundle-a
  config:
    layer: home
""")
    dumped = dump_config(lab_home, profile.name)
    print(f"再叠上 home 层后：shared.config = {dumped.config_of('shared')}")
    assert dumped.config_of("shared").get("layer") == "home"

    overlay = lab_home.root / "overlay-precedence.yml"
    overlay.write_text(
        """# 第 4 层覆盖 shared
- id: shared
  name: l04-bundle-a
  config:
    layer: overlay
""",
        encoding="utf-8",
    )
    dumped = dump_config(lab_home, profile.name, patch_files=(overlay,))
    print(f"最后叠上 overlay 层：shared.config = {dumped.config_of('shared')}")
    assert dumped.config_of("shared").get("layer") == "overlay"

    print("\n  → 四层叠加顺序与文档一致：bundle → profile → home → overlay，一层比一层新")


def test_home_layer_missing_equals_no_layer(lab_home: LabHome, fixtures_dir: Path, launch):
    """home 层文件不存在，等价于「没有这层」——不是错误。

    源码依据：`loadOptionalPatches`（home 层用的那个函数）遇 ENOENT 返回
    `undefined`，等价于「没有这层」。文档没有直接写「文件不存在会怎样」，但
    「各 profile 共享的机器本地偏好」这句表述本身暗示它是可选的——这条用官方
    措辞的语气推出来，值得实测坐实。

    光是 `dump_config` 不报错还不够严谨——那只能证明「静态组合没崩」，证明不了
    「能启动、能活着」。所以这个用例还要真的拉起一次实例。
    """
    lab_home.clear_home_patch()
    assert not lab_home.patch_path.exists(), "前提：home 层文件确实不存在"

    profile = make_layer_profile(lab_home, fixtures_dir, "missing-home")

    dumped = dump_config(lab_home, profile.name)
    print(f"\nhome 层文件不存在时，dump-config 正常返回，{len(dumped.entries)} 个条目：{dumped.ids()}")
    assert "from-bundle" in dumped.ids()

    inst = launch(profile, wait_http=False)
    time.sleep(5.0)
    alive = inst.alive()
    print(f"拉起后 5 秒，进程还活着？ {alive}")
    if not alive:
        print(inst.logs())
    assert alive, "home 层缺文件不该导致启动失败"


def test_home_layer_illegal_content_fails_loud(lab_home: LabHome, fixtures_dir: Path):
    """home 层内容非法（顶层不是数组）时必须 fail loud，不能静默降级。

    ⚠️ 这句承诺出自源码 JSDoc（`dsh-app-boot/lib/index.js:786-787` 一带，实测
    报错栈里的行号随打包版本可能有出入，但报错**文本**是钉死的），不是文档
    正文——引用时不能写成「文档说」。用 `dump_config` 就能撞到这条检查，不用
    真的拉实例（这条校验在 patch 解析阶段就抛，跟要不要启动无关）。
    """
    lab_home.write_home_patch("foo: bar\n")  # 顶层是 mapping，不是数组

    profile = make_layer_profile(lab_home, fixtures_dir, "illegal-home")

    with pytest.raises(LabError) as exc_info:
        dump_config(lab_home, profile.name)

    message = str(exc_info.value)
    print(f"\n报错信息：\n{message}")
    assert "must be a top-level YAML array of loader patch entries" in message, (
        "预期的 fail-loud 提示没出现——要么措辞变了，要么校验条件变了，都是重大发现"
    )


def test_overlay_order_by_argv(lab_home: LabHome, fixtures_dir: Path):
    """`--patch` overlay 按 argv 顺序叠加，后写的顶掉先写的——官方原文第 4 条。

    用 bundle 层已经建好的 `order-test` 条目当靶子，两份 overlay 各用裸
    `- id:` 覆盖语义改它的 `config`，交换两次调用的顺序，值应当跟着翻过来。
    """
    profile = make_layer_profile(lab_home, fixtures_dir, "overlay-order")

    overlay_a = lab_home.root / "overlay-a.yml"
    overlay_a.write_text(
        """- id: order-test
  name: l04-bundle-a
  config:
    which: a
""",
        encoding="utf-8",
    )
    overlay_b = lab_home.root / "overlay-b.yml"
    overlay_b.write_text(
        """- id: order-test
  name: l04-bundle-a
  config:
    which: b
""",
        encoding="utf-8",
    )

    dumped_ab = dump_config(lab_home, profile.name, patch_files=(overlay_a, overlay_b))
    which_ab = dumped_ab.config_of("order-test").get("which")
    print(f"\n--patch a b → order-test.config.which = {which_ab!r}")

    dumped_ba = dump_config(lab_home, profile.name, patch_files=(overlay_b, overlay_a))
    which_ba = dumped_ba.config_of("order-test").get("which")
    print(f"--patch b a → order-test.config.which = {which_ba!r}")

    assert which_ab == "b", "a b 顺序下，后写的 b 应当胜出"
    assert which_ba == "a", "b a 顺序下，后写的 a 应当胜出"
    print("  → 与文档一致：--patch 多个时按 argv 顺序，后者胜出")


# ── 用例：home 层对整个 home 生效 ────────────────────────────────────────────

#: 每个 profile 立起来的三条基础设施：timer / hmr / 观察器
_INFRA = """- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
"""


def build_reporter_profile(lab_home: LabHome, name: str, *, profile_extra: str = "") -> tuple[LabProfile, Path]:
    """搭一个 profile：基础设施三条 +（可选）写在 profile 层的条目。

    home 层由各用例自己写（`lab_home.write_home_patch`），因为它不属于任何一个
    profile——那正是这组用例要验的事。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = _INFRA.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    profile = lab_home.make_profile(name, bundles=[], patch=patch + profile_extra)
    profile.link_plugin("lab-recorder", OBSERVER)
    # 插件文件拷进 profile 目录。home 层写的条目也用 `./reporter.mjs` 找它——
    # `name` 是相对**这个 profile 的目录**去找的，跟条目写在哪一层无关
    shutil.copy2(REPORTER, profile.dir / "reporter.mjs")
    return profile, events


def wait_said(inst: Instance, path: Path, who: str, *, timeout: float = 40.0) -> list[dict]:
    """等某个条目把自己收到的 config 报出来。等的是它自己的上报，不是事件
    总数——那才是这组用例的判据。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        said = reports(read_events(path), who=who)
        if said:
            return said
        if not inst.alive():
            break
        time.sleep(0.3)
    return reports(read_events(path), who=who)


def got_config(said: list[dict], who: str) -> dict | None:
    assert said, f"{who} 没说话——它的 apply 可能压根没跑"
    return said[0]["data"]["内容"]


def test_the_other_place_works_the_same(lab_home: LabHome, launch):
    """条目写在 home 层，跟写在 profile 层一样好使——profile 层一个字都没多写，
    条目照样挂上、`apply` 照样跑、`config` 照样送到。
    """
    profile, events_path = build_reporter_profile(lab_home, "home-side")
    lab_home.write_home_patch("""# home 层：$DSH_HOME/cordis.patch.yml
- insert:
    - id: in-home
      name: ./reporter.mjs
      config:
        出处: home 层
""")

    inst = launch(profile, wait_http=False)
    said = wait_said(inst, events_path, "in-home")

    print("\n══ 条目写在 home 层 ══════════════════════════════════════")
    print(f"  文件：{lab_home.patch_path}")
    print("  profile 层写了什么：只有 timer / hmr / 观察器——没有 in-home")
    print(timeline(read_events(events_path), kinds=("report",)))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "in-home" in entry_ids(read_events(events_path)), "home 层写的条目应当出现在树上"
    assert got_config(said, "in-home") == {"出处": "home 层"}


def test_the_home_place_hits_every_profile(lab_home: LabHome, launch):
    """home 层写一次，这个 home 下每个 profile 都吃到——这是它被叫做「一层」
    的原因：它不属于任何一个 profile。两个 profile 各自跑一个实例、各自有
    自己的观察器、自己的事件流，但两边都能看到同一条，而且收到的 `config`
    是同一份。
    """
    lab_home.write_home_patch("""- insert:
    - id: in-home
      name: ./reporter.mjs
      config:
        出处: home 层
""")
    first, first_events = build_reporter_profile(lab_home, "twin-a")
    second, second_events = build_reporter_profile(lab_home, "twin-b")

    inst_a = launch(first, wait_http=False)
    inst_b = launch(second, wait_http=False)
    said_a = wait_said(inst_a, first_events, "in-home")
    said_b = wait_said(inst_b, second_events, "in-home")

    print("\n══ home 层写一次，两个 profile 都吃到 ═════════════════════")
    print(f"  profile {first.name} 收到：{got_config(said_a, 'in-home')}")
    print(f"  profile {second.name} 收到：{got_config(said_b, 'in-home')}")

    assert inst_a.alive() and inst_b.alive(), f"两个实例都该活着：\n{inst_a.logs()}\n{inst_b.logs()}"
    assert got_config(said_a, "in-home") == {"出处": "home 层"}
    assert got_config(said_b, "in-home") == {"出处": "home 层"}


def test_two_places_two_entries(lab_home: LabHome, launch):
    """两处各写一条、`id` 不同——两条都在，各收各的。两层是拼在一起的，不是
    二选一：profile 层写的不会因为 home 层也写了东西就消失。
    """
    profile, events_path = build_reporter_profile(
        lab_home,
        "both-sides",
        profile_extra="""
- insert:
    - id: in-profile
      name: ./reporter.mjs
      config:
        出处: profile 层
""",
    )
    lab_home.write_home_patch("""- insert:
    - id: in-home
      name: ./reporter.mjs
      config:
        出处: home 层
""")

    inst = launch(profile, wait_http=False)
    said_profile = wait_said(inst, events_path, "in-profile")
    said_home = wait_said(inst, events_path, "in-home")

    print("\n══ 两处各写一条 ══════════════════════════════════════════")
    print(timeline(read_events(events_path), kinds=("report",)))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got_config(said_profile, "in-profile") == {"出处": "profile 层"}
    assert got_config(said_home, "in-home") == {"出处": "home 层"}
