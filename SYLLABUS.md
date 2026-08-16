# 课程大纲

顺着**加载链条**编排：**你写的东西 → 声明它的那一行 → 那一行从哪来 → 变成什么 →
怎么活过来 → 活着的怎么变**。

**这是依赖顺序，不是排版顺序**——后一课要用到前一课立住的词和观测手段。
跳级的后果是**观测信号选不对**：不先搞清「重放发生时什么该变、什么不该变」，
就设计不出能判定「hmr 归属」的信号，跑出来的数据整批不可判。

## 两套标记

| 状态 | | 性质 | 含义 | 用例该怎么写 |
|---|---|---|---|---|
| ✅ | 做完，用例全过 | 📗 **复述型** | 官方文档已写明 | **对照式**：断言文档承诺的行为，一致则复述、不一致是重大发现 |
| 🚧 | 正在做 | 🔬 **发现型** | 文档没有，只能实测 | **观察式**：先如实记录发生了什么，再下判定 |
| ⬜ | 未开始 | ⚠️ **矫正型** | 文档写了但简化或不全 | **对比式**：文档说 X，实测 X 的边界在哪 |

**性质标记决定用例的写法**——探索式用例写成「跑跑看会怎样」，对照式用例写成
「文档承诺 X，验证这一版部署是不是 X」，断言强度和失败时的含义完全不同。

分类判据：官方文档已写明的是 📗；文档完全没有、只能实测的是 🔬；
文档写了但在教程语境里做了简化、照搬会踩坑的是 ⚠️。**开课第一件事是 grep
`docs/official/` 定性质**。

引用官方文档一律用 `docs/official/zh/...` 路径 + 行号（版本钉 `47f9438`）。

---

## L0 · 全景：一棵树长什么样

> ✅ 12 个用例 / 约 90s / 不需要 web ｜ 🔬 发现型 ｜ 前置：无

**先总后分的「总」。** 不求讲透任何一件事，只求让你一次看清整棵树的形状——
后面六个部分各展开其中一块。

一个 DSH 实例最少需要什么才能跑起来？答案是**你要声明的插件集合为空**
（`bundles: []` 就能跑），**但树里从来不空**。

五条判定，每条都在后面有专属的一课深入：

| 判定 | 展开于 |
|---|---|
| **配方 ≠ 树**：运行时多三个条目，`--dump-config` 永远看不见 | **L7** |
| **层级**：兜底的 timer/hmr 在根组、与 include 平级，不在配方子树里 | **L8** |
| **boot 期 PENDING 无条件致命**（`assertEntriesActivated`） | **L11** |
| **`name` 有三条解析路径**，互不相通 | **L3** |
| **`timer`/`hmr` 关不掉**，写进活层再 `disabled` 只会让框架另造一份 | L8、L17 |

立住的词：**幽灵条目**、普查员、兜底、空根。

**产出**：`make_minimal_profile()`——后面所有课的基线。相比 `dsh-base`（78 个条目）
启动快一截，事件流从几百条降到十几条，且剩下的每一条都跟被测对象有关。

⚠️ 兜底那个 hmr 是 `root: []`——够监听 patch 文件，**不监听代码文件**。
要测代码热重载得自己挂：`make_minimal_profile(hmr_root=[...])`。

---

# 一 · 插件与条目
> **你写的东西，和配方里指向它的那一行**

## ✅ L1 · 插件的最小形态

> 8 个用例 / 约 32s / 不需要 web ｜ ⚠️ 矫正型 ｜ 前置：L0

一个插件最少需要什么？怎么从**外部**证明它真被加载了？

立住的词：条目、活层、bundle 层、加载、见证文件。

**两条容易想当然的**：`exports["."]` **不是**必需项——Node 有
`exports → main → index.js` 回退链，三条断一条不影响；活层贡献的条目**也有**
来源注释，只是形式跟 bundle 层不同（bundle 层标包名，活层标 patch 文件绝对路径）。

📗 文档侧：`zh/user/develop/basic/index.md` 讲了插件的三种形态（函数 / 对象 / 类），
本课只测了函数形态——**对象形态与类形态未覆盖**，且官方 postmortem 0001
记录过「default export 导致 `inject` 丢失」的真事故，值得回填。

## ✅ L2 · 条目的字段

> 6 个用例 / 约 38s / 不需要 web ｜ 🔬 发现型 ｜ 前置：L1

条目能写哪些字段、各管什么。

立住的词：禁用、`!!js` 表达式、野字段。

关键结论：条目只有**六个字段**（id/name/config/disabled/group/inject）；
不认识的键**带着走但没人读**（写错字段名静默失败）；`disabled` 是不挂载不是删除，
且可写条件表达式。

📗 文档侧：`!!js` 的求值时机官方讲了——
「Loader 只挂载一次组合，等待每一行的普通注入，**再基于其已注入的上下文求值**
该行的 `!!js` 配置」（`zh/user/develop/basic/publish.md:151`）。
官方 postmortem 0002 记录了 `!!js` 表达式意外禁用文件系统工具的事故，**必读**。

## ✅ L3 · `name` 的三条解析路径

> 8 个用例 / 约 62s / 不需要 web ｜ ⚠️ 矫正型 ｜ 前置：L1

**要回答**：条目的 `name` 怎么变成一个真的模块？

L0 已经撞出了骨架：

```js
name.startsWith("cordis:") →  loader.builtins[...]              // 内置表
name.startsWith(".")       →  import(new URL(name, ctx.baseUrl)) // URL 解析
否则                        →  import(name)                       // 包解析
```

**实测推翻一个交底里的假设**：`ctx.get("loader").internal`（那个需要 native
addon `node-addon-require-builtin` 才能激活的分支）在本部署**确实激活**了，
不是"被 try/catch 静默吞掉"。后果是源码里的"四条判断"实际只有两层：
`cordis:` 前缀在 `internal` 判断之前就短路，独立生效；剩下相对路径 / 绝对路径 /
裸包名**代码路径合一**，全部丢给 `internal.import(name, baseUrl, {})`——但
报错堆栈直接暴露出 `internal.import` 内部就是 Node 自己的 ESM 解析器
（`legacyMainResolve`、`throwIfUnsupportedURLScheme` 等内部函数名清晰可见），
所以解析**行为**依然按协议/相对/包名分叉，只是走的是同一段代码。

**实测结论**：
- **Windows 裸盘符绝对路径加载不了**：`D:\...\index.js` 里的 `D:` 被 Node 当成
  URL scheme，报 `ERR_UNSUPPORTED_ESM_URL_SCHEME`；改成 `file://` URL 形式立刻成功
- **两种"加载失败"报错文本完全不同**：`cordis:` 未知内置项是 cordis 自造的
  `invalid plugin, expect function or object with an "apply" method`（从未
  建立 fiber，第三种失败形态）；裸包名找不到是 Node 标准的
  `ERR_MODULE_NOT_FOUND`——混着断言会把两种不同机制读成一件事
- **`exports` 子路径**（官方 publish 文档 `dsh-hello-plugin/startup` 那种写法）
  必须在 `exports` 里显式声明才能加载，声明了 `.` 不代表子路径也开放；
  未声明报 `ERR_PACKAGE_PATH_NOT_EXPORTED`，文件本身完好无损也拿不到
- **相对路径没有 `exports`/`main` 回退链**：同一份代码，相对路径直指非入口
  文件能加载，包名引用同一个包因为回退链走到底找不到默认 `index.js` 而失败

⚠️ **矫正点坐实**：`zh/user/develop/basic/index.md:56` 写「插件路径必须是绝对
路径」，示例给的是 POSIX 风格路径。这条建议在 POSIX 上成立是因为那种路径
恰好也是合法 URL；照搬到 Windows 的裸盘符路径上会失败——真正的规则是
「必须是合法 URL」，不是「必须是绝对路径」，两者在 Windows 上不等价。

详见 `experiments/l03_name_resolution/README.md`。

---

# 二 · 配方
> **那一行从哪来：五层 patch 是怎么叠成一份配方的**

⚠️ **这三课是对照式的**：层叠规则官方文档已经写全，所以要验的不是「规则是什么」，
而是**这一版部署的实际行为与文档承诺是否一致**——一致就复述，不一致才是重大发现。
这决定了用例的断言强度：直接断言文档承诺的行为，而不是「跑跑看会怎样」。

## ✅ L4 · 空根 + 五层叠加

> 📗 复述型 ｜ 前置：L2 ｜ 不需要 web ｜ 预计 4–5 用例

**要回答**：一棵组合树是怎么从空数组叠出来的？

📗 **官方原文**（`zh/user/develop/basic/publish.md:112-119`）逐条列明：

1. profile 的 `dsh.profile.bundles` 所列各 bundle 的 patch，按列表顺序
2. profile 自己的 `cordis.patch.yml`
3. home 级的 `$DSH_HOME/cordis.patch.yml`——各 profile 共享的机器本地偏好
4. 每个 `--patch <path>` overlay，按 argv 顺序

**已验证**：home 级层真实存在、优先级压过 profile 活层；
一份 home 层同时压中两个互不相干的 profile；`--patch` overlay 比 home 层还高。
**与文档一致。**

**~~新增要测~~：`cordis.yml` 被重写成 `[]`** —— **L0 已验**，本课只需复述：
profile 目录下不建这个文件也照跑，启动后框架自己建出来，内容就是源码里
`PROFILE_ROOT_CONFIG` 那个常量（三行注释 + `[]`）。

**为什么必须独立 home**：本课的实验对象就是 home 级 patch 文件，而那一层对该 home 下
**所有 profile** 同时生效。靠 `try/finally` 清理兜不住——异常、中断、并发任一都会漏，
所以每个实验一个独立 home，物理隔离。

## ✅ L5 · patch 的三种语义

> 9 个用例 / 约 19s / 不需要 web ｜ 📗 复述型 + 🔬 发现型 ｜ 前置：L4

**要回答**：`- insert:`（带/不带 id）与 `- id:` 覆盖各是什么语义？

📗 **官方原文**（同上 `:123`）：「后应用的层按行胜出，且 patch 会**替换目标行的整个
`config` 值，而不是深度合并各键**」，并给出作者侧的推论：覆盖时**必须重述该行需要的
每一个键**，不能只写改动的那个。

**已验证，与文档一致**：未在 patch 里出现的**字段**不受影响
（只写 `disabled` 不会清空 `config`），但只要写了 `config`，里面没重述的**键**就消失。

🔬 **文档没写、要实测的**：
- 野字段：patch 能塞任意键，loader 只读那六个（L2 带出来的）
- `null` 的删除语义：`if (isNullable(value)) delete candidate[key]`
- 找不到 id 时**只警告、静默跳过**——这跟「改配置没生效」是两种现象，别混
- 同一叠里后面的 patch 能改前面 patch 插进来的条目（`buildMap(insert)` 是有意为之）
- 同 id 双挂载抛 `duplicate loader entry id`，**整次重放事务回滚**

## ✅ L6 · bundle 层 vs 活层

> 3 个用例 / 约 70s / 需要 web ｜ 📗 部分复述 + 🔬 发现型 ｜ 前置：L5

**要回答**：两层的分工与冷热差别。

**已验证（两次独立实现、结论一致）**：改 bundle 的 patch
文件、或改 `dsh.profile.bundles` 名单，对**正在跑的实例毫无影响**，必须重启；
活层秒级生效——两者是**同一个根因**：`watchUserPatches` 只给 profile 活层和
home 层注册了 watcher，`dsh.profile.bundles` 列表本身与各 bundle 自己的 patch
文件物理上没有代码在监听。
附带：把包从 bundles 名单摘掉、重启后，活层里 insert 同一个包的条目**照常存活**
——两条独立的注册路径，且这条独立性扛得住重启。

🔬 **新增实测（源码 + 实测坐实）**：bundle 层与活层用同一个 `- insert:` id
双挂载，撞在**首次 boot**——`cordis-plugin-loader` 的 `EntryGroup.update()` 在
创建任何条目**之前**先扫一遍查重，抛 `duplicate loader entry id`，整个进程
以退出码 1 死掉（不是"打个警告、旧条目继续跑"那种运行期热重放会有的宽容）。

📗 **文档侧**：`zh/user/develop/basic/publish.md` 讲全了两种 manifest
（`dsh.bundle` vs `dsh.profile`）、`dsh plugin add` 的行为（转发 pnpm + 自动把声明
`dsh.bundle` 的包追加进 `bundles`）、以及从 GitHub 安装时 `prepare` 脚本这道坎。

🔬 **未实测、按源码结论直接写进 README**：`dsh plugin add` 的对账时机——它是
**按安装后的实际状态**对账的，这意味着一个包能否进 bundles 取决于安装结果而非
命令参数。纪律 8 明确禁止在本实验台里真跑 `dsh plugin` 任何子命令（会联网、
真改 profile），这条只走源码引用、不实跑验证。

⚠️ **实验台自己的做法与此相反**：`link_plugin()` 刻意**绕开** `dsh plugin add`，
因为它会把带 `dsh.bundle` 的包自动对账进 bundles，与活层 insert 双挂 →
`duplicate loader entry id`。本课用同一个教学插件在 boot 期正面撞了这个冲突
（见上面的新增实测），坐实了绕开 `dsh plugin add` 这个设计决定的必要性。

详见 `experiments/l06_bundle_vs_live/README.md`。

---

# 三 · 树
> **配方变成了什么：进程里真正跑着的那棵树**

**这是 L0 最核心的两条判定的展开处。** 官方文档在这一层是空白——
`user/develop/` 讲的是「怎么写插件」，不讲「框架怎么加载插件」。

## ✅ L7 · 配方 ≠ 树：`include` 与幽灵条目

> 6 个用例 / 约 60s / 不需要 web ｜ 🔬 发现型 ｜ 前置：L4、L0

**要回答**：`--dump-config` 算出来的东西，和进程里跑着的那棵树，差在哪？

**L0 已立住**：差三个条目，全都不在任何 patch 文件里。

| 条目 | 谁造的 | id | 何时 |
|---|---|---|---|
| `cordis:include` | `mountRootInclude()` | 固定 `include` | boot 期 |
| `timer` | profile-boot 兜底 | **随机生成** | boot **返回后** |
| `hmr` | 同上，`config: {root: []}` | **随机生成** | 同上 |

**本课要展开的**：

1. **`include` 不只是一个条目——整个配方装在它的 `config.patches` 里。**
   由此推出一条实现事实：**「配方热重放」就是「改 `include` 这一个条目的 config」**
   （`watchUserPatches` 的回调重新 compose 出 patches，然后 `entry.update({config})`）。
   这条是 L14 的地基，必须在这里钉死。
2. 兜底的触发条件是 `ctx.get("hmr") === void 0`——**判服务不判条目**。
   L0 验过：写进活层再 `disabled: true` 只会让框架另造一份，**关不掉**。
3. 幽灵条目的 id 每次启动都不一样，**只能认 `name` 不能认 id**——这是后面所有课
   写断言时的硬约束。
4. 🔬 **未坐实的观察**（L0 记下的）：兜底 `loader.create()` 会 `tree.write()` 写回
   `cordis.yml`，而那正是 root include 的 config 文件——可能触发一次整树刷新。
   只见过一次、证据被旧版工具覆盖了，本课或 L14 用事件流去抓。

**观测手段**：`fixtures/l00-census` 普查员（拍两张快照：apply 当下 + 延后）。

## ⬜ L8 · 层级：谁在子树里、谁不在

> 🔬 发现型 ｜ 前置：L7 ｜ 不需要 web ｜ 预计 4–5 用例

**要回答**：`loader.entries()` 是扁平遍历，那真实的层级是什么？谁管着谁？

**L0 已立住**：

```
根组
├─ include (cordis:include)    ← 树根，配方装在它的 config 里
│   └─ 配方里的条目…            ⊂include
├─ timer  ← 兜底，与 include **平级**
└─ hmr    ← 同上
```

**这条判定的分量**：配方热重放重新 compose 的**只有 include 的子树**，
碰不到平级的那些。于是同样叫 hmr，两种处境完全相反——

| | 位置 | 配方重放时 |
|---|---|---|
| 兜底的 hmr | 根组，与 include 平级 | 碰不到它，watcher 稳 |
| 写在配方里的 hmr | **include 子树里** | **可能被重挂，watcher 随 effect 一起清掉** |

真实部署里常见的是后者（web bundle 自带 hmr 条目、再靠活层反禁用），而最小环境是前者。
**「同样的操作在一处让 patch 监听哑火、在另一处却一切正常」很可能就源于这个差别**——
两边测的根本不是同一个东西。**L17 的实验设计完全依赖本课的结论。**

**本课补上的三件事（全部实测）**：

- **`group` 造嵌套子树**：三层嵌套（`include → outer-group → inner-group → leaf`）
  确认 `parent` 跟随 **config 的嵌套结构**，不是 patch 文件里的书写位置
- **禁用传播的 group 例外**：`disabled: true` 的 group **自己照常激活**
  （`fiberState=2`），但它的孩子拿不到 fiber；对照组（非 group 条目）则真被停掉。
  正是源码 `_disabled()` 里 `if (options.group) return false` 那一行
- **服务隔离**：两个 `isolate: {labFlavor: true}` 组各自提供同名服务、值不同，
  各组消费者只看见自己那份。⚠️ **只做了正向覆盖，负面对照未测**，README 已标注

🔬 **顺手撞出的一条，影响所有后续课**：
**`loader.entries()` 的顺序不稳定**——既不反映创建时间，也不反映树位置
（兄弟组的孩子并发创建、交错）。**只有 `parent` 能信。**
任何依赖 entries() 顺序的断言都是脆的，而且很容易写出来还碰巧通过。

---

# 四 · 激活
> **树上的条目怎么活过来：不是按顺序，是按服务**

## ✅ L9 · 服务与 `inject`

> 8 个用例 / 约 55s / 不需要 web ｜ 📗 复述型 + 🔬 发现型 ｜ 前置：L7
>
> *（排在「树」之后：先有树，才谈得上树上的条目怎么激活。）*

**实测结论**：

- `inject` 是**硬依赖**——服务没到位 `apply` 根本不执行（不是「执行了但拿到 undefined」）
- 🔬 条目级 `inject` 是**补充不是覆盖**，绕不开代码里的声明
  （文档只讲了代码级 `inject`，没提条目级）
- 书写顺序不决定加载顺序（倒着写结果一样）→ L10 展开
- 部分依赖满足也照样拦——依赖是全有全无
- 依赖永远满足不了 → boot 末尾整树回滚、进程退出码 1 → **L11 展开**

📗 **文档侧**（`zh/user/develop/framework/service.md`）：inject 硬依赖、
服务消失时依赖方自动 dispose、服务恢复后自动重载——这几条文档都写了。
🔬 **文档没写的**：`package.json` 里的**包级** `@deepseek-ai/cordis.services.required`
（hmr 包就是这么声明它依赖 timer 的）。

⚠️ **本课的用例 7 藏着一个必须知道的陷阱**：`start_instance(wait_http=False)`
**立即返回、不做存活检查**，所以判断「启动失败」只能自己等一会再看 `inst.alive()`，
靠 `try/except LabError` 是无效的——那个 except 永远不触发，
**用例会变成没在测它自称在测的东西**，而且它会安静地通过。详见本课 README。

**教学插件**（本部分共用，四个）：

| 插件 | 角色 | inject |
|---|---|---|
| `lab-registry` | 提供服务 `labRegistry`：一本「谁来登记过」的账本 | — |
| `lab-alpha` | 往账本里登记自己 | `labRegistry` |
| `lab-beta` | 二级依赖，验证依赖链传递 | `labRegistry`, `labAlpha` |
| `lab-probe` | 把账本经 HTTP 暴露出来，当**观测面** | `webServer`, `labRegistry` |

**观测面独立成一个插件**是有意的：把「被观察的对象」和「观察的手段」分开，
免得观测手段自己成为变量——探针和被测对象混在一起就会用错信号。

账本**每登记一笔就整份落盘**，所以见证文件里的顺序就是**真实的 apply 先后**——
L9 用它验依赖，L10 用同一份数据验顺序。

## ⬜ L10 · 加载顺序

> 📗 复述型 ｜ 前置：L9 ｜ 不需要 web ｜ 预计 3–4 用例

**要回答**：条目在 YAML 里的先后，决定加载顺序吗？

📗 **不决定，而且官方在两处写明**：`dsh-base` 的 patch 文件里有原话
*"Row order carries no load semantics (activation is service-availability driven)"*；
`EntryGroup.update()` 的实现是 `Promise.allSettled(config.map(...))`——
**所有条目并发创建**，谁先 apply 由服务就位顺序决定。

**实验设计**：
- 让四个插件 apply 时各自往**同一个账本文件追加一行**（带时间戳），读出真实 apply 顺序
- 变体 A：按依赖顺序书写（registry → alpha → beta）
- 变体 B：**倒着写**（beta → alpha → registry）
- 断言：两种书写顺序下，**实际 apply 顺序一致**且都满足依赖先于被依赖

**难点**：并发写同一个文件要防交错——用「一条一个文件、按 mtime 排序」或追加时带序号，
别让观测手段自己引入竞态。

## ⬜ L11 · boot 审计与 PENDING

> ⚠️ 矫正型 ｜ 前置：L9 ｜ 不需要 web ｜ 预计 4–5 用例

**要回答**：依赖永远满足不了的条目，会怎样？**什么时候**会怎样？

⚠️ **这是典型的矫正型**。官方只说「如果服务还没准备好，你的插件会等着，不会执行」
（`zh/user/develop/framework/service.md:32`）——**只描述了运行期**。

**L0 实测**：boot 期永远等不到会**杀掉整个进程**。`dsh-app-boot` 的
`assertEntriesActivated` 在 boot 末尾审计每个未 disabled 的条目，非 ACTIVE 一律抛错：

```
dsh: plugin tree failed to load: dsh: 1 entry did not activate
l00-needy: pending (waiting for service: definitelyNotAService)
```

**本课要钉死的分界**：审计**只在 boot 期做一次**。boot 之后靠热重放新加的条目
卡在 PENDING，不会杀进程——那是完全另一条路径。
**「PENDING 致不致命」这个问题必须先问「什么时候」。**

**本课要补的**：
- 运行期插入一个永远 PENDING 的条目（依赖 L14 的热重放手段），确认它安静地待着
- `FAILED` 态：`apply` 抛异常与 PENDING 在审计里走的是两条分支
  （FAILED 会 `await fiber.await()` 取回原始 rejection）
- ⚠️ **`inject: ["loader"]` 会把插件锁死在 PENDING**——loader 的 intercept 契约里有
  `await?: boolean`：*"Keep dependent plugins pending while loader entries are still
  loading"*。插件自己就是 loader 的一个条目，于是等成死结，**且日志里一个字都没有**
  （PENDING 不是错误，没人为它报警）。解法是 `ctx.get("loader")` 运行时取。
  → 本课要把这个 intercept 的 await 语义测清楚：哪些服务有它？

## ⬜ L12 · 卸载连锁

> 📗 复述型 ｜ 前置：L9、L8 ｜ 不需要 web ｜ 预计 4–5 用例

**要回答**：被依赖者下线时，依赖方怎么办？

📗 **文档已写**（`zh/user/develop/framework/index.md:38`）：依赖的服务消失时插件
自动卸载（ACTIVE → DISPOSED），待服务恢复后**重新加载**。

**实验设计**：
- 禁用 `lab-registry` → 看 alpha / beta 是否跟着不 apply
- 二级链：只禁 alpha → beta 怎样（beta 同时依赖 registry 和 alpha）
- 账本（registry 提供的服务）在依赖方下线后是什么状态
- 🔬 **恢复方向**：服务重新出现后依赖方自动重载——这一半没测过

**与 L8 的分工**：L8 测**结构性**的禁用传播（父子层级），L12 测**服务性**的连锁
（谁依赖谁）。两者是不同维度，别混。

---

# 五 · 效果与清理
> **理解「热」的前提：卸载时到底清理了什么**

## ⬜ L13 · `ctx.effect` 与 disposer

> 📗 复述型 ｜ 前置：L9 ｜ **需要 web** ｜ 预计 3–4 用例

**要回答**：注册副作用（HTTP 路由）时不用 `ctx.effect` 包住，会怎样？

📗 **文档写得很全**（`zh/user/develop/framework/index.md:40-63`）：通过 `ctx` 做的
任何注册在卸载时自动撤销（事件监听、工具注册、LLM 适配器注册、`ctx.effect` 自定义资源）；
**处置器按注册顺序的逆序调用，但多个异步处置器并发执行、不保证逐个完成**；
有顺序依赖的清理必须放进同一个 `ctx.effect` 里自己串行等待。

`zh/cordis-api/fiber.md` 更精确：`ctx.effect()` 的 `execute` **立即运行**；
fiber 已 dispose 时调用抛 `CordisError('INACTIVE_EFFECT')`。

**实验设计**：
- 两个几乎一样的插件：`lab-effect-wrapped` 用 `ctx.effect` 包，`lab-effect-raw` 不包
- 都注册各自的路由并返回可辨认的 JSON
- 启动 → 两个路由都通 → 禁用两个条目 → 再查
- 预期：包的那个 404（**SPA 兜底 200，必须校验响应体**），不包的那个**仍然应答**

**为什么放在「热」之前**：热重载 / 热重放的本质就是「dispose 旧的 + 挂新的」，
而 dispose 到底清理了什么、清不干净会怎样，是理解所有「热」现象的前提。
L0 的普查员就踩过这个坑——`ctx.on("dispose")` 清掉定时器，导致它看不见自己被重挂。

**难点**：「禁用条目」在运行中做属于热重放（L14）。本课用**重启法**绕开
（启动一次、禁用后重启、对比），重点是 effect 语义不是重放机制。

**🔑 白捡的工具**：`fiber.getEffects()` 返回当前 fiber 上所有已注册 effect 的
元数据树（带 label，形如 `ctx.on("event")`）。本课正好是它的第一个使用场景，
**为 L17 打样**。

---

# 六 · 热
> **活着的树怎么变**

## ⬜ L14 · 配方热重放

> 🔬 发现型 ｜ 前置：L7、L13 ｜ 需要 web ｜ 预计 5–6 用例
>
> **这一部分的地基——必须先做扎实。** 后面三课的观测方法论全从这里长出来。

**要回答**：活层文件改动之后，究竟发生了什么？**什么会变、什么不该变？**

**L7 已立住的地基**：配方装在 `include` 的 `config.patches` 里，
所以热重放 = `entry.update({config})` 换掉 include 的 config，
**只重新 compose include 的子树**。

**假说**（源码 `entry.ts` 的 `update()`）：
- 改 `config` → `fiber.update(config)`
- 改 `name` / `inject` / `group` → 重新 import + dispose + 重建
- `null` → 删除该键
- 无差异 → 直接 return，空操作
- 整个重放是**条目级事务 diff**：只动变化的条目，失败整体回滚

⚠️ **「改 config 不动 fiber」这个假说已被观测台推翻**：fiber 对象保住了
（无 `fiber disposed` 事件），但状态实实在在走了 `ACTIVE → UNLOADING → LOADING → ACTIVE`
——**`ctx.effect` 注册的副作用被清理并重跑**。
📗 官方也是这么说的：`fiber.update()` = 「校验并应用新配置，**然后重新启动插件**」
（`zh/cordis-api/fiber.md`），且它**先跑 `internal/update` waterfall，
所以更新钩子（以及 HMR）可以否决或取代重启**——最后这半句对 L17 很关键。

**观测方法论（本课最重要的产出）**：
> **只有变化的那个条目会重挂。** 所以判断「重放是否发生」，观测信号必须落在
> **被改动的那个条目**上。拿一个无关条目的 `appliedAt` 判断重放有没有发生是错的
> ——它本来就不该变，得到的是恒真结果。
>
> ⚠️ 但「条目级 diff」的位置要往下挪一层：**每次重放所有条目的 options 都被
> 无差别替换一遍**（`loader/partial-dispose` 事件，`active: true`），只是 fiber 没动。
> 漏了这一类事件就分不清「条目没被碰」和「条目被碰了但 fiber 没动」。

**实验设计**（每个用例都用三个指纹交叉判定：`marker` / `moduleLoadedAt` / `appliedAt`）：

| 改什么 | 预期 `moduleLoadedAt` | 预期 `appliedAt` | 说明 |
|---|---|---|---|
| 该条目的 `config` | 不变 | **变** | 模块不重 import，但 apply 重跑 |
| 该条目的 `name` | 变 | 变 | 重新 import + 重建 |
| **无关的另一个条目** | 不变 | **不变** | ← 专门用来钉死观测方法论 |
| 文件改了但内容等价 | 不变 | 不变 | 无差异即空操作 |
| 把条目改成 `disabled` | — | 条目下线 | |

**难点**：「活层只活一轮」这个现象处于**「没测过」状态**——不是「已知不成立」。
它被观测到过，但那次的判定信号是错的（拿无关条目的 `appliedAt` 当指示器），
所以既没被证实也没被证伪。**若它在正确观测下复现，那是一个真正的重大发现**，
L17 全部推倒重来。

## ⬜ L15 · 代码热重载与快照面

> 🔬 发现型 ｜ 前置：L14 ｜ 需要 web ｜ 预计 4–6 用例

**要回答**：改插件代码会怎样？哪些东西被缓存住了、谁负责刷新？

**已验证**：
- 改 `apply` 期 `readFileSync` 读的文件 → **冷**，无任何反应（它从没进过 ESM loadCache）
- 改插件代码 → 热：模块重 import、apply 重跑，**这时那个文件才被重新读到**
- 插件在 hmr `root` 之外 → 冷
- **`root` 指向 `node_modules` 里的 junction 而非真实源码目录 → 冷**
  （hmr 默认忽略 `**/node_modules`，依赖遍历也跳过它）

**hmr 主 watcher 的四条分支**（源码，要逐条验）：

| # | 条件 | 动作 |
|---|---|---|
| 1 | 是某个 include 的 config 文件 | 刷新那棵子树 ← **就是 L14 的配方热重放** |
| 2 | 在 `externals`（CLI 入口的依赖树）里 | **`loader.exit()`——整个进程退出** |
| 3 | 在 Node 的 ESM `loadCache` 里 | **代码热重载** |
| 4 | 以上都不是 | 只 `emit('hmr/change', url)`——**没人接** |

⚠️ 第 4 条是「非 import 文件是冷的」的实现根因。**`hmr/change` 的语义是
「看到了但没处理」**，不是「检测到变化」——真正处理了的反而不发这个事件。

**新增要测**：第 2 条（`externals` 变动触发整个进程退出）——HMR 唯一一条主动重启的路，
只读过源码。

**要产出**：一张完整的**快照面**表（哪个缓存、什么时候拍的、谁负责刷新、热还是冷）。

## ⬜ L16 · client 双面插件

> 🔬 发现型 ｜ 前置：L14 ｜ **需要 web** ｜ 预计 5–6 用例

**要回答**：带浏览器端的插件怎么工作？为什么有的改动要重启、有的不用？

**已验证**：
- **推论 1 成立**：全新包名在实例运行中挂上去，**不重启**就进图、`client.js` 返回 200
  → 推翻「client 模块表是 boot 时快照」的说法。真实机制是**按包名增量扫描 + 永久负判缓存**
- **推论 2 成立**：先以「无 `dsh.client` 声明」形态挂载过的包，负判进缓存后补声明也没用，
  **必须重启**
- **附加推论被推翻**：「缺 `exports["./client"]` 是抛错而非缓存、补上不用重启」——
  三次干净复现证明**不成立**，行为与负判缓存一致。别指望这个逃生门

**新增要测**：client bundle 内容变化的热换链路（500ms stat 轮询 → 重算 sha1 → 换 rev
→ SSE 推浏览器）。这条没测过。

📗 **文档侧**：`zh/subsystems/client-modules.md` 是这一课的官方对照，**开课前先读**。

**别忘了**：`bundle` 一词二义——**profile bundle**（冷）与 **client bundle**（热）
恰好是热冷两极。这是整份教材要澄清的头号术语陷阱，在本课收口。

**教具**：`demo/lab-inspector` 就是按 client 插件样板写的，可直接复用。

## ⬜ L17 · hmr 自身的归属

> 🔬 发现型 ｜ 前置：**L14、L8、L13** ｜ 需要 web ｜ 预计 4–6 用例
>
> **全课程的收口。没有 L14 的观测方法论和 L8 的层级结论，这一课测不了。**

**要回答**：是谁在监听 patch 文件？它什么时候会死？

**已知机制**（源码，兜底部分 **L0 已实测证实**）：
- `profile-boot` 在 boot 末尾判 `ctx.get("hmr") === void 0`——**判服务不判条目**，
  服务不在就运行时创建一个 `root: []` 的兜底 hmr
- 然后 `watchUserPatches` 把 profile 活层和 home 层的监听注册上去，
  **且只在 boot 时调用这一次**，之后没有任何代码会重新注册
- `hmr.registerConfig()` 建立的 watcher，清理挂在 **hmr 插件自己的 fiber** 上
- → 推论：**hmr 条目一旦经历 dispose + 重建，patch 监听就永久没了**

**L8 提供的关键区分**（本课的实验设计完全依赖它）：

| | 位置 | 配方重放时 |
|---|---|---|
| 兜底的 hmr | 根组，与 include 平级 | 碰不到它 |
| 配方里的 hmr | include 子树里 | **可能被重挂** |

**真实部署多是后者，最小环境是前者**——所以「一处哑火、另一处正常」很可能根本
不是矛盾，是**两边测的不是同一个东西**。

**实验设计**（必须**单轮观测**）：
- 每轮改动前**重启实例**，一次只观测一件事，避免多轮改动互相干扰
- 场景 A：boot 时活层就有 hmr 反禁用条（配方拥有 hmr，在 include 子树里）
- 场景 B：boot 时没有（游离的兜底 hmr，与 include 平级）
- 关键一问：**只改 hmr 条目自己的 `config`（比如往 `root` 加一项），会不会导致
  patch 监听自断？**——而按 L8，这一问在两个场景下答案可能相反

**核心任务：把下面这条推论测实或证伪。**

1. patch 文件的 watcher 由 `hmr.registerConfig()` 建立，**挂在 hmr 自己 fiber 的 effect 上**
2. `watchUserPatches` 只在 boot 时调用一次，之后无人重新注册
3. → **任何改动 hmr 条目 `config` 的操作，都会让 patch 监听被自己清掉且不恢复**

而「往 hmr 的 `root` 里叠一项」在真实工具链里是很常见的操作。
有一条与之吻合、但**尚未被可靠观测证实**的现象：「哑火是永久性的，把 `root` 改回去
也救不回来」。它值得作为本课的一个待验假说。

⚠️ **一个可能推翻整条推论的线索**：`fiber.update()` **先跑 `internal/update`
waterfall，更新钩子（以及 HMR）可以否决或取代重启**（`zh/cordis-api/fiber.md`）。
如果 HMR 对自己的 config 变更做了特殊处理，上面第 3 条就不成立。**开课先查这个。**

### 🔑 决定性的观测工具：`fiber.getEffects()`

补读官方文档时白捡的（`zh/cordis-api/fiber.md`）：返回当前 fiber 上所有已注册
effect 的元数据树，带 label。

**「hmr 的 patch watcher 还在不在」以前只能间接测**——改 patch 文件、看有没有反应；
而没反应可能是 watcher 死了，也可能是别的环节出问题，**分不开**——
这种间接观测正是「数据整批不可判」最典型的成因。

现在可以**直接看** hmr fiber 上的 effect 列表。本课的实验设计据此重写。

---

## 三档与最短路径

```
基础  L0–L9    10 节   写插件、诊断日常问题
进阶  L10–L13   4 节   激活细节 + 清理语义
专家  L14–L17   4 节   热链路（观测最难，信号选错就整批不可判）
```

**基础为什么划在 L9**：

1. 跟官方自己的边界对齐——`user/develop/basic/` 四篇覆盖的范围，正好是 L1–L6
   加上 L9 的 `inject` 部分
2. 学完能回答日常三问：**插件为什么没加载**（L3）、**配置为什么被覆盖**（L5）、
   **加载了为什么没执行**（L9）
3. L10 起观测手段上一个台阶——前十节靠见证文件就够；L10 要比对时序、
   L11 要读退出码与审计判词、L13 要起 web 验路由泄漏、L14 之后必须挂观测台

### ⚠️ 依赖顺序与难度顺序在这里分叉

L7–L8（树）夹在 L6 和 L9 中间，但它俩其实比 L9 更「深」。
一个**只想写插件**的人需要 `inject`（L9），却未必需要知道幽灵条目和层级——
那两课是**诊断**用的，不是**开发**用的。

顺序本身没错（先有树才谈得上激活，这个依赖是真的），所以不改顺序，改成标一条路：

```
写插件最短路径：L0 → L1 → L2 → L3 → L4 → L5 → L6 → L9
诊断 / 研究再补：              ↘ L7 → L8 ↗
```

**L7–L8 首次可跳过**，遇到「`--dump-config` 和实际对不上」「改了 hmr 的 config
patch 监听就没了」这类问题时回头补——那时它们才有用武之地。

## 各课依赖与开销一览

| 课 | 部分 | 性质 | 前置 | 需要 web | 用例 | 状态 |
|---|---|---|---|---|---|---|
| L0 · 全景 | — | 🔬 | — | 否 | 12 | ✅ |
| L1 · 插件的最小形态 | 一 | ⚠️ | L0 | 否 | 8 | ✅ |
| L2 · 条目的字段 | 一 | 🔬 | L1 | 否 | 6 | ✅ |
| L3 · `name` 三条解析路径 | 一 | ⚠️ | L1 | 否 | 8 | ✅ |
| L4 · 空根 + 五层叠加 | 二 | 📗 | L2 | 否 | 6 | ✅ |
| L5 · patch 三种语义 | 二 | 📗🔬 | L4 | 否 | 9 | ✅ |
| L6 · bundle 层 vs 活层 | 二 | 📗🔬 | L5 | 是 | 3 | ✅ |
| L7 · 配方 ≠ 树 | 三 | 🔬 | L4、L0 | 否 | 6 | ✅ |
| L8 · 层级 | 三 | 🔬 | **L0** | 否 | 4 | ✅ |
| L9 · 服务与 `inject` | 四 | 📗🔬 | L7 | 否 | 8 | ✅ |
| L10 · 加载顺序 | 四 | 📗 | L9 | 否 | 3–4 | ⬜ |
| L11 · boot 审计与 PENDING | 四 | ⚠️ | L9 | 否 | 4–5 | ⬜ |
| L12 · 卸载连锁 | 四 | 📗 | L9、L8 | 否 | 4–5 | ⬜ |
| L13 · `ctx.effect` | 五 | 📗 | L9 | **是** | 3–4 | ⬜ |
| L14 · 配方热重放 | 六 | 🔬 | L7、L13 | 是 | 5–6 | ⬜ |
| L15 · 代码热重载 | 六 | 🔬 | L14 | 是 | 4–6 | ⬜ |
| L16 · client 双面插件 | 六 | 🔬 | L14 | **是** | 5–6 | ⬜ |
| L17 · hmr 自身的归属 | 六 | 🔬 | **L14、L8、L13** | 是 | 4–6 | ⬜ |

**基线**：一律用 `make_minimal_profile()`（`bundles: []`）。需要 web 的课才叠
`dsh-web-app`。观测手段能用见证文件解决的就别起 HTTP——起了就得借端口、等启动、
还多几百条无关事件。
