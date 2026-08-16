"""L3 · `name` 的三条解析路径 —— 条目的 `name` 怎么变成一个真的模块。

⚠️ 矫正型：官方文档写了「插件路径必须是绝对路径」（`zh/user/develop/basic/
index.md:56`），但紧接着那句解释了原因——那是 `--patch` overlay 语境下的安全
建议（相对路径以 profile 目录为锚，不是以 patch 文件自身为锚，容易踩坑），
不是解析规则的全部。本课把「建议」和「规则」分清楚。

源码（`cordis-plugin-loader` 的 `EntryTree.import`）：

    if (name.startsWith("cordis:")) return this.ctx.loader.builtins[name.slice(7)]
    return composeError(async (info) => {
      if (this.ctx.loader.internal) return await this.ctx.loader.internal.import(name, this.ctx.baseUrl, {})
      else if (name.startsWith(".")) return await import(new URL(name, this.ctx.baseUrl).href)
      else return await import(name)
    }, getOuterStack)

第一件事必须先测：`ctx.loader.internal` 是否激活决定后面所有分支的因果解释
挂在哪——如果它激活，相对/绝对/裸包名全走同一条路，"三条路径"就不成立。

L0 已经立住的底子（本课直接复用，不重测）：
  - 裸包名以 dsh 安装目录为锚（共享 node_modules 符号链接农场）
  - 相对路径以 profile 目录为锚，且必须指到文件（指目录报 ERR_UNSUPPORTED_DIR_IMPORT）
  - `cordis:` 内置表只有 `include` 和 `group` 两项
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from lab import Instance, LabHome

#: 结果未知的用例统一用多久的固定等待。轮询提前退出只能证明"此刻还没发生"，
#: 证明不了"不会发生"——本课好几条用例的答案本身就是未知数，不能用轮询作弊。
OBSERVE = 10.0


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _insert(entry_id: str, name: str, witness: Path, **extra) -> str:
    """生成一条带 config.witness 的活层 insert。"""
    config = {"witness": witness.as_posix(), **extra}
    config_yaml = "\n".join(f"        {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in config.items())
    return f"""# L3 活层
- insert:
    - id: {entry_id}
      name: {json.dumps(name, ensure_ascii=False)}
      config:
{config_yaml}
"""


def _insert_bare(entry_id: str, name: str) -> str:
    """生成一条没有 config 的活层 insert —— 用于预期加载失败、apply 根本不会跑的用例。"""
    return f"""# L3 活层
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


# ── 用例 1 · 决定性的前置问题 ────────────────────────────────────────────────


def test_loader_internal_activated(lab_home: LabHome, fixtures_dir: Path, launch):
    """`ctx.loader.internal` 是否激活？—— 本课第一个、也是最要紧的问题。

    它决定后面每一个用例的因果解释挂在哪条分支上：激活时相对路径 / 绝对路径 /
    裸包名全部经同一条 `internal.import(name, baseUrl, {})`，name 原样传入、
    不做任何前缀判断，"三条互不相通的解析路径"的说法就不成立。

    探针本身走裸包名加载（两个分支下这条路都会成功），所以能不能测到这件事
    跟「internal 是否激活」这个问题本身正交，可以放心当第一条用例。
    """
    witness = lab_home.root / "witness-internal.json"
    profile = lab_home.make_minimal_profile("internal", patch=_insert("probe", "l03-probe", witness))
    profile.link_plugin("l03-probe", fixtures_dir / "l03-probe")

    launch(profile, wait_http=False)
    got = _wait_for_file(witness)

    print(f"\n  ctx.get('loader').internal 是否激活：{got['loaderInternal']}")
    print(f"  ctx.baseUrl：{got['baseUrl']!r}")
    if got["loaderInternal"]:
        print("  → internal 分支激活：相对/绝对/裸包名全走同一条路，不做前缀判断")
        print("    本课后面每条用例的解释都要挂在这条分支上，不是「三条路径」")
    elif got["loaderInternal"] is False:
        print("  → internal 未激活：真的按三条分支分派（cordis: / 相对路径 / 包解析）")
        print("    SYLLABUS 里画的那张三分支图对本次部署成立")
    else:
        print("  → 拿不到判定结果（loader 服务本身取不到）")

    assert got["loaderInternal"] is not None, (
        "探针应当能测到这个字段——拿到 None 说明连 loader 服务本身都取不到，那是比「internal 激不激活」更严重的问题"
    )


# ── 用例 2、3 · 绝对路径 vs file:// URL ──────────────────────────────────────


def test_windows_absolute_path(lab_home: LabHome, fixtures_dir: Path, launch):
    """Windows 绝对路径（`D:\\...\\index.js`）能不能被当作 `name` 加载？

    源码里唯一处理绝对路径的 `HostResolvedRootInclude` 是从未执行的死代码
    （L0 已证实：`bareModuleBaseUrl` 恒为 undefined，那个子类永远不会被实例化）。
    绝对路径原样是个字符串：不以 "." 开头、也不是 `cordis:` 前缀，如果 internal
    未激活就落进"否则"桶，走裸 `import(name)`。

    Node 的 ESM 解析器对着一个"看起来像文件系统路径、但既不是合法 URL、
    也不是合法包名"的字符串会怎么处理，没有先验答案——Windows 路径里的盘符
    冒号（`D:`）还可能被误判成协议前缀，必须实测，不能照抄 POSIX 直觉。
    """
    witness = lab_home.root / "witness-abswin.json"
    abs_path = str((fixtures_dir / "l03-probe" / "index.js").resolve())
    print(f"\n  绝对路径：{abs_path}")

    profile = lab_home.make_minimal_profile("abswin", patch=_insert("probe", abs_path, witness))
    # 故意不 link —— 全靠这个绝对路径字符串本身，跟裸包名解析（以 dsh 安装目录
    # 为锚）划清界限

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

    这条用来跟「Windows 绝对路径」形成对照——如果两条的成败不一样，问题就不在
    "Node 能不能识别这个字符串"，而在"cordis 有没有在真正解析前先拦一道"。
    """
    witness = lab_home.root / "witness-fileurl.json"
    file_url = (fixtures_dir / "l03-probe" / "index.js").resolve().as_uri()
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

    这条从头到尾没建立过 fiber，是第三种失败形态——跟 PENDING（L0/L11）、
    FAILED（apply 抛异常）不是一类，报错文本是 cordis 自造的，不是 Node 的。
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
    profile = lab_home.make_minimal_profile("nopkg", patch=_insert_bare("missing", "l03-definitely-does-not-exist"))

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
    "pkg, should_load",
    [("l03-subpath-declared", True), ("l03-subpath-undeclared", False)],
    ids=["declared", "undeclared"],
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
        assert got["marker"] == "l03-subpath-declared-tool-v1"
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

    `l03-fallback` 包故意让 L1 验过的三条回退路全断（没 exports、没 main，
    真代码又不叫 index.js，叫 plugin.js）——按 L1 的结论，**包名**引用这个包
    应该失败。这条补上对照面：同一份代码，**相对路径**直接指到 plugin.js，
    走的是纯 URL 解析，压根不看 package.json，那条回退链根本不存在，
    理应成功。两条路径指向同一段字节，成败却相反，边界就摆在这里。
    """
    source = (fixtures_dir / "l03-fallback" / "plugin.js").resolve()

    # 分支 A：相对路径直指非入口文件
    witness_rel = lab_home.root / "witness-fallback-rel.json"
    profile_rel = lab_home.make_minimal_profile("fallback-rel")
    spec = "./" + Path(os.path.relpath(source, profile_rel.dir.resolve())).as_posix()
    profile_rel.write_patch(_insert("plugin", spec, witness_rel))
    print(f"\n  相对路径：{spec}")

    got_rel = _run_until_witness(launch, profile_rel, witness_rel)
    print(f"  相对路径直指非入口文件 → 加载成功，marker={got_rel['marker']}")
    assert got_rel["marker"] == "l03-fallback-plugin-v1"

    # 分支 B：同一份代码，走包名解析
    witness_pkg = lab_home.root / "witness-fallback-pkg.json"
    profile_pkg = lab_home.make_minimal_profile("fallback-pkg", patch=_insert("plugin", "l03-fallback", witness_pkg))
    profile_pkg.link_plugin("l03-fallback", fixtures_dir / "l03-fallback")

    inst_pkg = launch(profile_pkg, wait_http=False)
    obs_pkg = _observe_fixed(inst_pkg, witness_pkg)
    print(f"  包名引用（同一份代码）→ 加载成功？ {obs_pkg['loaded']}")
    if not obs_pkg["loaded"]:
        print(f"  进程还活着？ {obs_pkg['alive']}\n{obs_pkg['logs']}")

    assert not obs_pkg["loaded"], (
        "包名解析不该找到 plugin.js —— exports/main/index.js 三条回退路全断，"
        "如果这里加载成功了，说明回退链比 L1 记录的更宽，这是个重大发现"
    )
    print("  → 同一份代码：相对路径能到，包名到不了。回退链只属于包解析，相对路径没有")
