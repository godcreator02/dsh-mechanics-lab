# dsh-mechanics-lab

DSH 框架层机制的**实验台 + 教材**。目标：把「什么改动是热的、什么必须重启」这件事
从「读源码推理」升级成「跑实验实测、可复跑」。

配套教材是 `index.html`（自包含单文件，浏览器直接开）。每条判定都标注它由哪个实验验证。

## 这箱不是孵化箱

`D:\dshfiles\` 下的其它箱子都是 `dshw_hatch` 孵化出来的**插件项目**，按 dshw 的三层布局
（项目层外层仓 + 内层 dev 仓 + 同级 stable worktree）活。**本箱不是**：

| 孵化箱规则 | 本箱 | 理由 |
|---|---|---|
| 容器 `D:\dshfiles` | ✅ 沿用 | 统一，不散落 |
| 箱名 `yyMMddHH`+3 位小写字母 | ✅ 沿用（`26081520anu`） | 解决容器内命名，与发版无关 |
| 项目层 / 内层同名嵌套 | ❌ 单层 | 没有「思考 vs 货」的双辖区需求 |
| stable worktree 线 | ❌ 无 | 本箱不发版、无消费者 |
| `.dshw.json` / `dshw up` | ❌ 无 | 加了会让**实验 profile** 和 **dshw 沙箱 profile** 混淆 |
| git init | ✅ | 实验结论有历史价值 |
| **「箱内零运行时数据」** | ⚠️ **有意破例** | 见下 |

### 破例声明：箱内有运行时数据（`.testhome/`）

`design.md` 第三节铁律「箱内零运行时数据……整箱是纯 git 项目，可整箱提交、打包、搬走」。
本箱内有一个假 DSH home（`.testhome/`），明显是运行时数据。**这是有意破例，不是手滑。**

- 该铁律的**动机**是「整箱可搬走」。`.testhome/` 已 gitignore，在 git 层面根本不存在，
  动机不受损。
- 换来的收益：实验**可复现**（路径稳定，不随会话消失）、**可整箱删干净**。
- 备选方案（假 home 放系统临时目录）被否：会话一结束实验就不可复现。

## 为什么必须用假 home，不能用 `~/.dsh`

1. **实验 E2 的对象就是 home 级 patch 层**（`$DSH_HOME/cordis.patch.yml`）。这一层的优先级
   **压过每个 profile 自己的活层**，在真 home 测等于同时打进主实例和全部沙箱——往生产线开枪。
2. 裸 profile **没有** autopilot 的 `seedWorkspace: false` 护身符（那是自家插件的行为，
   不是框架的），测试实例会往共享的 `storages/workspace.json` 写。
3. 实验要故意制造挂载失败、反复启停、观察永不过期的负判缓存，需要能整个删掉重来。

假 home 成本很低：`resolveBundleDir` 是 **install anchor 优先**，`dsh-base` / `dsh-web-app`
从 npx 缓存里那份 dsh 安装解析，**不需要 `pnpm install` 进 profile**。

## 端口占用声明

本箱的实例只用 **3090 / 3091 / 3092**——卡在主实例 3080 与 dshw 哈希池 3100–3979 之间的
空隙，dshw 永远分配不到，可与生产实例同时跑。

| 端口 | profile | 用途 |
|---|---|---|
| 3090 | `lab-a` | 活层**有** hmr 常驻反禁用条（复刻主实例形态） |
| 3091 | `lab-b` | 活层**无** hmr 常驻条（出厂形态） |
| 3092 | `lab-bundle` | 装假 profile bundle，测 bundle 层冷热 |

**绝不碰**：3080（主实例）、3239（dsh-letsgo）、3733（dshw-toolchain 沙箱）。

## 实验清单

| 编号 | 测什么 | 起实例？ | 期 |
|---|---|---|---|
| **E1** | patch 的 `config` 是整体替换还是按键 merge | ❌ 静态 | 一 |
| **E2** | home 级 patch 层是否存在、优先级排序 | ❌ 静态 | 一 |
| **E3** | hmr fiber 是否拥有 patch 监听的生死（含 attach 走钢丝风险） | ✅ | 二 |
| **E4** | profile bundle 层冷 vs 活层热，同树 A/B 对照 | ✅ | 二 |
| **E5** | 插件 apply 期 `readFileSync` 的文件是冷的（复现确认） | ✅ | 三 |
| **E6** | client 包元数据负判缓存永不过期 | ✅ | 三 |

第一期两个实验**不启动任何进程**，纯 `--dump-config`，零风险、秒出结果，
跑完即可定案两处已知的正本记载错误。

## 怎么跑

```powershell
cd D:\dshfiles\26081520anu\dsh-mechanics-lab\experiments
. .\lab.ps1                 # 载入公共函数（每个新终端都要先跑这句）
Assert-LabPortsFree         # 确认 3090-3092 没被占

.\E1-patch-config-replace.ps1
.\E2-home-patch-layer.ps1
```

每个实验脚本自带 `-KeepAlive`（跑完不停实例，便于手工 curl 追查）和 `-Verbose`。
原始输出落 `results\E<n>-<时间戳>.md`。

## 收尾

```powershell
. .\lab.ps1
Stop-AllLabInstances        # 停掉本箱起的全部实例
Reset-LabHome               # 删 .testhome 整个重来（不碰 ~/.dsh）
```

整箱删除：先 `Stop-AllLabInstances`，再删 `D:\dshfiles\26081520anu\`。
本箱**不在 dshw 注册表里**，无需 `dshw forget`；**没有 attach 到任何主实例**，无需 `dshw detach`。
