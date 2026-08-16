# l00 · 20260816-032005

跑于 2026-08-16 03:20:05（本地时间）

## 用例

### ✅ `test_profile_minimal_files`  ·  6.07s

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
    · id=58bcb02e                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=fe3c9214                     @deepseek-ai/cordis-plugin-hmr             state=2
```

### ✅ `test_ghost_entries`  ·  6.53s

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
    · id=bd9e6d44                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=879630c6                     @deepseek-ai/cordis-plugin-hmr             state=2

  幽灵条目（树里有、配方里没有）：['@deepseek-ai/cordis-plugin-hmr', '@deepseek-ai/cordis-plugin-timer', 'cordis:include']
  boot 之后新增的条目 id：['879630c6', 'bd9e6d44']
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
    · id=017c56b8                     @deepseek-ai/cordis-plugin-hmr             state=2

进程还活着？ True（退出码 None）
  没 link 的 timer 条目：{'id': 'unlinked-timer', 'name': '@deepseek-ai/cordis-plugin-timer', 'disabled': False, 'hasFiber': True, 'fiberState': 2, 'inject': []}
  → 裸包名以 dsh 安装目录为锚，官方包不需要 link
```

### ✅ `test_who_keeps_process_alive`  ·  15.09s

```
看了 15 秒。进程还活着？ True

  ── 还活着时树里有什么 ──
    服务：loader, timer, hmr
    · id=88152407                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=b0ec48df                     @deepseek-ai/cordis-plugin-hmr             state=2
```

### ✅ `test_pending_at_boot_is_fatal`  ·  0.63s

```
进程还活着？ False（退出码 1，死于 +0.5s）
needy 的 apply 被调用过吗？ False（预期 False —— 服务永远等不到）

日志里的审计判词：['Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate', 'l00-needy: pending (waiting for service: definitelyNotAService)', '  [cause]: Error: dsh: 1 entry did not activate', '  l00-needy: pending (waiting for service: definitelyNotAService)']
```

## 归档的观测产物

- `census-alive.json` — 1,866 字节
- `census-bare.json` — 2,094 字节
- `census-empty.json` — 1,866 字节
- `census-ghost.json` — 1,866 字节
- `census-minimal.json` — 38,137 字节
- `census-ownhmr.json` — 2,292 字节
- `census-pending.json` — 964 字节
