"""install-command · 官方安装命令改写了 profile 的什么

档次 ② ｜ 性质 📗 复述型（源码） ｜ 状态 ⚠️ 部分 ｜ 1 条用例 ｜ 不需要 web

## 判定

- **`dsh plugin --profile <名> add <包...>` 是一层很薄的转发。** 它在 profile
  目录里跑 `pnpm <参数...>`（`spawnSync`，`cwd` 设成 profile 目录、
  `stdio: "inherit"`），pnpm 成功之后才做第二件事：对账
  `dsh.profile.bundles`。证据：源码
  `@deepseek-ai/dsh` 打包产物 `lib/plugin-9h8shc4d.js` 的 `runPlugin()`
  （该包没有 `src/`，只能读打包产物；文件名带的哈希是构建产物的一部分，
  不同版本可能不同，见下方「本项不实际执行子命令」那段）
- **对账按「安装后的状态」重新算整份名单，不是按「这次装了什么」做差量。**
  `reconcilePlugins()` 遍历安装后 `package.json` 里全部
  `dependencies`：哪个依赖解析到的包声明了 `dsh.bundle.patch`，就把包名补进
  `dsh.profile.bundles`（没在名单里才补，已有的不重复）；哪个名单里的包
  不再是「依赖 + 声明了 bundle」，就从名单里删掉。按安装后状态重新核对而不是
  比较本次命令的参数差异，意味着 `update` 也能激活一个在新版本里才声明
  `dsh.bundle` 的包
- **只碰 `package.json` 的 `dependencies` 与 `dsh.profile.bundles` 两处，
  不碰活层 patch 文件。** `runPlugin()` 里没有任何代码路径写
  `cordis.patch.yml`——那份文件完全是别的机制（活层 insert）的地盘
- **相对路径参数按调用目录锚定，不按 profile 目录锚定。** `anchorPathSpec()`
  把 `.`/`..` 开头的路径参数（含 `file:`/`link:` 前缀）改写成相对于
  `process.cwd()` 的绝对路径——pnpm 实际的 `cwd` 是 profile 目录，如果不做
  这一步，`add .` 这种写法会在插件自己的检出目录里执行、把 profile 自链接
  进自己

## 观测方法

⚠️ **本项不实际执行子命令。** 项目实验纪律禁止在实验台里真跑 `dsh plugin`
任何子命令（会真的联网走 pnpm 的域名解析、真的改写假 home 下的 profile）；
`four-ways` 项里 `test_four_ways_mount_the_same_entry` 的途径③真跑了这条命令
（用来对比四种交付途径），那是它自己权衡后的决定（见该项 docstring），跟本项
遵守的纪律不冲突——本项要坐实的是源码写法本身，不需要真跑一遍。

判定完全来自读源码：`lab.dsh_bin()` 定位到本机 npx 缓存里的 dsh 部署，用例
再从它的 `bin.js` 找到 `plugin` 子命令实际 import 的那个模块（不写死带哈希的
文件名，改成从 `bin.js` 里动态解析 import 路径，这样能扛住构建产物换哈希），
读它的源码文本，对着上面判定里列的几个行为特征做正则匹配——只读磁盘上的文件，
不起子进程、不碰网络、不改任何 profile。只要 dsh 包整体升级到某个「plugin」
不再是 `case "plugin"` 这个写法的版本，这条用例会直接报「找不到 import」而
失败，不会静默通过一份读不到东西的空判定。

## 没覆盖到的

- 「按安装后的实际状态对账」这条判定目前只验证了源码写法与源码注释的描述
  一致，没有验证过真实跑一次 `pnpm add` 之后 `dsh.profile.bundles`
  确实按预期被改写——这一半需要真跑命令才能坐实，本项因纪律限制放弃了它
"""

from __future__ import annotations

import re

from lab import dsh_bin


def _plugin_module_source() -> str:
    """从 `bin.js` 找到 `plugin` 子命令 import 的模块，返回它的源码文本。"""
    bin_js = dsh_bin()
    bin_text = bin_js.read_text(encoding="utf-8")

    match = re.search(r'case\s+"plugin":\s*\{\s*const\s*\{[^}]*\}\s*=\s*await import\("(\./[^"]+\.js)"\)', bin_text)
    assert match, f"bin.js 里找不到 plugin 子命令的 import 语句，dsh 包的分发结构可能变了：{bin_js}"

    module_path = bin_js.parent / match.group(1)
    assert module_path.exists(), f"import 指向的文件不存在：{module_path}"
    return module_path.read_text(encoding="utf-8")


def test_install_command_forwards_to_pnpm_and_only_touches_manifest_bundles():
    """核对 `runPlugin()` 的几个行为特征：转发给 pnpm、cwd 在 profile 目录、
    对账只碰 `dsh.profile.bundles`、不碰活层 patch 文件。"""
    src = _plugin_module_source()

    print("\n══ dsh plugin 子命令的实现模块 ═══════════════════════════")
    print(f"  源文件大小：{len(src)} 字节")

    # ── 转发给 pnpm，cwd 是 profile 目录 ──────────────────────────────────
    spawn_at = src.find('spawnSync("pnpm"')
    assert spawn_at != -1, "该命令应当把参数转发给 pnpm 执行，不是自己实现安装逻辑"
    spawn_block = src[spawn_at : spawn_at + 300]  # 定长窗口，不靠配对括号找边界
    assert "cwd: dir" in spawn_block, f"pnpm 应当在 profile 目录（变量 dir）里跑，实际调用块：\n{spawn_block}"

    # ── 对账函数：读安装后的清单，按声明了 dsh.bundle 与否增删 bundles 名单 ──
    assert "function reconcilePlugins" in src, "找不到对账函数 reconcilePlugins"
    reconcile_match = re.search(r"function reconcilePlugins\([\s\S]*?\n\}", src)
    assert reconcile_match, "找不到 reconcilePlugins 的完整函数体"
    reconcile_body = reconcile_match.group(0)
    assert "dsh?.bundle?.patch" in src, "判断一个依赖是不是 bundle，应当看它的 dsh.bundle.patch 字段"
    assert "profile: {" in reconcile_body and "bundles: plugins" in reconcile_body, (
        f"对账写回的应当是 dsh.profile.bundles 这一份名单，实际函数体：\n{reconcile_body}"
    )

    # ── 对账函数只在成功之后才跑，且只在 pnpm 成功时执行 ──────────────────
    run_match = re.search(r"function runPlugin\([\s\S]*?\n\}", src)
    assert run_match, "找不到 runPlugin 的完整函数体"
    run_body = run_match.group(0)
    assert "reconcilePlugins(before, dir)" in run_body, f"runPlugin 应当在成功后调用 reconcilePlugins：\n{run_body}"

    # ── 不写活层 patch 文件：这整个模块源码里不该出现 cordis.patch.yml ──────
    assert "cordis.patch.yml" not in src, "这条命令不该碰 profile 的活层 patch 文件"

    # ── 相对路径参数按调用目录（不是 profile 目录）锚定 ────────────────────
    assert "function anchorPathSpec" in src, "找不到相对路径锚定函数 anchorPathSpec"
    anchor_match = re.search(r"function anchorPathSpec\([\s\S]*?\n\}", src)
    assert anchor_match, "找不到 anchorPathSpec 的完整函数体"
    anchor_body = anchor_match.group(0)
    assert "resolve(cwd, match.groups.path)" in anchor_body, (
        f"相对路径参数应当按调用目录（cwd 参数）锚定，实际函数体：\n{anchor_body}"
    )

    print('  转发目标：spawnSync("pnpm", ...)，cwd = profile 目录')
    print("  对账范围：package.json 的 dependencies → dsh.profile.bundles")
    print("  不碰：cordis.patch.yml（活层）")
    print("  相对路径参数锚定在调用目录，不是 profile 目录")
