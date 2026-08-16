"""待归位项 · junction 那一头的代码，hmr 够不够得着

**你不用做任何事，跑一下看输出就行：**

    uv run pytest experiments/chx_hmr_across_junction/ -n 0 -s

插件落地有三种形态，前面各项分别见过：

  * **代码就摆在 profile 目录里** —— 第 6 项那个 `greeter.mjs`，条目用相对路径引用
  * **代码在别处，装进来** —— `package.json` 写一行 `link:`，`node_modules` 里建
    一条 junction 指过去，条目用**包名**写在活层
  * **装进来 + 自注册** —— 上一种再加两样：包里声明 `dsh.bundle.patch`、包名进
    `dsh.profile.bundles` 名单，于是条目由**包自己那份 patch** 生，活层一个字不写。
    这是 publish.md 讲的分发形态，第 10 项见过它的配方那一面

第 6 项证明了第一种形态改代码就热重载。这一项问后两种：**同样改代码，
链接那一头的文件动了，hmr 认不认？**

这不是「hmr 灵不灵」的问题，是**它盯的范围与代码的真实落点对不对得上**的问题。
七条用例把变量拆开，一次只动一个：

| | 源码在哪 | 条目从哪来 | hmr 盯着哪 | `ignored` | 结果 |
|---|---|---|---|---|---|
| ① | profile 目录里 | 活层 | profile 目录 | 默认 | **重载**（对照组：不走 junction 就是好的） |
| ② | profile 外面 | 活层 | profile 目录 | 默认 | 没反应 —— watcher 一声没出 |
| ③ | profile 外面 | 活层 | **源码真实路径** | 默认 | 没反应 —— watcher **还是**一声没出 |
| ④ | profile 外面 | 活层 | **那条 junction** | 默认 | watcher 出声了，但没重载 |
| ⑤ | profile 外面 | 活层 | 源码真实路径 | **去掉 `**/.*`** | **重载** |
| ⑥ | profile 外面 | **包自注册** | 源码真实路径 | 去掉 `**/.*` | **重载**（跟 ⑤ 一样） |
| ⑦ | **profile 里面** | 包自注册 | profile 目录 | 默认 | **重载**（hmr 一个字没改） |
| ⑨ | profile 外面 | 包自注册 | profile 目录，里面有条 junction 指出去 | 默认 | watcher 出声了，但没重载 |

②③⑤⑥⑦⑨ 都是 junction 装进来、用包名引用的形态。①②只差一个 junction，
②③只差 hmr 的 `root`，③④只差同一份代码的两条路径，③⑤只差 `ignored` 里的一条，
⑤⑥只差条目写在哪一层，⑥⑦只差源码放在磁盘的哪个位置 —— 哪一环断的，
看哪两条的差就知道。

**能不能热重载，归结为一个充要条件**：watcher 报出的那条路径，`pathToFileURL`
之后要跟 `loadCache` 的 key 字节相同。而 `loadCache` 的 key 永远是 realpath
（Node 解析模块时就 realpath 了），watcher 报的路径**从不 realpath**——它保持你
给它的入口形态，从那个入口爬出来的每条路径也一样。所以：**watch 的入口必须
本身就是真实路径。** ①⑤⑥⑦ 满足它，②③ 连爬都没爬到，④⑨ 爬到了但入口是链接。

⑧⑩ 各问一件别的事：

  * **⑧** —— ⑦ 那个形态下**同时**改代码和改包里那份 patch 的 `config`，
    拿到的是哪一头的新值。答案是**新代码配旧配方**。
  * **⑩** —— 包进了 bundles 名单、活层**又挂一条不同 id 的**（同 id 会撞车，
    那堵墙归第 10 项）。改一次代码，**两个条目都重来**，各自沿用各自的 `config`。
  * **⑪** —— 同 id 的撞车分两种时机：启动时撞进程退出（第 10 项），
    **运行中撞则被兜住**——整次更新回滚，原条目毫发无损，实例继续健康。

七个判定（详见各用例的 docstring）：

  * **经 junction 装进来的模块，URL 是链接那一头的真实路径**，不含 `node_modules`。
    所以 hmr 那三处 `url.includes('/node_modules/')` 一处都不命中 —— 挡住热重载的
    从来不是这几处硬编码。
  * **挡住它的是 watcher 的 `ignored`，而且是被 `**/.*` 误伤的**：筛的是
    `relative(watchBaseDir, path)`，watch base 之外的路径以 `..` 开头，Windows 上
    这串反斜杠路径被 picomatch 当成一整段，一段以点开头就成了「隐藏文件」。
  * **误伤只在源码位于 watch base 外面时发作**。源码在里面，算出来的相对路径
    不以 `..` 开头，默认 `ignored` 原样就能用（⑦）—— 所以这不是「junction 形态
    与 hmr 不兼容」，是「向上走的相对路径与那条隐藏文件规则不兼容」。
  * **watcher 报出的路径从不做 realpath**，所以盯链接和盯链接那一头不是一回事：
    watcher 报链接路径，`loadCache` 存真实路径，`Map.has` 认字符串。你手填 junction
    路径（④）和让 chokidar 自己跟着 junction 爬进去（⑨），结果一样。
  * **条目从哪一层来不影响它能不能被热重载**：bundle 层生的条目跟活层写的条目在
    同一棵树上（两种形态报出的 `baseUrl` 都是 profile 目录），重载路径完全一样。
    跟第 10 项摆在一起看：**bundle 层的配方是冷的，但配方指向的代码是热的** ——
    改包里那份 `cordis.patch.yml` 要重启，改它指向的 `index.js` 不用。
  * **代码热重载不换 config，拿到的是「新代码 + 旧配方」**（⑧）。重载走
    `registry.plugin(plugin, oldFiber._config, ...)`，明写着沿用旧 fiber 的配置；
    而 bundle 层的配方本来就冷（`composed.bundlePatches` 是 boot 时读好的常量数组，
    `dsh/lib/profile-boot-DG5t9aNs.js:170,242`）。两件事叠一起，看起来就像
    「配置改了没生效」。⑧ 还坐实了「冷」的证据形态：那份 patch 文件落在 watch
    范围内、watcher **报了**它的变化（事件流里 `hmr-change` 点名 `cordis.patch.yml`），
    但它不是任何 include 的 filename、也不在 `loadCache` 里，于是掉进「只发个事件」
    的分支 —— **不是没人看见，是看见了没人管。**
  * **重载的单位是插件，不是条目**（⑩）。同一个包被两个条目挂着时，改一次代码
    发**一次** `hmr/reload`，但那一次里两个 fiber 全部重挂 —— 重挂循环遍历的是
    `runtime.fibers`，一个 Plugin 的所有 fiber。每个 fiber 各自沿用自己那份
    `oldFiber._config`，所以两条重来之后报出的 `config` 仍然各不相同。
  * **配置路径的失败是事务性的，而且被兜住**（⑪）。运行中把活层改成跟 bundle 层
    撞 id：`entry.update()` 整个 apply 失败（判词 `failed to apply loader entry
    include (cordis:include): duplicate loader entry id: greeter`），于是**整棵树
    一点不动** —— 原条目状态序列停在 `['LOADING', 'ACTIVE']`，连 `DISPOSED` 都
    没有。hmr 这边只记两条 warn、发一个 `hmr/config-update-failed`，进程照跑，
    之后改代码照样热重载。**所以活层改错了不会搞死实例**，它回到上一个好状态。
    跟启动时撞车正好成对：那时没有「上一个好状态」可退，只能退出进程。
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
    entry_ids,
    make_junction,
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

#: 包里那份 patch 的 config 里写着的那句话。用例把前者改成后者 —— 这是「改配方」。
CFG_FIRST, CFG_SECOND = "配置第一版", "配置第二版"

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
{entry}"""

#: 活层里那条 greeter。**bundle 形态下这块必须留空** —— 包自己那份 patch 已经
#: 生了同一个 `id`，活层再写一条就是两层撞同 id，挂载期抛 duplicate loader
#: entry id，实例当场退出（第 10 项那堵墙）。
ENTRY = """
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
    lab_home: LabHome, name: str, *, placement: str, watch: str, ignored: list[str] | None = None, live_extra: str = ""
) -> tuple[LabProfile, Path, Path]:
    """搭一个 profile。

    Args:
        placement: 代码落在哪、条目从哪来。
            ``"inline"`` —— 包目录直接摆进 profile 目录，条目用相对路径引用文件。
            ``"linked"`` —— 包目录留在 profile 外面，靠 `link:` + junction 装进来，
            **条目由用例写在活层**，用包名引用。
            ``"bundle"`` —— 装法同上，但包名进 `dsh.profile.bundles` 名单，
            **条目由包自己那份 `cordis.patch.yml` 生**，活层一个字不写。
            这才是 publish.md 描述的分发形态；`"linked"` 是把「装进来」和
            「自注册」拆开之后的前一半。
        watch: hmr 的 `root` 除了 `'.'` 还加什么。
            ``"profile"`` —— 什么都不加，就 `['.']`（默认值，也是 dsh-base 写的那个）。
            ``"source"`` —— 加**源码包目录的真实路径**。
            ``"junction"`` —— 加 **node_modules 里那条 junction 的路径**。
            后两个指的是磁盘上同一份代码的两条路径。
        ignored: hmr 的 `ignored` 名单。不传就不写这个键，走 schema 默认值
            ``['**/node_modules', '**/.*', 'cache', 'data']``。
        live_extra: 追加到活层 patch 文件末尾的内容。bundle 形态下用它再挂一条
            **不同 id** 的条目（同 id 会撞车，那是第 10 项的墙）。

    Returns:
        profile、事件流路径、**用例待会儿要改的那个 index.js**。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    # profile 目录不用建就能算出来，root 里要填的绝对路径靠它
    profile_dir = lab_home.root / "profiles" / name

    if placement == "inline":
        pkg_dir = copy_package(profile_dir / PKG_NAME)
        entry = ENTRY.format(entry_name=f"./{PKG_NAME}/index.js")
    elif placement == "linked":
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
        entry = ENTRY.format(entry_name=PKG_NAME)
    elif placement == "bundle":
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
        entry = ""  # 条目归包自己那份 patch 生，活层不写
    elif placement == "bundle-nested":
        # 同 bundle，只把源码目录挪进 profile 目录**里面** —— 于是它落在
        # `root: ['.']` 的范围内，算出来的相对路径也不再以 `..` 开头
        pkg_dir = copy_package(profile_dir / "src" / PKG_NAME)
        entry = ""
    elif placement == "junction-in":
        # 源码留在 profile **外面**，但 profile 里建一条 `src` junction 指过去。
        # 于是 watch 范围内存在一条通往源码的路，而且那条路不叫 node_modules。
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
        entry = ""
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
        entry=entry + live_extra,
    )
    in_bundles = placement in ("bundle", "bundle-nested", "junction-in")
    profile = lab_home.make_profile(name, bundles=[PKG_NAME] if in_bundles else [], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    if placement != "inline":
        # 装进来这件事要做两半：依赖声明一行、node_modules 里一条链接。
        # 缺哪半 Node 都找不到 `name: hmr-linked`（第 9 项讲过的那套）。
        # 进不进 bundles 名单是**另一件事**，由 placement 单独决定。
        profile.link_plugin(PKG_NAME, pkg_dir)
    if placement == "junction-in":
        # profile 里的第二条链接，指向源码目录的父级。它跟 node_modules 那条指的
        # 是同一份代码，区别只在这条落在 watch 范围内、而且名字不在 ignored 名单上。
        make_junction(profile.dir / "src", pkg_dir.parent)

    return profile, events, pkg_dir / "index.js"


def edit_code(index_js: Path) -> None:
    """把插件代码里的「第一版」改成「第二版」—— 在编辑器里改一行就是这个动作。"""
    text = index_js.read_text(encoding="utf-8")
    assert FIRST in text, f"前提：{index_js} 里本来写着{FIRST}"
    index_js.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


def edit_bundle_config(pkg_dir: Path) -> Path:
    """把**包里那份 patch** 的 config 从「配置第一版」改成「配置第二版」。

    跟 `edit_code` 是两个不同的动作：那个改代码，这个改配方。⑧ 同时做这两件事，
    看重载之后拿到的是哪一头的新值。
    """
    patch = pkg_dir / "cordis.patch.yml"
    text = patch.read_text(encoding="utf-8")
    assert CFG_FIRST in text, f"前提：{patch} 里本来写着{CFG_FIRST}"
    patch.write_text(text.replace(CFG_FIRST, CFG_SECOND), encoding="utf-8")
    return patch


# ── 读事件流 ────────────────────────────────────────────────────────────────


def said_versions(events: list[dict], who: str = "greeter") -> list[str]:
    """某个条目报过的「版本」，按时间顺序。"""
    return [e["data"]["版本"] for e in reports(events, who=who) if (e.get("data") or {}).get("版本")]


def said_pairs(events: list[dict]) -> list[tuple[str, str | None]]:
    """插件每次报出的（代码里那个版本, config 里那个版本），按时间顺序。

    ⑧ 的判据 —— 两个来路分开看，才分得出「新代码 + 旧配方」这种组合。
    """
    out = []
    for e in reports(events, who="greeter"):
        data = e.get("data") or {}
        if data.get("版本"):
            out.append((data["版本"], data.get("配置版本")))
    return out


def said_note(events: list[dict], note: str) -> list[dict]:
    """插件报的某一类话里的 data。身份三件套靠这个取。"""
    return [e["data"] for e in reports(events, who="greeter") if e.get("note") == note and e.get("data")]


def wait_said(inst: Instance, path: Path, *, count: int, who: str = "greeter", timeout: float = 40.0) -> list[str]:
    """等某个条目报到第 `count` 版为止 —— 验「应该发生的事」用轮询，比死等快也更稳。"""
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


def test_bundle_self_registered_entry(lab_home: LabHome, launch):
    """⑥ 真正的分发形态 · 条目由**包自己那份 patch** 生，活层一个字不写。

    前面五条的条目都是用例手写在活层的，那是把「装进来」和「自注册」拆开之后的
    前一半。publish.md 讲的分发形态是整套：包里声明 `dsh.bundle.patch`，用户把
    包名加进 `dsh.profile.bundles`，条目就自己上树。

    跟 ⑤ 只差这一件事 —— 装法、`root`、`ignored` 全部照搬 ⑤ 那套已经验过能重载的
    配置。所以这一条问的是：**条目从哪一层来，影不影响它能不能被热重载。**

    值得单测是因为重载路径上有一处依赖条目所在的树：`partialReload` 反查插件时，
    拿的是 `entry.parent.tree.ctx.baseUrl` 当解析基点、`entry.options.name` 当要
    解析的名字（`cordis-plugin-hmr/src/index.ts:409-417`）。bundle 层的条目跟活层
    的条目要是不在同一棵树上，这个基点就变了，`hmr-linked` 这个包名能不能从新基点
    解析出来是另一回事 —— 解析抛错会被 catch 吞掉，只留一条 warn。
    """
    profile, events_path, index_js = build(
        lab_home, "selfreg", placement="bundle", watch="source", ignored=["**/node_modules", "cache", "data"]
    )

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    got = wait_said(inst, events_path, count=2, timeout=25.0)

    events = read_events(events_path)
    print("\n══ ⑥ 条目由包自己那份 patch 生（真正的分发形态）═══════════")
    print(f"  bundles 名单：{[PKG_NAME]}　活层写的条目：无")
    print(f"  代码落点：{index_js}")
    print(f"  hmr 盯着：['.', '{index_js.parent.as_posix()}']　ignored 去掉了 `**/.*`")
    print(f"  {hmr_noise(events)}")
    print(show_identity(events))
    print(f"  插件报过的版本：{got}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "greeter" in entry_ids(events), "包自己那份 patch 写的条目应当出现在树上"
    assert got == [FIRST, SECOND], f"条目从哪一层来不该影响热重载，实际 {got}"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "该条目应当跑起来两次"


def test_source_nested_under_profile_needs_no_hmr_change(lab_home: LabHome, launch):
    """⑦ 同 ⑥ 的分发形态，只把源码目录挪进 profile 目录里面 —— **hmr 一个字不用改**。

    ⑤⑥ 都得动 hmr 两个键（`root` 加一条、`ignored` 去一条）才通。那两处改动
    都是为了对付同一件事：源码在 watch base **外面**。

    把源码挪进 profile 目录，这件事本身就没了：

      * 它落在 `root: ['.']` 的范围内，不用扩 `root`
      * `relative(watchBaseDir, path)` 算出的是 `src\\hmr-linked\\index.js` ——
        不以 `..` 开头，撞不上 `**/.*`；也不含 `node_modules` 那一段，
        撞不上 `**/node_modules`。默认 `ignored` 原样留着就行

    junction 照旧（`node_modules/hmr-linked` 指向 `<profile>/src/hmr-linked`），
    包名引用照旧，`dsh.profile.bundles` 照旧，包里那份 patch 照旧。变的只有
    源码放在磁盘的哪个位置。

    这一条跟 ① 不是一回事：① 没有 junction、条目用相对路径直接指文件。这里
    junction、包名解析、bundle 自注册全在，只是 watch 范围恰好罩住了源码。
    """
    profile, events_path, index_js = build(lab_home, "nested", placement="bundle-nested", watch="profile")

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    edit_code(index_js)
    got = wait_said(inst, events_path, count=2, timeout=25.0)

    events = read_events(events_path)
    print("\n══ ⑦ 源码挪进 profile 目录，hmr 用默认配置 ═══════════════")
    print(f"  bundles 名单：{[PKG_NAME]}　活层写的条目：无")
    print(f"  代码落点：{index_js}")
    print(f"  junction：{(profile.dir / 'node_modules' / PKG_NAME).as_posix()}")
    print("  hmr 盯着：['.']　ignored：默认（一个字没改）")
    print(f"  {hmr_noise(events)}")
    print(show_identity(events))
    print(f"  插件报过的版本：{got}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "greeter" in entry_ids(events), "包自己那份 patch 写的条目应当出现在树上"
    assert got == [FIRST, SECOND], f"源码在 watch base 里面，默认配置就该热重载，实际 {got}"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "该条目应当跑起来两次"


def test_junction_inside_profile_pointing_out(lab_home: LabHome, launch):
    """⑨ 源码留在 profile 外面，但 profile 里建一条链接指过去 —— hmr 全默认配置。

    这一条钻的是 ⑤⑦ 之间那道缝。⑤ 要改 hmr 两个键，⑦ 要把源码搬进 profile。
    要是两样都不想做呢：

      * 源码物理上留在你自己的工作目录（**没搬进 profile**）
      * `<profile>/src` 是一条 junction，指向源码目录的父级
      * hmr 一个字不改：`root: ['.']`、默认 `ignored`

    于是 watch 范围内**存在一条通往源码的路**，而且那条路不叫 `node_modules`——
    躲开了 ② 撞上的那条规则；它也不以 `..` 开头——躲开了 ③ 撞上的那条。

    结果：**不重载**，失败形态跟 ④ 一模一样 —— watcher 出声了，重载没发生。

    两件事一次问清了：chokidar 的 `followSymlinks` 默认为 true，它**确实**跟着这条
    junction 走了进去（所以有 `hmr-change`）；但它报出的是**链接路径**
    （`<profile>/src/...`），而 `loadCache` 存的是链接那头的真实路径，`Map.has`
    认字符串，对不上。

    ④ 是你手填 junction 路径，⑨ 是 chokidar 自己爬进去的 —— **两种方式都报链接
    路径**。所以「`root` 里的路径不做 realpath」这条判定的适用面比 ④ 单独看要宽：
    不只是你填的入口，watcher 从那个入口爬出来的每一条路径都保持链接形态。
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
    print("\n══ ⑨ profile 里一条链接指向外面的源码，hmr 全默认 ════════")
    print(f"  源码真身：　{index_js}")
    print(f"  profile 里的那条路：{via}")
    print("  hmr 盯着：['.']　ignored：默认（一个字没改）")
    print(f"  {hmr_noise(events)}")
    print(show_identity(events))
    print(f"  插件报过的版本：{got}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST], f"watcher 报的是链接路径，跟 loadCache 对不上，不该重载，实际 {got}"
    assert of_kind(events, "hmr-change"), "chokidar 该跟着 junction 走进去并报出变化"
    assert not of_kind(events, "hmr-reload"), "报了也不该重载：那条路径不在 loadCache 里"


def test_both_layers_different_ids_both_reload(lab_home: LabHome, launch):
    """⑩ 包进了 bundles 名单，活层**又挂一条不同 id 的** —— 两个条目都重来。

    「进 bundles 的同时也在活层 insert」有两种下场，取决于 `id` 撞不撞：

      * **同 id** —— 实例起不来。两层拼起来那是两个条目、`id` 撞了，挂载期抛
        `duplicate loader entry id`，进程当场退出。那堵墙归第 10 项，这里不重复。
      * **不同 id** —— 合法。同一个包被挂两次，两个条目各有各的 `config`。

    这一条测后者，问的是：**改一次代码，两个条目都会重来吗？**

    值得测是因为 `partialReload` 的重挂循环遍历的是
    `runtime.fibers`（`cordis-plugin-hmr/src/index.ts:503-508`）—— 一个 Plugin 的
    所有 fiber。两个条目就是两个 fiber，各带各的 `oldFiber._config`。

    配置照搬 ⑥ 那套已验能热重载的（源码在外 + `root` 加真实路径 + 去掉 `**/.*`），
    只多一条活层条目。
    """
    profile, events_path, index_js = build(
        lab_home,
        "twoids",
        placement="bundle",
        watch="source",
        ignored=["**/node_modules", "cache", "data"],
        live_extra=f"""
- insert:
    - id: greeter-live
      name: {PKG_NAME}
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
    print("\n══ ⑩ 一个包挂两次（bundle 层 + 活层，id 不同）═════════════")
    print(f"  bundle 层那条 greeter　　报过：{bundle_side}")
    print(f"  活层那条 greeter-live　　报过：{live_side}")
    print(f"  两条各自的 config：{[d.get('配置版本') for d in said_note(events, '我跑起来了')] or '见下方时间线'}")
    print(f"  {hmr_noise(events)}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert bundle_side == [FIRST, SECOND], f"bundle 层那条该重来，实际 {bundle_side}"
    assert live_side == [FIRST, SECOND], f"活层那条也该重来，实际 {live_side}"
    for who in ("greeter", "greeter-live"):
        assert states_of(events, who).count("ACTIVE") == 2, f"{who} 应当跑起来两次"
    # 一次改动、一次重载事件，但里面装着两个 fiber
    assert len(of_kind(events, "hmr-reload")) == 1, "改一个文件只该有一次重载"


def test_duplicate_id_added_while_running(lab_home: LabHome, launch):
    """⑪ 进程**已经起来了**，这时往活层加一条跟 bundle 层同 id 的 —— 会怎样。

    第 10 项那堵墙是**启动时**就撞上的：两层拼起来 id 重复，挂载期抛
    `duplicate loader entry id`，进程当场退出。这一条问的是运行中撞会怎样，
    走的是完全不同的一条路 —— 配置路径。

    那条路上的失败被 `refreshConfig` 的 try/catch 兜着
    （`cordis-plugin-hmr/src/index.ts:302-316`）：记两条 warn、发一个
    `hmr/config-update-failed` 事件，**不回滚也不退出**。所以要问三件事：

      * 进程还活着吗
      * 原来那个条目遭殃了吗
      * 撞完之后这个实例还健康吗 —— 代码热重载还能不能用

    最后一条最要紧：一次失败的配置更新如果让整棵树处于半死状态，那比直接退出
    还糟。用 ⑦ 那个形态（源码在 profile 里、hmr 默认配置）就是为了能在撞车之后
    接着改一次代码，看它还认不认。
    """
    profile, events_path, index_js = build(lab_home, "duprun", placement="bundle-nested", watch="profile")

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)

    # ── 运行时往活层追加一条同 id 的 ────────────────────────────────────────
    profile.write_patch(
        profile.read_patch()
        + f"""
- insert:
    - id: greeter
      name: {PKG_NAME}
      config:
        版本: 活层撞车
"""
    )
    Instance.settle(SETTLE)

    mid = read_events(events_path)
    failed = of_kind(mid, "hmr-failed")

    print("\n══ ⑪ 运行中往活层加一条同 id 的 ═════════════════════════")
    print(f"  进程还活着？　　{inst.alive()}")
    print(f"  hmr-failed 事件：{len(failed)} 条")
    for e in failed:
        print(f"    {Path(str(e.get('filename'))).name} → {e.get('error')}")
    print(f"  原来那条 greeter 报过：{said_versions(mid)}")
    print(f"  它走过的状态：{states_of(mid, 'greeter')}")

    assert inst.alive(), f"配置更新失败不该拖垮进程：\n{inst.logs()}"
    assert failed, "该发一个 hmr/config-update-failed 事件"
    assert any("duplicate" in str(e.get("error", "")).lower() for e in failed), (
        f"判词该点名 id 重复，实际 {[e.get('error') for e in failed]}"
    )
    assert said_versions(mid) == [FIRST], "原来那条不该被换成活层那个值"
    assert "DISPOSED" not in states_of(mid, "greeter"), "整次更新应当回滚，原来那条不该被拆掉"

    # ── 撞完之后，这个实例还健康吗 ──────────────────────────────────────────
    edit_code(index_js)
    got = wait_said(inst, events_path, count=2, timeout=25.0)

    after = read_events(events_path)
    print("\n══ 撞车之后再改一次代码 ══════════════════════════════════")
    print(f"  插件报过的版本：{got}")
    print(f"  {hmr_noise(after)}")
    print(show(after))

    assert inst.alive(), f"实例应当仍然活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"一次失败的配置更新不该弄坏代码热重载，实际 {got}"


def test_code_reload_keeps_the_old_config(lab_home: LabHome, launch):
    """⑧ 同一时刻改代码 + 改包里那份 patch 的 config —— 拿到的是**新代码配旧配方**。

    ⑦ 的形态（源码嵌在 profile 里，hmr 默认配置），所以两个文件都在 watch 范围内。
    一次改两处，一次读结果：

      * 代码里那句「第一版」→「第二版」
      * 包里那份 patch 的 `config.版本`「配置第一版」→「配置第二版」

    插件每次把两个值一起报出来，来路一眼分得开。

    三条判定挤在这一条用例里：

    **一 · 代码路径不换 config。** 重载走的是
    `registry.plugin(plugin, oldFiber._config, ...)`（`index.ts:502-509`）——
    明写着沿用旧 fiber 的 config。所以新代码拿到的是**上一程那份**配置。

    **二 · bundle 层的 config 是冷的。** `composeLive()` 里
    `composed.bundlePatches` 是 boot 时 `loadProfile()` 读好的常量数组
    （`dsh/lib/profile-boot-DG5t9aNs.js:170,242`），只有 profile 活层和 home 层
    每次重读盘。改包里那份 patch 不进这条路。

    **三 · watcher 看见了那个 patch 文件，但没有任何后续。** 它落在 `root: ['.']`
    范围内，所以 root watcher 报了 change；但它不是任何 include 的 filename，
    也不在 `loadCache` 里（不是 JS 模块），于是掉进最后那个「只发个事件」的分支
    （`index.ts:270`）—— 事件流里能看到 `hmr-change` 点名它。

    第三条是「配方冷」该有的证据形态：**不是没人看见，是看见了没人管。**

    最后重启一次坐实「冷」而不是「丢了」：新进程重新 `loadProfile()`，
    两个新值这才一起生效。
    """
    profile, events_path, index_js = build(lab_home, "cfgcold", placement="bundle-nested", watch="profile")
    pkg_dir = index_js.parent

    inst = launch(profile, wait_http=False)
    boot(inst, events_path)
    assert said_pairs(read_events(events_path)) == [(FIRST, CFG_FIRST)], "起手该是代码第一版配配方第一版"

    # ── 同一时刻，两处各改一笔 ──────────────────────────────────────────────
    edit_code(index_js)
    patch_file = edit_bundle_config(pkg_dir)

    wait_said(inst, events_path, count=2, timeout=25.0)
    Instance.settle(5.0)  # 再多坐一会儿：万一配方那笔走的是另一条更慢的路

    events = read_events(events_path)
    pairs = said_pairs(events)
    seen_patch = [e for e in of_kind(events, "hmr-change") if "cordis.patch.yml" in str(e.get("url"))]

    print("\n══ ⑧ 同时改代码和包里那份 patch 的 config ════════════════")
    print(f"  代码：{FIRST} → {SECOND}　　　（文件 {index_js.name}）")
    print(f"  配方：{CFG_FIRST} → {CFG_SECOND}（文件 {patch_file.name}，在 watch 范围内）")
    print(f"  {hmr_noise(events)}")
    print(f"  watcher 点名那份 patch 文件的次数：{len(seen_patch)}")
    print(f"  插件报过的（代码版本, 配方版本）：{pairs}")
    print(show(events))

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert pairs == [(FIRST, CFG_FIRST), (SECOND, CFG_FIRST)], f"该是「新代码 + 旧配方」，实际 {pairs}"
    assert seen_patch, "那份 patch 文件在 watch 范围内，watcher 该报出它的变化"
    assert len(of_kind(events, "hmr-reload")) == 1, "只该有一次重载（代码那次），配方那次不产生重载"

    # ── 重启：新进程重新 loadProfile()，配方那笔这才生效 ────────────────────
    inst.stop()
    events_path.replace(events_path.with_name(events_path.stem + "-run1.jsonl"))
    inst = launch(profile, wait_http=False)
    after = wait_said(inst, events_path, count=1)

    pairs_after = said_pairs(read_events(events_path))
    print("\n══ 重启之后 ══════════════════════════════════════════════")
    print(f"  插件报出的（代码版本, 配方版本）：{pairs_after}")

    assert inst.alive(), f"重启后实例应当活着：\n{inst.logs()}"
    assert after == [SECOND], f"重启后代码当然是新的，实际 {after}"
    assert pairs_after == [(SECOND, CFG_SECOND)], f"重启后配方那笔才生效，实际 {pairs_after}"
