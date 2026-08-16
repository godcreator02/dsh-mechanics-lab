# l04 · 20260816-135742

跑于 2026-08-16 13:57:42（本地时间）

## 用例

### ✅ `test_four_layers_identifiable`  ·  0.53s

```
组合树共 6 个条目：['from-bundle', 'shared', 'order-test', 'from-profile', 'from-home', 'from-overlay']
  from-bundle    来源 = l04-bundle-a
  from-profile   来源 = D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l04\profiles\identify\cordis.patch.yml
  from-home      来源 = D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l04\cordis.patch.yml
  from-overlay   来源 = D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l04\overlay-identify.yml

  → 四层各自的来源与文档描述一致：包名 / profile 活层路径 / home 层路径 / overlay 路径
```

### ✅ `test_same_id_layers_precedence`  ·  1.48s

```
只有 bundle 层：shared.config = {'layer': 'bundle', 'seq': 1}
叠上 profile 层后：shared.config = {'layer': 'profile'}
再叠上 home 层后：shared.config = {'layer': 'home'}
最后叠上 overlay 层：shared.config = {'layer': 'overlay'}

  → 四层叠加顺序与文档一致：bundle → profile → home → overlay，一层比一层新
```

### ✅ `test_home_layer_missing_equals_no_layer`  ·  5.41s

```
home 层文件不存在时，dump-config 正常返回，3 个条目：['from-bundle', 'shared', 'order-test']
拉起后 5 秒，进程还活着？ True
```

### ✅ `test_home_layer_illegal_content_fails_loud`  ·  0.40s

```
报错信息：
dump-config 失败（profile=illegal-home, 退出码=1）：
--- stdout ---

--- stderr ---
file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:840
	if (!Array.isArray(parsed)) throw new Error(`${binName}: ${label} ${file} must be a top-level YAML array of loader patch entries`);
	                                  ^

Error: dsh: patches D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l04\cordis.patch.yml must be a top-level YAML array of loader patch entries
    at parsePatchList (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:840:36)
    at loadOptionalPatches (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:800:9)
    at runDumpConfig (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/dump-config-D-jtgwY3.js:35:23)
    at file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:148:3
    at process.processTicksAndRejections (node:internal/process/task_queues:104:5)

Node.js v24.14.1
```

### ✅ `test_overlay_order_by_argv`  ·  0.75s

```
--patch a b → order-test.config.which = 'b'
--patch b a → order-test.config.which = 'a'
  → 与文档一致：--patch 多个时按 argv 顺序，后者胜出
```

### ✅ `test_running_overlay_not_hot_reloaded`  ·  10.58s

```
启动后见证文件：[{'marker': 'l04-witness-v1', 'applyIndex': 0, 'at': '2026-08-16T05:57:31.747Z', 'value': 'initial'}]
已把 overlay 文件里的 value 改成 changed。固定等待 10 秒——这是「验证什么都不该发生」，不能用轮询提前退出，提前退出只能证明「此刻还没发生」
等待后见证文件：[{'marker': 'l04-witness-v1', 'applyIndex': 0, 'at': '2026-08-16T05:57:31.747Z', 'value': 'initial'}]
  → 与调研②一致：overlay 文件改了，运行中的实例没读到，得重启才能生效
```

## 归档的观测产物

- `witness-overlay-runtime.json` — 125 字节
