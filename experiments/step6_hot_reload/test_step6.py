"""第 6 步 · 改了代码想立刻生效

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/step6_hot_reload/ -n 0 -s

前面几步每改一次插件都得把实例停掉重开。这一步不用了 —— 干这件事的正是第 1 步
就写进 patch 文件、一直没解释过的那条 `hmr`：它盯着一个目录，文件一变就把对应的
插件重新加载一遍，实例不重启、别的条目不动。

盯哪个目录由它的 `config.root` 说了算：

  * `root: ['.']` —— 盯 profile 目录，**这也是不写 config 时的默认值**
  * `root: []` —— 一个目录都不盯，改代码没有任何反应

所以第 1 步那个实例其实已经能热重载了，只是当时没告诉你。
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
    read_events,
    reports,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
GREETER = Path(__file__).resolve().parent / "fixtures" / "greeter.mjs"

#: 插件里写着的那句话。用例把前者改成后者 —— 这就是「改代码」。
FIRST, SECOND = "第一版", "第二版"

BASE = """- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'
{hmr_config}
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100

- insert:
    - id: greeter
      name: ./greeter.mjs
"""

#: hmr 那条上什么 config 都不写
NO_CONFIG = ""


def hmr_config(root: str | None) -> str:
    """hmr 那条的 config 段。`root=None` 表示写一个空名单。"""
    roots = "[]" if root is None else f"['{root}']"
    return f"""      config:
        root: {roots}
"""


def build(lab_home: LabHome, name: str, *, config_block: str) -> tuple[LabProfile, Path, Path]:
    """搭一个实例：基础三条（hmr 的 config 由调用方给）+ 你写的那条。

    返回 profile、事件流路径、**插件文件在 profile 里的落点** —— 最后一个是
    这一步的主角，用例待会儿要去改它。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, hmr_config=config_block, out=json.dumps(events.as_posix()))
    profile = lab_home.make_profile(name, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    plugin_file = profile.dir / "greeter.mjs"
    shutil.copy2(GREETER, plugin_file)
    return profile, events, plugin_file


def said_versions(path: Path) -> list[str]:
    """插件说过的话里的版本号，按时间顺序。"""
    return [e["data"]["版本"] for e in reports(read_events(path), who="greeter") if e.get("data")]


def wait_until_said(inst: Instance, path: Path, *, count: int, timeout: float = 40.0) -> list[str]:
    """等插件说到第 `count` 次为止 —— 验「应该发生的事」用轮询，比死等快也更稳。"""
    deadline = time.monotonic() + timeout
    got: list[str] = []
    while time.monotonic() < deadline:
        got = said_versions(path)
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


def boot_and_wait_first(inst: Instance, events_path: Path) -> None:
    """等实例起来、插件说完第一句，再多留一秒让启动那一阵彻底走完。

    多留这一秒纯粹是为了看得清：不留的话「启动」和「热重载」两拨事件在时间线上
    挤在几百毫秒里，读起来费劲。判定不依赖它。
    """
    first = wait_until_said(inst, events_path, count=1)
    assert first == [FIRST], f"实例起来后插件该说一次话，实际 {first}：\n{inst.logs()}"
    time.sleep(1.0)


def edit_plugin(plugin_file: Path) -> None:
    """把插件文件里的「第一版」改成「第二版」—— 你在编辑器里改一行就是这个动作。"""
    text = plugin_file.read_text(encoding="utf-8")
    assert FIRST in text, "前提：插件文件里本来写着第一版"
    plugin_file.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


# ── 时间线 ──────────────────────────────────────────────────────────────────


def hot_timeline(events: list[dict]) -> str:
    """这一步专用的时间线：标准那几类照旧，另把 hmr 自己发的事件也留下。

    `timeline()` 默认只留「看得懂的那几类」，hmr 那几类不在其中 —— 而这一步要看的
    恰恰是它们夹在插件两次说话之间的位置。标准那几类仍旧交给 `timeline()` 渲染
    （一次喂一条），这里只补 hmr 那三类、以及重新加载期间那个还没认领 id 的条目
    该怎么写成人话。
    """
    rows = []
    for e in events:
        kind = str(e.get("kind"))
        # 列宽跟 `timeline()` 对齐，两边的行才排得成一张表
        ms = f"{e.get('ms', 0):8.1f}ms"
        if kind == "hmr-change":
            rows.append(f"  {ms}  {kind:<10} {'':<16} 文件变了：{Path(str(e.get('url'))).name}")
        elif kind == "hmr-reload":
            files = [Path(str(f)).name for f in (e.get("files") or [])]
            rows.append(f"  {ms}  {kind:<10} {'':<16} 重新加载了 {e.get('count')} 个：{files}")
        elif kind == "hmr-failed":
            rows.append(f"  {ms}  {kind:<10} {'':<16} 失败：{e.get('error')}")
        elif kind == "status":
            who = e.get("id") or f"({e.get('name')})"
            rows.append(f"  {ms}  {kind:<10} {str(who):<16} {e.get('from')} → {e.get('to')}")
        else:
            row = timeline([e])
            if row:
                rows.append(row)
    return "\n".join(rows)


def report_ms(events: list[dict]) -> list[float]:
    return [float(e["ms"]) for e in reports(events, who="greeter")]


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_rooted_hmr_reloads_the_plugin(lab_home: LabHome, launch):
    """配上 `root: ['.']`：改插件文件 → 它被重新加载 → **同一个插件第二次说话**。

    这一步全部三条判定都在这一条用例里：
      * 插件说了两次，第二次说的是新代码里的话
      * 实例自始至终没重启（进程还活着，别的条目一动没动）
      * 事件流里看得到重新加载的全过程
    """
    profile, events_path, plugin_file = build(lab_home, "rooted", config_block=hmr_config("."))

    inst = launch(profile, wait_http=False)
    boot_and_wait_first(inst, events_path)

    edit_plugin(plugin_file)
    got = wait_until_said(inst, events_path, count=2)

    events = read_events(events_path)
    print("\n══ 改一次代码，实例没重启 ════════════════════════════════")
    print(hot_timeline(events))

    ms = report_ms(events)
    print(f"\n插件说过的版本：{got}")
    print(f"两次说话：{ms[0]:.1f}ms → {ms[1]:.1f}ms（隔了 {ms[1] - ms[0]:.1f}ms，其中 1000ms 是用例自己在等）")

    assert inst.alive(), f"实例应当一直活着 —— 热重载不是重启：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"该说两次、且第二次是新代码里的话，实际 {got}"

    # 重新加载的全过程：旧的下去、新的上来，都记在同一条事件流里
    states = [e.get("to") for e in events if e.get("kind") == "status" and e.get("id") == "greeter"]
    assert states.count("ACTIVE") == 2, f"应当有两次 ACTIVE（旧的一次、新的一次），实际 {states}"
    assert "DISPOSED" in states, f"旧的那个应当被拆掉，实际走过 {states}"
    assert [e for e in events if e.get("kind") == "hmr-reload"], "事件流里应当有 hmr 报的重新加载"

    # 只有被改的那个插件重来，别的条目不受牵连
    for other in ("timer", "hmr", "lab-recorder"):
        other_states = [e.get("to") for e in events if e.get("kind") == "status" and e.get("id") == other]
        assert "DISPOSED" not in other_states, f"{other} 不该被牵连，却走过 {other_states}"


def test_no_config_means_the_default_root(lab_home: LabHome, launch):
    """hmr 那条上一个 config 都不写 —— 结果跟写 `root: ['.']` 一模一样。

    `root` 的默认值就是 `['.']`。第 1 步那个实例因此本来就在盯着 profile 目录。
    """
    profile, events_path, plugin_file = build(lab_home, "default", config_block=NO_CONFIG)

    inst = launch(profile, wait_http=False)
    boot_and_wait_first(inst, events_path)

    edit_plugin(plugin_file)
    got = wait_until_said(inst, events_path, count=2)

    print("\n══ 一个 config 都不写 ═══════════════════════════════════")
    print(hot_timeline(read_events(events_path)))
    print(f"\n插件说过的版本：{got}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"不写 config 也该热重载（默认 root 是 ['.']），实际 {got}"


def test_absolute_root_works_too(lab_home: LabHome, launch):
    """`root` 写成 profile 目录的绝对路径，效果跟 `'.'` 一样。

    连着上一条一起看：`'.'` 指的就是 profile 目录。
    """
    profile, events_path, plugin_file = build(lab_home, "absolute", config_block=NO_CONFIG)
    # profile 目录建好之后才知道绝对路径，所以 config 这时候才补写进 patch 文件
    profile.write_patch(
        profile.read_patch().replace(
            f"      name: '{PKG_HMR}'\n", f"      name: '{PKG_HMR}'\n" + hmr_config(profile.dir.as_posix())
        )
    )

    inst = launch(profile, wait_http=False)
    boot_and_wait_first(inst, events_path)

    edit_plugin(plugin_file)
    got = wait_until_said(inst, events_path, count=2)

    print("\n══ root 写绝对路径 ══════════════════════════════════════")
    print(f"  root: ['{profile.dir.as_posix()}']")
    print(f"  插件说过的版本：{got}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"绝对路径也该热重载，实际 {got}"


def test_root_pointing_elsewhere_notices_nothing(lab_home: LabHome, launch):
    """`root` 指着另一个目录：插件文件改了，什么都不会发生。

    这条说明 `root` 是真的在起作用 —— 不是「有 hmr 就热重载」。
    """
    profile, events_path, plugin_file = build(lab_home, "elsewhere", config_block=hmr_config("./elsewhere"))
    (profile.dir / "elsewhere").mkdir(exist_ok=True)

    inst = launch(profile, wait_http=False)
    boot_and_wait_first(inst, events_path)

    edit_plugin(plugin_file)
    Instance.settle(15.0)  # 验「不该发生」：固定长等待，不许轮询提前退出

    print("\n══ root 指着别处 ════════════════════════════════════════")
    print(hot_timeline(read_events(events_path)))
    print(f"\n插件说过的版本：{said_versions(events_path)}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said_versions(events_path) == [FIRST], "root 没盯着插件所在的目录，它不该被重新加载"


def test_empty_root_watches_nothing(lab_home: LabHome, launch):
    """`root: []` —— 明写着「一个目录都不盯」，改代码同样没有任何反应。"""
    profile, events_path, plugin_file = build(lab_home, "empty", config_block=hmr_config(None))

    inst = launch(profile, wait_http=False)
    boot_and_wait_first(inst, events_path)

    edit_plugin(plugin_file)
    Instance.settle(15.0)

    print("\n══ root: [] ═════════════════════════════════════════════")
    print(hot_timeline(read_events(events_path)))
    print(f"\n插件说过的版本：{said_versions(events_path)}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said_versions(events_path) == [FIRST], "root 是空的，插件不该被重新加载"
