# dsh-mechanics-lab

DeepSeek Harness（DSH）插件系统原理的**独立研究项目**。

搞清楚「插件系统到底怎么工作」，从最简单的「一个插件是什么」讲到最难的
「谁在监听配方文件、它什么时候死」，**每一条判定都配一个能复跑的实验**。

两个产物：

- **实验** —— `experiments/` 下一课一目录，各自完全自包含
- **教材** —— 从简单到困难的原理讲解，每条判定标注由哪个实验验证

怎么在这个项目里干活见 `CLAUDE.md`；课程大纲见 `SYLLABUS.md`；
术语见 `GLOSSARY.md`；探索历史（推翻的判断、走死的路线）见 `trajectory/`。

## 跑

一律经 uv，不激活虚拟环境、不碰全局解释器：

```powershell
uv sync                                              # 首次或依赖变更后
uv run pytest experiments/                           # 全套
uv run pytest experiments/l00_minimal_environment/   # 单跑一课
```

解释器钉死 3.12.10（`.python-version`），依赖锁在 `uv.lock`。

## 实验纪律

| 项 | 规矩 |
|---|---|
| **home** | 只用假 home `.testhome/`——`DSH_HOME` 经子进程 `env` 传入，不改当前进程环境。**绝不碰 `~/.dsh`** |
| **端口** | 只用 **3090–3099**。绝不碰 3080 及 3100 以上——那些可能有别的东西在跑 |
| **删目录** | 逐层拆 junction，绝不跟着链接走（profile 的 `node_modules` 里全是指向源码和缓存的 junction） |
| **并发** | 写作可以并行，**跑实验必须串行**——实验台的锁会自动排队，不必手工协调 |

## 破例声明：箱内有运行时数据

`.testhome/` 是假的 DSH home，实验期间会往里写 profile、日志、见证文件。
它**在箱内**，这是有意的破例：

- 每个实验一个独立 home，**物理隔离**而非靠纪律——home 级 patch 层对该 home 下
  所有 profile 同时生效，靠 `try/finally` 清理兜不住（异常、中断、并发任一都会漏）
- 就近可查：实验失败时日志、profile、活层都在手边

`.testhome/` 不进 git（`.gitignore`），每次跑前清空。观测产物由 pytest 装置自动
归档到 `results/`——那里进 git，是实验证据。

## 整箱删除

先停掉所有实验实例（`uv run pytest` 自己会回收，异常中断的用 `taskkill` 清），
再删整个箱目录。本箱不注册进任何工具链、不 attach 到任何实例，删了不留残留。
