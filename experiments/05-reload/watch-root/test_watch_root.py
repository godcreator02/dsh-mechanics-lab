"""watch-root · hmr 主 watcher 的 `root` 语义

档次 ① ｜ 性质 🔬 ｜ 状态 ✅ ｜ 9 条用例 ｜ 不需要 web

## 判定

- **`root` 不写时默认值是 `['.']`**（相对 `baseUrl` 解析），即 profile 目录
  ——第一份最小实例因此「其实早就能热重载」，只是没写明。
  `test_no_config_means_the_default_root`
- **`'.'` 与 profile 目录的绝对路径等价。** `test_absolute_root_works_too`
- **`root` 指向别处或写成空数组，改代码没有任何反应**——这不是「hmr 坏了」，
  是它确实只盯配置里列出的那些目录。`test_root_pointing_elsewhere_notices_nothing`、
  `test_empty_root_watches_nothing`
- **代码摆在 profile 目录里，一定热。** `test_inline_package_reloads` 是这一项
  全部结论的对照组：同一个包、同一种改法，只要代码不经 junction，就该重载。
- **经 junction 装进来的包，默认 `root: ['.']` 够不着它。** profile 目录下通往
  链接那头代码的唯一路径要穿过 `node_modules`——hmr 默认 `ignored` 名单第一项
  就是 `**/node_modules`。`test_linked_package_default_root_notices_nothing`
- **条目从哪一层来（活层手写 / bundle 自注册）不影响能不能被热重载。**
  `test_bundle_self_registered_entry`：把 `root` 扩到源码真实路径、去掉
  `ignored` 里的 `**/.*`（详见 ignore-rules 项），条目由包自己那份 patch 生
  照样重载。
- **`root: []` 只关掉代码这一条路，不是「什么都不监听」。** 关掉之后跑着的
  代码永远拿不到新实现——ESM 在 `import` 那一刻就把静态依赖图读盘编译完了，
  调用不会回头读磁盘。`test_with_hmr_off_the_running_code_never_notices`

`root` 填 `node_modules` 里那条 junction 路径不生效——watcher 报的路径从不做
realpath，`loadCache` 的 key 永远是 realpath，两者对不上（`Map.has` 认字符
串）。这条坑的完整证据链在 ignore-rules 项。

## 观测方法

编辑插件文件后，读事件流里插件上报的「版本」字段——`FIRST`（第一版）变成
`SECOND`（第二版）出现几次，就是重载发生了几次。配合 `states_of` 校验条目
走过几次 `ACTIVE`/`DISPOSED`，用来区分「条目重挂」与「进程重启」（`pid` 不变、
别的条目状态序列里不出现 `DISPOSED`）。

「应该重载」的用例用 `wait_said`/`wait_until_said` 轮询到指定次数为止；
「不该重载」的用例用固定 15 秒等待（`Instance.settle`），不许轮询提前退出——
提前退出只能证明「此刻还没发生」，证明不了「不会发生」。

`test_with_hmr_off_the_running_code_never_notices` 另开了一个心跳（每 700ms
调一次纯函数并报出结果），排除「压根没人调用」这种会跟「拿到旧值」混淆的
解释。

## 没覆盖到的

`root` 指向 `node_modules` 里的 junction 路径、以及 profile 内部一条链接指向
外部源码这两种「watcher 出了声但没重载」的形态，判定详见 ignore-rules 项——
那两条属于 `ignored` 规则与 realpath 不对等的机制，不属于 `root` 本身的语义。
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
    read_events,
    reports,
    rmtree_safe,
    states_of,
)

OBSERVER = LAB_ROOT / "observatory" / "lab-recorder"

FIRST, SECOND = "第一版", "第二版"
ALGO_FIRST, ALGO_SECOND = "算法第一版", "算法第二版"

#: 「验证什么都不该发生」用的固定等待。
SETTLE = 15.0


# ══════════════════════════════════════════════════════════════════════════
# 一、单文件插件形态：条目用相对路径直接指一个文件，代码就在 profile 目录里
# ══════════════════════════════════════════════════════════════════════════

GREETER = Path(__file__).resolve().parent / "fixtures" / "greeter.mjs"

SINGLE_BASE = """- insert:
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

NO_CONFIG = ""


def single_hmr_config(root: str | None) -> str:
    """hmr 那条的 config 段。`root=None` 表示写一个空名单。"""
    roots = "[]" if root is None else f"['{root}']"
    return f"""      config:
        root: {roots}
"""


def build_single(lab_home: LabHome, name: str, *, config_block: str) -> tuple[LabProfile, Path, Path]:
    """搭一个实例：基础三条（hmr 的 config 由调用方给）+ 单文件插件条目。

    返回 profile、事件流路径、插件文件在 profile 里的落点。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    patch = SINGLE_BASE.format(timer=PKG_TIMER, hmr=PKG_HMR, hmr_config=config_block, out=json.dumps(events.as_posix()))
    profile = lab_home.make_profile(name, bundles=[], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    plugin_file = profile.dir / "greeter.mjs"
    shutil.copy2(GREETER, plugin_file)
    return profile, events, plugin_file


def single_said_versions(path: Path) -> list[str]:
    return [e["data"]["版本"] for e in reports(read_events(path), who="greeter") if e.get("data")]


def single_wait_until_said(inst: Instance, path: Path, *, count: int, timeout: float = 40.0) -> list[str]:
    deadline = time.monotonic() + timeout
    got: list[str] = []
    while time.monotonic() < deadline:
        got = single_said_versions(path)
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


def single_boot_and_wait_first(inst: Instance, events_path: Path) -> None:
    first = single_wait_until_said(inst, events_path, count=1)
    assert first == [FIRST], f"实例起来后插件该说一次话，实际 {first}：\n{inst.logs()}"
    time.sleep(1.0)  # 让启动那一阵与热重载那一阵在时间线上分得开，判定不依赖它


def single_edit_plugin(plugin_file: Path) -> None:
    text = plugin_file.read_text(encoding="utf-8")
    assert FIRST in text, "前提：插件文件里本来写着第一版"
    plugin_file.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


def test_root_dot_reloads_the_plugin(lab_home: LabHome, launch):
    """`root: ['.']`：改插件文件 → 重新加载 → 同一个插件第二次说话，实例不重启。"""
    profile, events_path, plugin_file = build_single(lab_home, "rooted", config_block=single_hmr_config("."))

    inst = launch(profile, wait_http=False)
    single_boot_and_wait_first(inst, events_path)

    single_edit_plugin(plugin_file)
    got = single_wait_until_said(inst, events_path, count=2)

    events = read_events(events_path)
    assert inst.alive(), f"热重载不是重启，实例应当一直活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"该说两次、且第二次是新代码里的话，实际 {got}"

    states = [e.get("to") for e in events if e.get("kind") == "status" and e.get("id") == "greeter"]
    assert states.count("ACTIVE") == 2, f"应当有两次 ACTIVE（旧的一次、新的一次），实际 {states}"
    assert "DISPOSED" in states, f"旧的那个应当被拆掉，实际走过 {states}"
    assert [e for e in events if e.get("kind") == "hmr-reload"], "事件流里应当有 hmr 报的重新加载"

    for other in ("timer", "hmr", "lab-recorder"):
        other_states = [e.get("to") for e in events if e.get("kind") == "status" and e.get("id") == other]
        assert "DISPOSED" not in other_states, f"{other} 不该被牵连，却走过 {other_states}"


def test_no_config_means_the_default_root(lab_home: LabHome, launch):
    """hmr 那条一个 config 都不写——`root` 的默认值就是 `['.']`，结果跟显式写一样。"""
    profile, events_path, plugin_file = build_single(lab_home, "default", config_block=NO_CONFIG)

    inst = launch(profile, wait_http=False)
    single_boot_and_wait_first(inst, events_path)

    single_edit_plugin(plugin_file)
    got = single_wait_until_said(inst, events_path, count=2)

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"不写 config 也该热重载（默认 root 是 ['.']），实际 {got}"


def test_absolute_root_works_too(lab_home: LabHome, launch):
    """`root` 写成 profile 目录的绝对路径，效果跟 `'.'` 一样。"""
    profile, events_path, plugin_file = build_single(lab_home, "absolute", config_block=NO_CONFIG)
    # profile 目录建好之后才知道绝对路径，config 这时候才补写进 patch 文件
    profile.write_patch(
        profile.read_patch().replace(
            f"      name: '{PKG_HMR}'\n", f"      name: '{PKG_HMR}'\n" + single_hmr_config(profile.dir.as_posix())
        )
    )

    inst = launch(profile, wait_http=False)
    single_boot_and_wait_first(inst, events_path)

    single_edit_plugin(plugin_file)
    got = single_wait_until_said(inst, events_path, count=2)

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"绝对路径也该热重载，实际 {got}"


def test_root_pointing_elsewhere_notices_nothing(lab_home: LabHome, launch):
    """`root` 指着另一个目录：插件文件改了，什么都不会发生——证明 `root` 是真的在起作用。"""
    profile, events_path, plugin_file = build_single(
        lab_home, "elsewhere", config_block=single_hmr_config("./elsewhere")
    )
    (profile.dir / "elsewhere").mkdir(exist_ok=True)

    inst = launch(profile, wait_http=False)
    single_boot_and_wait_first(inst, events_path)

    single_edit_plugin(plugin_file)
    Instance.settle(SETTLE)  # 验「不该发生」：固定长等待，不许轮询提前退出

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert single_said_versions(events_path) == [FIRST], "root 没盯着插件所在的目录，它不该被重新加载"


def test_empty_root_watches_nothing(lab_home: LabHome, launch):
    """`root: []`——明写着「一个目录都不盯」，改代码同样没有任何反应。"""
    profile, events_path, plugin_file = build_single(lab_home, "empty", config_block=single_hmr_config(None))

    inst = launch(profile, wait_http=False)
    single_boot_and_wait_first(inst, events_path)

    single_edit_plugin(plugin_file)
    Instance.settle(SETTLE)

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert single_said_versions(events_path) == [FIRST], "root 是空的，插件不该被重新加载"


# ══════════════════════════════════════════════════════════════════════════
# 二、包形态：靠 junction 装进来，条目用包名引用（活层写，或包自己那份 patch 生）
# ══════════════════════════════════════════════════════════════════════════

PKG_NAME = "hmr-linked"
CFG_FIRST = "配置第一版"

PKG_BASE = """- insert:
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

PKG_ENTRY = """
- insert:
    - id: greeter
      name: {entry_name}
{entry_config}"""


def copy_package(dest: Path) -> Path:
    """把教学插件那个包拷一份到指定落点，用例只改这份拷贝，仓库里的源保持原样。"""
    if dest.exists():
        rmtree_safe(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / PKG_NAME, dest)
    return dest


def build_pkg(
    lab_home: LabHome,
    name: str,
    *,
    placement: str,
    watch: str,
    ignored: list[str] | None = None,
    entry_config: str = "",
) -> tuple[LabProfile, Path, Path]:
    """搭一个 profile。

    Args:
        placement: 代码落在哪、条目从哪来。``"inline"`` 包目录摆进 profile 目录，
            条目用相对路径引用文件。``"linked"`` 包目录留在 profile 外面，靠
            `link:` + junction 装进来，条目由用例写在活层，用包名引用。
            ``"bundle"`` 装法同上，但包名进 `dsh.profile.bundles` 名单，条目
            由包自己那份 `cordis.patch.yml` 生，活层一个字不写。
        watch: hmr 的 `root` 填什么。``"none"`` 填 `[]`；``"profile"`` 填
            `['.']`（默认值）；``"source"`` 再加源码包目录的真实路径。
        ignored: hmr 的 `ignored` 名单。不传就不写这个键，走 schema 默认值。
    """
    events = lab_home.root / f"events-{name}.jsonl"
    profile_dir = lab_home.root / "profiles" / name

    if placement == "inline":
        pkg_dir = copy_package(profile_dir / PKG_NAME)
        entry = PKG_ENTRY.format(entry_name=f"./{PKG_NAME}/index.js", entry_config=entry_config)
    elif placement == "linked":
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
        entry = PKG_ENTRY.format(entry_name=PKG_NAME, entry_config=entry_config)
    elif placement == "bundle":
        pkg_dir = copy_package(lab_home.root / f"src-{name}" / PKG_NAME)
        entry = ""  # 条目归包自己那份 patch 生，活层不写
    else:
        raise ValueError(f"未知 placement：{placement}")

    junction_dir = profile_dir / "node_modules" / PKG_NAME
    roots = {
        "none": [],
        "profile": ["."],
        "source": [".", pkg_dir.as_posix()],
        "junction": [".", junction_dir.as_posix()],
    }[watch]

    patch = PKG_BASE.format(
        timer=PKG_TIMER,
        hmr=PKG_HMR,
        roots=json.dumps(roots),
        ignored="" if ignored is None else f"        ignored: {json.dumps(ignored)}\n",
        out=json.dumps(events.as_posix()),
        entry=entry,
    )
    in_bundles = placement in ("bundle",)
    profile = lab_home.make_profile(name, bundles=[PKG_NAME] if in_bundles else [], patch=patch)
    profile.link_plugin("lab-recorder", OBSERVER)
    if placement != "inline":
        profile.link_plugin(PKG_NAME, pkg_dir)

    return profile, events, pkg_dir / "index.js"


def pkg_edit_code(index_js: Path) -> None:
    text = index_js.read_text(encoding="utf-8")
    assert FIRST in text, f"前提：{index_js} 里本来写着{FIRST}"
    index_js.write_text(text.replace(FIRST, SECOND), encoding="utf-8")


def pkg_edit_helper(pkg_dir: Path) -> Path:
    helper = pkg_dir / "helper.js"
    text = helper.read_text(encoding="utf-8")
    assert ALGO_FIRST in text, f"前提：{helper} 里本来写着{ALGO_FIRST}"
    helper.write_text(text.replace(ALGO_FIRST, ALGO_SECOND), encoding="utf-8")
    return helper


def pkg_said_versions(events: list[dict], who: str = "greeter") -> list[str]:
    return [e["data"]["版本"] for e in reports(events, who=who) if (e.get("data") or {}).get("版本")]


def pkg_said_field(events: list[dict], field: str, who: str = "greeter") -> list:
    return [d[field] for e in reports(events, who=who) if field in (d := e.get("data") or {})]


def pkg_wait_said(inst: Instance, path: Path, *, count: int, who: str = "greeter", timeout: float = 40.0) -> list[str]:
    deadline = time.monotonic() + timeout
    got: list[str] = []
    while time.monotonic() < deadline:
        got = pkg_said_versions(read_events(path), who)
        if len(got) >= count:
            return got
        if not inst.alive():
            break
        time.sleep(0.3)
    return got


def pkg_boot(inst: Instance, events_path: Path) -> None:
    first = pkg_wait_said(inst, events_path, count=1)
    assert first == [FIRST], f"实例起来后插件该报一次版本，实际 {first}：\n{inst.logs()}"
    time.sleep(1.0)


def test_inline_package_reloads(lab_home: LabHome, launch):
    """对照组 · 包摆在 profile 目录里，改代码 → 重来一次。

    证明这一项的观测手段有效：同一个包、同一种改法、同一套判据，只要代码不在
    链接那一头，它就该热重载。有了这条，`test_linked_package_default_root_notices_nothing`
    要是不重载，就不能赖到「包这个形态有问题」头上——唯一的差别只剩 junction。
    """
    profile, events_path, index_js = build_pkg(lab_home, "inline", placement="inline", watch="profile")

    inst = launch(profile, wait_http=False)
    pkg_boot(inst, events_path)

    pkg_edit_code(index_js)
    got = pkg_wait_said(inst, events_path, count=2)

    events = read_events(events_path)
    assert inst.alive(), f"实例应当一直活着——热重载不是重启：\n{inst.logs()}"
    assert got == [FIRST, SECOND], f"代码在 profile 目录里就该热重载，实际 {got}"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "该条目应当跑起来两次（原来一次、改完又一次）"


def test_linked_package_default_root_notices_nothing(lab_home: LabHome, launch):
    """装进来的包 + 默认 `root: ['.']`——改代码，什么都不会发生。

    跟对照组只差一件事：代码不在 profile 目录里了，靠 junction 装进来。hmr 盯
    的还是 profile 目录，而 profile 目录下通往这份代码的唯一路径要穿过
    `node_modules`——那正是 hmr 默认 `ignored` 名单上的第一项。
    """
    # ⚠️ name 是**观测产物的文件名**（`events-<name>.jsonl`），而 `lab_home` 是模块级、
    # 一个文件里所有用例共用。跟别的用例撞名就会读到上一条用例的残留——而且残留里
    # 恰好有「重载发生了」的记录，于是本用例会拿别人的数据判自己失败。
    profile, events_path, index_js = build_pkg(lab_home, "linked-default", placement="linked", watch="profile")

    inst = launch(profile, wait_http=False)
    pkg_boot(inst, events_path)

    pkg_edit_code(index_js)
    Instance.settle(SETTLE)

    events = read_events(events_path)
    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert pkg_said_versions(events) == [FIRST], "hmr 没盯着代码的真实落点，它不该被重新加载"
    assert states_of(events, "greeter").count("ACTIVE") == 1, "该条目从头到尾只该跑起来一次"


def test_bundle_self_registered_entry(lab_home: LabHome, launch):
    """真正的分发形态 · 条目由包自己那份 patch 生，活层一个字不写。

    条目从哪一层来不影响它能不能被热重载：装法、`root`、`ignored` 全部照搬
    「源码在外 + root 加真实路径 + 去掉 `**/.*`」这套已验能重载的配置
    （细节见 ignore-rules 项），只是条目换成由 bundle 层自注册。
    """
    profile, events_path, index_js = build_pkg(
        lab_home, "selfreg", placement="bundle", watch="source", ignored=["**/node_modules", "cache", "data"]
    )

    inst = launch(profile, wait_http=False)
    pkg_boot(inst, events_path)

    pkg_edit_code(index_js)
    got = pkg_wait_said(inst, events_path, count=2, timeout=25.0)

    events = read_events(events_path)
    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert "greeter" in entry_ids(events), "包自己那份 patch 写的条目应当出现在树上"
    assert got == [FIRST, SECOND], f"条目从哪一层来不该影响热重载，实际 {got}"
    assert states_of(events, "greeter").count("ACTIVE") == 2, "该条目应当跑起来两次"


def test_with_hmr_off_the_running_code_never_notices(lab_home: LabHome, launch):
    """把 hmr 关掉（`root: []`），改纯算法文件——跑着的代码永远拿不到新实现。

    ESM 在 `import` 那一刻就把整棵静态依赖图读盘、编译完了，函数体之后一直在
    内存里，调用时不会回头读磁盘。光看「改完什么都没发生」不够——那有两种
    解释：调用拿到了旧值，或压根没人调用。插件开了心跳（每 700ms 调一次
    `compute()` 并报出结果），改文件之后再等 15 秒，期间它调了二十来次，
    每一次都是旧值，后一种解释就排除了。
    """
    profile, events_path, index_js = build_pkg(
        lab_home, "hmroff", placement="inline", watch="none", entry_config="      config:\n        心跳毫秒: 700\n"
    )
    pkg_dir = index_js.parent

    inst = launch(profile, wait_http=False)
    pkg_boot(inst, events_path)
    inst.wait_for(lambda: len(pkg_said_field(read_events(events_path), "第几次")) >= 3, timeout=20.0, what="心跳跑起来")
    before = len(pkg_said_field(read_events(events_path), "第几次"))

    pkg_edit_helper(pkg_dir)
    Instance.settle(SETTLE)

    events = read_events(events_path)
    beats = pkg_said_field(events, "算出来", who="greeter")
    ticks = pkg_said_field(events, "第几次")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert len(ticks) > before + 10, f"改动之后心跳该接着跳很多次，改前 {before} 此刻 {len(ticks)}"
    assert set(beats) == {ALGO_FIRST}, f"每一次调用都该拿到旧实现，实际见过 {sorted(set(beats))}"
    assert not [e for e in events if e.get("kind") == "hmr-reload"], "root 是空的，不该有任何重载"
    assert states_of(events, "greeter").count("ACTIVE") == 1, "条目自始至终只该跑起来一次"
