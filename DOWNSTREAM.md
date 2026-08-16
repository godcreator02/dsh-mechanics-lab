# 下游校准清单

本实验台研究 DSH 框架本身，**dshw 是它下游的一个消费者**。这里记 dshw 需要按哪些
结论校准自己——与原理讲解分开，教材正文不混进 dshw 视角。

反过来不成立：dshw 的做法对不对是结论出来之后的事，不是实验的出发点。

## 已可执行

这几条已有实测支撑，dshw 可以直接改。

### `config` 是整字段替换，不是按键 merge

`attach` 写 hmr 条目的账本块时，**必须每次写全** `base` / `debounce` / `root`——
只写改动的那个键会让其余键消失。

dshw 的 `CLAUDE.md` 记的是「按键 merge」，与官方原文相反
（`docs/official/zh/user/develop/basic/publish.md:123`：「patch 会替换目标行的整个
`config` 值，而不是深度合并各键」）。

### home 级 patch 层存在且优先级压过 profile 活层

`$DSH_HOME/cordis.patch.yml` 是共享 home 部署下**全实例的公共上游**。
dshw 的文档完全没记载这一层，需补；并明确 dshw 不碰它。

层序是 bundle → profile 活层 → home 层 → `--patch` overlay，后者胜出。

### client 模块表不是 boot 快照

`design.md` 写的「client 模块表是实例 boot 时的快照」不成立。真实机制是
**表的成员增量热维护，包元数据按名惰性缓存且永不过期**。

连带一条：「缺 `exports["./client"]` 是抛错而非缓存、补上不用重启」也不成立，
行为与负判缓存一致。写作契约里不能留这个逃生门。

### watch root 必须指真实源码目录

不能指 `node_modules` 里的 junction——hmr 默认忽略 `**/node_modules`，依赖遍历
也跳过它。这条是承重设计，dshw 现有做法正确，记录在此以防被误改。

## 待验证后再动

这几条已经知道 dshw 的记载有问题，但**替代结论还没实测坐实**，先不改。

### 「hmr 条目没在启动时启用的进程，patch 文件改了没人看」

与源码对不上。`profile-boot` 在 boot 返回后判 `ctx.get("hmr") === void 0`——
判的是**服务**不是条目，服务不在就补一个 `root: []` 的兜底 hmr，patch 监听照常
建立。dshw 那次观察另有原因。

### 「靠活层反禁用 hmr 来启用活层是鸡生蛋」

由上一条派生，同样要重查。兜底 hmr 一直在，活层从来就是活的。真正的区别只是
**兜底那个 `root: []` 不监听代码文件**——所以代码热重载不工作、而 patch 热重放工作。
这两件事在 dshw 的记载里可能被混成了一件。

### 两种 hmr 的处境相反

这条是 dshw「patch 监听哑火」问题最可能的根源。

| | 位置 | 配方重放时 |
|---|---|---|
| 兜底的 hmr | 根组，与 `include` 平级 | 碰不到它，watcher 稳 |
| 写在配方里的 hmr | **`include` 子树里** | **可能被重挂，watcher 随 effect 一起清掉** |

dshw 的场景是后者（web bundle 的 hmr 条目 + 活层反禁用），而本实验台的最小环境是
前者。**两边测的可能根本不是同一个东西。**

`dshw attach` 每挂一条分发线，干的正是「往 hmr 的 `root` 里叠一项」——按上表，
那是在动一个住在 include 子树里的条目。

⚠️ 有一条可能推翻整个推论的线索：`fiber.update()` **先跑 `internal/update`
waterfall，更新钩子（包括 HMR 自己）可以否决或取代重启**
（`docs/official/zh/cordis-api/fiber.md`）。如果 HMR 对自己的 config 变更做了特殊
处理，「改 hmr config 会自断 patch 监听」就不成立。动手前先查这个。

### 同 id 双挂载的后果分两种

dshw 的记载是「该次热重放整体事务回滚」。准确说法分两层：

- **不是回滚，是提前整批拒绝**——查重循环在 `try` 块之外，抛错时一个 `create()`
  都还没调用，旧组合原封不动
- **撞的时机决定后果**：撞在**首次 boot** 是整个进程启动失败（退出码 1）；
  撞在**运行中热重放**才是「日志一条警告、这次重放作废、旧条目继续跑」

dshw 描述的是后者，但没说清前者会直接起不来。
