"""client-side · 带浏览器端的包怎么被认出来

档次 ③ ｜ 性质 📗 复述型 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 需要 web

## 要验什么

一个包声明 `dsh.client`（`platform: 'web'`，可选 `inject` 依赖边、可选
`immediately`）并在 `exports["./client"]` 导出构建好的 bundle，就能加入
client 模块表。要验的是这条扫描与缓存机制：

- **按包名增量扫描。** `ctx.clientModules` 构造时同步跑一次激活扫描——已加载
  条目里有格式错误的声明或缺失的 bundle，会聚合成一次响亮的抛错（FAILED
  fiber，boot 末尾的激活普查会报出来）
- **包元数据按包名缓存，包括负判（「这不是 client 包」），且永不过期。**
  插件集变化要等重启才生效；fiber 重启会复用同一行和同一个 `rev`，bundle
  内容变化只经 `rebuilt()` 那条路进图
- 落到本项要验的具体行为：**负判一旦进了缓存，后续给这个包补上
  `dsh.client` 声明也不会让它变成 client 包**——要等进程重启

## 出处

📗 官方文档已经写明这条机制（复述型，直接对照文档断言即可）：

> Package metadata — including the negative "not a client package" verdict —
> is cached per name and never expires: plugin-set changes take effect on
> restart. A fiber restart reuses its row and rev untouched; bundle content
> changes reach the graph only through `rebuilt()`.

出处：`docs/official/en/subsystems/client-modules.md:53`（源码指向
`packages/client/modules/src/client/manifest.ts`，同篇文档开头有链接；仓库
中文版是同一相对路径下的 `docs/official/zh/subsystems/client-modules.md`，
两侧目录结构一致）。`docs/GLOSSARY.md` 里也有一行摘要（「快照面」小节，
`pkgMeta` 负判缓存那一行），本项与它是同一个事实，不重复展开。

## 没覆盖到的

这一项目前只有文档复述，没有用例——按纪律不能为了覆盖率造用例。要坐实需要
一个带 web 的实例，装一个负判会被缓存的包、观测「运行中补声明不生效、重启后
生效」这条时序，比对照文档断言更进一步。

⚠️ 更广的「client 双面插件」主题（host/client 通信、slot 语义、
`inject: ["loader"]` 死锁陷阱等）素材在 `.god-flow/drafts/l16-client-plugin.md`
——那份草稿的范围比本项宽得多，而且草稿自己写明「client 模块表怎么增量扫描 /
负判缓存」不是它要做的（那部分是本项的地盘）。本项只管上面「要验什么」列的
那部分；草稿里其余素材（双面插件怎么搭、插槽语义、host 半边读状态的判据）
不在本项范围内，哪一课要接手由后续开工时决定。
"""
