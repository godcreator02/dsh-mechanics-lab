# hmr 与 junction：一轮实验盘点

## 采集信息

| 项 | 值 |
|---|---|
| 对象 | `experiments/chx_hmr_across_junction/` 的 14 条用例 |
| 对应提交 | `b7af324`（本轮最后一次提交） |
| 跑法 | `uv run pytest experiments/chx_hmr_across_junction/ -n 0 -s` |
| 结果 | 14 passed in 162.04s |
| 判据 | 实测（事件流断言）为准；源码位置只写进「为什么」，不单独作判定依据 |
| 源码版本 | npx 缓存 `1e7f6d9597241db0` 下的 `@deepseek-ai/*`；官方文档快照钉 `47f9438` |

起因是一个具体问题：`dsh plugin add ./本地目录` 装进来的插件，改源码会不会热重载。

## 装置

一个教学包 `fixtures/hmr-linked/`：

- `index.js` —— 插件本体。报四样东西：代码里写死的「版本」、`config` 里的「配置版本」、
  身份三件套（模块 URL / `ctx.baseUrl` / `loadCache` 里相关的 key）、模块顶层计数器与
  `compute()` 的结果。另有可选心跳（`config.心跳毫秒`）。
- `helper.js` —— 纯算法文件，只有一个函数，不碰 `ctx`。
- `cordis.patch.yml` + `package.json` 的 `dsh.bundle` —— 只在包名进 `bundles` 名单时才生效。

`build()` 把三个变量拆开，一次只动一个：

| 参数 | 取值 |
|---|---|
| `placement` | `inline` / `linked` / `bundle` / `bundle-nested` / `junction-in` |
| `watch` | `none` / `profile` / `source` / `junction` |
| `ignored` | 不传（走默认）或显式名单 |

## 14 条用例

### 第一组：代码热不热（①—⑦⑨）

| | 源码在哪 | 条目从哪来 | hmr 盯着 | `ignored` | 结果 |
|---|---|---|---|---|---|
| ① | profile 里 | 活层 | profile 目录 | 默认 | 重载（对照组） |
| ② | profile 外 | 活层 | profile 目录 | 默认 | 没反应，watcher 一声没出 |
| ③ | profile 外 | 活层 | 源码真实路径 | 默认 | 没反应，watcher 还是一声没出 |
| ④ | profile 外 | 活层 | 那条 junction | 默认 | watcher 出声，没重载 |
| ⑤ | profile 外 | 活层 | 源码真实路径 | 去掉 `**/.*` | 重载 |
| ⑥ | profile 外 | 包自注册 | 源码真实路径 | 去掉 `**/.*` | 重载 |
| ⑦ | profile 里 | 包自注册 | profile 目录 | 默认 | 重载，hmr 一个字没改 |
| ⑨ | profile 外 | 包自注册 | profile 目录 + 一条 junction 指出去 | 默认 | watcher 出声，没重载 |

### 第二组：重载之后发生什么（⑧⑩⑪⑫⑬⑭）

| | 问什么 | 结果 |
|---|---|---|
| ⑧ | 同时改代码和包里 patch 的 `config` | 新代码配旧配方 |
| ⑩ | 一个包被两个条目挂着，改一次代码 | 一次 `hmr/reload`，两个 fiber 都重挂，各自沿用各自 `config` |
| ⑪ | 运行中往活层加一条同 `id` 的 | 整次更新回滚，原条目毫发无损，实例继续健康 |
| ⑫ | 改被 `import` 的 `helper.js` | 重来的是 `index.js`，插件入口是原子重载单位 |
| ⑬ | 重载后模块顶层的计数器 | 报 `[1, 1]` 不是 `[1, 2]`，状态清零 |
| ⑭ | hmr 关掉（`root: []`）改 `helper.js` | 之后 21 次 `compute()` 调用全是旧实现 |

## 判定

全部已实测。详细论证在各用例的 docstring，这里只列结论。

1. **经 junction 装进来的模块，URL 是链接那头的真实路径**，不含 `node_modules`。hmr 那三处
   `url.includes('/node_modules/')` 一处都不命中。
2. **挡住热重载的是 watcher 的 `ignored`，而且是被 `**/.*` 误伤的**：筛的是
   `relative(watchBaseDir, path)`，watch base 之外的路径以 `..` 开头，Windows 上这串反斜杠被
   picomatch 当成一整段，一段以点开头就成了「隐藏文件」。
3. **误伤只在源码位于 watch base 外面时发作。** 源码在里面，默认 `ignored` 原样能用。
4. **watcher 报出的路径从不做 realpath。** 手填 junction 路径（④）和让 chokidar 自己跟着爬进去
   （⑨），结果一样。
5. **条目从哪一层来不影响代码能不能热重载。** 两种形态的 `baseUrl` 都是 profile 目录。
6. **代码热重载不换 `config`。** 走 `registry.plugin(plugin, oldFiber._config, ...)`。
7. **bundle 层的配方冷，是「看见了没人管」不是「没人看见」。** 那份 patch 文件落在 watch 范围内时
   事件流里有 `hmr-change` 点名它，但它不是任何 include 的 filename、也不在 `loadCache` 里。
8. **重载的单位是插件不是条目。** 重挂循环遍历 `runtime.fibers`。
9. **配置路径的失败是事务性的而且被兜住。** `entry.update()` 整个 apply 失败，树一点不动。
10. **拆文件缩不小重载范围，模块顶层状态每次重载清零，函数调用不回头读磁盘。**

充要条件（①—⑨ 归结）：**watcher 报出的路径经 `pathToFileURL` 之后要跟 `loadCache` 的 key
字节相同。** `loadCache` 的 key 永远是 realpath，watcher 的路径从不 realpath —— 所以 watch
的入口必须本身就是真实路径。

## 这一轮修正过的判断

判据怎么被修正的，比最终清单更值得留。

**一 · 「三处 `isExcluded` 硬编码挡住了 link 形态」——错。**
最初读源码看到三处 `url.includes('/node_modules/')`，判断配置绕不过去。实测发现 realpath 让
link 装的包 URL 逃出了 node_modules，三处全不命中。真正挡住的只有 watcher 的 `ignored`，
而那是配置项。教训：**「代码里写着这个判断」不等于「这个判断会命中」**，得看实际喂进去的值。

**二 · 「Windows 上 `ignored` 整体失效」——猜对了有坑，猜错了位置。**
原猜测是反斜杠让 `**/node_modules` 匹配不上、导致 watcher 去爬整个 node_modules。实测反了：
顶层 `node_modules` 那次调用是单段无反斜杠，正常命中；出事的是 `**/.*` 误伤了 `..` 开头的
相对路径。单独用 picomatch 对照过：同一条路径换成正斜杠就不命中。

**三 · 「配置路径失败不回滚」——错。**
写进教材页之后被 ⑪ 推翻。hmr 确实不做补偿动作，但那是因为**不需要**：`entry.update()` 本身
是事务性的。代码路径才要 hmr 自己回滚，因为它绕过 entry 层直接操作 registry。

## 对既有课的影响

**第 10 项（`ch2_bundle_vs_live`）有一处论证站不住。**
`test_one_layer_is_hot_the_other_is_cold` 里的
`assert not of_kind(before, "hmr-change")` 配的解释是「包里那份 patch 文件连 hmr 都没当回事」。
但那条用例的 `root` 指向 `pkg.parent`，在 profile 目录外面，撞的是本轮 ③ 那个 `**/.*` 坑
——watcher 压根没看见那个目录。断言本身成立，解释不成立。

本轮 ⑧ 是那条论证该有的形态：patch 文件在 watch 范围内、watcher 报了它的变化、仍然没人认领。

第 10 项的主判定（改 bundle patch 不生效、重启才生效）不受影响，那是靠 `cold_runs == 1` 判的。

## 还没验证的

- **npm / tarball 安装形态**。代码物理住在 `node_modules` 里时模块 URL 真的含 `/node_modules/`，
  `loadDependencies` 第一行就返回空集 —— 推理如此，14 条测的全是 junction 形态。
- **`externals` 集合是否基本为空**。推理依据是 `loadDependencies` 跳过 node_modules 而 dsh CLI
  全装在那里面。14 条里没有一条触发过 `loader.exit()`，但那只能说明改的文件不在里面。
- **hmr 不等 `fiber.dispose()` 完成**。`registry.delete` 是同步方法、里面 `fiber.dispose()` 没有
  await，而 hmr 调 `registry.delete` 也没 await。⑤⑦⑬ 的时间线上能看见重叠（新实例 LOADING 比
  旧实例 DISPOSED 早约 0.2ms），但没有断言钉住。可以让插件在 dispose 里异步等 500ms，把这个
  从「差 0.2ms 可能是巧合」变成「差 500ms 不可能是巧合」。
- **Python SDK 场景**。SDK 是进程外调用方，通过 JSON-RPC 驱动内置 Node 运行时。Python 程序跑着
  不动、在外面改 JS 插件能不能热重载，没测；示例那个 `minimal.cordis.yml` 里有没有 hmr 也看不到
  （`examples/` 不在文档快照里）。

## 待归位

目录名 `chx_hmr_across_junction`，`chx` 表示章节与编号待定。归位时要做三件事：改目录名、
把判定写进 `docs/SYLLABUS.md`、教材页 `site/hmr-routes.html` 的面包屑改成正式编号。
