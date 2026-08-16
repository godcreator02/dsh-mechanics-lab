# l06 · 20260816-122136

跑于 2026-08-16 12:21:36（本地时间）

## 用例

### ✅ `test_bundle_patch_and_bundles_list_are_cold`  ·  36.27s

```
初次响应：{'marker': 'l06-probe-bundle-v1', 'moduleLoadedAt': '2026-08-16T04:20:35.869Z', 'appliedAt': '2026-08-16T04:20:36.569Z', 'configRevision': 'r1'}
改完 patch 之后，静态 --dump-config 已经算出新值：'r2'
运行中实例的响应（bundle patch 已经改了）：{'marker': 'l06-probe-bundle-v1', 'moduleLoadedAt': '2026-08-16T04:20:35.869Z', 'appliedAt': '2026-08-16T04:20:36.569Z', 'configRevision': 'r1'}
重启后的响应：{'marker': 'l06-probe-bundle-v1', 'moduleLoadedAt': '2026-08-16T04:20:52.590Z', 'appliedAt': '2026-08-16T04:20:53.089Z', 'configRevision': 'r2'}
摘掉 bundles 名单后、运行中实例的响应：{'marker': 'l06-probe-bundle-v1', 'moduleLoadedAt': '2026-08-16T04:20:52.590Z', 'appliedAt': '2026-08-16T04:20:53.089Z', 'configRevision': 'r2'}
重启后（bundles 名单已经不含探针包）：None
```

### ✅ `test_two_registration_paths_are_independent`  ·  6.05s

```
活层 insert、包不在 bundles 名单里：{'marker': 'l06-probe-bundle-v1', 'moduleLoadedAt': '2026-08-16T04:21:13.681Z', 'appliedAt': '2026-08-16T04:21:14.192Z', 'configRevision': 'live-insert'}
重启后：{'marker': 'l06-probe-bundle-v1', 'moduleLoadedAt': '2026-08-16T04:21:17.151Z', 'appliedAt': '2026-08-16T04:21:17.630Z', 'configRevision': 'live-insert'}
```

### ✅ `test_duplicate_id_across_bundle_and_live_layer_kills_boot`  ·  15.05s

```
进程还活着？False
退出码：1
--- dupboot.err.log（末 40 行）---
file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:1186
		throw new Error(`${binName}: ${stage}: ${detail}${stack}`, { cause });
		      ^

Error: dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include): duplicate loader entry id: probe
TypeError: duplicate loader entry id: probe
    at EntryGroup.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:81:28)
    at Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:19)
    at file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:234:34
    at boot (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:1186:9)
    at async runProfile (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/profile-boot-DG5t9aNs.js:247:14)
    at async file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh/lib/bin.js:133:3 {
  [cause]: Error: failed to apply loader entry include (cordis:include): duplicate loader entry id: probe
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
    [cause]: TypeError: duplicate loader entry id: probe
        at EntryGroup.update (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis-plugin-loader/lib/index.js:81:28)
        at Include._apply (file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:238:19)
        at file:///C:/Users/godamericatb14/AppData/Local/npm-cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/dsh-app-boot/lib/index.js:234:34
  }
}

Node.js v24.14.1
--- dupboot.out.log（末 40 行）---
```
