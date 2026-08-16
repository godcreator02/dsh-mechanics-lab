# L6 · bundle 层 vs 活层

> 3 个用例 ｜ 约 70 秒 ｜ **需要 web** ｜ 📗 部分复述 + 🔬 发现型 ｜ 前置：L5

**这一课回答：** 两层的分工与冷热差别——改 bundle 的 patch 文件、改
`dsh.profile.bundles` 名单，对**正在跑的实例**有没有影响？把包从 bundles 名单
摘掉、但活层里还 `insert` 着同一个包，这个包是不是就真的没了？

跑法：`uv run pytest experiments/l06_bundle_vs_live/ -v`

📗 **文档侧**（`docs/official/zh/user/develop/basic/publish.md`）讲全了两种
manifest（`dsh.bundle` vs `dsh.profile`）、层顺序（bundles → profile 活层 →
home 层 → `--patch` overlay）、`dsh plugin add` 的转发行为。**本课不重复这些
——只测文档没写的那部分：冷热差别，以及 `dsh plugin add` 之外「手改文件」这条
没人写但完全合法的路。**

---

## 结论速查

| 问题 | 答案 |
|---|---|
| 改 bundle 自己的 `cordis.patch.yml`，运行中实例会变吗 | **不会**。必须重启 |
| 改 profile 的 `dsh.profile.bundles` 名单，运行中实例会变吗 | **不会**。必须重启 |
| 两者是同一种"冷"吗 | 是——**都是同一处代码没在监听**造成的（见下） |
| `--dump-config` 看得到"改了但还没重启"这件事吗 | **看得到，但那不是运行中实例的状态**——它是纯读盘的静态合成 |
| 包从 bundles 摘掉、活层还 insert 着同一个包，条目会消失吗 | **不会**，且**重启后依然存活**——两条注册路径互不相干 |
| bundle 层和活层用同 id `insert` 同一个包会怎样 | 撞在**首次 boot**，`duplicate loader entry id`，**整个进程启动失败** |

---

## 一、两种"冷"，一个根因

v1 的结论是"改 bundle 的 patch 文件、或改 `dsh.profile.bundles` 名单，对正在跑
的实例毫无影响，必须重启"。这次用 Python 独立复跑，两件事挤在**同一个实例
存活期内**挨个撞：

```
初次响应：{'appliedAt': '...02.785Z', 'configRevision': 'r1'}
改完 patch 之后，静态 --dump-config 已经算出新值：'r2'
运行中实例的响应（bundle patch 已经改了）：{'appliedAt': '...02.785Z', 'configRevision': 'r1'}   ← 没变
重启后的响应：{'appliedAt': '...18.588Z', 'configRevision': 'r2'}                                  ← 变了
摘掉 bundles 名单后、运行中实例的响应：{'appliedAt': '...18.588Z', 'configRevision': 'r2'}          ← 没变
重启后（bundles 名单已经不含探针包）：None                                                          ← 条目整个消失
```

**与文档一致，且一致得比预期更彻底**：两种改动表现完全一样——运行中实例
`appliedAt` 纹丝不动，`moduleLoadedAt` 更不用说，重启后才双双生效。

这不是巧合，是**同一个根因**：L4/L7 已经立住的地基是"配方装在 `include` 这个
条目的 `config.patches` 里，活层热重放的实现就是重新 compose 出 patches、
`entry.update({config})`"。而 `watchUserPatches` **只**给 profile 活层文件和
home 层文件注册了 watcher——`dsh.profile.bundles` 这个列表本身、以及列表里
每个 bundle 自己的 `cordis.patch.yml`，物理上**没有任何代码在监听**。不是
"故意不响应"，是压根没人往这个方向看一眼。

`--dump-config` 在这中间是个陷阱：它是**纯读盘**的静态合成，改完 bundle 的
patch 文件之后立刻能看到新值（上面的 `r2` 就是这么读出来的），但那跟"运行
中进程里的状态"是两回事——本课的核心就是拿这组对照把两者的界线钉死。
⚠️ 判断"进程内状态有没有变"绝不能拿 `--dump-config` 当证据，理由见项目
`CLAUDE.md` 观测方法论第 6 条。

## 二、两条注册路径互不相干

```
活层 insert、包不在 bundles 名单里：{'configRevision': 'live-insert'}
重启后：{'configRevision': 'live-insert'}   ← 照样在
```

`link_plugin()` 只做两件事：往 profile 的 `package.json` 加一行 `dependencies`
（`link:` 协议），往 `node_modules` 建一条 junction。这两件事只关系到
**Node 模块解析**——`import("l06-probe-bundle")` 能不能找到代码。至于这个包
是不是 `dsh.profile.bundles` 名单里的一员，是完全独立的另一件事：那份名单
只决定"要不要把这个包自己的 `cordis.patch.yml` 也叠进配方"。

活层自己的 `- insert:` 不需要经过 bundles 名单这条路——它是配方的另一层，
直接按包名引用即可，只要模块解析得到就行。所以"包没在 bundles 名单里"和
"包提供的条目没在树里"是两件不能互相推出的事，且这条独立性**扛得住重启**：
不是热重放期间"暂时还没被清"的假象，是两套注册路径本来就没有交叉。

**这条独立性有实际用处**：插件供给可以走**纯活层形态**（`link:` 依赖 + 活层
`insert`，完全不进 bundles），照样挂得上，也不会因为名单里没有它而被清掉。

## 三、同 id 双挂载：撞在首次 boot 就是整个进程死掉

```
Error: dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include): duplicate loader entry id: probe
TypeError: duplicate loader entry id: probe
    at EntryGroup.update (...cordis-plugin-loader/lib/index.js:81:28)
    at Include._apply (...dsh-app-boot/lib/index.js:238:19)
    ...
    at async mountRootInclude (...dsh-app-boot/lib/index.js:984:20)
    at async boot (...dsh-app-boot/lib/index.js:1175:3)
```

机制链条（源码坐实，三段拼起来）：

1. `cordis-plugin-include` 的 `applyEntryPatches`：`- insert:` 语义是
   `data.push(...insert)`——**不按 id 去重**。bundle 层的 `probe` 和活层的
   `probe` 都用 `insert` 写法，于是最终合成的条目列表里**真的有两个 id
   相同的对象**，不是被去重成一个又神秘复活。
2. 这份列表整个交给 `EntryGroup.update()`（`cordis-plugin-loader`），它在
   **创建任何条目之前**先扫一遍查重：

   ```js
   for (const options of config) {
     const id = this.tree.ensureId(options)
     if (seen.has(id)) throw new TypeError(`duplicate loader entry id: ${id}`)
   }
   ```

   查重循环在 `try` 块**之外**——这是"整批提前拒绝"，不是"先挂上去、
   建好一部分之后再回滚"。
3. 这个 `update()` 正是 `mountRootInclude()` 挂载 include 子树时调用的那个
   （`Group` 的 `Service.init` 里 `await this.update(this.config)`）——也就是
   说，撞车发生在 **boot 阶段挂载配方树的第一步**，早于 `dsh-base` 的 78 个
   条目里任何一个被创建。日志里 `Include._apply` 那一帧就是这个调用点。

`dsh-app-boot` 把这个 `TypeError` 原样包了两层（`updateError` → `boot` 的
`throw new Error(...)`）往外抛，进程以退出码 1 结束——**日志里能直接看到
"duplicate loader entry id: probe"**，不需要去猜。

⚠️ 项目 `CLAUDE.md` 记的是"撞在运行中热重放 = 只打一条警告、这次重放作废、
旧条目继续跑"，跟本课"撞在首次 boot = 整个进程死掉"是**两个不同的时机**，
后果完全不同——别把两条判定混成一条。本课只验了 boot 期这一半。

## 四、实验台自己的 `link_plugin()` 为什么绕开 `dsh plugin add`

`dsh plugin add` 装完会按"安装后的实际状态"对账：任何声明了 `dsh.bundle` 的
包，都会被自动追加进 `dsh.profile.bundles`。而本课的教学插件
`l06-probe-bundle` 恰好**同时**：

- 声明了 `dsh.bundle`（它是一个组合包）
- 又想在某些用例里**单独**用活层 `insert` 挂它（用例 3 就是这么干的）

如果走 `dsh plugin add`，这两件事会自动叠成同 id 双挂载——正是上面第三节
撞车的配方。`link_plugin()` 手动做「link 依赖 + junction」而不碰
`dsh.profile.bundles`，把"这个包能不能被 import"和"这个包是不是 bundles
名单成员"两件事解耦开，才让用例 1/2（包在 bundles 里）和用例 3（包不在
bundles 里，靠活层单独 insert）能用同一个教学插件复用，不用为每条用例
另造一个包。

## 五、观测手法

`fixtures/l06-probe-bundle` 身兼两职：既是"组合包"（`package.json` 声明
`dsh.bundle.patch`，指向同目录的 `cordis.patch.yml`——与官方 publish.md 的
hello-plugin 一模一样的写法），又是自己那份 patch 指向的插件模块本身。

探针路由 `GET /l06-probe/state` 回四个字段，缺一不可：

| 字段 | 只有什么情况会变 |
|---|---|
| `marker` | 改了这个源文件本身（本课全程没变过，用来确认真的是同一份代码） |
| `moduleLoadedAt` | 模块被**重新 import**——冷重启是一种，代码热重载是另一种 |
| `appliedAt` | **apply 被重跑**——不需要重新 import 也能变（纯 config 热重放） |
| `configRevision` | config 里的 `revision` 值，回显当前挂着的是哪一版 |

本课全程 `moduleLoadedAt` 和 `appliedAt` 要么一起不变（真正的"冷"），要么
重启后一起变（全新进程，模块重新 import、apply 重跑一次）——没有出现
"`appliedAt` 变了但 `moduleLoadedAt` 没变"这种"纯 config 热重放"的中间态。
这跟 L14 要测的活层热重放不是一回事：**本课测的两种改动压根没有被任何
watcher 看见，连"重放"这个动作都没发生**，不是"重放了但没生效"。

写法上跟 l00 的普查员一脉相承：观测点绝不抛错（探针路由天然满足——连不上
就是连不上，不会把"插件没装上"和"插件抛异常"混成一个结果）；`Instance.json_at`
校验响应体而不是只看状态码（dsh 的 web 应用对未匹配路径回 200 + SPA 兜底
HTML，本课用例 1 最后一步"包已从 bundles 摘掉、重启后条目消失"正是靠这条
纪律才没有假阳性——如果只看状态码，那次请求同样会是 200）。

## 六、这一课立住的词

- **组合包（bundle）/ profile bundle** —— 冷。`dsh.profile.bundles` 名单和
  每个 bundle 自己的 `cordis.patch.yml`，物理上没有 watcher 在盯
- **活层** —— 热。改动秒级触发 `include` 条目的 `config.patches` 重新 compose
- **两条独立的注册路径** —— "包是不是 bundles 名单成员"（决定要不要叠它的
  bundle patch 层）与"包能不能被 `import(name)` 解析"（决定 `link_plugin`
  建没建 junction）互不相干，且这条独立性扛得住重启
- **整批提前拒绝** —— 同 id 双挂载撞在 boot 期的失败模式：查重发生在创建
  任何条目之前，不是"先挂后回滚"

⚠️ 术语陷阱提醒：`bundle` 一词二义——本课全程说的都是**profile bundle**
（冷）。**client bundle**（浏览器 JS，热，L16 的主题）是完全不同的东西，
提到时务必分清指的是哪一个。

## 七、下一课

**L7 · 配方 ≠ 树** —— 从"两层怎么叠成一份配方"转向"配方变成了什么"：
`--dump-config` 算出来的东西，和进程里真正跑着的那棵树，差在哪。
