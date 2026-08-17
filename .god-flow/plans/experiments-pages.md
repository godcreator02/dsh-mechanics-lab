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

**每个分步舞台正上方放一块底座参考块**（`.basemap`，代码骨架见文末附录）。
左栏 profile 文件树、右栏插件文件树，都要完整不裁剪，每行右边一句话说这个文件
干什么，当前这步在动哪个文件就点亮哪一行。

判据是：页面直接画「patch 里插了什么、树上长出哪几条」，读者却不知道 patch 文件
住在哪、旁边还有什么文件、插件本身是几个文件——**没有这层，图讲的东西是悬空的**。
树里的文件名对着 `results/*/profiles/` 与本项 `fixtures/` 写，跟数字一样不许编。

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

---

## 附录：底座参考块的代码骨架

### 它解决什么

00-base 的页面开门见山就画「patch 里插了什么、树上长出哪几条」，但从没告诉读者
**patch 文件住在哪、旁边还有什么文件、插件本身是几个文件**。参考块补的就是这个。

### 放哪

**每个带分步舞台的小节，正上方放一块。** 一页有两个舞台就放两块，各自独立联动。
位置在小节标题 `<h2>` + `.note` 之后、舞台容器之前。

### 硬规矩

1. **树必须完整、不裁剪**。左栏 profile 树从 `$DSH_HOME/` 起，右栏插件树从
   `fixtures/` 起，中间层级一个不省
2. **文件名必须真实**——profile 树对着 `results/<最新一次>/profiles/` 的实际内容写，
   插件树对着本项 `fixtures/` 目录的实际内容写。**一个文件名都不许编**
3. **每行右边配一句话说这个文件干什么**——这就是「基本介绍」，不要另写文字段落
4. 高亮跟着分步指针走：这一步在动哪个文件，那一行点亮，其余压暗

### CSS（照抄，只改 `--bmhit` 取值让它跟本页配色不撞）

```css
/* ── 底座参考块：这一节在动哪个文件 ── */
.basemap{display:grid;grid-template-columns:1fr 1fr;gap:16px;
  background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:14px 16px;margin:0 0 14px}
.bm-h{font-family:var(--mono);font-size:11px;color:var(--dim);
  margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.bm-tree{list-style:none;margin:0;padding:0;font-family:var(--mono);font-size:11.5px}
.bm-tree li{display:flex;gap:10px;align-items:baseline;padding:2.5px 6px;
  border-radius:5px;transition:background .2s,opacity .2s}
.bm-tree li .bm-n{white-space:pre;flex:none}
.bm-tree li .bm-c{font-size:11px;color:var(--dim);line-height:1.5;
  font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.bm-tree li.dim{opacity:.35}
.bm-tree li.hit{background:color-mix(in srgb,var(--bmhit) 14%,transparent);
  box-shadow:inset 2px 0 0 var(--bmhit)}
.bm-tree li.hit .bm-n{color:var(--bmhit);font-weight:600}
.bm-tree li.hit .bm-c{color:var(--fg)}
@media (max-width:700px){.basemap{grid-template-columns:1fr}}
```

`--bmhit` 三处都要定义（`:root`、`prefers-color-scheme:dark` 那套、`[data-theme=dark]` 那套）。

### HTML 骨架

`data-f` 是这一行的键，分步那边靠它点名。缩进用制表画线字符写在 `.bm-n` 里，
`white-space:pre` 会原样保留。

```html
<div class="basemap" id="bm1">
  <div>
    <div class="bm-h">profile 树 · 实验跑起来时假 home 里的样子</div>
    <ul class="bm-tree">
      <li data-f="home"><span class="bm-n">$DSH_HOME/</span><span class="bm-c">假 home，一项一个，住 out/testhome/&lt;项名&gt;/</span></li>
      <li data-f="homepatch"><span class="bm-n">├─ cordis.patch.yml</span><span class="bm-c">home 级活层，压过下面每个 profile 自己的</span></li>
      <li data-f="logs"><span class="bm-n">├─ logs/</span><span class="bm-c">实例的 stdout / stderr</span></li>
      <li data-f="profiles"><span class="bm-n">└─ profiles/</span><span class="bm-c"></span></li>
      <li data-f="farm"><span class="bm-n">   ├─ node_modules/</span><span class="bm-c">符号链接农场，dsh 自己维护；timer / hmr 这些裸包名靠 Node parent-walk 在这里解析</span></li>
      <li data-f="prof"><span class="bm-n">   └─ rooted/</span><span class="bm-c">一个 profile</span></li>
      <li data-f="pkg"><span class="bm-n">      ├─ package.json</span><span class="bm-c">dsh.profile.bundles 名单 ＋ dependencies（link: 供给）</span></li>
      <li data-f="yml"><span class="bm-n">      ├─ cordis.yml</span><span class="bm-c">恒为 []，每次启动被 profile-boot 重写</span></li>
      <li data-f="patch"><span class="bm-n">      ├─ cordis.patch.yml</span><span class="bm-c">活层 —— 实验改的就是这个文件</span></li>
      <li data-f="nm"><span class="bm-n">      └─ node_modules/</span><span class="bm-c"></span></li>
      <li data-f="junction"><span class="bm-n">         └─ base-census →</span><span class="bm-c">junction，指向下面那棵插件树</span></li>
    </ul>
  </div>
  <div>
    <div class="bm-h">插件树 · 本项用的教学插件</div>
    <ul class="bm-tree">
      <li data-f="plugpkg"><span class="bm-n">fixtures/base-census/</span><span class="bm-c">包型插件：有 package.json，靠包名引用</span></li>
      <li data-f="plugpkg"><span class="bm-n">├─ package.json</span><span class="bm-c">name / type:module / exports</span></li>
      <li data-f="plugidx"><span class="bm-n">└─ index.js</span><span class="bm-c">export function apply(ctx, config)</span></li>
    </ul>
  </div>
</div>
```

### JS 契约

**必须带 scope 参数**——一页可能有两块，不能互相串。

```js
/** 点亮这一步在动的文件；keys 为空时整块复原。 */
function bmHighlight(scopeEl, keys){
  const set = new Set(keys || []);
  scopeEl.querySelectorAll('li[data-f]').forEach(li => {
    li.classList.toggle('hit', set.has(li.dataset.f));
    li.classList.toggle('dim', set.size > 0 && !set.has(li.dataset.f));
  });
}
```

在本节原有的 `render(i)` 末尾加一行调用，键从该步的数据里取：

```js
bmHighlight(document.getElementById('bm1'), STEPS[i].files);
```

**hover 预览也要联动**，规矩跟别处一致：hover 临时点亮被预览那张对应的文件，
`mouseleave` 回落到当前分步指针那一步。

### 两种插件形态（按本项实际用到的画，别画没用到的）

```
包型插件                                  裸文件插件
fixtures/base-census/                     fixtures/neighbor.mjs
├─ package.json   name/type/exports       单文件，没有 package.json、没有构建
└─ index.js       export function apply   export const inject = [...]
                                          export function apply(ctx, config)
```

