# l02 · 20260816-033402

跑于 2026-08-16 03:34:02（本地时间）

## 用例

### ✅ `test_entry_field_vocabulary`  ·  0.53s

```
79 个条目里出现过的字段：['config', 'disabled', 'id', 'name']
  权威清单（EntryOptions）：['config', 'disabled', 'group', 'id', 'inject', 'name']
  本树未用到的：['group', 'inject']
```

### ✅ `test_unknown_field_is_carried_but_ignored`  ·  3.42s

```
野字段进了组合树，插件照常加载 —— 不认识的键不报错，只是没人读
```

### ✅ `test_disabled_keeps_entry_but_skips_apply`  ·  13.32s

```
条目在组合树里、disabled=True，apply 未执行 —— 禁用 ≠ 删除
```

### ✅ `test_disabled_accepts_js_expression[expr-true]`  ·  13.30s

```
[条件成立 → 禁用] 表达式 `process.platform === 'win32'` → 未加载（本机 win32）
```

### ✅ `test_disabled_accepts_js_expression[expr-false]`  ·  3.43s

```
[条件不成立 → 照常加载] 表达式 `process.platform === 'linux'` → 加载了（本机 win32）
```

### ✅ `test_config_is_arbitrary_json`  ·  3.09s

```
嵌套 config 原样送达：{"层一": {"层二": [1, 2, {"深处": "到底了"}]}}
```

## 归档的观测产物

- `w-expr-t.json` — 251 字节
- `w-json.json` — 513 字节
- `w-unknown.json` — 252 字节
