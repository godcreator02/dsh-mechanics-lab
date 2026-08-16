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
    return {"alive": inst.alive(), "died_at": died_at, "exit_code": inst.proc.returncode, "logs": inst.logs(tail=30)}


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
    inst.wait_for(root_config.exists, timeout=45.0, what="框架建出空根 cordis.yml")
    got = watch(inst, seconds=1.0)

    print("启动后 cordis.yml 存在？ True")
    print("  内容：")
    for line in root_config.read_text(encoding="utf-8").splitlines():
        print(f"    | {line}")
    print(f"进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")
    if not got["alive"]:
        print(got["logs"])
    assert root_config.read_text(encoding="utf-8").strip().endswith("[]"), "空根的内容应当是一个空数组"


def test_empty_bundles_boots(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 2：配方能不能是空的？

    `bundles: []` + 活层里只有基础设施两条和普查员自己。没有 dsh-base，
    没有任何 DSH 业务插件。这一跑要么证明「DSH 的插件系统能脱离 DSH 的业务层
    独立运行」，要么证明「有什么东西是硬前提」—— 两个结果都有用。

    注意「空」说的是 **bundle 名单**空，不是 patch 空：`timer` / `hmr` 是承重的
    （hmr 包级 `services.required: ["timer"]`，`watchUserPatches()` 开头就是
    `if (hmr === undefined) throw`），基线把它们显式写进 patch。
    """
    census_out = lab_home.root / "census-empty.json"
    profile = lab_home.make_minimal_profile("empty", patch=census_patch(census_out))
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")

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


def test_effective_config_vs_entry_tree(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 4（本课核心）：entry tree 跟 effective config 一样吗？

    **不一样，差一个 `cordis:include`。**

    它是框架在 boot 期建的树根，而**整份 effective config 就装在它的
    `config.patches` 里**——所以它必然不出现在自己装的那份 config 中，
    否则就是自指。`--dump-config` 因此永远看不见它。

    这个差别是**结构性**的：不管 config 怎么写、带不带任何 bundle，它都在。
    """
    census_out = lab_home.root / "census-ghost.json"
    profile = lab_home.make_minimal_profile("tree", patch=census_patch(census_out))
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")

    dumped = dump_config(lab_home, profile.name)
    recipe_ids = {e.get("id") for e in dumped.entries if isinstance(e, dict)}
    print(f"\neffective config 里的 id（{len(recipe_ids)} 个）：{sorted(recipe_ids)}")

    inst = launch(profile, wait_http=False)
    watch(inst)

    census = read_census(census_out)
    boot_snap, settle_snap = phase(census, "boot"), phase(census, "settle")
    show_entries(boot_snap, "boot 期：boot() 还没返回")
    show_entries(settle_snap, "settle：boot() 返回之后")

    if settle_snap is None or settle_snap.get("entries") is None:
        pytest.skip("拿不到 settle 快照，本用例无从判断 —— 先看上面的输出")

    tree_ids = {e["id"] for e in settle_snap["entries"]}
    ghosts = tree_ids - recipe_ids
    print(f"\n  树上有、config 里没有的：{sorted(ghosts)}")

    boot_ids = {e["id"] for e in (boot_snap or {}).get("entries") or []}
    print(f"  boot 返回之后新增的 id：{sorted(tree_ids - boot_ids) or '（没有）'}")

    assert ghosts == {"include"}, (
        f"预期只差 include 一个，实际 {sorted(ghosts)}。多出来的说明基线没把基础设施带全，或者框架又补了别的东西"
    )
    assert recipe_ids <= tree_ids, f"config 里有、树上没有的：{sorted(recipe_ids - tree_ids)}"


def test_bare_name_resolution(lab_home: LabHome, fixtures_dir: Path, launch):
    """问题 7：条目的 `name` 以哪里为锚解析？

    这直接决定 L1–L3 一直在做的那件事（`link_plugin` 把包 junction 进
    profile 的 node_modules）是不是必需的。

    **基线自己就是这个实验**：`timer` / `hmr` 两条写的都是裸包名
    （`@deepseek-ai/cordis-plugin-*`），而我们从来没 link 过它们——profile 的
    node_modules 里只有自己 link 的教学插件。它们照样激活，说明 profile 自己的
    node_modules 不是唯一锚点。

    机制是标准 Node parent-walk：profile 目录往上一层就是
    `$DSH_HOME/profiles/node_modules`，那是 dsh 的 `healScaffoldModuleFallback`
    每次 `prepareProfile` 时幂等维护的符号链接农场。本用例把这两头都打印出来。
    """
    census_out = lab_home.root / "census-bare.json"
    profile = lab_home.make_minimal_profile("bare", patch=census_patch(census_out))
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")

    inst = launch(profile, wait_http=False)
    got = watch(inst)

    linked = profile.dir / "node_modules" / "@deepseek-ai" / "cordis-plugin-timer"
    farm = lab_home.root / "profiles" / "node_modules" / "@deepseek-ai" / "cordis-plugin-timer"
    print(f"\ntimer 被 link 进 profile 了吗？        {linked.exists()}（预期 False）")
    print(f"上一层的共享 node_modules 里有吗？    {farm.exists()}（预期 True）")

    census = read_census(census_out)
    settle_snap = phase(census, "settle")
    show_entries(settle_snap, "settle 快照")
    print(f"\n进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")

    assert settle_snap is not None, f"普查员没被加载：\n{got['logs']}"
    assert not linked.exists(), "前提被破坏：timer 竟然被 link 进 profile 了"
    for eid in ("timer", "hmr"):
        e = next((x for x in settle_snap["entries"] if x["id"] == eid), None)
        assert e is not None and e["fiberState"] == 2, f"裸包名 {eid} 没能激活 —— 那 link 就是必需的\n{got['logs']}"
    print("  → 裸包名不用 link 进 profile：parent-walk 找到了上一层的共享 node_modules")


@pytest.mark.parametrize("kind, suffix", [("指向目录", ""), ("指向文件", "/index.js")])
def test_relative_name_resolution(lab_home: LabHome, fixtures_dir: Path, launch, kind: str, suffix: str):
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
    profile = lab_home.make_minimal_profile(f"rel{label}")
    # 故意**不** link —— 全靠相对路径找过去
    source = (fixtures_dir / "l00-census").resolve()
    # 假 home 和 fixtures 都在实验台里，必然同盘，relpath 一定算得出
    spec = "./" + Path(os.path.relpath(source, profile.dir.resolve())).as_posix() + suffix
    print(f"\n{kind}")
    print(f"  profile 在 {profile.dir}")
    print(f"  相对路径   {spec}")

    # 拼在基线那块之后 —— patch 文件是 YAML 数组，允许多个 `- insert:` 块
    profile.write_patch(
        profile.read_patch()
        + f"""# 相对路径引用
- insert:
    - id: census
      name: {json.dumps(spec)}
      config:
        out: {json.dumps(census_out.as_posix())}
        delayMs: {CENSUS_DELAY_MS}
"""
    )

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

    本用例把**基线**跑给它看：没有 web 服务、没有任何业务插件，树上只有
    `include` + `timer` + `hmr` + 普查员。活着 → 这两个基础设施的句柄就够撑住；
    死了 → 保活需要更多东西，那「最小集合」的定义就得往上加。
    """
    census_out = lab_home.root / "census-alive.json"
    profile = lab_home.make_minimal_profile("alive", patch=census_patch(census_out, delay_ms=1000))
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")

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
    """把前面的结论固化成基线，然后验它 —— `make_minimal_profile()`。

    基线做两件事：**不叠任何 bundle**（去噪声），**但显式带上 timer 与 hmr**
    （贴近真实——`dsh-base` 的 patch 头两条就是它们）。

    要验三点：

      1. 树的形状**完全可预测**：include + timer + hmr + 调用方自己的 entry，
         而且 id 全是我们给的，没有框架 fallback 那种随机 id
      2. `hmr_root` 能控制 watch root——默认 `[]` 只监听 patch 文件，
         传目录才监听代码文件（要测热重载的课用得上）
      3. patch 文件是 YAML 数组、**允许多个 `- insert:` 块**。基线靠这一点把
         基础设施两条拼在调用方的 patch 前面，不用解析也不用改调用方那段字符串
    """
    for label, hmr_root in (("默认 root []", None), ("指定 watch root", ["."])):
        tag = "dflt" if hmr_root is None else "rooted"
        census_out = lab_home.root / f"census-baseline-{tag}.json"
        profile = lab_home.make_minimal_profile(tag, hmr_root=hmr_root, patch=census_patch(census_out))
        profile.link_plugin("l00-census", fixtures_dir / "l00-census")

        inst = launch(profile, wait_http=False)
        got = watch(inst)
        settle_snap = phase(read_census(census_out), "settle")
        show_entries(settle_snap, f"基线 · {label}")
        if not got["alive"]:
            print(got["logs"])

        assert settle_snap is not None, f"{label}：普查员没被加载\n{got['logs']}"
        entries = settle_snap["entries"]
        ids = sorted(e["id"] for e in entries)

        # ① 形状完全可预测——多一个少一个都说明基线漏了东西或框架补了东西
        assert ids == ["census", "hmr", "include", "timer"], f"{label}：树的形状不是预期的四个，实际 {ids}"
        # ③ 多 insert 块共存：census 来自调用方的 patch，timer/hmr 来自基线那块
        assert any(e["id"] == "census" for e in entries), f"{label}：多 insert 块没能共存 —— 拼接方案不成立"

        hmr = next(e for e in entries if e["id"] == "hmr")
        print(f"    hmr：id={hmr['id']} state={hmr['fiberState']} ⊂{hmr['parent']}")
        # 基线声明的两条走的是 patch，所以落在 include 的 subtree 里
        assert hmr["parent"] == "include", (
            f"{label}：基线声明的 hmr 应当在 include 的 subtree 里，实际 ⊂{hmr['parent']}"
        )


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
    profile = lab_home.make_minimal_profile(
        "pending",
        patch=census_patch(
            census_out,
            extra=f"""
    - id: needy
      name: l00-needy
      config:
        witness: {json.dumps(witness.as_posix())}
""",
        ),
    )
    profile.link_plugin("l00-census", fixtures_dir / "l00-census")
    profile.link_plugin("l00-needy", fixtures_dir / "l00-needy")

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
