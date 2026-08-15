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

### 🟨 hmr

热重载。承担**两件不同的事**：

1. **配方热重放**——监听 patch 文件，重新 compose 整叠 → loader 做条目级事务 diff
2. **代码热重载**——监听 watch root 下的模块文件，清 ESM/CJS 缓存 → 重 import → 原位重挂

⚠️ ✅ 它的 `ignored` 默认含 `**/node_modules`，依赖遍历也跳过——
**watch root 必须指向真实源码目录，指向 `node_modules` 里的 junction 是无效的**。

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

### ⬜ 教具 / fixture / 采集器

- **fixture** —— 某一课专用的教学插件，住在该课目录下，**允许跨课重复**
  （一个目录就是完整的一课，改一课弄不坏另一课）
- **教具** —— 跨课通用的演示件，住 `demo/`
- **采集器**（`lab-recorder`）—— 观测台注入进被观测进程的那一半

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
| **热重载** | **热重放** | 代码热重载（清模块缓存重 import）vs 配方热重放（重新 compose patch 叠）。两条不同的链路 |
