# L9 · 服务与 `inject`

> 8 个用例 ｜ 约 55 秒 ｜ 不需要 web ｜ 📗 复述型 + 🔬 发现型 ｜ 前置：L7

**这一课回答：** 谁提供服务、谁依赖它、**依赖没到位时会怎样**。

跑法：`uv run pytest experiments/l09_service_inject/`

> 本课排在「树」之后：**先有树，才谈得上树上的条目怎么激活。**

📗 **文档已写明的**（`docs/official/zh/user/develop/framework/service.md`）：
`inject` 是硬依赖、服务消失时依赖方自动 dispose、服务恢复后自动重载。

🔬 **文档没写、本课测出来的**：条目级 `inject` 是**补充不是覆盖**；
另有一种**包级**声明（`package.json` 里的 `@deepseek-ai/cordis.services.required`，
hmr 包就是这么声明它依赖 timer 的）。

---

## 一、三个插件构成的依赖链

```
lab-registry  ←──  lab-alpha  ←──  lab-beta
提供 labRegistry    登记 + 提供       登记（要两个服务）
（不依赖任何人）     labAlpha
```

账本（`labRegistry` 提供的那个对象）**每登记一笔就整份落盘**，
所以见证文件里的顺序就是**真实的 apply 先后**——L9 用它验依赖，L10 用同一份数据验顺序。

## 二、实测结论

### 1. `inject` 是硬依赖：服务没到位，`apply` 根本不执行

把 `lab-registry` 禁用之后，`lab-alpha` 的见证文件**不出现**——不是「apply 了但拿到
undefined」，是**压根没 apply**。

### 2. 依赖永远满足不了时，条目在 PENDING 里等到 boot 审计，然后**整棵树陪葬**

装上观测台直接看 fiber 状态，这是完整的一生：

```
+  1.861ms  snapshot  fiberState=PENDING  hasFiber=True
+169.677ms  fiber disposed
+169.769ms  PENDING → UNLOADING
+176.033ms  UNLOADING → DISPOSED
```

**它先进 PENDING 等，然后在 boot 末尾（约 +170ms）被销毁——但销毁它的不是
「等超时了放弃」，而是 `boot()` 失败后的整树回滚**（catch 块里
`await ctx.fiber.dispose()`）。进程随即以退出码 1 退出。

⚠️ **这条状态链极易被读反**——见第三节的陷阱二。

### 3. 条目级 `inject` 不会削弱代码里的声明

`lab-alpha` 代码里声明了 `inject = ["labRegistry"]`，条目上再写 `inject: []`（空）：

- 组合树里条目的 `inject` 确实是 `[]`（`--dump-config` 可见）
- 但插件**照常等到服务就位才 apply**

所以条目级 `inject` 是**补充**，不是**覆盖**。想靠它绕开代码里的依赖声明是行不通的。

### 4. 书写顺序不决定加载顺序

把依赖链**倒着写**（`beta` → `alpha` → `registry`），实际 apply 顺序仍是
`lab-alpha` → `lab-beta`。

依据在 `EntryGroup.update()`：所有条目走 `Promise.allSettled(config.map(...))`
**并发创建**，谁先 apply 由服务就位顺序决定。`dsh-base` 的 patch 文件里那句
*"Row order carries no load semantics (activation is service-availability driven)"*
在这里被直接验证。（L4 会深入展开。）

### 5. 部分依赖满足也一样拦

只禁用中段 `lab-alpha`：`lab-beta` 要 `labRegistry` + `labAlpha` 两个，
拿到了前一个、缺后一个——照样**不 apply**。依赖是全有全无，不是能拿多少算多少。

## 三、⚠️ 本课第一版在这里栽了个大跟头（L0 复核推翻）

> 下面这段保留了错误的推理过程，因为**它比结论本身更有教学价值**。

早先做教具时观察到：`inject` 一个**从不存在的服务名**会让 boot 直接 fail-loud。
本课用例 7 复现同样的情形，却打印出「启动成功」，于是当时写下：

> 差异不在服务名，剩下的唯一变量是 **bundle 组合**——教具那次叠了 `dsh-web-app`，
> 本课只叠 `dsh-base`。「boot 期的 PENDING 是致命的」要带上条件，不能当通则用。

**整段是错的，而且错在实验设计，不在推理。**

用例 7 靠 `except LabError` 判断启动失败，可 `start_instance(wait_http=False)`
**立即返回、不做任何存活检查**——那个 `except` 永远不会触发。两个变体因此双双
落进「启动成功」分支。**用例根本没在测它自称在测的东西。**

L0 从源码和实测两头钉死了真相：`dsh-app-boot` 的 `assertEntriesActivated` 在
boot 末尾审计每个未 disabled 的条目，非 ACTIVE 一律抛错。**PENDING 无条件致命，
跟 bundle 组合毫无关系。** 改成直接看进程死没死之后：

| 变体 | 结果 |
|---|---|
| 提供者被禁用（`labRegistry`） | **启动失败，退出码 1** |
| 服务名从不存在 | **启动失败，退出码 1** |

```
Error: dsh: plugin tree failed to load: dsh: 1 entry did not activate
lab-alpha: pending (waiting for services: labRegistry, 从来没有人提供过这个服务)
```

（顺带二次印证了结论 3：条目级 `inject` 是**补充**——两个服务都在等待名单里。）

### 最值得记的一点

那条 `PENDING → UNLOADING → DISPOSED` 的状态链，**当时被读成「条目被销毁所以
审计无话可说」，实际上它是启动失败的证据**：`boot()` 的 catch 里
`await ctx.fiber.dispose()` 把整棵树销毁了，事件流记下的正是这个动作。

同一份观测数据，因为缺了「进程还活着吗」这一个对照，读出了完全相反的结论。
**观测到的现象越丰富，越要先确认最粗的那个事实。**

## 四、一个实验设计上的教训

第一版的教学插件在拿不到服务时 `throw`：

```js
const book = ctx.get("labRegistry");
if (!book) throw new Error("...");   // ← 错
```

这会把两种**完全不同**的现象混成同一个结果（实例起不来）：

- inject 没满足 → **根本没 apply**
- apply 了 → 但服务是 `undefined`

**探针不该在观测点抛错。** 改成如实记录之后（`gotRegistry: false` + 见证文件照常写），
两种情况立刻可分——而真相是第一种，第二种在这套框架里根本不会发生。

## 五、这一课立住的词

- **提供者 / 消费者** — `ctx.provide(name, value)` 提供（返回 disposer，fiber 卸载时自动撤销）；
  `ctx.get(name)` 取用
- **硬依赖** — `inject` 声明的服务没到位，`apply` 不执行
- **依赖链** — 消费者自己也可以是提供者，构成多级

## 六、下一课

**L4 · 加载顺序** —— 把「服务可用性驱动」展开：并发创建、书写顺序无效、
以及框架自带那 79 个条目的真实加载图景。
