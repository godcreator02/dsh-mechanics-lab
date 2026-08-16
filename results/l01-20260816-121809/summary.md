# l01 · 20260816-121809

跑于 2026-08-16 12:18:09（本地时间）

## 用例

### ✅ `test_entry_lands_in_composed_tree`  ·  0.58s

```
组合树共 79 个条目
  lab-minimal 的来源：D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l01\profiles\l01-static\cordis.patch.yml
  timer 的来源      ：@deepseek-ai/dsh-base
```

### ✅ `test_apply_actually_runs`  ·  11.27s

```
apply 执行于 2026-08-16T04:17:40.644Z，模块 import 于 2026-08-16T04:17:33.335Z
```

### ✅ `test_id_and_name_are_different_things`  ·  3.55s

```
id 与包名完全不同，插件照常加载 —— id 只是树内地址
```

### ✅ `test_config_reaches_apply`  ·  3.17s

```
apply 收到的 config：{'witness': 'D:/dshfiles/26081520anu/dsh-mechanics-lab/.testhome/l01/witness-config.json', '口令': '洛阳纸贵', '数字': 42, '开关': True}
```

### ✅ `test_resolution_is_the_real_boundary[exports]`  ·  3.09s

```
[exports 指向入口] → 加载了（符合预期）
```

### ✅ `test_resolution_is_the_real_boundary[index-fallback]`  ·  3.17s

```
[无 exports，入口恰好叫 index.js] → 加载了（符合预期）
```

### ✅ `test_resolution_is_the_real_boundary[no-entry-point]`  ·  12.05s

```
[无 exports，入口叫别的名字] → 没加载（符合预期）。实例还活着=False
```

### ✅ `test_resolution_is_the_real_boundary[main-fallback]`  ·  3.14s

```
[无 exports，但 main 指向入口] → 加载了（符合预期）
```

## 归档的观测产物

- `witness-alias.json` — 234 字节
- `witness-config.json` — 303 字节
- `witness-lab-min-index-yes-0.json` — 248 字节
- `witness-lab-min-index-yes-1.json` — 248 字节
- `witness-lab-min-plugin-yes-1.json` — 249 字节
- `witness-run.json` — 232 字节
