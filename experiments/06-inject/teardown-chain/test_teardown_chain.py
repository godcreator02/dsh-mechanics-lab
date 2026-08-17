"""teardown-chain · 服务消失时依赖方的下场

档次 ② ｜ 性质 📗 复述型 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 不需要 web

## 判定

无——本项没有配套用例，以下只是要验什么与为什么还没验。

官方文档已写明（`docs/official/zh/user/develop/framework/service.md:102-109`，
「服务消失时的行为」一节）：

> 如果应用运行期间某项必需服务消失（例如其提供方卸载）：
> 1. 依赖它的插件会自动 dispose（资源释放）
> 2. 当服务重新出现时，插件自动重新加载

这条跟 06-inject 其余三项的差别在于**时机**：`inject-hard-dependency` /
`dependency-chain` 验的都是「boot 期依赖从一开始就没满足」；这一条问的是
「服务在**运行中**消失、又**运行中**恢复」——依赖方要能跟着起落两次，且中间不
需要重启实例。这正是 `inject` 硬依赖契约里官方明确承诺、但本仓还没实测过的
那一半。

## 没覆盖到的

要验的两段行为：

1. **消失即卸载**：起一条 `lab-registry` ← `lab-alpha` 的链，稳定运行后，
   不重启实例、只把 `lab-registry` 的活层条目改成 `disabled: true`（走热重放，
   见 05-reload 的机制），观察 `lab-alpha` 是不是被自动 dispose——判据可以是
   `lab-alpha` 提供的下游服务消失、或者挂采集器直接看它的 fiber 状态从
   `ACTIVE` 走到 `UNLOADING`/`DISPOSED`
2. **恢复即重载**：把 `lab-registry` 的 `disabled` 改回 `false`，观察
   `lab-alpha` 是否自动重新 apply（见证文件的 `appliedAt` 应该刷新成新的
   时间戳），不需要人工触发，也不需要重启实例

关键的观测面仍然是 fiber 状态与见证文件，跟本组其余用例一致；难点在于要在
**同一个运行中的实例**里连续制造两次状态迁移并分别捕捉到，而不是像
`inject-hard-dependency` 那样只看 boot 时的一次性结果。
"""
