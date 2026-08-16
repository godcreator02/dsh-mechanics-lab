# l00 · 20260816-162910

跑于 2026-08-16 16:29:10（本地时间）

## 用例

### ✅ `test_profile_minimal_files`  ·  2.05s

```
启动前 cordis.yml 存在？ False
启动后 cordis.yml 存在？ True
  内容：
    | # dsh profile root — an empty entry list. The tree is composed as patches:
    | # each bundle in package.json's dsh.profile.bundles, then cordis.patch.yml, then any
    | # --patch overlays. Edit cordis.patch.yml, not this file.
    | []
进程还活着？ True（退出码 None）
```

### ✅ `test_empty_bundles_boots`  ·  6.53s

```
--dump-config 算出 1 个条目：
    · census → l00-census

进程还活着？ True（退出码 None，死于 +Nones）
普查员写出见证文件了吗？ True

  ── boot 期快照 ──
    服务：loader
    · id=include                  cordis:include                             state=1
    ·     id=census                   l00-census                                 state=1  ⊂include

  ── settle 快照 ──
    服务：loader, timer, hmr
    · id=include                  cordis:include                             state=2
    ·     id=census                   l00-census                                 state=2  ⊂include
    · id=a59e21ad                 @deepseek-ai/cordis-plugin-timer           state=2
    · id=fb786e56                 @deepseek-ai/cordis-plugin-hmr             state=2
```

### ✅ `test_effective_config_vs_entry_tree`  ·  6.58s

```
effective config 里的 id（3 个）：['census', 'hmr', 'timer']

  ── boot 期：boot() 还没返回 ──
    服务：loader
    · id=include                  cordis:include                             state=1
    ·     id=timer                    @deepseek-ai/cordis-plugin-timer           无 fiber  ⊂include
    ·     id=hmr                      @deepseek-ai/cordis-plugin-hmr             无 fiber  ⊂include
    ·     id=census                   l00-census                                 state=1  ⊂include

  ── settle：boot() 返回之后 ──
    服务：loader, timer, hmr
    · id=include                  cordis:include                             state=2
    ·     id=timer                    @deepseek-ai/cordis-plugin-timer           state=2  ⊂include
    ·     id=hmr                      @deepseek-ai/cordis-plugin-hmr             state=2  ⊂include
    ·     id=census                   l00-census                                 state=2  ⊂include

  树上有、config 里没有的：['include']
  boot 返回之后新增的 id：（没有）
```

### ✅ `test_bare_name_resolution`  ·  6.08s

```
timer 有没有被 link 进 profile？ False（预期 False）

  ── settle 快照 ──
    服务：loader, timer, hmr
    · id=include                  cordis:include                             state=2
    ·     id=census                   l00-census                                 state=2  ⊂include
    ·     id=unlinked-timer           @deepseek-ai/cordis-plugin-timer           state=2  ⊂include
    · id=25fd4470                 @deepseek-ai/cordis-plugin-hmr             state=2

进程还活着？ True（退出码 None）
  没 link 的 timer 条目：{'id': 'unlinked-timer', 'name': '@deepseek-ai/cordis-plugin-timer', 'parent': 'include', 'disabled': False, 'hasFiber': True, 'fiberState': 2, 'inject': []}
  → 裸包名以 dsh 安装目录为锚，官方包不需要 link
```

### ✅ `test_relative_name_resolution[\u6307\u5411\u76ee\u5f55-]`  ·  0.55s

```
指向目录
  profile 在 D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\reldir
  相对路径   ./../../../../experiments/l00_minimal_environment/fixtures/l00-census
  有没有 link？ False（预期 False）

  普查员被加载了吗？ False
  进程还活着？ False（退出码 1）
  → 指到**目录**加载失败，报 ERR_UNSUPPORTED_DIR_IMPORT：True
```

### ✅ `test_relative_name_resolution[\u6307\u5411\u6587\u4ef6-/index.js]`  ·  6.04s

```
指向文件
  profile 在 D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\relfile
  相对路径   ./../../../../experiments/l00_minimal_environment/fixtures/l00-census/index.js
  有没有 link？ False（预期 False）

  普查员被加载了吗？ True
  进程还活着？ True（退出码 None）
  → 相对路径指到**文件**可用，link 不是必需的
```

### ✅ `test_who_keeps_process_alive`  ·  15.09s

```
看了 15 秒。进程还活着？ True

  ── 还活着时树里有什么 ──
    服务：loader, timer, hmr
    · id=include                  cordis:include                             state=2
    ·     id=census                   l00-census                                 state=2  ⊂include
    · id=7c64a0d2                 @deepseek-ai/cordis-plugin-timer           state=2
    · id=d1bf202d                 @deepseek-ai/cordis-plugin-hmr             state=2
```

### ✅ `test_baseline_profile`  ·  12.18s

```
── 基线 · 默认 root [] ──
    服务：loader, timer, hmr
    · id=include                  cordis:include                             state=2
    ·     id=timer                    @deepseek-ai/cordis-plugin-timer           state=2  ⊂include
    ·     id=hmr                      @deepseek-ai/cordis-plugin-hmr             state=2  ⊂include
    ·     id=census                   l00-census                                 state=2  ⊂include
    hmr：id=hmr state=2 ⊂include

  ── 基线 · 指定 watch root ──
    服务：loader, timer, hmr
    · id=include                  cordis:include                             state=2
    ·     id=timer                    @deepseek-ai/cordis-plugin-timer           state=2  ⊂include
    ·     id=hmr                      @deepseek-ai/cordis-plugin-hmr             state=2  ⊂include
    ·     id=census                   l00-census                                 state=2  ⊂include
    hmr：id=hmr state=2 ⊂include
```

### ✅ `test_pending_at_boot_is_fatal`  ·  0.58s

```
进程还活着？ False（退出码 1，死于 +0.5s）
needy 的 apply 被调用过吗？ False（预期 False —— 服务永远等不到）

日志里的审计判词：['Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate', 'l00-needy: pending (waiting for service: definitelyNotAService)', '  [cause]: Error: dsh: 1 entry did not activate', '  l00-needy: pending (waiting for service: definitelyNotAService)']
```

## 归档的观测产物

- `census-alive.json` — 2,243 字节
- `census-bare.json` — 2,525 字节
- `census-baseline-dflt.json` — 2,765 字节
- `census-baseline-rooted.json` — 2,765 字节
- `census-empty.json` — 2,243 字节
- `census-ghost.json` — 2,765 字节
- `census-pending.json` — 1,177 字节
- `census-rel-file.json` — 2,379 字节
