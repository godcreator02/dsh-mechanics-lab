# 术语表

DSH 的词汇分属**三个层次**，混在一起讲是理解这套系统最大的障碍。每个词都标了出身：

| 标记 | 出身 |
|---|---|
| 🟦 | **Cordis** —— 底层的插件运行时框架（`@deepseek-ai/cordis`） |
| 🟩 | **Loader** —— 建立在 Cordis 之上的配置加载器（`cordis-plugin-loader`） |
| 🟨 | **DSH** —— DeepSeek Harness 自己的约定（`@deepseek-ai/dsh-*`） |
| ⬜ | **本实验台自造的词** —— 框架里没有，是我们为了讲清楚而起的名字 |

标了 ✅ 的性质是**本实验台实测过**的；没标的来自源码阅读。

---

## 一、Cordis 层：插件怎么活

### 🟦 Plugin（插件）

一个可被挂载的东西。形态可以是函数、带 `apply` 方法的对象、或类。
DSH 的写作契约用的是「模块导出 `apply` 函数」这一种：

```js
export function apply(ctx, config) { ... }
export const inject = ["webServer"]   // 可选
```

**注意**：Plugin 是**定义**，不是运行中的东西。同一个 Plugin 可以被挂载多次。

### 🟦 Fiber（纤程）

**一个插件的一次运行实例。** 这是理解整套系统的枢纽概念。

三者的关系是逐级具体的：

```
Plugin（定义）  →  Runtime（被注册后的运行时）  →  Fiber（每一次挂载的实例）
   一份代码            一个插件一个                  挂几次就有几个
```

✅ 实测佐证：把同一个包 `lab-minimal` 用两个不同 id（`alpha`、`beta`）挂进同一棵树，
它们**各有独立的 fiber**——改 `alpha` 的配置时 `beta` 全程静默，两者的状态转换互不相干。

一个 Fiber 携带：`state`（生命周期状态）、`uid`（注册表内唯一 id，root 是 0，
销毁后变 `null`）、`runtime`、`entry`（如果它对应一个 loader 条目）、
以及这次挂载注册的所有 effect。

### 🟦 FiberState（生命周期状态）

**一共六个**，定义在 `@deepseek-ai/cordis` 的 `lib/types/fiber.d.ts`：

| 值 | 名字 | 含义 |
|---|---|---|
| 0 | `PENDING` | 等 `inject` 声明的服务就位 |
| 1 | `LOADING` | 插件回调正在执行（`apply` 运行中） |
| 2 | `ACTIVE` | 加载完成，正在提供服务 |
| 3 | `FAILED` | 回调或配置校验抛了错 |
| 4 | `DISPOSED` | 已移除，不会再启动 |
| 5 | `UNLOADING` | disposer 正在跑 |

⚠️ **实现坑**：它是 TypeScript 的 `const enum`，编译后被内联成数字字面量，
**运行时不存在这个对象**，`import` 不到——数字到名字的映射表得自己写一份。

✅ 实测到的典型转换链：

```
首次挂载    PENDING → LOADING → ACTIVE
改 config   ACTIVE → UNLOADING → LOADING → ACTIVE   ← fiber 对象保住，但副作用被清理重跑
禁用条目    ACTIVE → UNLOADING → DISPOSED
```

✅ 另外两条实测结论：
- **`PENDING` 在稳态实例里看不到**——boot 末尾有 `assertEntriesActivated` 逐条检查，
  只要有条目停在 pending 就整体 fail-loud，实例压根起不来
- **`LOADING` 窗口只有约 2 毫秒**——轮询无论多快都撞不到，只能靠事件捕捉

### 🟦 Context（上下文）

插件拿到的 `ctx`。它是访问一切的入口：`ctx.on()` 订阅事件、`ctx.effect()` 注册副作用、
`ctx.get("服务名")` 取服务、`ctx.fiber` 拿到自己的 fiber。

Context 是**有层级**的——插件的 ctx 由父级派生，服务查找会沿链向上。

### 🟦 Service（服务）

插件之间互相提供能力的方式。一个插件 `provide` 某个服务，别的插件通过
`inject` 声明依赖、或用 `ctx.get()` 运行时取。

DSH 里常见的服务：`webServer`（注册 HTTP 路由）、`loader`（读组合树）、
`slots`（client 侧插槽注册表）、`hmr`、`tools`、`skills`。

### 🟦 inject（依赖声明）

声明「我需要哪些服务才能跑」。两种写法：

```js
export const inject = ["webServer"]        // 插件代码里（主流）
```
```yaml
- id: webserver                            # 条目上（少数派）
  inject: [webStartup]
```

✅ 实测：一棵只叠 `dsh-base` 的树有 79 个条目，**条目级 `inject` 一次都没出现**——
服务依赖主要声明在插件代码里。

⚠️ **有 await 语义的服务要当心。** `loader` 的 intercept 契约里写着
*"Keep dependent plugins pending while loader entries are still loading"*——
声明依赖 `loader` 的插件会被挂在 `PENDING` 等所有条目加载完。
而插件自己也是 loader 的条目之一，于是等成死结。
✅ 实测症状：路由永远 404，**日志里一个字都没有**（`PENDING` 不是错误，无人报警）。
解法是 `ctx.get("loader")` 运行时取。

### 🟦 effect（副作用）与 disposer（清理器）

`ctx.effect(body, label)` 注册一个副作用，返回值是它的清理函数。
fiber 卸载时，所有 disposer **按注册的逆序**执行。

DSH 写作契约里最重要的一条：**HTTP 路由必须用 `ctx.effect` 包住**，
否则插件卸载后路由泄漏、继续应答。

⚠️ 关键性质：**`UNLOADING` 阶段会清理该 fiber 上所有 effect**。
所以「fiber 对象没被销毁」不等于「它注册的东西还在」——改 `config` 就是这种情况。

---

## 二、Loader 层：配方怎么组合

### 🟩 Entry（条目）

组合树里的**一行**，是「配方」的最小单位。它是**静态描述**，不是运行中的东西——
运行中的那个是它的 fiber。

### 🟩 EntryOptions（条目的字段）

**一共六个**，定义在 `cordis-plugin-loader` 的 `config/entry.ts`：

| 字段 | 管什么 |
|---|---|
| `id` | **树内地址**。patch 靠它定位条目 |
| `name` | **模块说明符**。loader 拿它去 Node 那儿 resolve |
| `config` | 传给 `apply(ctx, config)` 的第二个参数 |
| `disabled` | 挂不挂。可以是布尔，也可以是 `!!js` 表达式 |
| `group` | 标记这是个嵌套条目组 |
| `inject` | 该条目需要的服务（覆盖/补充插件代码里的声明） |

✅ 实测：79 个条目的真实组合树里只用到四个（`id`/`name`/`config`/`disabled`），
`group` 和 `inject` 一次没出现。

⚠️ **不认识的字段会被带着走但没人读**——`applyEntryPatches` 是 `target[key] = value`，
不筛。所以 `disable: true`（少个 d）不报错、条目照常运行，是个静默失败面。

### 🟩 patch（补丁）

**对条目列表的一次编辑指令。** 整棵组合树 100% 由 patch 叠出来——根永远是空数组。

三种语义：

| 形态 | 做什么 | 失败时 |
|---|---|---|
| `- insert: [...]`（无 id） | 条目追加到根列表末尾。**新增插件的唯一姿势** | — |
| `- insert: [...]`（有 id） | 追加进该 id 指向的 **group** 里 | 目标不是 group → 警告跳过 |
| `- id: X` + 若干字段 | 定位已有条目改它 | 找不到 id → **只警告，静默跳过** |

⚠️ ✅ **`config` 是按字段整体替换，不是按键 merge。** 源码是 `target[key] = value`：
patch 里出现的每个顶层字段被整体换掉，没出现的字段不受影响。
所以只写 `disabled` 不会清空 `config`，但只要写了 `config`，里面没重述的键就消失。

### 🟩 `!!js` 表达式

patch 方言：值不在解析时求值，而是延迟到条目激活时、在该条目自己的上下文里算。

```yaml
disabled: !!js process.platform === 'win32'
port: !!js ctx.webStartup.port ?? 3080
```

✅ 实测：静态 `--dump-config` 里保留的是**表达式原文**，不是求值结果。
⚠️ PyYAML 之类的解析器遇到这个未注册标签会直接抛错，得显式注册。

### 🟩 group（条目组）

标记 `group: true` 的条目是个**容器**，它的 `config` 就是子条目数组。
带 id 的 `insert` 就是往某个 group 里塞孩子。

源码性质：**group 永远是「启用」的**（`if (options.group) return false`），
但它的孩子会因为父级 `disabled` 而停——禁用会沿父链**向下传播**。

⚠️ 官方 DSH 部署里**一个 group 条目都没有**（两个 bundle 的 patch 文件里 `group` 一次没出现）。
本实验台未实测。

### 🟩 EntryTree / EntryGroup / Loader

- **EntryTree** —— 一棵可变的条目树，`entries()` 遍历自己和嵌套子树
- **EntryGroup** —— 一组子条目的运行时归属者，`update()` 是**事务性**的：
  所有条目**并发创建**（`Promise.allSettled`），任一失败整体回滚
- **Loader** —— 拥有条目树、负责 import 插件模块的服务，是 EntryTree 的子类

⚠️ 「并发创建」直接推出一条反直觉结论：**条目在 YAML 里的书写顺序不决定加载顺序**，
加载由**服务可用性**驱动。`dsh-base` 的 patch 文件里有原话：
*"Row order carries no load semantics (activation is service-availability driven)"*。

### 🟩 root include（`cordis:include`）

**整棵配方树的根。** 由 `mountRootInclude()` 在 boot 期创建，id 固定是 `include`。

它不只是「一个条目」——**整个配方装在它的 `config` 里**：

```js
config: {
  path: …/cordis.yml,      // 空根 []
  patches: [...patches]    // bundle 层 + 活层 + home 层 + overlays 全在这
}
```

✅ 由此推出一条实现事实：**「配方热重放」就是「改 include 这一个条目的 config」**
（`watchUserPatches` 的回调重新 compose 出 patches，然后 `entry.update({config})`）。

✅ **层级要紧**（L0 实测）：配方里的条目住在 **include 的子树**里，
而兜底补的 `timer`/`hmr` 在**根组、与 include 平级**：

```
根组
├─ include                  ← 树根
│   └─ 配方里的条目…         ⊂include
├─ timer  ← 兜底，平级
└─ hmr    ← 兜底，平级
```

配方重放重新 compose 的只有 include 的子树，**碰不到平级的那些**。
所以同样叫 hmr，兜底的那个和写在配方里的那个处境完全不同——
后者每次重放都可能被重挂、watcher 随 effect 一起清掉。

### 🟩 name 的三条解析路径

条目的 `name` 怎么变成一个真的模块？`EntryTree.import` 分三条路，**互不相通**：

| 写法 | 走哪条 | 锚点 |
|---|---|---|
| `cordis:xxx` | 内置表 `loader.builtins` | 不解析文件 |
| `./xxx` `../xxx` | **URL 解析** | `ctx.baseUrl` = **profile 目录** |
| 其它（裸包名） | **包解析** | dsh **安装目录**（`bareModuleBaseUrl`） |

三条路的实际后果（L0 实测）：

- **内置表只有两个**：`cordis:include` 和 `cordis:group`，由 `mountRootInclude()`
  塞进去。出厂是空对象，没有第三个
- **官方包不需要 link 进 profile** 就能用裸包名引用（L0 实测：没 link 的
  `@deepseek-ai/cordis-plugin-timer` 照样 `state=2` 激活）
- **相对路径必须指到文件**。指到目录报 `ERR_UNSUPPORTED_DIR_IMPORT`——
  因为**只有包解析认 `package.json`**，L1 验过的那条回退链
  （`exports["."]` → `main` → `index.js`）对相对路径不存在

「官方包不用 link」靠的是**标准 Node parent-walk + 一层共享 `node_modules`**，
没有任何特殊锚点：

```
$DSH_HOME/profiles/
├── node_modules/          ← 符号链接农场（实测 252 条）
│   └── @deepseek-ai/
│       ├── cordis-plugin-timer  → <npx 缓存>/…/cordis-plugin-timer   [junction]
│       └── …
└── <profile 名>/          ← ctx.baseUrl 锚在这里
    └── node_modules/      ← 我们 link 自己 fixture 的地方
```

profile 目录向上遍历**一层**就撞见那份共享 `node_modules`，所以内置包不必 link 进
每个 profile。农场由 `healScaffoldModuleFallback`（`dsh-app-boot`）每次
`prepareProfile` 时幂等维护：对 dsh 自身依赖做 BFS，每个包建一条指向真实安装位置的
junction，安装位置变了会重新指。

⚠️ **我们自己的 fixture 不在农场里，所以仍然必须 link。**

⚠️ `dsh-app-boot` 里另有一个 `HostResolvedRootInclude` 子类，看上去是给裸包名
用的专门解析路径（`bareModuleBaseUrl`）——**它不会被激活**：那是 `boot()` 的第 5 个
参数，而唯一调用点只传 4 个。读那段代码时别把它当成实际生效的机制。

### 🟩 assertEntriesActivated（boot 末尾的审计）

`dsh-app-boot` 在 `boot()` 返回前跑的最后一道检查：遍历每个**未 disabled** 的条目，
只要有一个不是 `ACTIVE` 就抛错，整个启动失败（退出码 1）。

PENDING 的那条还会把缺的服务名列出来：

```
dsh: 1 entry did not activate
l00-needy: pending (waiting for service: definitelyNotAService)
```

⚠️ **只在 boot 期审计这一次。** boot 之后靠热重放新加的条目卡在 PENDING，
不会杀进程——那是完全另一条路径。「PENDING 致不致命」这个问题必须**先问什么时候**。

---

## 三、DSH 层：一套部署长什么样

### 🟨 home

`~/.dsh`（或 `$DSH_HOME`）。一套部署的数据面 + profile 的家：

```
~/.dsh/
  profiles/         各个 profile
  sessions/         会话
  storages/         各类存储（工作区注册表等）
  .credentials.yaml
  settings.yaml
  cordis.patch.yml  ← home 级 patch 层，见下
```

### 🟨 profile

**一个真正的 npm 包，同时是一套组合配方。** 有 `package.json`、有 `dependencies`、
有 `node_modules`，`pnpm install` 在它目录里跑。

```
~/.dsh/profiles/web/
  package.json        dsh.profile.bundles 名单 + link: 依赖
  cordis.yml          内容永远是 []
  cordis.patch.yml    活层
  node_modules/       插件从这里被 resolve
```

所以「profile 隔离」的本质是**依赖解析视野的隔离**——它是 Node 世界的 venv，
这个类比是字面意义上准确的。

⚠️ ✅ **`cordis.yml` 永远是空数组，而且每次启动都被无条件重写。**
源码注释说明了原因：loader 有 tree write-back（插件自我 dispose 会把当前树持久化回去），
不重写的话下次启动 bundle 的 insert 会翻倍。

### 🟨 bundle ⚠️ **这个词指两样完全不同的东西**

这是整套术语里最大的陷阱，而且两者恰好落在热/冷光谱的两极：

| | **profile bundle** | **client bundle** |
|---|---|---|
| 是什么 | 一个 **npm 包**，`package.json` 里声明 `dsh.bundle.patch`，内容实质是**一叠 patch 指令** | 一个**浏览器端 JS 文件**，`exports["./client"]` 指向它 |
| 住哪 | profile 的 `dsh.profile.bundles` 名单 | 插件包里，经 `/plugins/<id>/client.js` 出街 |
| 谁读它 | `composeProfile()`，整个进程**只读一次** | `serveBundle()`，**每次 HTTP 请求都现读磁盘** |
| 改了会怎样 | ✅ **冷**——必须重启 | ✅ **热**——约 3 秒换掉 |
| 例子 | `@deepseek-ai/dsh-base`、`dsh-web-app` | 任何带 UI 的插件的 `lib/client.js` |

**记住**：profile bundle 不是「一个插件」，是「**一叠 patch**」。
✅ 只叠 `dsh-base` 一个 bundle，组合树就有 79 个条目。

### 🟨 活层（user patch layer）

profile 自己的 `cordis.patch.yml`——你日常动的那一层。**被 watcher 监听，改动秒级热重放。**

### 🟨 五层 patch 叠加

组合树从空数组开始，按序叠五层，后叠的赢：

| # | 层 | 文件 | 热/冷 |
|---|---|---|---|
| 1 | bundle 层 | 每个 bundle 包自带的 `cordis.patch.yml`，按 `dsh.profile.bundles` 顺序 | ✅ 冷 |
| 2 | profile 活层 | `profiles/<名>/cordis.patch.yml` | ✅ 热 |
| 3 | **home 级层** | `$DSH_HOME/cordis.patch.yml` | ✅ 热 |
| 4 | overlay | `--patch <路径>`，按 argv 顺序 | 冷 |
| 5 | 内置 overlay | agent-presets 根、telemetry 开关 | 冷 |

⚠️ ✅ **第 3 层很多文档都漏了**，但它真实存在，**优先级压过 profile 自己的活层**，
且对同一个 home 下**所有 profile 同时生效**。共享 home 的部署里，
往那个文件写一笔会打进所有实例。

### 🟩 hmr ⚠️ **这个词也指两样东西**

**全称 Hot Module Replacement，中文「模块热替换」。** 这不是外部译法，
是官方在包里自报的——`@deepseek-ai/cordis-plugin-hmr` 的 `package.json` 里：

```json
"@deepseek-ai/cordis": {
  "services": { "required": ["timer"] },
  "description": { "en": "Hot Module Replacement", "zh": "模块热替换" }
}
```

顺带看到 **hmr 硬依赖 `timer`**，而且是**包级**声明的（不是条目级 `inject`）。
这解释了 L0 观测到的兜底顺序：框架补 hmr 之前先补 timer，
否则 hmr 会卡在 PENDING 等一个永远不来的服务。

跟 `bundle` 一样，`hmr` 在这套系统里有两个互不相干的实现：

| | **host 侧 hmr** | **client 侧 hmr** |
|---|---|---|
| 包 | 🟩 `@deepseek-ai/cordis-plugin-hmr` | 🟨 `@deepseek-ai/dsh-client-hmr` |
| 管什么 | Node 进程里的配方与模块 | 浏览器里的 client bundle |
| 机制 | chokidar 文件监听 | **500ms `statSync` 轮询** + SSE 推送 |
| 生效 | 约 1–2 秒 | 约 3 秒，不用 F5 |

（client 侧用轮询不用 inotify 是有意的，源码注释：网络挂载不发 inotify 事件。）

下面讲的都是 **host 侧**那个。它是 cordis 生态的插件，不是 DSH 自己的东西——
跟 `cordis-plugin-loader`、`cordis-plugin-include` 同族。

#### 它有两个 watcher，别混

| | **主 watcher** | **`registerConfig` 的 watcher** |
|---|---|---|
| 监视什么 | `root` 配置的那些目录（递归） | **精确到单个文件**（每个 patch 文件一个） |
| 谁建的 | hmr 的 `Service.init` | `watchUserPatches()` 在 boot 时调 `hmr.registerConfig()` |
| 干什么 | 走下面那四条分支 | 触发**配方热重放** |

#### 主 watcher 的四条分支

文件一变，主 watcher 按顺序判断：

| # | 条件 | 动作 |
|---|---|---|
| 1 | 是某个 include 的 config 文件 | 刷新那棵子树 |
| 2 | 在 **`externals`** 里（CLI 入口的依赖树，即框架自己的代码） | **`loader.exit()`——整个进程退出** |
| 3 | 在 Node 的 **ESM `loadCache`** 里（被 import 过的模块） | **代码热重载**：清 ESM+CJS 缓存 → 重 import → dispose 旧 fiber → 原位重挂，失败双向回滚 |
| 4 | 以上都不是 | 只 `emit('hmr/change', url)`——**没人接** |

⚠️ ✅ **第 4 条分支是「非 import 文件是冷的」的实现根因。** 插件在 `apply` 里
`readFileSync` 读的文件从没进过 `loadCache`，所以改了它只走到第 4 条：
HMR 看得见，但归类为「不关我事」。

✅ **实测佐证**：改 `cordis.patch.yml` 时，观测到两条 `hmr/change` 事件，
而且**发生在配方重放之后**——重放是 `registerConfig` 的那个 watcher 干的；
主 watcher 因为 `root: ['.']` 覆盖了 profile 目录也看见了同一个文件，
但一路走到第 4 条分支，发了个没人接的事件。

所以 **`hmr/change` 的语义是「我看到了但没处理」**，不是「检测到变化」。

#### 关键配置

| 键 | 默认 | 说明 |
|---|---|---|
| `root` | `['.']` | watch root 数组，相对 `base` 解析 |
| `base` | ctx.baseUrl | 相对路径的基准 |
| `debounce` | 100ms | 合并突发变更。消费 stable 线时会调到 1000ms |
| `ignored` | 含 `**/node_modules` | 见下 |

⚠️ ✅ **watch root 必须指向真实源码目录**——`ignored` 默认含 `**/node_modules`，
而且**依赖遍历也跳过 node_modules**，所以把 root 指向 `node_modules` 里那个
junction 是完全无效的（实测：改真实源码文件毫无反应）。

#### 三个相关事件

| 事件 | 什么时候发 |
|---|---|
| `hmr/change` | 第 4 条分支——看到了但没处理 |
| `hmr/reload` | **代码**热重载完成，带这次重载了哪些插件 |
| `hmr/config-update-failed` | 配方重放失败 |

✅ 实测：改 patch 文件时只有 `hmr/change`，**一条 `hmr/reload` 都没有**——
因为那走的是配方热重放，不是代码热重载。**两条链路的区分可以直接观测到。**

#### ⚠️ 一条待验的要害

`registerConfig` 建立的 watcher，其清理**挂在 hmr 自己 fiber 的 `ctx.effect` 上**；
而 `watchUserPatches()` **只在 boot 时调用一次**，之后无人重新注册。

✅ 又实测到：改一个条目的 `config` 会让它的 fiber 走 `UNLOADING → LOADING`，
**effect 被清理并重跑**。

两条接起来 → **改动 hmr 条目的 `config`，很可能把 patch 监听自己清掉且不恢复**。
这正是 L13 要测实或证伪的核心问题。

### 🟨 dsh.client / client-modules

包的 `package.json` 里 `"dsh": {"client": {...}}` 声明它有浏览器半边。
`dsh-client-modules` 扫这些声明，组装 `window.__DSH_BOOT__` 并服务 `client.js`。

⚠️ ✅ **包元数据按包名缓存且永不过期**，包括「这不是 client 包」的**否定结论**。
所以：全新包名首次挂载**不用重启**就能进图；但曾以「无声明」形态挂载过的包，
后补声明**必须重启**。

---

## 四、本实验台自造的词

### ⬜ 见证文件（witness）

教学插件在 `apply` 里写的一个 JSON 文件，内容是三个指纹：
`marker`（代码版本）、`moduleLoadedAt`（模块被 import 的时刻）、
`appliedAt`（apply 执行的时刻）。

**为什么不用日志**：日志会被吞、被缓冲、被格式变化骗过去；文件存在与否是硬事实。
✅ 「插件被加载了」的可操作定义就是「`apply` 被执行了」。

### ⬜ 见证流 / 事件流（A 流与 B 流）

观测台的两条流，来源完全不同，**别混**：

| | **A · 见证流** | **B · 框架事件流** |
|---|---|---|
| 谁产生的 | **我们自己的教学插件**，在 `apply` 里主动写 | **框架自己**发的 Cordis 事件，采集器订阅后转记 |
| 内容 | 见证文件里那几个指纹（marker / 两个时刻 / config 回显） | `internal/status`、`internal/plugin`、`loader/partial-dispose`… |
| 回答什么 | 「**我的**插件被加载了吗、拿到什么 config」 | 「**这棵树**上发生了什么、什么时候」 |
| 缺点 | 只看得见自己 | 看得见全部，但要自己分辨哪条与被测对象有关 |

一句话：**见证流是「我说我在」，事件流是「框架说谁在」。** 两条互为佐证——
见证文件写出来了但事件流里没有对应的状态迁移，那说明观测本身有问题。

### ⬜ 幽灵条目（ghost entry）

**在运行时的树里、却不在任何 patch 文件里的条目。** L0 立的词。

`--dump-config` 算的是「配方」，进程里跑的是「树」，两者差三个：

| 条目 | 谁造的 | id |
|---|---|---|
| `cordis:include` | `mountRootInclude()`，**整棵树的根** | 固定 `include` |
| `timer` | profile-boot 兜底 | **随机生成** |
| `hmr` | profile-boot 兜底，`root: []` | **随机生成** |

⚠️ 后两个的 id 每次启动都不一样，**只能认 `name` 不能认 id**。

⚠️ **关不掉。** 那段兜底在 `boot()` 返回后无条件执行，没有开关；
把 `timer`/`hmr` 写进活层再 `disabled: true` 只会让框架**另造一份**
（判据是服务不是条目）。所以 **DSH 实例不存在「没有 hmr」的形态**——
「patch 监听死了」只可能是「hmr 还在但 watcher 被清了」，
不可能是「hmr 不在」。

### ⬜ 普查员（census）

L0 的核心观测工具（`l00-census`）：拿 `ctx.get("loader")` 遍历 `loader.entries()`，
把运行时那棵树整个序列化下来。**拍两张快照**——`apply` 当下（boot 期）和延后两秒
（settle），因为幽灵条目是 `boot()` 返回之后才补的，只拍一张永远看不见。

跟见证文件的区别：见证文件说「我在」，普查员说「**树上都有谁**」。

### ⬜ 教具 / fixture / 采集器

- **fixture** —— 某一课专用的教学插件，住在该课目录下，**允许跨课重复**
  （一个目录就是完整的一课，改一课弄不坏另一课）
- **教具** —— 跨课通用的演示件，住 `demo/`
- **采集器**（`lab-recorder`）—— 观测台注入进被观测进程的那一半

### ⬜ snapshot ⚠️ **这个词在本项目里也指两样东西**

两个含义方向相反：一个是**我们的观测动作**，一个是**被观测的机制**。

#### ① 起点快照（`snapshot` 事件）—— 观测动作

采集器挂载的那一刻，**遍历整棵树、把每个条目此刻的状态记一遍**，
产出一批 `kind: "snapshot"` 的事件。

**为什么需要它**：采集器自己也是树上的一个条目，在它 `apply` 之前挂载的条目，
其 `fiber created` 和 `PENDING → LOADING` 已经发生完了。
✅ 实测（补快照之前）：78 个条目本该约 234 次状态转换，只录到 203 次；
`lab-minimal` 只赶上最后一跳 `LOADING → ACTIVE`。

**它记什么**：条目 id、name、此刻的 `FiberState`、有没有 fiber、是否 disabled、
config 摘要。

**跟 `status` 事件的区别**：

| | `snapshot` | `status` |
|---|---|---|
| 性质 | **补记**——「我来晚了，现在长这样」 | **实时**——「刚刚变了」 |
| 有无 `from` | 无（不知道之前是什么） | 有旧状态 |
| 时机 | 只在采集器挂载时一批 | 每次转换 |

**局限**：它补的是**起点**，补不了**过程**。丢掉的 `PENDING → LOADING` 永远丢了。
而且没法根治——加载顺序由**服务可用性**驱动，没法把采集器排到第一个。
时间线顶部那条「采集开始（本行之前的事件未被记录）」就是这个边界的标记。

#### ② 快照面 —— 被观测的机制

指**系统里那些"拍了照就不再更新"的缓存**。判断「改了这个要不要重启」，
本质就是问：**它撞在哪个快照面上，那个面有没有人负责刷新**。

| 快照面 | 什么时候拍的 | 谁负责刷新 |
|---|---|---|
| profile bundle 叠 | boot 时 `composeProfile()` 读一次 | ✅ **无人** → 必须重启 |
| Node 的 ESM / CJS 模块缓存 | 首次 `import()` | hmr（清缓存重 import） |
| `link:` 依赖指向哪个目录 | `pnpm install` 落 junction 时 | ✅ **无人** → 必须重启 |
| `pkgMeta` 负判缓存（「这不是 client 包」） | 该包名首次被 resolve 时 | ✅ **无人，源码注释直说 never expires** |
| 插件 `apply` 期 `readFileSync` 读进来的东西 | `apply` 执行那一刻 | ✅ 只有让 `apply` 重跑才行 |

⚠️ **两个含义别混**：「起点快照」是我们**主动拍**的一张照片；
「快照面」是系统**自己拍了不更新**的那些照片。前者是仪器，后者是被测对象。

### ⬜ 关系表 / 事件三分类

**关系表**（`events.relations.json`）—— 采集器对**高频、去重后才有价值**的信息做的
聚合输出：有哪些服务、谁监听什么事件、谁读什么服务。它**没有时序意义**，
所以不进时间线，单独一块展示。

**事件三分类** —— 采集器对订阅对象的分类，依据是**「是不是 waterfall」**，
不是「量大不大」：

| 类 | 怎么记 | 为什么 |
|---|---|---|
| **流水型** | 全量记进 `events.jsonl` | 低频、有时序意义 |
| **关系型** | 去重聚合进关系表 | 价值在关系不在次数（"谁监听 X" 有意义，"触发了 8000 次" 没有） |
| **链路型** | **默认不订** | waterfall 事件的监听器**必须调 `next()`**，订阅它等于插进执行链，不再是只读观测 |

---

## 五、最容易混的几对

| 这个 | 不是那个 | 差别 |
|---|---|---|
| **Plugin** | **Fiber** | 定义 vs 一次运行实例。同一个 Plugin 挂两次 = 两个 Fiber |
| **Entry** | **Fiber** | 配方里的一行（静态）vs 它的运行实例（动态）。禁用的条目**有 Entry 没有 Fiber** |
| **`id`** | **`name`** | 树内地址 vs Node 模块解析名。✅ 实测：id 起个完全不像包名的别名，插件照常加载 |
| **profile bundle** | **client bundle** | 一叠 patch（冷）vs 一个浏览器 JS 文件（热） |
| **bundle 层** | **活层** | 两条**独立**的注册路径。✅ 实测：把包从 bundles 名单摘掉重启后，活层里 insert 同一个包的条目照常存活 |
| **`DISABLED`** | **`PENDING`** | 人主动关的（连 fiber 都没有）vs 依赖没到位（fiber 建了在等）。排查方向完全相反 |
| **fiber 没被销毁** | **fiber 没动过** | ✅ 改 `config` 时 fiber 对象保住，但状态走了 `UNLOADING → LOADING`，**effect 被清理重跑** |
| **热重载** | **热重放** | 代码热重载（清模块缓存重 import）vs 配方热重放（重新 compose patch 叠）。✅ 实测可分辨：改 patch 文件只出 `hmr/change`，一条 `hmr/reload` 都没有 |
| **host 侧 hmr** | **client 侧 hmr** | `cordis-plugin-hmr`（chokidar 监听 Node 进程）vs `dsh-client-hmr`（500ms 轮询 + SSE 推浏览器） |
| **起点快照** | **快照面** | 我们**主动拍**的一张照片（仪器）vs 系统**自己拍了不更新**的那些缓存（被测对象） |
| **`hmr/change`** | 「检测到变化」 | ✅ 它其实是「**看到了但没处理**」——四条分支都不匹配时才发。真正处理了的反而不发这个事件 |
| **配方** | **树** | ✅ `--dump-config` 算出的 vs 进程里真跑着的。后者多三个**幽灵条目**（`cordis:include` + 兜底的 timer/hmr），静态 dump 永远看不见 |
| **裸包名** | **相对路径** | 两套解析算法。✅ 前者以 dsh 安装目录为锚且认 `package.json`；后者以 profile 为锚、走纯 URL 解析、**必须指到文件** |
| **hmr 条目在不在** | **hmr 服务在不在** | ✅ 兜底判的是**服务**。条目写了但 `disabled: true` → 服务不在 → 框架照样再补一个 |
| **兜底 hmr** | **自挂 hmr** | ✅ 兜底那个 `root: []`——够监听 patch 文件（精确路径注册，与 root 无关），但**不监听代码文件**。所以最小环境下热重放工作、热重载不工作 |
| **见证流** | **事件流** | 「我说我在」（自己的插件主动写）vs「框架说谁在」（订阅 Cordis 事件）。互为佐证 |
