"""cold-reads · 插件 `apply` 期主动读的文件是冷的

档次 ② ｜ 性质 🔬 ｜ 状态 ⬜ ｜ 0 条用例 ｜ 不需要 web

## 现状

**没有用例，全仓找过一遍没找到。** `docs/GLOSSARY.md:416-417` 与旧
`docs/SYLLABUS.md:516` 都写着「改 `apply` 期 `readFileSync` 读的文件 → 冷，
无任何反应（它从没进过 ESM loadCache）」并标了「✅ 已验证」，但全仓 grep
`readFileSync`（`experiments/**/*.js`、`**/*.mjs`）零命中——没有任何教学
插件在 `apply` 里用 `readFileSync`/`readFile` 读过外部文件，这条结论目前
只是**源码机制推理**，不是实测结论：

- hmr 主 watcher 的四条分支里，第 4 条「以上都不是 → 只 `emit('hmr/change',
  url)`，没人接」被当成「非 import 文件冷」的实现根因（`docs/GLOSSARY.md:409-418`）
- 唯一贴近的实测证据是 new-code-old-config 项（原 chx ⑧）：bundle 层那份
  `cordis.patch.yml` 落在 watch 范围内、`hmr-change` 点名了它，但没有触发
  重载——它符合第 4 条分支。但那是**框架自己读的 YAML 配置文件**，不是
  「插件在 `apply` 里主动 `readFileSync` 读一个任意文件」，两者共享同一条
  源码分支，不等于同一件事被测过

## 要验什么

补一个教学插件，在 `apply` 里 `readFileSync` 读一个 profile 目录下的任意
文本文件并把内容上报；用例改这个文件的内容，断言：

1. 插件不会自动重新读取（没有第二次上报）
2. 该文件的改动如果落在 watch 范围内，会不会仍然产生一条没人接的
   `hmr-change`（验证「看见了但没人管」而不是「压根没被监听」）
3. 只有让 `apply` 重跑（比如改插件代码触发热重载，或改它的条目 `config`
   触发条目级重放）之后，读到的才是新内容

## 没覆盖到的

整项待建：需要新写教学插件（现有 fixtures 都没有 `readFileSync` 用法）。
"""
