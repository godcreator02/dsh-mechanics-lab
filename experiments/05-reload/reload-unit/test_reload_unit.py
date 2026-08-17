"""reload-unit · 重载的单位是插件入口

档次 ① ｜ 性质 🔬 ｜ 状态 ✅ ｜ 2 条用例 ｜ 不需要 web

## 判定

- **重载的单位是插件，不是条目。** 同一个包被两个条目挂着（bundle 层一条 +
  活层一条不同 id），改一次代码只发**一次** `hmr/reload`，但那一次里两个
  fiber 全部重挂——重挂循环遍历的是 `runtime.fibers`，一个 Plugin 的所有
  fiber。每个 fiber 各自沿用自己那份 `oldFiber._config`，重来之后报出的
  `config` 仍然各不相同。`test_both_layers_different_ids_both_reload`
- **拆文件缩不小重载范围。** 改一个只有一个纯函数、不碰 ctx 的 `helper.js`，
  `hmr/reload` 报出来的文件是 `index.js`——插件入口是原子重载单位。
  `partialReload` 从条目的 `name` 解析出入口，再看它的依赖树里有没有沾上被
  改的文件；沾上了就整个入口重新 import。所以「把纯逻辑拆出去以便单独热
  替换」这个想法不成立，代价跟改主文件一样。
  `test_editing_an_imported_helper_reloads_the_whole_plugin`
- **热重载换代有重叠窗口，不是「拆干净再建」。** 旧的先进 `UNLOADING`、新的
  紧接着开始建（`LOADING`），中间有一段两者并存的窗口，`hmr` 才报「重新加载
  了」，旧的这时才真正 `DISPOSED`。已实测：数据来自 `step6_hot_reload`（旧
  实验，判定已拆分吸收进本项与 `watch-root`）一轮真实运行的 `events.jsonl`
  时序——`greeter` 旧的 1506.5ms 进 `UNLOADING`、新的 1506.8ms 进 `LOADING`、
  1507.0ms `hmr` 报 `reload` 且旧的同一刻才 `DISPOSED`，整段换代约 700 微秒。
  当前树没有对这段时序单独断言，是历史观察记录，不是本项用例复现的不变量。
- **无关条目在热重载中纹丝不动。** 同一次热重载里只有被改的那个条目经历
  拆/建，其余条目一次都没被 `DISPOSED` 过。已实测：`watch-root` 项
  `test_root_dot_reloads_the_plugin` 对 `timer`/`hmr`/`lab-recorder` 三条逐一
  断言 `"DISPOSED" not in other_states`。

## 观测方法

判据落在两处：条目上报的字段是否变成新值（新代码/新实现确实生效了），以及
`hmr-reload` 事件的 `files` 字段与条数（重载单位、以及一次改动触发几次
`hmr/reload`，不是几个条目）。「重载了几次」与「重挂了几个条目」是两件
必须分开判的事——`test_both_layers_different_ids_both_reload` 里前者是 1、
后者是 2。
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lab import (  # noqa: E402
    LAB_ROOT,
    PKG_HMR,
    PKG_TIMER,
    Instance,
    LabHome,
    LabProfile,
    of_kind,
    read_events,
    reports,
    rmtree_safe,
    states_of,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
PKG_NAME = "hmr-linked"

FIRST, SECOND = "第一版", "第二版"
ALGO_FIRST, ALGO_SECOND = "算法第一版", "算法第二版"

BASE = """- insert:
    - id: timer
      name: '{timer}'

    - id: hmr
      name: '{hmr}'
      config:
        root: {roots}
        debounce: 100
{ignored}
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {out}
        flushMs: 100
{entry}"""


def copy_package(dest: Path) -> Path:
    """把教学插件那个包拷一份到指定落点，用例只改这份拷贝，仓库里的源保持原样。"""
    if dest.exists():
        rmtree_safe(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / PKG_NAME, dest)
    return dest


def build(
    lab_home: LabHome, name: str, *, placement: str, watch: str, ignored: list[str] | None = None, live_extra: str = ""
) -> tuple[LabProfile, Path, Path]:
    """搭一个 profile。

    Args:
        placement: ``"bundle"`` —— 源码留在 profile 外面，包名进
            `dsh.profile.bundles` 名单，条目由包自己那份 patch 生。
            ``"bundle-nested"`` —— 同上，但源码目录挪进 profile 目录里面。
        watch: hmr 的 `root` 填什么，``"source"`` 再加源码包目录的真实路径，
            ``"profile"`` 只有 `['.']`。
        live_extra: 追加到活层 patch 文件末尾的内容。用来在 bundle 层之外
            再挂一条**不同 id** 的条目（同 id 会撞车，那不是本项的范围）。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    profile_dir = lab_home.root / "profiles" / name

    if placement == "bundle":
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
    elif placement == "bundle-nested":
        pkg_dir = copy_package(profile_dir / "src" / PKG_NAME)
    else:
        raise ValueError(f"未知 placement：{placement}")

    roots = {"profile": ["."], "source": [".", pkg_dir.as_posix()]}[watch]

    patch = BASE.format(
        timer=PKG_TIMER,
        hmr=PKG_HMR,
        roots=json.dumps(roots),
        ignored="" if ignored is None else f"        ignored: {json.dumps(ignored)}\n",
        out=json.dumps(events.as_posix()),
        entry=live_extra,
    )
    profile = lab_home.make_profile(name, bundles=[PKG_NAME], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    profile.link_plugin(PKG_NAME, pkg_dir)

    return profile, events, pkg_dir / "index.js"


def edit_code(index_js: Path) -> None:
    text = index_js.read_text(encoding="utf-8")
    assert FIRST in text, f"前提：{index_js} 里本来写着{FIRST}"
    index_js.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


def edit_helper(pkg_dir: Path) -> Path:
    """把辅助文件里的「算法第一版」改成「算法第二版」，一个字不碰 index.js。"""
    helper = pkg_dir / "helper.js"
    text = helper.read_text(encoding="utf-8")
    assert ALGO_FIRST in text, f"前提：{helper} 里本来写着{ALGO_FIRST}"
    helper.write_text(text.replace(ALGO_FIRST, ALGO_SECOND), encoding="utf-8")
    return helper


def said_versions(events: list[dict], who: str = "greeter") -> list[str]:
    return [e["data"]["版本"] for e in reports(events, who=who) if (e.get("data") or {}).get("版本")]


def said_field(events: list[dict], field: str, who: str = "greeter") -> list:
    return [d[field] for e in reports(events, who=who) if field in (d := e.get("data") or {})]


def wait_said(inst: Instance, path: Path, *, count: int, who: str = "greeter", timeout: float = 40.0) -> list[str]:
    deadline = time.monotonic() + timeout
    got: list[str] = []
    while time.monotonic() < deadline:
        got = said_versions(read_events(path), who)
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


def test_both_layers_different_ids_both_reload(lab_home: LabHome, launch):
    """包进了 bundles 名单，活层又挂一条不同 id 的——改一次代码，两个条目都重来。

    值得测是因为 `partialReload` 的重挂循环遍历的是 `runtime.fibers`——一个
    Plugin 的所有 fiber。两个条目就是两个 fiber，各带各的 `oldFiber._config`。

    （同一个包被挂两次，`id` 撞了会导致挂载期抛 `duplicate loader entry id`、
    进程退出，那是另一件事，不在本项范围。这里测的是 `id` 不同、合法的情形。）
    """
    profile, events_path, index_js = build(
        lab_home,
        "twoids",
        placement="bundle",
        watch="source",
        ignored=["**/node_modules", "cache", "data"],
        live_extra="""
- insert:
    - id: greeter-live
      name: hmr-linked
      config:
        版本: 活层这条
""",
    )

    inst = launch(profile, wait_http=False)
    assert wait_said(inst, events_path, count=1, who="greeter") == [FIRST]
    assert wait_said(inst, events_path, count=1, who="greeter-live") == [FIRST]
    time.sleep(1.0)

    edit_code(index_js)
    bundle_side = wait_said(inst, events_path, count=2, who="greeter", timeout=25.0)
    live_side = wait_said(inst, events_path, count=2, who="greeter-live", timeout=25.0)

    events = read_events(events_path)
    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert bundle_side == [FIRST, SECOND], f"bundle 层那条该重来，实际 {bundle_side}"
    assert live_side == [FIRST, SECOND], f"活层那条也该重来，实际 {live_side}"
    for who in ("greeter", "greeter-live"):
        assert states_of(events, who).count("ACTIVE") == 2, f"{who} 应当跑起来两次"
    # 一次改动、一次重载事件，但里面装着两个 fiber
    assert len(of_kind(events, "hmr-reload")) == 1, "改一个文件只该有一次重载"


def test_editing_an_imported_helper_reloads_the_whole_plugin(lab_home: LabHome, launch):
    """改一个被 `import` 的辅助文件——重来的是整个插件入口，不是那个文件。

    `helper.js` 里只有一个纯函数，不碰 ctx、不注册任何东西。用例改它的实现，
    `index.js` 一个字不动。判据落在两处，缺一不可：插件报出的「算出来」变成
    新值（新实现确实生效了），以及 `hmr/reload` 事件里的文件名是
    `index.js`——重载的单位是插件入口，不是被改的那个文件。

    实际含义：把代码拆成多个文件缩不小重载范围。改一个几行的纯函数，付出的
    代价跟改主文件一样——整个插件 dispose 再装回来。
    """
    profile, events_path, index_js = build(lab_home, "helper", placement="bundle-nested", watch="profile")
    pkg_dir = index_js.parent

    inst = launch(profile, wait_http=False)
    first = wait_said(inst, events_path, count=1)
    assert first == [FIRST], f"实例起来后插件该报一次版本，实际 {first}：\n{inst.logs()}"
    time.sleep(1.0)
    assert said_field(read_events(events_path), "算出来") == [ALGO_FIRST]

    edit_helper(pkg_dir)
    inst.wait_for(
        lambda: len(said_field(read_events(events_path), "算出来")) >= 2, timeout=25.0, what="插件重新报出算出来的值"
    )

    events = read_events(events_path)
    algo = said_field(events, "算出来")
    reload_files = [f for e in of_kind(events, "hmr-reload") for f in (e.get("files") or [])]

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert algo == [ALGO_FIRST, ALGO_SECOND], f"新实现该生效，实际 {algo}"
    assert said_versions(events) == [FIRST, FIRST], "index.js 没改，那句话两次都该是第一版"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "整个条目该重挂一次"
    assert reload_files, "该有 hmr/reload 事件"
    assert all("index.js" in str(f) for f in reload_files), (
        f"重载单位是插件入口 index.js，不是被改的 helper.js，实际 {reload_files}"
    )
