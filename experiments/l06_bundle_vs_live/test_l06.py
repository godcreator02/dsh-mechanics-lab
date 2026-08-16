"""L6 · bundle 层 vs 活层 —— 两层的分工与冷热差别。

**要回答**：改 bundle 的 patch 文件、或改 `dsh.profile.bundles` 名单，对**正在跑的
实例**有没有影响？把包从 bundles 名单摘掉、但活层里还 insert 着同一个包，
这个包是不是就真的没了？

**v1 已有结论（本课要用 Python 复跑对齐）**：改 bundle 的 patch 文件、或改
`dsh.profile.bundles` 名单，对正在跑的实例毫无影响，必须重启；活层秒级生效。
附带：把包从 bundles 名单摘掉、重启后，活层里 insert 同一个包的条目**照常存活**
——两条独立的注册路径。

只用一个教学插件 `fixtures/l06-probe-bundle`：它既是"组合包"（`package.json` 声明
`dsh.bundle.patch`），又是自己那份 patch 指向的插件模块本身——与官方 publish.md
的 hello-plugin 同款写法。探针路由回三个指纹（marker / moduleLoadedAt / appliedAt）
外加 config 回显，见 `fixtures/l06-probe-bundle/index.js` 顶部注释。

⚠️ 本课需要 web profile（`dsh-web-app` 覆盖 `dsh-base` 的行，两者必须一起叠），
启动慢；用例 1+2 挤在同一个实例存活期内测，最后统一重启验证，
全课总共 3 次重启（用例 1+2 两次、用例 3 一次），用例 4（可选）单独一次全新启动。
"""

from __future__ import annotations

import json
from pathlib import Path

from lab import BUNDLE_BASE, BUNDLE_WEB, Instance, LabHome, dump_config, start_instance

#: 探针路由。fixtures/l06-probe-bundle/index.js 里的默认值，这里复述一份只为可读。
PROBE_ROUTE = "/l06-probe/state"

#: 固定等待，用于"验证什么都不该发生"。热重放/debounce 通常在毫秒到一两秒量级，
#: 12 秒留足余量（纪律：这类断言不能用轮询提前退出，见 CLAUDE.md 观测方法论 4）。
SETTLE = 12.0

#: dsh-base + dsh-web-app 一起叠，起步比 L0-L5 的最小基线慢一截，
#: 放宽超时避免在慢机器上误判"启动失败"。
START_TIMEOUT = 150.0


# ── 辅助 ────────────────────────────────────────────────────────────────────


def write_bundle_patch(fixtures_dir: Path, revision: str) -> None:
    """改写探针包**自己的** `cordis.patch.yml`——这是 bundle 层，不是活层。

    显式写、不依赖 git 里提交的默认内容：每条用例开头都调一次，保证起手状态
    可控，不会因为上一条用例（或上一次跑）改过这份文件而互相污染。
    """
    patch_path = fixtures_dir / "l06-probe-bundle" / "cordis.patch.yml"
    patch_path.write_text(
        f"""# 由 test_l06.py 在用例开头写入，内容以此为准。
- insert:
    - id: probe
      name: l06-probe-bundle
      config:
        revision: {revision}
""",
        encoding="utf-8",
    )


def set_profile_bundles(profile, bundles: list[str]) -> None:
    """直接改 profile 的 `package.json`——**绝不**走 `dsh plugin add`（纪律 8：
    那条命令会真的调 pnpm、联网，且会把带 `dsh.bundle` 的包自动对账进
    `dsh.profile.bundles`，本课要的是"手改名单"这个动作本身）。
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


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_bundle_patch_and_bundles_list_are_cold(lab_home: LabHome, fixtures_dir: Path, launch, free_port):
    """用例 1+2：改 bundle 的 patch 文件、改 profile 的 `dsh.profile.bundles`
    名单，对**正在跑的实例**都毫无影响，必须重启才生效。

    两件事挤在同一个实例存活期内挨个撞，最后各自重启一次验证——这是
    SYLLABUS 建议的做法，把重启次数压到最低。
    """
    write_bundle_patch(fixtures_dir, "r1")
    profile = lab_home.make_profile("coldbundle", bundles=[BUNDLE_BASE, BUNDLE_WEB, "l06-probe-bundle"], web=True)
    profile.link_plugin("l06-probe-bundle", fixtures_dir / "l06-probe-bundle")

    port = free_port
    inst = launch(profile, port=port, timeout=START_TIMEOUT)
    got = inst.wait_for(lambda: probe(inst), timeout=20.0, what="探针路由响应")
    print(f"\n初次响应：{got}")
    assert got["configRevision"] == "r1"
    module_loaded_at_1 = got["moduleLoadedAt"]
    applied_at_1 = got["appliedAt"]

    # ── 用例 1：改 bundle 自己的 patch 文件 ──────────────────────────────────
    write_bundle_patch(fixtures_dir, "r2")

    # 静态视角（--dump-config）此刻已经读到新值——它是纯读盘的，
    # 跟"运行中实例有没有反应"是两件不同的事（CLAUDE.md 观测方法论 6）。
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

    # ── 用例 2：把包从 bundles 名单摘掉（手改 package.json） ──────────────────
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
    """用例 3：两条注册路径互不相干——包从 `dsh.profile.bundles` 名单里摘掉，
    但活层直接 `insert` 同一个包，条目照样活着，且**重启后依然存活**。

    `link_plugin()` 只往 profile 的 node_modules 建 junction、往 package.json
    的 `dependencies` 加一行——那是 Node 模块解析要用的，跟"这个包是不是
    bundles 名单里的一员"是两件不相干的事。名字能不能被 `import(name)` 解析，
    与"这个包有没有贡献一份 bundle patch 层"完全独立。
    """
    profile = lab_home.make_profile(
        "livepath",
        bundles=[BUNDLE_BASE, BUNDLE_WEB],  # 故意不列 l06-probe-bundle
        web=True,
        patch="""# 活层直接 insert 同一个包 —— 绕开 bundles 名单这条路
- insert:
    - id: probe
      name: l06-probe-bundle
      config:
        revision: live-insert
""",
    )
    profile.link_plugin("l06-probe-bundle", fixtures_dir / "l06-probe-bundle")

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


def test_duplicate_id_across_bundle_and_live_layer_kills_boot(lab_home: LabHome, fixtures_dir: Path, free_port):
    """用例 4（可选）：bundle 层和活层用同一个 id `insert` 同一个包，撞在
    **首次 boot**——整个进程启动失败，不是"打个警告然后活着"。

    源码依据（`cordis-plugin-include` 的 `applyEntryPatches`）：`- insert:` 语义
    是 `data.push(...insert)`，**不按 id 去重**；两处都用 insert（不是 `- id:`
    覆盖语义），于是最终合成的条目列表里出现两个 id 相同的 `probe`。这份列表
    整个交给 `EntryGroup.update()`，它在**创建任何条目之前**先扫一遍查重
    （`cordis-plugin-loader` 的 `group.ts`）：

        for (const options of config) {
          const id = this.tree.ensureId(options)
          if (seen.has(id)) throw new TypeError(`duplicate loader entry id: ${id}`)
        }

    这个 `update()` 正是 boot 期挂载 include 子树时调用的那个（`Group` 的
    `Service.init` 里 `await this.update(this.config)`），所以撞车发生在
    **创建任何条目之前**——不是「先挂后回滚」，是「整批提前拒绝」。
    """
    write_bundle_patch(fixtures_dir, "dup")
    profile = lab_home.make_profile(
        "dupboot",
        bundles=[BUNDLE_BASE, BUNDLE_WEB, "l06-probe-bundle"],
        web=True,
        patch="""# 活层也 insert 一个同 id 的条目 —— 跟 bundle 层的那个撞车
- insert:
    - id: probe
      name: l06-probe-bundle
      config:
        revision: from-live-layer
""",
    )
    profile.link_plugin("l06-probe-bundle", fixtures_dir / "l06-probe-bundle")

    inst = start_instance(profile, port=free_port, wait_http=False)
    try:
        # 固定等待：验证"进程会死"这件事。轮询提前退出只能证明"此刻还没死"，
        # 证明不了"不会死"（CLAUDE.md 观测方法论 4）。查重是同步检查、
        # 发生在创建任何条目之前，预期死得很快，15 秒留足余量。
        Instance.settle(15.0)
        alive = inst.alive()
        print(f"\n进程还活着？{alive}")
        logs = inst.logs()
        if not alive:
            print(f"退出码：{inst.proc.returncode}")
        print(logs)

        assert not alive, "同 id 双挂载撞在 boot 期，预期启动失败"
        assert "duplicate loader entry id" in logs, "预期是这个具体错误，不是别的原因挂了"
    finally:
        inst.stop()
