# plan：实验说明页铺开到 00–03

## 现状

六页样板已成并逐页验过：`watch-root`、`recipe-vs-tree`、`layer-stack`、
`activation-order`、`duplicate-id-timing`、`one-owner`。
入口是 `experiments/index.html`（58 项覆盖地图，可按档次和「还没验的」筛）。

## 硬规格（派 agent 时整段给它）

**页面只负责让人看懂，不负责举证。** 判定的唯一正本是各项 `test_*.py` 的模块 docstring。

- 别把 docstring 抄一遍，页面要精简，**用图和动画代替文字**
- 每块图标出它对应哪个用例（`test_xxx`），读者追证据去 docstring
- **页面上的数字必须来自 `results/` 归档**，footer 标明取自哪一次。**不许编**
- 数字是**一次观测的快照**，不需要跟 docstring 同步；判定才需要，而判定不上页面

**交互按内容性质选**：

| 性质 | 用什么 |
|---|---|
| 过程（有时间顺序） | 分步：`← 上一步 / N / M / 下一步 →`，每步一句说明 |
| 查询（并置状态） | hover 为主 + 分步辅助；hover 是临时预览、不改分步指针，移开回指针那一步 |
| 关系（结构性） | 静态 + 联动高亮，辅以分步 |

**不许自动播放。** 节奏归读者——自动播放的毛病是读者还在读标题、动画已经放完了，
想看清某一步只能重放整段。

**技术**：自包含单文件、样式脚本内联、无外部资源、双主题
（`prefers-color-scheme` + `[data-theme]` 两套都要）、原生 CSS/JS 不引图表库。
控件 CSS 从 `experiments/05-reload/watch-root/index.html` 逐段抄。

## 分批（每批验完再下一批）

| 批 | 组 | 项数 |
|---|---|---|
| 一 | `00-base` | 5 —— 含一个「没数据」项，第一批就把那种形态定下来 |
| 二 | `01-entry` | 6 |
| 三 | `02-recipe` | 4（`layer-stack` 已做） |
| 四 | `03-supply` | 6 |

## 每项的图型判断（已过一遍，别推翻重来）

**很值得画**

- `name-resolution` —— 三条解析路径的分支 + Windows 裸盘符那个矫正点
- `override-semantics` —— 覆盖前后的键差（整键赋值不是深合并）
- `four-ways` —— 四条路殊途同归
- `supply-x-activation` —— 三条正交轴
- `disabled` —— 树上还在但没 fiber

**值得**

`recorder-reach`、`minimal-profile`、`framework-fallback`、`inject-field`、
`insert-semantics`、`cross-layer-targeting`、`self-registration`、`pinned-worktree`

**图帮不上忙**（做极简页或跳过，**别为凑数造图**）

`field-vocabulary`（六个字段一张表就完了）、`config-delivery`（贴 YAML 再贴收到的对象）、
`apply-runs`、`install-command`

**没有归档数据**（`isolation-guarantees`、`dump-fidelity`、`client-side`）

0 用例、`results/` 是空的。整页标「未覆盖」，画**缺口**——要验什么 / 为什么还没验 /
补上需要什么装置。**视觉上必须跟已验项区分开**，别让读者以为它跟别的页一样确凿。

## 验收（每批都要做，不能只看 agent 报告）

1. 起静态服务：工作目录 `experiments/`，`uv run python -m http.server 8901 --bind 127.0.0.1`
2. **脚本验分步逻辑**（比截图可靠）：走完全程看每步的点亮数、字幕、`pos`、首末按钮
   disabled；倒回第一步看重置干不干净；hover 之后看分步指针有没有被改掉
3. **截图看视觉**——对齐、重叠、颜色
4. 跑门禁：外链数为 0、双主题齐全、页面引用的 `test_xxx` 在代码里真实存在
5. 做完更新 `experiments/index.html` 的 `HAS_PAGE` 集合

## 已知的坑

- **Chrome 扩展不能导航 `file://`**，必须起本地 HTTP 服务
- **改了文件要加查询参数才刷新**（`?v=2`），否则读缓存——为此白改过一次
- **窗口太宽时截图只覆盖左边一部分**（视口 1966 CSS px 时截图只有 1568），
  先 `resize_window` 到 1280×900
- **截图会 CDP 超时**，重试一次通常就好；连续失败改用脚本验证
- **一页可以有多个独立分步序列**（`one-owner` 有两个舞台），那时 id 要带序号、
  方向键按鼠标所在舞台分派
- **`goto()` 跳步时，如果每步的 `fn` 是增量改动，必须先重置再从头重放**，
  否则跳步错乱；顺带清掉裸 `setTimeout` 的残留定时器
