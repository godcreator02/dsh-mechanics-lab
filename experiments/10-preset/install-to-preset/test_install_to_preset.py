"""install-to-preset · 装进 profile、只挂在 preset 的完整链路

档次 ① ｜ 性质 🔬 发现型 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 需要 web

## 要验什么

「给某一类会话单独加一个插件」的可操作路径，端到端跑一遍：

    ① dsh plugin --profile <名> add <本地目录>   代码进 profile/node_modules
    ② 条目写进 user preset 的 agent.cordis.yml    决定谁看得见
    ③ 别的 preset 的会话看不见它

地基已经由 `module-resolution` 坐实（裸包名从 profile 目录解析，profile 装的包
user preset 引用得到）。本项剩下的是**第 ① 步用真命令跑**，以及第 ③ 步的隔离。

关键分支来自 `03-supply/install-command` 的判定：

- 装的包**声明了 `dsh.bundle.patch`** → `reconcilePlugins()` 把包名补进
  `dsh.profile.bundles` → 它的 patch 成为 bundle 层 → 条目进 host 树 →
  **所有 preset 都看得见**
- 装的包**没声明** → 只进 `node_modules`，**一个条目都不产生** → 挂哪儿由人决定

⚠️ 所以「装插件会不会污染所有 preset」的答案取决于包的类型，不是取决于命令。
这条要用两个教学插件（一个带 `dsh.bundle`、一个不带）对照跑出来。

## 为什么还没验

第 ③ 步「别的 preset 看不见」需要读某个 scope 的工具目录，跟
`preset-vs-host-plane` 卡在同一个观测面上。第 ①② 步现在就能跑。

## 实验设计要点

- **`dsh plugin add` 可以真跑**：实验纪律禁的是「对生产 home 跑」和「装会联网
  拉取的包」两件事，不是这条命令本身。同组 `03-supply/four-ways` 已经真跑过一次
  （装本地目录），有归档
- ⚠️ 但 `lab.LabProfile.link_plugin()` 的注释写了：装带 `dsh.bundle` 的包会被
  自动对账进 `dsh.profile.bundles`，若活层又 insert 同一个 id，挂载期会抛
  duplicate loader entry id。本项要的正是那个对账动作，所以**不能**再在活层
  insert 同一个包
- 第 ③ 步在观测面通了之后补；在那之前先把 ①② 跑成两条用例
"""
