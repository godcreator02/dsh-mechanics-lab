# plan：把说明页做完

## ① 档已完工

**① 档 23 项的页全部到位**：11 项新画（`insert-semantics` / `override-semantics` /
`four-ways` / `self-registration` / `pinned-worktree` / `replay-mechanism` /
`cold-surfaces` / `ignore-rules` / `reload-unit` / `new-code-old-config` /
`inject-hard-dependency`），3 项从旧规格翻新（`layer-stack` / `watch-root` /
`activation-order`），9 项此前已合格（`00-base` 四项 ＋ `01-entry` 五项）。

全仓 58 项现有 28 页。下一轮的目标由用户定，候选顺序见文末。

⚠️ **`h2` 数量少不等于缺层。** `baseline-profile` 的第一层完整写在 `h1` 与第一个
`h2` 之间、不戴标题帽子；`framework-fallback` / `apply-runs` / `config-delivery` /
`inject-field` 的判定卡不另立 `h2`。这几页四层都齐。真正缺层的是 `h2` 只有 1–2 个
那几张——门禁的 `?` 提示用来挑出该人读的页，不是判据。

⚠️ **`01-entry/name-resolution` 开篇有一处「其实」落在机制讲完之前**，门禁会一直
提示它。那句修饰的是「四种写法实测只有两条算法」这个机制陈述、不是抛盲区，
判为可接受；要改就顺手改，别当 bug 追。

## 全局账目

58 项、17 页已有。剩 41 页，按 SYLLABUS 的状态标记分：

- **有判定 28 项**（含两个特殊形态，见下）
- **未覆盖 ⬜ 13 项**

⚠️ **别拿「用例数是不是 0」当筛选条件**，要看 SYLLABUS 的状态标记。两者在
`02-recipe/dump-fidelity` 上给出相反答案：它 0 条用例，但标 ⚠️ 不是 ⬜——判定有源码
证据（`cordis-plugin-include/src/index.ts:58-128` 的 `applyEntryPatches()`）加一条从
`recipe-vs-tree` 借来的断言，而且它是 02 组其余四项敢只用静态 dump 判定的前提。
按未覆盖形态去画它，等于把一条地基判定当成空白展示。

## 已定的做法

- **翻新 6 页旧规格排在最后**，不打头。41 页写下来必然会发现骨架还得调，翻新在前
  要翻两次；那 6 页现在至少能看，空白页是真空白。其中 `layer-stack` / `watch-root` /
  `activation-order` 是 ① 档，也照这条推后
- **翻新时补原理层，观测层直接搬旧页的图和数字**。只换骨架不补原理层等于给不成立的
  页刷新漆（page-writing 第二节：四层缺一层页面就不成立）；当新建页重写又太贵
- **门禁住 `experiments/lab/pagegate.py`，进 git。** 它是 page-writing 的机器化表达，
  规范在它就该在

## 骨架不下放

**共享的 CSS 与 JS 由主会话写，agent 只写本页内容。** 这条是买来的：上一轮五个 agent
并行写同一个组件，长出了五种实现（`cnode` / `mstep` / `step-btn` / `mech-item` /
`steplist`）和三份 CSS 变体。

要动 `lab.css` / `lab.js` 时，主会话改完再派活；agent 的任务书里写死「不许改这两个文件、
不许另起类名」。

## 验收：每批四步，一步都不能省

1. **门禁全绿**——`uv run python experiments/lab/pagegate.py <本批各页>`。
   它查外链、双主题、`test_xxx` 真实存在、无自动播放、归档目录存在、只引
   `lab.css` / `lab.js`，以及内联原文与磁盘一致（整份逐字相等；出处带 ` · <哪一段>`
   的按片段比对）
2. **浏览器里跑 `experiments/lab/pagecheck.js`**——它把每个 picker 项、每个折叠开关、
   每个文件行都点一遍，收 `onerror` 与 `console.error`，并报出点开是空的死行。
   门禁抓不到运行时报错——`config-delivery` 的 `initPicker` 撞 null 就是这么漏出去的，
   而那个 agent 的自查报告是全绿的。起法与注意事项写在那个文件的头注释里
3. **看折行与溢出**——`pagecheck.js` 的 `wrapped` 与 `overflowX` 两项，再截图扫一眼。
   `field-vocabulary` 的表格第三列被挤到 48px、「必填与否」竖成一字一行，
   脚本一个字都查不出来
4. **读 agent 改了什么，别只扫结论**——`isolation-guarantees` 那次把 `bmHighlight()`
   留下改指向新侧栏，报告里写的是「统一改指向新侧栏」，听着像在遵守规格，实际是反的

任务书里要求 agent 把门禁的**原始输出**贴回报告，不接受「我跑了，是绿的」——三次事故
全是同一类：agent 自查报告不可信，而现有应对全在下游加网。

做完更新 `experiments/index.html` 的 `HAS_PAGE` 集合，然后提交。

## 已知的坑

按踩到的顺序记，都是会重复发生的：

- **内联文件原文不能走「读出来再抄进去」**。工具展示文本会把 CRLF 显示成 LF、
  把 NUL 这类不可见字节吞掉，照抄就跟磁盘对不上而且看不出来。必须字节级读写。
  门禁按 `INVISIBLE` 逐个核对不可见字符的出现次数；行尾符差异不算内容差异
- **门禁扫「页面行为」的几项要先摘掉 `<pre>`**。内联的真实源码里有 `setInterval`，
  被当成自动播放。否则页面越忠实于原文越容易被判违规，逼人改内容迎合检查
- **PowerShell 的数组会扁平化**。`@(@(a,b))` 摊成两个字符串后 `$pair[0]` 取到的是
  首字符，`.Replace('v','a')` 把全文的 `v` 换成了 `a`。批量替换用 Python 写显式映射表
- **自己的正则也会骗人**。`^[^\{\}]*` 里 `[^\{\}]` 包含换行，能从文件开头一路吞到
  几百行之后，拼出来的「内容错乱」是工具造的假象。核内容用 DOM 或字节比对，别用正则
- **改 CSS 层叠顺序要有安全网**。抽共享样式会改变规则先后，用全元素计算样式快照
  前后对比兜底。**统一飘掉的规则时不能要求 0 差异**，要逐条审差异是不是预期内的
- **Chrome 截图会 CDP 超时**，重试一次通常好；连续失败改用脚本量（`getBoundingClientRect`
  比截图更准，也不受窗口宽度影响）
- **页内样式的体量不能在浏览器里量。** 浏览器扩展往 `<head>` 注入自己的 `<style>`
  ——实测 8 个、七千多字节，把页面自己的 1259 字节淹掉一个数量级。照这个数去对
  agent 的自报值，会得出「它虚报了十倍」的假结论。样式体量在磁盘上量
- **`file://` 打不开页面**（扩展拒绝 browser-internal URL），要起本地静态服务器。
  用 8791 一类的端口，**别占 3090–3099**——那是实验的段
- **改了文件要加查询参数才刷新**（`?v=2`），否则读缓存
- **同一个标签页里上一轮的点击状态会留下**，误判成 bug。核默认状态要干净加载后立刻读

## 剩下 30 页的候选顺序

② 档有判定页 → ③ 档有判定页 → 翻新剩下 3 页旧规格（`07-tree/recipe-vs-tree`、
`08-service-core/one-owner`、`09-boot-vs-runtime/duplicate-id-timing`，`h2` 只有
1 / 3 / 2 个）→ 未覆盖 13 页。

**每一档开工前重算一次账目，别照抄这里的数字**——页做掉了账就变。用
`uv run python experiments/lab/pagegate.py` 扫一遍，`?` 提示会把缺层的页挑出来。

特殊项到时候按各自形态处理：

- **`03-supply/install-command`**：1 条用例但没有归档。数字无处可取，页面上一个数字
  都不许有，按「有机制依据、无观测数据」的形态做
- **`02-recipe/dump-fidelity`**：0 用例但有判定，按部分覆盖形态做，不按未覆盖
- **`09/boot-failure-shapes`**：9 个 profile、8 条用例（参数化），全仓最重的一项
