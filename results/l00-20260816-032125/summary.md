# l00 · 20260816-032125

跑于 2026-08-16 03:21:25（本地时间）

## 用例

### ✅ `test_relative_name_resolution`  ·  0.77s

```
profile 在 D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\rel
插件在   D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments\l00_minimal_environment\fixtures\l00-census
相对路径 ./../../../../experiments/l00_minimal_environment/fixtures/l00-census
有没有 link？ False（预期 False）

普查员被加载了吗？ False
进程还活着？ False（退出码 1）

--- rel.err.log（末 30 行）---
    [cause]: Error: failed to import loader entry census (./../../../../experiments/l00_minimal_environment/fixtures/l00-census): Directory import 'D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments\l00_minimal_environment\fixtures\l00-census' is not supported resolving ES modules imported from D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\rel\
    Did you mean to import "../../../../experiments/l00_minimal_environment/fixtures/l00-census/index.js"?
        at updateError (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:299:9)
        at Entry._init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:514:10)
        at async Entry.init (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:495:4)
        at async Entry.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:416:37)
        at async EntryGroup.create (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:55:4)
        at async Promise.allSettled (index 0)
        at async EntryGroup.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:87:21)
        at async Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:3) {
      [cause]: Error [ERR_UNSUPPORTED_DIR_IMPORT]: Directory import 'D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments\l00_minimal_environment\fixtures\l00-census' is not supported resolving ES modules imported from D:\dshfiles\26081520anu\dsh-mechanics-lab\.testhome\l00\profiles\rel\
      Did you mean to import "../../../../experiments/l00_minimal_environment/fixtures/l00-census/index.js"?
          at finalizeResolution (node:internal/modules/esm/resolve:263:11)
          at moduleResolve (node:internal/modules/esm/resolve:865:10)
          at defaultResolve (node:internal/modules/esm/resolve:991:11)
          at #cachedDefaultResolve (node:internal/modules/esm/loader:719:20)
          at #resolveAndMaybeBlockOnLoaderThread (node:internal/modules/esm/loader:736:38)
          at ModuleLoader.resolveSync (node:internal/modules/esm/loader:765:52)
          at #resolve (node:internal/modules/esm/loader:701:17)
          at ModuleLoader.getOrCreateModuleJob (node:internal/modules/esm/loader:621:35)
          at onImport.tracePromise.__proto__ (node:internal/modules/esm/loader:650:32)
          at TracingChannel.tracePromise (node:diagnostics_channel:350:14) {
        code: 'ERR_UNSUPPORTED_DIR_IMPORT',
        url: 'file:///D:/dshfiles/26081520anu/dsh-mechanics-lab/experiments/l00_minimal_environment/fixtures/l00-census'
      }
    }
  }
}

Node.js v24.14.1
--- rel.out.log（末 30 行）---
  → 相对路径不通，link 是必需的
```
