# L2 · 条目的字段

**这一课回答：** 一个条目能写哪些字段、各管什么、写了会怎样。

跑法：`uv run pytest experiments/l02_entry_fields/`（约 38 秒，6 个用例）

本课只讲字段的**静态语义**（写下去、启动、看效果）。「**运行中**改字段会怎样」
属于热重放的范畴，留给 L10——那里才有把「重放到底发生没发生」测干净的工具。

---

## 一、条目只有六个字段

权威清单来自 `cordis-plugin-loader` 的 `EntryOptions` 接口：

| 字段 | 类型 | 管什么 |
|---|---|---|
| `id` | string | **树内地址**。patch 靠它定位条目 |
| `name` | string | **模块说明符**。loader 拿它去 Node 那儿 resolve |
| `config` | any | 传给 `apply(ctx, config)` 的第二个参数 |
| `disabled` | boolean \| `!!js` | 挂不挂。见下 |
| `group` | boolean | 标记这是个嵌套条目组（容器） |
| `inject` | Inject | 该条目需要的服务 / 服务拦截配置（L3 详讲） |

**实测**：一棵只叠 `dsh-base` 的真实组合树（79 个条目）里，出现过的字段只有四个：

```
config, disabled, id, name          ← 实际用到
group, inject                       ← 一次都没出现
```

`inject` 一次没出现是有信息量的——**服务依赖主要声明在插件代码里**
（`export const inject = ["webServer"]`），条目上的 `inject` 字段是**可选的覆盖/补充**。
`dsh-web-app` 的 patch 里就有 `inject: [webStartup]` 这样的条目级声明，
但那是少数派。这条留到 L3 展开。

## 二、不认识的字段：带着走，不报错

patch 能往条目里塞任意键（`applyEntryPatches` 就是 `target[key] = value`，不筛）。
实测塞一个 `野字段: "loader 不认识我"`：

- 它**进了组合树**，dump 里看得见
- 插件**照常加载**，没有任何警告或报错

所以 patch 里字段名写错不会报错——它不是「非法」，只是**没人读**。
这是个真实的踩坑面：`disable: true`（少个 d）不会有任何提示，条目照常运行。

## 三、`disabled`：不挂载，不是删除

```yaml
- id: lab-fields
  name: lab-fields
  disabled: true
```

实测：条目**仍在组合树里**（dump 看得见、patch 还能按 id 定位它），只是 `apply` 不执行。

这个区分要紧：**禁用是可逆的，删除不是**。把 `disabled` 改回 `false` 条目就回来了，
而删掉条目之后，patch 想再改它只会得到一句
`patch: entry "xxx" not found` 的警告然后静默跳过。

### `disabled` 可以是 `!!js` 表达式

不止能写布尔值，还能写延迟求值的表达式，在条目激活时才算：

```yaml
disabled: !!js process.platform === 'win32'
```

官方 `dsh-base` 就用这招做平台条件禁用。实测两个变体（本机是 win32）：

| 表达式 | 结果 |
|---|---|
| `process.platform === 'win32'` | ❌ 未加载（条件成立 → 禁用） |
| `process.platform === 'linux'` | ✅ 加载（条件不成立） |

预期正好相反的一对，比断言一个死值更能证明**表达式真的被求值了**。

⚠️ 注意：静态 `--dump-config` 里保留的是**表达式原文**，不是求值结果——
dump 是静态展开，不求值。想知道某条实际上启不启用，只能看运行时。

## 四、`config` 是任意 JSON

嵌套对象、数组、`null`、浮点，原样送达 `apply` 的第二参：

```yaml
config:
  嵌套: {层一: {层二: [1, 2, {深处: "到底了"}]}}
  数组: ["甲", "乙", "丙"]
  空值: null
  浮点: 3.14
```

loader 对 config 的**结构**不做任何约束。约束来自插件自己声明的 schema——
如果它声明了的话。（严格校验 config 的插件遇到未知键会直接抛错，
这一点在后面讲强制重放时还会遇到。）

## 五、源码旁注：几条本课没实测的机制

以下来自 `cordis-plugin-loader/src/config/entry.ts` 的阅读，**尚未实测**，
按本项目的纪律它们只能作为「为什么」的解释，不能单独当判定依据。
相关的都排进了后续课程：

| 机制 | 源码怎么说 | 归属 |
|---|---|---|
| **禁用向下传播** | `_disabled()` 会沿父链向上追溯，任一祖先禁用则本条目不运行 | L6 |
| **group 永远启用** | `if (options.group) return false`——group 自己不受 `disabled` 影响，但它的孩子会因父级禁用而停 | L6 |
| **改 `config` 是原地 reconfigure** | `replace = diff.some(key => key === 'name' \|\| 'inject' \|\| 'group')`；不在这三个里就只走 `fiber.update(config)`，**不 dispose fiber** | L10 |
| **改 `name`/`inject`/`group` 是重建** | 重新 import + dispose 旧 fiber + 重新 start | L10 |
| **`null` 是删除键** | `if (isNullable(value)) delete candidate[key]` | L10 |
| **无差异即空操作** | `if (!diff.length && !force) return` | L10 |

其中第三条尤其值得记一笔：它是「运行中改一个条目的 config 会不会导致该插件被
卸载重建」这个问题的源码答案，而这个问题在 v1 的探索里一直悬着。L10 会把它测实。

## 六、关于 `group`：本课不实测，如实说明

`group` 的语义是「这个条目是个**嵌套条目组**」，它的 `config` 就是子条目数组；
带 id 的 `- insert:` 就是往某个 group 里塞孩子（无 id 的 insert 则追加到根）。

**但官方 DSH 部署里一个 group 条目都没有**——`dsh-base` 和 `dsh-web-app`
两个 bundle 的 patch 文件里，`group` 一次都没出现。

所以本课只说明其语义，不做实测：它属于 cordis loader 的能力，不在 DSH 的日常路径上。
真要用到时（比如需要给一组插件做统一的服务隔离），再单独补一课。

## 七、这一课立住的词

- **禁用（disabled）** — 条目在树里但不挂载，可逆
- **`!!js` 表达式** — 延迟到激活时、在条目自己上下文里求值的配置值
- **野字段** — patch 能写、loader 不读的键；写错字段名的静默失败面

## 八、下一课

**L3 · 服务与 `inject`** —— 谁提供服务、谁依赖它、依赖没到位时会等还是会挂。
「小型依赖系统」从这一课开始登场。
