"""待归位项 · junction 那一头的代码，hmr 够不够得着

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/chx_hmr_across_junction/ -n 0 -s

装插件有两种落地形态，前面各项分别见过：

  * **代码就摆在 profile 目录里** —— 第 6 项那个 `greeter.mjs`，条目用相对路径引用
  * **代码在别处，装进来** —— 第 9、10 项那套：`package.json` 写一行 `link:`，
    `node_modules` 里建一条 junction 指过去，条目用**包名**引用

第 6 项证明了第一种形态改代码就热重载。这一项问第二种：**同样改代码，
链接那一头的文件动了，hmr 认不认？**

这不是「hmr 灵不灵」的问题，是**它盯的范围与代码的真实落点对不对得上**的问题。
五条用例把变量拆开，一次只动一个：

| | 代码在哪 | hmr 盯着哪 | `ignored` | 结果 |
|---|---|---|---|---|
| ① | profile 目录里 | profile 目录 | 默认 | **重载**（对照组：不走 junction 就是好的） |
| ② | 链接那一头 | profile 目录 | 默认 | 没反应 —— watcher 一声没出 |
| ③ | 链接那一头 | **源码真实路径** | 默认 | 没反应 —— watcher **还是**一声没出 |
| ④ | 链接那一头 | **那条 junction** | 默认 | watcher 出声了，但没重载 |
| ⑤ | 链接那一头 | 源码真实路径 | **去掉 `**/.*`** | **重载** |

①②只差一个 junction，②③只差 hmr 的 `root`，③④只差同一份代码的两条路径，
③⑤只差 `ignored` 里的一条 —— 哪一环断的，看哪两条的差就知道。

三个判定（详见各用例的 docstring）：

  * **经 junction 装进来的模块，URL 是链接那一头的真实路径**，不含 `node_modules`。
    所以 hmr 那三处 `url.includes('/node_modules/')` 一处都不命中 —— 挡住热重载的
    从来不是这几处硬编码。
  * **挡住它的是 watcher 的 `ignored`，而且是被 `**/.*` 误伤的**：筛的是
    `relative(watchBaseDir, path)`，watch base 之外的路径以 `..` 开头，Windows 上
    这串反斜杠路径被 picomatch 当成一整段，一段以点开头就成了「隐藏文件」。
  * **`root` 里的路径不做 realpath**，所以盯 junction 和盯它那一头不是一回事：
    watcher 报 junction 路径，`loadCache` 存真实路径，`Map.has` 认字符串。
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
    of_kind,
    read_events,
    reports,
    rmtree_safe,
    states_of,
    timeline,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"

#: 教学插件那个包的名字。链接形态下条目就用这个名字引用它。
PKG_NAME = "hmr-linked"

#: 插件代码里写着的那句话。用例把前者改成后者 —— 这就是「改代码」。
FIRST, SECOND = "第一版", "第二版"

#: 「验证什么都不该发生」用的固定等待。热重载是一两秒的事，15 秒远超它 ——
#: 这类断言不许轮询提前退出：提前退出只能证明「此刻还没发生」。
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

- insert:
    - id: greeter
      name: {entry_name}
"""


# ── 搭台 ────────────────────────────────────────────────────────────────────


def copy_package(dest: Path) -> Path:
    """把教学插件那个包拷一份到指定落点，用例只改这份拷贝。

    仓库里 `fixtures/hmr-linked/` 那份是**源**，从头到尾保持原样。用例要改的是
    包里的 `index.js`，改在拷贝上，跑多少次都不脏源。
    """
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
        placement: 代码落在哪。
            ``"inline"`` —— 包目录直接摆进 profile 目录，条目用相对路径引用文件。
            ``"linked"`` —— 包目录留在 profile 外面，靠 `link:` + junction 装进来，
            条目用包名引用（第 9、10 项那套供给形态）。
        watch: hmr 的 `root` 除了 `'.'` 还加什么。
            ``"profile"`` —— 什么都不加，就 `['.']`（默认值，也是 dsh-base 写的那个）。
            ``"source"`` —— 加**源码包目录的真实路径**。
            ``"junction"`` —— 加 **node_modules 里那条 junction 的路径**。
            后两个指的是磁盘上同一份代码的两条路径。
        ignored: hmr 的 `ignored` 名单。不传就不写这个键，走 schema 默认值
            ``['**/node_modules', '**/.*', 'cache', 'data']``。

    Returns:
        profile、事件流路径、**用例待会儿要改的那个 index.js**。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    # profile 目录不用建就能算出来，root 里要填的绝对路径靠它
    profile_dir = lab_home.root / "profiles" / name

    if placement == "inline":
        pkg_dir = copy_package(profile_dir / PKG_NAME)
        entry_name = f"./{PKG_NAME}/index.js"
    elif placement == "linked":
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
        entry_name = PKG_NAME
    else:
        raise ValueError(f"未知 placement：{placement}")

    junction_dir = profile_dir / "node_modules" / PKG_NAME
    extra = {"profile": [], "source": [pkg_dir.as_posix()], "junction": [junction_dir.as_posix()]}[watch]

    patch = BASE.format(
        timer=PKG_TIMER,
        hmr=PKG_HMR,
        roots=json.dumps(["."] + extra),
        ignored="" if ignored is None else f"        ignored: {json.dumps(ignored)}\n",
        out=json.dumps(events.as_posix()),
        entry_name=entry_name,
    )
    profile = lab_home.make_profile(name, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    if placement == "linked":
        # 装进来这件事要做两半：依赖声明一行、node_modules 里一条链接。
        # 缺哪半 Node 都找不到 `name: hmr-linked`（第 9 项讲过的那套）。
        profile.link_plugin(PKG_NAME, pkg_dir)

    return profile, events, pkg_dir / "index.js"


def edit_code(index_js: Path) -> None:
    """把插件代码里的「第一版」改成「第二版」—— 在编辑器里改一行就是这个动作。"""
    text = index_js.read_text(encoding="utf-8")
    assert FIRST in text, f"前提：{index_js} 里本来写着{FIRST}"
    index_js.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


# ── 读事件流 ────────────────────────────────────────────────────────────────


def said_versions(events: list[dict]) -> list[str]:
    """插件报过的「版本」，按时间顺序。"""
    return [e["data"]["版本"] for e in reports(events, who="greeter") if (e.get("data") or {}).get("版本")]


def said_note(events: list[dict], note: str) -> list[dict]:
    """插件报的某一类话里的 data。身份三件套靠这个取。"""
    return [e["data"] for e in reports(events, who="greeter") if e.get("note") == note and e.get("data")]


def wait_said(inst: Instance, path: Path, *, count: int, timeout: float = 40.0) -> list[str]:
    """等插件报到第 `count` 版为止 —— 验「应该发生的事」用轮询，比死等快也更稳。"""
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


def show_identity(events: list[dict]) -> str:
    """把插件报出的身份三件套排出来。这一项的观察式产出。"""
    rows = []
    for note in ("我的模块 URL", "树的 baseUrl", "loadCache 里跟我有关的 key"):
        for data in said_note(events, note):
            rows.append(f"  {note}：{json.dumps(data, ensure_ascii=False)}")
    return "\n".join(rows) or "  （插件没报出身份 —— 它压根没跑起来？）"


def show(events: list[dict]) -> str:
    return timeline(events, kinds=("report", "status"))


def hmr_noise(events: list[dict]) -> str:
    """hmr 自己报的动静。断在哪一环，看它有没有出声最直接。"""
    changes = [Path(str(e.get("url"))).name for e in of_kind(events, "hmr-change")]
    reloads = of_kind(events, "hmr-reload")
    return f"hmr-change {len(changes)} 条 {changes}　hmr-reload {len(reloads)} 条"


def boot(inst: Instance, events_path: Path) -> None:
    """等实例起来、插件报完第一版，再多留一秒让启动那一阵彻底走完。

    多留这一秒纯粹是为了看得清 —— 不留的话「启动」和「热重载」两拨事件挤在
    几百毫秒里，读起来费劲。判定不依赖它。
    """
    first = wait_said(inst, events_path, count=1)
    assert first == [FIRST], f"实例起来后插件该报一次版本，实际 {first}：\n{inst.logs()}"
    time.sleep(1.0)


# ── 用例 ────────────────────────────────────────────────────────────────────


def test_inline_package_reloads(lab_home: LabHome, launch):
    """① 对照组 · 包摆在 profile 目录里，改代码 → 重来一次。

    这一条不是来发现什么的，是来**证明这一项的观测手段有效**的：同一个包、
    同一种改法、同一套判据，只要代码不在链接那一头，它就该热重载。

    有了这条，后面几条要是不重载，就不能赖到「包这个形态有问题」头上 ——
    唯一的差别只剩 junction。
    """
    profile, events_path, index_js = build(lab_home, "inline", placement="inline", watch="profile")

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    got = wait_said(inst, events_path, count=2)

    events = read_events(events_path)
    print("\n══ ① 包摆在 profile 目录里 ═══════════════════════════════")
    print(f"  代码落点：{index_js}")
    print("  条目引用：./hmr-linked/index.js　hmr 盯着：['.']")
    print(f"  {hmr_noise(events)}")
    print(show_identity(events))
    print(f"  插件报过的版本：{got}")

    assert inst.alive(), f"实例应当一直活着 —— 热重载不是重启：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"代码在 profile 目录里就该热重载，实际 {got}"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "该条目应当跑起来两次（原来一次、改完又一次）"


def test_linked_package_default_root_notices_nothing(lab_home: LabHome, launch):
    """② 装进来的包 + 默认 `root: ['.']` —— 改代码，什么都不会发生。

    跟 ① 只差一件事：代码不在 profile 目录里了，是靠 junction 装进来的。
    hmr 盯的还是 profile 目录，而 profile 目录下通往这份代码的唯一路径要穿过
    `node_modules` —— 那正是 hmr 默认 `ignored` 名单上的第一项。
    """
    profile, events_path, index_js = build(lab_home, "default", placement="linked", watch="profile")

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    Instance.settle(SETTLE)

    events = read_events(events_path)
    print("\n══ ② 装进来的包，hmr 盯着 profile 目录 ═══════════════════")
    print(f"  代码落点：{index_js}")
    print(f"  条目引用：{PKG_NAME}（包名）　hmr 盯着：['.']")
    print(f"  {hmr_noise(events)}")
    print(show_identity(events))
    print(f"  插件报过的版本：{said_versions(events)}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said_versions(events) == [FIRST], "hmr 没盯着代码的真实落点，它不该被重新加载"
    assert states_of(events, "greeter").count("ACTIVE") == 1, "该条目从头到尾只该跑起来一次"


def test_watching_the_real_source_dir_is_silently_ignored(lab_home: LabHome, launch):
    """③ 把 `root` 扩到**源码目录的真实路径** —— 照样没反应，而且**连事件都没有**。

    跟 ② 只差 hmr 的 `root` 里多了一条绝对路径，而那条路径落在 profile 目录
    **外面**（前面几项测过的绝对路径都在里面）。

    判据落在 `hmr-change` 的**条数**上，不落在「重载了没有」上 —— 这是这一条与
    ④ 唯一分得开的地方：两条都不重载，但 ③ 是 watcher 从头到尾一声没出，
    ④ 是 watcher 出了声、后面才断。断在哪一环，就看这个数。

    ③ 断在 watcher 这一环，原因是 hmr 拿 `ignored` 名单去筛的不是原路径，而是
    `relative(watchBaseDir, path)` 的结果（`cordis-plugin-hmr/src/index.ts:231`）。
    源码目录在 watch base 外面，算出来的相对路径以 `..` 开头；Windows 的
    `relative()` 返回反斜杠，而 picomatch 不把反斜杠当路径分隔符 —— 整串被当成
    一个路径段，这一段以点开头，正好撞上默认 `ignored` 里的 `**/.*`（那条本意是
    「忽略隐藏文件」）。同一条路径换成正斜杠就不命中。

    所以这不是「chokidar 不认 watch base 之外的绝对路径」，是**隐藏文件规则
    误伤了向上走的相对路径**。⑤ 把 `**/.*` 拿掉，同样的配置立刻就通。
    """
    profile, events_path, index_js = build(lab_home, "source", placement="linked", watch="source")

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    Instance.settle(SETTLE)

    events = read_events(events_path)
    print("\n══ ③ hmr 盯着源码目录的真实路径 ═════════════════════════")
    print(f"  代码落点：{index_js}")
    print(f"  hmr 盯着：['.', '{index_js.parent.as_posix()}']")
    print(f"  {hmr_noise(events)}　← 一声没出，断在 watcher 这一环")
    print(show_identity(events))
    print(f"  插件报过的版本：{said_versions(events)}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said_versions(events) == [FIRST], "watcher 都没看见，它不该被重新加载"
    assert not of_kind(events, "hmr-change"), "这一条的特征是 watcher 一声没出 —— 有 hmr-change 就说明断点不在这儿"


def test_dropping_the_dotfile_rule_makes_it_work(lab_home: LabHome, launch):
    """⑤ 跟 ③ 一模一样，只把 `ignored` 里的 `**/.*` 拿掉 —— 立刻就热重载了。

    这是 ③ 那条判定的验证：配置只差这一项，结果从「一声不出」翻成「重载成功」，
    那么拦住 ③ 的就是这一项，不是别的。

    也就是说链路本身是通的 —— 模块 URL 经 junction 之后是链接那头的真实路径
    （①②③④ 报出的 URL 都证明了这点），所以 hmr 那三处
    `url.includes('/node_modules/')` 一处都不命中。真正卡住的只有 watcher 那道
    筛子，而且是被一条与 node_modules 毫无关系的规则误伤的。

    ⚠️ 拿掉 `**/.*` 的代价：watch 范围里的隐藏文件与目录（`.git` 那些）不再被
    忽略。这一项只为把机制钉死，不是在推荐这么配。
    """
    profile, events_path, index_js = build(
        lab_home, "nodot", placement="linked", watch="source", ignored=["**/node_modules", "cache", "data"]
    )

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    got = wait_said(inst, events_path, count=2, timeout=25.0)

    events = read_events(events_path)
    print("\n══ ⑤ 同样的配置，只去掉 ignored 里的 `**/.*` ═════════════")
    print(f"  代码落点：{index_js}")
    print(f"  hmr 盯着：['.', '{index_js.parent.as_posix()}']")
    print("  ignored：['**/node_modules', 'cache', 'data']（默认名单去掉 `**/.*`）")
    print(f"  {hmr_noise(events)}")
    print(f"  插件报过的版本：{got}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"去掉 `**/.*` 之后就该热重载了，实际 {got}"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "该条目应当跑起来两次"


def test_watching_the_junction_path(lab_home: LabHome, launch):
    """④ `root` 填的是 **node_modules 里那条 junction** —— 跟 ③ 是同一份代码的两条路径。

    磁盘上就一个 `index.js`，改它一次。区别只在告诉 hmr 的是哪条路：
    ③ 给的是链接那一头的真实路径，④ 给的是链接本身。

    结果：watcher **出声了**（跟 ③ 正相反 —— junction 路径落在 watch base 里面，
    算出来的相对路径不以 `..` 开头，躲过了那条隐藏文件规则；而 `**/node_modules`
    只匹配到 `node_modules` 这一段本身，匹配不上它下面的多段路径），但重载没发生。

    停在哪一步是确定的：`hmr-change` 这个事件只在 `loadCache.has(url)` 返回
    **false** 时才发（`cordis-plugin-hmr/src/index.ts:265-270`）。watcher 报的是
    junction 路径，模块加载时那个 URL 是链接那头的真实路径 —— 同一个文件，
    两个字符串，`Map.has` 认字符串。

    所以这条链路上确实有一处在拿**路径字符串**做等值判断。`watchBaseDir` 自己
    做过 realpath（`index.ts:216`），`root` 里给的路径没有。
    """
    profile, events_path, index_js = build(lab_home, "junction", placement="linked", watch="junction")
    junction_index = profile.dir / "node_modules" / PKG_NAME / "index.js"

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    Instance.settle(SETTLE)

    events = read_events(events_path)
    got = said_versions(events)
    print("\n══ ④ hmr 盯着 node_modules 里那条 junction ═══════════════")
    print(f"  改的是：　　{index_js}")
    print(f"  hmr 盯着：　{junction_index.parent.as_posix()}")
    print("  （磁盘上是同一个文件，两条路径）")
    print(f"  {hmr_noise(events)}")
    print(show_identity(events))
    print(f"  插件报过的版本：{got}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST], f"两条路径不等价，盯着 junction 不该导致重载，实际 {got}"
    assert of_kind(events, "hmr-change"), "这一条的特征恰恰是 watcher 出了声 —— 没有 hmr-change 就跟 ③ 混了"
    assert not of_kind(events, "hmr-reload"), "出了声也不该重载：报的路径不在 loadCache 里"
