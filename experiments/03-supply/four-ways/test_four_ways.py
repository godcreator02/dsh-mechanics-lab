"""four-ways · 同一个插件，四种挂法挂出来的条目有没有区别

档次 ① ｜ 性质 📗 部分复述 + 🔬 发现型 ｜ 状态 ✅ 已实测 ｜ 3 条用例 ｜ 不需要 web

## 判定

- **四条路挂出来的条目没有任何区别。** 状态迁移（`LOADING → ACTIVE`）、`apply`
  跑的时机（早于 `ACTIVE`）、`config` 的送达、`disabled` 取值，四条路
  （单文件拷贝 / junction 到一个包 / 走官方 `dsh plugin add` 命令 / 依赖指向一份
  钉了 tag 的 git 工作副本）完全一致。唯一看得见的差别只有条目自己写的 `name`
  字段：单文件写相对路径（`./courier.mjs`），其余三条写包名（`ch2-courier`）。
  条目身上不带「我是怎么被挂上来的」这种标记。证据：
  `test_four_ways_mount_the_same_entry`
- **四条路的代价差得很远。** 要准备的文件数、profile 目录里留下的东西、要不要
  手写活层 `insert` 各不相同；正经安装是唯一「包自己声明要挂哪个条目」的一条
  ——代价是它会改写 profile 的 `package.json`（细节见 `install-command` 项）
- **包摆在那儿，不装也不写，什么都不会发生。** 同一个包、同样建好目录链接，
  只要没跑安装命令、也没手写 `insert`，条目就不存在——包根那份
  `cordis.patch.yml` 没人会去读它。自注册靠的是「装」这个动作（把包名写进
  `dsh.profile.bundles`），不是「包目录里躺着一份 patch 文件」。证据：
  `test_the_package_alone_registers_nothing`

## 观测方法

判据全部落在教学插件自己上报的内容上（走 `observatory/lab-recorder`），不看树的
其它部分：条目在不在树上、走过哪些状态、说过什么话、报出来的 `config`、条目上
的 `name`。四条路各起一个独立实例（一条路一个 profile），互不干扰，观测完再
横向对比。

## 途径③会真的跑安装命令

`test_four_ways_mount_the_same_entry` 搭途径③（正经安装）那个 profile 时，
调用的是 `node <dsh 部署的 bin.js> plugin --profile <名> add <包目录>`——真实
子进程调用，会在假 home 下真的执行 `pnpm add`（本地路径依赖，不联网，只改
`$DSH_HOME` 下那个 profile 目录，细节见 `install-command` 项的源码分析）。

已裁决：保留原样。项目纪律禁的是「对生产 home 跑」和「会联网拉包」的
`dsh plugin` 调用，这里两条都不成立——改的是假 home 里的 profile，装的是本地
目录，不触网。`install-command` 项自己遵守「不实跑 `dsh plugin` 子命令」的
纪律，是它为了保持纯源码引用的静态用例做出的选择，不代表本项也必须回避；本项
要展示的正是「四条路挂出来的条目没有区别」，途径③不真的走一遍安装命令就验不到
途径③本身，只是在验途径②的另一份拷贝。边界：不许对生产 home（`~/.dsh`）跑这条
命令，不许装会联网拉取的包（写公网包名而不是本地目录）。

## 对比表里寄居着一条单独的判定

`test_four_ways_mount_the_same_entry` 里 `assert got["apply 早于 ACTIVE"]` 这行，
断言的不只是「四条路一致」，它顺带保住了「同条目内 `apply` 说话的时刻早于该条目
变 `ACTIVE`——apply 是跑在 `LOADING` 期间，不是等到 `ACTIVE` 之后」这个判定。
这条原本有一条专门演示它的独立用例（`test_apply_runs_while_loading`），现在寄居
在这张四条路的横向对比表里，靠 `look()` 里的 `"apply 早于 ACTIVE"` 一列产出。
以后要找这条判定，grep `apply 早于 ACTIVE`。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from lab import (
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    dsh_bin,
    entry_ids,
    of_kind,
    read_events,
    reports,
    states_of,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
COURIER = Path(__file__).resolve().parent / "fixtures" / "courier"

#: 教学插件的包名与它挂出来的条目 id —— 四条路全用同一对
PACKAGE = "ch2-courier"
ENTRY_ID = "courier"

#: 三条基础设施条目，原样带过来
BASE = """- insert:
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

#: 途径①②④手写的那一条，`name` 不同；途径③不写这一段（靠包自己的 patch 上树）。
YOURS = """
- insert:
    - id: {id}
      name: {name}
      config:
        途径: {way}
"""


# ── 搭台 ────────────────────────────────────────────────────────────────────


def new_profile(lab_home: LabHome, label: str, *, yours: str = "") -> tuple[LabProfile, Path]:
    """搭一个空实例：三条基础设施 +（可选）手写的那一条。"""
    events = lab_home.root / f"events-{label}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix())) + yours
    profile = lab_home.make_profile(label, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    return profile, events


def git(argv: list[str]) -> None:
    got = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if got.returncode != 0:
        raise AssertionError(f"git 失败（{' '.join(argv)}）：\n{got.stdout}\n{got.stderr}")


def make_worktree(lab_home: LabHome) -> Path:
    """把插件包做成一个 git 仓，钉一个 tag，再签出一份工作副本。依赖指向的是这份
    副本，不是仓库本体。"""
    repo = lab_home.root / "delivery" / "repo"
    copy = lab_home.root / "delivery" / "at-v1"
    shutil.copytree(COURIER, repo, dirs_exist_ok=True)

    at = ["git", "-C", str(repo), "-c", "user.name=lab", "-c", "user.email=lab@example.invalid"]
    git(["git", "init", "-q", "-b", "main", str(repo)])
    git([*at, "add", "."])
    git([*at, "commit", "-q", "-m", "v1"])
    git([*at, "tag", "v1"])
    git([*at, "worktree", "add", "-q", "--detach", str(copy), "v1"])
    return copy


def install(lab_home: LabHome, profile: LabProfile, package_dir: Path) -> subprocess.CompletedProcess[str]:
    """跑官方安装命令。不判成败——它的输出本身就是产物，交给调用方断言。

    `cwd` 设在项目根、包目录传绝对路径：这条命令会把相对路径按调用目录重算，
    传绝对路径就没有「算到哪去了」这个问题。
    """
    argv = ["node", str(dsh_bin()), "plugin", "--profile", profile.name, "add", str(package_dir)]
    env = {**lab_home.env(), "NPM_CONFIG_UPDATE_NOTIFIER": "false"}
    return subprocess.run(
        argv, cwd=str(LAB_ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


# ── 四条路各自怎么搭 ────────────────────────────────────────────────────────


def build_single_file(lab_home: LabHome) -> tuple[LabProfile, Path]:
    """① 单文件：把 `.mjs` 拷进 profile 目录，`name` 写相对路径。"""
    yours = YOURS.format(id=ENTRY_ID, name=json.dumps("./courier.mjs"), way="单文件")
    profile, events = new_profile(lab_home, "single-file", yours=yours)
    shutil.copy2(COURIER / "index.mjs", profile.dir / "courier.mjs")
    return profile, events


def build_linked(lab_home: LabHome) -> tuple[LabProfile, Path]:
    """② 目录链接：`dependencies` 写一行 `link:`，`node_modules` 里建一条链接。
    两件事缺一不可——`dependencies` 是给人和工具看的声明，真正决定「`name` 写
    包名能不能找到东西」的是那条链接。"""
    yours = YOURS.format(id=ENTRY_ID, name=json.dumps(PACKAGE), way="目录链接")
    profile, events = new_profile(lab_home, "linked", yours=yours)
    profile.link_plugin(PACKAGE, COURIER)
    return profile, events


def build_installed(lab_home: LabHome) -> tuple[LabProfile, Path]:
    """③ 正经安装：跑官方命令，patch 文件里一行都不写。"""
    profile, events = new_profile(lab_home, "installed")
    got = install(lab_home, profile, COURIER)
    assert got.returncode == 0, f"安装命令失败（退出码 {got.returncode}）：\n{got.stdout}\n{got.stderr}"
    assert ENTRY_ID not in profile.read_patch(), "前提：patch 文件里没有手写任何一条 courier"
    return profile, events


def build_worktree(lab_home: LabHome) -> tuple[LabProfile, Path]:
    """④ 工作副本：跟途径②同一套写法，只是链接指向那份 git 工作副本。"""
    copy = make_worktree(lab_home)
    yours = YOURS.format(id=ENTRY_ID, name=json.dumps(PACKAGE), way="工作副本")
    profile, events = new_profile(lab_home, "worktree", yours=yours)
    profile.link_plugin(PACKAGE, copy)
    return profile, events


WAYS = {
    "① 单文件": build_single_file,
    "② 目录链接": build_linked,
    "③ 正经安装": build_installed,
    "④ 工作副本": build_worktree,
}


# ── 观测 ────────────────────────────────────────────────────────────────────


def wait_for_courier(inst: Instance, path: Path, *, timeout: float = 60.0) -> list[dict]:
    """等它自己的上报出现，不是等事件总数。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = read_events(path)
        if reports(events, who=ENTRY_ID):
            time.sleep(0.5)  # 让采集器把同一批的状态事件也刷完
            return read_events(path)
        if not inst.alive():
            break
        time.sleep(0.3)
    return read_events(path)


def look(events: list[dict]) -> dict:
    """从事件流里把「这条条目长什么样」抠出来。"""
    said = reports(events, who=ENTRY_ID)
    snap = next((e for e in of_kind(events, "snapshot") if e.get("id") == ENTRY_ID), None)
    active = [e for e in events if e.get("kind") == "status" and e.get("id") == ENTRY_ID and e.get("to") == "ACTIVE"]
    return {
        "在树上": ENTRY_ID in entry_ids(events),
        "走过的状态": states_of(events, ENTRY_ID),
        "说的话": said[0]["note"] if said else None,
        "报出来的 config": said[0].get("data") if said else None,
        "apply 早于 ACTIVE": bool(said and active and float(said[0]["ms"]) < float(active[0]["ms"])),
        "disabled": snap.get("disabled") if snap else None,
        "条目上的 name": snap.get("name") if snap else None,
        # 观察器睁眼那一刻这条是什么样。只打印、不进判定：取决于观察器自己
        # 挂上的时机，是时序信号，不是条目的属性。
        "观察器睁眼时": (snap.get("to") or "还没建起来") if snap else "不在名单里",
    }


def cell(value: object) -> str:
    if isinstance(value, list):
        return " → ".join(str(item) for item in value)
    return json.dumps(value, ensure_ascii=False)


def footprint(profile: LabProfile) -> dict:
    """这条路在 profile 目录里留下的痕迹。"""
    manifest = json.loads((profile.dir / "package.json").read_text(encoding="utf-8"))
    node_modules = profile.dir / "node_modules"
    return {
        "profile 目录里": sorted(p.name for p in profile.dir.iterdir() if p.name != "node_modules"),
        "node_modules 里": sorted(p.name for p in node_modules.iterdir()) if node_modules.is_dir() else [],
        "dsh.profile.bundles": manifest["dsh"]["profile"]["bundles"],
        "dependencies": sorted(manifest.get("dependencies", {})),
        "patch 文件里手写了 courier 吗": ENTRY_ID in profile.read_patch(),
    }


# ── 用例 1 · 四条路挂出来的条目一模一样 ─────────────────────────────────────


def test_four_ways_mount_the_same_entry(lab_home: LabHome, launch):
    """同一个插件，四种挂法，四个实例——挂出来的条目没有任何区别。

    四条路各起一个实例（互不干扰，一条路一个 profile），各自等它说话，
    再把四份观测摆在一起对。
    """
    seen: dict[str, dict] = {}
    marks: dict[str, dict] = {}

    for way, build in WAYS.items():
        profile, events_path = build(lab_home)
        inst = launch(profile, wait_http=False)
        events = wait_for_courier(inst, events_path)
        assert inst.alive(), f"{way}：实例应当活着\n{inst.logs()}"
        seen[way] = look(events)
        marks[way] = footprint(profile)
        inst.stop()

    print("\n══ 四条路挂出来的条目 ════════════════════════════════════")
    rows = ["在树上", "走过的状态", "说的话", "apply 早于 ACTIVE", "disabled", "报出来的 config", "条目上的 name"]
    cells = {(row, way): cell(seen[way][row]) for row in rows for way in WAYS}
    width = max(len(text) for text in [*cells.values(), *WAYS]) + 2
    print(f"  {'':<20}" + "".join(f"{way:<{width}}" for way in WAYS))
    for row in rows:
        print(f"  {row:<20}" + "".join(f"{cells[row, way]:<{width}}" for way in WAYS))

    print("\n  ↓ 附：观察器睁眼那一刻看到的它（不进判定，跟时序有关）")
    print(f"  {'观察器睁眼时':<20}" + "".join(f"{cell(seen[way]['观察器睁眼时']):<{width}}" for way in WAYS))

    print("\n══ 各自的代价 ════════════════════════════════════════════")
    for way in WAYS:
        print(f"\n  {way}")
        for key, value in marks[way].items():
            print(f"    {key:<28}{json.dumps(value, ensure_ascii=False)}")

    # ── 一样的那部分 ────────────────────────────────────────────────────────
    for way, got in seen.items():
        assert got["在树上"], f"{way}：这条没挂上"
        assert got["走过的状态"] == ["LOADING", "ACTIVE"], f"{way}：状态迁移不对，实际 {got['走过的状态']}"
        assert got["说的话"] == "我跑起来了", f"{way}：它没说该说的话，实际 {got['说的话']!r}"
        assert got["apply 早于 ACTIVE"], f"{way}：apply 该跑在这条变 ACTIVE 之前"
        assert got["disabled"] is False, f"{way}：不该被标成 disabled"

    same = {
        way: (tuple(got["走过的状态"]), got["说的话"], got["apply 早于 ACTIVE"], got["disabled"])
        for way, got in seen.items()
    }
    assert len(set(same.values())) == 1, f"四条路挂出来的条目应当没有区别：{same}"

    # ── config 照样原样送达，途径③ 送的是包自己写的那份 ──────────────────────
    assert {way: got["报出来的 config"] for way, got in seen.items()} == {
        "① 单文件": {"途径": "单文件"},
        "② 目录链接": {"途径": "目录链接"},
        "③ 正经安装": {"途径": "正经安装"},
        "④ 工作副本": {"途径": "工作副本"},
    }

    # ── 不一样的那一个字段：name 写路径还是写包名 ────────────────────────────
    assert seen["① 单文件"]["条目上的 name"] == "./courier.mjs"
    for way in ("② 目录链接", "③ 正经安装", "④ 工作副本"):
        assert seen[way]["条目上的 name"] == PACKAGE, f"{way}：`name` 该写包名"


# ── 用例 2 · 对照：包摆在那儿，不装也不写，什么都不会发生 ────────────────────


def test_the_package_alone_registers_nothing(lab_home: LabHome, launch):
    """同一个包、同样建好目录链接，只是没跑安装命令、也没手写 `insert`
    ——条目就不存在。

    自注册靠的是「装」这个动作（把包名写进 profile 的 `package.json`），不是
    「包目录里躺着一份 `cordis.patch.yml`」——文件躺在那儿，没人会去读它。
    """
    profile, events_path = new_profile(lab_home, "notinstalled")
    profile.link_plugin(PACKAGE, COURIER)
    assert (COURIER / "cordis.patch.yml").exists(), "前提：包里确实带着那份 patch 文件"

    inst = launch(profile, wait_http=False)
    wait_for_courier(inst, events_path, timeout=15.0)

    # 验「不该发生」：固定等一段，不能轮询提前退出
    Instance.settle(10.0)
    events = read_events(events_path)

    print("\n══ 包在，但既没装、也没手写那一条 ════════════════════════")
    print(f"  实例还活着？    {inst.alive()}")
    print(f"  树上的条目：    {sorted(entry_ids(events))}")
    print(f"  它说的话：      {[e.get('note') for e in reports(events, who=ENTRY_ID)] or '（一句都没有）'}")
    manifest = json.loads((profile.dir / "package.json").read_text(encoding="utf-8"))
    print(f"  那份名单：      dsh.profile.bundles = {manifest['dsh']['profile']['bundles']}")

    assert inst.alive(), f"实例应当照常活着——少挂一个插件不是错误\n{inst.logs()}"
    assert ENTRY_ID not in entry_ids(events), f"它不该出现在树上：{sorted(entry_ids(events))}"
    assert not reports(events, who=ENTRY_ID), "它不该说话——包里那份 patch 文件没人读"
