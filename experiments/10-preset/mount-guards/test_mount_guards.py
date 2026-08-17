"""mount-guards · preset 挂载期的三道拒绝

档次 ② ｜ 性质 📗 复述型（源码） ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 需要 web

## 要验什么

`mountPreset()`（`dsh-agent-presets/lib/index.js:707-723`）在挂完之后逐道检查，
任何一道不过就整个 mount 失败、agent 创建回滚。三道各有自己的文案：

- **没有 scope**——`refusing to mount preset "<id>" into an unscoped context;
  its registrations would apply to every agent in the process`
- **有行没激活**——`<N> row(s) did not activate:` 加逐行清单（`inactiveRows()`）。
  这正是 `capability-seams.md:439` 说的「拒绝始终未激活的行」
- **服务发到了根 realm**——`row(s) published process-global service(s) [<名>];
  a preset service must sit behind an \\`isolate\\` realm or move to the host
  composition`（`leakedServices()`）。错误消息**自己给出两条出路**

第三道是「preset 里的服务必须藏在 isolate realm 里」这条判定的执行层依据，
也是 `capability-seams.md:439` 那句「拒绝向根服务 realm 发布服务的行」的正身。

## 为什么还没验

不难，只是排在①档后面。三道都能用 `standingKeyFor()` 触发（`module-resolution`
已经趟通那条路），教学插件按需造：一个 inject 永远等不到的服务（触发未激活）、
一个裸 `provide` 不带 isolate（触发根 realm 泄漏）。

第一道（无 scope）从外部触发不了——`ensureStanding()` 自己 `createScope()`，
调用方拿不到「没有 scope 的 ctx」。这一条只能留在源码层，或者由 `isolate-realm`
项从另一侧覆盖。

## 实验设计要点

- 未激活那道：教学插件写 `export const inject = ["no-such-service"]`，它会一直
  等、永不激活
- 根 realm 泄漏那道：教学插件 `ctx.provide("labLeak", …)`，preset 里**不**给它
  套 `cordis:group` + `isolate`
- 对照组：同一个插件套上 `isolate: {labLeak: true}` 之后应当挂得上
- ⚠️ 三条各用独立 preset id（standing mount 按 id 缓存）
"""
