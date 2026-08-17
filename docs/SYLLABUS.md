# 覆盖清单

DSH 插件系统有哪些机制、每个机制归哪一组、由哪个实验项负责、验没验过、该先做还是后做。

**这份文件只做索引。** 每一项的判定、证据出处、观测方法住**那一项自己的
`test_*.py` 模块 docstring**——判定跟着代码走，这里不复述，改结论只改那一处。

## 怎么读这张表

两条正交的轴，各管各的：

- **组**回答「这个机制归谁管」——一个机制一个家。组编号只提供稳定排序，不表示依赖
- **档**回答「什么时候做它」——标在项上，不标在组上

| 档 | 含义 | 谁会撞上 |
|---|---|---|
| ① | 天天碰 | 写插件、装插件、改完要生效 |
| ② | 要懂才用得好 | 想让结果可预测、想知道改一处波及多远 |
| ③ | 深水区与边界 | 造服务的人；出了事回头查的人 |

| 状态 | 含义 |
|---|---|
| ✅ | 有用例、跑绿 |
| ⚠️ | 主判定成立但有明确缺口，缺什么写在那一项的 docstring 里 |
| ⬜ | 没有用例。目录里只有一个**光有 docstring、没有用例函数**的 `test_*.py`，写清要验什么、为什么还没验、实验设计要点 |

⬜ 项照样占位：**这张表是覆盖清单，不是完工清单**。没进表的机制才是真的漏了。

各项 docstring 里还标着**性质**（📗 复述型 / 🔬 发现型 / ⚠️ 矫正型），它决定用例的
断言强度——对照式直接断言文档承诺的行为，观察式先如实记录再下判定，失败时的含义
完全不同。**开工第一件事是 grep `docs/official/` 定性质。**

---

## 00 base · 底座

测的是后面每一项站在什么上面：被观测的最小环境是什么形状，观测它的仪器能信到什么程度。

| 项 | 档 | 状态 |
|---|---|---|
| `recorder-reach` | ① | ✅ |
| `minimal-profile` | ① | ✅ |
| `framework-fallback` | ① | ⚠️ |
| `baseline-profile` | ① | ✅ |
| `isolation-guarantees` | ② | ⬜ |

## 01 entry · 条目

| 项 | 档 | 状态 |
|---|---|---|
| `field-vocabulary` | ① | ✅ |
| `config-delivery` | ① | ✅ |
| `disabled` | ① | ✅ |
| `name-resolution` | ① | ✅ |
| `apply-runs` | ① | ✅ |
| `inject-field` | ② | ✅ |

## 02 recipe · 配方怎么叠出来

| 项 | 档 | 状态 |
|---|---|---|
| `layer-stack` | ① | ✅ |
| `insert-semantics` | ① | ✅ |
| `override-semantics` | ① | ✅ |
| `cross-layer-targeting` | ② | ✅ |
| `dump-fidelity` | ② | ⚠️ |

## 03 supply · 插件从哪来

| 项 | 档 | 状态 |
|---|---|---|
| `four-ways` | ① | ✅ |
| `self-registration` | ① | ✅ |
| `pinned-worktree` | ① | ✅ |
| `supply-x-activation` | ② | ✅ |
| `install-command` | ② | ⚠️ |
| `client-side` | ③ | ⬜ |

## 04 replay · 配方热重放

| 项 | 档 | 状态 |
|---|---|---|
| `replay-mechanism` | ① | ✅ |
| `cold-surfaces` | ① | ✅ |
| `replay-granularity` | ② | ⬜ |

## 05 reload · 代码热重载

| 项 | 档 | 状态 |
|---|---|---|
| `watch-root` | ① | ✅ |
| `ignore-rules` | ① | ✅ |
| `reload-unit` | ① | ✅ |
| `new-code-old-config` | ① | ✅ |
| `reload-debounce` | ② | ✅ |
| `reload-while-busy` | ② | ✅ |
| `cold-reads` | ② | ⬜ |
| `client-swap` | ③ | ⬜ |
| `hmr-self` | ③ | ⬜ |

## 06 inject · 用别人的服务

写插件天天写的那一半。**造**服务归 08。

| 项 | 档 | 状态 |
|---|---|---|
| `inject-hard-dependency` | ① | ✅ |
| `activation-order` | ① | ✅ |
| `dependency-chain` | ② | ✅ |
| `teardown-chain` | ② | ⬜ |

## 07 tree · 运行时的树

官方文档在这一层是空白的——`user/develop/` 讲「怎么写插件」，不讲「框架怎么加载插件」。

| 项 | 档 | 状态 |
|---|---|---|
| `recipe-vs-tree` | ② | ✅ |
| `hierarchy` | ② | ✅ |
| `disabled-propagation` | ② | ✅ |
| `entries-order` | ② | ⬜ |

## 08 service-core · 自己造服务与副作用

cordis 的运行时内核。写插件的人用它的产物，造框架件的人才动它。

| 项 | 档 | 状态 |
|---|---|---|
| `provide` | ③ | ✅ |
| `one-owner` | ③ | ✅ |
| `registry` | ③ | ✅ |
| `availability-contract` | ③ | ✅ |
| `isolate` | ③ | ⚠️ |
| `leak-on-reload` | ③ | ✅ |
| `module-state-reset` | ③ | ✅ |
| `effect-vs-raw` | ③ | ⬜ |
| `disposer-order` | ③ | ⬜ |
| `effect-inventory` | ③ | ⬜ |

`provide → one-owner → registry → availability-contract` 是一条论证链，每项的 docstring
点名相邻那项、不复述它的结论。

## 09 boot-vs-runtime · 同一件事，两个时机两种下场

不是失败的杂物抽屉，它有自己的机制内核：**同一种反常，启动期与运行期的处置完全不同**。
「致不致命」这个问题必须先问「什么时候」。

| 项 | 档 | 状态 |
|---|---|---|
| `boot-audit` | ③ | ✅ |
| `boot-failure-shapes` | ③ | ✅ |
| `duplicate-id-timing` | ③ | ✅ |
| `pending-timing` | ③ | ⬜ |
| `loader-self-deadlock` | ③ | ⬜ |
| `externals-exit` | ③ | ⬜ |

---

## 一档往前排的代价

三档的 `boot-audit` 与 `boot-failure-shapes` 排在最后，但一档的实验先用得上它们——
任何一项判「这次跑挂了」，都要认得出启动失败长什么样：退出码、判词、以及
「一条挂不上整树陪葬」这个前提。

所以一档实验里对启动失败的判断按**已知结论**用，不在那些项里重新论证；
到 09 组开工时再坐实并回填。这是排序换来的代价，不是漏洞，但它意味着
**09 组一旦推翻某条前提，前面引用过它的项要跟着复核**。

## 跑法与开销

```powershell
uv sync                                          # 首次或依赖变更后
uv run pytest                                    # 全套
uv run pytest -m static                          # 只跑不起进程的
uv run pytest experiments/01-entry/              # 单跑一组
uv run pytest experiments/01-entry/disabled/     # 单跑一项
uv run pytest experiments/01-entry/disabled/ -n 0   # 关掉并行，看清教学输出或用 pdb
```

端口段 3090–3099 是硬边界，扩不了。项数远超 worker 数，所以**用端口的项打
`xdist_group` 标记**钉在固定 worker 上；不用端口的项随便分。不做「取模复用端口」。

基线一律用 `make_minimal_profile()`（`bundles: []`，但显式带上 timer 与 hmr）。
需要 web 的项才叠 `dsh-web-app`——它很重，能用见证文件解决的就别起 HTTP。

归档落 `<实验目录>/results/<时间戳>/`，每项留最近三次，整个 `results/` 不进 git。
假 home 在 `out/testhome/<项名>/`，跑前清空重建。
