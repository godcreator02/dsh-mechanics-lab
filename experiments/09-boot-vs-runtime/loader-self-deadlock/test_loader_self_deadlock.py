"""loader-self-deadlock · 依赖 loader 服务，等成死结

档次 ③ ｜ 性质 🔬 发现型 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 不需要 web

## 要验什么

`inject: ["loader"]` 会把插件自己锁死在 PENDING，而且**日志里一个字都
没有**。

机制（只读过源码，待实测坐实）：`cordis-plugin-loader` 的 intercept 契约
里有 `await?: boolean`，注释原话是 *"Keep dependent plugins pending while
loader entries are still loading"*。插件自己就是 loader 管理的一个条目
——声明依赖 `loader` 服务，等于让 loader 等自己名下的条目都不再 LOADING
才放行，而自己正是那个还没放行、卡在 LOADING/PENDING 的条目之一，于是
等成一个死结。

这跟本组其它项不是同一种「致命」：`boot-audit` 里的 PENDING 会被 boot
末尾的审计抓出来、判死刑、退出进程；这里的死结**连审计都等不到**——
它不是「等不到服务然后被判定失败」，是「永远等不到，也永远不会被判定」。
PENDING 本身不是错误，没有任何机制会为一个安静等待中的条目报警。
解法是运行时 `ctx.get("loader")` 取，不写进 `inject` 声明。

**实验台自己踩过这个坑。** `observatory/lab-recorder/index.js` 的采集器
零 inject（只订阅事件、写文件用 `node:fs`），文件头的设计约束里点名了
反面教材：

> 反面教材：lab-inspector 因为 inject 了 loader，被 loader 的 await 语义
> 锁死在 PENDING —— 见 demo/README.md。

采集器起点快照那段同样是绕开这条坑的证据（`observatory/lab-recorder/index.js`
第 297 行注释）：

> 用 ctx.get 运行时取 loader，**不写进 inject** —— loader 的 intercept 有
> await 语义，声明依赖它会把本插件锁死在 PENDING。

## 为什么还没验

需要先起一个实例、挂一个 `inject: ["loader"]` 的条目、观察它卡死后
**日志与事件流双双沉默**这件事——判定的难点恰恰在于「没有任何信号」，
需要设计一个能反向证明「死结确实发生了」而不是「只是还没轮到」的观测
手段（比如同时挂一个正常条目做时间对照、或者直接读 fiber 状态确认它
停在 LOADING 而非 PENDING）。取材表没有列出对应的旧用例，判定目前只有
源码引用，**未覆盖**，不代造用例。

## 没覆盖到的

- 死结发生时条目的 fiber 状态到底是 LOADING 还是 PENDING（intercept 的
  await 语义具体挂在哪个状态转换上），源码没有直接引用到具体行号，
  待实测时一并钉死。
- 哪些服务除了 `loader` 之外也带这个 `await` intercept 契约，没有清单
  ——旧版大纲留了一句「本课要把这个 intercept 的 await 语义测清楚：
  哪些服务有它」，本项取材范围里没有对应实验，点名记在这里。
"""
