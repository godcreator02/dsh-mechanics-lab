# 观测台

看实验跑的时候框架内部到底发生了什么——**事件级**，不是轮询级。

```powershell
# 1. 采集：给某个 profile 的活层加一条 lab-recorder（见下）
# 2. 看板：
uv run python observatory/board/server.py       # → http://127.0.0.1:8899/
```

## 两个部分，职责严格分开

```
实验进程（保持轻：只叠 dsh-base，79 条目）
  ├─ 教学插件（零改动、零依赖，仍然最小）
  └─ lab-recorder ────┐   ← 唯一住在进程内的部分。无 UI、零 inject
                      │  追加写 events.jsonl
                      ↓
  看板（独立 Python 进程，标准库 http.server，常驻）
    └─ 读 events.jsonl + witness-*.json → 网页
```

**为什么采集必须在进程内**：`internal/status` 这类事件只在那棵树内部发出，
跨进程听不见。

**为什么看板必须在进程外**：实验实例是短命的（pytest 起了就停），看板要常驻；
而且事件落了盘，**实例停了还能回看、还能把两次运行摆一起对比**——
看板长在进程里就永远做不到这个。

## 它是注入式的，不是外部观测

这一点要说清楚，因为它决定了这套仪器的能力上限和副作用。

`lab-recorder` **不是探针，是一个普通的 DSH 插件条目**——写在同一个活层里，
跟被观测的教学插件平级，没有任何特权。

| | |
|---|---|
| ✅ 只用**公开 API**（`ctx.on(...)`） | 不改框架一行代码、不 monkey-patch、不 hook Node 的模块加载、不用 `--inspect` 调试协议 |
| ✅ 可完全撤除 | 把那条 `insert` 删掉，系统恢复原样，不留痕迹 |
| ⚠️ **但它是树的一部分** | 它自己也占一个条目位、也产生自己的状态事件（时间线上看得到 `lab-recorder LOADING → ACTIVE`）、也受同样的加载规则约束 |

所以它是**内部观察者**，不是外部探针。三个必然后果：

1. **拿不到自己挂载之前的历史** —— 框架不提供事件回放，只能靠起点快照补
2. **没法保证自己第一个挂** —— 加载顺序由服务可用性驱动，不由书写顺序决定
3. **它本身是一个变量** —— 81 个条目 vs 80 个，外加每个事件一次回调开销

第 3 条就是它**默认不挂**的原因：实验保持「洁净房」状态，装仪器是显式动作。
对「什么变了什么没变」这类**定性**结论影响可忽略；测精确耗时时要心里有数。

看板那一半则是**纯外部**的：只读磁盘文件，跟被观测进程零耦合，
连实例是死是活都不需要知道。

## 怎么给一个实验装上采集器

采集器**默认不挂**——保持实验的「洁净房」状态，装仪器是显式动作。要观察时，
在活层加一条：

```yaml
- insert:
    - id: lab-recorder
      name: lab-recorder
      config:
        out: "<假home>/events.jsonl"
        flushMs: 100
```

然后把 `observatory/lab-recorder` link 进那个 profile。现成的例子见
`observatory/verify_scope.py` 和 `observatory/demo_lifecycle.py`。

## 订阅了什么：三类事件，依据是「是不是 waterfall」

分类标准**不是**"量大不大"，而是**订阅这个动作本身会不会改变系统**。

### 流水型 —— 全量记进 `events.jsonl`，时间线展示

| 事件 | 拿到什么 | 服务哪一课 |
|---|---|---|
| `internal/status` | fiber 状态每次转换，**带旧状态** | 全部 |
| `internal/plugin` | fiber 创建／销毁 | 全部 |
| `loader/partial-dispose` | 条目被重配置，**`legacy` 是改动前的 options** | ⭐ L10 |
| `internal/service` | 服务出现／撤销，**带提供者** | ⭐ L3 |
| `hmr/change` | HMR **看到了但没处理**的文件变化（见下） | ⭐ L11 |
| `hmr/reload` | **代码**热重载完成，带这次重载了哪些 | ⭐ L11 |
| `hmr/config-update-failed` | patch 重放失败及原因 | 排障 |
| `loader/entry-init` | 条目初始化 | 出生链 |
| `loader/config-update` | loader 把树写回磁盘 | 解释 `cordis.yml` 被重写 |

### 关系型 —— 去重聚合进 `events.relations.json`，单独一块展示

`internal/listener`（谁监听什么事件）。它**不是** waterfall（签名里没有 `next`），可以安全订阅。

**为什么去重而不记流水**：这类信息的价值在于**关系**，不在于次数。
"谁监听了 `session/event`" 有意义，"监听器被触发了 8000 次"没有。
去重后几十条，还直接画得出依赖图。

### 链路型 —— waterfall，**默认关**

`internal/config`、`internal/update`、`internal/get`、`internal/set`、`loader/patch-context`

⚠️ 这些监听器**必须调用 `next()` 并传回返回值**，否则**阻断整条执行链**。
订阅它们不再是只读观测，而是插进了执行路径。

打开方式：条目 config 里写 `waterfall: true`。打开后 `internal/get`
（每次服务访问都触发，热路径）走**去重聚合**，绝不记流水。

**为什么默认关**：L10 / L13 测的就是时序。仪器插在执行链里会让那两课的结论可疑。
平时想看服务读取关系再打开。

### 不订的

- 业务层 `session/*`、`tools/*`、`skills/*`、`session-telemetry/*` —— 跟插件机制无关，纯噪音

## 实测的事件量

一次 `demo_lifecycle` 运行（只叠 `dsh-base`，三次活层改动）：

```
status         209      entry-dispose  158      plugin    101
snapshot        82      service         42      hmr-change  2
```

共 596 条。看板按**时间间隔自动切组**（相邻事件超过 500ms 就切），
这次正好切成「启动 / 重放 #1 / 重放 #2」三组——L10 要看的就是
「这**一次**改动引发了什么」，而不是一条几百行的流水账。

### 顺带被数据证实的两件事

**① 配方热重放 ≠ 代码热重载。** 这次运行有 **2 条 `hmr-change`**（对应两次改活层文件），
但**一条 `hmr-reload` 都没有**——因为改的是 **patch 文件**（走配方热重放），
不是**插件代码**（走代码热重载）。两条链路的区分**被直接观测到**，不用再靠推理。

**② `hmr/change` 的语义是「看到了但没处理」，不是「检测到变化」。**

hmr 的主 watcher 对每个文件变化按顺序判断四条分支：是 include 的 config 文件 →
刷新子树；在 `externals` 里 → 整进程退出；在 ESM `loadCache` 里 → 代码热重载；
**都不是 → 只 `emit('hmr/change')`，没人接**。

那 2 条 `hmr-change` 的 url 都是 `cordis.patch.yml`，而且时间戳落在**配方重放之后**：

```
重放 #1 从 +1052.2ms 起  ……  hmr-change 在 +1058.971ms
重放 #2 从 +4058.3ms 起  ……  hmr-change 在 +4058.316ms
```

说明 patch 文件的重放是 **`registerConfig` 那个独立 watcher** 干的；
主 watcher 因为 `root: ['.']` 覆盖了 profile 目录也看见了同一个文件，
但一路走到第 4 条分支，发了个没人接的事件。

⚠️ 第 4 条分支同时是「**非 import 文件是冷的**」的实现根因：插件在 `apply` 里
`readFileSync` 读的文件从没进过 `loadCache`，改了它就走到这一条。

## 采集器的三条设计约束

1. **零 `inject`**。订阅事件只要 `apply` 的 `ctx`，写文件只要 `node:fs`。
   没有依赖就没有等待，它会在很早的批次里挂上，漏掉的早期事件最少。
   （反面教材：`lab-inspector` 因为 `inject: ["loader"]` 被 loader 的 await 语义
   锁死在 PENDING，日志里一个字都没有。见 `demo/README.md`。）
2. **内存缓冲 + 定时 flush**，不是每个事件同步写盘。实验里有几百次状态转换，
   逐个同步写会明显改变时序；我们测的是「什么变了什么没变」这类定性结论，
   宁可丢掉最后 250ms 也不污染时序。
3. **只记录，不判断**。事件原样落盘，过滤/聚合/解释全在看板做。
   采集器越笨越好——它是唯一会影响被观测系统的部分。

## 已验证的地基

`uv run python observatory/verify_scope.py`

`ctx.on('internal/status')` **能听见整棵树**，不只是自己子树：一次运行采到 386 条
事件、81 个条目，框架自带的 `timer`/`llm`/`session`/`agent`/`hmr` 全部命中。

### 但采集器挂载之前的事件必然丢失

实测（加快照之前）：`lab-minimal` 只录到**最后一跳** `LOADING → ACTIVE`，
它的 `fiber created` 和 `PENDING → LOADING` 都发生在采集器 apply 之前。
78 个条目本该有约 234 次转换，只录到 203 次。

**缓解**：订阅之后立刻拍一张全树快照（`snapshot` 事件），记下每个条目此刻的状态。
丢掉的仍然是**过程**，但起点是确切的。

**为什么没法根治**：加载顺序由**服务可用性**驱动、不由书写顺序决定
（L4 的主题），没法把采集器排到第一个。时间线顶部那条
「采集开始（本行之前的事件未被记录）」就是这个边界的标记。

## 实测：条目被更新 / 禁用时发生什么

`uv run python observatory/demo_lifecycle.py`

挂两个条目（`alpha`、`beta`），每次只动一个，另一个当对照组。

### 改 `config`

```
alpha   ACTIVE → UNLOADING
alpha   UNLOADING → LOADING
alpha   LOADING → ACTIVE
beta    （一个事件都没有）
```

**⚠️ 这修正了一个源码推断。** 从 `entry.ts` 的 `update()` 读出来的是
「改 config 走原地 reconfigure 分支，不 dispose fiber」，于是我一度认为
「fiber 不动」。实测更精确：

- **fiber 对象确实保住了**——没有 `fiber disposed` 事件（对比下面禁用 beta 那条）
- **但状态实实在在走了一遍 `UNLOADING → LOADING`**，意味着 **`ctx.effect` 注册的
  副作用被清理并重新执行了一遍**

「fiber 没被销毁」≠「fiber 没动过」。这个区别对下面这条推论是决定性的。

### 禁用条目

```
beta    fiber disposed          ← internal/plugin，在状态转换之前
beta    ACTIVE → UNLOADING
beta    UNLOADING → DISPOSED
alpha   （一个事件都没有）
```

### 强杀时看不到卸载链

`inst.stop()` 走的是 `taskkill /T /F`，disposer 根本不跑，所以停止阶段
「一个事件都没有」。要看优雅卸载，只能让进程自己退出。

## 这套东西直接解决了 v1 E3 的观测难题

E3 废掉的根因是：拿**一个无关条目**的 `appliedAt` 判断「活层重放有没有发生」，
而条目级 diff 意味着无关条目本来就不该动，于是它永远分不清两种情况。

现在当场可分：

| 现象 | 结论 |
|---|---|
| 别的条目有事件、目标条目没有 | 重放发生了，条目级 diff 生效 |
| **全树一个事件都没有** | 重放根本没发生 |

上面两个阶段的对照组（改 alpha 时 beta 静默、改 beta 时 alpha 静默）
就是条目级 diff 的**直接实测证据**——v1 想测而没测成的正是这个。

## ⚠️ 一条待验的重要线索：hmr 的 config 一改，patch 监听可能就断了

把实测和源码接起来：

1. 改 `config` 会让 fiber 走 `UNLOADING → LOADING`（**本页实测**）
2. `UNLOADING` 阶段会清理该 fiber 上所有 `ctx.effect` 注册的副作用（Cordis 语义）
3. `hmr.registerConfig()` 建立的 patch 文件 watcher，**正是挂在 hmr 自己 fiber 的
   effect 上**（`cordis-plugin-hmr` 源码）
4. 而 `watchUserPatches` **只在 boot 时调用一次**，之后没有任何代码会重新注册
   （`profile-boot` 源码）

**推论：任何改动 hmr 条目 `config` 的操作，都会让 patch 文件监听被自己清掉，
且不会恢复——直到重启。**

而 `dshw attach` 每挂一条分发线，做的正是「往 hmr 条目的 `root` 里叠一项」。

这条推论与 v1 E3 的一个观察吻合：Part C4 记录到「哑火是永久性的，把 root 改回去
也救不回来」。当时因为观测信号选错、整批数据作废，这一条也就没被当真。

**这是 L13 的核心问题，必须单独实测，不能就这么写进结论。**
但它已经足以推翻我之前给出的「dshw attach 是安全的」这个说法——那个说法建立在
「改 config 不动 fiber」这个**不够精确**的源码推断上。

## 边界（有意划死的）

这是观察窗口，不是仪表盘产品：

- **只读、只显示**，不能启停实例、不能改任何配置
- 服务端无状态，就是读文件 + 渲染
- 单文件 HTML，零依赖（标准库 `http.server`），不引入构建步骤
- 功能封顶四样：**时间线 / 当前态 / 见证流 / 跨运行对比**。
  超出的想法先记进 `DRAFT.md` 待议，不直接做——这个项目的产物是**理解**，
  不是一个需要维护的仪表盘。

端口用 **8899**，躲开实验段（3090–3099）、主实例（3080）和 dshw 哈希池（3100–3979）。
