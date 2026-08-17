# dsh-mechanics-lab

DeepSeek Harness（DSH）插件系统原理的**独立研究项目**。

搞清楚「插件系统到底怎么工作」——从「一个插件是什么」到「谁在监听配方文件、
它什么时候死」。**每一条判定都配一个能复跑的实验**，没有实验支撑的不算判定。

产物只有一个：`experiments/` 下的实验台。一项一目录，各自完全自包含——
一份用例、一份教学插件、跑出来的归档，**判定写在用例文件的模块 docstring 里**。
没有另一份文档，读用例的人不用翻第二个文件。

怎么在这个项目里干活见 `CLAUDE.md`；其余文档在 `docs/` 下——
覆盖清单 `docs/SYLLABUS.md`（有哪些机制、谁管、验没验）、术语 `docs/GLOSSARY.md`、
探索历史 `docs/trajectory/`、官方文档快照 `docs/official/`。

## 跑

一律经 uv，不激活虚拟环境、不碰全局解释器：

```powershell
uv sync                                            # 首次或依赖变更后
uv run pytest                                      # 全套
uv run pytest -m static                            # 只跑不起进程的
uv run pytest experiments/01-entry/                # 单跑一组
uv run pytest experiments/01-entry/disabled/       # 单跑一项
uv run pytest experiments/01-entry/disabled/ -n 0  # 关并行，看清输出或用 pdb
```

解释器钉死 3.12.10（`.python-version`），依赖锁在 `uv.lock`。

默认 `-n 10 --dist loadfile`。全套串行要 8 分钟，其中九成时间是在干等固定观测窗口
——那些窗口 CPU 基本空着，并行几乎白赚。削不掉的是需要 `dsh-web-app` 真启动的那几项，
并行的下限就卡在它们身上。

端口段 3090–3099 只有十个，是硬边界。项数远超 worker 数，所以用端口的项打了
`xdist_group` 标记钉在固定 worker 上。

## 实验纪律

**规矩写在 `CLAUDE.md` 第四节**，一处定义。一句话概括：只碰假 home、只用 3090–3099、
删目录逐层拆 junction、`dsh plugin` 只许对假 home 跑。**违反会打到生产实例上。**

## 破例声明：箱内有运行时数据

```
out/testhome/          假 DSH home，一项一个子目录。整个 out/ gitignore
experiments/…/results/ 每次运行的观测归档，跟着实验走。也 gitignore
```

运行时数据**在箱内**，这是有意的破例：

- 每个实验一个独立 home，**物理隔离**而非靠纪律——home 级 patch 层对该 home 下
  所有 profile 同时生效，靠 `try/finally` 清理兜不住（异常、中断、并发任一都会漏）
- 就近可查：实验失败时日志、profile、活层都在手边

两样东西分开放是有原因的。**归档是纯文件**，所以住各实验目录下，点开一项就看得到
它跑出来什么（观测产物 + 当时的配置现场 + summary，留最近三次）。**假 home 不行**——
它的 `profiles/*/node_modules/` 是指向 npx 缓存与本仓源码的 junction 农场，进了源码树，
任何递归遍历都会跟着走出去（ripgrep 扫进缓存、pytest 收到链接那头的用例、IDE 索引吃 CPU）。

两者都不进 git，因为**跑一次就能再生**。归档留着是为了跑完能翻——并行之后终端输出
是交错的，看 `results/<时间戳>/summary.md` 比翻 scrollback 靠谱。它不是为了长期保存
证据：**证据的归宿是那一项 docstring 里的结论**，不是原始 json 躺在仓库里。

每项的假 home 在跑那一项时先整个清空再重建，跑完留着。

## 整箱删除

先停掉所有实验实例（`uv run pytest` 自己会回收，异常中断的用 `taskkill` 清），
再删整个箱目录。本箱不注册进任何工具链、不 attach 到任何实例，删了不留残留。

⚠️ **删 `out/` 要逐层拆 junction，绝不跟着链接走**——profile 的 `node_modules`
里全是指向 fixtures 和 npx 缓存的 junction（实测一次全套跑完有五千多条）。
用现成的：

```powershell
uv run python -c "import sys; sys.path.insert(0,'experiments'); from lab.core import rmtree_safe, OUT_DIR; rmtree_safe(OUT_DIR)"
```
