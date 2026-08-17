"""preset-vs-host-plane · 同一个包为什么在两个平面各有一行

档次 ① ｜ 性质 🔬 发现型 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 需要 web

## 要验什么

静态比对已经做过（读 bundle patch 文件 + 四个 shipped preset），结论待实测坐实：

- **`standard` preset 的 23 个包里有 21 个在 host 平面也有一行**，只有
  `dsh-persona` 与 `dsh-tool-ask-user` 是 preset 独有。`minimal` 的 6 个里只有
  `dsh-tool-str-replace-editor` 重合。
- **重合的那些在 host 侧是被禁用的。** `dsh-base` 的单个 `- insert:` 块平铺 78 行，
  里面就含一整套面向模型的工具（`tool-fs` / `tool-bash` / `plan-mode` /
  `compaction-*` / `tool-subagent-*` …）；`dsh-web-app` 再用 patch 按 id 把其中
  **24 条**逐个 `disabled: true`。
- **那套 host 侧的工具是给 rosterless 部署兜底的。** 官方注释（`composeFrom`
  的 JSDoc）说「a rosterless deployment … the model-facing rows sit in the host
  composition」。`dsh-headless` 只有 6 行、3 个覆盖，正是那种部署——它不禁这些。
- ⚠️ **待验的关键推论**：`disabled: true` 只管住 base 自带的那 24 行。往 host
  平面**新加**一个注册全局工具的插件，没有任何机制阻止它对所有 preset 可见——
  包括 `minimal`。也就是说「minimal 只有两个工具」是当前配置凑出来的状态，
  **不是 preset 机制维持的不变量**。

## 为什么还没验

**缺一个能读到「某个 agent 的工具目录」的观测面。** 前三项都用
`standingKeyFor()` 绕开了建会话，但工具目录是 agent scope 的东西：
`ctx.tools.schemas(scope)` 要传 ScopeKey。

`standingKeyFor()` 返回的正是那个 key，所以**可能不用建会话**——探针拿到
standing key 之后直接 `ctx.tools.schemas(key)`，对比传 key 与不传（全局视图）
的差集。这条路没试过，是本项开工第一件事。

## 实验设计要点

- 正向：起 web profile，探针分别读「全局视图」与「minimal 的 standing scope
  视图」，对比两份工具名清单
- 反向（那条待验推论）：往 profile 活层 insert 一个注册全局工具的教学插件，
  再看 `minimal` 的 scope 视图里出不出现它。出现即坐实「preset 挡不住 host
  新加的全局工具」
- ⚠️ 别拿 `--dump-config` 取证：`preset-discovery` 已坐实 dump 与 boot 是两条
  独立的合成实现，而且工具注册根本不在配置树上
"""
