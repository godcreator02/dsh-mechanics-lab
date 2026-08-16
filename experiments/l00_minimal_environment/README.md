# L0 · 全景：一棵树长什么样

> 9 个用例 ｜ 约 70 秒 ｜ 不需要 web ｜ 🔬 发现型 ｜ 前置：无

**这是「先总后分」的总。** 不求讲透任何一件事，只求让你一次看清整棵树的形状——
后面六个部分各展开其中一块：

| 本课立住的 | 展开于 |
|---|---|
| **配方 ≠ 树**：运行时多一个 `cordis:include`，`--dump-config` 永远看不见 | **L7** |
| **层级**：patch 里写的条目全住在 `include` 的子树里 | **L8** |
| **boot 期 PENDING 无条件致命** | **L11** |
| **`name` 有三条解析路径**，互不相通 | **L3** |
| **hmr 有两种处境**（在子树里 / 与 `include` 平级），死法完全不同 | L8、L17 |

---

## 起点的问题：一个实例最少需要什么？

这一课是**探路**。后面每一课都要拉实例，而「拉起来的到底是什么」如果没先钉死，
所有观测都建立在没验过的假设上。L1/L2/L9 用的基线是 `dsh-base`——78 个条目，
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
| 最小 bundle 集合是什么 | **空集**。`bundles: []` 照跑，`dsh-base` 整个是可选的 |
| `cordis.yml` 要自己建吗 | 不要。框架每次启动都重写它 |
| 运行时的树 = 配方吗 | **不等于**。基线下多一个 `cordis:include`，静态 dump 永远看不见 |
| `timer` / `hmr` 能不要吗 | **不能**。你不写，框架也会在 boot 返回后自己补一份 |
| 基线为什么自己写上它们 | 树的形状变得完全可预测：id 是我们给的，且它们跟别的条目一样住在 `include` 的子树里 |
| 谁保持进程活着 | 就这两个的句柄（timer 的定时器 + hmr 的 watcher） |
| boot 期 PENDING | **无条件致命**，退出码 1 |
| 裸包名以哪儿为锚 | profile 目录，标准 parent-walk。官方包不用 link |
| 相对路径以哪儿为锚 | profile 目录，且**必须指到文件** |

---

## 一、「空集」指的是 bundle 名单

`bundles: []`、活层里只挂一个自己的插件，实例照跑不误：

```
--dump-config 算出 1 个条目：
    · census → l00-census
进程还活着？ True
```

**插件系统的基础设施不由任何 bundle 提供，是框架自带的。** `dsh-base` 提供的
是「一个 AI 助手」，不是「一个插件运行时」。要研究插件系统，它整个是可选的。

### ⚠️ 但「空集」很容易被读错

它说的是 **bundle 名单**为空，**不是**「进程里可以没有插件」。
`timer` 和 `hmr` 不是「碰巧在」，是**承重的**：

| | 为什么少不了 |
|---|---|
| `timer` | `hmr` 包级声明 `services.required: ["timer"]`。没它 hmr 永远 PENDING |
| `hmr` | `watchUserPatches()` 开头就是 `if (hmr === undefined) throw`。没它 patch 监听建不起来 |
| 两个合起来 | 空树时**只有**它们的句柄撑着事件循环。没它们进程立刻退出 |

所以基线（`make_minimal_profile()`）是这么定的：**`bundles: []`，但 patch 里
显式写上 `timer` 和 `hmr`**。这跟真实部署一致——`dsh-base` 的 patch 头两条
就是这两个。把 base 拿掉是为了减噪（那 78 个条目里只有这俩跟插件系统有关，
其余全是业务线），不是为了模拟「没有它们」，那个场景现实中不存在。

`test_who_keeps_process_alive` 拿基线看了 15 秒没死：**没有 web 服务、没有任何
业务插件，就这两个基础设施的句柄（timer 的定时器 + hmr 的 chokidar watcher）
撑住了事件循环。**

基线跑出来的树，四个条目，一个不多一个不少（`test_baseline_profile` 拿
`ids == ["census", "hmr", "include", "timer"]` 硬断言）：

```
根组
└─ include (cordis:include)   ← 树根，唯一的幽灵条目
    ├─ timer                  ⊂include   ← 基线写的
    ├─ hmr                    ⊂include   ← 基线写的，root: []
    └─ census                 ⊂include   ← 你的插件
```

显式带上的两个直接好处：**树的形状完全可预测**（id 是我们给的，断言直接认
`timer`/`hmr`），**没有意外的条目混进来**。

> 补一句源码事实，本实验台的用例不覆盖它：patch 里没有 hmr **服务**时
> （判据是 `ctx.get("hmr") === void 0`，判服务不判条目），`boot()` 返回之后
> 框架会自己补一份 timer + hmr，无条件执行、没有开关。推论是
> **DSH 实例不存在「没有 hmr」的形态**——L17 要查的「patch 监听什么时候会死」
> 因此不可能是「hmr 不在」，只可能是「hmr 还在但 watcher 被清了」。

---

## 二、配方 ≠ 树

这是本课**最要紧**的一条判定，也是后面每一课的观测前提。

`--dump-config` 告诉你的是「配方算出来是什么」。而进程里真正跑着的那棵树，
比配方多**一个**条目：

| 条目 | 何时出现 | 来自哪里 |
|---|---|---|
| `cordis:include` | boot 期就在 | `mountRootInclude()`，是**整棵树的根** |

只有它一个，而且这不是巧合，是**结构性**的：整份配方就装在它自己的
`config.patches` 里（下一小节），它不可能出现在自己装的那份 config 中，
否则就是自指。所以不管配方怎么写、带不带 bundle，静态 dump 都看不见它。

`test_effective_config_vs_entry_tree` 就是照着这句写的断言——dump 的 id 集合
跟运行时树的 id 集合相减，`ghosts == {"include"}`。

普查员拍两张快照，顺带看到状态迁移：

```
── boot 期：boot() 还没返回 ──
    服务：loader
    · id=include         cordis:include                     state=1
    ·     id=timer       @deepseek-ai/cordis-plugin-timer   无 fiber  ⊂include
    ·     id=hmr         @deepseek-ai/cordis-plugin-hmr     无 fiber  ⊂include
    ·     id=census      l00-census                         state=1   ⊂include

── settle：boot() 返回之后 ──
    服务：loader, timer, hmr
    · id=include         cordis:include                     state=2
    ·     id=timer       @deepseek-ai/cordis-plugin-timer   state=2   ⊂include
    ·     id=hmr         @deepseek-ai/cordis-plugin-hmr     state=2   ⊂include
    ·     id=census      l00-census                         state=2   ⊂include
```

boot 期那张有两处值得停一下：

- **插件自己的 `apply` 跑在 LOADING 期**（`census` 是 `state=1`）——在自己的
  apply 里既看不到自己 ACTIVE，也看不到同一份 patch 里别的条目建好没有：
  拍到这一刻，`timer` 和 `hmr` 连 fiber 都还没有
- **服务列表里只有 `loader`**。`timer`/`hmr` 服务是 boot 返回后才齐的

### `include` 是什么：整个配方装在它的 config 里

它不只是「一个条目」。`mountRootInclude()` 建它的时候：

```js
const rootInclude = {
  id: "include",
  name: "cordis:include",
  config: {
    path: …/cordis.yml,      // 空根 []
    patches: [...patches]    // bundle 层 + 活层 + home 层 + overlays 全在这
  }
}
```

**所谓「配方」，就是这个条目的 `config.patches`。** 由此推出一条不显然的实现事实：
`watchUserPatches` 的回调干的事是重新 compose 出 patches，然后
`entry.update({config: {...includeConfig, patches}})`——

> **「配方热重放」在实现上就是「改 `include` 这一个条目的 config」。**

### 层级：谁在子树里，谁不在

`loader.entries()` 是扁平遍历（自己 + 所有嵌套子树），光看列表分不出层级。
给普查员补上 `parent` 之后：

```
根组
└─ include (cordis:include)    ← 树根
    ├─ timer                   ⊂include
    ├─ hmr                     ⊂include
    └─ census                  ⊂include
```

**除了树根，全都在 `include` 的子树里**——因为它们全来自 patch 文件，
而整份 patch 就装在 include 的 config 里。这不是巧合，是同一件事的两面。

⚠️ **这对 L17 很要紧**：配方热重放重新 compose 的，正是 `include` 的子树。
也就是说 `hmr` 自己就落在会被重放波及的范围内——每次重放它都可能被重挂、
watcher 随 effect 一起清掉。真实部署也是这个形态（web bundle 自带 hmr 条目
＋活层反禁用），所以「patch 监听哑火」的排查方向只有一个：
**不是「hmr 不在」，是「hmr 还在但 watcher 被清了」。**

（这条是推论，L17 去坐实。）

---

## 三、基线的 hmr 是 `root: []`：热重放工作，热重载不工作

基线给 hmr 的 config 是 `{root: [], debounce: 100}`——**watch root 是空的**。

空 root 不等于「什么都不监听」。`watchUserPatches()` 是按**精确路径**注册的
（profile 那个活层文件、home 那个 patch 文件），跟 root 完全无关。所以：

| 改什么 | 空 root 的 hmr |
|---|---|
| **patch 文件** | ✅ 照常热重放——监听按精确路径注册，不看 root |
| **插件源码** | ❌ 不监听任何代码文件，不会热重载 |

这两件事很容易被混成一件，「改了没反应」的排查会因此走岔。

要测代码热重载，得给一个真的 watch root：`make_minimal_profile(hmr_root=["."])`。
`test_baseline_profile` 两个变体（默认 `[]` / 指定 `["."]`）验的就是这个开关，
两种都是四个条目、形状不变，区别只在 hmr 的 config。

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

### 裸包名 → 官方包不用 link

实测：**基线自己就是这个实验**。`timer` / `hmr` 两条写的都是裸包名
（`@deepseek-ai/cordis-plugin-*`），而 profile 的 `node_modules` 里只有我们
自己 link 的教学插件、从来没有它们——照样 `state=2` 激活。
**官方包不需要 link。**（`test_bare_name_resolution` 把两头都打印出来：
profile 里没有、上一层的共享 `node_modules` 里有。）

⚠️ **但机制的第一版解释是错的**（2026-08-16 修正）。原来写的是
「`profile-boot` 把自己的 `package.json` 当 `bareModuleBaseUrl` 传给 `boot()`」，
依据是 `mountRootInclude()` 里那个专门处理裸包名的 `HostResolvedRootInclude` 子类。

**那段代码从未执行。** `bareModuleBaseUrl` 是 `boot()` 的第 5 个参数，而唯一的调用点
（`profile-boot-*.js:247`）只传了 4 个：

```js
const ctx = await boot(NAME, rootConfig, structuredClone(allPatches(composed)), (hostCtx) => {…})
//                                                                             ↑ 第 4 个，没有第 5 个
```

于是 `bareModuleBaseUrl === void 0` 恒成立，`builtins.include` 永远是朴素版 `Include`。
那个子类是**真实存在但从未激活的死代码**——而且它逻辑清晰、注释详尽，很有迷惑性。

真实机制平淡得多：**标准 Node parent-walk + 一层共享 `node_modules`**。

```
$DSH_HOME/profiles/
├── node_modules/          ← 符号链接农场（本机实测 252 条）
│   └── @deepseek-ai/
│       ├── cordis-plugin-timer  → <npx 缓存>/…/cordis-plugin-timer   [junction]
│       └── …
└── <profile 名>/          ← ctx.baseUrl 锚在这里
    └── node_modules/      ← 我们 link 自己 fixture 的地方
```

profile 目录向上遍历**一层**就撞见那份共享 `node_modules`。农场由 `dsh-app-boot` 的
`healScaffoldModuleFallback` 每次 `prepareProfile` 时幂等维护（对 dsh 自身依赖做 BFS，
每个包一条 junction，安装位置变了会重新指）。

**结论没变，机制变了**：锚点仍是 profile 目录、算法仍是标准包解析，不存在特殊锚点。
我们自己的 fixture 不在农场里，所以**仍然必须 link**。

这条修正的教训写在下面「一条读源码的教训」。

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

### 一条读源码的教训

上面那个 `bareModuleBaseUrl` 的错误，根子在**只读了函数体、没追调用链**。

那段代码写得非常好——有专门的子类名（`HostResolvedRootInclude`）、有 `isAbsolute()`
判断、有详尽的 JSDoc 解释「when the host, rather than the configuration project,
owns the complete plugin set」。**越是写得好的代码，越容易让人忘了问一句：
它到底被调用了吗？**

所以纪律加一条：**从源码得出的机制解释，必须追到调用点确认参数真的传了**。
可选参数尤其危险——它的默认分支往往才是实际走的那条。

（这个错误是 subagent 顺调用链核查时发现的。它给的替代解释——共享 node_modules
农场——随后被实测证实：`.testhome/l00/profiles/node_modules` 下 252 条，
`cordis-plugin-timer` 是一条指向 npx 缓存的 junction。）

---

## 六、谁保持进程活着

Node 进程在事件循环空了之后就退出。基线跑起来看了 15 秒没死——
**就 `timer` 和 `hmr` 这两个的句柄撑着事件循环**（timer 的定时器、
hmr 的 chokidar watcher）。

不需要 web 服务，不需要 `dsh-base`。

---

## 本课产出

`LabHome.make_minimal_profile()` —— 后面所有课的基线：

```python
# 默认：hmr 的 root 是 []。patch 监听可用，代码热重载不可用
profile = home.make_minimal_profile("demo", patch=my_patch)

# 要测代码热重载：给一个真的 watch root
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

1. **拍两张快照**（apply 当下 + 延后 2 秒）。只拍一张看到的是半成品：插件的
   `apply` 跑在 LOADING 期，那一刻同批的别的条目可能连 fiber 都还没建
   （上面 boot 期那张里的 `timer`/`hmr` 就是），服务表也还没齐。
2. **观测点绝不抛错**。拿不到 loader 就如实记 `null`。L3 第一版拿不到服务就
   `throw`，把「根本没跑到这」和「跑到了但没拿到」混成同一个结果。
3. **记录数组建在模块级，写文件时写整个数组**——见下。

延后用 Node 原生 `setTimeout`，**不用 `ctx.setTimeout`**——后者是 timer 服务
提供的，拿被测系统的一部分当测量工具，观测和被观测就纠缠在一起了。

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

### 那次 settle 丢失，后来查清了

当时最合理的猜测是「框架在 boot 返回后 `loader.create()` 补条目，
连带 `tree.write()` 写回 `cordis.yml`，触发一次整树刷新」。

**这条因果链在源头上就不成立**（L7 往下读了一层源码）：`Loader` 作为根树，
它的 `write()` 是空操作，注释写着 *"Loader's root tree is in-memory;
writes are no-ops."*——只有某个 `Include` 实例自己的子树落盘时才真的
`writeFile`。修好工具之后的每次复跑也都是 `apply 1 次`，没再见过。

所以那次丢失更可能就是**旧版普查员自己的缺陷**（`record` 建在 `apply` 里、
被覆盖后「重挂过」和「只挂了一次」长得一模一样），不是框架真做了整树刷新。
现在基线显式带上 timer/hmr，那条 `loader.create()` 路径根本不会被走到。
