"""ignore-rules · watcher 的 `ignored` 名单与 realpath 不对等

档次 ① ｜ 性质 🔬 ｜ 状态 ✅ ｜ 5 条用例 ｜ 不需要 web

## 判定

- **挡住经 junction 装进来的代码热重载的，是 watcher 的 `ignored`，而且是被
  `**/.*` 误伤的。** hmr 筛的是 `relative(watchBaseDir, path)`，watch base
  之外的路径以 `..` 开头；Windows 上这串反斜杠路径被 picomatch 当成一整段，
  一段以点开头就撞上了默认名单里「忽略隐藏文件」那条。
  `test_watching_the_real_source_dir_is_silently_ignored`
- **这条误伤只在源码位于 watch base 外面时发作，不是「junction 形态跟 hmr
  不兼容」。** 把 `**/.*` 拿掉，同样的配置立刻就通。
  `test_dropping_the_dotfile_rule_makes_it_work`
- **watcher 报出的路径从不做 realpath，`loadCache` 的 key 永远是 realpath**——
  两者不是同一个字符串，`Map.has` 判等失败，所以盯 junction 路径本身不生效，
  即便 watcher 确实报了变化。`test_watching_the_junction_path`
- **这条规律不分「你手填链接路径」还是「chokidar 自己爬进链接」**：profile
  里建一条 junction 指向外部源码、hmr 全默认配置，chokidar 确实跟着
  `followSymlinks` 爬了进去、报了变化，但报的是链接路径，同样对不上
  `loadCache`。`test_junction_inside_profile_pointing_out`
- **把源码搬进 profile 目录，两条规则都不用改。** 相对路径不再以 `..` 开头
  （躲开隐藏文件规则），也不含 `node_modules` 一段（躲开默认 ignored 第一
  项）。`test_source_nested_under_profile_needs_no_hmr_change`

充要条件（本项五条用例共同归结出的）：**watcher 报出的路径经 `pathToFileURL`
之后要跟 `loadCache` 的 key 字节相同**，而 `loadCache` 的 key 永远是
realpath、watcher 的路径从不 realpath——所以 watch 的入口必须本身就是真实
路径。

## 观测方法

`hmr-change` 事件的条数是关键信号，区分两种「不重载」：**watcher 一声没出**
（0 条 `hmr-change`）说明断点在 `ignored` 筛子这一层；**watcher 出了声但没
`hmr-reload`**（≥1 条 `hmr-change`，0 条 `hmr-reload`）说明断点在
`loadCache` 对账这一层。只看「重载了没有」分不出这两种断点。改代码后读插件
上报的「版本」判断是否重载；「不该重载」的用例固定等 15 秒，不许轮询提前
退出。

## 没覆盖到的

`root` 未扩展、默认配置下 junction 装进来的包完全没被 watcher 看见的那条基线
（对照组，watcher 一声不出）由 watch-root 项的 `test_linked_package_default_root_notices_nothing`
覆盖，不在本项重复。

`root`/`ignored` 两个键要「一起动」这件事，本项只验了一个方向——**只扩
`root` 不改 `ignored`**（`test_watching_the_real_source_dir_is_silently_ignored`：
watcher 一声不出）。另外两个方向没有用例，只有 `site/hmr-routes.html`「三个
必须」小节的陈述：**只写 `ignored: []`**（清空整份名单，不是去掉 `**/.*`
那一条）会不会把 `node_modules` 也纳入 watch 范围；**只改 `ignored`（比如去
掉 `**/.*`）不扩 `root`**，watch 范围有没有扩大过去。两条目前都只有源码
依据，没有实测佐证。
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
    entry_ids,
    make_junction,
    of_kind,
    read_events,
    reports,
    rmtree_safe,
    states_of,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"
PKG_NAME = "hmr-linked"

FIRST, SECOND = "第一版", "第二版"
SETTLE = 15.0

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

ENTRY = """
- insert:
    - id: greeter
      name: {entry_name}"""


def copy_package(dest: Path) -> Path:
    """把教学插件那个包拷一份到指定落点，用例只改这份拷贝，仓库里的源保持原样。"""
    if dest.exists():
        rmtree_safe(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / PKG_NAME, dest)
    return dest


def build(
    lab_home: LabHome, name: str, *, placement: str, watch: str, ignored: list[str] | None = None
) -> tuple[LabProfile, Path, Path]:
    """搭一个 profile。

    Args:
        placement: ``"linked"`` —— 源码留在 profile 外面，靠 `link:` + junction
            装进来，条目由用例写在活层，用包名引用。
            ``"bundle-nested"`` —— 同 bundle 自注册，但把源码目录挪进 profile
            目录**里面**，于是它落在 `root: ['.']` 的范围内，算出来的相对路径
            也不再以 `..` 开头。
            ``"junction-in"`` —— 源码留在 profile 外面，但 profile 里建一条
            `src` junction 指过去，watch 范围内因此存在一条通往源码的路，
            而且那条路不叫 `node_modules`。
        watch: hmr 的 `root` 填什么。``"profile"`` 是 `['.']`（默认值）；
            ``"source"`` 再加源码包目录的真实路径；``"junction"`` 再加
            `node_modules` 里那条 junction 的路径。
        ignored: hmr 的 `ignored` 名单。不传就不写这个键，走 schema 默认值
            ``['**/node_modules', '**/.*', 'cache', 'data']``。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    profile_dir = lab_home.root / "profiles" / name

    if placement == "linked":
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
        entry = ENTRY.format(entry_name=PKG_NAME)
    elif placement == "bundle-nested":
        pkg_dir = copy_package(profile_dir / "src" / PKG_NAME)
        entry = ""  # 条目归包自己那份 patch 生，活层不写
    elif placement == "junction-in":
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
        entry = ""
    else:
        raise ValueError(f"未知 placement：{placement}")

    junction_dir = profile_dir / "node_modules" / PKG_NAME
    roots = {"profile": ["."], "source": [".", pkg_dir.as_posix()], "junction": [".", junction_dir.as_posix()]}[watch]

    patch = BASE.format(
        timer=PKG_TIMER,
        hmr=PKG_HMR,
        roots=json.dumps(roots),
        ignored="" if ignored is None else f"        ignored: {json.dumps(ignored)}\n",
        out=json.dumps(events.as_posix()),
        entry=entry,
    )
    in_bundles = placement in ("bundle-nested", "junction-in")
    profile = lab_home.make_profile(name, bundles=[PKG_NAME] if in_bundles else [], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    profile.link_plugin(PKG_NAME, pkg_dir)
    if placement == "junction-in":
        # profile 里的第二条链接，指向源码目录的父级。跟 node_modules 那条指向
        # 同一份代码，区别只在这条落在 watch 范围内、而且名字不在 ignored 名单上。
        make_junction(profile.dir / "src", pkg_dir.parent)

    return profile, events, pkg_dir / "index.js"


def edit_code(index_js: Path) -> None:
    text = index_js.read_text(encoding="utf-8")
    assert FIRST in text, f"前提：{index_js} 里本来写着{FIRST}"
    index_js.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


def said_versions(events: list[dict], who: str = "greeter") -> list[str]:
    return [e["data"]["版本"] for e in reports(events, who=who) if (e.get("data") or {}).get("版本")]


def wait_said(inst: Instance, path: Path, *, count: int, timeout: float = 40.0) -> list[str]:
    deadline = time.monotonic() + timeout
    got: list[str] = []
    while time.monotonic() < deadline:
        got = said_versions(read_events(path))
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


def boot(inst: Instance, events_path: Path) -> None:
    first = wait_said(inst, events_path, count=1)
    assert first == [FIRST], f"实例起来后插件该报一次版本，实际 {first}：\n{inst.logs()}"
    time.sleep(1.0)


def test_watching_the_real_source_dir_is_silently_ignored(lab_home: LabHome, launch):
    """把 `root` 扩到源码目录的真实路径——照样没反应，而且连事件都没有。

    判据落在 `hmr-change` 的条数上，不落在「重载了没有」——这是这一条与
    `test_watching_the_junction_path` 唯一分得开的地方：两条都不重载，但这一条
    是 watcher 从头到尾一声没出，那一条是 watcher 出了声、后面才断。
    """
    profile, events_path, index_js = build(lab_home, "source", placement="linked", watch="source")

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    Instance.settle(SETTLE)

    events = read_events(events_path)
    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said_versions(events) == [FIRST], "watcher 都没看见，它不该被重新加载"
    assert not of_kind(events, "hmr-change"), "这一条的特征是 watcher 一声没出——有 hmr-change 就说明断点不在这儿"


def test_dropping_the_dotfile_rule_makes_it_work(lab_home: LabHome, launch):
    """跟上一条一模一样，只把 `ignored` 里的 `**/.*` 拿掉——立刻就热重载了。

    配置只差这一项，结果从「一声不出」翻成「重载成功」，说明拦住上一条的就是
    这一项，不是别的：模块 URL 经 junction 之后是链接那头的真实路径，hmr 那
    三处 `url.includes('/node_modules/')` 一处都不命中，真正卡住的只有 watcher
    那道筛子。

    ⚠️ 拿掉 `**/.*` 的代价：watch 范围里的隐藏文件与目录（`.git` 那些）不再被
    忽略。这一条只为把机制钉死，不是在推荐这么配。
    """
    profile, events_path, index_js = build(
        lab_home, "nodot", placement="linked", watch="source", ignored=["**/node_modules", "cache", "data"]
    )

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    got = wait_said(inst, events_path, count=2, timeout=25.0)

    events = read_events(events_path)
    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"去掉 `**/.*` 之后就该热重载了，实际 {got}"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "该条目应当跑起来两次"


def test_watching_the_junction_path(lab_home: LabHome, launch):
    """`root` 填的是 node_modules 里那条 junction——跟上面两条是同一份代码的另一条路径。

    磁盘上就一个 `index.js`，改它一次。区别只在告诉 hmr 的是哪条路：前两条给的
    是链接那一头的真实路径，这一条给的是链接本身。

    结果：watcher 出声了（junction 路径落在 watch base 里面，算出来的相对路径
    不以 `..` 开头，躲过了隐藏文件规则；而 `**/node_modules` 只匹配到
    `node_modules` 这一段本身，匹配不上它下面的多段路径），但重载没发生——
    `hmr-change` 只在 `loadCache.has(url)` 返回 false 时才发；watcher 报的是
    junction 路径，模块加载时那个 URL 是链接那头的真实路径，同一个文件两个
    字符串，`Map.has` 认字符串。
    """
    profile, events_path, index_js = build(lab_home, "junction", placement="linked", watch="junction")
    junction_index = profile.dir / "node_modules" / PKG_NAME / "index.js"

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    Instance.settle(SETTLE)

    events = read_events(events_path)
    got = said_versions(events)
    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST], f"两条路径不等价，盯着 junction 不该导致重载，实际 {got}"
    assert of_kind(events, "hmr-change"), "这一条的特征恰恰是 watcher 出了声——没有 hmr-change 就跟上一条混了"
    assert not of_kind(events, "hmr-reload"), "出了声也不该重载：报的路径不在 loadCache 里"
    assert junction_index.exists(), "junction 路径本身应当存在（供人对照磁盘布局）"


def test_source_nested_under_profile_needs_no_hmr_change(lab_home: LabHome, launch):
    """源码挪进 profile 目录里面——hmr 一个字不用改。

    要让 junction 装进来的代码热重载，通常得动 hmr 两个键（`root` 加一条、
    `ignored` 去一条），那两处改动都是为了对付同一件事：源码在 watch base
    外面。把源码挪进 profile 目录，这件事本身就没了：它落在 `root: ['.']`
    范围内，不用扩 `root`；算出的相对路径不以 `..` 开头也不含
    `node_modules` 一段，默认 `ignored` 原样就够用。junction、包名解析、
    bundle 自注册全在，只是源码物理位置挪了。
    """
    profile, events_path, index_js = build(lab_home, "nested", placement="bundle-nested", watch="profile")

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    got = wait_said(inst, events_path, count=2, timeout=25.0)

    events = read_events(events_path)
    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "greeter" in entry_ids(events), "包自己那份 patch 写的条目应当出现在树上"
    assert got == [FIRST, SECOND], f"源码在 watch base 里面，默认配置就该热重载，实际 {got}"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "该条目应当跑起来两次"


def test_junction_inside_profile_pointing_out(lab_home: LabHome, launch):
    """源码留在 profile 外面，但 profile 里建一条链接指过去——hmr 全默认配置，仍不重载。

    钻的是「改 hmr 两个键」与「把源码搬进 profile」之间那道缝：源码物理上留在
    profile 外面（没搬进去），`<profile>/src` 是一条 junction 指向源码目录的
    父级，hmr 一个字不改。于是 watch 范围内存在一条通往源码的路，而且那条路
    不叫 `node_modules`（躲开默认 ignored 第一项），也不以 `..` 开头（躲开
    `**/.*`）。

    结果仍然是不重载，失败形态跟 `test_watching_the_junction_path` 一样——
    watcher 出声了，重载没发生：chokidar 的 `followSymlinks` 默认为 true，
    它确实跟着这条 junction 走了进去，但它报出的是链接路径
    （`<profile>/src/...`），而 `loadCache` 存的是链接那头的真实路径，
    `Map.has` 认字符串，对不上。跟上一条不同的是那条是「你手填 junction
    路径」，这条是「chokidar 自己爬进去的」——两种方式殊途同归：watcher 从
    一个链接入口爬出来的每一条路径都保持链接形态。
    """
    profile, events_path, index_js = build(lab_home, "jin", placement="junction-in", watch="profile")
    via = profile.dir / "src" / PKG_NAME / "index.js"

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    got = wait_said(inst, events_path, count=2, timeout=25.0)
    if len(got) < 2:
        Instance.settle(8.0)  # 没等到就再坐实一会儿，别把「慢」读成「不会」
        got = said_versions(read_events(events_path))

    events = read_events(events_path)
    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST], f"watcher 报的是链接路径，跟 loadCache 对不上，不该重载，实际 {got}"
    assert of_kind(events, "hmr-change"), "chokidar 该跟着 junction 走进去并报出变化"
    assert not of_kind(events, "hmr-reload"), "报了也不该重载：那条路径不在 loadCache 里"
    assert via.exists(), "profile 里那条指向源码的链接本身应当存在（供人对照磁盘布局）"
