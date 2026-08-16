# 官方文档存档

DSH 官方仓库 `docs/` 目录的完整快照，**215 个 markdown 文件，2.93 MB**。

| | |
|---|---|
| 来源 | `github.com/deepseek-ai/deepseek-harness` 的 `docs/` |
| 版本 | **`47f9438`**（钉死的 commit，不是 `master`） |
| 拉取时间 | 2026-08-16 |
| 目录结构 | 与仓库 `docs/` 下一致（去掉了 `docs/` 前缀） |

## 为什么钉 commit 而不是拉最新

我们的实测结论是**对着某一版文档**说「这条文档写了 / 没写 / 写得不一样」的。
文档会改，一旦拉了新版，所有这类对照就失去基准，分不清是「我们看错了」还是
「文档后来改了」。要更新就换个目录另存一份，两版并列。

重拉的命令记在本文末尾。

## 中英文

每篇都有两个版本：`x.md`（英文）和 `x.zh.md`（中文）。**中文不是机翻**——
仓库里有 `verify-translation-pairing` 脚本维护双语配对，`cordis-api/` 那几篇
的开头还写着「本中文文件是通过双语配对维护的经评审对侧」。

grep 时建议只搜 `*.zh.md`，否则每条命中都是双份。

## 目录导览（按对本实验台的价值排序）

### 🔴 `cordis-api/` — 机制的一手正本

**从源码注释自动生成**（`scripts/gen-cordis-catalog.ts`），每条都带源码行号链接。
这是全套文档里最精确的部分，讲的正是我们在研究的东西。

| 文件 | 讲什么 | 关联 |
|---|---|---|
| `fiber.zh.md` | Fiber 的完整 API：`state` / `uid` / `update()` / `restart()` / `effect()` / **`getEffects()`** | L5、L6、**L13** |
| `context.zh.md` | Context 的 API | L3 |
| `registry.zh.md` | 插件注册表 | L4 |
| `service.zh.md` | Service 基类 | L3 |
| `events.zh.md` | 事件 API | 观测台 |

⚠️ **`fiber.getEffects()` 是个我们一直没用上的现成观测接口**——它返回当前 fiber
上所有已注册 effect 的元数据树（带 label，形如 `ctx.on("event")`）。
L13 要查「hmr 的 patch watcher 还在不在」，用它可以**直接看**，
不必靠「改文件看有没有反应」这种间接观测。

### 🟠 `user/develop/` — 开发者教程（本次点名要读的）

`basic/`（index → tool → config → publish）+ `framework/`（index / service / events）
+ `practice/`。**比预期详细得多**，见下面的盘点。

### 🟠 `subsystems/` — 92 个文件，每个子系统一篇

`core.zh.md`（56 KB）里有自动生成的 `cordis-surface` 区块，列出每个服务的
签名与触发模式。要查「某个服务由谁提供、有哪些方法」看这里。

### 🟡 `postmortem/` — 官方事后分析，只有 4 篇但都是真事故

| 编号 | 事故 | 关联 |
|---|---|---|
| 0001 | default export 导致 `inject` 丢失 | L3 |
| 0002 | **`!!js` 表达式意外禁用了文件系统工具** | **L2** |
| 0003 | web agent GUI 反馈环 | — |
| 0004 | landlock 部分通知误判子进程失败 | — |

0002 讲的正是我们 L2 测过的 `!!js` 条件表达式——**官方踩过坑并写了报告**。

### 🟡 根目录的单篇

`glossary.zh.md`（**官方术语表**）、`architecture.zh.md`、`cordis-primer.zh.md`、
`config-catalog.zh.md`（133 KB，全部配置项）、`module-graph.zh.md`、
`capability-seams.zh.md`、`defensive-patterns.zh.md`、`testing.zh.md`。

### 🟢 `cordis-tutorial/` — 16 篇，从零搭 Cordis

不依赖 DSH、不需要 API key，在临时目录里动手。适合补 Cordis 本身的基础。

### ⚪ `cookbook/`、`user/guide/`、`i18n/`

应用层与使用者向，与插件加载机制关系不大。

## 怎么重拉

```powershell
$sha = (Invoke-RestMethod "https://api.github.com/repos/deepseek-ai/deepseek-harness/commits/master").sha
$dest = "<新目录>"
$tree = Invoke-RestMethod "https://api.github.com/repos/deepseek-ai/deepseek-harness/git/trees/$sha`?recursive=1"
$tree.tree | Where-Object { $_.path -match '^docs/.*\.md$' } | ForEach-Object -ThrottleLimit 8 -Parallel {
    $out = Join-Path $using:dest (($_ -replace '^docs/','') -replace '/','\')
    New-Item -ItemType Directory -Force (Split-Path $out -Parent) | Out-Null
    Invoke-WebRequest "https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/$using:sha/$($_.path)" -OutFile $out
}
```

## 使用纪律

**文档是证据，不是结论。** 它写的是设计意图与承诺的行为，我们测的是这一版部署
的实际行为，两者可能不一致——**那种不一致恰恰是本实验台最有价值的产出**。

所以引用文档时永远标明出处与版本，例如
「`user/develop/basic/publish.zh.md` 第 123 行（`47f9438`）」，
不要写成「官方说……」。
