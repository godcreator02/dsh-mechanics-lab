"""override-semantics · 裸 `- id:` 覆盖是整键赋值，不是深度合并

档次 ① ｜ 性质 📗 复述型（含四条 🔬 边界）｜ 状态 ✅ 已验 ｜ 6 条用例 ｜ 不需要 web

## 判定

- **覆盖替换目标行的整个 `config` 值，不深度合并各键；必须重述该行需要的每一个键。**
  `docs/official/zh/user/develop/basic/publish.md:123-126` 明文写了这条：「后应用的层按行胜出，
  且 patch 会替换目标行的整个 `config` 值，而不是深度合并各键。……你的 patch 可以按 `id` 覆盖前面
  各层的行……但必须重述该行需要的每一个键，而不是只写改动的那个。」
  `test_bare_id_changes_the_entry_that_is_already_there` 已实测坐实（前面写两个键，覆盖只写一个，
  另一个消失）
- **🔬 `null` 是字面赋值，不是删除。** `applyEntryPatches` 的覆盖分支是纯 `target[key] = value`，
  YAML 批量重载的调用链永远传 `create=true`，走不到 `Entry.update()` 里那段只在 `create=false` 才
  生效的 `delete` 分支。`test_null_sets_key_to_null_not_delete` 已实测：键还在，值变成字面 `None`
- **🔬 覆盖找不到 id：只警告、跳过这一条，同批其余 patch 照常生效。**
  `test_missing_id_warns_and_skips_rest_still_applies` 已实测；同一份文件里改一个不存在的 id 也是
  这个下场，`test_changing_an_id_that_is_not_there` 从「运行时条目会不会被静默创建」的角度补了一遍，
  而且验证了**日志里一个字都没有**——排查时不能指望日志会提示
- **🔬 覆盖分支没有字段白名单，野字段原样带着走、不报任何错误或警告。**
  `test_arbitrary_fields_pass_through_patch` 已实测
- **🔬 `disabled` 也能被后面一条覆盖关掉，不用回去改前面那条。**
  `test_bare_id_can_switch_disabled_on` 已实测

唯一实现是 `cordis-plugin-include` 的 `applyEntryPatches()`
（`<npx 缓存>/node_modules/@deepseek-ai/cordis-plugin-include/src/index.ts:58-128`）里的覆盖分支——
`for (const [key, value] of Object.entries(overrides)) target[key] = value`，纯对象赋值，没有任何
字段白名单，也没有对 `null` 的特殊处理。这解释了上面三条静态判定：整键替换（不是合并）、野字段不
过滤、`null` 只是字面赋值。

## 观测方法

`null` / 找不到 id / 野字段三条只用静态 `--dump-config` 判定——覆盖发生了什么，dump 和运行时挂载
走的是同一个 `applyEntryPatches()` 调用。但「改的是运行时已经挂上的那个条目」这条必须拉真实例：
static dump 分不清「先 insert 再 override」和「只 insert 了最终值」，只有让条目真的先挂一次、再看
它有没有被重新 apply、说的话变没变，才能验证「覆盖」和「重新创建」是两回事——
`test_bare_id_changes_the_entry_that_is_already_there` 断言 speaker 只说了一句话（`len(said) == 1`），
证明它没有被挂载两次。

`test_changing_an_id_that_is_not_there` 与 `test_bare_id_can_switch_disabled_on` 验证「不该发生」的
那一半用固定长等待（10 秒），不能用轮询提前退出——轮询提前退出只能证明「此刻还没发生」，证明不了
「不会发生」。

`lab.dump_config()` 成功时会静默丢弃 stderr，而覆盖的警告恰恰走 stderr、且从不影响退出码。本项自己
包一层 `dump_with_warnings()` 把 stderr 带出来判定，不改 `lab/dump.py`。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import yaml
from lab import (
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    DumpResult,
    Instance,
    JsExpr,
    LabError,
    LabHome,
    LabProfile,
    dsh_bin,
    entry_ids,
    read_events,
    reports,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ── 静态 dump + stderr（本项专用，不改 lab/dump.py） ─────────────────────────


class _Loader(yaml.SafeLoader):
    """跟 `lab.dump._LabLoader` 一样的 `!!js` 方言注册，本项自己留一份。"""


_Loader.add_constructor("tag:yaml.org,2002:js", lambda loader, node: JsExpr(loader.construct_scalar(node)))


def dump_with_warnings(home: LabHome, profile_name: str) -> tuple[DumpResult, str]:
    """跑一次 `--dump-config`，同时要回 stderr——`lab.dump_config()` 成功时会
    把它丢掉，而覆盖的警告正是走 stderr、且不影响退出码。
    """
    argv = ["node", str(dsh_bin()), "--profile", profile_name, "--dump-config"]
    proc = subprocess.run(argv, env=home.env(), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise LabError(f"dump-config 失败：\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}")
    parsed = yaml.load(proc.stdout, Loader=_Loader)
    if parsed is None:
        parsed = []
    return DumpResult(entries=parsed, raw=proc.stdout), proc.stderr


# ── 用例 1 · null 到底删不删键 ───────────────────────────────────────────────


def test_null_sets_key_to_null_not_delete(lab_home, fixtures_dir):
    """patch 里写 `键: null`，那个键是被删掉了，还是变成字面 `null`？

    `applyEntryPatches` 的覆盖分支就是 `target[key] = value`——没有任何针对
    `null` 的特殊处理，`value` 是 `null` 就原样赋值。真正「`isNullable(value)` 就
    `delete candidate[key]`」的逻辑在 `cordis-plugin-loader` 的 `Entry.update()`
    里，但那段代码只在 `create === false` 时跑；YAML 批量重载的调用链
    （`Include._apply` → `EntryGroup.update` → `entry.update(options, true, true)`）
    永远传 `create=true`，走的是整份顶替（`candidate = options`），根本不会
    进那个 delete 分支。预期：键还在，只是值变成了 `None`（YAML/Python 里
    `null`/`None` 同一个东西）。
    """
    profile = lab_home.make_profile("override-null", bundles=[])
    profile.write_patch("""# 覆盖成 null
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


# ── 用例 2 · 覆盖找不到 id → 只警告，同批其余 patch 照常生效 ────────────────


def test_missing_id_warns_and_skips_rest_still_applies(lab_home, fixtures_dir):
    """覆盖一个不存在的 id：只警告 + 跳过这一条，不影响同一批里其余的 patch。

    这跟「改配置没生效」是两种不同现象——一条 patch 打空不该让整批作废。
    """
    profile = lab_home.make_profile("override-missing-id", bundles=[])
    profile.write_patch("""# 覆盖找不到的 id
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
    assert dump.config_of("alpha") == {"x": 99}, "打空的那条之后，同一批里对 alpha 的覆盖应该照常生效——不是整批作废"
    assert 'patch: entry "no-such-id" not found' in stderr, f"应该有「找不到 id」的警告，实际 stderr：{stderr!r}"


# ── 用例 3 · 野字段被完整带着走 ───────────────────────────────────────────────


def test_arbitrary_fields_pass_through_patch(lab_home, fixtures_dir):
    """`applyEntryPatches` 和 `EntryOptions` 都没有字段白名单：覆盖分支就是
    `for (const [key, value] of Object.entries(overrides)) target[key] = value`，
    运行时是纯对象赋值，patch 能塞任意键，且不报任何错误或警告。
    """
    profile = lab_home.make_profile("override-wild-field", bundles=[])
    profile.write_patch("""# 野字段
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


# ── 动态用例：改的是已经挂上的那个条目 ──────────────────────────────────────

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

#: 先挂上 speaker，写两个 config 键，好看清后面覆盖动了什么
_MOUNTED = """
- insert:
    - id: speaker
      name: ./speaker.mjs
      config:
        台词: 原来的台词
        音量: 3
"""


def build_speaker_profile(lab_home: LabHome, fixtures_dir: Path, name: str, *, tail: str) -> tuple[LabProfile, Path]:
    """搭一个挂了 speaker 的实例，`tail` 原样接在 patch 文件后面。

    patch 文件是 YAML 数组，条目按写下的顺序一条条处理——「改已有条目」的那一条
    必须写在它要改的那条后面，直接拼字符串就行。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = _INFRA.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix())) + tail
    profile = lab_home.make_profile(name, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(fixtures_dir / "speaker.mjs", profile.dir / "speaker.mjs")
    return profile, events


def wait_for_speaker(inst: Instance, path: Path, *, timeout: float = 40.0) -> list[dict]:
    """等到 speaker 自己把话说出来为止。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        said = reports(read_events(path), who="speaker")
        if said:
            return said
        if not inst.alive():
            break
        time.sleep(0.3)
    return reports(read_events(path), who="speaker")


def wait_for_events(inst: Instance, path: Path, *, least: int = 5, timeout: float = 40.0) -> list[dict]:
    """等观察器把事件刷出来——用于「speaker 不该说话」那类用例的起跑线。"""
    deadline = time.monotonic() + timeout
    events: list[dict] = []
    while time.monotonic() < deadline:
        events = read_events(path)
        if len(events) >= least:
            return events
        if not inst.alive():
            break
        time.sleep(0.3)
    return events


def only_report(said: list[dict]) -> dict:
    assert said, "speaker 没说话——它的 apply 可能压根没跑"
    return said[0]["data"]


def log_lines(inst: Instance, needle: str) -> list[str]:
    """从实例的完整日志里挑出带某个词的行（去掉颜色码）。

    读的是整份日志文件，不是 `inst.logs()` 的末尾几行——启动早期的判词很容易被
    后面的输出挤出去。
    """
    hits = []
    for path in (inst.err_log, inst.out_log):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            plain = _ANSI.sub("", line).strip()
            if needle in plain:
                hits.append(plain)
    return hits


def test_bare_id_changes_the_entry_that_is_already_there(lab_home: LabHome, fixtures_dir: Path, launch):
    """不带 `insert` 的那条改掉了前面那条的 `config`——speaker 报出来的是新值。

    顺带验证整键赋值：前面写了两个键，覆盖时只写了一个，另一个就没了——不是
    把新键并进旧的里面。
    """
    profile, events_path = build_speaker_profile(
        lab_home,
        fixtures_dir,
        "override",
        tail=_MOUNTED
        + """
- id: speaker
  config:
    台词: 改过的台词
""",
    )

    inst = launch(profile, wait_http=False)
    said = wait_for_speaker(inst, events_path)
    events = read_events(events_path)

    print("\n══ 前面挂一条，后面改一条 ════════════════════════════════")
    print(timeline(events, kinds=("report",)))

    got = only_report(said)
    print("\n  patch 里先写的：  {'台词': '原来的台词', '音量': 3}")
    print("  后面那条改成：    {'台词': '改过的台词'}")
    print(f"  speaker 实际收到：{json.dumps(got['内容'], ensure_ascii=False)}")
    print(f"  speaker 一共说了几句：{len(said)}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got["内容"] == {"台词": "改过的台词"}, f"应当收到改过之后的 config，实际 {got['内容']}"
    assert len(said) == 1, f"speaker 只该有一份、说一句——说了 {len(said)} 句就说明它被挂了不止一次"


def test_changing_an_id_that_is_not_there(lab_home: LabHome, fixtures_dir: Path, launch):
    """把 id 打错一个字母：那一条作废，同一个文件里其余的照常生效，而且没有
    任何提示。

    三条摆在一起——挂上 speaker、改一个不存在的 `speakr`、再改一次 speaker。
    中间那条不会变成一个新条目，也不会让实例起不来，日志里更是一个字都没有。
    """
    profile, events_path = build_speaker_profile(
        lab_home,
        fixtures_dir,
        "typo",
        tail=_MOUNTED
        + """
- id: speakr
  config:
    台词: 这条打空了

- id: speaker
  config:
    台词: 后面这条照样生效
""",
    )

    inst = launch(profile, wait_http=False)
    said = wait_for_speaker(inst, events_path)
    events = read_events(events_path)

    got = only_report(said)
    ids = sorted(entry_ids(events))
    noise = log_lines(inst, "speakr") + log_lines(inst, "patch")

    print("\n══ 改一个不存在的 id ═════════════════════════════════════")
    print(f"  实例还活着？        {inst.alive()}")
    print(f"  出现过的条目：      {ids}")
    print(f"  speaker 收到的：    {json.dumps(got['内容'], ensure_ascii=False)}")
    print(f"  日志里说了什么：    {noise or '（一个字都没有）'}")

    assert inst.alive(), f"实例应当照常活着——打空一条不是致命错误：\n{inst.logs()}"
    assert "speakr" not in ids, f"打错的那个 id 不该凭空变成一个条目，实际 {ids}"
    assert got["内容"] == {"台词": "后面这条照样生效"}, f"同一个文件里后面那条该照常生效，实际 {got['内容']}"
    assert not noise, f"这一条是悄悄作废的，日志里不该有任何提示，实际 {noise}"


def test_bare_id_can_switch_disabled_on(lab_home: LabHome, fixtures_dir: Path, launch):
    """`disabled` 也改得掉：前面挂上的那条，后面一条就能把它关掉，不用回去改
    前面那条——前面那行原样留着，关不关由后面那条说了算。
    """
    profile, events_path = build_speaker_profile(
        lab_home,
        fixtures_dir,
        "switch-off",
        tail=_MOUNTED
        + """
- id: speaker
  disabled: true
""",
    )

    inst = launch(profile, wait_http=False)
    wait_for_events(inst, events_path, least=5)

    # 验「不该发生」：固定等一段，不能轮询提前退出
    Instance.settle(10.0)
    events = read_events(events_path)
    said = reports(events, who="speaker")

    print("\n══ 后面一条把它关掉 ══════════════════════════════════════")
    print(f"  实例还活着？        {inst.alive()}")
    print(f"  出现过的条目：      {sorted(entry_ids(events))}")
    print(f"  speaker 说的话：    {[e.get('note') for e in said] or '（一句都没有）'}")

    assert inst.alive(), f"实例应当照常活着——关掉一个条目不是错误：\n{inst.logs()}"
    assert not said, f"speaker 已经被关掉了，不该说话：{said}"
