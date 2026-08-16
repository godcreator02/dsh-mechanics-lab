# l00 · 20260816-032227

跑于 2026-08-16 03:22:27（本地时间）

## 用例

### ✅ `test_relative_name_resolution[\u6307\u5411\u76ee\u5f55-]`  ·  0.77s

```
指向目录
  profile 在 D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\reldir
  相对路径   ./../../../../experiments/l00_minimal_environment/fixtures/l00-census
  有没有 link？ False（预期 False）

  普查员被加载了吗？ False
  进程还活着？ False（退出码 1）
  → 指到**目录**加载失败，报 ERR_UNSUPPORTED_DIR_IMPORT：True
```

### ✅ `test_relative_name_resolution[\u6307\u5411\u6587\u4ef6-/index.js]`  ·  6.03s

```
指向文件
  profile 在 D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\relfile
  相对路径   ./../../../../experiments/l00_minimal_environment/fixtures/l00-census/index.js
  有没有 link？ False（预期 False）

  普查员被加载了吗？ True
  进程还活着？ True（退出码 None）
  → 相对路径指到**文件**可用，link 不是必需的
```

## 归档的观测产物

- `census-rel-file.json` — 2,002 字节
