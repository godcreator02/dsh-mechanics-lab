# L1 · 插件的最小形态

**这一课回答两个问题：** 一个 DSH 插件最少需要什么才能被加载？以及——
怎么从**外部**证明它真的被加载了，而不是听它自己说？

跑法：`uv run pytest experiments/l01_minimal_plugin/`（约 32 秒，8 个用例）

---

## 一、观测手段：见证文件，不是日志

判断「插件被加载了」不能靠日志——日志会被吞、被缓冲、被格式变化骗过去。
本课的插件在 `apply()` 里**写一个见证文件**，内容是三个指纹：

| 字段 | 含义 | 用途 |
|---|---|---|
| `marker` | 代码里写死的版本串 | 改了它就能证明跑的是新代码 |
| `moduleLoadedAt` | **模块顶层**求值的时刻 | 变了说明模块被重新 `import` 过 |
| `appliedAt` | `apply()` 执行的时刻 | 变了说明 apply 重跑过 |

文件存在与否是硬事实。而且这样本课**不需要 webServer**——profile 只叠
`@deepseek-ai/dsh-base` 就能跑，启动快一大截。

> **「被加载」的可操作定义就是「`apply` 被执行」。** 静态看配方只能证明
> 「配方里写了它」，证明不了「它真的跑了」。本课两样证据都取。

## 二、插件的最小家当

```
lab-minimal/
  package.json    { "type": "module", "exports": { ".": "./index.js" } }
  index.js        export function apply(ctx, config) { ... }
```

就这些。不 inject 任何服务、不注册路由、不碰 UI——刻意做到最小，
这样「它被加载了」就没有任何别的解释。

## 三、实测结论

### 1. 最小形态的边界不在 `exports`，在「Node 能不能 resolve 到入口」

最初的假设是「`exports["."]` 是必需项」，**被实测推翻**。Node 的解析有回退链：

```
exports["."]   →   main   →   默认 index.js
```

四个变体实测：

| 变体 | 结果 |
|---|---|
| `exports["."]` 指向入口 | ✅ 加载 |
| 无 `exports`，入口恰好叫 `index.js` | ✅ 加载 |
| 无 `exports`，但 `main` 指向入口 | ✅ 加载 |
| 无 `exports`、无 `main`、入口又不叫 `index.js` | ❌ 不加载 |

三条路任意一条通就行，全断才真的加载不了。

所以写作契约里「`exports["."]` 指向真实存在的 host 入口」是**推荐做法**
（显式，而且能同时声明 `./client`、`./package.json` 等子路径），不是 Node 的硬性要求。

**附带发现**：三条路全断时，**实例进程直接退出**（实测 `实例还活着=False`）——
解析不到插件是 fail-loud，不是静默跳过。

### 2. dump 把每个条目的出身写在脸上

`--dump-config` 会给**每个**条目标来源注释，而且两种层用两种形式：

```yaml
# == @deepseek-ai/dsh-base                          ← bundle 层：标包名
- id: timer
  name: '@deepseek-ai/cordis-plugin-timer'

# == D:\...\profiles\l01-static\cordis.patch.yml    ← 活层：标 patch 文件的绝对路径
- id: lab-minimal
  name: lab-minimal
```

最初的假设是「活层条目没有来源注释」，也**被实测推翻**——它有，只是形式不同。
这比原以为的更有用：**「这条是谁塞进来的」从来不用猜。**

被多层改过的条目还会写明经手人，形如
`@deepseek-ai/dsh-base, patched by @deepseek-ai/dsh-web-app`。

### 3. `id` 是树内地址，`name` 是模块解析名

两者毫无关系。把 id 改成 `完全不像包名的别名`，插件照常加载：loader 拿 **name**
去 resolve 模块，拿 **id** 在树里定位条目。后续 patch 想改这个条目时，用的是 id。

### 4. `config` 原样送达 `apply` 的第二个参数

活层条目里 `config:` 写什么，`apply(ctx, config)` 就收到什么，中文键也一样：

```
{'witness': '...', '口令': '洛阳纸贵', '数字': 42, '开关': True}
```

### 5. 一点规模感

只叠 `dsh-base` 一个 bundle 的 profile，组合树就有 **79 个条目**。
「装一个 bundle」= 「往配方里叠一整叠 patch 指令」，不是「加一个插件」。

模块 `import` 与 `apply` 执行之间实测相差约 340ms——它们是两个不同的时刻，
后面讲热重载时这个区分很关键（改代码会让两者都变，只让 apply 重跑则只有后者变）。

## 四、这一课立住的词

后面几课会反复用到，在这里第一次有了确切含义：

- **条目（entry）** — 组合树里的一行，有 `id`、`name`、可选的 `config` / `disabled`
- **活层（live layer）** — profile 的 `cordis.patch.yml`，你日常动的那一层
- **bundle 层** — `dsh.profile.bundles` 里那些包各自带的 patch
- **加载** — `apply()` 被执行
- **见证文件** — 插件留下的可观测副作用，本实验台判定「有没有真的发生」的通用手段

## 五、下一课

**L2 · 条目字段** —— `disabled` 怎么用、`config` 改了会怎样、条目还能带哪些字段。
