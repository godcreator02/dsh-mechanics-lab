# l00 · 20260816-033254

跑于 2026-08-16 03:32:54（本地时间）

## 用例

### ✅ `test_profile_minimal_files`  ·  6.06s

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

### ✅ `test_empty_bundles_boots`  ·  6.44s

```
--dump-config 算出 1 个条目：
    · census → l00-census

进程还活着？ True（退出码 None，死于 +Nones）
普查员写出见证文件了吗？ True

  ── boot 期快照 ──
    服务：loader
    · id=include                      cordis:include                             state=1
    · id=census                       l00-census                                 state=1

  ── settle 快照 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=7656669d                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=af2cec8c                     @deepseek-ai/cordis-plugin-hmr             state=2
```

### ✅ `test_ghost_entries`  ·  6.42s

```
配方里的条目（1 个）：['l00-census']

  ── boot 期：boot() 还没返回 ──
    服务：loader
    · id=include                      cordis:include                             state=1
    · id=census                       l00-census                                 state=1

  ── settle：boot() 返回之后 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=71a597ee                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=aea3403d                     @deepseek-ai/cordis-plugin-hmr             state=2

  幽灵条目（树里有、配方里没有）：['@deepseek-ai/cordis-plugin-hmr', '@deepseek-ai/cordis-plugin-timer', 'cordis:include']
  boot 之后新增的条目 id：['71a597ee', 'aea3403d']
```

### ✅ `test_hmr_fallback_condition`  ·  6.06s

```
── 自带 timer + hmr 时的 settle 快照 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=my-timer                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=my-hmr                       @deepseek-ai/cordis-plugin-hmr             state=2

  树里的 hmr 条目共 1 个：['my-hmr']
  hmr 服务在不在：True
```

### ✅ `test_bare_name_resolution`  ·  6.07s

```
timer 有没有被 link 进 profile？ False（预期 False）

  ── settle 快照 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=unlinked-timer               @deepseek-ai/cordis-plugin-timer           state=2
    · id=9413a65f                     @deepseek-ai/cordis-plugin-hmr             state=2

进程还活着？ True（退出码 None）
  没 link 的 timer 条目：{'id': 'unlinked-timer', 'name': '@deepseek-ai/cordis-plugin-timer', 'disabled': False, 'hasFiber': True, 'fiberState': 2, 'inject': []}
  → 裸包名以 dsh 安装目录为锚，官方包不需要 link
```

### ✅ `test_relative_name_resolution[\u6307\u5411\u76ee\u5f55-]`  ·  0.52s

```
指向目录
  profile 在 D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\reldir
  相对路径   ./../../../../experiments/l00_minimal_environment/fixtures/l00-census
  有没有 link？ False（预期 False）

  普查员被加载了吗？ False
  进程还活着？ False（退出码 1）
  → 指到**目录**加载失败，报 ERR_UNSUPPORTED_DIR_IMPORT：True
```

### ✅ `test_relative_name_resolution[\u6307\u5411\u6587\u4ef6-/index.js]`  ·  6.03s

```
指向文件
  profile 在 D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\relfile
  相对路径   ./../../../../experiments/l00_minimal_environment/fixtures/l00-census/index.js
  有没有 link？ False（预期 False）

  普查员被加载了吗？ True
  进程还活着？ True（退出码 None）
  → 相对路径指到**文件**可用，link 不是必需的
```

### ✅ `test_who_keeps_process_alive`  ·  15.08s

```
看了 15 秒。进程还活着？ True

  ── 还活着时树里有什么 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=e47908bb                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=5aa3bb20                     @deepseek-ai/cordis-plugin-hmr             state=2
```

### ✅ `test_baseline_profile`  ·  12.13s

```
── 基线 · 默认（兜底） ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=0ed6ff84                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=d3c7fe74                     @deepseek-ai/cordis-plugin-hmr             state=2
    hmr 条目：['d3c7fe74']

  ── 基线 · 自挂 hmr ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=timer                        @deepseek-ai/cordis-plugin-timer           state=2
    · id=hmr                          @deepseek-ai/cordis-plugin-hmr             state=2
    · id=census                       l00-census                                 state=2
    hmr 条目：['hmr']
```

### ✅ `test_pending_at_boot_is_fatal`  ·  0.58s

```
进程还活着？ False（退出码 1，死于 +0.5s）
needy 的 apply 被调用过吗？ False（预期 False —— 服务永远等不到）

日志里的审计判词：['Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate', 'l00-needy: pending (waiting for service: definitelyNotAService)', '  [cause]: Error: dsh: 1 entry did not activate', '  l00-needy: pending (waiting for service: definitelyNotAService)']
```

## 归档的观测产物

- `census-alive.json` — 1,866 字节
- `census-bare.json` — 2,094 字节
- `census-baseline-auto.json` — 1,866 字节
- `census-baseline-own.json` — 2,280 字节
- `census-empty.json` — 1,866 字节
- `census-ghost.json` — 1,866 字节
- `census-minimal.json` — 38,137 字节
- `census-ownhmr.json` — 2,292 字节
- `census-pending.json` — 964 字节
- `census-rel-file.json` — 2,002 字节
