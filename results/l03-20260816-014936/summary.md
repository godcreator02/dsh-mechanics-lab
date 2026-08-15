# l03 · 20260816-014936

跑于 2026-08-16 01:49:36（本地时间）

## 用例

### ✅ `test_dependency_chain_loads_in_service_order`  ·  3.34s

```
账本顺序：['lab-alpha', 'lab-beta']
  alpha 登记时账本为空；beta 登记时已有 alpha，间隔 7.427ms
```

### ✅ `test_missing_provider`  ·  12.11s

```
实例照常启动；lab-alpha **没有 apply**（见证文件不存在）
    → inject 拦住了它，但没有 pending 条目导致 boot 失败
```

## 归档的观测产物

- `ledger.json` — 361 字节
- `w-alpha.json` — 257 字节
- `w-beta.json` — 410 字节
