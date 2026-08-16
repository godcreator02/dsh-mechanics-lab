# L16 · client 双面插件

> **这里的东西还没有用例覆盖。** 它们来自一个真做出来、跑起来过的插件
> （`lab-inspector`，2026-08-16 随 `demo/` 一起删掉），当时肉眼验过、也有过
> 一个非交互自检，但从没进过 pytest。开 L16 时把它们设计成用例，验过了
> 结论才进 `docs/SYLLABUS.md` 和课 README，这里对应的段随之清掉。

## 假设

- L16 在 SYLLABUS 里的位置和前置（L6 · bundle vs 活层）不变
- 这一课需要 web —— client 半边要真被浏览器加载才算验到
- 端口仍在 3090–3099，跟别的课一样按 worker 分段

---

## §1 需求

### 1.1 要回答什么

**一个包怎么同时活在两侧？** host 半边跑在 Node 进程里，client 半边跑在浏览器里，
它们是同一个 npm 包的两个入口。要弄清的是：

- client bundle 怎么被 host 挂出来、浏览器怎么找到它
- 两侧怎么通信（host 注册只读路由，client 去取）
- 插槽（slot）语义：坐进去之后是叠加还是替换

### 1.2 不做什么

- 不做「client 模块表怎么增量扫描 / 负判缓存」——那是 L6 已经验过的
- 不做构建工具链（webpack / vite 配置）。本课要证的恰好相反：**不需要构建**
- 不做 UI 好不好看。面板只要能渲染出可断言的 DOM 就够

### 1.3 边界

本课只管**一个包两侧**这件事。跨包的 client 依赖、client 之间怎么互相调用，
不算本课的事。

### 1.4 宏观验收

- 一个不经任何构建步骤的包，client 半边能被浏览器加载并渲染出内容
- host 半边的路由能被 client 取到
- 上面两条都由用例断言，不靠肉眼

**分叉题 · artifact 做成什么**

- [ ] **只读状态面板**（推荐）—— 沿用 `lab-inspector` 的形态：列出所有
      `lab-` 开头的条目，显示 fiber 状态。比如面板上一行
      `lab-demo-sleeping  FIBER —— / ENTRY DISABLED`，用例断言这行的
      `data-*` 属性
- [ ] **最小 hello world 双面插件** —— 只验通路：client 渲染一个固定字符串、
      host 回一个固定 JSON。比如断言页面上出现 `l16-ok`，不做任何状态展示

---

## §2 artifact 定义

一个教学插件包，`fixtures/l16-panel/`（名字待定于上面那道题），包含：

- **host 半边**（`lib/index.js`）：注册一个只读 GET 路由，返回条目状态的 JSON
- **client 半边**（`lib/client.js`）：手写的 bundle，挂进一个插槽，取上面那个路由渲染
- **`package.json`**：带 `dsh.client` 声明和 `exports["./client"]`

外加该课的用例：拉一个带 web 的实例、断言 `client.js` 取得到、断言页面渲染了内容。

**这个包本身就是这一课的教材**——它是「双面插件长什么样」的最小完整样本。

---

## §3 技术

### 3.1 client 半边可以完全不用构建

手写成官方 client bundle 同款的 `window.__ModuleLoader__.load` 格式，
整个包就**不需要任何构建步骤**——没有 webpack、没有 vite、没有 `dist/`。

这条如果成立，对教学价值极大：读者不用先装一套前端工具链才能看懂双面插件。

⚠️ **待验**：当时是肉眼看到面板渲染出来了，没有断言。要验的是
「手写格式真的被 `__ModuleLoader__` 接受」，而不是「页面上有东西」。

### 3.2 插槽有两种语义，别坐错座位

| 插槽 | 语义 | 坐上去的后果 |
|---|---|---|
| `shell.overlay` | **叠加** | 浮在已有界面之上，不抢占任何已有区域 |
| `details` | **替换** | 坐上去就得自己渲染整块，原来那块没了 |

`lab-inspector` 挂的是 `shell.overlay`，所以能跟正常界面共存。

### 3.3 ⚠️ `inject: ["loader"]` 会把插件锁死在 PENDING

**这条是写 host 半边时撞上的，而且极难排查。**

loader 的 intercept 契约里有一句：

> `await?: boolean` — Keep dependent plugins **pending** while loader entries
> are still loading.

于是：声明依赖 `loader` 的插件会被挂起，等所有 loader 条目加载完；
而这个插件**自己就是 loader 的一个条目**——它等 loader 加载完，
loader 要加载完得先把它加载完。**死结。**

症状是最坏的那种：**路由永远 404，日志里一个字都没有。**
因为 **PENDING 不是错误，没有人会为它报警**。

解法：不写进 `inject`，在 `apply` 里用 `ctx.get("loader")` 运行时取
——跑到 `apply` 的时候 loader 必然已经就位。

**分叉题 · 这条归谁验**

- [ ] **等 L16 一起做**（推荐）—— 本课本来就要写 host 半边，顺手加一个变体：
      同一个插件，一版写 `inject: ["loader"]`、一版运行时 `ctx.get`，
      比较两者的 fiber 状态与路由可达性。比如断言前者 `fiberState=PENDING`
      且 `GET /l16-panel/state` 连不上，后者 `ACTIVE` 且返回 200
- [ ] **现在给 L9 补一个用例** —— L9（服务与 inject）已完成，这条是 inject 的
      一个真实陷阱，补进去更贴主题。比如在 L9 加
      `test_inject_loader_self_deadlock`，代价是要回头改一课已定稿的内容

### 3.4 host 半边读条目状态的判据

抄自 `cordis-plugin-loader` 的 `Entry`：`entry.fiber` 有没有、`entry.fiber.state`
是几、以及 `entry.disabled`（这是个 **getter，会沿父链向上追溯**，祖先被禁用时
它也返回 true）。

`FiberState` 的数字→名字映射得自己写一张表：它在 cordis 里是 TypeScript 的
`const enum`，编译后被内联成数字字面量，**运行时不存在这个对象，import 不到**。

⚠️ 展示状态时，**官方的 `FiberState` 和条目级事实必须分成两个字段**，
不能合并成一个「状态」。没有 fiber 时 FiberState 那一栏显示 `——` 而不是某个
自造的名字——「没有 fiber」压根不是 `FiberState` 的成员，硬塞一个进去，
读的人会以为 Cordis 有七个状态。

`DISABLED`（人主动关的、连 fiber 都没有）与 `PENDING`（fiber 建了、卡在等依赖）
的区别尤其要紧，排查方向完全相反。
