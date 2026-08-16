# L7 · 配方 ≠ 树：`include` 与幽灵条目

> 6 个用例 ｜ 约 60 秒 ｜ 不需要 web ｜ 🔬 发现型 ｜ 前置：L0、L4

**要回答**：`--dump-config` 算出来的**配方**，和进程里真正跑着的那棵**树**，差在哪。

---

## 为什么这件事重要

`--dump-config` 是所有人诊断配方问题的第一工具——改了 patch 却不生效、
条目对不上号，第一反应都是先 dump 一份出来看。但它**系统性地看不见三个条目**
（L0 已验）：

| 条目 | 谁造的 | 何时 |
|---|---|---|
| `cordis:include` | `mountRootInclude()` | boot 期 |
| `timer` | profile-boot 兜底 | boot **返回后** |
| `hmr` | 同上 | boot **返回后** |

其中 `hmr` 还是 patch 热重放的承担者——**不知道它是「兜底补的、dump 看不见的
条目」这件事，排查「改了 patch 没反应」时会从一开始就找错方向**：会去怀疑
patch 文件语法、怀疑活层没生效，却想不到去查「hmr 这个条目本身是不是还在」。

本课把这件事从「看得见有三个幽灵条目」推进到「看清 `include` 这个条目**自己
的内部结构**」——它不只是树上的一个节点，它的 `config.patches` 字段就是
「配方」这个概念的真身。这一步是 L14（配方热重放怎么实现）的地基：
不先弄清楚「配方存在哪」，就无从谈「配方怎么被改」。

---

## 结论速查

| 问题 | 答案 |
|---|---|
| 「配方」存在哪 | `include` 条目自己的 `config.patches`——不是什么抽象说法，是这个条目实实在在持有的一个数组字段 |
| 「配方热重放」的实现是什么 | 改 `include` 这一个条目的 `config`（`entry.update({config})`），别的条目碰不到 |
| 兜底判的是条目还是服务 | **服务**（`ctx.get("hmr") === void 0`）。写进活层再 `disabled` 只会让框架另造一份，关不掉 |
| 兜底会不会因为已有激活的 hmr 而不触发 | 会。服务已经在了，兜底就不补 |
| 幽灵条目的 id 稳定吗 | **不稳定**，每次启动都不一样。只能认 `name`（包名） |
| 兜底创建 timer/hmr 会不会写回 `cordis.yml`、触发整树刷新 | **源码上不成立**（根树 `write()` 是空操作），实测两次都没复现 |

---

## 一、`include` 不只是一个条目——整个配方装在它的 `config.patches` 里

源码（`dsh-app-boot` `lib/index.js` 的 `mountRootInclude()`）：

```js
const rootInclude = {
  id: "include",
  name: "cordis:include",
  config: {
    path: pathToFileURL(absoluteConfigPath).href,   // 空根 cordis.yml
    ...patches.length > 0 ? { patches: [...patches] } : {}
  }
}
```

`patches` 就是四层（bundle 层 / profile 活层 / home 层 / `--patch` overlay）
拼接后的**那份完整列表**，原样塞进这一个条目的 `config` 里。

`test_include_config_holds_full_recipe` 的验法：profile 活层埋一个标记
`profile-marker`，home 层埋另一个标记 `home-marker`（两个不同的文件、两条独立
的 patch 层），boot 之后从普查员报的 `include` 条目里直接读 `config.patches`：

```
· id=include          cordis:include
    config.patches：present=True count=2
      - {'op': 'insert', 'ids': ['census', 'profile-marker']}
      - {'op': 'insert', 'ids': ['home-marker']}
```

两条 `insert` 操作分别来自两个文件（`profile.cordis.patch.yml` 贡献第一条，
`$DSH_HOME/cordis.patch.yml` 贡献第二条），两个标记都在。**这就是「配方」这个
词的实际所指**——不是某种运行时算出来又扔掉的中间结果，是一个持久挂在
`include` 条目上、随时能读到的数组。

### 由此推出：「配方热重放」= 改 `include` 这一个条目的 `config`

源码（`watchUserPatches` 的回调，`lib/index.js:766`）：

```js
const register = hmr.registerConfig(filename, async () => {
  const { patches: _previousPatches, ...includeConfig } = entry.options.config;
  const patches = compose(loadOptionalPatches(binName, filename) ?? []);
  await entry.update({ config: { ...includeConfig, patches } });
});
```

活层文件一变，回调重新读文件、重新 compose 出 `patches`，然后就是**一次
`entry.update({config})`**——改的是 `include` 这个条目自己的配置，没有任何
「遍历整棵树、逐个比对」的动作在这一层发生。

`test_recipe_hot_reload_updates_include_config` 实测：boot 之后活着改
profile 的活层文件、多插一个 `profile-marker-2`，第二张快照（`settle2`）里
`include.config.patches` 立刻多了这一条：

```
改动前：['census', 'profile-marker', 'home-marker']
改动后：['census', 'profile-marker', 'profile-marker-2', 'home-marker']
```

⚠️ 本课只坐实到「亲眼看见这个数组变了」这一步，**不追问 fiber 状态变没变**
（`census` 条目自己的 `state` 全程是 `2`，没被重挂——它的那一行在两次 patch
文件里字节相同）。「哪些条目会因此被重挂」是 L14 的地基之上要继续盖的部分，
本课只负责把地基钉实。

---

## 二、兜底判的是「服务」，不是「条目」，而且关不掉

L0 已经把这条钉死了（`disabled: true` 关不掉、框架照样另造一份）。本课在
自己的环境里复核一次，并**补上另一半对照**：如果自己挂的 hmr 是**激活**的
（不禁用），兜底会不会因为服务已经在了而不触发。

| 用例 | 挂法 | hmr 条目数 | 结论 |
|---|---|---|---|
| `test_fallback_creates_even_when_disabled` | 自己的 `my-hmr` 写 `disabled: true` | **2**（`my-hmr` 禁用 + 框架补的一份激活的） | 禁用不提供服务，兜底照样触发 |
| `test_fallback_skips_when_own_hmr_active` | 自己的 `my-hmr` 激活（配 `root: []`） | **1**（只有 `my-hmr` 自己） | 服务已经在了，兜底不补 |

两个方向合起来，`ctx.get("hmr") === void 0` 判的确实是**服务在不在**，不是
「条目写没写」——这条对 dshw 有直接影响：只要活层里有一条**激活**的 hmr
条目（哪怕是反禁用来的），兜底就不会插手；但只要那条还没激活（比如反禁用
本身还没生效的那个瞬间窗口），框架就已经在用一份 `root: []` 的兜底 hmr
撑着 patch 监听了。

---

## 三、幽灵条目的 id 每次启动都不一样，只能认 `name`

源码里那两句创建兜底条目的调用**没传 id**：

```js
await ctx.loader.create({ name: "@deepseek-ai/cordis-plugin-timer" })
await ctx.loader.create({ name: "@deepseek-ai/cordis-plugin-hmr", config: { root: [] } })
```

id 由 loader 自动生成。`test_ghost_ids_differ_names_stable` 起两个完全独立
（除了名字）的最小 profile，各自读一次 settle 快照：

```
ghosta 的幽灵条目：{'plugin-timer': 'f8eb7d25', 'plugin-hmr': '610176d9'}
ghostb 的幽灵条目：{'plugin-timer': '7b7a3383', 'plugin-hmr': '5a64d170'}
```

四个 id 两两不同，`name` 都稳定落在同一个包名后缀上。**这是后面所有课写
断言时的硬约束**：想在测试里认出「这是不是那个兜底的 hmr」，唯一可靠的办法
是比 `name`，绝不能记住某次跑出来的 id 再去找它。

---

## 四、未坐实的观察：兜底会不会触发一次整树刷新

L0 记下但没坐实一个现象：早期一次跑里，普查员的 settle 快照凭空消失了，
当时最合理的猜测是——兜底的 `ctx.loader.create()` 会 `tree.write()`，
而那正是 `include` 的 `config.path`（`cordis.yml`），于是触发一次整树刷新，
把普查员也捎带重挂了。但两次复跑都没能重现，旧版工具的证据也已经被覆盖，
所以只能记「符合观察，没有实锤」。

本课往下多读了一层源码（`cordis-plugin-loader/src/index.ts`），这条假说的
**因果链在源头上就不成立**：

```ts
// class Loader extends EntryTree —— 树的根，ctx.loader 本身
write() {
  // Loader's root tree is in-memory; writes are no-ops.
}

// class Include extends EntryTree —— 某个 cordis:include 条目自己的子树
write() {
  this.context.emit('loader/config-update')
  return this.writeFile(this.root.data)   // 只有这里真的落盘
}
```

兜底的 `ctx.loader.create()` 落在**根**这棵树上——timer/hmr 跟 `include`
平级（L0 已验），不是 `include` 的子树成员。而根树（`Loader` 自己）的
`write()` 明确是空操作，注释原文写着 *"Loader's root tree is in-memory;
writes are no-ops."*。只有某个 `Include` 实例自己的子树落盘时才会真的
`writeFile`。兜底创建 timer/hmr 压根碰不到磁盘上的 `cordis.yml`，
「写回配置文件、触发整树刷新」这回事从源头上就没有发生的条件。

`test_ghost_creation_does_not_lose_settle_snapshot` 仍然去实测——源码分析
可能漏看了别的路径。用普查员的 `applyIndex`/多条 record 数组直接看
「观察窗口内被 apply 了几次」：

```
普查员在观察窗口内被 apply 了 1 次
record[0]：applyIndex=0，拍到的快照=['boot', 'settle', 'settle2']
```

**未复现，跟 L0 两次复跑的结果一致。** 结合上面的源码证据，现在倾向于认为
这不是「还没抓到」，而是「这条因果链本身大概率不存在」——L0 那次 settle
丢失更可能是**旧版普查员自己的缺陷**（`record` 建在 `apply` 里、被覆盖后
「重挂过」和「只挂了一次但定时器没跑」长得一模一样，这条缺陷本身在 L0 的
README 里已经记录并修复），不是框架真的做了一次整树刷新。

⚠️ 这个判定的状态是**待验证降级为「大概率不成立」**，不是「已推翻」——
没有找到那次现象的替代解释，只是排除了 L0 猜的这一种机制。如果后面哪一课
（大概率是 L14，需要观测台的事件流）撞见类似现象，值得回来更新这一节。

---

## 观测手法

`fixtures/l07-census`——从 `l00_minimal_environment/fixtures/l00-census`
拷来改造（跨课重复是特性，见项目 `CLAUDE.md`）。在 L0 普查员的基础上加了两件事：

1. **摘 `include` 条目的 `config.patches`**：只有这一个条目才摘，且不整体
   `JSON.stringify`——`!!js` 表达式解析后是个不透明的求值单元，直接序列化
   容易失真甚至抛错。摘要只取「这条 patch 操作是 `insert` 还是 `override`、
   涉及哪些 id/name」，足够用来对账「配方里写的东西是不是真的出现在这里」。
2. **一张可选的第三快照 `settle2`**（`config.delayMs2`）：不起 web 服务也能
   验证「活层文件改了之后，`include` 的 `config.patches` 跟着变了没有」——
   先拍一张，测试代码这时去改活层文件，再拍一张，两张一比。

其余设计（模块级 `records` 数组、`parent` 字段、观测点绝不抛错、延后用原生
`setTimeout` 不用 `ctx.setTimeout`）原样继承自 L0 的普查员，那边的 README
第「观测手法」节讲了每一条的来历，这里不重复。

---

## 与后面课的关系

- **L8**：本课已经在快照里带出了层级（`parent` 字段）——`include` 的子树
  条目标 `⊂include`，兜底的 timer/hmr 没有这个标记（跟 `include` 平级）。
  L8 要把这条从「顺带看到」升级成正面验证的对象。
- **L14**：本课钉死的「配方热重放 = 改 `include` 的 `config`」是 L14 的
  唯一地基。L14 要往下追一层：`fiber.update(config)` 会不会动 fiber、
  条目级 diff 到底diff 在哪一层。
