# l03 · 20260816-120721

跑于 2026-08-16 12:07:21（本地时间）

## 用例

### ✅ `test_loader_internal_activated`  ·  0.66s

```
ctx.get('loader').internal 是否激活：True
  ctx.baseUrl：'file:///D:/dshfiles/26081520anu/dsh-mechanics-lab/.testhome/l03/profiles/internal/'
  → internal 分支激活：相对/绝对/裸包名全走同一条路，不做前缀判断
    本课后面每条用例的解释都要挂在这条分支上，不是「三条路径」
```

### ✅ `test_windows_absolute_path`  ·  10.02s

```
绝对路径：D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments\l03_name_resolution\fixtures\l03-probe\index.js
  加载成功？ False
  进程还活着？ False（退出码 1）
  → 加载失败：
--- abswin.err.log（末 40 行）---
    at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
    at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
  [cause]: Error: failed to apply loader entry include (cordis:include): failed to import loader entry probe (D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments\l03_name_resolution\fixtures\l03-probe\index.js): Only URLs with a scheme in: file, data, and node are supported by the default ESM loader. On Windows, absolute paths must be valid file:// URLs. Received protocol 'd:'
      at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
      at Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:519:10)
      at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
      at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
      at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
      at async Proxy.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:217:14)
      at async mountRootInclude (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:984:20)
      at async boot (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:1175:3)
      at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
      at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
    [cause]: Error: failed to import loader entry probe (D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments\l03_name_resolution\fixtures\l03-probe\index.js): Only URLs with a scheme in: file, data, and node are supported by the default ESM loader. On Windows, absolute paths must be valid file:// URLs. Received protocol 'd:'
        at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
        at Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:514:10)
        at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
        at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
        at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
        at async Promise.allSettled (index 0)
        at async EntryGroup.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:87:21)
        at async Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:3) {
      [cause]: Error [ERR_UNSUPPORTED_ESM_URL_SCHEME]: Only URLs with a scheme in: file, data, and node are supported by the default ESM loader. On Windows, absolute paths must be valid file:// URLs. Received protocol 'd:'
          at throwIfUnsupportedURLScheme (node:internal/modules/esm/load:195:11)
          at defaultLoadSync (node:internal/modules/esm/load:142:3)
          at #loadAndMaybeBlockOnLoaderThread (node:internal/modules/esm/loader:796:12)
          at #loadSync (node:internal/modules/esm/loader:816:49)
          at ModuleLoader.load (node:internal/modules/esm/loader:781:26)
          at ModuleLoader.loadAndTranslate (node:internal/modules/esm/loader:526:31)
          at #getOrCreateModuleJobAfterResolve (node:internal/modules/esm/loader:577:36)
          at afterResolve (node:internal/modules/esm/loader:625:52)
          at ModuleLoader.getOrCreateModuleJob (node:internal/modules/esm/loader:631:12)
          at onImport.tracePromise.__proto__ (node:internal/modules/esm/loader:650:32) {
        code: 'ERR_UNSUPPORTED_ESM_URL_SCHEME'
      }
    }
  }
}

Node.js v24.14.1
--- abswin.out.log（末 40 行）---
```

### ✅ `test_file_url`  ·  10.02s

```
file:// URL：file:///D:/dshfiles/26081520anu/dsh-mechanics-lab/experiments/l03_name_resolution/fixtures/l03-probe/index.js
  加载成功？ True
  进程还活着？ True（退出码 None）
  → file:// URL 可以直接被加载（internal=True）
```

### ✅ `test_cordis_unknown_builtin`  ·  8.03s

```
进程还活着？ False（退出码 1）
--- cordisbad.err.log（末 40 行）---
    at async Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:517:4)
    at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
    at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
    at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
    at async Promise.allSettled (index 0)
    at async EntryGroup.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:87:21)
    at async Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:3)
    at boot (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:1186:9)
    at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
    at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
  [cause]: Error: failed to apply loader entry include (cordis:include): failed to apply loader entry bad (cordis:nonexistent): invalid plugin, expect function or object with an "apply" method, received undefined
      at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
      ... 3 lines matching cause stack trace ...
      at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
      at async Proxy.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:217:14)
      at async mountRootInclude (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:984:20)
      at async boot (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:1175:3)
      at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
      at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
    [cause]: Error: failed to apply loader entry bad (cordis:nonexistent): invalid plugin, expect function or object with an "apply" method, received undefined
        at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
        at Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:519:10)
        at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
        ... 4 lines matching cause stack trace ...
        at async Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:3) {
      [cause]: Error: invalid plugin, expect function or object with an "apply" method, received undefined
          at Proxy.plugin (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis/lib/index.js:1620:24)
          at Entry._start (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:527:43)
          at async Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:517:4)
          at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
          at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
          at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
          at async Promise.allSettled (index 0)
          at async EntryGroup.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:87:21)
          at async Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:3)
    }
  }
}

Node.js v24.14.1
--- cordisbad.out.log（末 40 行）---
  → 报错文本吻合源码推导：'invalid plugin, expect function or object with an "apply" method'
```

### ✅ `test_nonexistent_bare_package`  ·  8.02s

```
进程还活着？ False（退出码 1）
--- nopkg.err.log（末 40 行）---
    at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
    at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
  [cause]: Error: failed to apply loader entry include (cordis:include): failed to import loader entry missing (l03-definitely-does-not-exist): Cannot find package 'l03-definitely-does-not-exist' imported from D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\nopkg\
      at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
      at Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:519:10)
      at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
      at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
      at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
      at async Proxy.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:217:14)
      at async mountRootInclude (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:984:20)
      at async boot (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:1175:3)
      at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
      at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
    [cause]: Error: failed to import loader entry missing (l03-definitely-does-not-exist): Cannot find package 'l03-definitely-does-not-exist' imported from D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\nopkg\
        at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
        at Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:514:10)
        at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
        at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
        at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
        at async Promise.allSettled (index 0)
        at async EntryGroup.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:87:21)
        at async Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:3) {
      [cause]: Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'l03-definitely-does-not-exist' imported from D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\nopkg\
          at Object.getPackageJSONURL (node:internal/modules/package_json_reader:301:9)
          at packageResolve (node:internal/modules/esm/resolve:768:81)
          at moduleResolve (node:internal/modules/esm/resolve:859:18)
          at defaultResolve (node:internal/modules/esm/resolve:991:11)
          at #cachedDefaultResolve (node:internal/modules/esm/loader:719:20)
          at #resolveAndMaybeBlockOnLoaderThread (node:internal/modules/esm/loader:736:38)
          at ModuleLoader.resolveSync (node:internal/modules/esm/loader:765:52)
          at #resolve (node:internal/modules/esm/loader:701:17)
          at ModuleLoader.getOrCreateModuleJob (node:internal/modules/esm/loader:621:35)
          at onImport.tracePromise.__proto__ (node:internal/modules/esm/loader:650:32) {
        code: 'ERR_MODULE_NOT_FOUND'
      }
    }
  }
}

Node.js v24.14.1
--- nopkg.out.log（末 40 行）---
  匹配到的 Node 标准报错关键字：['Cannot find package', 'ERR_MODULE_NOT_FOUND']
  → 报错文本与 cordis: 未知 builtin 那条不同（分类断言通过）
```

### ✅ `test_exports_subpath[declared]`  ·  0.66s

```
[l03-subpath-declared] name='l03-subpath-declared/tool' → 加载成功，marker=l03-subpath-declared-tool-v1
```

### ✅ `test_exports_subpath[undeclared]`  ·  10.06s

```
[l03-subpath-undeclared] name='l03-subpath-undeclared/tool' → 加载成功？ False
  进程还活着？ False
  报 ERR_PACKAGE_PATH_NOT_EXPORTED？ True
```

### ✅ `test_relative_path_has_no_fallback_chain`  ·  10.68s

```
相对路径：./../../../../experiments/l03_name_resolution/fixtures/l03-fallback/plugin.js
  相对路径直指非入口文件 → 加载成功，marker=l03-fallback-plugin-v1
  包名引用（同一份代码）→ 加载成功？ False
  进程还活着？ False
--- fallback-pkg.err.log（末 40 行）---
    at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
    at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
  [cause]: Error: failed to apply loader entry include (cordis:include): failed to import loader entry plugin (l03-fallback): Cannot find package 'D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\fallback-pkg\node_modules\l03-fallback\index.js' imported from D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\fallback-pkg\
      at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
      at Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:519:10)
      at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
      at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
      at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
      at async Proxy.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:217:14)
      at async mountRootInclude (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:984:20)
      at async boot (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:1175:3)
      at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
      at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
    [cause]: Error: failed to import loader entry plugin (l03-fallback): Cannot find package 'D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\fallback-pkg\node_modules\l03-fallback\index.js' imported from D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\fallback-pkg\
        at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
        at Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:514:10)
        at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
        at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
        at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
        at async Promise.allSettled (index 0)
        at async EntryGroup.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:87:21)
        at async Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:3) {
      [cause]: Error: Cannot find package 'D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\fallback-pkg\node_modules\l03-fallback\index.js' imported from D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l03\profiles\fallback-pkg\
          at legacyMainResolve (node:internal/modules/esm/resolve:205:26)
          at packageResolve (node:internal/modules/esm/resolve:778:12)
          at moduleResolve (node:internal/modules/esm/resolve:859:18)
          at defaultResolve (node:internal/modules/esm/resolve:991:11)
          at #cachedDefaultResolve (node:internal/modules/esm/loader:719:20)
          at #resolveAndMaybeBlockOnLoaderThread (node:internal/modules/esm/loader:736:38)
          at ModuleLoader.resolveSync (node:internal/modules/esm/loader:765:52)
          at #resolve (node:internal/modules/esm/loader:701:17)
          at ModuleLoader.getOrCreateModuleJob (node:internal/modules/esm/loader:621:35)
          at onImport.tracePromise.__proto__ (node:internal/modules/esm/loader:650:32) {
        code: 'ERR_MODULE_NOT_FOUND'
      }
    }
  }
}

Node.js v24.14.1
--- fallback-pkg.out.log（末 40 行）---
  → 同一份代码：相对路径能到，包名到不了。回退链只属于包解析，相对路径没有
```

## 归档的观测产物

- `witness-fallback-rel.json` — 83 字节
- `witness-fileurl.json` — 358 字节
- `witness-internal.json` — 360 字节
- `witness-subpath-declared.json` — 89 字节
