# L0 · 最小可运行环境

> 第零级 · 环境 ｜ 12 个用例 ｜ 约 90 秒 ｜ 前置：无

一个 DSH 实例最少需要什么才能跑起来？

这一课是**探路**。后面每一课都要拉实例，而「拉起来的到底是什么」如果没先钉死，
所有观测都建立在没验过的假设上。L1–L3 用的基线是 `dsh-base`——78 个条目，
一整套 AI 助手，其中跟插件系统本身有关的只有两个（`timer` 和 `hmr`），
剩下 76 个全是业务线：会话、工具、模型、沙箱、技能……

它们不只是慢，是**噪声**：往事件流里灌几百条与被测对象无关的事件，
让「这个事件是我们造成的吗」变成一道需要推理的题。

```powershell
uv run pytest experiments/l00_minimal_environment/
```

---

## 结论速查

| 问题 | 答案 |
|---|---|
| 最小插件集合是什么 | **你要声明的是空集**，但树里从来不空——见下面第一节 |
| `cordis.yml` 要自己建吗 | 不要。框架每次启动都重写它 |
| 运行时的树 = 配方吗 | **不等于**。有三个条目不在任何 patch 文件里 |
| `timer` / `hmr` 能不要吗 | **不能，也关不掉**。写进活层再 `disabled` 只会让框架另造一份 |
| 谁保持进程活着 | 框架兜底补的 `timer` + `hmr` 就够 |
| 兜底的触发条件 | `hmr` **服务**不存在（不是「条目不存在」） |
| boot 期 PENDING | **无条件致命**，退出码 1 |
| 裸包名以哪儿为锚 | dsh 安装目录。官方包不用 link |
| 相对路径以哪儿为锚 | profile 目录，且**必须指到文件** |

---

## 一、「空集」指的是你要写的那个集合

`bundles: []`、活层里只挂一个自己的插件，实例照跑不误：

```
--dump-config 算出 1 个条目：
    · census → l00-census
进程还活着？ True
```

**插件系统的基础设施不由任何 bundle 提供，是框架自带的。** `dsh-base` 提供的
是「一个 AI 助手」，不是「一个插件运行时」。要研究插件系统，它整个是可选的。

### ⚠️ 但「空集」很容易被读错

它说的是**你需要声明的集合**为空，**不是**「进程里可以没有插件」。
树里从来不空——至少三个，见下一节。

而且 `timer` 和 `hmr` 不只是「碰巧在」，是**承重的**：

| | 为什么少不了 |
|---|---|
| `timer` | `hmr` 包级声明 `services.required: ["timer"]`。没它 hmr 永远 PENDING |
| `hmr` | `watchUserPatches()` 开头就是 `if (hmr === undefined) throw`。没它 patch 监听建不起来 |
| 两个合起来 | 空树时**只有**它们的句柄撑着事件循环。没它们进程立刻退出 |

### 试着关掉它们：关不掉

最直接的尝试是写进活层再 `disabled: true`。结果是**多造了一份**：

```
· id=my-hmr      …cordis-plugin-hmr     无 fiber [disabled]   ← 我们禁用的
· id=a1be1ad8    …cordis-plugin-timer   state=2               ← 框架补的
· id=169bbc99    …cordis-plugin-hmr     state=2               ← 框架补的
```

因为兜底判的是 `ctx.get("hmr") === void 0`——**服务在不在**。禁用的条目不提供
服务，所以判定成立，框架照补不误。连带把 `timer` 也补上（源码里 timer 那句
嵌套在 hmr 判断里）。

那段代码在 `boot()` 返回之后无条件执行，**没有任何开关**。

推论，也是这条判定真正的分量：**DSH 实例不存在「没有 hmr」的形态。**
所以 L13 要查的「patch 监听什么时候会死」，不可能是「hmr 不在」，
只可能是「hmr 还在但 watcher 被清了」——两个方向的排查手法完全不同。

后面所有课的基线因此定为 `make_minimal_profile()`——`bundles: []`。

---

## 二、配方 ≠ 树

这是本课**最要紧**的一条判定，也是后面每一课的观测前提。

`--dump-config` 告诉你的是「配方算出来是什么」。而进程里真正跑着的那棵树，
比配方多三个条目：

| 条目 | 何时出现 | 来自哪里 |
|---|---|---|
| `cordis:include` | boot 期就在 | `mountRootInclude()`，是**整棵树的根** |
| `timer` | boot 返回**之后** | profile-boot 的兜底 |
| `hmr` | boot 返回**之后** | 同上，`config: {root: []}` |

它们不在任何 patch 文件里，静态 dump 永远看不见。源码（`dsh/lib/profile-boot`，
`boot()` 返回后）：

```js
if (ctx.get("hmr") === void 0) {
  if (ctx.get("timer") === void 0) await ctx.loader.create({ name: "…timer" })
  await ctx.loader.create({ name: "…hmr", config: { root: [] } })
}
await watchUserPatches(ctx, { filename: profile 活层, … })
await watchUserPatches(ctx, { filename: home 层, … })
```

注意 `loader.create` **没传 id**——id 由 loader 自动生成。所以幽灵条目的 id
每次启动都不一样（`a561686b`、`bd9e6d44`、`58bcb02e`……），**不能拿 id 认它们**，
只能认 `name`。

普查员靠拍两张快照把它们逼出来：

```
── boot 期：boot() 还没返回 ──
    服务：loader
    · id=include     cordis:include      state=1
    · id=census      l00-census          state=1

── settle：boot() 返回之后 ──
    服务：loader, timer, hmr
    · id=include     cordis:include      state=2
    · id=census      l00-census          state=2
    · id=bd9e6d44    …cordis-plugin-timer  state=2
    · id=879630c6    …cordis-plugin-hmr    state=2
```

顺带看到状态迁移：boot 期两个条目都是 `1`（LOADING），settle 时都是 `2`（ACTIVE）。
插件自己的 `apply` 跑在 LOADING 期——**在自己的 apply 里是看不到自己 ACTIVE 的**。

---

## 三、兜底判的是服务，不是条目

`ctx.get("hmr") === void 0` 这一句判的是**服务在不在**。这个区别有后果：

- 条目写了但 `disabled: true` → 服务不存在 → 框架**照样再补一个**
- 条目写了且激活了 → 服务存在 → 不补

对照实验（自己挂 `my-timer` + `my-hmr`）：

```
· id=my-timer   …cordis-plugin-timer   state=2
· id=my-hmr     …cordis-plugin-hmr     state=2
树里的 hmr 条目共 1 个：['my-hmr']
```

只有一个。兜底没触发。

**这条对 dshw 有直接影响**：dshw 靠活层「反禁用」web bundle 出厂那条
`disabled: true` 的 hmr。在反禁用生效之前，服务是不存在的，所以框架其实一直
在补一个 `root: []` 的兜底 hmr——patch 监听从来没断过。这跟 dshw 项目正本里
「hmr 条目没在启动时启用的进程，patch 文件改了没人看」的记载**对不上**，
那条判定需要重验（→ L13）。

### 兜底那个 hmr 有个硬限制

`config: {root: []}`——**watch root 是空的**。它足够撑起 `watchUserPatches`
（那是按精确路径注册的，跟 root 无关），但**不监听任何代码文件**。

所以最小基线下：**改 patch 文件会热重放，改插件源码不会热重载。**

要测代码热重载就得自己挂 hmr 并给一个真的 root——`make_minimal_profile(hmr_root=[...])`
就是干这个的。

---

## 四、boot 期 PENDING 无条件致命

这个问题从 L3 挂到现在。当时的观察是矛盾的：教具那次（叠了 `dsh-web-app`）
启动直接失败，L3 那次（只叠 `dsh-base`）照常跑，于是归因到「bundle 组合」。

**那个归因是错的。** 源码里 `dsh-app-boot` 的 `assertEntriesActivated` 在 boot
末尾审计每一个未 disabled 的条目，任何一个不是 ACTIVE 就抛错：

```js
if (state === FIBER_PENDING) {
  const missing = Object.keys(fiber.inject).filter(s => fiber.ctx.get(s) === undefined)
  failures.push(`${name}: pending (waiting for ${subject}: ${missing.join(", ")})`)
}
```

实测（硬依赖一个不存在的服务）：

```
进程还活着？ False（退出码 1，死于 +0.52s）
日志：dsh: plugin tree failed to load: dsh: 1 entry did not activate
      l00-needy: pending (waiting for service: definitelyNotAService)
```

跟 bundle 组合没有任何关系。L3 那次之所以没死，是因为那些条目**最终变成了
ACTIVE**——观察到的从来不是「永久 PENDING 却活着」，是「PENDING 是个中间态」。
把中间态误当终态，这是本实验台迄今最有代表性的一次误读。

审计只在 **boot 期**做一次。boot 之后靠热重放新加的条目卡在 PENDING，
不会杀进程——那是另一套路径（→ L10）。

---

## 五、name 怎么解析：两套算法

`cordis-plugin-loader` 的 `EntryTree.import` 分两条路：

```js
name.startsWith("cordis:") →  loader.builtins[name.slice(7)]   // 内置表
name.startsWith(".")       →  import(new URL(name, ctx.baseUrl))  // URL 解析
否则                        →  import(name)                        // 包解析
```

### 裸包名 → dsh 安装目录

`profile-boot` 把自己的 `package.json` 当 `bareModuleBaseUrl` 传给 `boot()`。
官方注释说得很直白：

> use it when the host, rather than the configuration project, owns the complete plugin set

实测：挂一个**没有** link 进 profile 的 `@deepseek-ai/cordis-plugin-timer`，
照样 `state=2` 激活。**官方包不需要 link。**

### 相对路径 → profile 目录，且必须指到文件

两种写法的对照是本课最干净的一组数据：

| 写法 | 结果 |
|---|---|
| `./…/l00-census` | ❌ `ERR_UNSUPPORTED_DIR_IMPORT` |
| `./…/l00-census/index.js` | ✅ 加载成功 |

原因：**只有包解析认 package.json**。L1 验过的那条回退链
（`exports["."]` → `main` → `index.js`）是**包解析算法**的一部分；
相对路径走纯 URL 解析，压根不看 package.json，那条回退链不存在。

所以自己的插件有两条路：link 成包（现在的做法，能享受回退链），
或者相对路径直接指到入口文件。

### `cordis:` 内置表只有两个

`builtins` 出厂是空对象，只有 `mountRootInclude()` 往里塞了两个：
`cordis:include` 和 `cordis:group`。没有第三个。

---

## 六、谁保持进程活着

Node 进程在事件循环空了之后就退出。空树 + 兜底的 timer/hmr，看了 15 秒没死——
**框架兜底那两个就够撑住事件循环**（chokidar 的 watcher 和 timer 的句柄）。

不需要 web 服务，不需要 `dsh-base`。

---

## 本课产出

`LabHome.make_minimal_profile()` —— 后面所有课的基线：

```python
# 默认：靠框架兜底。patch 监听可用，代码热重载不可用
profile = home.make_minimal_profile("demo", patch=my_patch)

# 要测代码热重载：自挂 timer+hmr，给一个真的 watch root
profile = home.make_minimal_profile("demo", hmr_root=["."], patch=my_patch)
```

顺带验了一条基础设施事实：**活层允许多个 `- insert:` 块**，各块独立生效。
基线 API 靠这一点把自己的条目拼在调用方的 patch 前面，不用解析也不用改
调用方那段字符串。

---

## 观测手法

本课的核心工具是 `fixtures/l00-census`——**普查员**。

它解决的问题是：`--dump-config` 看不见运行时的树。要看见幽灵条目，
只能从进程内部往外看。做法是拿 `ctx.get("loader")`，遍历 `loader.entries()`，
把每个条目的 id / name / disabled / 有没有 fiber / fiber 状态 / 在等哪些服务
全序列化出来。

三个设计要点，都是踩过坑换来的：

1. **拍两张快照**（apply 当下 + 延后 2 秒）。幽灵条目是 `boot()` 返回之后才补的，
   只拍一张永远看不到它们。
2. **观测点绝不抛错**。拿不到 loader 就如实记 `null`。L3 第一版拿不到服务就
   `throw`，把「根本没跑到这」和「跑到了但没拿到」混成同一个结果。
3. **记录数组建在模块级，写文件时写整个数组**——见下。

延后用 Node 原生 `setTimeout`，**不用 `ctx.setTimeout`**——后者是 timer 服务
提供的，而 timer 在不在正是本课要测的东西，拿被测对象当测量工具就循环论证了。

### 第 3 条是怎么来的：工具把自己的问题藏住了

第一版把 `record` 建在 `apply` 里。跑「显式禁用 hmr」那个变体时出了怪事：
文件里**只有 boot 快照，没有 settle**，可进程活得好好的。

原因是普查员被**重挂**了：`ctx.on("dispose")` 清掉定时器，重挂后新的 `record`
又把文件整个覆盖。于是「被重挂过」在文件里长得跟「只挂了一次但定时器没跑」
一模一样——**工具把自己被重挂这件事藏住了。**

挪到模块级、改成写整个数组之后，重挂会往数组里多加一条，
`applyIndex` 和数组长度都看得见。从缺陷变成了一个有用的观测量。

（模块级变量只在**模块被重新 import** 时才清空，条目重挂不清。
这两件事的区别正好是 L11 的主题。）

### 一个还没坐实的观察

上面那次 settle 丢失，最合理的解释是兜底 `loader.create()` 会 `tree.write()`
写回 `cordis.yml`，而那正是 root include 的 config 文件，于是触发一次整树刷新。

但**这条没被直接证实**：修好工具之后两次复跑都是 `apply 1 次`，没抓到重挂。
旧版工具已经把当时的证据覆盖掉了，所以只能说「符合观察」，不能说「已验证」。
真要坐实，得在 L10 用观测台的事件流去抓——那里才有分辨「重放发生了但条目没变」
和「重放根本没发生」的手段。

**记在这里而不是删掉**：一个只见过一次、又拿不出证据的现象，比没见过更危险。
