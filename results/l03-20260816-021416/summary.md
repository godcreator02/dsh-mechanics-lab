# l03 · 20260816-021416

跑于 2026-08-16 02:14:16（本地时间）

## 用例

### ✅ `test_dependency_chain_loads_in_service_order`  ·  3.78s

```
账本顺序：['lab-alpha', 'lab-beta']
  alpha 登记时账本为空；beta 登记时已有 alpha，间隔 8.240ms
```

### ✅ `test_missing_provider`  ·  12.11s

```
实例照常启动；lab-alpha **没有 apply**（见证文件不存在）
    → inject 拦住了它，但没有 pending 条目导致 boot 失败
```

### ✅ `test_missing_middle_breaks_only_second_level`  ·  12.11s

```
实例照常启动；lab-beta **没有 apply**
    账本：[]
```

### ✅ `test_entry_level_inject_vs_code_level`  ·  3.55s

```
条目级 inject: [] → 照常加载，说明它**没有削弱**代码里的声明
    账本：['lab-alpha']
```

### ✅ `test_write_order_does_not_decide_load_order`  ·  3.19s

```
条目倒着写（beta→alpha→registry），实际 apply 顺序仍是：['lab-alpha', 'lab-beta']
```

### ✅ `test_pending_dependent_seen_through_recorder`  ·  7.17s

```
lab-alpha 的全部事件：
    +   1.071ms  snapshot  fiberState=PENDING  hasFiber=True  disabled=False
    + 166.767ms  plugin  uid=None
    + 166.826ms    PENDING → UNLOADING
    + 170.923ms  UNLOADING → DISPOSED

  labRegistry 从未出现在服务列表里（共 45 个服务）
```

### ✅ `test_boot_outcome_for_unsatisfiable_inject[provider-disabled]`  ·  6.16s

```
[提供者被禁用] → **启动成功**
    +   1.045ms  snapshot fiberState=PENDING
    + 165.607ms    PENDING → UNLOADING
    + 168.943ms  UNLOADING → DISPOSED
```

### ✅ `test_boot_outcome_for_unsatisfiable_inject[never-exists]`  ·  6.16s

```
[服务名从不存在] → **启动成功**
    +   1.000ms  snapshot fiberState=PENDING
    + 163.207ms    PENDING → UNLOADING
    + 166.778ms  UNLOADING → DISPOSED
```

## 归档的观测产物

- `events-dis.jsonl` — 125,950 字节
- `events-never.jsonl` — 125,684 字节
- `events.jsonl` — 125,942 字节
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
