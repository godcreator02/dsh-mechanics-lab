# L3 · 服务与 `inject`

**这一课回答：** 谁提供服务、谁依赖它、**依赖没到位时会怎样**。

跑法：`uv run pytest experiments/l03_service_inject/`（约 55 秒，8 个用例）

---

## 一、三个插件构成的依赖链

```
lab-registry  ←──  lab-alpha  ←──  lab-beta
提供 labRegistry    登记 + 提供       登记（要两个服务）
（不依赖任何人）     labAlpha
```

账本（`labRegistry` 提供的那个对象）**每登记一笔就整份落盘**，
所以见证文件里的顺序就是**真实的 apply 先后**——L3 用它验依赖，L4 用同一份数据验顺序。

## 二、实测结论

### 1. `inject` 是硬依赖：服务没到位，`apply` 根本不执行

把 `lab-registry` 禁用之后，`lab-alpha` 的见证文件**不出现**——不是「apply 了但拿到
undefined」，是**压根没 apply**。

### 2. 但依赖永远满足不了时，条目不会一直 PENDING，而是**被 DISPOSED**

装上观测台直接看 fiber 状态，这是完整的一生：

```
+  1.861ms  snapshot  fiberState=PENDING  hasFiber=True
+169.677ms  fiber disposed
+169.769ms  PENDING → UNLOADING
+176.033ms  UNLOADING → DISPOSED
```

**它先进 PENDING 等，然后在 boot 末尾（约 +170ms）被主动销毁。**
而**实例照常启动**——因为销毁之后它不再是 pending，`assertEntriesActivated` 也就无话可说。

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

## 三、⚠️ 一处未解的矛盾（已缩小到一个变量）

早先做教具时观察到：`inject` 一个**从不存在的服务名**会让 boot 直接 fail-loud：

```
dsh: plugin tree failed to load: 1 entry did not activate
lab-demo-waiting: pending (waiting for service: 压根不存在的服务)
```

本课里同样是「依赖永远满足不了」，实例却**照常启动**。

用例 7 做了隔离实验，把「服务名是否有被禁用的提供者」这个变量单独拎出来测：

| 变体 | 结果 |
|---|---|
| 提供者被禁用（`labRegistry`） | 启动成功，`PENDING → UNLOADING → DISPOSED` |
| 服务名从不存在 | 启动成功，**行为完全一致** |

**所以差异不在服务名。** 两次实验剩下的唯一变量是 **bundle 组合**——
教具那次 profile 叠了 `dsh-web-app`，本课只叠 `dsh-base`。

**这条列为待查**，不在本课深挖（它属于 boot 机制，归 L7）。
在查清之前，「boot 期的 PENDING 是致命的」这个说法**要带上条件**，不能当通则用。

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
