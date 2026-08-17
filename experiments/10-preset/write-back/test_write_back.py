"""write-back · 为什么 preset 文件不会被运行时改写

档次 ③ ｜ 性质 🔬 发现型 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 不需要 web

## 要验什么

Loader 有 tree write-back：它认为 config 变了就把整棵树写回源文件，而**插件自我
dispose 就足以触发**。同一个机制，两个平面用了**完全相反**的对策：

- **profile**：接受写回，靠每次启动把 `cordis.yml` 无条件重写成 `[]` 兜底
  （本仓已实测，见 `docs/GLOSSARY.md` 的 🟨 profile 节）
- **preset**：**直接把 `write()` 覆盖成空函数**
  （`dsh-agent-presets/lib/index.js:523`）

`PresetTree.write()` 的 JSDoc 写了不禁掉的后果：

    Inherited, that rewrites the preset file with whatever the dying tree held,
    which in practice means truncating a shipped composition to `[]` the first
    time a session ends.

**第一个会话结束就会把 shipped 组合截断成 `[]`**——这是个具体到可怕的失败模式，
值得一条用例把「现在确实不会发生」钉死。

同一段注释还回答了另一个常问的问题：

    a future "edit your preset while it runs" flow needs a deliberate
    persistence path rather than this method's return.

——**运行中编辑 preset 目前不支持**。配合 `standing-mount` 项的 stamp 比对，
完整图景是：已有会话不受影响，新会话拿新版，但没有任何东西会把改动写回文件。

## 为什么还没验

③ 档。而且触发条件要绕一下：得让一个已挂载的 preset 子树被 dispose，才能看出
写回有没有发生。

## 实验设计要点

- 起手先记下 `agent.cordis.yml` 的字节内容与 mtime
- `standingKeyFor()` ensure 一次，再想办法让那棵子树 dispose——教学插件自己调
  `ctx.scope.dispose()` 是最直接的触发方式（JSDoc 明说「a plugin self-disposing
  is enough」）
- 断言文件内容与 mtime 都没变
- **不需要 web**：不涉及 HTTP 观测面，见证可以直接落文件。但 `agent-presets`
  条目住在 `dsh-web-app` 里——要么叠 web bundle，要么在最小基线上自己 insert
  一行 `agent-presets`（后者更快，且能顺带验「这一行不依赖 web-app」）
"""
