# 官方文档存档

DSH 官方仓库 `docs/` 目录的完整快照，**215 篇 markdown、2.93 MB**，按语言分成两棵树。

| | |
|---|---|
| 来源 | `github.com/deepseek-ai/deepseek-harness` 的 `docs/` |
| 版本 | **`47f9438`**（钉死的 commit，不是 `master`） |
| 拉取时间 | 2026-08-16 |

```
docs/official/
├── README.md   ← 本文件（我们写的，不属于任何一侧）
├── zh/         中文 105 篇  ← 平时看这个
└── en/         英文 110 篇
```

**两侧目录结构完全一致**：同一条相对路径就是同一篇文档的两个语言版本。
比如 `zh/user/develop/basic/publish.md` 和 `en/user/develop/basic/publish.md`。

## 中英差 5 篇

`en/` 多出来的这 5 篇没有中文版，全是仓库内部工作文件、不是用户向文档：

| 文件 | 是什么 |
|---|---|
| `AGENTS.md` | 给 AI 助手的仓库指示 |
| `cordis-api/inherited.md` | Cordis API 的继承成员清单 |
| `i18n/style-samples.md` | 翻译风格样例 |
| `i18n/terminology.md` | 术语对照表 |
| `i18n/translation-prompt.md` | 翻译用提示词 |

`zh/` 里没有只此一份的文件——中文是英文的完整子集。

## 中文的可信度

**不是机翻。** 仓库有一套双语配对机制（`zh/i18n/README.md` 有完整说明）：
每对文档由 `foo.md` + `foo.zh.md` + 一份记录两侧内容哈希的 `foo.i18n.yaml` 组成，
配对必须整体合并，PR 不允许只改一侧。`cordis-api/` 那几篇开头还写着
「本中文文件是通过双语配对维护的经评审对侧」。

结构一致性也有门禁：标题深度与顺序、列表项数量、表格行列数、链接目标、
**逐字节一致的代码块**——两侧一一对应。

## ⚠️ 我们的目录结构和官方是反的

官方在 `zh/i18n/README.md` 里明确写了它的约定：

> 一对文档是三个同目录文件……**不用语言目录**，不用独立翻译仓库，不用中英混排的单文件。

我们这里偏偏用了语言目录。理由是**用途不同**：

- 官方要**维护**双语——同目录才能让配对门禁、链接校验、逐字节比对跑起来
- 我们只**读和 grep** ——混在一起的话每次 grep 都是双份命中，噪声一倍

### 代价：跨语言链接失效

每篇开头那行 `[English](xxx.md)` / `[中文](xxx.zh.md)` 现在指不到东西了
（`.zh.md` 后缀已去掉，两侧也不在同一目录）。**篇内的相对链接同样如此**。
这是重组的已知代价——存档是拿来读的，不是拿来渲染成网站的。

要跳到另一语言版本，把路径里的 `zh/` 换成 `en/` 即可，其余部分一模一样。

## 目录导览（按对本实验台的价值排序）

以下路径都相对 `zh/`（英文同路径换 `en/`）。

### 🔴 `cordis-api/` — 机制的一手正本

**从源码注释自动生成**（`scripts/gen-cordis-catalog.ts`），每条都带源码行号链接。
这是全套文档里最精确的部分，讲的正是我们在研究的东西。

| 文件 | 讲什么 | 关联 |
|---|---|---|
| `fiber.md` | Fiber 完整 API：`state` / `uid` / `update()` / `restart()` / `effect()` / **`getEffects()`** | L5、L6、**L13** |
| `context.md` | Context 的 API | L3 |
| `registry.md` | 插件注册表 | L4 |
| `service.md` | Service 基类 | L3 |
| `events.md` | 事件 API | 观测台 |

⚠️ **`fiber.getEffects()` 是个一直没用上的现成观测接口**——返回当前 fiber 上所有
已注册 effect 的元数据树（带 label，形如 `ctx.on("event")`）。L13 要查
「hmr 的 patch watcher 还在不在」，用它可以**直接看**，不必靠「改文件看有没有反应」
这种间接观测——而间接观测正是 v1 E3 整批数据作废的原因。

### 🟠 `user/develop/` — 开发者教程（2026-08-16 已通读中文版）

`basic/`（index → tool → config → publish）+ `framework/`（index / service / events）
+ `practice/`。**比预期详细得多**——对照盘点见 `DRAFT.md` 第八节，
其中 12 条是我们绕远路重新发现的。

### 🟠 `subsystems/` — 92 篇，每个子系统一篇

`core.md`（56 KB）里有自动生成的 `cordis-surface` 区块，列出每个服务的签名与
触发模式。要查「某个服务由谁提供、有哪些方法」看这里。

### 🟡 `postmortem/` — 官方事故报告，只有 4 篇但都是真事故

| 编号 | 事故 | 关联 |
|---|---|---|
| 0001 | default export 导致 `inject` 丢失 | L3 |
| 0002 | **`!!js` 表达式意外禁用了文件系统工具** | **L2** |
| 0003 | web agent GUI 反馈环 | — |
| 0004 | landlock 部分通知误判子进程失败 | — |

### 🟡 根目录的单篇

`glossary.md`（**官方术语表**）、`architecture.md`、`cordis-primer.md`、
`config-catalog.md`（133 KB，全部配置项）、`module-graph.md`、
`capability-seams.md`、`defensive-patterns.md`、`testing.md`。

### 🟢 `cordis-tutorial/` — 16 篇，从零搭 Cordis

不依赖 DSH、不需要 API key，在临时目录里动手。适合补 Cordis 本身的基础。

### ⚪ `cookbook/`、`user/guide/`、`i18n/`

应用层与使用者向，与插件加载机制关系不大。

## 怎么重拉

两步：下载，然后按语言重组。

```powershell
$sha  = (Invoke-RestMethod "https://api.github.com/repos/deepseek-ai/deepseek-harness/commits/master").sha
$dest = "<新目录>"   # 换个目录另存，别覆盖旧版——两版并列才能看出文档改了什么

$tree = Invoke-RestMethod "https://api.github.com/repos/deepseek-ai/deepseek-harness/git/trees/$sha`?recursive=1"
$tree.tree | Where-Object { $_.path -match '^docs/.*\.md$' } | ForEach-Object -ThrottleLimit 8 -Parallel {
    $out = Join-Path $using:dest (($_.path -replace '^docs/','') -replace '/','\')
    New-Item -ItemType Directory -Force (Split-Path $out -Parent) | Out-Null
    Invoke-WebRequest "https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/$using:sha/$($_.path)" -OutFile $out
}

# 重组：*.zh.md → zh/ 去后缀，其余 *.md → en/
foreach ($f in Get-ChildItem $dest -Recurse -File -Filter *.md) {
    $rel = $f.FullName.Substring($dest.Length + 1)
    $to  = if ($rel -like '*.zh.md') { Join-Path "$dest\zh" ($rel -replace '\.zh\.md$','.md') }
           else                      { Join-Path "$dest\en" $rel }
    New-Item -ItemType Directory -Force (Split-Path $to -Parent) | Out-Null
    Move-Item -LiteralPath $f.FullName -Destination $to -Force
}
```

## 为什么钉 commit 而不是拉最新

我们的实测结论是**对着某一版文档**说「这条文档写了 / 没写 / 写得不一样」的。
文档会改，一旦拉了新版，所有这类对照就失去基准，分不清是「我们看错了」还是
「文档后来改了」。

## 使用纪律

**文档是证据，不是结论。** 它写的是设计意图与承诺的行为，我们测的是这一版部署
的实际行为，两者可能不一致——**那种不一致恰恰是本实验台最有价值的产出**。

引用时永远标明出处与版本，例如
「`docs/official/zh/user/develop/basic/publish.md:123`（`47f9438`）」，
不要写成「官方说……」。
