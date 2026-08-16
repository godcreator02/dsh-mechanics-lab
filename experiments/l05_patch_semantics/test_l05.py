"""L5 · patch 的三种语义

见同目录 README.md。一句话：`- insert:`（带/不带 id）与 `- id:` 覆盖各是什么语义，
以及几条文档没写、只能实测的边界（野字段、`null` 删键、跨层改前插条目、
找不到 id 时的静默跳过、`disabled: !!js` 的当前行为）。

唯一实现是 `cordis-plugin-include` 的 `applyEntryPatches()`（源码见
`<npx 缓存>/node_modules/@deepseek-ai/cordis-plugin-include/src/index.ts`）。
dump-config 和运行时挂载走的是**同一个函数**——`dsh-app-boot` 的
`renderConfigDump()`/`composeEntries()` 与 `Include.applyPatches()` 都直接调它
（`dsh-app-boot/lib/index.js` 的注释原话："the same single call boot() makes"）。
这就是本课除 disabled `!!js` 求值（运行时专属）和 duplicate-id boot 致命
（运行时专属）之外，其余用例都能靠 `--dump-config` 静态验证的原因——
静态算出来的树，跟真实挂载用的是同一套 compose 逻辑，不是近似。

⚠️ 唯一的坑：`lab.dump_config()` 只在失败时把 stderr 塞进异常里，成功时**静默丢弃**。
而 patch 的警告（`patch: entry ... not found` 这类）恰恰是走 stderr、且**不影响退出码**
（`renderConfigDump` 的默认 warn 只是 `process.stderr.write`，从不 throw）。
所以本课自己包一层 `dump_with_warnings()`，把 stderr 原样带出来——不改
`lab/dump.py`，只是在这个文件里多留一份 stderr。
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest
import yaml

from lab import DumpResult, JsExpr, LabError, dsh_bin

# ── 静态 dump + stderr（本课专用，不改 lab/dump.py） ─────────────────────────


class _L05Loader(yaml.SafeLoader):
    """跟 lab.dump._LabLoader 一样的 `!!js` 方言注册，本课自己留一份。"""


_L05Loader.add_constructor(
    "tag:yaml.org,2002:js",
    lambda loader, node: JsExpr(loader.construct_scalar(node)),
)


def dump_with_warnings(home, profile_name: str) -> tuple[DumpResult, str]:
    """跑一次 `--dump-config`，同时要回 stderr。

    `renderConfigDump` 的警告走的是默认 `warn = (line) => process.stderr.write(line)`
    ——**不进 stdout，也不改变退出码**。`lab.dump_config()` 因为只关心组合树本身，
    成功时把 stderr 直接丢了；本课要判定的正是这些警告，所以自己跑一遍拿全。

    dump-config 本身不 import 任何插件模块（只解析/合成 YAML），所以这里的
    `name` 字段可以随便写，不需要 `link_plugin` 出一个真能解析的包。
    """
    argv = ["node", str(dsh_bin()), "--profile", profile_name, "--dump-config"]
    proc = subprocess.run(
        argv,
        env=home.env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise LabError(f"dump-config 失败：\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
    parsed = yaml.load(proc.stdout, Loader=_L05Loader)
    if parsed is None:
        parsed = []
    return DumpResult(entries=parsed, raw=proc.stdout), proc.stderr


# ── 运行时辅助（只有用例 7、8 需要，其余用例全静态） ─────────────────────────


def _wait_for_file(path: Path, *, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.3)
    raise AssertionError(f"等了 {timeout}s，见证文件仍未出现：{path}")


def _assert_never_applies(witness: Path, *, seconds: float = 12.0) -> None:
    """验证 apply **不会**执行。固定长等待，不能轮询提前退出——
    提前退出只能证明「此刻还没发生」，证明不了「不会发生」。
    """
    time.sleep(seconds)
    assert not witness.exists(), f"apply 竟然执行了：{witness}"


def _watch_alive(inst, seconds: float) -> dict:
    """看着实例跑一段时间，如实记录死没死、退出码、日志。不做任何断言。"""
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
        "logs": inst.logs(tail=40),
    }


# ── 用例 1 · insert 不带 id → 追加进根组 ────────────────────────────────────


def test_insert_without_id_appends_to_root(lab_home, fixtures_dir):
    """最基本的语义：`- insert:` 不带 `id` 时，`insert` 列表原样追加进根组。"""
    profile = lab_home.make_profile("l05-insert-root", bundles=[])
    profile.write_patch("""# L5 用例 1：insert 不带 id
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
    profile = lab_home.make_profile("l05-insert-nongroup", bundles=[])
    profile.write_patch("""# L5 用例 2：insert 带 id，目标不是 group
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
    assert 'patch insert: entry "leaf" is not a group' in stderr, (
        f"应该有「不是 group」的警告，实际 stderr：{stderr!r}"
    )


# ── 用例 3 · null 到底删不删键 ───────────────────────────────────────────────


def test_null_sets_key_to_null_not_delete(lab_home, fixtures_dir):
    """patch 里写 `键: null`，那个键是被删掉了，还是变成字面 `null`？

    `applyEntryPatches` 的覆盖分支就是 `target[key] = value`——没有任何针对
    `null` 的特殊处理，`value` 是 `null` 就原样赋值。真正「`isNullable(value)` 就
    `delete candidate[key]`」的逻辑在 `cordis-plugin-loader` 的 `Entry.update()`
    里，但那段代码只在 `create === false` 时跑；YAML 批量重载的调用链
    （`Include._apply` → `EntryGroup.update` → `entry.update(options, true, true)`）
    永远传 `create=true`，走的是整份顶替（`candidate = options`），根本不会
    进那个 delete 分支。

    所以预期是：键还在，只是值变成了 `None`（YAML/Python 里 `null`/`None` 同一个东西）。
    """
    profile = lab_home.make_profile("l05-null", bundles=[])
    profile.write_patch("""# L5 用例 3：覆盖成 null
- insert:
    - id: solo
      name: dummy-solo
      disabled: true
- id: solo
  disabled: null
""")

    dump, stderr = dump_with_warnings(lab_home, profile.name)
    entry = dump.require("solo")
    print(f"\n  solo 条目：{entry}")
    print(f"  stderr：{stderr.strip() or '（空）'}")

    assert "disabled" in entry, "键应该还在——null 不是删除"
    assert entry["disabled"] is None, f"值应该是字面 null，实际是 {entry['disabled']!r}"


# ── 用例 4 · 同一叠里后面的 patch 能改前面 insert 插进来的条目 ──────────────


def test_later_patch_can_target_earlier_insert(lab_home, fixtures_dir):
    """`buildMap(insert)` 是有意为之：每次 insert 后立刻把新条目登记进索引，
    所以同一份 patch 列表里，后面的条目能找到前面 insert 刚插进来的那一行。
    """
    profile = lab_home.make_profile("l05-later-targets-earlier", bundles=[])
    profile.write_patch("""# L5 用例 4：同一叠内，后插改前插
- insert:
    - id: kid
      name: dummy-kid
      config:
        n: 1
- id: kid
  config:
    n: 2
""")

    dump, stderr = dump_with_warnings(lab_home, profile.name)
    print(f"\n  kid 的 config：{dump.config_of('kid')}")
    print(f"  stderr：{stderr.strip() or '（空）'}")

    assert dump.config_of("kid") == {"n": 2}, "后面那条 patch 应该改到了前面刚插进来的 kid"
    assert stderr.strip() == "", "这是条合法的覆盖，不该有警告"


# ── 用例 5 · 覆盖找不到 id → 只警告，同批其余 patch 照常生效 ────────────────


def test_missing_id_warns_and_skips_rest_still_applies(lab_home, fixtures_dir):
    """覆盖一个不存在的 id：只警告 + 跳过**这一条**，不影响同一批里其余的 patch。

    这跟「改配置没生效」是两种不同现象——一条 patch 打空不该让整批作废。
    """
    profile = lab_home.make_profile("l05-missing-id", bundles=[])
    profile.write_patch("""# L5 用例 5：覆盖找不到的 id
- insert:
    - id: alpha
      name: dummy-alpha
      config:
        x: 1
- id: no-such-id
  config:
    y: 2
- id: alpha
  config:
    x: 99
""")

    dump, stderr = dump_with_warnings(lab_home, profile.name)
    print(f"\n  alpha 的 config：{dump.config_of('alpha')}")
    print(f"  no-such-id 存在吗：{dump.entry('no-such-id') is not None}")
    print(f"  stderr：{stderr.strip() or '（空）'}")

    assert dump.entry("no-such-id") is None, "打空的那条 patch 不该凭空造出条目"
    assert dump.config_of("alpha") == {"x": 99}, (
        "打空的那条之后，同一批里对 alpha 的覆盖应该照常生效——不是整批作废"
    )
    assert 'patch: entry "no-such-id" not found' in stderr, (
        f"应该有「找不到 id」的警告，实际 stderr：{stderr!r}"
    )


# ── 用例 6 · 野字段被完整带着走 ───────────────────────────────────────────────


def test_arbitrary_fields_pass_through_patch(lab_home, fixtures_dir):
    """`applyEntryPatches` 和 `EntryOptions` 都没有字段白名单：覆盖分支就是
    `for (const [key, value] of Object.entries(overrides)) target[key] = value`，
    运行时是纯对象赋值，patch 能塞任意键，且不报任何错误或警告。
    """
    profile = lab_home.make_profile("l05-wild-field", bundles=[])
    profile.write_patch("""# L5 用例 6：野字段
- insert:
    - id: wild
      name: dummy-wild
- id: wild
  随便字段: "loader 不认识我"
  另一个字段: 42
""")

    dump, stderr = dump_with_warnings(lab_home, profile.name)
    entry = dump.require("wild")
    print(f"\n  wild 条目：{entry}")
    print(f"  stderr：{stderr.strip() or '（空）'}")

    assert entry["随便字段"] == "loader 不认识我"
    assert entry["另一个字段"] == 42
    assert stderr.strip() == "", "野字段不该触发任何警告——它不是非法，只是没人读"


# ── 用例 7 · disabled: !!js 当前是否生效（对照 postmortem 0002） ───────────


@pytest.mark.instance
@pytest.mark.parametrize(
    ("expr", "should_load"),
    [
        ("false", True),
        ("true", False),
    ],
    ids=["expr-false-loads", "expr-true-disabled"],
)
def test_disabled_js_expression_is_evaluated(
    lab_home, fixtures_dir, launch, expr, should_load
):
    """官方 postmortem 0002 记的根因是：`Entry.disabled` 直接读
    `entry.options.disabled`，从不对它插值——`!!js` 表达式解析成一个对象，
    对象恒真，所以文件系统插件永远被判定为「禁用」，不管表达式写的是什么。

    但当前 `cordis-plugin-loader/src/config/entry.ts` 的 `disabledOf()`：

        return isJsExpr(options.disabled)
          ? Boolean(this.evaluate(options.disabled.__jsExpr))
          : Boolean(options.disabled)

    ——**会**对 `!!js` 表达式求值。这条用例用最能分辨两种世界的写法验证现状：
    `!!js false` 和 `!!js true` 都是「语法合法的表达式对象」，如果 postmortem
    描述的 bug 仍在，两者都应该恒真 → 插件永远不加载；如果已经修复，
    两者的加载结果应该相反（`false` 加载、`true` 不加载）。

    这就是「语法合法 ≠ 该处被求值」的活教材——本课直接对照它验证当前行为。
    """
    tag = "t" if should_load else "f"
    witness = lab_home.root / f"w-jsdisabled-{tag}.json"
    profile = lab_home.make_minimal_profile(
        f"l05-jsdisabled-{tag}",
        patch=f"""# L5 用例 7：disabled 的 !!js 表达式当前会不会被求值
- insert:
    - id: probe
      name: lab-patch
      disabled: !!js {expr}
      config:
        witness: {json.dumps(witness.as_posix())}
""",
    )
    profile.link_plugin("lab-patch", fixtures_dir / "lab-patch")

    dump, _stderr = dump_with_warnings(lab_home, profile.name)
    # 静态 dump 里保留的是表达式原文，不是求值结果——这条本课 L2 已经验过，
    # 这里只顺手确认一下没有走样，重点在下面的运行时观察。
    assert dump.require("probe")["disabled"] == expr

    inst = launch(profile, wait_http=False)
    try:
        if should_load:
            got = _wait_for_file(witness)
            print(f"\n  !!js {expr} → 加载了：{got['marker']}")
        else:
            _assert_never_applies(witness)
            print(f"\n  !!js {expr} → 未加载（12s 内没写见证文件）")
    finally:
        inst.stop()


# ── 用例 8（可选）· 同 id 双挂载撞在 boot 期 → 进程起不来 ───────────────────


def test_duplicate_id_at_boot_is_fatal(lab_home, fixtures_dir, launch):
    """`EntryGroup.update()` 的查重循环在 `try` 块**之外**：

        for (const options of config) {
          const id = this.tree.ensureId(options)
          if (seen.has(id)) throw new TypeError(`duplicate loader entry id: ${id}`)
          seen.add(id)
        }

    抛错时一个 `create()` 都没调用。撞在**首次 boot**（本用例的场景）—— 这不是
    「回滚」，是那次 `EntryGroup.update` 从未成功过，`assertEntriesActivated`
    自然通不过，boot() 直接失败，整个进程死掉（不同于运行中热重放撞见同一个
    错误——那时只是这一次重放作废、旧条目继续跑，见 SYLLABUS L5 小节的注）。

    造法：两个独立的 `- insert:` 块（都不带 id，都追加进根组），
    但块里的条目**id 相同**——`applyEntryPatches` 本身不去重
    （它只在 insert 时 `buildMap` 建索引，从不检查冲突），所以两个条目会一起
    进最终的组合数组，冲突留到 `EntryGroup.update` 才被发现。
    """
    profile = lab_home.make_profile("l05-dup-boot", bundles=[])
    profile.link_plugin("lab-patch", fixtures_dir / "lab-patch")
    w1 = lab_home.root / "w-dup-1.json"
    w2 = lab_home.root / "w-dup-2.json"
    profile.write_patch(f"""# L5 用例 8：同 id 双挂载，撞在 boot 期
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
""")

    dump, stderr = dump_with_warnings(lab_home, profile.name)
    dup_entries = [e for e in dump.entries if isinstance(e, dict) and e.get("id") == "dup"]
    print(f"\n  静态 dump 里 id=dup 的条目数：{len(dup_entries)}（预期 2——applyEntryPatches 不去重）")
    print(f"  dump 阶段 stderr：{stderr.strip() or '（空，不是这里报错）'}")
    assert len(dup_entries) == 2, "两个 insert 块都该原样进了组合数组——冲突要留到挂载期才现形"

    inst = launch(profile, wait_http=False)
    got = _watch_alive(inst, seconds=15.0)

    print(f"\n  进程还活着？ {got['alive']}（退出码 {got['exit_code']}，死于 +{got['died_at']}s）")
    hit = [ln for ln in got["logs"].splitlines() if "duplicate loader entry id" in ln]
    print(f"  日志里的判词：{hit or '（没找到，看完整日志）'}")
    if not hit:
        print(got["logs"])

    assert not got["alive"], "boot 期撞见同 id 双挂载应当致命——进程不该活下来"
    assert hit, f"预期日志里有 'duplicate loader entry id'：\n{got['logs']}"
