"""isolate-realm · isolate 到底隔离了什么

档次 ③ ｜ 性质 ⚠️ 矫正型 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 需要 web

## 要验什么

realm 的正身在 `cordis-plugin-loader/src/config/isolate.ts:25-68`（这个包**带
TS 原文件**，别读打包产物）：

    /** Symbol realm used to isolate service implementations by entry or label. */
    export abstract class Realm { protected store: Dict<symbol> …; abstract get suffix(): string }
    export class LocalRealm  extends Realm { get suffix() { return '#' + this.entry.options.id } }
    export class GlobalRealm extends Realm { get suffix() { return '@' + this.label } }

**realm 就是服务名到 symbol 的一层命名空间映射**，`isolate: {x: true}` 给名字
加 `#<entry id>` 后缀、`isolate: {x: "label"}` 加 `@<label>`。由此推出三条待验：

- **方向是单向的**：realm 内解析得到外面（根 realm）的服务，外面解析不到 realm
  内的。`minimal` preset 的注释「the backend still consumes the host sandbox
  policy and subprocess implementation」正是这个意思——realm 管发布，不管消费
- **同名遮蔽**：realm 内 provide 一个跟 host 同名的服务，realm 内的消费者拿到
  自己那份。`minimal` 用 `isolate: {fs: true}` 把 host 的沙箱 fs 换成裸
  `fs-local`，注释说得很直白：`shadows the host's sandboxed provider`
- **⚠️ 共享 label 不池化实例**：`GlobalRealm` 同 label 共用同一个 Realm 对象 →
  同一个 symbol → 第二次 `provide()` 直接抛。`standard/agent.cordis.yml` 的注释
  说的正是这个（「labels join REALMS」），而 `code/agent.cordis.yml` 说「A shared
  label would instead pool one instance across every session」——**两句不可能
  都对**，源码站前者。这条与 `standing-mount` 项是同一场矛盾的两个侧面

## 为什么还没验

③ 档，排在最后。而且要验「外面看不见 realm 内」需要一个 realm 外的观测者去
解析同一个服务名——探针本身住 host 平面，正好可以充当那个观测者。

## 实验设计要点

- 教学插件 provide 一个带指纹的服务；preset 里套 `isolate: {labProbe: true}`
- realm 内的观测：同一个 preset 里再挂一行消费者，它 `ctx.get("labProbe")`
  应当拿到那个指纹
- realm 外的观测：host 平面的探针 `ctx.get("labProbe")` 应当拿不到；
  但 `ctx.agentPresets.serviceFor(agent, "labProbe")` 应当拿得到——那是官方给
  外部读 preset 服务的唯一通道，**且只读**
- 共享 label 那条：两个条目声明同一个 label 并都 provide 同名服务，
  预期第二个抛错。若反而池化成一个实例，`standard` 的注释就被推翻了
- ⚠️ `serviceFor()` 要一个 agent，而本组前几项都没建会话——这条可能得等观测面
"""
