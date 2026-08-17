"""insert-semantics · `- insert:` 是新增条目的唯一姿势

档次 ① ｜ 性质 ⚠️ 矫正型 ｜ 状态 ✅ 已验 ｜ 3 条用例 ｜ 不需要 web

## 判定

- **不带 `id` 的 `- insert:`，`insert` 列表原样追加进根组。** 官方文档展示过这种写法
  （`docs/official/zh/user/develop/basic/publish.md:56-62`、
  `docs/official/zh/user/develop/basic/config.md:36-43`），但没有明确说「追加进根组」这句话
  本身——这条从 `applyEntryPatches()` 源码坐实。`test_insert_without_id_appends_to_root` 已实测
- **带 `id` 的 `- insert:`，那个 `id` 指的是已存在的目标 group，`insert` 列表塞进它的 `config`
  数组——不是给新条目起名叫这个 id。** 文档完全没提这条语义，只能从 `cordis-plugin-include` 的
  `applyEntryPatches()`（`<npx 缓存>/node_modules/@deepseek-ai/cordis-plugin-include/src/index.ts:58-128`）
  读出来。目标存在但不是 group 时，只警告（`patch insert: entry "xxx" is not a group`）、**整条
  patch 被跳过**，不是报错中断，子条目一个都不会被创建，目标条目本身也毫发无损。
  `test_insert_with_id_targeting_non_group_warns_and_skips` 已实测
- **活层 insert 出来的条目，dump 把它的来源写在脸上。** bundle 层标包名，活层标那份 patch 文件的
  绝对路径，「这条是谁塞进来的」从不用猜。`test_entry_lands_in_composed_tree` 已实测

## 观测方法

`dsh --dump-config` 的 `renderConfigDump()` 与运行时挂载的 `Include.applyPatches()` 走的是同一个
`applyEntryPatches()` 调用，所以本项全部用例只用静态 `--dump-config`，不用拉真实例——静态算出来的
树和真实挂载走的是同一套 compose 逻辑，不是近似。

`lab.dump_config()` 成功时会静默丢弃 stderr，而 insert 的警告恰恰走 stderr、且从不影响退出码。本项
自己包一层 `dump_with_warnings()` 把 stderr 带出来判定，不改 `lab/dump.py`。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lab import DumpResult, LabError, LabHome, dsh_bin, dump_config, load_yaml


def dump_with_warnings(home: LabHome, profile_name: str) -> tuple[DumpResult, str]:
    """跑一次 `--dump-config`，同时要回 stderr。

    `renderConfigDump` 的警告走的是默认 `warn = (line) => process.stderr.write(line)`
    ——不进 stdout，也不改变退出码。`lab.dump_config()` 因为只关心组合树本身，
    成功时把 stderr 直接丢了；本项要判定的正是这些警告，所以自己跑一遍拿全。
    """
    argv = ["node", str(dsh_bin()), "--profile", profile_name, "--dump-config"]
    proc = subprocess.run(argv, env=home.env(), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise LabError(f"dump-config 失败：\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
    parsed = load_yaml(proc.stdout)
    if parsed is None:
        parsed = []
    return DumpResult(entries=parsed, raw=proc.stdout), proc.stderr


# ── 用例 1 · insert 不带 id → 追加进根组 ────────────────────────────────────


def test_insert_without_id_appends_to_root(lab_home, fixtures_dir):
    """最基本的语义：`- insert:` 不带 `id` 时，`insert` 列表原样追加进根组。"""
    profile = lab_home.make_profile("insert-root", bundles=[])
    profile.write_patch("""# insert 不带 id
- insert:
    - id: alpha
      name: dummy-alpha
    - id: beta
      name: dummy-beta
""")

    dump, stderr = dump_with_warnings(lab_home, profile.name)
    print(f"\n  组合树 id 列表：{dump.ids()}")
    print(f"  stderr：{stderr or '（空）'}")

    assert dump.ids() == ["alpha", "beta"], "两条 insert 应该按原样顺序进了根组"
    assert stderr.strip() == "", "这条 patch 完全合法，不该有任何警告"


# ── 用例 2 · insert 带 id 但目标不是 group ──────────────────────────────────


def test_insert_with_id_targeting_non_group_warns_and_skips(lab_home, fixtures_dir):
    """`insert:` 带的 `id` 是「目标 group」，不是新条目的 id。

    目标存在但不是 group（没有 `group: true`）时：只警告，插入被整体跳过——
    子条目一个都不会被创建，目标条目本身也毫发无损。
    """
    profile = lab_home.make_profile("insert-nongroup", bundles=[])
    profile.write_patch("""# insert 带 id，目标不是 group
- insert:
    - id: leaf
      name: dummy-leaf
      config:
        x: 1
- id: leaf
  insert:
    - id: child
      name: dummy-child
""")

    dump, stderr = dump_with_warnings(lab_home, profile.name)
    print(f"\n  组合树 id 列表：{dump.ids()}")
    print(f"  stderr：{stderr.strip() or '（空）'}")

    assert dump.entry("child") is None, "目标不是 group，子条目不该被创建"
    leaf = dump.require("leaf")
    assert leaf["config"] == {"x": 1}, "leaf 自身应该原封不动"
    assert 'patch insert: entry "leaf" is not a group' in stderr, f"应该有「不是 group」的警告，实际 stderr：{stderr!r}"


# ── 用例 3 · 活层条目落进组合树，来源写在脸上 ────────────────────────────────


def test_entry_lands_in_composed_tree(lab_home, fixtures_dir):
    """活层 `- insert:` 的条目会出现在组合树里，且 dump 把它的出身写在脸上。

    dump 对每个条目都标来源，两种层两种形式：
      bundle 层 → 包名（`@deepseek-ai/dsh-base`）
      活层     → 那份 patch 文件的绝对路径
    所以「这条是谁塞进来的」从来不用猜。
    """
    profile = lab_home.make_profile("insert-lands")
    profile.link_plugin("lab-minimal", fixtures_dir / "lab-minimal")
    witness = lab_home.root / "witness-lands.json"
    profile.write_patch(f"""# 活层 insert
- insert:
    - id: lab-minimal
      name: lab-minimal
      config:
        witness: {json.dumps(witness.as_posix())}
""")

    dump = dump_config(lab_home, profile.name)

    entry = dump.require("lab-minimal")
    assert entry["name"] == "lab-minimal"

    # 活层条目的来源 = 活层文件本身
    live_src = dump.source_of("lab-minimal")
    assert live_src is not None
    assert Path(live_src) == profile.patch_path

    # 对照：bundle 层条目的来源 = 包名
    bundle_src = dump.source_of("timer")
    assert bundle_src == "@deepseek-ai/dsh-base"

    print(f"\n  组合树共 {len(dump.entries)} 个条目")
    print(f"  lab-minimal 的来源：{live_src}")
    print(f"  timer 的来源      ：{bundle_src}")
