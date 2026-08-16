# L8 · 层级：谁在子树里、谁不在

> 4 个用例 ｜ 约 25 秒 ｜ 不需要 web ｜ 🔬 发现型 ｜ 前置：L0（复用其普查手法与 `parentIdOf()`）

`loader.entries()` 是扁平遍历（自己 + 所有嵌套子树），光看那个列表分不出层级。
真实的树是什么形状？谁管着谁？这决定了「配方热重放」到底碰得到谁、碰不到谁——
而那正是本课要交给 L17 的东西。

```powershell
uv run pytest experiments/l08_tree_hierarchy/ -v
```

---

## L0 已经立住的地基

给普查员加上 `parent` 字段、实测最小环境之后，L0 已经把树的骨架钉死：

```
根组
└─ include (cordis:include)    ← 树根，配方装在它的 config.patches 里
    ├─ timer                   ⊂include   ← 基线声明的基础设施
    ├─ hmr                     ⊂include
    └─ 配方里的其它条目…         ⊂include
```

**除了树根，所有条目都在 `include` 的子树里**——它们全来自 patch 文件，
而整份 patch 就装在 include 的 config 里。

取父条目的办法，照抄 loader 源码 `getOuterStack` 的走法：

```js
entry.parent?.ctx?.fiber?.entry?.options?.id ?? null   // 根组没有拥有者，返回 null
```

本课的普查员 `fixtures/l08-census` 就是 L0 那份的原样拷贝（跨课重复是设计
允许的），只加了 `labFlavor` 到关心的服务列表、marker 换成自己的版本号。

本课要在这个地基上补三件事：`group`（第二个内置插件）怎么造出嵌套子树、
禁用的向下传播、以及服务隔离（`isolate`）。

---

## 结论速查

| 问题 | 答案 |
|---|---|
| `cordis:group` 条目的孩子 `parent` 指向谁 | 指向 group 自己（用条目 id，不是 `cordis:group` 这个 name） |
| group 能不能嵌套 | 能，层级随嵌套深度线性增加，`loader.entries()` 照样摊平列出来 |
| group 自己被 `disabled: true`，它自己会不会停 | **不会**——`if (options.group) return false`，group 自己免疫 |
| 但它的孩子呢 | **照样被拦下**——孩子沿父链查到的是 group 的 `options.disabled` 原文 |
| 普通（非 group）条目被禁用 | 自己就真的不激活——这是默认行为，group 才是例外 |
| `isolate: { <服务名>: true }` 能不能让两个组各自看到不同的服务实例 | **能**，实测两组各自的消费者互不串 |
| `loader.entries()` 的列表顺序等不等于树的先后关系 | **不等于**——见下面「一个意外收获」 |

---

## 一、group 怎么造出嵌套子树

条目写法（源码 `cordis-plugin-loader/src/config/group.ts`）：`Group extends
EntryGroup`，激活时 `Service.init` 无条件跑 `this.update(this.config)`，
把 `config` 数组里的每一项都 `create` 成一个真的子条目，父指针是 group 自己：

```yaml
- id: outer-group
  name: '@deepseek-ai/cordis-plugin-group'
  group: true
  config:
    - id: leaf-1
      name: l08-leaf
    - id: inner-group
      name: '@deepseek-ai/cordis-plugin-group'
      group: true
      config:
        - id: leaf-2
          name: l08-leaf
```

实测出来的真实结构（`test_group_builds_nested_subtree`，普查员的 settle 快照，
按 `parent` 链缩进）：

```
· id=include              cordis:include                         state=2
    · id=census               l08-census                             state=2  ⊂include
    · id=outer-group          @deepseek-ai/cordis-plugin-group       state=2 [group]  ⊂include
        · id=leaf-1               l08-leaf                               state=2  ⊂outer-group
        · id=inner-group          @deepseek-ai/cordis-plugin-group       state=2 [group]  ⊂outer-group
            · id=leaf-2               l08-leaf                               state=2  ⊂inner-group
· id=86b74f9e             @deepseek-ai/cordis-plugin-timer       state=2
· id=646e3e7b             @deepseek-ai/cordis-plugin-hmr         state=2
```

三条判定，都在用例里正面断言过：

1. **`inner-group` 的 `parent` 是 `outer-group`，不是 `include`。** 它嵌套写在
   `outer-group` 的 `config` 里，父指针跟着嵌套关系走，不是跟着「在哪个 patch
   文件里」走——这是 group 和「活层里平铺一堆 `- insert:`」的本质区别。
2. **`leaf-1` 与 `inner-group` 深度相同**（都是 `outer-group` 的直接孩子），
   **`leaf-2` 比它们深一层**——`depth_of()` 完全靠 `parent` 链往上走出来的，
   `loader.entries()` 本身不带这个信息。
3. **扁平列表把三层深的 `leaf-2` 和顶层的 `census` 摆在同一份列表里**：

   ```
   ['include', 'census', 'outer-group', 'leaf-1', 'inner-group', 'leaf-2', '86b74f9e', '646e3e7b']
   ```

   这就是「`loader.entries()` 是扁平遍历」这句话的字面意思——不带 `parent`，
   压根看不出 `leaf-2` 比 `census` 深两层。

---

## 二、禁用的向下传播，以及 group 的例外

源码 `cordis-plugin-loader/src/config/entry.ts`：

```ts
private _disabled(options: EntryOptions) {
  // group is always enabled
  if (options.group) return false
  if (this.disabledOf(options)) return true
  let entry = this.parent.ctx.fiber.entry
  while (entry) {
    if (this.disabledOf(entry.options)) return true
    entry = entry.parent.ctx.fiber.entry
  }
  return false
}
```

普通条目沿父链一路往上查，任一祖先的 `disabled` 求值为真就不激活。但函数开头
那一句短路——**如果这个条目自己就是 group（`options.group` 为真），直接返回
`false`，后面的判断根本不看。**

这条例外只保护 group **自己**，不保护它的孩子。原因在于 group 的 `孩子`
在自己的 `_disabled()` 里往上走一层查到的父条目，**正是这个 group 自己的
`options`**——那里的 `disabled` 字段读到的是原文 `true`，孩子照样被拦。
「group 自己不受影响」和「它的孩子受影响」因此同时成立，两条判定看似矛盾，
实则是同一段代码的两个分支各自生效的自然结果。

实测（`test_disabled_propagation`，两个变体）：

**变体 A：group 自身写 `disabled: true`**

```
· id=include              cordis:include                         state=2
    · id=census-group         l08-census                             state=2  ⊂include
    · id=disabled-group       @deepseek-ai/cordis-plugin-group       state=2 [group, disabled(原文)]  ⊂include
        · id=child-under-disabled l08-leaf                               无 fiber  ⊂disabled-group
```

`disabled-group` 自己 `hasFiber=True`、`fiberState=2`（ACTIVE）——**激活了**，
尽管它自己的 `options.disabled` 原文就是 `true`。它的孩子
`child-under-disabled` 却是 `无 fiber`——从未被初始化。

**变体 B（对照组）：普通条目自己写 `disabled: true`**

```
· id=include              cordis:include                         state=2
    · id=census-plain         l08-census                             state=2  ⊂include
    · id=disabled-plain       l08-leaf                               无 fiber [disabled(原文)]  ⊂include
```

没有 `group: true` 时，`disabled: true` 就是字面意思——条目自己不激活。
两相对照，「group 自己不受 disabled 影响」的分量才看得清：那是**例外**，
不是「disabled 在 group 语境下失效了」。

---

## 三、服务隔离（isolate）

📗 官方文档 `zh/user/develop/framework/service.md:113` 讲了「服务隔离」：
`cordis.yml` 支持同一个服务有多个实例，不同插件组看到不同实例，写法是
给 `cordis:group` 的条目加 `isolate: { <服务名>: true }`。

源码侧（`cordis-plugin-loader/src/config/isolate.ts`）：`isolate: true` 给这个
条目建一个 `LocalRealm`（以条目自己的 id 为后缀的 symbol 命名空间），组内
`ctx.provide()` 落进这个 realm 专属的 symbol；组外、以及用了不同 `isolate`
标签的另一个组，都看不见这份实现——这正是「同一服务名、多份实例」的机制。

**实验设计**：两个组都提供同一个服务名 `labFlavor`，值不同：

```yaml
- id: group-a
  name: '@deepseek-ai/cordis-plugin-group'
  group: true
  isolate: { labFlavor: true }
  config:
    - id: flavor-a
      name: lab-flavor
      config: { value: vanilla }
    - id: taster-a
      name: lab-flavor-taster
      config: { witness: <path-a> }

- id: group-b
  name: '@deepseek-ai/cordis-plugin-group'
  group: true
  isolate: { labFlavor: true }
  config:
    - id: flavor-b
      name: lab-flavor
      config: { value: chocolate }
    - id: taster-b
      name: lab-flavor-taster
      config: { witness: <path-b> }
```

`lab-flavor` 只做一件事——`ctx.provide("labFlavor", { value })`；
`lab-flavor-taster` 硬依赖它（`inject: ["labFlavor"]`），把看到的值写进见证文件。
`inject` 是硬依赖（L9 立住的规矩），所以见证文件本身出现就说明「在这个组的
隔离上下文里，`labFlavor` 是可解析的」，文件内容说明解析到的是**哪一份**。

实测（`test_isolate_gives_each_group_its_own_service_instance`）：

```
group-a 的 taster 看到：{'sawValue': 'vanilla',   'sawProviderMarker': 'lab-flavor-v1'}
group-b 的 taster 看到：{'sawValue': 'chocolate', 'sawProviderMarker': 'lab-flavor-v1'}
```

两组各自看到自己组里的值，没有互相覆盖，也没有报重复注册——隔离生效。
`sawProviderMarker` 两边相同（同一份插件代码、同一次模块 import），差异
只在 `sawValue`，正好排除了「两边其实是两次独立 import 出的不同模块」这种
干扰解释，把差异钉死在「同一份代码、两个隔离的服务实例」上。

⚠️ **本课的隔离验证只覆盖了「正面：两组互不干扰」这一条**。「不加 isolate、
两个组都 provide 同名服务会不会真的冲突／报错」这个负面对照没有测——
留一句如实的标注：**这个维度（isolate 缺失时的冲突行为）未覆盖**，
不要假装测过。

---

## 一个意外收获：扁平列表的顺序也不能当树用

`test_isolate_gives_each_group_its_own_service_instance` 多跑几次，同一份
patch 每次拍到的 `loader.entries()` 顺序都不一样。某一次是这样：

```
· id=61857800             @deepseek-ai/cordis-plugin-timer       state=2   ← 幽灵条目跑到最前面了
· id=include              cordis:include                         state=2
    · id=census               l08-census                             state=2  ⊂include
    · id=group-a              @deepseek-ai/cordis-plugin-group       state=2 [group]  ⊂include
    · id=group-b              @deepseek-ai/cordis-plugin-group       state=2 [group]  ⊂include
        · id=flavor-a             lab-flavor                             state=2  ⊂group-a
        · id=taster-a             lab-flavor-taster                      state=2  ⊂group-a
        · id=flavor-b             lab-flavor                             state=2  ⊂group-b
        · id=taster-b             lab-flavor-taster                      state=2  ⊂group-b
```

两处都值得记一笔：

1. **`timer` 幽灵条目有时排在 `include` 前面**——`loader.entries()` 的顺序
   不是稳定的「先创建先出现」，别拿列表位置当创建时序的证据。
2. **`group-a` / `group-b` 两个 group 各自的孩子没有紧跟在自己父条目后面**，
   而是等两个 group 都建完之后才成批出现（`flavor-a, taster-a, flavor-b,
   taster-b`）。这是 `EntryGroup.update()` 用 `Promise.allSettled` 并发创建
   同级条目（L10 的结论）在跨层级场景下的自然推论：`outer-group` 和
   `inner-group`（同属 `include` 一级）是并发创建的，而它们各自的孩子又是
   各自内部并发创建——所以「先出现在列表里」既不代表「先创建」，也不代表
   「在树里更靠前」。**认层级只能靠 `parent` 字段，认哪个都不能靠列表顺序。**

这不是本课原计划要测的东西，是普查手法本身的副产品——记在这里而不是删掉，
理由跟 L0 记「未坐实的观察」一样：一个反直觉的现象，比没见过更值得留痕。

---

## 这条判定的分量：hmr 自己也在重放的射程内

本课把归属这件事坐实到了「group 能不能改变归属」这一层：条目落在哪个父级
子树里，不取决于它是什么类型的插件，只取决于它的 `parent` 指针指向谁——
嵌进 group 只是让它换个父亲，换不出 `include` 的子树。

于是有一条对 L17 决定性的推论：**`hmr` 自己就住在 `include` 的子树里**
（不管它写在活层顶层还是嵌在某个 group 里）。而**配方热重放重新 compose 的
正是 `include` 的子树**——也就是说，hmr 在它自己触发的那次重放的射程之内，
每次重放都可能被重挂、watcher 随 effect 一起清掉。

真实部署也是这个形态（web bundle 自带 hmr 条目 ＋ 活层反禁用），本实验台的
基线同样是。所以「patch 监听哑火」的排查方向只有一个：不是「hmr 不在」，
是「hmr 还在但 watcher 被清了」。

**L17（hmr 归属，全课程收口）的实验设计完全建立在这条上。**

---

## 观测手法

沿用 L0 的普查员（`fixtures/l08-census`，原样拷贝改造），核心手段不变：
`ctx.get("loader")` 拿到 loader，遍历 `loader.entries()`，给每个条目记
`id / name / parent / disabled(原文) / group / hasFiber / fiberState`，
拍两张快照（apply 当下 + 延后 2.5 秒）。

本课新增的辅助函数：

- `entries_by_id()`：把某张快照的条目列表转成 `id → 条目` 的字典，供
  `depth_of()` 沿 `parent` 链回溯用。
- `depth_of()`：从一个条目出发，沿 `parent` 链往上数，数到根（`parent`
  为 `None`）为止。这是本课的核心论证工具——它证明「深度」这件事完全是
  从 `parent` 字段**重新算出来**的，`loader.entries()` 本身不带。
- `show_tree()`：按 `depth_of()` 算出的深度缩进打印，同时标 `[group]` /
  `[disabled(原文)]` 两个标记，方便肉眼核对「group 的 disabled 原文是 true，
  但它自己照样 `state=2`」这类反直觉的组合。

三个教学插件（`l08-leaf` / `lab-flavor` / `lab-flavor-taster`）都遵循 L0/L9
立住的规矩：观测点绝不抛错、账本落盘即可判定，不需要每个插件都自建一套
观测面——层级和禁用状态全部经普查员的全局快照拿到，只有服务隔离这条
必须靠真实的 provide/inject 才能验，普查员帮不上忙。
