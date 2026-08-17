"""name-resolution · 条目的 `name` 怎么变成一个真的模块

档次 ① ｜ 性质 ⚠️ 矫正型 ｜ 状态 ✅ ｜ 11 条用例（4 个参数化） ｜ 不需要 web

本组最重的一项：`l03_name_resolution` 全部 7 条 + `l00_minimal_environment` 的
2 条（1 个参数化）+ `l01_minimal_plugin` 的 1 条（参数化 4 变体）+
`step5_when_it_wont_load` 的对照组 1 条，一共汇入本项。

## 判定

### ⚠️ 矫正点：官方「必须是绝对路径」，实际规则是「必须是合法 URL」

官方 `docs/official/zh/user/develop/basic/index.md:56` 写「插件路径必须是
绝对路径」，示例是 POSIX 风格 `/absolute/path/to/deepseek-harness/...`。这是
建议，不是解析规则的全部——真正的规则是**必须是合法 URL**：

- Windows 裸盘符路径（`D:\\...\\index.js`）**加载失败**：`D:` 被当成 URL
  scheme 解析，报 `ERR_UNSUPPORTED_ESM_URL_SCHEME`（`test_windows_absolute_path`
  + `test_resolution_is_the_real_boundary` 一系间接印证）
- `file://` URL 形式**能加载**（`test_file_url`）——这才是 Windows 下
  「绝对路径」应该写的形式

POSIX 上 `/absolute/path` 恰好同时是合法 URL 路径部分，所以文档的建议在
POSIX 上不会踩这个坑，但文档没有区分操作系统。这是「建议」和「规则」的落差。

### `ctx.loader.internal` 激活，「三条互不相通的路径」只成立一半

源码画的是四条判断（`cordis:` / internal 分支 / 相对路径 / 裸包名），但
`internal` 排在最前——**实测它在本部署上是激活的**（`test_loader_internal_activated`）。
后果：

- `cordis:` 前缀在 `internal` 判断之前就短路，是独立的第一刀
- 剩下的相对路径 / 绝对路径 / 裸包名**代码路径合一**，全部丢给
  `internal.import(name, baseUrl, {})`——但表现出来的解析行为（协议判断、
  URL 解析、包解析）跟源码注释的三分支几乎一致，因为 `internal.import`
  内部就是在做同一件事（报错堆栈里能看到 Node 内部 ESM loader 的函数名）

源码（`cordis-plugin-loader` 的 `EntryTree.import`）：

    if (name.startsWith("cordis:")) return this.ctx.loader.builtins[name.slice(7)]
    return composeError(async (info) => {
      if (this.ctx.loader.internal) return await this.ctx.loader.internal.import(name, this.ctx.baseUrl, {})
      else if (name.startsWith(".")) return await import(new URL(name, this.ctx.baseUrl).href)
      else return await import(name)
    }, getOuterStack)

### 两种「加载失败」，报错文本完全不同

- `cordis:` 指向不存在的内置表项：cordis 自造的报错
  `invalid plugin, expect function or object with an "apply" method, received undefined`，
  从没建立过 fiber——`test_cordis_unknown_builtin`
- 裸包名指向不存在的包：Node 标准的 `ERR_MODULE_NOT_FOUND`——
  `test_nonexistent_bare_package`

两者都表现为「启动失败」，但成因不同，混着断言（只判断有没有报错）会把两种
机制读成同一件事。

### `exports` 子路径要显式声明，相对路径没有回退链

- `exports` 声明的子路径才能被包解析找到，未声明的哪怕文件确实存在也会
  `ERR_PACKAGE_PATH_NOT_EXPORTED`——`test_exports_subpath`
- 包解析的回退链是 `exports["."]` → `main` → 默认 `index.js`，三条路任意一条
  通就能被包名 resolve 到，只有三条全断才加载不了——`test_resolution_is_the_real_boundary`
- 这条回退链**只属于包解析**。相对路径走纯 URL 解析，压根不看
  `package.json`，同一份代码：相对路径直指非入口文件能加载，包名引用同一个包
  （三条回退路全断）加载不了——`test_relative_path_has_no_fallback_chain`

### 裸包名以 dsh 安装目录为锚，不必 link 进 profile

标准 Node parent-walk：profile 目录往上一层就是共享的
`$DSH_HOME/profiles/node_modules`，dsh 每次 `prepareProfile` 幂等维护的符号
链接农场。`timer` / `hmr` 从没被 link 过，照样激活——
`test_bare_package_name_resolves_via_shared_node_modules`。

### 相对路径指到目录会失败，指到文件才行

`name.startsWith(".")` 走 `import(new URL(name, ctx.baseUrl))`，指到目录报
`ERR_UNSUPPORTED_DIR_IMPORT`，指到文件才成功——
`test_relative_name_resolution`（参数化两个变体）。

### 对照组：正确写法就是能跑

`test_correct_relative_name_just_runs` 排除「插件本身有毛病」这种可能——
同一份文件，`name` 写对了就跑了，前面所有失败都只跟 `name` 本身有关。

## 观测方法

见证文件套路延续 01-entry 其余项，`fixtures/probe` 多探一件事：
`ctx.get("loader").internal !== undefined`，跟其余指纹一起写进见证文件——
这是本项能立住「internal 是否激活」这条判定的唯一手段。第一件事必须先测：
`ctx.loader.internal` 是否激活决定后面所有分支的因果解释挂在哪。

**观测点绝不抛错**：探针里的 `safe()` 包了一层 try/catch，拿不到就记 `null`，
不让「根本没跑到这」和「跑到了但没拿到」混成同一个结果。

**结果未知的用例，统一用固定等待而不是轮询提前退出**——`_observe_fixed()`：
Windows 绝对路径、`file://` URL 这类用例事先不知道会成功还是失败，用轮询
等成功只能证明「这一刻还没成功」，证明不了「永远不会成功」。

**两种「加载失败」分开断言**：不能只判断「有没有报错」，报错文本要分开记录、
分开断言——这条规矩来自 CLAUDE.md 的观测方法论第 5 条。
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest
from lab import LAB_ROOT, Instance, LabHome, read_events, reports

pytestmark = pytest.mark.instance

#: 结果未知的用例统一用多久的固定等待。轮询提前退出只能证明"此刻还没发生"，
#: 证明不了"不会发生"——本项好几条用例的答案本身就是未知数，不能用轮询作弊。
OBSERVE = 10.0

RECORDER = LAB_ROOT / "observatory" / "lab-recorder"


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _insert(entry_id: str, name: str, witness: Path, **extra) -> str:
    """生成一条带 config.witness 的活层 insert。"""
    config = {"witness": witness.as_posix(), **extra}
    config_yaml = "\n".join(f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items())
    return f"""# name-resolution 活层
- insert:
    - id: {entry_id}
      name: {json.dumps(name, ensure_ascii=False)}
      config:
{config_yaml}
"""


def _insert_bare(entry_id: str, name: str) -> str:
    """生成一条没有 config 的活层 insert——用于预期加载失败、apply 根本不会跑的用例。"""
    return f"""# name-resolution 活层
- insert:
    - id: {entry_id}
      name: {json.dumps(name, ensure_ascii=False)}
"""


def _wait_for_file(path: Path, *, timeout: float = 20.0, interval: float = 0.3) -> dict:
    """轮询等见证文件出现。用于"验证应该发生的事"。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(interval)
    raise AssertionError(f"等了 {timeout}s，见证文件仍未出现：{path}")


def _run_until_witness(launch, profile, witness: Path, *, timeout: float = 20.0) -> dict:
    """拉起实例，等见证文件落地。失败时把实例状态和日志一起报出来。"""
    inst = launch(profile, wait_http=False)
    try:
        return _wait_for_file(witness, timeout=timeout)
    except AssertionError as exc:
        raise AssertionError(f"{exc}\n实例还活着={inst.alive()}\n{inst.logs()}") from exc


def _observe_fixed(inst: Instance, witness: Path | None = None, seconds: float = OBSERVE) -> dict:
    """固定等待 seconds 秒后，如实记录发生了什么。

    结果未知或预期失败的用例统一用这个：不做任何预设判断，只把「加载没加载、
    进程还活不活着、日志写了什么」原样收集起来，判断留给调用方。
    """
    time.sleep(seconds)
    data = None
    if witness is not None and witness.exists():
        try:
            data = json.loads(witness.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
    return {
        "loaded": data is not None,
        "data": data,
        "alive": inst.alive(),
        "exit_code": inst.proc.returncode,
        "logs": inst.logs(tail=40),
    }


# ── 用例 1 · 决定性的前置问题：internal 是否激活 ────────────────────────────


def test_loader_internal_activated(lab_home: LabHome, fixtures_dir: Path, launch):
    """`ctx.loader.internal` 是否激活？——最要紧的问题，决定后面每一条用例的
    因果解释挂在哪条分支上。

    激活时相对路径 / 绝对路径 / 裸包名全部经同一条
    `internal.import(name, baseUrl, {})`，name 原样传入、不做任何前缀判断，
    "三条互不相通的解析路径"的说法就不成立。

    探针本身走裸包名加载（两个分支下这条路都会成功），所以能不能测到这件事
    跟"internal 是否激活"这个问题本身正交，可以放心当第一条用例。
    """
    witness = lab_home.root / "witness-internal.json"
    profile = lab_home.make_minimal_profile("internal", patch=_insert("probe", "name-resolution-probe", witness))
    profile.link_plugin("name-resolution-probe", fixtures_dir / "probe")

    launch(profile, wait_http=False)
    got = _wait_for_file(witness)

    print(f"\n  ctx.get('loader').internal 是否激活：{got['loaderInternal']}")
    print(f"  ctx.baseUrl：{got['baseUrl']!r}")
    if got["loaderInternal"]:
        print("  → internal 分支激活：相对/绝对/裸包名全走同一条路，不做前缀判断")
    elif got["loaderInternal"] is False:
        print("  → internal 未激活：真的按三条分支分派（cordis: / 相对路径 / 包解析）")
    else:
        print("  → 拿不到判定结果（loader 服务本身取不到）")

    assert got["loaderInternal"] is not None, (
        "探针应当能测到这个字段——拿到 None 说明连 loader 服务本身都取不到，那是比「internal 激不激活」更严重的问题"
    )


# ── 用例 2、3 · 绝对路径 vs file:// URL ──────────────────────────────────────


def test_windows_absolute_path(lab_home: LabHome, fixtures_dir: Path, launch):
    """Windows 绝对路径（`D:\\...\\index.js`）能不能被当作 `name` 加载？

    绝对路径原样是个字符串：不以 "." 开头、也不是 `cordis:` 前缀，如果 internal
    未激活就落进"否则"桶，走裸 `import(name)`。Node 的 ESM 解析器对着一个
    "看起来像文件系统路径、但既不是合法 URL、也不是合法包名"的字符串会怎么
    处理，没有先验答案——Windows 路径里的盘符冒号（`D:`）还可能被误判成协议
    前缀，必须实测，不能照抄 POSIX 直觉。
    """
    witness = lab_home.root / "witness-abswin.json"
    abs_path = str((fixtures_dir / "probe" / "index.js").resolve())
    print(f"\n  绝对路径：{abs_path}")

    profile = lab_home.make_minimal_profile("abswin", patch=_insert("probe", abs_path, witness))
    # 故意不 link——全靠这个绝对路径字符串本身，跟裸包名解析（以 dsh 安装
    # 目录为锚）划清界限

    inst = launch(profile, wait_http=False)
    got = _observe_fixed(inst, witness)

    print(f"  加载成功？ {got['loaded']}")
    print(f"  进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")
    if got["loaded"]:
        print(f"  → Windows 绝对路径可以直接被加载（internal={got['data'].get('loaderInternal')}）")
    else:
        print(f"  → 加载失败：\n{got['logs']}")


def test_file_url(lab_home: LabHome, fixtures_dir: Path, launch):
    """对照上一条：`file://` URL 形式一定是合法 URL，Node 的解析器认得它。

    这条用来跟"Windows 绝对路径"形成对照——如果两条的成败不一样，问题就不在
    "Node 能不能识别这个字符串"，而在"cordis 有没有在真正解析前先拦一道"。
    """
    witness = lab_home.root / "witness-fileurl.json"
    file_url = (fixtures_dir / "probe" / "index.js").resolve().as_uri()
    print(f"\n  file:// URL：{file_url}")

    profile = lab_home.make_minimal_profile("fileurl", patch=_insert("probe", file_url, witness))

    inst = launch(profile, wait_http=False)
    got = _observe_fixed(inst, witness)

    print(f"  加载成功？ {got['loaded']}")
    print(f"  进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")
    if got["loaded"]:
        print(f"  → file:// URL 可以直接被加载（internal={got['data'].get('loaderInternal')}）")
    else:
        print(f"  → 加载失败：\n{got['logs']}")


# ── 用例 4、5 · 两种"加载失败"，报错文本必须分开记录 ──────────────────────────


def test_cordis_unknown_builtin(lab_home: LabHome, fixtures_dir: Path, launch):
    """`cordis:` 前缀指向不存在的内置表项，会发生什么？

    源码推导：`builtins[未知key]` → `undefined` → `unwrapExports` 对 nullable
    原样放行 → `registry.plugin(undefined)` 同步抛
    `invalid plugin, expect function or object with an "apply" method, received undefined`。

    这条从头到尾没建立过 fiber，是第三种失败形态——跟 PENDING、FAILED（apply
    抛异常）不是一类，报错文本是 cordis 自造的，不是 Node 的。
    """
    profile = lab_home.make_minimal_profile("cordisbad", patch=_insert_bare("bad", "cordis:nonexistent"))

    inst = launch(profile, wait_http=False)
    got = _observe_fixed(inst, seconds=8.0)

    print(f"\n  进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")
    print(got["logs"])

    expected = 'invalid plugin, expect function or object with an "apply" method'
    assert not got["alive"], "预期 cordis: 未知 builtin 会让启动失败"
    assert expected in got["logs"], f"报错文本跟源码推导的不一致，实际日志：\n{got['logs']}"
    print(f"  → 报错文本吻合源码推导：{expected!r}")


def test_nonexistent_bare_package(lab_home: LabHome, fixtures_dir: Path, launch):
    """裸包名指向一个根本不存在的包，报错文本长什么样？

    跟上一条对照：`cordis:` 未知 builtin 是 cordis 自造的报错文本（从没建立过
    fiber）；这条走的是 Node 标准的包解析失败。两者表现都是"启动失败"，
    但成因完全不同——报错文本必须分开记录、分开断言，不能只判断"有没有报错"。
    """
    profile = lab_home.make_minimal_profile(
        "nopkg", patch=_insert_bare("missing", "name-resolution-definitely-does-not-exist")
    )

    inst = launch(profile, wait_http=False)
    got = _observe_fixed(inst, seconds=8.0)

    print(f"\n  进程还活着？ {got['alive']}（退出码 {got['exit_code']}）")
    print(got["logs"])

    node_hints = ["Cannot find package", "Cannot find module", "ERR_MODULE_NOT_FOUND", "ERR_PACKAGE_NOT_FOUND"]
    hit = [h for h in node_hints if h in got["logs"]]
    print(f"  匹配到的 Node 标准报错关键字：{hit or '（一个都没匹配到，看上面日志）'}")

    cordis_text = 'expect function or object with an "apply" method'
    assert not got["alive"], "预期找不到的裸包名也会让启动失败"
    assert cordis_text not in got["logs"], (
        "报错文本不该是 cordis 自造的那句——这条应该是 Node 标准的包解析失败，跟 cordis: 未知 builtin 那条不是一回事"
    )
    print("  → 报错文本与 cordis: 未知 builtin 那条不同（分类断言通过）")


# ── 用例 6 · exports 子路径：声明了 vs 没声明 ─────────────────────────────────


@pytest.mark.parametrize(
    "pkg, should_load", [("subpath-declared", True), ("subpath-undeclared", False)], ids=["declared", "undeclared"]
)
def test_exports_subpath(lab_home: LabHome, fixtures_dir: Path, launch, pkg: str, should_load: bool):
    """官方 publish 文档里 `dsh-hello-plugin/startup` 那种子路径引用，走哪条路？

    子路径不以 "." 或 "cordis:" 开头，落进"否则"桶，走纯 Node 包解析——
    exports 映射表由 Node 处理，没有 cordis 代码参与。两个包的 `tool.js`
    逐字节相同，唯一差异是 package.json 的 exports 里有没有声明 "./tool"。
    """
    tag = "declared" if should_load else "undeclared"
    witness = lab_home.root / f"witness-subpath-{tag}.json"
    name = f"{pkg}/tool"

    profile = lab_home.make_minimal_profile(tag, patch=_insert("tool", name, witness))
    profile.link_plugin(pkg, fixtures_dir / pkg)

    inst = launch(profile, wait_http=False)

    if should_load:
        got = _wait_for_file(witness)
        print(f"\n  [{pkg}] name={name!r} → 加载成功，marker={got['marker']}")
        assert got["marker"] == "subpath-declared-tool-v1"
    else:
        obs = _observe_fixed(inst, witness)
        print(f"\n  [{pkg}] name={name!r} → 加载成功？ {obs['loaded']}")
        print(f"  进程还活着？ {obs['alive']}")
        hit = "ERR_PACKAGE_PATH_NOT_EXPORTED" in obs["logs"]
        print(f"  报 ERR_PACKAGE_PATH_NOT_EXPORTED？ {hit}")
        if not hit:
            print(obs["logs"])
        assert not obs["loaded"], f"{pkg}: exports 没声明这条子路径，不该能加载到"


# ── 用例 7 · 相对路径没有 exports 回退链 ─────────────────────────────────────


def test_relative_path_has_no_fallback_chain(lab_home: LabHome, fixtures_dir: Path, launch):
    """相对路径没有 exports 回退链。

    `fixtures/fallback` 包故意让三条回退路全断（没 exports、没 main，真代码
    又不叫 index.js，叫 plugin.js）——按包解析的回退链结论，包名引用这个包
    应该失败。这条补上对照面：同一份代码，相对路径直接指到 plugin.js，走的是
    纯 URL 解析，压根不看 package.json，那条回退链根本不存在，理应成功。
    两条路径指向同一段字节，成败却相反，边界就摆在这里。
    """
    source = (fixtures_dir / "fallback" / "plugin.js").resolve()

    # 分支 A：相对路径直指非入口文件
    witness_rel = lab_home.root / "witness-fallback-rel.json"
    profile_rel = lab_home.make_minimal_profile("fallback-rel")
    spec = "./" + Path(os.path.relpath(source, profile_rel.dir.resolve())).as_posix()
    profile_rel.write_patch(_insert("plugin", spec, witness_rel))
    print(f"\n  相对路径：{spec}")

    got_rel = _run_until_witness(launch, profile_rel, witness_rel)
    print(f"  相对路径直指非入口文件 → 加载成功，marker={got_rel['marker']}")
    assert got_rel["marker"] == "fallback-plugin-v1"

    # 分支 B：同一份代码，走包名解析
    witness_pkg = lab_home.root / "witness-fallback-pkg.json"
    profile_pkg = lab_home.make_minimal_profile("fallback-pkg", patch=_insert("plugin", "fallback", witness_pkg))
    profile_pkg.link_plugin("fallback", fixtures_dir / "fallback")

    inst_pkg = launch(profile_pkg, wait_http=False)
    obs_pkg = _observe_fixed(inst_pkg, witness_pkg)
    print(f"  包名引用（同一份代码）→ 加载成功？ {obs_pkg['loaded']}")
    if not obs_pkg["loaded"]:
        print(f"  进程还活着？ {obs_pkg['alive']}\n{obs_pkg['logs']}")

    assert not obs_pkg["loaded"], (
        "包名解析不该找到 plugin.js——exports/main/index.js 三条回退路全断，"
        "如果这里加载成功了，说明回退链比记录的更宽，这是个重大发现"
    )
    print("  → 同一份代码：相对路径能到，包名到不了。回退链只属于包解析，相对路径没有")


# ── 用例 8 · 裸包名以 dsh 安装目录为锚，不用 link 进 profile ────────────────


def test_bare_package_name_resolves_via_shared_node_modules(lab_home: LabHome, fixtures_dir: Path, launch):
    """条目的 `name` 写裸包名时，以哪里为锚解析？

    这直接决定「用 `link_plugin` 把包 junction 进 profile 的 node_modules」是不是
    必需的。`make_minimal_profile` 自带的 `timer` / `hmr` 两条写的都是裸包名
    （`@deepseek-ai/cordis-plugin-*`），而我们从来没 link 过它们——profile 的
    node_modules 里只有自己 link 的教学插件。它们照样激活，说明 profile 自己的
    node_modules 不是唯一锚点。

    机制是标准 Node parent-walk：profile 目录往上一层就是
    `$DSH_HOME/profiles/node_modules`，那是 dsh 的 `healScaffoldModuleFallback`
    每次 `prepareProfile` 时幂等维护的符号链接农场。
    """
    census_out = lab_home.root / "census-bare.json"
    profile = lab_home.make_minimal_profile(
        "bare",
        patch=f"""# name-resolution 活层
- insert:
    - id: census
      name: census
      config:
        out: {json.dumps(census_out.as_posix())}
        delayMs: 2000
""",
    )
    profile.link_plugin("census", fixtures_dir / "census")

    inst = launch(profile, wait_http=False)
    time.sleep(4.0)

    linked = profile.dir / "node_modules" / "@deepseek-ai" / "cordis-plugin-timer"
    farm = lab_home.root / "profiles" / "node_modules" / "@deepseek-ai" / "cordis-plugin-timer"
    print(f"\n  timer 被 link 进 profile 了吗？        {linked.exists()}（预期 False）")
    print(f"  上一层的共享 node_modules 里有吗？    {farm.exists()}（预期 True）")

    got = _wait_for_file(census_out, timeout=15.0)
    entries = {e["id"]: e for e in (got.get("entries") or [])}
    print(f"  进程还活着？ {inst.alive()}")

    assert not linked.exists(), "前提被破坏：timer 竟然被 link 进 profile 了"
    for eid in ("timer", "hmr"):
        e = entries.get(eid)
        assert e is not None and e["fiberState"] == 2, f"裸包名 {eid} 没能激活——那 link 就是必需的\n{inst.logs()}"
    print("  → 裸包名不用 link 进 profile：parent-walk 找到了上一层的共享 node_modules")


# ── 用例 9 · 相对路径的 name：指到目录 vs 指到文件 ──────────────────────────


@pytest.mark.parametrize("kind, suffix", [("指向目录", ""), ("指向文件", "/index.js")])
def test_relative_name_resolution(lab_home: LabHome, fixtures_dir: Path, launch, kind: str, suffix: str):
    """相对路径的 `name` 怎么解析？

    上一条证明了裸包名以 dsh 安装目录为锚——那对官方包够用，但自己的教学
    插件不在那儿，只能靠 `link_plugin` 建 junction 或者写相对路径。源码里
    两种名字走的是两条不同的分支（`cordis-plugin-loader` 的 `EntryTree.import`）：

        name.startsWith(".")  →  import(new URL(name, ctx.baseUrl))   // URL 解析
        否则                   →  import(name)                          // 包解析

    这个区别有个不显然的后果：只有包解析认 package.json。相对路径走的是纯 URL
    解析，压根不看 package.json——那条回退链不存在。所以同一个插件目录，写成
    包名能加载，写成相对路径可能就不行。
    """
    label = "dir" if not suffix else "file"
    census_out = lab_home.root / f"census-rel-{label}.json"
    profile = lab_home.make_minimal_profile(f"rel{label}")
    # 故意不 link——全靠相对路径找过去
    source = (fixtures_dir / "census").resolve()
    # 假 home 和 fixtures 都在实验台里，必然同盘，relpath 一定算得出
    spec = "./" + Path(os.path.relpath(source, profile.dir.resolve())).as_posix() + suffix
    print(f"\n{kind}")
    print(f"  相对路径   {spec}")

    profile.write_patch(
        profile.read_patch()
        + f"""# 相对路径引用
- insert:
    - id: census
      name: {json.dumps(spec)}
      config:
        out: {json.dumps(census_out.as_posix())}
        delayMs: 2000
"""
    )

    linked = profile.dir / "node_modules" / "census"
    print(f"  有没有 link？ {linked.exists()}（预期 False）")

    inst = launch(profile, wait_http=False)
    time.sleep(4.0)
    print(f"  进程还活着？ {inst.alive()}")

    if suffix:
        got = _wait_for_file(census_out, timeout=15.0)
        assert got is not None, f"指到文件应当能加载：\n{inst.logs()}"
        print("  → 相对路径指到文件可用，link 不是必需的")
    else:
        obs = _observe_fixed(inst, census_out, seconds=8.0)
        assert not obs["loaded"], "指到目录居然加载成功了——那说明相对路径也走包解析"
        code = "ERR_UNSUPPORTED_DIR_IMPORT" in obs["logs"]
        print(f"  → 指到目录加载失败，报 ERR_UNSUPPORTED_DIR_IMPORT：{code}")
        assert code, f"失败了但不是预期的原因，看日志：\n{obs['logs']}"


# ── 用例 10 · 最小构成的边界：exports/main/index.js 三条回退路 ──────────────


@pytest.mark.parametrize(
    ("variant", "entry_file", "manifest_extra", "should_load"),
    [
        ("exports 指向入口", "index.js", {"exports": {".": "./index.js"}}, True),
        ("无 exports，入口恰好叫 index.js", "index.js", {}, True),
        ("无 exports，入口叫别的名字", "plugin.js", {}, False),
        ("无 exports，但 main 指向入口", "plugin.js", {"main": "./plugin.js"}, True),
    ],
    ids=["exports", "index-fallback", "no-entry-point", "main-fallback"],
)
def test_resolution_is_the_real_boundary(
    lab_home: LabHome, fixtures_dir: Path, launch, tmp_path, variant, entry_file, manifest_extra, should_load
):
    """包解析的边界不在 `exports`，而在「Node 能不能 resolve 到入口」。

    Node 的解析有回退链：`exports["."]` → `main` → 默认 `index.js`，三条路
    任意一条通，插件就能被 resolve 到。只有三条全断（没 exports、没 main、
    入口又不叫 index.js）才真的加载不了。所以「`exports["."]` 指向真实存在的
    host 入口」是推荐做法（显式，且能同时声明 `./client` 等子路径），不是
    Node 的硬性要求。
    """
    pkg_name = f"boundary-{entry_file.split('.')[0]}-{'yes' if should_load else 'no'}-{len(manifest_extra)}"
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir()

    (pkg_dir / entry_file).write_text(
        (fixtures_dir / "minimal" / "index.js").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (pkg_dir / "package.json").write_text(
        json.dumps(
            {"name": pkg_name, "version": "0.0.0", "private": True, "type": "module", **manifest_extra}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )

    witness = lab_home.root / f"witness-{pkg_name}.json"
    profile = lab_home.make_minimal_profile(f"res-{pkg_name}", patch=_insert(pkg_name, pkg_name, witness))
    profile.link_plugin(pkg_name, pkg_dir)

    inst = launch(profile, wait_http=False)
    try:
        if should_load:
            got = _wait_for_file(witness, timeout=30)
            assert got["marker"] == "name-resolution-minimal-v1"
            print(f"\n  [{variant}] → 加载了（符合预期）")
        else:
            # 「验证什么都不该发生」：必须固定长等待，不能轮询提前退出
            time.sleep(12)
            assert not witness.exists(), f"[{variant}] 竟然还能加载？"
            print(f"\n  [{variant}] → 没加载（符合预期）。实例还活着={inst.alive()}")
    finally:
        inst.stop()


# ── 用例 11 · 对照组：正确的相对路径就是能跑 ────────────────────────────────


def test_correct_relative_name_just_runs(lab_home: LabHome, fixtures_dir: Path, launch):
    """对照组：同一份文件，`name` 写对了（`./tool.mjs`）就跑了。

    这条排除「插件本身有毛病」这种可能——前面写错的那些失败全部只跟 `name`
    有关，不是文件本身的问题。
    """
    events_path = lab_home.root / "events-ok.jsonl"
    profile = lab_home.make_minimal_profile(
        "ok",
        patch=f"""# name-resolution 活层：对照组
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: {json.dumps(events_path.as_posix())}
        flushMs: 100

- insert:
    - id: tool
      name: ./tool.mjs
""",
    )
    profile.link_plugin("lab-recorder", RECORDER)
    shutil.copy2(fixtures_dir / "tool.mjs", profile.dir / "tool.mjs")

    inst = launch(profile, wait_http=False)
    said = inst.wait_for(lambda: reports(read_events(events_path), who="tool"), timeout=40.0, what="tool 说话")

    print("\n══ 对照：同一份文件，name 写对 ══")
    print(f"  实例还活着？  {inst.alive()}")
    print(f"  它说的话：    {[e.get('note') for e in said]}")

    assert inst.alive(), f"实例应当活着：\n{inst.logs()}"
    assert said[0]["note"] == "工具插件跑起来了"
