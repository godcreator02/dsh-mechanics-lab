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
  `dsh.bundle` 的包。这条现在有跨项目的实测印证：同组 `four-ways` 项的
  `test_four_ways_mount_the_same_entry` 真跑了一次 `dsh plugin add`，安装后
  `dsh.profile.bundles` 确实被写入了包名（归档
  `four-ways/results/20260817-142825/profiles/installed/package.json`）
- **只碰 `package.json` 的 `dependencies` 与 `dsh.profile.bundles` 两处，
  不碰活层 patch 文件。** `runPlugin()` 里没有任何代码路径写
  `cordis.patch.yml`——那份文件完全是别的机制（活层 insert）的地盘
- **相对路径参数按调用目录锚定，不按 profile 目录锚定。** `anchorPathSpec()`
  把 `.`/`..` 开头的路径参数（含 `file:`/`link:` 前缀）改写成相对于
  `process.cwd()` 的绝对路径——pnpm 实际的 `cwd` 是 profile 目录，如果不做
  这一步，`add .` 这种写法会在插件自己的检出目录里执行、把 profile 自链接
  进自己

## 观测方法

⚠️ **本项不实际执行子命令，这是本项自己的选择，不是纪律逼的。** 实验纪律
（`CLAUDE.md` 第四节「`dsh plugin`」一行）禁的是「对生产 home 跑」和「装会
联网拉取的包」这两件事，不是这条命令本身——对假 home 里的 profile 跑、装本地
目录都是允许的。`four-ways` 项里 `test_four_ways_mount_the_same_entry` 的
途径③就真跑了这条命令（用来对比四种交付途径，两条边界都没踩）。本项仍然
选择只读源码：要坐实的是命令的实现写法本身，不是它跑起来的效果，静态分析
就够了；跑起来之后的效果由 `four-ways` 的真实执行提供实测印证（见上面
「判定」第二条）。

判定完全来自读源码：`lab.dsh_bin()` 定位到本机 npx 缓存里的 dsh 部署，用例
再从它的 `bin.js` 找到 `plugin` 子命令实际 import 的那个模块（不写死带哈希的
文件名，改成从 `bin.js` 里动态解析 import 路径，这样能扛住构建产物换哈希），
读它的源码文本，对着上面判定里列的几个行为特征做正则匹配——只读磁盘上的文件，
不起子进程、不碰网络、不改任何 profile。只要 dsh 包整体升级到某个「plugin」
不再是 `case "plugin"` 这个写法的版本，这条用例会直接报「找不到 import」而
失败，不会静默通过一份读不到东西的空判定。

## 没覆盖到的

- **`--profile <名>` 传一个不存在的名字，会不会新建一个同名 profile 而不是
  报错——没有用例覆盖这条，只有一处源码线索。** `bin.js` 里 `plugin` 子命令的
  选项描述写的是「the profile whose plugins to manage (initialized on first
  use)」，字面意思是「不存在就在首次使用时初始化」，但这只是命令行帮助文本、
  不是行为断言，本项和 `four-ways` 都没有实际传一个打错的 profile 名跑一遍、
  确认它到底新建了 profile 还是报了错
- **命令的回显（pnpm 打印在终端上的路径）与写进 `package.json` 的落盘内容
  是不是两个不同的东西——这个对照本身没有用例覆盖。** 落盘那一侧已经有实测
  印证：`four-ways` 归档的 `package.json` 里 `"ch2-courier":
  "link:D:/…/fixtures/courier"` 确实是绝对路径的 `link:`；但回显那一侧（pnpm
  输出的文本，比如是不是打的相对路径）没有被任何现存用例捕获或打印过——
  `install()` 返回的 `subprocess.CompletedProcess.stdout` 从来没被读取，「回显
  ≠ 落盘」这句话本身缺实验支撑，只有「落盘是绝对路径」这半有证据
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
