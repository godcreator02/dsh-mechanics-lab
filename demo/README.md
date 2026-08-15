# lab-inspector · 教学演示件

在 DSH 的 Web 界面右侧贴一个**只读**卡片面板，实时显示实验插件的状态。

```powershell
uv run python demo/run_demo.py            # 起演示实例，Ctrl-C 停
uv run python demo/run_demo.py --check    # 非交互自检：起→验→停，退出码即结论
uv run python demo/run_demo.py --demo-pending   # 演示「boot 期 PENDING 是致命的」
```

打开它打印的地址（`http://127.0.0.1:3090/`），面板在右上角。

> 这是**教具**，不是某一课的 fixture。fixtures 按课分、允许重复；教具跨课通用，
> 所以住在 `demo/` 而不是某个 `l0X_*/fixtures/`。

## 状态名用框架自己的，不自己发明

卡片上的状态是 **Cordis 的 `FiberState`** 原名（`@deepseek-ai/cordis` 的
`lib/types/fiber.d.ts`），不翻译——这样面板上看到的词，和源码、日志、报错里的词是同一个：

| 状态 | 含义 | 颜色 |
|---|---|---|
| `ACTIVE` | 加载完成，正在提供服务 | 绿 |
| `PENDING` | 等 `inject` 声明的服务就位 | 黄 |
| `LOADING` | 插件回调正在执行 | 蓝 |
| `UNLOADING` | disposer 正在跑 | 蓝 |
| `FAILED` | 回调或配置校验抛了错 | 红 |
| `DISPOSED` | 已移除，不会再启动 | 灰 |

外加一个**条目级**（不是 fiber 级）的状态：

| 状态 | 含义 | 颜色 |
|---|---|---|
| `DISABLED` | 条目写了 `disabled`，压根没创建 fiber | 灰 |

**`DISABLED` 与 `PENDING` 的区别很要紧**：前者是人主动关的，后者是依赖没到位——
排查方向完全不同。悬停卡片能看到每个状态的一句话解释。

配色走框架的设计令牌（`--dsw-alias-state-success-primary` 等），亮/暗主题自动跟随。
实测暗色主题下绿色渲染为 `rgb(34,197,94)`——是令牌值，不是代码里的 fallback。

## 演示阵容

| 条目 | 状态 | 演示什么 |
|---|---|---|
| `lab-inspector` | ACTIVE | 面板自己（它也叫 `lab-` 开头，所以会列出自己） |
| `lab-demo-alpha` | ACTIVE | 正常挂载 |
| `lab-demo-sleeping` | DISABLED | 条目写了 `disabled: true` |
| `lab-demo-waiting` | —— | 只在 `--demo-pending` 时加入，见下 |

## 两条做的时候撞出来的机制

### 一、`inject: ["loader"]` 会把插件锁死在 PENDING

第一版给 host 半边写了 `export const inject = ["webServer", "loader"]`，结果
**路由永远 404，而且日志里一个字都没有**。

原因在 loader 的 intercept 契约里：

> `await?: boolean` — Keep dependent plugins **pending** while loader entries are still loading.

声明依赖 `loader` 的插件，会被挂在 PENDING 上等所有 loader 条目加载完。
而本插件**自己就是 loader 的一个条目**——它等 loader 加载完，loader 要加载完得先把它
加载完。死结。

**PENDING 不是错误，没人会为它报警**，所以日志干干净净，极难排查。

解法：不写进 `inject`，在 `apply` 里用 `ctx.get("loader")` 运行时取——那时它必然已就位。

### 二、boot 期的 PENDING 是致命的，稳态实例里看不到 PENDING

原本想让 `lab-demo-waiting`（`inject` 一个不存在的服务）在面板上显示一张黄色 PENDING
卡片。实测发现**实例根本起不来**：

```
dsh: plugin tree failed to load: dsh: 1 entry did not activate
lab-demo-waiting: pending (waiting for service: 压根不存在的服务)
```

`dsh-app-boot` 的 `assertEntriesActivated` 在 boot 末尾逐个检查条目是否激活，
只要有一个停在 pending 就整体 fail-loud。

**推论：一个正常跑着的实例里，PENDING 卡片是看不到的**——带 PENDING 条目的实例
压根起不来。`PENDING` 只可能出现在热重放中途加入条目的瞬间。

这条留给 `--demo-pending` 演示（它会如预期启动失败并打印上面那段报错），
也进了 `SYLLABUS.md` 的 L3。

## 它是怎么读到状态的

host 半边注册一个只读路由：

```
GET /lab-inspector/state
→ { marker, at, prefix, entries: [{ id, name, state, stateCode, disabled, ... }] }
```

判据抄自 `cordis-plugin-loader` 的 `Entry`：`entry.fiber` 有没有、`entry.fiber.state`
是几、以及 `entry.disabled`（这是个 getter，会**沿父链向上追溯**，祖先被禁用时也返回 true）。

`FiberState` 的数字→名字映射得自己写一张表：它在 cordis 里是 TypeScript 的
`const enum`，编译后被内联成数字字面量，**运行时不存在这个对象**，import 不到。

client 半边手写成官方 client bundle 同款的 `window.__ModuleLoader__.load` 格式，
所以这个包**不需要任何构建步骤**；挂在 `shell.overlay` 插槽（叠加语义，不抢占任何
已有区域——`details` 那个座位是「坐上去就得自己渲染整块」的替换语义）。

## 只读

没有按钮、没有点击、不发任何写请求。host 侧也没有任何改变状态的接口。
