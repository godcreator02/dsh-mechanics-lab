"""第 10 项 · bundle 层与活层的分水岭

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/ch2_bundle_vs_live/ -n 0 -s

到现在为止，「写 patch 的地方」一共见过两处：profile 目录里那份、home 目录里那份。
它们其实是同一种东西 —— 都叫**活层**：改完一两秒就生效，实例不用重启。前面每一次
「改 patch 文件」说的都是改活层。

这一项补上第三处：**bundle 层**。它不在你手上，在**包**里 —— 包的 `package.json`
声明 `dsh.bundle.patch`，包根放一份 `cordis.patch.yml`，包一旦进了这个 profile 的
bundle 名单，那份 patch 里写的条目就自己上树了。

四件事：

1. 包能自注册 —— profile 那份 patch 文件里一个字都没写，条目照样在树上、照样跑
2. 改活层：一两秒就生效（前面第 5、6 项见过的现象，这里当对照组）
3. 改 bundle 层：**实例毫无反应**，重启之后才生效
4. 同一个包既进 bundle 名单、又在活层 insert 同一个 `id`：撞的是第 6、7 项那堵墙

判据全部落在**插件自己报出来的那个「版本」**上：写进哪个文件是我们做的事，
它报出什么是它说的事，两边摆在一起才叫对上了。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lab import (  # noqa: E402
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    entry_ids,
    of_kind,
    read_events,
    reports,
    rmtree_safe,
    states_of,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"

#: 这一项的教学插件。它自己就是一个包 —— 见 fixtures/ch2-greeter/package.json。
PKG_NAME = "ch2-greeter"

#: 前几项立起来的三条，原样带过来。它们写在 **profile 那份 patch 文件**里，也就是活层。
BASE = """- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'
      config:
        root: {roots}
        debounce: 100

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
"""

#: 「验证什么都不该发生」用的固定等待。改活层是一两秒的事，15 秒远远超过它 ——
#: 这类断言不许轮询提前退出：提前退出只能证明「此刻还没发生」。
SETTLE = 15.0


# ── 搭台 ────────────────────────────────────────────────────────────────────


def copy_package(lab_home: LabHome, tag: str) -> Path:
    """把教学插件那个包拷一份到假 home 里，用例只改这份拷贝。

    仓库里 `fixtures/ch2-greeter/` 那份是**源**，从头到尾保持原样 —— 页面上要印的
    就是它。用例要改的是「包里那份 patch 文件」，改在拷贝上，跑多少次都不脏源。
    """
    dest = lab_home.root / f"pkg-{tag}" / PKG_NAME
    if dest.exists():
        rmtree_safe(dest)
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / PKG_NAME, dest)
    return dest


def write_package_patch(pkg_dir: Path, version: str) -> None:
    """改**包里**那份 `cordis.patch.yml` —— 这就是「改 bundle 层」这个动作。

    每条用例开头都显式写一次，起手状态才可控：不会因为上一条用例改过而互相串味。
    """
    (pkg_dir / "cordis.patch.yml").write_text(
        f"""# 包自己那份 patch 文件（bundle 层）。内容由用例写入。
- insert:
    - id: greeter
      name: {PKG_NAME}
      config:
        版本: {version}
""",
        encoding="utf-8",
    )


def build(
    lab_home: LabHome, name: str, *, pkg_dir: Path, in_bundles: bool, live_extra: str = "", watch_pkg: bool = False
) -> tuple[LabProfile, Path]:
    """搭一个 profile。

    Args:
        pkg_dir: 教学插件那个包在哪儿（假 home 里的那份拷贝）。
        in_bundles: 把包名写进 `dsh.profile.bundles` 名单没有 —— 这一项的主角。
        live_extra: 追加写进 profile 那份 patch 文件（活层）的内容。
        watch_pkg: 让 hmr 盯着包所在的目录。用来堵一个可能的疑问：
            「bundle 层没反应，会不会只是因为没人盯着那个目录？」
    """
    events = lab_home.root / f"events-{name}.jsonl"
    roots = json.dumps([pkg_dir.parent.as_posix()] if watch_pkg else [])
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, roots=roots, out=json.dumps(events.as_posix()))
    profile = lab_home.make_profile(name, bundles=[PKG_NAME] if in_bundles else [], patch=patch + live_extra)
    profile.link_plugin("lab-recorder", OBSERVER)
    # 包要能被 `name: ch2-greeter` 找到，就得先装进这个 profile —— 依赖声明一行、
    # node_modules 里一条链接，两件事缺一不可（第 9 项讲过的那套）。
    # 注意：装进来和「进 bundle 名单」是两件事，后者由 in_bundles 单独控制。
    profile.link_plugin(PKG_NAME, pkg_dir)
    return profile, events


# ── 读事件流 ────────────────────────────────────────────────────────────────


def said_versions(events: list[dict], who: str) -> list[str]:
    """某个条目报过的「版本」，按时间顺序。"""
    return [e["data"]["版本"] for e in reports(events, who=who) if e.get("data")]


def wait_said(inst: Instance, path: Path, who: str, *, count: int = 1, timeout: float = 40.0) -> list[str]:
    """等某个条目报到第 `count` 次为止 —— 验「应该发生的事」用轮询。"""
    deadline = time.monotonic() + timeout
    got: list[str] = []
    while time.monotonic() < deadline:
        got = said_versions(read_events(path), who)
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


def show(events: list[dict]) -> str:
    return timeline(events, kinds=("report",))


def restart(launch, profile: LabProfile, events_path: Path, inst: Instance) -> Instance:
    """停掉再拉起来，顺手把上一程的事件流挪开。

    事件流是按路径写的，新实例起来第一件事就是把它清空重写。挪开是为了别把
    「上一程的残留」当成「这一程说的话」—— 那会让「等它说话」当场就返回，
    读到的全是旧的。挪走的那份留着，跑完一起归档。
    """
    inst.stop()
    events_path.replace(events_path.with_name(events_path.stem + "-run1.jsonl"))
    return launch(profile, wait_http=False)


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_a_package_mounts_itself(lab_home: LabHome, launch):
    """判定 1 · 包能自注册。

    profile 那份 patch 文件里**没有一个字**提到这个插件 —— 只有 timer、hmr、
    观察器那三条老面孔。我们做的唯一一件事是把包名写进 `dsh.profile.bundles`
    名单。然后条目 `greeter` 就在树上了、`apply` 跑了、`config` 也收到了。

    那条 insert 是**包自己**写的，写在它自己那份 `cordis.patch.yml` 里。
    """
    pkg = copy_package(lab_home, "selfmount")
    write_package_patch(pkg, "第一版")
    profile, events_path = build(lab_home, "selfmount", pkg_dir=pkg, in_bundles=True)

    inst = launch(profile, wait_http=False)
    got = wait_said(inst, events_path, "greeter")

    events = read_events(events_path)
    print("\n══ 包把自己挂上去了 ══════════════════════════════════════")
    print("  profile 那份 patch 文件（活层）写了什么：")
    print("    只有 timer / hmr / 观察器 —— 没有 greeter")
    print(f"  package.json 的 bundle 名单：{[PKG_NAME]}")
    print("  包自己那份 cordis.patch.yml：")
    print("    - insert: [{ id: greeter, name: ch2-greeter, config: {版本: 第一版} }]")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "greeter" in entry_ids(events), "包自己那份 patch 写的条目应当出现在树上"
    assert got == ["第一版"], f"它该报出包里写的那一版，实际 {got}"


def test_one_layer_is_hot_the_other_is_cold(lab_home: LabHome, launch):
    """判定 2 + 3 · 两份 patch 文件，同一种改法，两种下场。

    树上挂着同一个插件的两个条目：

      * `greeter`      —— 来自 **bundle 层**（包自己那份 patch 文件）
      * `greeter-live` —— 来自 **活层**（profile 那份 patch 文件，我们一直在改的那个）

    在**同一时刻**把两份文件都改一遍，然后固定等 15 秒，一次读事件流：

      * 活层那条又报了一次，报的是新值 —— 它是热的
      * bundle 层那条一声不吭，还是启动时那个值 —— 它是冷的

    两条摆在同一条时间线上，「是不是等得不够久」这个疑问当场就没了：同一个 15 秒里
    活层那条已经动完了。

    hmr 这一次还特意盯着包所在的目录（`root` 指过去了），所以也不是「没人看着那边」
    ——包里那份 patch 文件就是没人拿它当回事。

    最后重启一次：新进程重新读盘，bundle 层那条才报出新值。
    """
    pkg = copy_package(lab_home, "coldhot")
    write_package_patch(pkg, "第一版")
    profile, events_path = build(
        lab_home,
        "coldhot",
        pkg_dir=pkg,
        in_bundles=True,
        watch_pkg=True,
        live_extra=f"""
- insert:
    - id: greeter-live
      name: {PKG_NAME}
      config:
        版本: 活层第一版
""",
    )

    inst = launch(profile, wait_http=False)
    assert wait_said(inst, events_path, "greeter") == ["第一版"]
    assert wait_said(inst, events_path, "greeter-live") == ["活层第一版"]

    # ── 同一时刻，两份文件各改一处 ──────────────────────────────────────────
    write_package_patch(pkg, "第二版")  # bundle 层
    profile.write_patch(profile.read_patch().replace("活层第一版", "活层第二版"))  # 活层

    Instance.settle(SETTLE)

    before = read_events(events_path)
    cold_before = said_versions(before, "greeter")
    hot_before = said_versions(before, "greeter-live")

    # 「跑起来了几次」比「报了几次话」更硬：报话是插件自己的事，这个是框架记的。
    cold_runs = states_of(before, "greeter").count("ACTIVE")
    hot_runs = states_of(before, "greeter-live").count("ACTIVE")

    print("\n══ 两份文件同时改，等了 15 秒 ════════════════════════════")
    print(f"  包里那份 patch（bundle 层）：第一版 → 第二版　　该条目报过：{cold_before}（跑起来 {cold_runs} 次）")
    print(f"  profile 那份 patch（活层）：活层第一版 → 活层第二版　该条目报过：{hot_before}（跑起来 {hot_runs} 次）")
    print(f"  hmr 盯着的目录：{[pkg.parent.as_posix()]}（包就在里面）")
    print(f"  事件流里 hmr 报的动静：{len(of_kind(before, 'hmr-change'))} 条")
    print(show(before))

    assert inst.alive(), f"实例应当一直活着：\n{inst.logs()}"
    assert hot_before == ["活层第一版", "活层第二版"], f"活层是热的，改完该重跑一次，实际 {hot_before}"
    assert hot_runs == 2, f"活层那条应当跑起来两次（原来一次、改完又一次），实际 {hot_runs}"
    assert cold_before == ["第一版"], f"bundle 层是冷的，改了不该有任何反应，实际 {cold_before}"
    assert cold_runs == 1, f"bundle 层那条从头到尾只该跑起来一次，实际 {cold_runs}"
    assert not of_kind(before, "hmr-change"), "包里那份 patch 文件连 hmr 都没当回事 —— 它盯的是代码"

    # ── 重启：新进程重新读盘 ────────────────────────────────────────────────
    inst = restart(launch, profile, events_path, inst)
    cold_after = wait_said(inst, events_path, "greeter")
    hot_after = wait_said(inst, events_path, "greeter-live")

    print("\n══ 重启之后 ══════════════════════════════════════════════")
    print(f"  bundle 层那条报的是：{cold_after}")
    print(f"  活层那条报的是：　　 {hot_after}")
    print(show(read_events(events_path)))

    assert inst.alive(), f"重启后实例应当活着：\n{inst.logs()}"
    assert cold_after == ["第二版"], f"重启后 bundle 层的改动才生效，实际 {cold_after}"
    assert hot_after == ["活层第二版"], f"活层那条重启后当然也是新值，实际 {hot_after}"


def test_same_id_in_both_layers_will_not_start(lab_home: LabHome, launch):
    """判定 4 · 包进了 bundle 名单，活层又 insert 了同一个 `id` —— 实例起不来。

    这跟第 6 项「两处 patch 写了同一个 `id`」是**同一堵墙**：两层拼起来之后那是
    两个条目，`id` 撞了，进程当场退出，日志里点名是哪个 `id`。

    差别只在这次撞车的两边一边在你手上、一边在包里：包自己那份 patch 用的 `id`
    是它自己定的，你在活层随手写一个同名的，撞得毫无征兆。
    """
    pkg = copy_package(lab_home, "dup")
    write_package_patch(pkg, "第一版")
    profile, events_path = build(
        lab_home,
        "dup",
        pkg_dir=pkg,
        in_bundles=True,
        live_extra=f"""
- insert:
    - id: greeter
      name: {PKG_NAME}
      config:
        版本: 活层写的
""",
    )

    inst = launch(profile, wait_http=False)

    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)

    logs = inst.logs()
    verdict = [ln.strip() for ln in logs.splitlines() if "duplicate loader entry id" in ln]

    print("\n══ bundle 层和活层撞了同一个 id ══════════════════════════")
    print(f"  进程还活着？ {inst.alive()}（退出码 {inst.proc.returncode}）")
    print(f"  日志里的判词：{verdict[0] if verdict else '（没找到，看完整日志）'}")
    print(f"  它说过话吗：{said_versions(read_events(events_path), 'greeter') or '一句都没有'}")
    if not verdict:
        print(logs)

    assert not inst.alive(), "两层撞了同一个 id 居然起来了 —— 那它们就被当成一个条目了"
    assert verdict, f"日志里应当有 duplicate loader entry id 的判词：\n{logs}"
    assert any("greeter" in ln for ln in verdict), f"判词该点名撞车的那个 id：{verdict}"
    assert not said_versions(read_events(events_path), "greeter"), "进程都没起来，它不该说过话"
