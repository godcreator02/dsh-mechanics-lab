"""standing-mount · 一个 preset 的组合被多少个 agent 共用

档次 ② ｜ 性质 ⚠️ 矫正型 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 需要 web

## 要验什么

**官方随发行版交付的文件里，对这件事的说法自相矛盾**——这是本项最值钱的地方，
它不是「文档与实现偏离」，是**同一个目录下的官方文件互相打架**：

- **`standard/agent.cordis.yml:1-18`**：roster 挂载它 **ONCE**，在一个
  **standing scope** 下，每个会话靠 scope 父子关系加入；共享 label **不**池化
  实例，同一 realm symbol 第二次 `provide()` 会抛
- **`code/agent.cordis.yml:12-26`**：它挂在**一个 agent 的 scope context** 下，
  `true` = 每个挂载的会话一份私有实例；共享 label **会**把一个实例池化给所有会话
- **`cordis/agent.cordis.yml`（persona 正文）**：「an agent preset is one such
  file **mounted for a single session**」

源码站 `standard` 那边，`ensureStanding()`（`dsh-agent-presets/lib/index.js:1129-1150`）：

    const pending = this.standing.get(preset.id);      // 按 preset.id 缓存
    const key = { agentPreset: preset.id };            // key 只含 preset id
    const scope = createScope(this.selfCtx, key);      // 从 selfCtx 派生

`module-resolution` 已经实测到 key 确实是 `{"agentPreset": "<id>"}`，但**「多个
agent 是不是真的共用同一批插件实例」还没验过**。

顺带要验的两条：

- **stamp 比对触发重挂。** 组合文件改了之后，已有的 standing 不动（旧 generation
  继续服务它的 agent），下一次 `ensureStanding` 发现 stamp 变了就丢弃缓存、
  挂一份新的——**两代并存**。这也解释了 `composeFrom` 为什么坚持让子 agent
  继承父的 generation 而不是按 id 重解析。
- **`recompose()` 只在 agent 什么都没产出时可用**，且是「parent 重新链接」
  而不是卸载重挂：旧组合留给它的其他 agent。

## 为什么还没验

需要**同时存在两个 agent**才能验「共用」，而本组前三项都用 `standingKeyFor()`
绕开了建会话。要么找到建会话的路（`session.selectModel` 那套 RPC 的 wire 形状
没有公开文档），要么让探针在同一个 standing scope 下做两次 ensure 并比对实例
身份。

## 实验设计要点

- 最省事的路子：教学插件在 `apply` 里生成一个模块级唯一 id 并写进见证文件；
  对同一个 preset 连续 `standingKeyFor()` 两次，见证文件**只多一行**就说明
  第二次吃的是缓存
- 真要验「两个 agent 共用」，得先解决建会话的观测面，见 `preset-vs-host-plane`
  里记的那条思路
- stamp 那条：ensure 一次 → 改组合文件 → 再 ensure → 见证文件应当多出一行，
  且两行的实例 id 不同（两代并存）
- ⚠️ 本项与其他项**必须用独立的 preset id**：standing mount 按 id 缓存且永久，
  共用 id 会让别的用例吃到本项挂出来的那一份
"""
