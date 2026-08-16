"""第 5 步 · 挂不上，怎么查

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/step5_when_it_wont_load/ -n 0 -s

前四步里插件都挂上了。这一步把 `name` 一行行写错，看**错了会怎样、报错长什么样**。

插件文件（`fixtures/tool.mjs`）在每个用例里都原样放进 profile 目录，一个字没改。
变的只有条目上那一行 `name` —— 所以凡是没跑起来的，问题都在 `name` 上。

## 先记住一件事：一条挂不上，整个实例都起不来

不是「跳过这条、别的照跑」。进程直接退出，退出码 1。而且事件流会告诉你：
别的条目（timer、hmr、观察器）都已经跑完了，然后跟着一起被撤下来。
所以**排错的第一现场是启动日志**，不是实例里的什么面板 —— 实例根本没起来。

## 报错怎么读

日志里那一句判词长这样（写错的是 `./typo.mjs`）：

    Error: dsh: plugin tree failed to load: failed to apply loader entry include
    (cordis:include): failed to import loader entry tool (./typo.mjs): Cannot find
    module 'D:\\...\\profiles\\nofile\\typo.mjs' imported from D:\\...\\profiles\\nofile\\

三段，从后往前读最省事：

* **最后一段是真正的原因** —— Node 说它找不到什么，而且**把找过的完整路径印出来了**。
  拿这个路径去文件管理器里看一眼，多半当场就明白了
* **中间一段点名了是谁** —— `loader entry tool (./typo.mjs)`：条目 id 是 `tool`，
  它的 `name` 写的是 `./typo.mjs`。你写进 patch 文件的那两样原样回显
* 前面那句 `loader entry include (cordis:include)` 是框架自己那条，不是你的问题

紧接着还有一行带方括号的错误代码（`Error [ERR_MODULE_NOT_FOUND]: ...`），
**认代码比认句子快**，下面这张表就是按它分的。

## 六种写错，各自的报错

| 写错 | 错误代码 | 判词里的关键句 |
|---|---|---|
| `./typo.mjs` 文件不存在 | `ERR_MODULE_NOT_FOUND` | `Cannot find module '<完整路径>'` |
| `./tool` 少写扩展名 | `ERR_MODULE_NOT_FOUND` | `Cannot find module '<完整路径>\\tool'` |
| `./toolbox` 指到目录 | `ERR_UNSUPPORTED_DIR_IMPORT` | `Directory import '<完整路径>'` |
| `tool.mjs` 少写 `./` | `ERR_MODULE_NOT_FOUND` | `Cannot find package 'tool.mjs'` |
| `step5-not-linked` 包没装 | `ERR_MODULE_NOT_FOUND` | `Cannot find package 'step5-not-linked'` |
| `D:\\...\\tool.mjs` 盘符路径 | `ERR_UNSUPPORTED_ESM_URL_SCHEME` | `must be valid file:// URLs` |

后两句表格里放不下，完整原句是：

    Directory import '<完整路径>' is not supported resolving ES modules
    imported from <profile 目录>

    Only URLs with a scheme in: file, data, and node are supported by the
    default ESM loader. On Windows, absolute paths must be valid file:// URLs.
    Received protocol 'd:'

⚠️ **`module` 和 `package` 是两个词，别看串了。** 同样是 `ERR_MODULE_NOT_FOUND`：

* 说 **module** —— 你的 `name` 被当成**路径**，它按路径找，找不到那个文件
* 说 **package** —— 你的 `name` 被当成**包名**，它去装好的包里找，没这个包

分水岭就是开头那两个字符 `./`。`tool.mjs` 这种写法最坑：文件明明就躺在旁边，
报错却说找不到「包」—— 因为少了 `./`，它压根没往这个目录里找过。
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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

#: 前四步立起来的那三条，原样带过来
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

#: 每个用例里 profile 目录长这样（内容跟 fixtures/ 一模一样）：
#:
#:   tool.mjs          一个能跑的插件
#:   toolbox/          目录，里面是 index.mjs，同样能跑
#:
#: 两样东西每次都摆在那儿。写错的只有 name。
LAYOUT = ("tool.mjs", "toolbox")


def build(lab_home: LabHome, label: str, name: str) -> tuple[LabProfile, Path]:
    """搭一个实例，条目的 `name` 写成给定的样子。

    `name` 用 `json.dumps` 包一层再写进 patch 文件：Windows 路径里的反斜杠
    必须转义，直接拼字符串会被 YAML 吃掉。
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
    """等它退出。

    「实例会死」是**预期会发生的事**，所以用轮询等 —— 死了立刻往下走，
    不用干等满 30 秒。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and inst.alive():
        time.sleep(0.3)


def verdict(inst: Instance) -> str:
    """启动日志里那一句判词 —— `Error: dsh: ...` 开头的第一行。

    直接读 err 日志文件而不是 `inst.logs()`：判词在日志**开头**（第 5 行左右），
    取末尾若干行会正好把它切掉。
    """
    text = inst.err_log.read_text(encoding="utf-8", errors="replace") if inst.err_log.exists() else ""
    for line in text.splitlines():
        if line.startswith("Error: dsh:"):
            return line
    return ""


def error_code(inst: Instance) -> str:
    """判词下面那行方括号里的错误代码，如 `ERR_MODULE_NOT_FOUND`。"""
    text = inst.err_log.read_text(encoding="utf-8", errors="replace") if inst.err_log.exists() else ""
    found = re.search(r"^Error \[(ERR_[A-Z_]+)\]", text, re.MULTILINE)
    return found.group(1) if found else ""


#: 六种写错 + 它们的错误代码与关键句。
#:
#: `ABS` 是个占位符：盘符绝对路径要等 profile 目录定下来才能拼，见用例里那行。
CASES = [
    ("nofile", "文件不存在", "./typo.mjs", "ERR_MODULE_NOT_FOUND", "Cannot find module "),
    ("noext", "少写扩展名", "./tool", "ERR_MODULE_NOT_FOUND", "Cannot find module "),
    ("dir", "指到目录", "./toolbox", "ERR_UNSUPPORTED_DIR_IMPORT", "Directory import "),
    ("noslash", "少写 ./", "tool.mjs", "ERR_MODULE_NOT_FOUND", "Cannot find package 'tool.mjs'"),
    ("pkg", "包没装进来", "step5-not-linked", "ERR_MODULE_NOT_FOUND", "Cannot find package 'step5-not-linked'"),
    ("drive", "盘符绝对路径", "ABS", "ERR_UNSUPPORTED_ESM_URL_SCHEME", "must be valid file:// URLs"),
]


@pytest.mark.parametrize("label, what, name, code, phrase", CASES, ids=[c[0] for c in CASES])
def test_a_wrong_name_kills_the_instance(
    lab_home: LabHome, launch, label: str, what: str, name: str, code: str, phrase: str
):
    """`name` 写错的六种样子：实例一律起不来，退出码 1，日志里点名是哪条、写的什么。

    每个用例三样一起验，缺一样都会把结论读歪：

      * **进程状态** —— 死了，退出码 1（不是「起来了但那条没生效」）
      * **判词** —— 点名条目 id、原样回显你写的 `name`、给出错误代码与原因
      * **事件流** —— `tool` 从头到尾没出现过，它连上树的机会都没有
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

    assert not inst.alive(), f"实例居然活着 —— 那这条挂不上就不是致命的了：\n{inst.logs()}"
    assert inst.proc.returncode == 1, f"预期退出码 1，实际 {inst.proc.returncode}"

    assert line, f"没找到 `Error: dsh:` 那句判词：\n{inst.logs(tail=80)}"
    assert f"loader entry tool ({name})" in line, f"判词该点名条目 id 与你写的 name，实际：{line}"
    assert phrase in line, f"判词里该有「{phrase}」，实际：{line}"
    assert got_code == code, f"预期错误代码 {code}，实际 {got_code}"

    # 事件流是补充：进程是崩着退的，采集器未必来得及把话说完，所以这里只断言
    # 「tool 没出现过」—— 这个方向不会因为少收几条事件而假失败。
    assert "tool" not in entry_ids(events), f"这条根本没挂上，不该出现在事件流里：{sorted(entry_ids(events))}"
    assert not reports(events, who="tool"), "它的 apply 不该跑过"


def test_the_others_ran_before_everything_came_down(lab_home: LabHome, launch):
    """一条挂不上，是**整个实例陪葬**，不是「跳过它继续」。

    看的是同一次失败启动的事件流：timer、hmr、观察器全都到过 ACTIVE，
    然后紧接着被撤下来。所以「别的插件好好的」不能当作「我这条没问题」的证据。
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


def test_the_same_file_with_the_right_name_just_runs(lab_home: LabHome, launch):
    """对照组：一个字都不改，只把 `name` 写成 `./tool.mjs` —— 它就跑了。

    这条排除「插件本身有毛病」这种可能：前面那些失败全部只跟 `name` 有关。
    """
    profile, events_path = build(lab_home, "ok", "./tool.mjs")

    inst = launch(profile, wait_http=False)
    said = inst.wait_for(lambda: reports(read_events(events_path), who="tool"), timeout=40.0, what="tool 说话")

    print("\n══ 对照：同一份文件，name 写对 ═══════════════════════════")
    print(f"  实例还活着？  {inst.alive()}")
    print(f"  它说的话：    {[e.get('note') for e in said]}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said[0]["note"] == "工具插件跑起来了"
