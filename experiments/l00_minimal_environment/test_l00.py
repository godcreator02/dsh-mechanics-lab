"""L0 · 最小可运行环境 —— 一个 DSH 实例最少需要什么才能跑起来。

这一课是**探路**：后面每一课都要拉实例，而「拉起来的到底是什么」如果没先钉死，
所有观测都建立在一堆没验过的假设上。L1–L3 用的基线是 `dsh-base`（78 个条目、
一整套 AI 助手），其中跟插件系统本身有关的只有两个。剩下 76 个是噪声：
拖慢启动，还往事件流里灌几百条与被测对象无关的事件。

要回答七个问题：

  1. profile 最少需要哪几个文件？`cordis.yml` 要不要自己建？
  2. 配方能不能是空的？空树能不能启动？
  3. 谁保持进程活着？
  4. 运行时的树跟配方一样吗？—— 本课最要紧的一问
  5. 框架的兜底什么时候触发？
  6. boot 期停在 PENDING 的条目，是不是一律致命？
  7. 条目的 `name` 以哪里为锚解析？插件包必须 link 进 profile 吗？

写法上全部是**观察型**：先跑、先打印看到了什么，再做保守断言。
L3 吃过反过来做的亏 —— 先按「应该失败」写死断言，结果它没失败，
三个用例白写，而真正发生的事一个字都没记下来。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from lab import BUNDLE_BASE, Instance, LabHome, dump_config

#: 拉起后观察多久。框架的兜底条目是 boot() **返回之后**才补的，
#: 普查员的 settle 快照又要再延后一截，留足余量。
OBSERVE = 6.0

#: 普查员延后拍第二张快照的间隔
CENSUS_DELAY_MS = 2000


# ── 辅助 ────────────────────────────────────────────────────────────────────


def census_patch(out: Path, *, delay_ms: int = CENSUS_DELAY_MS, extra: str = "") -> str:
    """只挂一个普查员的活层。extra 原样追加，用来叠别的条目。"""
    return f"""# L0 活层
- insert:
    - id: census
      name: l00-census
      config:
        out: {json.dumps(out.as_posix())}
        delayMs: {delay_ms}
{extra}"""


def watch(inst: Instance, seconds: float = OBSERVE) -> dict:
    """看着实例跑一段时间，把观察到的事实收集成一份记录。

    不做任何断言 —— 这个函数只负责**如实描述**发生了什么，
    判断留给各个用例。启动失败在本课是完全正常的结果之一。
    """
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
        "logs": inst.logs(tail=30),
    }


def read_census(path: Path) -> list[dict] | None:
    """读普查文件。返回**历次 apply** 的记录列表。

    是列表而不是单条，因为条目会被重挂——普查员每挂一次往里加一条。
    列表长度本身就是个观测量：长度 > 1 说明这个条目在观察期内被重挂过。
    """
    if not path.exists():
        return None
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return got if isinstance(got, list) else None


def phase(census: list[dict] | None, name: str) -> dict | None:
    """取某一张快照，**从最后一次 apply 往前找**。

    为什么从后往前：重挂之后前一轮的快照就过时了，稳定态以最新的为准。
    往前兜底是因为最后一轮可能还没来得及拍 settle（观察窗口结束了），
    那时前一轮的 settle 仍然比什么都没有强——但它是**过时的**，
    所以调用方要靠 `apply 次数` 自己判断可信度。

    拿不到返回 None，让用例自己决定这算不算失败。
    """
    if not census:
        return None
    for record in reversed(census):
        for snap in record.get("snapshots", []):
            if snap.get("phase") == name:
                return snap
    return None


def applies(census: list[dict] | None) -> int:
    """普查员被 apply 了几次。> 1 就是被重挂过。"""
    return 0 if census is None else len(census)


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
    if not entries:
        print("    条目：（空树）")
    for e in entries:
        state = "无 fiber" if not e["hasFiber"] else f"state={e['fiberState']}"
        flag = " [disabled]" if e["disabled"] else ""
        # 缩进表示层级：根组的顶格，有父条目的往里缩一层
        indent = "    " if e.get("parent") else ""
        under = f"  ⊂{e['parent']}" if e.get("parent") else ""
        print(f"    · {indent}id={e['id']!s:<24} {e['name']!s:<42} {state}{flag}{under}")


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_profile_minimal_files(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 1：profile 最少需要哪几个文件？

    只写两个文件，**故意不建 `cordis.yml`**：
        package.json      —— bundles 名单
        cordis.patch.yml  —— 活层

    源码依据（`dsh/lib/profile-boot`）：`PROFILE_ROOT_CONFIG` 是一个常量字符串，
    内容是一句注释加一个 `[]`。它是「每棵 profile 树打补丁的那个空根」。
    如果框架每次启动都自己写这个文件，那它就不该由人来建 —— 更要紧的是，
    人建了也会被覆盖掉。
    """
    census_out = lab_home.root / "census-minimal.json"
    profile = lab_home.make_profile("minimal", bundles=[BUNDLE_BASE])
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.write_patch(census_patch(census_out))

    root_config = profile.dir / "cordis.yml"
    print(f"\n启动前 cordis.yml 存在？ {root_config.exists()}")
    assert not root_config.exists(), "前提：我们没建它"

    inst = launch(profile, wait_http=False)

    # 「验证**应该**发生的事」用轮询，不能用固定窗口——本用例第一版用 watch() 那个
    # 固定 6 秒，单跑时稳过，但全套跑到这里机器负载高、dsh 启动变慢，
    # 窗口到期时框架还没写完这个文件，用例就假失败了。
    # 这正是观测方法论第 4 条说的那种错：验「该发生」用轮询，验「不该发生」才用固定长等待。
    inst.wait_for(
        root_config.exists,
        timeout=45.0,
        what="框架建出空根 cordis.yml",
    )
    got = watch(inst, seconds=1.0)

    print("启动后 cordis.yml 存在？ True")
    print("  内容：")
    for line in root_config.read_text(encoding="utf-8").splitlines():
        print(f"    | {line}")
    print(f"进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")
    if not got["alive"]:
        print(got["logs"])
    assert root_config.read_text(encoding="utf-8").strip().endswith("[]"), (
        "空根的内容应当是一个空数组"
    )


def test_empty_bundles_boots(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 2：配方能不能是空的？

    `bundles: []` + 活层里只有普查员自己。没有 dsh-base，没有任何 DSH 业务插件。
    这一跑要么证明「DSH 的插件系统能脱离 DSH 的业务层独立运行」，
    要么证明「有什么东西是硬前提」—— 两个结果都有用。
    """
    census_out = lab_home.root / "census-empty.json"
    profile = lab_home.make_profile("empty", bundles=[])
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.write_patch(census_patch(census_out))

    dumped = dump_config(lab_home, profile.name)
    print(f"\n--dump-config 算出 {len(dumped.entries)} 个条目：")
    for e in dumped.entries:
        print(f"    · {e.get('id')} → {e.get('name')}")

    inst = launch(profile, wait_http=False)
    got = watch(inst)

    print(f"\n进程还活着？ {got['alive']}（退出码 {got['exit_code']}，死于 +{got['died_at']}s）")
    census = read_census(census_out)
    print(f"普查员写出见证文件了吗？ {census is not None}")
    show_entries(phase(census, "boot"), "boot 期快照")
    show_entries(phase(census, "settle"), "settle 快照")
    if not got["alive"]:
        print(f"\n{got['logs']}")

    assert census is not None, "空 bundles 下普查员都没被加载 —— 记下日志里的原因"


def test_ghost_entries(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 4（本课核心）：运行时的树跟配方一样吗？

    源码里 `profile-boot` 在 `boot()` 返回之后有这么一段：

        if (ctx.get("hmr") === void 0) {
          if (ctx.get("timer") === void 0) await ctx.loader.create({ name: "…timer" })
          await ctx.loader.create({ name: "…hmr", config: { root: [] } })
        }

    注意 `loader.create` **没传 id** —— id 由 loader 自动生成。这两个条目
    不在任何 patch 文件里，`--dump-config` 永远看不见它们。

    这一跑要验的判定是：**配方 ≠ 树**。
    静态 dump 是「配方算出来的样子」，跟进程里真正跑着的那棵树不是一回事。
    """
    census_out = lab_home.root / "census-ghost.json"
    profile = lab_home.make_profile("ghost", bundles=[])
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.write_patch(census_patch(census_out))

    dumped = dump_config(lab_home, profile.name)
    recipe_names = {e.get("name") for e in dumped.entries}
    print(f"\n配方里的条目（{len(recipe_names)} 个）：{sorted(n for n in recipe_names if n)}")

    inst = launch(profile, wait_http=False)
    watch(inst)

    census = read_census(census_out)
    boot_snap, settle_snap = phase(census, "boot"), phase(census, "settle")
    show_entries(boot_snap, "boot 期：boot() 还没返回")
    show_entries(settle_snap, "settle：boot() 返回之后")

    if settle_snap is None or settle_snap.get("entries") is None:
        pytest.skip("拿不到 settle 快照，本用例无从判断 —— 先看上面的输出")

    runtime_names = {e["name"] for e in settle_snap["entries"]}
    ghosts = sorted(n for n in runtime_names - recipe_names if n)
    print(f"\n  幽灵条目（树里有、配方里没有）：{ghosts or '（没有）'}")

    boot_ids = {e["id"] for e in (boot_snap or {}).get("entries") or []}
    settle_ids = {e["id"] for e in settle_snap["entries"]}
    print(f"  boot 之后新增的条目 id：{sorted(settle_ids - boot_ids)}")

    assert ghosts, (
        "预期框架会补 timer/hmr 两个条目进树。一个都没有的话，"
        "要么兜底没触发（看 settle 快照的服务表），要么普查员拍晚了"
    )


@pytest.mark.parametrize(
    "kind, entries",
    [
        ("显式禁用 hmr", """
    - id: my-hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      disabled: true
"""),
        ("连 timer 一起禁用", """
    - id: my-timer
      name: '@deepseek-ai/cordis-plugin-timer'
      disabled: true

    - id: my-hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      disabled: true
"""),
    ],
)
def test_infra_cannot_be_opted_out(
    lab_home: LabHome, fixtures_dir: Path, launch, kind: str, entries: str
):
    """能不能**真的不要** timer 和 hmr？

    「最小插件集合是空集」这句话容易被读成「树里可以没有插件」。不是那个意思——
    是**你要声明的集合**为空，树里从来不空。这一跑就是去撞那堵墙。

    最直接的尝试：把它们显式写进活层再 `disabled: true`。按 L0 已经立住的
    「兜底判服务不判条目」，禁用的条目不提供服务 → `ctx.get("hmr")` 仍是
    undefined → 框架照样补一个。也就是说**禁用不但没关掉它，还多造了一份**。

    两个变体的差别是「顺带把 timer 也禁掉」——用来确认兜底会不会连 timer
    一起补（源码里 timer 那句是嵌套在 hmr 判断里的，单独看不出来）。

    这条判定的分量：它意味着 DSH 实例**不存在「没有 hmr」的形态**。
    L13 要测的「patch 监听什么时候会死」，因此不可能是「hmr 不在」，
    只可能是「hmr 还在但 watcher 被清了」——两者的排查方向完全不同。
    """
    tag = "nohmr" if "timer" not in entries else "noinfra"
    census_out = lab_home.root / f"census-{tag}.json"
    profile = lab_home.make_profile(tag, bundles=[])
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.write_patch(census_patch(census_out, extra=entries))

    inst = launch(profile, wait_http=False)
    got = watch(inst)

    census = read_census(census_out)
    settle_snap = phase(census, "settle")
    show_entries(settle_snap, f"{kind} 之后的 settle 快照")
    print(f"\n  进程还活着？ {got['alive']}")
    print(f"  普查员被 apply 了 {applies(census)} 次"
          f"{'（被重挂过）' if applies(census) > 1 else ''}")
    if not got["alive"]:
        print(got["logs"])

    assert settle_snap is not None, f"{kind}：普查员没被加载\n{got['logs']}"
    rows = settle_snap["entries"]

    for pkg in ("plugin-timer", "plugin-hmr"):
        mine = [e for e in rows if (e["name"] or "").endswith(pkg)]
        live = [e for e in mine if not e["disabled"]]
        print(f"    {pkg}：共 {len(mine)} 条，其中没被禁用的 {len(live)} 条 "
              f"→ {[e['id'] for e in live]}")
        assert live, (
            f"{kind}：禁用之后 {pkg} 就真没了 —— 那说明兜底有本课没发现的前提条件"
        )

    assert settle_snap["services"]["hmr"], "hmr 服务应当照样在"
    assert settle_snap["services"]["timer"], "timer 服务应当照样在"
    print("  → 禁不掉。禁用只是让框架另造一份，服务照样在")


def test_hmr_fallback_condition(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 5：兜底的触发条件到底是什么？

    源码判的是 `ctx.get("hmr") === void 0` —— **服务**在不在，不是条目在不在。
    这个区别有后果：条目写了但没激活（比如 `disabled: true`），服务照样是
    undefined，框架会再造一个。

    对照组：自己挂一个货真价实的 hmr 条目（给它固定 id `my-hmr`）。
    如果它激活了，服务就在，兜底就不该触发 —— 树里应当**只有**这一个 hmr。
    """
    census_out = lab_home.root / "census-ownhmr.json"
    profile = lab_home.make_profile("ownhmr", bundles=[])
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.write_patch(census_patch(census_out, extra="""
    - id: my-timer
      name: '@deepseek-ai/cordis-plugin-timer'

    - id: my-hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      config:
        root: []
"""))

    inst = launch(profile, wait_http=False)
    got = watch(inst)

    census = read_census(census_out)
    settle_snap = phase(census, "settle")
    show_entries(settle_snap, "自带 timer + hmr 时的 settle 快照")
    if not got["alive"]:
        print(f"\n{got['logs']}")

    if settle_snap is None or settle_snap.get("entries") is None:
        pytest.skip("拿不到 settle 快照 —— 先看上面的输出")

    hmr_entries = [e for e in settle_snap["entries"] if (e["name"] or "").endswith("plugin-hmr")]
    print(f"\n  树里的 hmr 条目共 {len(hmr_entries)} 个：{[e['id'] for e in hmr_entries]}")
    print(f"  hmr 服务在不在：{settle_snap['services'].get('hmr')}")

    assert len(hmr_entries) == 1, (
        "自己挂的 hmr 激活后，框架不该再补一个。多于一个说明兜底判的不是服务，"
        "或者自己那个没激活成功"
    )


def test_bare_name_resolution(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 7：条目的 `name` 以哪里为锚解析？

    这直接决定 L1–L3 一直在做的那件事（`link_plugin` 把包 junction 进
    profile 的 node_modules）是不是必需的。

    源码里有两套锚点，且**用途不同**：
      * `ctx.baseUrl` = profile 目录（`boot()` 里设的），子树条目走这个
      * `bareModuleBaseUrl` = dsh 安装目录（profile-boot 传的 `INSTALL_ANCHOR`），
        注释说「when the host, rather than the configuration project, owns the
        complete plugin set」

    实验：挂一个 `@deepseek-ai/cordis-plugin-timer`，但**不** link 进 profile。
    它只存在于 dsh 的安装目录里。加载成功 = 裸包名以 host 为锚；
    加载失败 = 以 profile 为锚，我们的 link 是必需的。
    """
    census_out = lab_home.root / "census-bare.json"
    profile = lab_home.make_profile("bare", bundles=[])
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.write_patch(census_patch(census_out, extra="""
    - id: unlinked-timer
      name: '@deepseek-ai/cordis-plugin-timer'
"""))

    linked = profile.dir / "node_modules" / "@deepseek-ai" / "cordis-plugin-timer"
    print(f"\ntimer 有没有被 link 进 profile？ {linked.exists()}（预期 False）")

    inst = launch(profile, wait_http=False)
    got = watch(inst)

    census = read_census(census_out)
    settle_snap = phase(census, "settle")
    show_entries(settle_snap, "settle 快照")
    print(f"\n进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")

    entries = (settle_snap or {}).get("entries") or []
    timer_entry = next((e for e in entries if e["id"] == "unlinked-timer"), None)
    if timer_entry is None:
        print("  没 link 的 timer 条目：树里找不到 → 裸包名以 profile 为锚，link 是必需的")
        print(f"\n{got['logs']}")
    else:
        print(f"  没 link 的 timer 条目：{timer_entry}")
        print("  → 裸包名以 dsh 安装目录为锚，官方包不需要 link")


@pytest.mark.parametrize(
    "kind, suffix",
    [
        ("指向目录", ""),
        ("指向文件", "/index.js"),
    ],
)
def test_relative_name_resolution(
    lab_home: LabHome, fixtures_dir: Path, launch, kind: str, suffix: str
):
    """问题 7 的另一半：**相对路径**的 `name` 怎么解析？

    上一个用例证明了裸包名以 dsh 安装目录为锚 —— 那对官方包够用，
    但我们自己的教学插件不在那儿，只能靠 `link_plugin` 建 junction。
    如果 `./` 开头的路径名能直接指向 fixtures，link 那一步就能整个省掉。

    源码里两种名字走的是**两条不同的分支**（`cordis-plugin-loader` 的
    `EntryTree.import`）：

        name.startsWith(".")  →  import(new URL(name, ctx.baseUrl))   // URL 解析
        否则                   →  import(name)                          // 包解析

    这个区别有个不显然的后果，正是本用例要测的：**只有包解析认 package.json**。
    L1 验过包名的回退链（`exports["."]` → `main` → `index.js`），
    而相对路径走的是纯 URL 解析，压根不看 package.json —— 那条回退链不存在。

    所以同一个插件目录，写成包名能加载，写成相对路径可能就不行。
    参数化两种写法，让差异自己显出来。
    """
    label = "dir" if not suffix else "file"
    census_out = lab_home.root / f"census-rel-{label}.json"
    profile = lab_home.make_profile(f"rel{label}", bundles=[])
    # 故意**不** link —— 全靠相对路径找过去
    source = (fixtures_dir / "l00-census").resolve()
    # 假 home 和 fixtures 都在实验台里，必然同盘，relpath 一定算得出
    spec = "./" + Path(os.path.relpath(source, profile.dir.resolve())).as_posix() + suffix
    print(f"\n{kind}")
    print(f"  profile 在 {profile.dir}")
    print(f"  相对路径   {spec}")

    profile.write_patch(f"""# 相对路径引用
- insert:
    - id: census
      name: {json.dumps(spec)}
      config:
        out: {json.dumps(census_out.as_posix())}
        delayMs: {CENSUS_DELAY_MS}
""")

    linked = profile.dir / "node_modules" / "l00-census"
    print(f"  有没有 link？ {linked.exists()}（预期 False）")

    inst = launch(profile, wait_http=False)
    got = watch(inst)

    census = read_census(census_out)
    print(f"\n  普查员被加载了吗？ {census is not None}")
    print(f"  进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")

    if suffix:
        assert census is not None, f"指到文件应当能加载：\n{got['logs']}"
        print("  → 相对路径指到**文件**可用，link 不是必需的")
    else:
        assert census is None, "指到目录居然加载成功了 —— 那说明相对路径也走包解析"
        err = got["logs"]
        code = "ERR_UNSUPPORTED_DIR_IMPORT" in err
        print(f"  → 指到**目录**加载失败，报 ERR_UNSUPPORTED_DIR_IMPORT：{code}")
        assert code, f"失败了但不是预期的原因，看日志：\n{err}"


def test_who_keeps_process_alive(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 3：谁保持进程活着？

    Node 进程在事件循环空了之后就会退出。DSH 实例能一直跑着，一定有东西
    在占着事件循环。候选就那么几个：timer 的定时器、hmr 的文件 watcher、
    web 服务的监听套接字。

    本用例不预设答案，只做一件事：**把空树跑给它看**，看它活不活。
    活着 → 框架兜底补的 timer/hmr 就够撑住；
    死了 → 保活需要更多东西，那「最小集合」的定义就得往上加。
    """
    census_out = lab_home.root / "census-alive.json"
    profile = lab_home.make_profile("alive", bundles=[])
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.write_patch(census_patch(census_out, delay_ms=1000))

    inst = launch(profile, wait_http=False)
    # 比别的用例看得久：要排除「刚开始活着、过一会儿事件循环空了才退」
    got = watch(inst, seconds=15.0)

    print(f"\n看了 15 秒。进程还活着？ {got['alive']}")
    if not got["alive"]:
        print(f"  死于第 {got['died_at']} 秒，退出码 {got['exit_code']}")
        print(f"\n{got['logs']}")
    else:
        settle_snap = phase(read_census(census_out), "settle")
        show_entries(settle_snap, "还活着时树里有什么")


def test_baseline_profile(lab_home: LabHome, fixtures_dir: Path, launch):
    """把前面七问的结论固化成基线，然后验它 —— `make_minimal_profile()`。

    两种形态各起一次：

      默认      靠框架兜底的 timer+hmr。hmr 的 `root: []`，只够监听 patch
                文件，**代码文件不监听**。绝大多数课够用。
      hmr_root  自挂 timer+hmr 并给一个真的 watch root。服务提前就位，
                兜底不触发。要测代码热重载的课用这个。

    顺带验一件基础设施的事：活层是 YAML 数组，**允许多个 `- insert:` 块**。
    基线 API 靠这一点把自己的条目拼在调用方的 patch 前面，不用去解析
    也不用去改调用方那段字符串。这条不成立的话整个拼接方案就得推翻。
    """
    for label, hmr_root in (("默认（兜底）", None), ("自挂 hmr", ["."])):
        census_out = lab_home.root / f"census-baseline-{'auto' if hmr_root is None else 'own'}.json"
        profile = lab_home.make_minimal_profile(
            "auto" if hmr_root is None else "own",
            hmr_root=hmr_root,
            patch=census_patch(census_out),
        )
        profile.link_plugin("l00-census", fixtures_dir / "l00-census")

        inst = launch(profile, wait_http=False)
        got = watch(inst)
        settle_snap = phase(read_census(census_out), "settle")
        show_entries(settle_snap, f"基线 · {label}")
        if not got["alive"]:
            print(got["logs"])

        assert settle_snap is not None, f"{label}：普查员没被加载\n{got['logs']}"
        entries = settle_snap["entries"]
        assert any(e["id"] == "census" for e in entries), (
            f"{label}：多 insert 块没能共存 —— 拼接方案不成立"
        )

        hmr_ids = [e["id"] for e in entries if (e["name"] or "").endswith("plugin-hmr")]
        print(f"    hmr 条目：{hmr_ids}")
        assert len(hmr_ids) == 1, f"{label}：hmr 条目应当只有一个，实际 {hmr_ids}"
        if hmr_root is not None:
            assert hmr_ids == ["hmr"], "自挂时那一个应当是我们自己的（id 是我们给的）"


def test_pending_at_boot_is_fatal(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 6：boot 期停在 PENDING 的条目，是不是一律致命？

    这个问题从 L3 挂到现在。当时的观察是矛盾的：教具那次（叠了 dsh-web-app）
    启动直接失败，L3 那次（只叠 dsh-base）照常跑。当时归因到「bundle 组合」，
    但那只是个还没排除的变量，不是解释。

    源码给了明确答案 —— `dsh-app-boot` 的 `assertEntriesActivated` 在 boot
    末尾审计每一个未 disabled 的条目，任何一个不是 ACTIVE 就抛错，
    PENDING 的那条还会把缺的服务名列出来：

        `${name}: pending (waiting for ${subject}: ${missing.join(", ")})`

    照这段代码，PENDING 应当**无条件**致命，跟 bundle 组合没关系。
    这一跑就是去验它：挂一个硬依赖 `definitelyNotAService` 的条目。
    """
    census_out = lab_home.root / "census-pending.json"
    witness = lab_home.root / "needy-witness.json"
    profile = lab_home.make_profile("pending", bundles=[])
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.link_plugin("l00-needy", fixtures_dir / "l00-needy")
    profile.write_patch(census_patch(census_out, extra=f"""
    - id: needy
      name: l00-needy
      config:
        witness: {json.dumps(witness.as_posix())}
"""))

    inst = launch(profile, wait_http=False)
    got = watch(inst, seconds=20.0)

    print(f"\n进程还活着？ {got['alive']}（退出码 {got['exit_code']}，死于 +{got['died_at']}s）")
    print(f"needy 的 apply 被调用过吗？ {witness.exists()}（预期 False —— 服务永远等不到）")

    logs = got["logs"]
    hit = [ln for ln in logs.splitlines() if "did not activate" in ln or "pending (waiting" in ln]
    print(f"\n日志里的审计判词：{hit or '（没找到）'}")
    if not hit:
        print(logs)

    assert not witness.exists(), "硬依赖没满足，apply 不该被调用"
    assert not got["alive"], (
        "预期 boot 末尾的审计会让启动失败。如果它活着，说明 assertEntriesActivated "
        "有本课还没发现的放行条件 —— 那是个比原判定更重要的发现，记进 DRAFT.md"
    )
