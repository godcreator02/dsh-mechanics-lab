# 把一个插件接进来的几种办法

> 4 个用例 ｜ 约 35 秒 ｜ **不需要 web** ｜ 🔬 发现型 + 📗 部分复述

**这一课回答：** 手上有一个插件——自己写的、别人给的、从 npm 装的——把它接进一个
实例，有几种办法？各自换一版要付什么代价？

跑法：`uv run pytest experiments/plugin_wiring/ -n 0 -s`

📗 **文档侧**（`docs/official/zh/user/develop/basic/publish.md`）讲了两种 manifest
（`dsh.bundle` vs `dsh.profile`）、层顺序、`dsh plugin add` 的行为。**本课不复述这些**
——它换一个切法：官方是**枚举做法**，本课是**拆维度**，拆完之后那些做法自己长出来，
还多出两个官方没提的格子。

---

## 结论速查

| 问题 | 答案 |
|---|---|
| 「接进来」是一个动作吗 | **不是，是三个正交的动作**：供给 / 激活 / 版本钉法 |
| 包声明了 `dsh.bundle`，就会自注册吗 | **不会**。还得被列进 `dsh.profile.bundles`，两个条件缺一不可 |
| 供给方式（相对路径 / junction / git 工作副本）影响热重载吗 | **不影响**。三种在「改代码」上表现一致，全热 |
| 那什么决定冷热 | **激活轴**。活层 insert 热，bundle 层自注册冷 |
| 一次 `git checkout` 同时改了代码和 bundle patch，会怎样 | **两个轴分道扬镳**：代码热了，bundle 层纹丝不动，重启才生效 |
| hmr 是不是没看见 bundle patch 的变化 | **看见了**（有 `hmr-change` 事件），但对树没有任何影响 |
| hmr 的 `root` 能指到 profile 目录外吗 | 能写进配置，但**收不到变更事件**（实测对照） |

---

## 一、三条轴

「把插件接进来」在这套系统里不是一个动作，是三个——而且它们**互不影响**：

| 轴 | 问的是 | 取值 |
|---|---|---|
| **供给** | `name` 怎么被 resolve 成一个真实文件 | 相对路径 / junction（`link:`）/ 钉 tag 的 git 工作副本 |
| **激活** | 条目怎么进树 | bundle 层自注册 / 活层 `insert` |
| **版本钉法** | 换一版时动哪个文件 | 改代码本身 / 改 bundle 自己的 patch / 换 git tag |

⚠️ **拆轴不是为了好看，是因为枚举会漏格。** 官方那套「四种交付途径」枚举的是常见
组合；三条轴一乘就能看出还有别的格子，本课的形态 D 和 F 就是被枚举漏掉的两个，
而 D 恰恰是日常最常用的形态之一。

## 二、六种形态

| 形态 | 供给 | 激活 | 换一版要动什么 |
|---|---|---|---|
| A | 相对路径（文件在 profile 目录里） | 活层 insert | 改文件 |
| B | junction（`link:` 到一个包） | 活层 insert | 改文件 |
| C | junction | **bundle 层自注册** | 改文件 / 改 bundle 自己的 patch（**冷**） |
| D | junction（**声明了 `dsh.bundle` 却没进名单**） | 活层 insert | 改文件 |
| E | git 工作副本（钉 tag） | 活层 insert | 改文件 |
| F | git 工作副本（钉 tag） | **bundle 层自注册** | 换 tag（代码热、bundle 层冷） |

实测五种（A–E）同时挂在一个实例里全部上树，互不干扰；F 单独一个 profile。

### D 这一格：声明了 ≠ 被激活

`route-d` 的包**声明了 `dsh.bundle.patch`**，它自带的 patch 里 insert 了一个
`id: route-d-selfmounted`、config 写着 `层版本: d-r1-NEVER-APPLIED` 的条目。
用例把这个包 link 进 profile 但**不**列进 `dsh.profile.bundles`，改在活层自己
insert 一条 `id: route-d`。

实测：`d-r1-NEVER-APPLIED` 在整条事件流里出现 **0 次**。

**「包声明了 `dsh.bundle`」和「这叠 patch 会生效」是两件事**，中间隔着
`dsh.profile.bundles` 那份名单。这条的实际用处是：第三方 bundle 包也可以**不让它
自注册**——把条目控制权拿回自己手里，id 和 config 全由你定，还顺带把它从「冷」
搬进了「热」。

⚠️ 但**不能两条路一起走**：同一个包既进名单又在活层 insert 同一个 id，会撞
`duplicate loader entry id`，整个进程死在 boot。所以实验台一律用 `link_plugin()`
手工 link，**绝不用 `dsh plugin add`**——那个命令会把声明了 `dsh.bundle` 的包
自动追加进名单，正好凑成撞车的配方。

## 三、题眼：一次 checkout，两个轴分道扬镳

形态 F 让供给轴和激活轴同时动起来：包由 git 工作副本供给，又走 bundle 层自注册。
`v1 → v2` 这个 tag 里**同时**改了两样东西——`index.js` 里的代码版本、
`cordis.patch.yml` 里的层版本。一条 `git checkout v2` 把两个文件一起换掉：

```
checkout 前：{代码版本: 'f-v1', 层版本: 'f-r1'}
checkout 后：{代码版本: 'f-v2', 层版本: 'f-r1'}   ← 代码变了，层没变
重启后：    {代码版本: 'f-v2', 层版本: 'f-r2'}   ← 层这才跟上
```

**同一次文件系统改动，两条轴给出了完全不同的反应。** 这是三条轴正交最直接的实证
——它们不是分析框架，是系统本身的结构。

### 而且 hmr 明明看见了

事件流里两条 hmr 事件都在：

```
hmr-change  → .../route-f-src/cordis.patch.yml    ← 看见了 bundle patch 变了
hmr-reload  → .../route-f-src/index.js            ← 代码这条真的重载了
```

所以 bundle 层的冷**不是「没人监听」**——watcher 明明报告了那个文件的变化，
hmr 只是不认得这是一份需要重读的 bundle 配置。用例 3 用另一条路独立复现了同一现象：
改 `route-c` 的 `cordis.patch.yml`，同样只出 `hmr-change`，层版本纹丝不动。

根因在启动时就定死了：整叠 bundle patch 在 boot 时被读成内存里的数据，之后
**热重放重新 compose 时用的还是那份内存快照，根本不重读磁盘**。文件变没变、
watcher 看没看见，都进不到那条路上。

## 四、hmr 只认 watch root 覆盖到的文件

本课六个形态的真身**全部落在 profile 目录里面**（B/C/D 拷贝进去，E/F 的 git
工作副本直接建在里面），hmr 只配一条 root：`['.']`。

这不是图省事：

- **junction 那一层本身是死路** —— hmr 默认 `ignored` 名单里有 `**/node_modules`
- **profile 目录外的 root 收不到事件** —— 即使把绝对路径写进 `config.root` 也不行

对照实测（其余条件不变，只挪工作副本的位置）：

| 工作副本在哪 | hmr root | E / F 的结果 |
|---|---|---|
| profile 目录**外** | `['.', '<绝对路径>']` | **一个 hmr 事件都没有** |
| profile 目录**内** | `['.']` | 正常热重载 |

机制上对得起来：hmr 的 watcher 把 chokidar 的 `cwd` 设成 profile 目录，
`ignored` 判定走 `relative(profile, path)`——落在外面的路径算出来是 `..\..\` 开头。

⚠️ 所以「worktree 双线」这套玩法有个前置条件：**工作副本必须落在 watch root
覆盖得到的地方**，否则换 tag 之后什么都不会发生。

## 五、观测手法

全程走 `observatory/lab-recorder` 事件流，不用 HTTP 探针——不需要 `dsh-web-app`，
四个用例合计约 35 秒。

每个教学插件 apply 时上报同一个结构，一条事件同时带齐两条轴的读数：

```js
say("我上树了", { 形态: "X", 代码版本: CODE_VERSION, 层版本: config?.层版本 ?? null });
```

- `代码版本` 是模块顶层常量 → **供给轴**的读数（它变了说明模块被重新 import）
- `层版本` 从 config 读 → **激活轴**的读数（它变了说明配方重新算过）

两个读数在同一条记录里，才能看清「一个变了另一个没变」这种分道扬镳。

⚠️ 跨两程的用例（3、4）**重启前必须把 `events.jsonl` 挪走**：采集器每次挂载会把
它清空重写，但旧进程死掉到新进程写第一行之间有个窗口，这期间轮询会读到上一程的
残留、把「上一程说过的话」当成「这一程已经说了」。挪走的那份留着一起归档。

⚠️ 判断某个形态有没有变，信号必须落在**它自己那条上报**上。拿别的条目判会得到
恒真结果——那些条目本来就不该变。

## 六、这一课立住的词

- **三条轴（供给 / 激活 / 版本钉法）** —— 正交，可以自由组合；拆轴能推出枚举漏掉的格子
- **声明 ≠ 激活** —— `dsh.bundle` 只是包的自我声明，`dsh.profile.bundles` 才是那份名单
- **冷热由激活轴决定，不由供给轴决定** —— 三种供给方式在改代码这件事上完全一致
- **「看见了也不管」** —— bundle 层的冷不是没人监听；watcher 报告了变化，但那条路
  通不到树上，因为数据源是 boot 时的内存快照
- **watch root 覆盖不到 = 等于没有** —— 写进 `config.root` 不代表收得到事件
