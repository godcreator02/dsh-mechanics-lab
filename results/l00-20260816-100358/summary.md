# l00 · 20260816-100358

跑于 2026-08-16 10:03:58（本地时间）

## 用例

### ✅ `test_ghost_entries`  ·  6.68s

```
配方里的条目（1 个）：['l00-census']

  ── boot 期：boot() 还没返回 ──
    服务：loader
    · id=include                  cordis:include                             state=1
    ·     id=census                   l00-census                                 state=1  ⊂include

  ── settle：boot() 返回之后 ──
    服务：loader, timer, hmr
    · id=include                  cordis:include                             state=2
    ·     id=census                   l00-census                                 state=2  ⊂include
    · id=f6ca8c01                 @deepseek-ai/cordis-plugin-timer           state=2
    · id=730a50ab                 @deepseek-ai/cordis-plugin-hmr             state=2

  幽灵条目（树里有、配方里没有）：['@deepseek-ai/cordis-plugin-hmr', '@deepseek-ai/cordis-plugin-timer', 'cordis:include']
  boot 之后新增的条目 id：['730a50ab', 'f6ca8c01']
```

## 归档的观测产物

- `census-ghost.json` — 2,243 字节
