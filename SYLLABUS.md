# 课程大纲

四级梯度，从简单到困难。**梯度是依赖顺序，不是排版顺序**——后一课要用到前一课立住的词和
观测手段，跳级会翻车（v1 的 E3 就是跳过 L10 直奔 L13 才废掉的）。

| 状态 | 含义 |
|---|---|
| ✅ | 做完，用例全过 |
| 🚧 | 正在做 |
| ⬜ | 未开始 |

---

## 第一级 · 一个插件

### ✅ L1 · 插件的最小形态

一个插件最少需要什么？怎么从外部证明它真被加载了？
8 个用例 / 约 32s / 不需要 web。

立住的词：条目、活层、bundle 层、加载、见证文件。
**实测推翻两个假设**：`exports["."]` 不是必需项（Node 有 `exports → main → index.js`
回退链）；活层条目也有来源注释（标 patch 文件绝对路径）。

### ✅ L2 · 条目的字段

条目能写哪些字段、各管什么。
6 个用例 / 约 38s / 不需要 web。

立住的词：禁用、`!!js` 表达式、野字段。
关键结论：条目只有六个字段；不认识的键**带着走但没人读**（写错字段名静默失败）；
`disabled` 是不挂载不是删除，且可写条件表达式。

---

## 第二级 · 插件之间

「小型依赖系统」住在这一级。四个教学插件贯穿 L3–L6：

| 插件 | 角色 | 依赖 |
|---|---|---|
| `lab-registry` | 提供服务 `labRegistry`：一本「谁来登记过」的账本 | — |
| `lab-alpha` | 往账本里登记自己 | `labRegistry` |
| `lab-beta` | 二级依赖，验证依赖链传递 | `labRegistry`, `labAlpha` |
| `lab-probe` | 把账本经 HTTP 暴露出来，当**观测面** | `webServer`, `labRegistry` |

**观测面独立成一个插件**是有意的：把「被观察的对象」和「观察的手段」分开，
免得观测手段自己成为变量。v1 把探针和被测对象混在一起，才会用错信号。

### ⬜ L3 · 服务与 `inject`

**要回答**：A 提供服务、B 声明依赖它。B 在 A 就位之前是**根本不挂载**，还是
**挂载了但拿不到**？A 后来就位了，B 会自动补上吗？

**假说**（源码）：`inject` 不满足时条目不 apply；服务就位触发重新检查并 apply。
loader 源码里有一句注释提到 fiber 会被「inject checker」dispose，说明依赖是活的、
会双向影响。

**实验设计**：
- 用 `disabled` 开关控制 registry 的就位时机（L2 已立住这个手段）
- alpha 的 apply 往见证文件写一行；registry 不在时见证文件不该出现
- 把 registry 从禁用改为启用（需重启，运行时改动属 L10），看 alpha 是否随之 apply
- 对照：不声明 `inject` 却直接用服务 → 预期拿到 undefined 或抛错

**难点**：`inject` 有两种写法（插件代码里 `export const inject = [...]`，
条目上 `inject: [...]`）。L2 实测发现 dsh-base 的 79 个条目**一个都没写条目级 inject**，
所以要把两种写法的关系测清楚：是覆盖、合并，还是各自独立生效？

**已有的两条实证**（写 `demo/lab-inspector` 教具时撞出来的，见 `demo/README.md`）：

1. **`inject: ["loader"]` 会把插件锁死在 PENDING。** loader 的 intercept 契约里有
   `await?: boolean` — *"Keep dependent plugins pending while loader entries are still
   loading"*。而插件自己就是 loader 的一个条目，于是等成死结：路由永远 404，
   **且日志里一个字都没有**（PENDING 不是错误，没人为它报警）。
   解法是 `ctx.get("loader")` 运行时取。
   → 本课要把这个 intercept 机制测清楚：哪些服务有这种 await 语义？

2. **boot 期的 PENDING 是致命的。** `dsh-app-boot` 的 `assertEntriesActivated` 在 boot
   末尾逐个检查，只要有条目停在 pending 就整体 fail-loud：
   `dsh: 1 entry did not activate / lab-demo-waiting: pending (waiting for service: ...)`。
   **推论：稳态运行的实例里根本看不到 PENDING**，它只可能出现在热重放中途加入条目的瞬间。
   → 这条直接影响 L3 的实验设计：不能指望「造一个 PENDING 条目然后观察它」，
   实例会起不来；要观察 PENDING 只能在运行中经热重放插入（那就依赖 L10 了）。

### ⬜ L4 · 加载顺序

**要回答**：条目在 YAML 里的先后，决定加载顺序吗？

**假说**：**不决定**。`dsh-base` 的 patch 文件里有原话
*"Row order carries no load semantics (activation is service-availability driven)"*，
而 `EntryGroup.update()` 的实现是 `Promise.allSettled(config.map(...))`——
**所有条目并发创建**，谁先 apply 由服务就位顺序决定。

**实验设计**：
- 让四个插件 apply 时各自往**同一个账本文件追加一行**（带时间戳），最后读出真实 apply 顺序
- 变体 A：按依赖顺序书写（registry → alpha → beta）
- 变体 B：**倒着写**（beta → alpha → registry）
- 断言：两种书写顺序下，**实际 apply 顺序一致**且都满足依赖先于被依赖

**难点**：并发写同一个文件要防交错——用「一条一个文件、按文件 mtime 排序」或
追加时带序号，别让观测手段自己引入竞态。

### ⬜ L5 · `ctx.effect`

**要回答**：注册副作用（HTTP 路由）时不用 `ctx.effect` 包住，会怎样？

**假说**：插件卸载后路由**泄漏**，继续应答。写作契约里说的就是这个。

**实验设计**：
- 两个几乎一样的插件：`lab-effect-wrapped` 用 `ctx.effect` 包，`lab-effect-raw` 不包
- 都注册各自的路由并返回可辨认的 JSON
- 启动 → 两个路由都通 → 禁用两个条目 → 再查
- 预期：包的那个 404（SPA 兜底，要校验响应体），不包的那个**仍然应答**

**这是第一课需要 web**：profile 要叠 `dsh-web-app`，启动更慢，要借端口。

**难点**：「禁用条目」在运行中做属于热重放（L10）。L5 要么用重启法绕开
（启动一次、禁用后重启、对比），要么等 L10 之后再回填。**倾向前者**——
L5 的重点是 effect 语义，不是重放机制。

### ⬜ L6 · 卸载连锁

**要回答**：被依赖者下线时，依赖方怎么办？

**假说**（源码 `entry.ts`）：
- 禁用**向下传播**：`_disabled()` 沿父链向上追溯，任一祖先禁用则本条目不运行
- **group 永远启用**：`if (options.group) return false`，group 自己不受 `disabled` 影响，
  但它的孩子会因父级禁用而停
- 服务消失时，依赖它的 fiber 被 dispose（loader 注释里的 "inject checker"）

**实验设计**：
- 禁用 `lab-registry` → 看 alpha / beta 是否跟着不 apply
- 二级链：只禁 alpha → beta 怎样（beta 同时依赖 registry 和 alpha）
- 账本（registry 提供的服务）在依赖方下线后是什么状态

**难点**：这一课可能要碰 group（测禁用传播）。若 group 实测走不通，
就只测服务维度的连锁，并如实标注 group 维度未覆盖。

---

## 第三级 · 配方从哪来

这一级的三课是 v1 已有结论的迁入 + 去 dshw 视角重述。**结论可信**（用例互相印证过），
但要用 Python 重写并复跑对齐——那既是格式统一，也是**独立第二实现的交叉验证**。

### ⬜ L7 · 空根 + patch 层叠

**要回答**：一棵组合树是怎么从空数组叠出来的？共五层，顺序和优先级如何？

**v1 结论（E2，4/4 通过）**：
- `$DSH_HOME/cordis.patch.yml` 这个 home 级层**真实存在**，优先级**压过** profile 活层
- 一份 home 层同时压中两个互不相干的 profile
- `--patch` overlay 优先级比 home 层还高

**新增要测**：`cordis.yml` 每次启动被重写成 `[]`（源码说是为了防 tree write-back
把已组合的行烤进文件、导致下次启动 insert 翻倍）——这条 v1 没测过，值得实测。

**为什么必须独立 home**：本课的实验对象就是 home 级 patch 文件。v1 共用 home 时
靠 `try/finally` 清理兜着，异常、中断、并发任一都会漏。现在是物理隔离。

### ⬜ L8 · patch 的三种语义

**要回答**：`- insert:`（带/不带 id）与 `- id:` 覆盖各是什么语义？

**v1 结论（E1，5/5 通过）**：`config` 是**按字段整体替换**，不是按键 merge。
未在 patch 里出现的**字段**不受影响（只写 `disabled` 不会清空 `config`），
但只要写了 `config`，里面没重述的**键**就消失。

**新增要测**（L2 带出来的）：
- 野字段：patch 能塞任意键，loader 只读那六个
- `null` 的删除语义：`if (isNullable(value)) delete candidate[key]`
- 找不到 id 时只警告、静默跳过
- 同一叠里后面的 patch 能改前面 patch 插进来的条目（`buildMap(insert)` 是有意为之）

### ⬜ L9 · bundle 层 vs 活层

**要回答**：两层的分工与冷热差别。

**v1 结论（E4，4/4 通过）**：改 bundle 的 patch 文件、或改 `dsh.profile.bundles`
名单，对**正在跑的实例毫无影响**，必须重启；活层秒级生效。
附带：把包从 bundles 名单摘掉、重启后，活层里 insert 同一个包的条目**照常存活**
——两条独立的注册路径。

**新增要测**：`dsh plugin add` 的真实机制（pnpm 转发器 + 按安装后实际状态对账，
凡声明 `dsh.bundle` 的依赖自动进名单）。这条 v1 只读了源码没实测。

---

## 第四级 · 什么是热的

### ⬜ L10 · 配方热重放

**这一课是第四级的地基，也是 v1 翻车的根因所在——必须先做扎实。**

**要回答**：活层文件改动之后，究竟发生了什么？**什么会变、什么不该变？**

**假说**（源码 `entry.ts` 的 `update()`）：
- 改 `config` → **原地 reconfigure**（`fiber.update(config)`），**不 dispose fiber**
- 改 `name` / `inject` / `group` → 重新 import + dispose + 重建
- `null` → 删除该键
- 无差异 → 直接 return，空操作
- 整个重放是**条目级事务 diff**：只动变化的条目，失败整体回滚

**观测方法论（本课最重要的产出）**：
> **只有变化的那个条目会重挂。** 所以判断「重放是否发生」，观测信号必须落在
> **被改动的那个条目**上。拿一个无关条目的 `appliedAt` 判断重放有没有发生是错的
> ——它本来就不该变。v1 的 E3 整批数据因此作废。

**实验设计**（每个用例都用三个指纹交叉判定：`marker` / `moduleLoadedAt` / `appliedAt`）：

| 改什么 | 预期 `moduleLoadedAt` | 预期 `appliedAt` | 说明 |
|---|---|---|---|
| 该条目的 `config` | 不变 | **变** | 原地 reconfigure，模块不重 import |
| 该条目的 `name` | 变 | 变 | 重新 import + 重建 |
| **无关的另一个条目** | 不变 | **不变** | ← 这条专门用来钉死观测方法论 |
| 文件改了但内容等价 | 不变 | 不变 | 无差异即空操作 |
| 把条目改成 `disabled` | — | 条目下线 | |

**难点**：v1 报过「活层只活一轮」的现象。那很可能是观测信号错误造成的误判
（同一份数据里 A2/C2 两轮又判定"生效"，自相矛盾）。本课要用正确信号重新验证。
**若「只活一轮」在正确观测下依然复现，那是一个真正的重大发现**，L13 全部推倒重来。

### ⬜ L11 · 代码热重载与快照面

**要回答**：改插件代码会怎样？哪些东西被缓存住了、谁负责刷新？

**v1 结论（E5，4/4 通过）**：
- 改 `apply` 期 `readFileSync` 读的文件 → **冷**，无任何反应（它从没进过 ESM loadCache）
- 改插件代码 → 热：模块重 import、apply 重跑，**这时那个文件才被重新读到**
- 插件在 hmr `root` 之外 → 冷
- **`root` 指向 `node_modules` 里的 junction 而非真实源码目录 → 冷**（hmr 默认忽略
  `**/node_modules`，依赖遍历也跳过它）

**新增要测**：`externals`（CLI 入口的依赖树）变动会触发 `loader.exit()` 整个进程退出
——HMR 唯一一条主动重启的路。这条只读过源码。

**要产出**：一张完整的**快照面**表（哪个缓存、什么时候拍的、谁负责刷新、热还是冷）。

### ⬜ L12 · client 双面插件

**要回答**：带浏览器端的插件怎么工作？为什么有的改动要重启、有的不用？

**v1 结论（E6）**：
- **推论 1 成立**：全新包名在实例运行中挂上去，**不重启**就进图、`client.js` 返回 200
  → 推翻「client 模块表是 boot 时快照」的说法。真实机制是**按包名增量扫描 + 永久负判缓存**
- **推论 2 成立**：先以「无 `dsh.client` 声明」形态挂载过的包，负判进缓存后补声明也没用，
  **必须重启**
- **附加推论被推翻**：「缺 `exports["./client"]` 是抛错而非缓存、补上不用重启」——
  三次干净复现证明**不成立**，行为与负判缓存一致。别指望这个逃生门

**新增要测**：client bundle 内容变化的热换链路（500ms stat 轮询 → 重算 sha1 → 换 rev
→ SSE 推浏览器）。v1 没测过这条。

**别忘了**：`bundle` 一词二义——**profile bundle**（冷）与 **client bundle**（热）
恰好是热冷两极。这是整份教材要澄清的头号术语陷阱，在本课收口。

### ⬜ L13 · hmr 自身的归属

**建立在 L10 之上。没有 L10 的观测方法论，这一课测不了。**

**要回答**：是谁在监听 patch 文件？它什么时候会死？

**已知机制**（源码）：
- `profile-boot` 在 boot 末尾：树里没有 hmr 服务时，**运行时创建一个 `root: []` 的兜底 hmr**
- 然后 `watchUserPatches` 把 profile 活层和 home 层的监听注册上去，
  **且只在 boot 时调用这一次**，之后没有任何代码会重新注册
- `registerConfig` 建立的 watcher，清理挂在 **hmr 插件自己的 fiber** 上
- 推论：**hmr 条目一旦经历 dispose + 重建，patch 监听就永久没了**

**实验设计**（v1 的教训：必须**单轮观测**）：
- 每轮改动前**重启实例**，一次只观测一件事，避免多轮改动互相干扰
- 场景 A：boot 时活层就有 hmr 反禁用条（树拥有 hmr）
- 场景 B：boot 时没有（游离的兜底 hmr）
- 关键一问：**只改 hmr 条目自己的 `config`（比如往 `root` 加一项），会不会导致
  patch 监听自断？**

**L10 的源码结论已经给了预言**：改 `config` 走的是原地 reconfigure 分支
（`replace` 只在 `name`/`inject`/`group` 变化时为真），**不 dispose fiber**，
所以监听不该断。本课负责把这个预言测实。

---

## 各课依赖与开销一览

| 课 | 前置 | 需要 web profile | 需要端口 | 预计用例 |
|---|---|---|---|---|
| L1 ✅ | — | 否 | 否 | 8 |
| L2 ✅ | L1 | 否 | 否 | 6 |
| L3 | L2 | 否 | 否 | 4–6 |
| L4 | L3 | 否 | 否 | 3–4 |
| L5 | L2 | **是** | 是 | 3–4 |
| L6 | L3 | 否 | 否 | 4–5 |
| L7 | L2 | 否 | 否 | 4–5 |
| L8 | L7 | 否 | 否 | 6–8 |
| L9 | L8 | 是 | 是 | 4–5 |
| L10 | L8 | 是 | 是 | 5–6 |
| L11 | L10 | 是 | 是 | 4–6 |
| L12 | L10 | **是** | 是 | 5–6 |
| L13 | **L10** | 是 | 是 | 4–6 |

**不需要 web 的课要坚持不叠 `dsh-web-app`**：只叠 `dsh-base` 时组合树是 79 个条目，
加上 web 会翻倍，启动慢一大截。观测手段能用见证文件解决的就别起 HTTP。
