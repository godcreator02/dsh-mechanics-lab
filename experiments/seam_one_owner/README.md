# seam · 一个名字一个主人

```powershell
uv run pytest experiments/seam_one_owner/ -n 0 -s
```

3 个用例 / 约 6 秒 / 不需要 web ｜ 🔬 发现型

## 这一项讲什么

前面每一步里，你写的插件都在**用**别人提供的东西。这一步反过来：你自己提供一个
东西，让别的插件来用。

提供有两种写法：

| 写法 | 怎么写 | 谁在用 |
|---|---|---|
| 裸对象 | `ctx.provide("名字", 那个对象)` | 本项目的教学插件与采集器 |
| 服务基类 | `class X extends Service`，构造里 `super(ctx, "名字")` | DSH 自己的可替换能力 |

摆在一起是为了回答一个问题：**两个插件想占同一个名字，会怎样？换种写法会不会
就不一样了？**

## 实测判定

### 一、一个名字只有一个主人，谁先到谁得

两个插件占同一个名字，**后到的那个当场失败**，框架报的原话是：

```
service "labSeat" has been registered at <Include>
```

失败者的 fiber 走 `LOADING → UNLOADING → FAILED`，`apply` 里 `provide` 之后的
代码一行都没执行。

### 二、换成服务基类，一字不差的同一句话

裸对象 vs 服务基类抢同一个名字，报错文本与判定一**完全相同**。

**独占不是服务基类那种写法的特性。** 两种写法最终都落到框架那唯一一条注册通道上，
重复检查长在那条通道里——所以「谁能占名」这件事跟写法无关，只跟名字有关。

用例里两条判定共用同一个字面量常量做断言，一字不差这件事由代码本身保证。

### 三、名字不同就不撞

同样两个插件、同样两种写法，只把名字改成不一样的：两个都占上、都跑到 `ACTIVE`、
实例照常活着。

撞车的病因是**名字相同**，不是「有两个提供者」，也不是「两种写法混用」。

## 排错时用得上的两件事

**报错里点得出「谁失败了」，点不出「谁先占的」。** 完整那句是：

```
dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include):
failed to apply loader entry 裸乙 (./bare-owner.mjs): service "labSeat" has been registered at <Include>
```

失败方的条目 id 和 `name` 都在（`裸乙 (./bare-owner.mjs)`），照着就能在 patch 文件里
找到那一行。但先占者只显示成 `<Include>`——那是 fiber 名，不是条目 id，从这句话
看不出是谁占的。想知道先占者，得去事件流里找那条「服务出现」，它带着条目 id。

**启动期撞车拖垮整个实例**，退出码 1。连占名成功的那个也会被拆掉——事件流里它走完
`LOADING → ACTIVE` 之后还有 `UNLOADING → DISPOSED`，服务跟着撤销。

## 官方文档侧

`docs/official/zh/glossary.md:9` 把 Service Definition 定义为「拥有自身 `ctx.<key>`
和词汇类型的 Cordis `Service`——可以是抽象类，也可以是具体注册表，绝不是 TypeScript
`interface`」，`architecture.md:104` 给出三角色的划分。两处都没有讲重复注册会怎样，
本项目实测补上。
