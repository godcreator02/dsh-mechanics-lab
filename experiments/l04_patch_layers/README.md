# L4 · 空根 + 五层叠加

> 6 个用例 ｜ 约 21 秒 ｜ 不需要 web ｜ 📗 复述型（含一条 🔬 增量） ｜ 前置：L2

**这是「二·配方」部分的第一课**，要回答：一棵组合树是怎么从空根（`cordis.yml`
里的 `[]`）之上，逐层叠成生效配置的？

---

## 官方原文（本课的判定基准）

`docs/official/zh/user/develop/basic/publish.md:112-119`：

> 生效配置在空根之上按以下顺序逐层组合：
> 1. profile 的 `dsh.profile.bundles` 列表所列的各个组合包 patch，按列表顺序
> 2. profile 自己的 `cordis.patch.yml`
> 3. home 级的 `$DSH_HOME/cordis.patch.yml`——各 profile 共享的机器本地偏好
> 4. 每个 `--patch <path>` overlay，按 argv 顺序

`docs/official/zh/architecture.md:27` 有一份独立表述，措辞不同、意思一致，
可互相印证：「各层按此顺序应用在空条目列表之上：先按 profile 列出的顺序应用
每个组合包，然后是 profile 的 `cordis.patch.yml`，然后是 home 级的那份，
最后是任意 `--patch` overlay。」

**本课是复述型**：官方已经把顺序讲全了，所以定位是**验证这一版部署的实际
行为与文档承诺是否一致**——一致就复述，不一致才是重大发现。六个用例里
五个是对照式，第六个（运行期改 overlay 文件）文档完全没提，是本课唯一的
增量产出。

```powershell
uv run pytest experiments/l04_patch_layers/ -v
```

---

## 结论速查

| 问题 | 答案 | 状态 |
|---|---|---|
| 四层的来源在 dump 里认得出来吗 | 认得出来：包名 / profile 活层路径 / home 层路径 / overlay 路径 | ✅ 与文档一致 |
| 同一 id 在四层都写，谁赢 | 一层比一层新——bundle → profile → home → overlay | ✅ 与文档一致 |
| home 层文件不存在会怎样 | 等价于「没有这层」，正常启动、正常存活 | ✅ 与调研③一致 |
| home 层内容非法（顶层不是数组）会怎样 | fail loud，报错含固定文本 | ✅ 与调研④一致（⚠️ 出处是源码不是文档） |
| `--patch` 多个时顺序重要吗 | 重要，按 argv 顺序、后者胜出 | ✅ 与文档一致 |
| 运行中的实例改 `--patch` 指向的文件，会热生效吗 | **不会**，改了也没用，得重启 | 🔬 增量，与调研②一致 |

---

## 一、四层各自的来源，dump 里写得明明白白

四层各插一条互不重名的标记条目（`from-bundle` / `from-profile` / `from-home`
/ `from-overlay`），`--dump-config` 的输出里每条都能追出处：

```
from-bundle    来源 = l04-bundle-a
from-profile   来源 = D:\...\.testhome\l04\profiles\identify\cordis.patch.yml
from-home      来源 = D:\...\.testhome\l04\cordis.patch.yml
from-overlay   来源 = D:\...\.testhome\l04\overlay-identify.yml
```

跟文档描述完全对得上：bundle 层标**包名**，其余三层各标**自己那份 patch
文件的绝对路径**。

⚠️ **`DumpResult.source_of()` 的一个实测细节，记录在这里免得后面的课踩坑**：
dump 输出里 `# ==` 来源注释是**按连续同源的条目块标一次**，不是每条都标：

```yaml
# == l04-bundle-a
- id: from-bundle
  ...
- id: shared        # 跟上面同一个来源块，但这一行前面没有 "# ==" 注释
  ...
```

而 `source_of()`（见 `lab/dump.py`）只认「紧邻上方那一行来源注释」，所以只能
认出**每个来源块里的第一条**；块内后续条目会拿到 `None`。这不是 bug，是这个
辅助函数本身的设计边界——本课因此把要测来源的条目都摆在各自 patch 文件的
第一条，`shared`/`order-test` 这两个"同块里的后续条目"只用 `config_of()`
判定，不测它们的 `source_of()`。

## 二、层级是真的分层，不是"最后写的赢"这么简单

同一个 id（`shared`）在四层各出现一次、值不同，逐层叠加、逐层观测：

```
只有 bundle 层：      shared.config = {'layer': 'bundle', 'seq': 1}
叠上 profile 层后：   shared.config = {'layer': 'profile'}
再叠上 home 层后：    shared.config = {'layer': 'home'}
最后叠上 overlay 层： shared.config = {'layer': 'overlay'}
```

每加一层，`shared` 的值就跟着变成那一层写的——不是只测"最终等于 overlay
那句话"能代表的，中间态也完全对得上文档给的顺序。

覆盖用的是裸 `- id:` 语义（不带 `insert`），这不是本课的发现，是 SYLLABUS
里 L5 要展开的既有认知，这里只是借它把"层级"这件事做得看得见。

## 三、home 层缺文件：无害；home 层内容非法：致命

**缺文件**——不建 `$DSH_HOME/cordis.patch.yml`，`dump-config` 照常返回、
实例照常启动，拉起来看 5 秒还活着。跟"已完成的调研③"一致：
`loadOptionalPatches` 遇 ENOENT 返回 `undefined`，等价于"没有这层"。

**内容非法**——把它写成 `foo: bar`（顶层是 mapping 不是数组），`dump-config`
直接失败，退出码 1：

```
Error: dsh: patches D:\...\.testhome\l04\cordis.patch.yml must be a top-level
YAML array of loader patch entries
    at parsePatchList (...\dsh-app-boot\lib\index.js:840:36)
```

⚠️ **这句承诺出自源码 JSDoc**（`dsh-app-boot/lib/index.js:786-787` 一带；
实测报错栈里的具体行号随打包版本可能有出入，但报错**文本**是钉死的），
**不是文档正文**——引用时不能写成"文档说"，这条是"已完成的调研④"给的
提醒，本课实测坐实。

## 四、`--patch` 按 argv 顺序，后者胜出

同一个 id（`order-test`）被两份 overlay 文件各改一次，交换调用顺序，
值跟着翻过来：

```
--patch a b → order-test.config.which = 'b'
--patch b a → order-test.config.which = 'a'
```

跟文档「按 argv 顺序」完全一致。

## 五、（增量）运行中的实例改 `--patch` 文件——改了也没用

这是本课唯一的 🔬 增量，文档完全没提。「已完成的调研②」给出的推论是：
热重放时 `composeLive()` 只现读**两层**——

```js
const composeLive = () => structuredClone([
	...composed.bundlePatches,                                       // boot 时的静态快照
	...loadOptionalPatches(NAME, composed.profile.patchPath) ?? [],  // 每次现读
	...loadOptionalPatches(NAME, homePatchPath()) ?? [],             // 每次现读
	...composed.overlays                                             // boot 时的静态快照
]);
```

bundle 层和 `--patch` overlay 都是 **boot 时的静态快照**，只有 profile 活层
和 home 层每次重放会重新读文件。推论：**运行期改 `--patch` 指向的文件不会
被热重放拾取，必须重启**。

实测：拉起一个实例，`--patch` 指向的 overlay 文件里有个见证插件条目
（`config.value: initial`），等它 apply 一次、写出见证文件确认收到
`initial`；然后**在实例还活着的时候**把 overlay 文件改成 `config.value:
changed`，固定等 10 秒（这是"验证什么都不该发生"，只能用固定等待，
轮询提前退出只能证明"此刻还没发生"，证明不了"不会发生"）：

```
启动后见证文件：[{'value': 'initial', ...}]
（改了 overlay 文件，固定等 10 秒）
等待后见证文件：[{'value': 'initial', ...}]   ← 还是只有一条，还是 initial
```

见证文件全程只有一条记录，`value` 没变过——**推论坐实**：overlay 文件是
boot 时读进来钉死的，运行期怎么改都没用，唯一的办法是重启。

⚠️ **实现细节**：`lab.instance.start_instance()`（公共脚手架）不支持传
`--patch` 参数，按 CLAUDE.md 的实验纪律不能为了这一课去改它。本用例自己
拼了一个最小的启动子进程（参数、环境变量传法跟 `start_instance` 一致，
只是多带 `--patch`），把结果塞进共享的 `Instance` 数据类复用它的
`alive()` / `wait_for()` / `stop()`，并登记进 `running` 夹具保证自动回收。

---

## 本课产出：一个自制的教学组合包

`fixtures/l04-bundle-a` 是一个最小的**组合包**（bundle，不是普通插件）：
manifest 里带 `dsh.bundle.patch` 字段指向自己的 `cordis.patch.yml`
（`docs/official/zh/user/develop/basic/publish.md:42`），用
`profile.link_plugin()` link 进 profile——跟 link 普通插件走的是同一套
机制（`link_plugin` 只关心"写 `dependencies` + 建 `node_modules`
junction"，不关心对方是插件还是组合包），`dsh.profile.bundles` 列表里
写它的包名就能让 dsh 把它当第 1 层组合包读进去。

它的 `cordis.patch.yml` 预先插了三条互不相干的标记条目，各自服务不同用例：

| 条目 id | 服务哪个用例 |
|---|---|
| `from-bundle` | 「四层来源可辨认」 |
| `shared` | 「同一 id 在四层各出现一次，谁胜出」 |
| `order-test` | 「`--patch` 多个时按 argv 顺序」 |

`fixtures/l04-witness` 是给增量用例（六）用的见证插件：把每次 `apply`
收到的 `config` 原样写进一份见证文件，跟 L0 的普查员一样把记录数组建在
模块级、每次写整个数组——这样"被重挂过"和"只 apply 过一次"不会长得一样。

---

## 观测手法：几乎全靠 `dump_config`，不拉实例

四层怎么叠是**配方层面**的事——`--dump-config` 秒级返回，不用起进程、
不用等端口，比拉一个真实例便宜得多。本课六个用例里，只有第六个（增量：
运行期改 overlay 文件）必须拉真进程，因为"热重放到底读没读这个文件"这件事，
静态 dump 回答不了，非看一个活着的进程不可；第三个用例（home 层缺文件）
也顺带拉了一次，因为"dump 不报错"证明不了"能正常启动、能活着"。

**独立 home 的必要性**：本课的实验对象就是 **home 级 patch 文件**——那一层
对本 home 下所有 profile 同时生效。`lab_home` fixture 本身是模块级独立 home，
但同一个模块内的多个用例仍然共享同一个 home，所以本文件另加了一个
`_clean_home_patch` autouse fixture：每个用例跑完自动清掉 home 层，防止
一个用例留下的 home patch 泄漏进下一个用例。
