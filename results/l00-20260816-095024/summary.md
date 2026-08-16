# l00 · 20260816-095024

跑于 2026-08-16 09:50:24（本地时间）

## 用例

### ❌ `test_infra_cannot_be_opted_out[\u663e\u5f0f\u7981\u7528 hmr-\n    - id: my-hmr\n      name: '@deepseek-ai/cordis-plugin-hmr'\n      disabled: true\n]`  ·  6.07s

```
── 显式禁用 hmr 之后的 settle 快照 ──
    （没有这张快照）

  进程还活着？ True
```

### ✅ `test_infra_cannot_be_opted_out[\u8fde timer \u4e00\u8d77\u7981\u7528-\n    - id: my-timer\n      name: '@deepseek-ai/cordis-plugin-timer'\n      disabled: true\n\n    - id: my-hmr\n      name: '@deepseek-ai/cordis-plugin-hmr'\n      disabled: true\n]`  ·  6.08s

```
── 连 timer 一起禁用 之后的 settle 快照 ──
    服务：loader, timer, hmr
    · id=include                      cordis:include                             state=2
    · id=census                       l00-census                                 state=2
    · id=my-timer                     @deepseek-ai/cordis-plugin-timer           无 fiber [disabled]
    · id=my-hmr                       @deepseek-ai/cordis-plugin-hmr             无 fiber [disabled]
    · id=e2222909                     @deepseek-ai/cordis-plugin-timer           state=2
    · id=44d2cba1                     @deepseek-ai/cordis-plugin-hmr             state=2

  进程还活着？ True
    plugin-timer：共 2 条，其中没被禁用的 1 条 → ['e2222909']
    plugin-hmr：共 2 条，其中没被禁用的 1 条 → ['44d2cba1']
  → 禁不掉。禁用只是让框架另造一份，服务照样在
```

## 归档的观测产物

- `census-nohmr.json` — 944 字节
- `census-noinfra.json` — 2,718 字节
