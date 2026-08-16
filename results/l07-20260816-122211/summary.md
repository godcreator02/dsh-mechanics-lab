# l07 · 20260816-122211

跑于 2026-08-16 12:22:11（本地时间）

## 用例

### ✅ `test_include_config_holds_full_recipe`  ·  3.07s

```
── settle：静态构成 ──
    服务：loader, timer, hmr
    · id=include          cordis:include                   state=2
        config.patches：present=True count=2
          - {'op': 'insert', 'ids': ['census', 'profile-marker']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=census           l07-census                       state=2  ⊂include
    · id=profile-marker   l07-marker-profile               无 fiber [disabled]  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include
    · id=cf1066ab         @deepseek-ai/cordis-plugin-timer state=2
    · id=f1d8ba26         @deepseek-ai/cordis-plugin-hmr   state=2

  include.config.patches 里的 id：['census', 'profile-marker', 'home-marker']
```

### ✅ `test_recipe_hot_reload_updates_include_config`  ·  8.59s

```
改动前 include.config.patches 里的 id：['census', 'profile-marker', 'home-marker']
  活层文件已改动，多插了 profile-marker-2，等第二张快照…

  ── settle2：改动之后 ──
    服务：loader, timer, hmr
    · id=include          cordis:include                   state=2
        config.patches：present=True count=2
          - {'op': 'insert', 'ids': ['census', 'profile-marker', 'profile-marker-2']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=census           l07-census                       state=2  ⊂include
    · id=profile-marker   l07-marker-profile               无 fiber [disabled]  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include
    · id=profile-marker-2 l07-marker-profile-2             无 fiber [disabled]  ⊂include
    · id=4687b8c0         @deepseek-ai/cordis-plugin-timer state=2
    · id=f125e5fd         @deepseek-ai/cordis-plugin-hmr   state=2

  改动之后 include.config.patches 里的 id：['census', 'profile-marker', 'profile-marker-2', 'home-marker']
```

### ✅ `test_fallback_creates_even_when_disabled`  ·  2.58s

```
── 禁用之后 ──
    服务：loader, timer, hmr
    · id=include          cordis:include                   state=2
        config.patches：present=True count=2
          - {'op': 'insert', 'ids': ['census', 'my-hmr']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=census           l07-census                       state=2  ⊂include
    · id=my-hmr           @deepseek-ai/cordis-plugin-hmr   无 fiber [disabled]  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include
    · id=4cd13e98         @deepseek-ai/cordis-plugin-timer state=2
    · id=a1ad003e         @deepseek-ai/cordis-plugin-hmr   state=2

  hmr 条目：[('my-hmr', True), ('a1ad003e', False)]
```

### ✅ `test_fallback_skips_when_own_hmr_active`  ·  2.57s

```
── 自带激活的 hmr ──
    服务：loader, timer, hmr
    · id=include          cordis:include                   state=2
        config.patches：present=True count=2
          - {'op': 'insert', 'ids': ['census', 'my-timer', 'my-hmr']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=census           l07-census                       state=2  ⊂include
    · id=my-timer         @deepseek-ai/cordis-plugin-timer state=2  ⊂include
    · id=my-hmr           @deepseek-ai/cordis-plugin-hmr   state=2  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include

  hmr 条目：['my-hmr']
```

### ✅ `test_ghost_ids_differ_names_stable`  ·  5.13s

```
── ghosta 的 settle 快照 ──
    服务：loader, timer, hmr
    · id=include          cordis:include                   state=2
        config.patches：present=True count=2
          - {'op': 'insert', 'ids': ['census']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=census           l07-census                       state=2  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include
    · id=6577c16c         @deepseek-ai/cordis-plugin-timer state=2
    · id=0a50809b         @deepseek-ai/cordis-plugin-hmr   state=2

  ghosta 的幽灵条目：{'plugin-timer': '6577c16c', 'plugin-hmr': '0a50809b'}

  ── ghostb 的 settle 快照 ──
    服务：loader, timer, hmr
    · id=64200777         @deepseek-ai/cordis-plugin-timer state=2
    · id=include          cordis:include                   state=2
        config.patches：present=True count=2
          - {'op': 'insert', 'ids': ['census']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=census           l07-census                       state=2  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include
    · id=c2500901         @deepseek-ai/cordis-plugin-hmr   state=2

  ghostb 的幽灵条目：{'plugin-timer': '64200777', 'plugin-hmr': 'c2500901'}

  → id 不稳定，只能认 name（包名后缀）
```

### ✅ `test_ghost_creation_does_not_lose_settle_snapshot`  ·  6.58s

```
普查员在观察窗口内被 apply 了 1 次
    record[0]：applyIndex=0，拍到的快照=['boot', 'settle', 'settle2']

  → 未复现（跟 L0 两次复跑的结果一致）。结合上面的源码证据，现在有理由认为不是『还没抓到』，是『这条因果链本身大概率不存在』——L0 那次 settle 丢失更可能是旧版工具自己的缺陷（record 建在 apply 里、被覆盖），不是框架触发了整树刷新。
```

## 归档的观测产物

- `census-fallback-active.json` — 4,313 字节
- `census-fallback-disabled.json` — 4,235 字节
- `census-ghost-ghosta.json` — 3,655 字节
- `census-ghost-ghostb.json` — 3,655 字节
- `census-recipe-hot.json` — 6,883 字节
- `census-recipe-static.json` — 4,243 字节
- `census-refresh.json` — 5,700 字节
