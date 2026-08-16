"""第 9 项 · 四种交付途径

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/ch2_four_ways/ -n 0 -s

第一章教出来的插件是「profile 目录里的一个文件」——那不是能给别人的东西。
这一项把**同一个插件**用四种方式挂进去，横向对比。

| 途径 | 怎么挂 |
|---|---|
| ① 单文件 | 把那个 `.mjs` 扔进 profile 目录，`name` 写 `./courier.mjs` |
| ② 目录链接 | 建一条目录链接 ＋ `dependencies` 里一行 `link:` 声明，`name` 写包名 |
| ③ 正经安装 | 官方命令 `dsh plugin --profile <名> add <包目录>` |
| ④ 工作副本 | 依赖指向一份 git 工作副本（worktree），`name` 写包名 |

四条路上的插件源码**一个字节都不差**：途径① 拷进去的就是那个包里的
`index.mjs` 本尊。所以凡是四条路上有差别的东西，都跟插件本身无关。

## 结论一：挂出来的条目一模一样

状态迁移、`apply` 跑的时机、`config` 的送达、能不能上报——四条路没有任何区别。
**条目身上不带「我是怎么被挂上来的」这种标记**，树上看不出来，插件自己也看不出来。

四条路上看得见的不同只有一处：**`name` 写路径还是写包名**
（`./courier.mjs` vs `ch2-courier`）。那是你自己写的那一行，不是框架给条目盖的章。

## 结论二：代价差得很远

选哪条路看的是这个：

| 途径 | 要准备几个文件 | profile 目录里留下什么 | patch 文件里要手写 insert 吗 |
|---|---|---|---|
| ① 单文件 | 1（`.mjs`） | 多一个 `.mjs` | **要** |
| ② 目录链接 | 3（`.mjs` ＋ `package.json` ＋ 包自带的 patch 文件） | 一条链接 | **要** |
| ③ 正经安装 | 同上 | 一条链接 ＋ `pnpm-lock.yaml` | **不用**——包自己带 |
| ④ 工作副本 | 同上 ＋ 一个 git 仓 | 一条链接 | **要** |

profile 的 `package.json` 也各不相同：①什么都不用动；②④ 自己加一行
`dependencies`；③ 由命令替你改两处——`dependencies` 加一行，`dsh.profile.bundles`
的名单里补上包名。

途径③ 是唯一「包能自己声明要挂哪个条目」的一条：包根放一份
`cordis.patch.yml`，`package.json` 里用 `dsh.bundle.patch` 指向它，装完 profile 的
patch 文件里一个字都不用写。代价是它会去改 profile 的 `package.json`
——本文件用例 2 把改动前后原样印出来。

## 关于途径③ 那条命令

`dsh plugin --profile <名> add <包目录>` 是一层很薄的转发：它在 profile 目录里
跑 `pnpm add <包目录>`，跑完再回头对账，把「装进来、而且自带 patch 文件」的包
补进 `dsh.profile.bundles`。

两件事因此是确定的：

* **它只动 `$DSH_HOME` 下的那个 profile 目录**——profile 目录是拿
  `$DSH_HOME` 加 profile 名算出来的，本实验的 `$DSH_HOME` 只指向假 home
* **它不上网**——传进去的是本地绝对路径，`pnpm` 记下来的依赖是一条
  `link:<绝对路径>`，没有任何东西要从远处拉。用例 2 顺带验了它连插件源码目录
  都没写过一个字节
"""

from __future__ import annotations

import json
import shutil
import subprocess
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

#: 前几步立起来的那三条，原样带过来
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

#: 手写的那一条。途径①②④ 都要写，只有 `name` 不同；途径③ 不写这一段。
YOURS = """
- insert:
    - id: {id}
      name: {name}
      config:
        途径: {way}
"""


# ── 搭台 ────────────────────────────────────────────────────────────────────


def new_profile(lab_home: LabHome, label: str, *, yours: str = "") -> tuple[LabProfile, Path]:
    """搭一个空实例：框架三条 +（可选）你手写的那条。

    观察器（lab-recorder）走目录链接挂上——它是装好的设备，不是这一项的对比对象。
    """
    events = lab_home.root / f"events-{label}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix())) + yours
    profile = lab_home.make_profile(label, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    return profile, events


def git(argv: list[str]) -> None:
    """跑一条 git，失败就把原文抬出来——搭台失败不能伪装成实验结论。"""
    got = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if got.returncode != 0:
        raise AssertionError(f"git 失败（{' '.join(argv)}）：\n{got.stdout}\n{got.stderr}")


def make_worktree(lab_home: LabHome) -> Path:
    """把插件包做成一个 git 仓，钉一个 tag，再签出一份工作副本。

    途径④ 的依赖指向的就是这份副本，而不是仓库本体。这一项只验「能挂上」——
    副本钉在哪个 tag 上、换 tag 会怎样，是第 11 项的事。
    """
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
    """跑官方安装命令。**不判成败**，交给调用方断言——它的输出本身就是产物。

    两处刻意写死：

      * `cwd` 设在本项目根，包目录传**绝对路径**。这条命令会把相对路径按调用
        目录重算，传绝对路径就没有「算到哪去了」这个问题
      * `NPM_CONFIG_UPDATE_NOTIFIER=false` 关掉 pnpm 自己那条「有新版本」的横幅
        ——那是 pnpm 的事，不是本实验的观测对象
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

    两件事缺一不可——`dependencies` 是给人和工具看的声明，真正决定
    「`name` 写包名能不能找到东西」的是那条链接。
    """
    yours = YOURS.format(id=ENTRY_ID, name=json.dumps(PACKAGE), way="目录链接")
    profile, events = new_profile(lab_home, "linked", yours=yours)
    profile.link_plugin(PACKAGE, COURIER)
    return profile, events


def build_installed(lab_home: LabHome) -> tuple[LabProfile, Path]:
    """③ 正经安装：跑官方命令，patch 文件里**一行都不写**。"""
    profile, events = new_profile(lab_home, "installed")
    got = install(lab_home, profile, COURIER)
    assert got.returncode == 0, f"安装命令失败（退出码 {got.returncode}）：\n{got.stdout}\n{got.stderr}"
    assert ENTRY_ID not in profile.read_patch(), "前提：patch 文件里没有手写任何一条 courier"
    return profile, events


def build_worktree(lab_home: LabHome) -> tuple[LabProfile, Path]:
    """④ 工作副本：跟途径② 同一套写法，只是链接指向那份 git 工作副本。"""
    copy = make_worktree(lab_home)
    yours = YOURS.format(id=ENTRY_ID, name=json.dumps(PACKAGE), way="工作副本")
    profile, events = new_profile(lab_home, "worktree", yours=yours)
    profile.link_plugin(PACKAGE, copy)
    return profile, events


#: 四条路，按教学顺序
WAYS = {
    "① 单文件": build_single_file,
    "② 目录链接": build_linked,
    "③ 正经安装": build_installed,
    "④ 工作副本": build_worktree,
}


# ── 观测 ────────────────────────────────────────────────────────────────────


def wait_for_courier(inst: Instance, path: Path, *, timeout: float = 60.0) -> list[dict]:
    """等到它把话说出来为止。等的是**它自己的上报**，不是事件总数。"""
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
        # 观察器睁眼那一刻这条是什么样。只打印、不进判定：它取决于观察器自己
        # 挂上的时机，是时序信号，不是条目的属性。
        "观察器睁眼时": (snap.get("to") or "还没建起来") if snap else "不在名单里",
    }


def cell(value: object) -> str:
    """把一个观测值压成表格里的一格。状态序列写成 `A → B`，其余原样。"""
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

    print("\n  ↓ 附：观察器睁眼那一刻看到的它（不进上面的判定，这一格跟时序有关）")
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


# ── 用例 2 · 那条命令替你改了 profile 的 package.json ────────────────────────


def test_installing_rewrites_the_profile_manifest(lab_home: LabHome):
    """途径③ 执行前后，profile 的 `package.json` 原样对照。

    这一条不起实例——要看的全在磁盘上。
    """
    profile, _events = new_profile(lab_home, "manifest")
    manifest_path = profile.dir / "package.json"

    before_text = manifest_path.read_text(encoding="utf-8")
    before_files = sorted(p.name for p in profile.dir.iterdir())
    before_patch = profile.read_patch()

    got = install(lab_home, profile, COURIER)

    after_text = manifest_path.read_text(encoding="utf-8")
    after_files = sorted(p.name for p in profile.dir.iterdir())

    print("\n══ 那条命令 ══════════════════════════════════════════════")
    print(f"  dsh plugin --profile {profile.name} add <包目录>")
    print(f"  退出码 {got.returncode}")
    for line in (got.stdout + got.stderr).splitlines():
        if line.strip():
            print(f"    | {line.rstrip()}")

    print("\n══ profile 的 package.json：执行前 ═══════════════════════")
    print("\n".join(f"  {line}" for line in before_text.splitlines()))
    print("\n══ profile 的 package.json：执行后 ═══════════════════════")
    print("\n".join(f"  {line}" for line in after_text.splitlines()))
    print("\n══ profile 目录 ══════════════════════════════════════════")
    print(f"  执行前：{before_files}")
    print(f"  执行后：{after_files}")

    assert got.returncode == 0, f"安装命令应当成功：\n{got.stdout}\n{got.stderr}"

    before = json.loads(before_text)
    after = json.loads(after_text)
    assert before["dsh"]["profile"]["bundles"] == [], "前提：装之前那份名单是空的"
    assert after["dsh"]["profile"]["bundles"] == [PACKAGE], "装完包名该被补进 dsh.profile.bundles"
    assert "dependencies" not in before or PACKAGE not in before["dependencies"], "前提：装之前没有这个依赖"
    assert after["dependencies"][PACKAGE].startswith("link:"), (
        f"依赖该记成一条本地 link:，实际 {after['dependencies'][PACKAGE]!r}"
    )
    assert "pnpm-lock.yaml" in set(after_files) - set(before_files), f"该多出一个锁文件：{after_files}"

    # patch 文件一个字都没动 —— 途径③ 不用你写 insert，命令也没替你写
    assert profile.read_patch() == before_patch, "这条命令不该碰 profile 的 patch 文件"

    # 只动了假 home 里那个 profile：插件源码目录一个文件都没多出来
    assert not (COURIER / "node_modules").exists(), "插件源码目录里不该被写进 node_modules"
    assert not (COURIER / "pnpm-lock.yaml").exists(), "插件源码目录里不该被写进锁文件"


# ── 用例 3 · 对照：包摆在那儿，不装也不写，什么都不会发生 ────────────────────


def test_the_package_alone_registers_nothing(lab_home: LabHome, launch):
    """同一个包、同样建好目录链接，只是**没跑那条安装命令、也没手写 insert**
    ——条目就不存在。

    这条把途径③ 的「包能自注册」钉在正确的位置上：自注册靠的是**装**这个动作
    （把包名写进 profile 的 `package.json`），不是「包目录里躺着一份
    `cordis.patch.yml`」。文件躺在那儿，没人会去读它。
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
