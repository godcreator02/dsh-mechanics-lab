"""cold-surfaces · 哪些面够不着热重放这条路

档次 ① ｜ 性质 📗 部分复述 + 🔬 发现型 ｜ 状态 ✅ ｜ 3 条用例 ｜ 部分用例需要 web

`replay-mechanism`（同组）已经坐实：活层热重放的实现是 `watchUserPatches` 给
profile 活层文件和 home 层文件各注册一个 `hmr.registerConfig` 回调，文件一变
就重新 compose、`entry.update()` 改 `include` 这一个条目的 config。本项验的
是这条路**没有**覆盖到的面。

## 判定

- **三样文件都是冷的，且是同一个根因：`watchUserPatches` 只给 profile 活层
  文件和 home 层文件各注册了一个 `hmr.registerConfig` 回调。** 除此之外没有
  任何代码在监听文件系统。
  - **bundle 自己的 `cordis.patch.yml`**——组合包贡献的那份 patch，运行中实例
    改了毫无反应，重启才生效。证据：`test_bundle_patch_and_bundles_list_are_cold`
  - **profile 的 `dsh.profile.bundles` 名单本身**——手改名单，运行中实例照样
    没反应，重启后名单里已经不含的包，条目才整个消失。证据：同一条用例
  - **`--patch` 指向的 overlay 文件**——运行期改文件，热重放拾不到，必须重启。
    证据：`test_overlay_file_is_cold`
- **两条注册路径（bundles 名单成员资格 / 能否被 `import(name)` 解析）互不相干，
  且这条独立性扛得住重启。** 包不在 bundles 名单里，活层直接 `insert` 同一个
  包照样能挂上、照样能扛过重启存活。证据：`test_two_registration_paths_are_independent`
- **`--dump-config` 是个陷阱**：它是纯读盘的静态合成，bundle 层文件改完立刻能
  读到新值，但那跟「运行中实例有没有反应」是两回事——不能拿它当「进程内状态
  变了」的证据（CLAUDE.md 观测方法论第 6 条）。
- 三样文件都冷，不是「故意不响应」，是压根没人往这个方向看一眼——
  `composeLive()`（热重放每次重新组合时调的那个函数）只现读 profile 活层与
  home 层，bundle 层 patch 与 `--patch` overlay 都是 boot 时读进内存的静态
  快照，重放时用的还是那份内存数据，不重读磁盘。

## 观测方法

判断「运行中实例有没有反应」，信号必须落在**被改的那个条目自己**身上
（`configRevision` / 见证文件里的 `value`）——探针路由回显 `moduleLoadedAt`
（模块有没有被重新 import）与 `appliedAt`（apply 有没有被重跑）两个字段，
两个一起看才能分清「完全没反应」和「热重放了但看起来没变」。overlay 那条
用例用见证文件的记录条数与 `value` 字段做同样的事。

「验证什么都不该发生」（改了冷的那一面）用固定等待（10～12 秒），不用轮询
提前退出——提前退出只能证明「此刻还没发生」，证明不了「不会发生」。「验证
应该发生」（改活层、重启后读新值）用轮询。

`--patch` 参数不被公共脚手架的 `start_instance()` 支持，`test_overlay_file_is_cold`
自己拼了一个最小启动子进程（参数与环境变量传法跟 `start_instance` 一致，只是
多带 `--patch`），结果复用共享的 `Instance` 数据类。

## 没覆盖到的

以下几份旧实验目录用不同的插件、不同的场景验证了同一个根因，跑绿之后没有
再重新验证，仅在此存证、不重复实现：

- `plugin_wiring` 的 `test_bundle_layer_needs_a_restart_but_live_layer_does_not`：
  同一个根因换了个更锋利的角度——hmr 的 watcher 其实**看见了** bundle 层
  patch 文件的变化（事件流里有 `hmr-change`），只是没人拿它当「需要重读的
  bundle 配置」处理。这个「看见了也不管」的细节比本项的「完全没反应」更精确地
  刻画了机制本身：不是没人监听文件系统，是监听到了也没有消费者。
- `ch2_bundle_vs_live` 的 `test_one_layer_is_hot_the_other_is_cold`：同一个
  根因的第三份独立实现，用的教学插件把包放在假 home 根目录（不在 profile
  目录里面）。它断言「改 bundle 层的 patch 文件时一个 `hmr-change` 事件都没
  有」，表面上与 `plugin_wiring` 的观察矛盾，但两者并不真的冲突——`plugin_wiring`
  的结论本身就是「hmr 只认 watch root 覆盖到的文件」，而 `ch2_bundle_vs_live`
  的包恰好落在 watch root 之外，所以看不到 `hmr-change` 完全在预期之内。
  这条「watch root 覆盖范围」是 `05-reload` 组的机制（供给包的真身必须落在
  profile 目录里面才能被 hmr 看见），不在本项重复验证。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from lab import BUNDLE_BASE, BUNDLE_WEB, Instance, LabHome, LabProfile, dsh_bin, dump_config

#: 需要端口 / dsh-web-app 的用例都在本文件里，整份钉在同一个 xdist worker 上。
pytestmark = pytest.mark.xdist_group("cold-surfaces")

PROBE_ROUTE = "/replay-cold-bundle/state"

#: 固定等待，用于"验证什么都不该发生"（见模块 docstring）。
SETTLE = 12.0

#: dsh-base + dsh-web-app 一起叠，起步比最小基线慢一截。
START_TIMEOUT = 150.0


# ── 辅助：bundle-patch / bundles-list ────────────────────────────────────────


def write_bundle_patch(fixtures_dir: Path, revision: str) -> None:
    """改写探针包自己的 `cordis.patch.yml`——这是 bundle 层，不是活层。

    每条用例开头都显式写一次，保证起手状态可控，不受上一次跑遗留内容影响。
    """
    patch_path = fixtures_dir / "replay-cold-bundle" / "cordis.patch.yml"
    patch_path.write_text(
        f"""# 由 test_cold_surfaces.py 在用例开头写入，内容以此为准。
- insert:
    - id: probe
      name: replay-cold-bundle
      config:
        revision: {revision}
""",
        encoding="utf-8",
    )


def set_profile_bundles(profile: LabProfile, bundles: list[str]) -> None:
    """直接改 profile 的 `package.json`——绝不走 `dsh plugin add`（那条命令会真的
    调 pnpm、联网，且会把带 `dsh.bundle` 的包自动对账进 `dsh.profile.bundles`，
    本项要的是"手改名单"这个动作本身）。
    """
    manifest_path = profile.dir / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dsh"]["profile"]["bundles"] = bundles
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def probe(inst: Instance) -> dict | None:
    """查探针路由。不是 JSON（比如 SPA 兜底的 200 HTML）就返回 None——
    `Instance.json_at` 已经处理了"200 但不是我们的路由"这个假阳性。
    """
    return inst.json_at(PROBE_ROUTE)


# ── 用例一：bundle 自己的 patch 文件、profile 的 bundles 名单，都是冷的 ─────────


def test_bundle_patch_and_bundles_list_are_cold(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """改 bundle 自己的 `cordis.patch.yml`、改 profile 的 `dsh.profile.bundles`
    名单，对正在跑的实例都毫无影响，必须重启才生效——两件事挤在同一个实例
    存活期内挨个撞，最后各自重启一次验证，把重启次数压到最低。
    """
    write_bundle_patch(fixtures_dir, "r1")
    profile = lab_home.make_profile("coldbundle", bundles=[BUNDLE_BASE, BUNDLE_WEB, "replay-cold-bundle"], web=True)
    profile.link_plugin("replay-cold-bundle", fixtures_dir / "replay-cold-bundle")

    port = free_port
    inst = launch(profile, port=port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: probe(inst), timeout=20.0, what="探针路由响应")
    print(f"\n初次响应：{got}")
    assert got["configRevision"] == "r1"
    module_loaded_at_1 = got["moduleLoadedAt"]
    applied_at_1 = got["appliedAt"]

    # ── 改 bundle 自己的 patch 文件 ──────────────────────────────────────────
    write_bundle_patch(fixtures_dir, "r2")

    # 静态视角（--dump-config）此刻已经算出新值——它是纯读盘的，跟"运行中实例
    # 有没有反应"是两件不同的事，别把它当成"进程内状态变了"的证据。
    dumped = dump_config(lab_home, profile.name)
    static_revision = dumped.config_of("probe").get("revision")
    print(f"改完 patch 之后，静态 --dump-config 已经算出新值：{static_revision!r}")
    assert static_revision == "r2", "静态视角应当已经看到新值——它是纯读盘的合成结果"

    Instance.settle(SETTLE)
    got_running = probe(inst)
    print(f"运行中实例的响应（bundle patch 已经改了）：{got_running}")
    assert got_running is not None, "路由不该消失——运行中实例应当还是原来那棵树"
    assert got_running["configRevision"] == "r1", "bundle 层是冷的，运行中实例不该变"
    assert got_running["moduleLoadedAt"] == module_loaded_at_1, "模块不该被重新 import"
    assert got_running["appliedAt"] == applied_at_1, "apply 不该被重跑"

    # 重启：新进程读盘，应当拿到 r2
    inst.stop()
    inst = launch(profile, port=port, timeout=START_TIMEOUT)
    got_restarted = inst.wait_for(lambda: probe(inst), timeout=20.0, what="重启后探针路由响应")
    print(f"重启后的响应：{got_restarted}")
    assert got_restarted["configRevision"] == "r2", "重启后应当读到新 revision"
    assert got_restarted["moduleLoadedAt"] != module_loaded_at_1, "重启=全新进程，模块重新 import"

    # ── 把包从 bundles 名单摘掉（手改 package.json） ─────────────────────────
    applied_at_2 = got_restarted["appliedAt"]
    set_profile_bundles(profile, [BUNDLE_BASE, BUNDLE_WEB])

    Instance.settle(SETTLE)
    got_after_edit = probe(inst)
    print(f"摘掉 bundles 名单后、运行中实例的响应：{got_after_edit}")
    assert got_after_edit is not None, "bundles 名单也是冷的，运行中实例的路由应当照样在"
    assert got_after_edit["appliedAt"] == applied_at_2, "运行中实例不该有任何动静"

    # 重启：这次新进程的配方里已经不含这个包的 patch 层，条目应当整个消失
    inst.stop()
    inst = launch(profile, port=port, timeout=START_TIMEOUT)
    inst.wait_for(lambda: inst.http("/") is not None, timeout=20.0, what="实例重新起来")
    got_final = probe(inst)
    print(f"重启后（bundles 名单已经不含探针包）：{got_final}")
    assert got_final is None, "包已经从 bundles 名单摘掉，重启后这条路由不该再存在了"


def test_two_registration_paths_are_independent(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """包从 `dsh.profile.bundles` 名单里摘掉，但活层直接 `insert` 同一个包，
    条目照样活着，且重启后依然存活——两条注册路径互不相干，且这条独立性扛得住
    重启（不是热重放期间"暂时还没被清"的假象）。

    `link_plugin()` 只往 profile 的 node_modules 建 junction、往 package.json
    的 `dependencies` 加一行——那只关系到 Node 模块解析，跟"这个包是不是
    bundles 名单里的一员"是完全独立的另一件事：那份名单只决定"要不要把这个包
    自己的 `cordis.patch.yml` 也叠进配方"。
    """
    profile = lab_home.make_profile(
        "livepath",
        bundles=[BUNDLE_BASE, BUNDLE_WEB],  # 故意不列 replay-cold-bundle
        web=True,
        patch="""# 活层直接 insert 同一个包 —— 绕开 bundles 名单这条路
- insert:
    - id: probe
      name: replay-cold-bundle
      config:
        revision: live-insert
""",
    )
    profile.link_plugin("replay-cold-bundle", fixtures_dir / "replay-cold-bundle")

    port = free_port
    inst = launch(profile, port=port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: probe(inst), timeout=20.0, what="探针路由响应")
    print(f"\n活层 insert、包不在 bundles 名单里：{got}")
    assert got["configRevision"] == "live-insert", "活层的注册路径应当独立生效——不需要这个包同时是 bundles 名单里的一员"

    inst.stop()
    inst = launch(profile, port=port, timeout=START_TIMEOUT)
    got_restarted = inst.wait_for(lambda: probe(inst), timeout=20.0, what="重启后探针路由响应")
    print(f"重启后：{got_restarted}")
    assert got_restarted["configRevision"] == "live-insert", "重启后活层这条注册路径应当照样存活"


# ── 用例二：`--patch` overlay 文件是冷的 ────────────────────────────────────


def test_overlay_file_is_cold(lab_home: LabHome, fixtures_dir: Path, running: list[Instance]):
    """运行期改 `--patch` 指向的文件，实例热重放拾不拾得到？答案是拾不到——
    `composeLive()` 每次热重放只现读 profile 活层和 home 层，**bundle 层与
    overlay 都是 boot 时的静态快照**，不会被文件改动触发重读。

    ⚠️ `lab.instance.start_instance()` 不支持传 `--patch`（公共脚手架不能为了
    单个用例去改），本用例自己拼一个最小的启动子进程，参数和环境变量传法跟
    `start_instance` 一致，只是多带一个 `--patch`。结果照样塞进共享的
    `Instance` 数据类，复用它的 `alive()` / `wait_for()` / `stop()`，并登记进
    `running` 夹具保证测完自动回收。
    """
    profile = lab_home.make_minimal_profile("overlay-runtime")
    profile.link_plugin("replay-cold-witness", fixtures_dir / "replay-cold-witness")

    witness_out = lab_home.root / "witness-overlay-runtime.json"
    overlay = lab_home.root / "overlay-runtime.yml"

    def write_overlay(value: str) -> None:
        overlay.write_text(
            f"""- insert:
    - id: witness
      name: replay-cold-witness
      config:
        out: {json.dumps(witness_out.as_posix())}
        value: {value}
""",
            encoding="utf-8",
        )

    write_overlay("initial")

    out_log = lab_home.root / "logs" / "overlay-runtime.out.log"
    err_log = lab_home.root / "logs" / "overlay-runtime.err.log"
    out_log.parent.mkdir(parents=True, exist_ok=True)
    argv = ["node", str(dsh_bin()), "--profile", profile.name, "--patch", str(overlay)]
    proc = subprocess.Popen(
        argv,
        cwd=str(profile.dir),
        env=lab_home.env(),
        stdout=out_log.open("w", encoding="utf-8"),
        stderr=err_log.open("w", encoding="utf-8"),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    inst = Instance(home=lab_home, profile_name=profile.name, port=None, proc=proc, out_log=out_log, err_log=err_log)
    running.append(inst)  # 保证测完自动 stop，异常路径也不例外

    def read_witness() -> list[dict] | None:
        if not witness_out.exists():
            return None
        try:
            data = json.loads(witness_out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else None

    got = inst.wait_for(read_witness, timeout=30.0, what="见证文件出现第一条记录")
    print(f"\n启动后见证文件：{got}")
    assert len(got) == 1 and got[0]["value"] == "initial"

    write_overlay("changed")
    print("已把 overlay 文件里的 value 改成 changed。固定等待 10 秒（验证什么都不该发生）")
    Instance.settle(10.0)

    after = read_witness()
    print(f"等待后见证文件：{after}")

    assert inst.alive(), f"进程不该崩：\n{inst.logs()}"
    assert after is not None and len(after) == 1, (
        "见证文件多出了新记录——说明 overlay 文件的改动被热重放拾到了，跟已知结论相反，是重大发现"
    )
    assert after[0]["value"] == "initial", (
        f"value 变成了 {after[0]['value']!r}——overlay 改动生效了，"
        "推翻了「运行期改 --patch 文件不会被热重放拾取」这条判定"
    )
