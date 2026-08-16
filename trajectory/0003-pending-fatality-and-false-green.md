# PENDING 致命性悬案与用例的假绿

> 了断于 2026-08-16 ｜ 推翻 ｜ 冻结

## 背景

DSH 的插件在依赖的服务没就位时会停在 `PENDING` 态。做教具时撞见过一次：
`inject` 一个从不存在的服务名，实例直接启动失败（fail loud）。后来 L9（服务与
`inject`，当时编号 L3）做同一件事，却观察到「实例照常启动，那个条目只是被
DISPOSED 掉了」。

两次结果相反，当时把差异归到**bundle 组合**上——教具那次叠了 `dsh-web-app`，
L9 那次只叠 `dsh-base`——并据此在课程大纲里写下「『boot 期 PENDING 致命』要带
上条件，不能当通则用」，这个「待查」挂了两课。

## 结论与边界

**boot 期的 PENDING 无条件致命，跟 bundle 组合毫无关系。** `dsh-app-boot` 的
`assertEntriesActivated` 在 boot 末尾审计每个未 disabled 的条目，非 `ACTIVE` 一律
抛错，进程以退出码 1 退出。

边界：**这条只管 boot 期**。审计只在 `boot()` 返回前跑一次；boot 之后靠热重放新加
的条目卡在 PENDING **不会**杀进程——那是另一条路径，本次没测（归后续的热重放课）。

「L9 那次照常启动」这个观察本身是假的：**用例根本没在检查进程死没死**。

## 经过

复核从跑全套测试时的结论打架开始：L0 新做的用例断言「PENDING 致命、退出码 1」
通过，而 L9 既有的用例打印「启动成功」——同一件事两个相反结论同时为绿。

查 L9 那个用例，问题在这段：

```python
try:
    inst = launch(profile, wait_http=False)
    time.sleep(5)
except LabError:
    outcome = "启动失败"
```

`start_instance(wait_http=False)` **立即返回，不做任何存活检查**（源码：
`experiments/lab/instance.py`，`wait_http` 为假时直接 `return inst`）。那个
`except LabError` 永远不会触发，两个变体因此双双落进「启动成功」分支。

改成直接看 `inst.alive()` 之后，两个变体都是**退出码 1**：

```
[提供者被禁用]   → 启动失败（退出码 1）
[服务名从不存在] → 启动失败（退出码 1）
Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate
lab-alpha: pending (waiting for services: labRegistry, 从来没有人提供过这个服务)
```

物证：修正后的用例与输出在 commit `ee7d251`，归档在
`results/l09-20260816-034145/summary.md`。

## 依据

审计代码遍历每个未 disabled 的条目，`state !== ACTIVE` 就记进 failures：

```js
if (state === FIBER_PENDING) {
  const missing = Object.keys(fiber.inject).filter(s => fiber.ctx.get(s) === undefined)
  failures.push(`${name}: pending (waiting for ${subject}: ${missing.join(", ")})`)
}
```

条件里没有任何与 bundle 组合相关的分支——「叠了什么 bundle」根本进不了这段判断。

那么教具那次和 L9 那次为什么看起来不同？**它们其实相同**，都是启动失败。
差别只在观测：教具那次是人眼看到进程退出，L9 那次用例没检查存活。

## 否掉的候选

- **「差异在服务名是否有被禁用的提供者」** —— L9 的用例 7 就是为隔离这个变量设计的，
  两个变体（提供者被禁用 / 服务名从不存在）跑出来行为一致。这条被自己的实验否掉了，
  但因为整个用例的判定是坏的，当时得出的「一致」是「一致地假绿」
- **「差异在 bundle 组合」** —— 死在源码上：审计逻辑里没有任何与 bundle 相关的分支

## 代价与遗留

这个错误结论在课程大纲里挂了两课，期间写的每一处「PENDING 有条件致命」都要回改。

更贵的代价是**观测数据被误读**：事件流里那条 `PENDING → UNLOADING → DISPOSED`
当时被读成「条目等超时被放弃，所以审计无话可说」，实际它是 `boot()` 失败后
catch 里 `ctx.fiber.dispose()` 的**整树回滚**——一直是启动失败的证据。

同一份观测数据，缺了「进程还活着吗」这一个最粗的对照，读出了完全相反的结论。

遗留：`start_instance(wait_http=False)` 的这个陷阱已写进函数 docstring 的警告段，
但**没有从 API 上堵死**——它仍然可能被下一个人以同样的方式误用。彻底的修法是让
`wait_http=False` 也做一次短暂的存活检查，未实施。
