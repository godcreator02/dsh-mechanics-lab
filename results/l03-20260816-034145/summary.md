# l03 · 20260816-034145

跑于 2026-08-16 03:41:45（本地时间）

## 用例

### ✅ `test_dependency_chain_loads_in_service_order`  ·  3.14s

```
账本顺序：['lab-alpha', 'lab-beta']
  alpha 登记时账本为空；beta 登记时已有 alpha，间隔 7.327ms
```

### ✅ `test_missing_provider`  ·  12.11s

```
实例照常启动；lab-alpha **没有 apply**（见证文件不存在）
    → inject 拦住了它，但没有 pending 条目导致 boot 失败
```

### ✅ `test_missing_middle_breaks_only_second_level`  ·  12.12s

```
实例照常启动；lab-beta **没有 apply**
    账本：[]
```

### ✅ `test_entry_level_inject_vs_code_level`  ·  3.49s

```
条目级 inject: [] → 照常加载，说明它**没有削弱**代码里的声明
    账本：['lab-alpha']
```

### ✅ `test_write_order_does_not_decide_load_order`  ·  3.13s

```
条目倒着写（beta→alpha→registry），实际 apply 顺序仍是：['lab-alpha', 'lab-beta']
```

### ✅ `test_pending_dependent_seen_through_recorder`  ·  7.15s

```
lab-alpha 的全部事件：
    +   0.926ms  snapshot  fiberState=PENDING  hasFiber=True  disabled=False
    + 148.531ms  plugin  uid=None
    + 148.585ms    PENDING → UNLOADING
    + 152.101ms  UNLOADING → DISPOSED

  labRegistry 从未出现在服务列表里（共 45 个服务）
```

### ✅ `test_boot_outcome_for_unsatisfiable_inject[provider-disabled]`  ·  6.17s

```
[提供者被禁用] → **启动失败**（退出码 1）
    Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate
    lab-alpha: pending (waiting for service: labRegistry)
    [cause]: Error: dsh: 1 entry did not activate
    +   1.100ms  snapshot fiberState=PENDING
    + 158.540ms    PENDING → UNLOADING
    + 162.724ms  UNLOADING → DISPOSED
```

### ✅ `test_boot_outcome_for_unsatisfiable_inject[never-exists]`  ·  6.15s

```
[服务名从不存在] → **启动失败**（退出码 1）
    Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate
    lab-alpha: pending (waiting for services: labRegistry, 从来没有人提供过这个服务)
    [cause]: Error: dsh: 1 entry did not activate
    +   0.909ms  snapshot fiberState=PENDING
    + 157.237ms    PENDING → UNLOADING
    + 160.644ms  UNLOADING → DISPOSED
```

## 归档的观测产物

- `events-dis.jsonl` — 125,979 字节
- `events-never.jsonl` — 125,667 字节
- `events.jsonl` — 125,932 字节
- `events-dis.relations.json` — 8,617 字节
- `events-never.relations.json` — 8,617 字节
- `events.relations.json` — 8,617 字节
- `ledger-inject.json` — 214 字节
- `ledger-nomid.json` — 94 字节
- `ledger-reverse.json` — 345 字节
- `ledger.json` — 361 字节
- `w-alpha.json` — 257 字节
- `w-beta-reverse.json` — 402 字节
- `w-beta.json` — 410 字节
