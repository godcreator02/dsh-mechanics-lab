# l03 · 20260816-033636

跑于 2026-08-16 03:36:36（本地时间）

## 用例

### ✅ `test_boot_outcome_for_unsatisfiable_inject[provider-disabled]`  ·  6.16s

```
[提供者被禁用] → **启动失败**（退出码 1）
    Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate
    lab-alpha: pending (waiting for service: labRegistry)
    [cause]: Error: dsh: 1 entry did not activate
    +   1.000ms  snapshot fiberState=PENDING
    + 155.043ms    PENDING → UNLOADING
    + 158.269ms  UNLOADING → DISPOSED
```

### ✅ `test_boot_outcome_for_unsatisfiable_inject[never-exists]`  ·  6.16s

```
[服务名从不存在] → **启动失败**（退出码 1）
    Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate
    lab-alpha: pending (waiting for services: labRegistry, 从来没有人提供过这个服务)
    [cause]: Error: dsh: 1 entry did not activate
    +   1.001ms  snapshot fiberState=PENDING
    + 156.610ms    PENDING → UNLOADING
    + 160.244ms  UNLOADING → DISPOSED
```

## 归档的观测产物

- `events-dis.jsonl` — 125,934 字节
- `events-never.jsonl` — 125,667 字节
- `events-dis.relations.json` — 8,617 字节
- `events-never.relations.json` — 8,617 字节
