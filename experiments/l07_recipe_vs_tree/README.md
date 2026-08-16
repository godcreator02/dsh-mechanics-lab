# L7 · 配方 ≠ 树：`include` 与幽灵条目

> 3 个用例 ｜ 约 15 秒 ｜ 不需要 web ｜ 🔬 发现型 ｜ 前置：L0、L4

**要回答**：`--dump-config` 算出来的**配方**，和进程里真正跑着的那棵**树**，差在哪。

---

## 为什么这件事重要

`--dump-config` 是所有人诊断配方问题的第一工具——改了 patch 却不生效、
条目对不上号，第一反应都是先 dump 一份出来看。但它**系统性地看不见树根**
（`cordis:include`，L0 已验）。

而看不见的偏偏是最要紧的那一个：**整份配方就装在它的 `config.patches` 里。**

本课把这件事从「知道它在」推进到「看清它自己的内部结构」——`include` 不只是
树上的一个节点，它那个 `config.patches` 字段就是「配方」这个概念的真身。
这一步是 L14（配方热重放怎么实现）的地基：不先弄清楚「配方存在哪」，
就无从谈「配方怎么被改」。

---

## 结论速查

| 问题 | 答案 |
|---|---|
| 「配方」存在哪 | `include` 条目自己的 `config.patches`——不是什么抽象说法，是这个条目实实在在持有的一个数组字段 |
| 「配方热重放」的实现是什么 | 改 `include` 这一个条目的 `config`（`entry.update({config})`），别的条目碰不到 |
| 树上有几个条目不来自 patch 文件 | **一个**：`cordis:include` |
| 为什么偏偏是它 | **结构性的**：整份 config 装在它自己的 config 里，它出现在其中就是自指 |

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

## 二、`include` 是树上唯一不来自 patch 文件的条目

`test_include_is_the_only_ghost` 的算法直白：`--dump-config` 拿一份 id 集合，
普查员从进程里拿一份 id 集合，两个相减。

```
effective config 里的 id：['census', 'hmr', 'home-marker', 'timer']

树上的条目：
    · id=include          cordis:include
        config.patches：present=True count=2
    ·     id=timer         @deepseek-ai/cordis-plugin-timer   state=2  ⊂include
    ·     id=hmr           @deepseek-ai/cordis-plugin-hmr     state=2  ⊂include
    ·     id=census        l07-census                         state=2  ⊂include
    ·     id=home-marker   l07-marker-home                    无 fiber [disabled]  ⊂include

树上有、config 里没有的 id：['include']
```

**这个「一个」不是巧合，是结构性的。** 整份 effective config 就装在
`include` 自己的 `config.patches` 里（上一节），所以它不可能出现在自己装的
那份 config 中——出现了就是自指。不管配方怎么写、带不带任何 bundle，
它都在树上、都不在 dump 里。

反过来那半边也一并验了：`recipe_ids <= tree_ids`——配方里写的每一条都真的
上了树，没有「算出来了却没挂上」的漏网条目（禁用的那条也在树上，
只是没有 fiber）。

### 一个附带的观察：条目在树上的层级

快照里 `timer` / `hmr` / `census` / `home-marker` 全带 `⊂include` 标记，
只有 `include` 自己没有。**所有来自 patch 文件的条目都住在 include 的子树里**
——这跟「整份 patch 装在 include 的 config 里」是同一件事的两面。L8 把这条
从「顺带看到」升级成正面验证的对象。

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

- **L8**：本课已经在快照里带出了层级（`parent` 字段）——除了树根，所有条目
  都标着 `⊂include`。L8 要把这条从「顺带看到」升级成正面验证的对象，
  并往下看 group 怎么造出更深的嵌套。
- **L14**：本课钉死的「配方热重放 = 改 `include` 的 `config`」是 L14 的
  唯一地基。L14 要往下追一层：`fiber.update(config)` 会不会动 fiber、
  条目级 diff 到底 diff 在哪一层。
