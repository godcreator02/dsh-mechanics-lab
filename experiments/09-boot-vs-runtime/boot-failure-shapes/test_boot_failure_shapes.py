"""boot-failure-shapes · 启动失败的形态学

档次 ③ ｜ 性质 🔬 发现型 ｜ 状态 ✅ 已验（三种成因中的两种；「撞车」详情见
`duplicate-id-timing`）｜ 用例 8 条 ｜ 不需要 web

## 判定

- **「boot 挂了」不止一种成因，本项覆盖两种：**

  - **解析不到**——报错首句 `failed to import loader entry <id> (<name>)`。
    典型触发：`name` 指不到任何模块——文件不存在、少写扩展名、指到目录、
    少写 `./`、包没装进来、Windows 盘符绝对路径。
  - **依赖等不到**——报错首句 `dsh: N entries did not activate`。典型
    触发：`inject` 的服务永远不会出现，条目卡在 PENDING，被
    `boot-audit` 那道普查判死刑。
  - **撞车**（不在本项，见 `duplicate-id-timing`）——报错首句
    `duplicate loader entry id: <id>`。典型触发：两处 patch 用同一个
    id `insert`。

  证据：`test_unresolvable_name_kills_the_instance`（六种「解析不到」写法）、
  `test_unresolvable_and_unsatisfiable_share_the_same_verdict_shape`（「依赖
  等不到」的判词句式）。

- **`ERR_MODULE_NOT_FOUND` 底下还分两个词，决定往哪查。** `name` 是不是
  `./` 开头，决定 Node 把它当路径找还是当包名找：

  ```
  ./ 开头   → 当路径找，相对 profile 目录
             找不到 → Cannot find module '<完整路径>'
             指到目录 → ERR_UNSUPPORTED_DIR_IMPORT

  不带 ./   → 当包名找，去 node_modules 里翻
             找不到 → Cannot find package '<name>'
  ```

  说 **module** 的是按路径找、说 **package** 的是按包名找——看到 package
  就别再去核对文件在不在了，它压根没往那个方向找。这条坑最典型的样子是
  `tool.mjs`（漏了开头的 `./`）：文件明明就摆在旁边，报错却说找不到「包」。

- **成因不同，下场相同：一条挂不上是整树陪葬，不是「跳过它继续」。**
  同一次失败启动的事件流里，`timer`、`hmr`、观察器全都先跑到过 ACTIVE，
  紧接着被一起撤下来。「别的插件都好好的」不能当成自己那条没问题的证据
  ——真到那一步，实例根本没起来。证据：
  `test_the_others_ran_before_everything_came_down`。

- **「解析不到」跟「依赖等不到」判词句式不同，但「依赖等不到」内部不区分
  等的人是谁、等的是什么。** 你写的插件等一个自造的服务名，跟框架自带
  的 `hmr` 缺了它硬依赖的 `timer`，走的是同一条审计路径——判词句式一字
  不差（数字抹掉后完全相同）、同样退出码 1。这跟 `boot-audit` 里「提供者
  被禁用 vs 服务名从不存在」也是同一个结局的另一次印证：boot 期的审计
  只认「等到没等到」，不认原因。

## 观测方法

- 判词读**整份**日志文件（`inst.err_log`），不是 `inst.logs()` 的末尾几行
  ——启动早期的判词很容易被后面的输出挤出去；「解析不到」那句 `Error:
  dsh:` 更是固定出现在日志**开头**（第 5 行左右）。
- 「实例会死」是预期会发生的事，用轮询等（`while inst.alive(): sleep`），
  不用死等满超时。
- 事件流是补充证据：进程是崩着退的，采集器未必来得及把话说完，所以只
  断言「没出现过」这个方向——它不会因为少收几条事件而假失败。

## 没覆盖到的

- 「撞车」这第三种成因的机制细节（查重发生在创建任何条目之前、
  `EntryGroup.update()` 的查重循环在 `try` 块之外）不在本项——它是
  `duplicate-id-timing` 的主题，本项只在判定里点名，不重复验证。
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lab import (  # noqa: E402
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    entry_ids,
    read_events,
    reports,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

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

LAYOUT = ("tool.mjs", "toolbox")


def build(lab_home: LabHome, label: str, name: str) -> tuple[LabProfile, Path]:
    """搭一个实例，条目的 `name` 写成给定的样子。文件布局（tool.mjs + toolbox/）
    每次都原样摆好——写错的只有 name。
    """
    events = lab_home.root / f"events-{label}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    patch += f"""
- insert:
    - id: tool
      name: {json.dumps(name)}
"""
    profile = lab_home.make_profile(label, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(FIXTURES / "tool.mjs", profile.dir / "tool.mjs")
    shutil.copytree(FIXTURES / "toolbox", profile.dir / "toolbox", dirs_exist_ok=True)
    return profile, events


def wait_until_dead(inst: Instance, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)


def verdict(inst: Instance) -> str:
    """启动日志里那一句判词——`Error: dsh: ...` 开头的第一行。读 err 日志文件
    而不是 `inst.logs()`：判词在开头，取末尾若干行会正好把它切掉。
    """
    text = inst.err_log.read_text(encoding="utf-8", errors="replace") if inst.err_log.exists() else ""
    for line in text.splitlines():
        if line.startswith("Error: dsh:"):
            return line
    return ""


def error_code(inst: Instance) -> str:
    text = inst.err_log.read_text(encoding="utf-8", errors="replace") if inst.err_log.exists() else ""
    found = re.search(r"^Error \[(ERR_[A-Z_]+)\]", text, re.MULTILINE)
    return found.group(1) if found else ""


#: 六种「解析不到」的写法 + 错误代码 + 判词里的关键句。
CASES = [
    ("nofile", "文件不存在", "./typo.mjs", "ERR_MODULE_NOT_FOUND", "Cannot find module "),
    ("noext", "少写扩展名", "./tool", "ERR_MODULE_NOT_FOUND", "Cannot find module "),
    ("dir", "指到目录", "./toolbox", "ERR_UNSUPPORTED_DIR_IMPORT", "Directory import "),
    ("noslash", "少写 ./", "tool.mjs", "ERR_MODULE_NOT_FOUND", "Cannot find package 'tool.mjs'"),
    ("pkg", "包没装进来", "step5-not-linked", "ERR_MODULE_NOT_FOUND", "Cannot find package 'step5-not-linked'"),
    ("drive", "盘符绝对路径", "ABS", "ERR_UNSUPPORTED_ESM_URL_SCHEME", "must be valid file:// URLs"),
]


@pytest.mark.parametrize("label, what, name, code, phrase", CASES, ids=[c[0] for c in CASES])
def test_unresolvable_name_kills_the_instance(
    lab_home: LabHome, launch, label: str, what: str, name: str, code: str, phrase: str
):
    """六种「解析不到」的写法：实例一律起不来，退出码 1，日志点名是哪条、
    错在哪、错误代码是什么，且事件流里那个条目从没出现过——它连上树的
    机会都没有。
    """
    if name == "ABS":
        name = str(lab_home.root / "profiles" / label / "tool.mjs")

    profile, events_path = build(lab_home, label, name)
    for item in LAYOUT:
        assert (profile.dir / item).exists(), f"前提：{item} 确实摆在 profile 目录里"

    inst = launch(profile, wait_http=False)
    wait_until_dead(inst)

    line, got_code = verdict(inst), error_code(inst)
    events = read_events(events_path)

    print(f"\n══ {what}：name: {name} ══════════════════════")
    print(f"  实例还活着？  {inst.alive()}    退出码：{inst.proc.returncode}")
    print(f"  错误代码：    {got_code}")
    print(f"  判词：        {line}")
    print(f"  事件流里的条目：{sorted(entry_ids(events))}")

    assert not inst.alive(), f"实例居然活着——那这条挂不上就不是致命的了：\n{inst.logs()}"
    assert inst.proc.returncode == 1, f"预期退出码 1，实际 {inst.proc.returncode}"
    assert line, f"没找到 `Error: dsh:` 那句判词：\n{inst.logs(tail=80)}"
    assert f"loader entry tool ({name})" in line, f"判词该点名条目 id 与写的 name，实际：{line}"
    assert phrase in line, f"判词里该有「{phrase}」，实际：{line}"
    assert got_code == code, f"预期错误代码 {code}，实际 {got_code}"
    assert "tool" not in entry_ids(events), f"这条根本没挂上，不该出现在事件流里：{sorted(entry_ids(events))}"
    assert not reports(events, who="tool"), "它的 apply 不该跑过"


def test_the_others_ran_before_everything_came_down(lab_home: LabHome, launch):
    """一条挂不上，是整个实例陪葬，不是「跳过它继续」——同一次失败启动的
    事件流里，timer、hmr、观察器全都到过 ACTIVE，然后紧接着被撤下来。
    「别的插件好好的」不能当作「自己那条没问题」的证据。
    """
    profile, events_path = build(lab_home, "others", "./typo.mjs")

    inst = launch(profile, wait_http=False)
    wait_until_dead(inst)
    events = read_events(events_path)

    def went(entry_id: str, to: str) -> bool:
        return any(e.get("kind") == "status" and e.get("id") == entry_id and e.get("to") == to for e in events)

    print("\n══ 别的条目当时在干嘛 ════════════════════════════════════")
    for eid in ("timer", "hmr", "lab-recorder"):
        print(f"  {eid:<14} 到过 ACTIVE：{went(eid, 'ACTIVE')}")
    print(f"  观察器被撤下来：{went('lab-recorder', 'UNLOADING')}")

    assert not inst.alive(), "前提：这次启动是失败的"
    assert went("timer", "ACTIVE") and went("hmr", "ACTIVE"), (
        f"别的条目本该照常跑起来，事件流却不是这样：{sorted(entry_ids(events))}"
    )
    assert went("lab-recorder", "UNLOADING"), "跑起来的那些应当跟着一起被撤下来"


# ── 「解析不到」vs「依赖等不到」：同一堵墙，两种成因 ────────────────────────


#: 判词的句式：`<等的人>: pending (waiting for service: <等的东西>)`
PENDING_LINE = re.compile(r"^(?P<who>.+): pending \(waiting for service: (?P<what>.+)\)$")

ONLY_HMR = """- insert:
    - id: hmr
      name: '{hmr}'

    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
"""


def _build_locked(lab_home: LabHome, label: str) -> tuple[LabProfile, Path, Path]:
    events = lab_home.root / f"events-{label}.jsonl"
    witness = lab_home.root / f"witness-{label}.json"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, out=json.dumps(events.as_posix()))
    patch += f"""
- insert:
    - id: mine
      name: ./locked.mjs
      config:
        见证: {json.dumps(witness.as_posix())}
"""
    profile = lab_home.make_profile(label, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    shutil.copy2(FIXTURES / "locked.mjs", profile.dir / "locked.mjs")
    return profile, events, witness


def _verdicts(logs: str) -> list[str]:
    keep = [line.strip() for line in logs.splitlines() if "pending (waiting" in line or "did not activate" in line]
    return list(dict.fromkeys(keep))


def test_unresolvable_and_unsatisfiable_share_the_same_verdict_shape(lab_home: LabHome, launch):
    """两种不同成因的启动失败，收尾判词是同一个句式、同一个退出码。

    对照的是本组另一项（`boot-audit`）已经立住的那个机制：一个条目
    `inject` 了一个从没人提供的服务（这里是「开锁服务」），跟框架自带的
    `hmr` 缺了它硬依赖的 `timer`（本课的对照组：只写 hmr、不写 timer），
    走的是同一条审计路径——判词一字不差、下场一样（整个实例起不来，
    退出码 1）。「解析不到」（上面几条用例）是另一种成因，报错首句不同
    （import 失败 vs 审计失败），但同样是整树陪葬。
    """
    profile_a, events_a, witness_a = _build_locked(lab_home, "cmp-mine")
    inst_a = launch(profile_a, wait_http=False)
    wait_until_dead(inst_a)
    lines_a = _verdicts(inst_a.logs(tail=80))
    print("\n══ 依赖等不到：你写的插件等一个没人提供的服务 ═══════════")
    print(f"  进程还活着？ {inst_a.alive()}（退出码 {inst_a.proc.returncode}）")

    events_b = lab_home.root / "events-cmp-hmr.jsonl"
    profile_b = lab_home.make_profile(
        "cmp-hmr", bundles=[], patch=ONLY_HMR.format(hmr=PKG_HMR, out=json.dumps(events_b.as_posix()))
    )
    profile_b.link_plugin("lab-recorder", OBSERVER)
    inst_b = launch(profile_b, wait_http=False)
    wait_until_dead(inst_b)
    lines_b = _verdicts(inst_b.logs(tail=80))
    print("\n══ 依赖等不到：框架自带的 hmr 等 timer（对照组，本课没写 timer） ═")
    print(f"  进程还活着？ {inst_b.alive()}（退出码 {inst_b.proc.returncode}）")

    def parse(lines: list[str]) -> list[re.Match]:
        return [m for line in lines if (m := PENDING_LINE.match(line))]

    def summary(lines: list[str]) -> list[str]:
        rest = [line for line in lines if not PENDING_LINE.match(line)]
        return sorted(dict.fromkeys(re.sub(r"\d+", "…", line) for line in rest))

    got_a, got_b = parse(lines_a), parse(lines_b)
    print(f"\n  谁在等（name）→ 等的服务：{[(m['who'], m['what']) for m in got_a]}")
    print(f"  谁在等（name）→ 等的服务：{[(m['who'], m['what']) for m in got_b]}")

    assert not witness_a.exists(), "启动都失败了，locked 不该 apply 过"
    assert not inst_b.alive(), "只写 hmr 的实例该起不来"
    assert inst_a.proc.returncode == inst_b.proc.returncode == 1, (
        f"两边该是同一个退出码：{inst_a.proc.returncode} / {inst_b.proc.returncode}"
    )
    assert got_a and got_b, f"两边都该有 pending 那句判词：{lines_a} / {lines_b}"
    assert [m["what"] for m in got_a] == ["开锁服务"]
    assert [m["what"] for m in got_b] == ["timer"]
    assert summary(lines_a) == summary(lines_b), (
        f"收尾判词该完全一样，是同一个机制：\n  {summary(lines_a)}\n  {summary(lines_b)}"
    )
