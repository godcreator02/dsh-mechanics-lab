# l00 · 20260816-095521

跑于 2026-08-16 09:55:21（本地时间）

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

### ✅ `test_empty_bundles_boots`  ·  6.51s

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
    · id=03d10f27                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=a3df99b6                     @deepseek-ai/cordis-plugin-hmr             state=2
```

### ✅ `test_ghost_entries`  ·  6.48s

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
    · id=28c8da39                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=1f7ef402                     @deepseek-ai/cordis-plugin-hmr             state=2

  幽灵条目（树里有、配方里没有）：['@deepseek-ai/cordis-plugin-hmr', '@deepseek-ai/cordis-plugin-timer', 'cordis:include']
  boot 之后新增的条目 id：['1f7ef402', '28c8da39']
```

### ✅ `test_infra_cannot_be_opted_out[\u663e\u5f0f\u7981\u7528 hmr-\n    - id: my-hmr\n      name: '@deepseek-ai/cordis-plugin-hmr'\n      disabled: true\n]`  ·  6.06s

```
── 显式禁用 hmr 之后的 settle 快照 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=my-hmr                       @deepseek-ai/cordis-plugin-hmr             无 fiber [disabled]
    · id=b445eae7                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=980f6db2                     @deepseek-ai/cordis-plugin-hmr             state=2

  进程还活着？ True
  普查员被 apply 了 1 次
    plugin-timer：共 1 条，其中没被禁用的 1 条 → ['b445eae7']
    plugin-hmr：共 2 条，其中没被禁用的 1 条 → ['980f6db2']
  → 禁不掉。禁用只是让框架另造一份，服务照样在
```

### ✅ `test_infra_cannot_be_opted_out[\u8fde timer \u4e00\u8d77\u7981\u7528-\n    - id: my-timer\n      name: '@deepseek-ai/cordis-plugin-timer'\n      disabled: true\n\n    - id: my-hmr\n      name: '@deepseek-ai/cordis-plugin-hmr'\n      disabled: true\n]`  ·  6.07s

```
── 连 timer 一起禁用 之后的 settle 快照 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=my-timer                     @deepseek-ai/cordis-plugin-timer           无 fiber [disabled]
    · id=my-hmr                       @deepseek-ai/cordis-plugin-hmr             无 fiber [disabled]
    · id=d61d776c                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=ec95668d                     @deepseek-ai/cordis-plugin-hmr             state=2

  进程还活着？ True
  普查员被 apply 了 1 次
    plugin-timer：共 2 条，其中没被禁用的 1 条 → ['d61d776c']
    plugin-hmr：共 2 条，其中没被禁用的 1 条 → ['ec95668d']
  → 禁不掉。禁用只是让框架另造一份，服务照样在
```

### ✅ `test_hmr_fallback_condition`  ·  6.07s

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

### ✅ `test_bare_name_resolution`  ·  6.08s

```
timer 有没有被 link 进 profile？ False（预期 False）

  ── settle 快照 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=unlinked-timer               @deepseek-ai/cordis-plugin-timer           state=2
    · id=50c54664                     @deepseek-ai/cordis-plugin-hmr             state=2

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

### ✅ `test_who_keeps_process_alive`  ·  15.09s

```
看了 15 秒。进程还活着？ True

  ── 还活着时树里有什么 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=a5f34477                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=c1dceb16                     @deepseek-ai/cordis-plugin-hmr             state=2
```

### ✅ `test_baseline_profile`  ·  12.15s

```
── 基线 · 默认（兜底） ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=16592f9f                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=497fa359                     @deepseek-ai/cordis-plugin-hmr             state=2
    hmr 条目：['497fa359']

  ── 基线 · 自挂 hmr ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=timer                        @deepseek-ai/cordis-plugin-timer           state=2
    · id=hmr                          @deepseek-ai/cordis-plugin-hmr             state=2
    · id=census                       l00-census                                 state=2
    hmr 条目：['hmr']
```

### ✅ `test_pending_at_boot_is_fatal`  ·  0.61s

```
进程还活着？ False（退出码 1，死于 +0.5s）
needy 的 apply 被调用过吗？ False（预期 False —— 服务永远等不到）

日志里的审计判词：['Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate', 'l00-needy: pending (waiting for service: definitelyNotAService)', '  [cause]: Error: dsh: 1 entry did not activate', '  l00-needy: pending (waiting for service: definitelyNotAService)']
```

## 归档的观测产物

- `census-alive.json` — 2,065 字节
- `census-bare.json` — 2,309 字节
- `census-baseline-auto.json` — 2,065 字节
- `census-baseline-own.json` — 2,511 字节
- `census-empty.json` — 2,065 字节
- `census-ghost.json` — 2,065 字节
- `census-nohmr.json` — 2,519 字节
- `census-noinfra.json` — 2,981 字节
- `census-ownhmr.json` — 2,523 字节
- `census-pending.json` — 1,083 字节
- `census-rel-file.json` — 2,201 字节
