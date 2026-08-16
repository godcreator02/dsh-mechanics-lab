# l07 · 20260816-163344

跑于 2026-08-16 16:33:44（本地时间）

## 用例

### ✅ `test_include_config_holds_full_recipe`  ·  3.08s

```
── settle：静态构成 ──
    服务：loader, timer, hmr
    · id=include          cordis:include                   state=2
        config.patches：present=True count=3
          - {'op': 'insert', 'ids': ['timer', 'hmr']}
          - {'op': 'insert', 'ids': ['census', 'profile-marker']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=timer            @deepseek-ai/cordis-plugin-timer state=2  ⊂include
    · id=hmr              @deepseek-ai/cordis-plugin-hmr   state=2  ⊂include
    · id=census           l07-census                       state=2  ⊂include
    · id=profile-marker   l07-marker-profile               无 fiber [disabled]  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include

  include.config.patches 里的 id：['timer', 'hmr', 'census', 'profile-marker', 'home-marker']
```

### ✅ `test_recipe_hot_reload_updates_include_config`  ·  8.62s

```
改动前 include.config.patches 里的 id：['timer', 'hmr', 'census', 'profile-marker', 'home-marker']
  活层文件已改动，多插了 profile-marker-2，等第二张快照…

  ── settle2：改动之后 ──
    服务：loader
    · id=include          cordis:include                   state=2
        config.patches：present=True count=2
          - {'op': 'insert', 'ids': ['census', 'profile-marker', 'profile-marker-2']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=timer            @deepseek-ai/cordis-plugin-timer 无 fiber  ⊂include
    · id=hmr              @deepseek-ai/cordis-plugin-hmr   state=5  ⊂include
    · id=census           l07-census                       state=2  ⊂include
    · id=profile-marker   l07-marker-profile               无 fiber [disabled]  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include
    · id=profile-marker-2 l07-marker-profile-2             无 fiber [disabled]  ⊂include

  改动之后 include.config.patches 里的 id：['census', 'profile-marker', 'profile-marker-2', 'home-marker']
```

### ✅ `test_include_is_the_only_ghost`  ·  2.98s

```
effective config 里的 id（4 个）：['census', 'hmr', 'home-marker', 'timer']

  ── entry tree ──
    服务：loader, timer, hmr
    · id=include          cordis:include                   state=2
        config.patches：present=True count=3
          - {'op': 'insert', 'ids': ['timer', 'hmr']}
          - {'op': 'insert', 'ids': ['census']}
          - {'op': 'insert', 'ids': ['home-marker']}
    · id=timer            @deepseek-ai/cordis-plugin-timer state=2  ⊂include
    · id=hmr              @deepseek-ai/cordis-plugin-hmr   state=2  ⊂include
    · id=census           l07-census                       state=2  ⊂include
    · id=home-marker      l07-marker-home                  无 fiber [disabled]  ⊂include

  树上有、config 里没有的 id：['include']
```

## 归档的观测产物

- `census-only-ghost.json` — 4,523 字节
- `census-recipe-hot.json` — 7,761 字节
- `census-recipe-static.json` — 5,111 字节
