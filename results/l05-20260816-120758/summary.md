# l05 · 20260816-120758

跑于 2026-08-16 12:07:58（本地时间）

## 用例

### ✅ `test_insert_without_id_appends_to_root`  ·  0.48s

```
组合树 id 列表：['alpha', 'beta']
  stderr：（空）
```

### ✅ `test_insert_with_id_targeting_non_group_warns_and_skips`  ·  0.35s

```
组合树 id 列表：['leaf']
  stderr：dsh: [D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l05\profiles\l05-insert-nongroup\cordis.patch.yml] patch insert: entry "leaf" is not a group
```

### ✅ `test_null_sets_key_to_null_not_delete`  ·  0.35s

```
solo 条目：{'id': 'solo', 'name': 'dummy-solo', 'disabled': None}
  stderr：（空）
```

### ✅ `test_later_patch_can_target_earlier_insert`  ·  0.39s

```
kid 的 config：{'n': 2}
  stderr：（空）
```

### ✅ `test_missing_id_warns_and_skips_rest_still_applies`  ·  0.34s

```
alpha 的 config：{'x': 99}
  no-such-id 存在吗：False
  stderr：dsh: [D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l05\profiles\l05-missing-id\cordis.patch.yml] patch: entry "no-such-id" not found
```

### ✅ `test_arbitrary_fields_pass_through_patch`  ·  0.36s

```
wild 条目：{'id': 'wild', 'name': 'dummy-wild', '随便字段': 'loader 不认识我', '另一个字段': 42}
  stderr：（空）
```

### ✅ `test_disabled_js_expression_is_evaluated[expr-false-loads]`  ·  1.94s

```
!!js false → 加载了：l05-patch-v1
```

### ✅ `test_disabled_js_expression_is_evaluated[expr-true-disabled]`  ·  13.34s

```
!!js true → 未加载（12s 内没写见证文件）
```

### ✅ `test_duplicate_id_at_boot_is_fatal`  ·  0.92s

```
静态 dump 里 id=dup 的条目数：2（预期 2——applyEntryPatches 不去重）
  dump 阶段 stderr：（空，不是这里报错）

  进程还活着？ False（退出码 1，死于 +0.5s）
  日志里的判词：['Error: dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include): duplicate loader entry id: dup', 'TypeError: duplicate loader entry id: dup', '  [cause]: Error: failed to apply loader entry include (cordis:include): duplicate loader entry id: dup', '    [cause]: TypeError: duplicate loader entry id: dup']
```

## 归档的观测产物

- `w-jsdisabled-t.json` — 233 字节
