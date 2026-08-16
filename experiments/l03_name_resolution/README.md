# L3 · `name` 的三条解析路径

> 8 个用例 ｜ 约 62 秒 ｜ 不需要 web ｜ ⚠️ 矫正型 ｜ 前置：L1

**要回答**：条目的 `name` 怎么变成一个真的模块？

```powershell
uv run pytest experiments/l03_name_resolution/ -v
```

---

## 起点：源码画的是三条分支

`cordis-plugin-loader` 的 `EntryTree.import`：

```js
import(name, getOuterStack) {
    if (name.startsWith("cordis:")) return this.ctx.loader.builtins[name.slice(7)];
    return composeError(async (info) => {
        if (this.ctx.loader.internal) return await this.ctx.loader.internal.import(name, this.ctx.baseUrl, {});
        else if (name.startsWith(".")) return await import(new URL(name, this.ctx.baseUrl).href);
        else return await import(name);
    }, getOuterStack);
}
```

表面上是四条判断，但 `internal` 那一句排在最前面——如果它激活，相对路径 /
绝对路径 / 裸包名会全部经同一条 `internal.import(name, baseUrl, {})`。
`internal = ModuleLoader.fromInternal()`，试图 require 一个叫
`node-addon-require-builtin` 的 native addon 拿 Node 内部 ESM loader；
这一步被 try/catch 包着，成不成功没有先验答案——**必须先测这件事，
否则后面每一条用例的因果解释都不知道该往哪边挂**，所以它是本课第一个用例。

---

## 结论速查

| 问题 | 答案 |
|---|---|
| `ctx.get("loader").internal` 在本部署是否激活 | **是**。那个"addon 装不上、被静默吞掉"的假设不成立——它是真的装上了，且在工作 |
| 于是"三条互不相通的路径"还成立吗 | **只成立一半**：`cordis:` 前缀在 `internal` 判断之前就短路，是独立的第一刀；剩下相对路径／绝对路径／裸包名**代码路径合一**，全部丢给 `internal.import`，但表现出来的解析行为（协议判断、URL 解析、包解析）跟源码注释的三分支几乎一致——因为 `internal.import` 内部本来就是在做同一件事 |
| Windows 裸盘符绝对路径（`D:\...\index.js`）能加载吗 | **不能**。`D:` 被当成 URL scheme，报 `ERR_UNSUPPORTED_ESM_URL_SCHEME` |
| `file://` URL 形式的绝对路径能加载吗 | **能**。这才是 Windows 下"绝对路径"应该写的形式 |
| `cordis:` 指向不存在的内置表项 | cordis 自造的报错：`invalid plugin, expect function or object with an "apply" method, received undefined`；这条从没建立过 fiber |
| 裸包名指向不存在的包 | Node 标准报错：`ERR_MODULE_NOT_FOUND: Cannot find package '...'`；跟上一条文本完全不同，别用同一个断言判断 |
| `exports` 子路径声明了会怎样 | 能加载 |
| `exports` 子路径没声明会怎样 | `ERR_PACKAGE_PATH_NOT_EXPORTED` |
| 相对路径有 `exports`/`main` 回退链吗 | **没有**。同一份代码：相对路径直指非入口文件成功；包名引用同一个包失败（`legacyMainResolve` 去找默认 `index.js`，找不到） |

---

## 一、决定性的前置问题：`internal` 是真的激活了

探针（`fixtures/l03-probe`）走裸包名加载，在 `apply` 里顺手记一笔
`ctx.get("loader").internal !== undefined`：

```
ctx.get('loader').internal 是否激活：True
ctx.baseUrl：'file:///D:/dshfiles/.../.testhome/l03/profiles/internal/'
```

**这推翻了任务交底里的假设**——原以为 `node-addon-require-builtin` 这个 addon
"能否 require 成功被 try/catch 静默吞掉"是个未知数，需要先蹚一遍才知道走哪条路。
实测很直接：它成功了，且贯穿本课全部用例（同一份 `dsh` 部署、同一个 Node
运行时，没有理由后面几条用例会切到另一条分支）。

**后果**：源码里画的"四条判断"在这次部署里实际只有两层：

1. `cordis:` 前缀——**在 `internal` 判断之前就短路**，走 `loader.builtins[...]`，
   跟 `internal` 激不激活无关（L0 已验过这张表只有 `include` 和 `group` 两项）。
2. 剩下所有 `name`（不管是 `.` 开头、盘符开头，还是裸包名）——**全部丢给
   `internal.import(name, this.ctx.baseUrl, {})`**，代码路径是同一条。

但"代码路径合一"不等于"解析行为也合一"。往下看就知道：`internal.import`
内部照样按协议、按相对/绝对、按包名分别处理——报错堆栈里能直接看到
`node:internal/modules/esm/resolve`、`legacyMainResolve`、
`throwIfUnsupportedURLScheme` 这些 **Node 自己 ESM loader 内部函数的名字**，
说明 `internal.import` 就是直接拿到了 Node 内部那套解析器的引用，
不是 cordis 自己另写的一套。所以后面几条用例测到的边界，本质上就是
**Node ESM 解析器本身的边界**，只是通过 `internal` 这条捷径直达，没有经过
公开的 `import()` 语句。

---

## 二、Windows 绝对路径：裸盘符路径不行，`file://` URL 才行

两种写法对照：

| 写法 | 结果 |
|---|---|
| `D:\dshfiles\...\l03-probe\index.js`（裸盘符路径） | ❌ |
| `file:///D:/dshfiles/.../l03-probe/index.js`（`file://` URL） | ✅ |

裸盘符路径的失败原因非常明确，Node 自己的报错说得很清楚：

```
Only URLs with a scheme in: file, data, and node are supported by the
default ESM loader. On Windows, absolute paths must be valid file:// URLs.
Received protocol 'd:'
```

**`D:` 被当成了 URL scheme。** Node 的 ESM 解析器不认"这是个文件系统路径"，
只认"这是不是一个合法 URL"——`D:\...` 这个字符串恰好长得像 `scheme:rest`，
于是被当成协议名是 `d:` 的 URL 去解析，而 `d:` 不在允许的协议白名单
（`file`、`data`、`node`）里，直接拒绝。

`file://` URL 那条完全成功，见证文件里 `loaderInternal: true` 原样带出来，
证明走的还是同一条 `internal.import`。

**⚠️ 矫正点**：官方 `zh/user/develop/basic/index.md:56` 写「插件路径必须是绝对路径」，
给的示例是 POSIX 风格 `/absolute/path/to/deepseek-harness/...`——在 POSIX 系统上
这种路径不会被误判成 URL scheme（没有那个冒号），直接能用。但照这条建议原样
搬到 Windows 上（裸盘符路径），**会失败**。文档没有区分操作系统，这就是
"建议"和"规则"的落差：真正对的规则是"必须是合法 URL"，`/absolute/path` 在
POSIX 上恰好也是合法 URL 路径部分，Windows 盘符路径不是，需要显式转成
`file://` 形式（Node 的 `pathToFileURL()` 或 Python 的 `Path.as_uri()` 都是干这个的）。

---

## 三、两种"加载失败"：报错文本完全不同，别用同一个断言

`cordis:` 前缀在 `internal` 分支之前就短路，走的是 `loader.builtins[...]`
查表——查不到就是 `undefined`，`undefined` 被当插件启动，cordis 自己抛：

```
invalid plugin, expect function or object with an "apply" method, received undefined
```

这条从头到尾**没有走任何模块解析**，也没建立过 fiber——跟 PENDING（L0/L11）、
FAILED（`apply` 内部抛异常）都不是一类，是第三种失败形态，纯粹是"查表查到空"。

裸包名指向不存在的包，走的是 `internal.import` → Node 标准 ESM 解析，
抛的是 Node 自己的错：

```
Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'l03-definitely-does-not-exist'
imported from D:\...\profiles\nopkg\
```

两条都表现为"启动失败、退出码 1"，但**成因完全不同**——前者是 cordis
的查表逻辑对 nullable 值放行导致的下游报错，后者是 Node 模块系统本身的
标准报错。混着断言（比如只判断"有没有报错"）会把这两种完全不同的机制
读成同一件事。

---

## 四、`exports` 子路径：声明了才能走通

官方 publish 文档演示过 `dsh-hello-plugin/startup` 这种子路径写法
（`zh/user/develop/basic/publish.md:136`）。子路径不以 `.` 或 `cordis:` 开头，
落进"否则"桶，走纯 Node 包解析——**exports 映射表由 Node 处理，没有 cordis
代码参与**。

两个 fixture 包的 `tool.js` 逐字节相同，唯一差异是 `package.json`：

```json
// l03-subpath-declared：exports 里显式列了 "./tool"
{ "exports": { ".": "./index.js", "./tool": "./tool.js" } }

// l03-subpath-undeclared：exports 存在，但没提 "./tool"
{ "exports": { ".": "./index.js" } }
```

结果：

| 包 | `name` | 结果 |
|---|---|---|
| `l03-subpath-declared` | `l03-subpath-declared/tool` | ✅ 加载成功 |
| `l03-subpath-undeclared` | `l03-subpath-undeclared/tool` | ❌ `ERR_PACKAGE_PATH_NOT_EXPORTED` |

`tool.js` 在磁盘上确确实实存在，两个包里都有——undeclared 那个失败**不是
因为文件不存在**，是因为 `exports` 映射表把这条子路径挡在外面。**只要一个
包声明了 `exports`，它就变成一份"公开接口白名单"**：没写进去的子路径，
哪怕文件本身完好无损，也访问不到。

---

## 五、相对路径没有 `exports`/`main` 回退链

L1 验过包名解析的回退链：`exports["."]` → `main` → 默认 `index.js`，三条路
任意一条通就能被包名 resolve 到。这条回退链**只属于包解析**，本课要正面
测一次它对相对路径是否成立。

`fixtures/l03-fallback` 故意让三条路全断——没有 `exports`、没有 `main`，
真正的代码文件又不叫 `index.js`（叫 `plugin.js`）：

```json
{ "name": "l03-fallback", "type": "module" }
```

同一份 `plugin.js`，两种引用方式：

| 引用方式 | `name` | 结果 |
|---|---|---|
| 相对路径直指文件 | `./.../l03-fallback/plugin.js` | ✅ 加载成功 |
| 包名（默认子路径 `.`） | `l03-fallback` | ❌ 加载失败 |

失败的具体报错：

```
Error: Cannot find package '...\node_modules\l03-fallback\index.js'
imported from ...
    at legacyMainResolve (node:internal/modules/esm/resolve:205:26)
```

`legacyMainResolve` 是 Node 在包没声明 `exports` 时的回退逻辑——它会去找
`main` 字段，没有就去找默认的 `index.js`。这个包哪个都没有，所以回退链
走到底还是找不到，报错。

而相对路径那条**压根不会触发 `legacyMainResolve`**——它是纯 URL 解析
（`new URL(name, ctx.baseUrl)`，或者本课证实的 `internal.import` 内部对相对
路径的等价处理），根本不看 `package.json`，直接把字符串拼成文件系统路径
去找文件。**同一段字节，两条引用方式的成败完全相反，边界就画在"要不要经过
`package.json`"这一步上。**

推论：自己写的教学插件如果不想为了满足包解析的回退链而特意把入口文件叫
`index.js`，可以选择用相对路径直接指到真实文件——但要接受"必须指到文件、
不能指到目录"（L0 已验）这个代价。

---

## 观测手法

延续 L0/L1 的见证文件套路，`fixtures/l03-probe` 多探一件事：
`ctx.get("loader").internal !== undefined`，跟 `moduleLoadedAt` / `appliedAt`
一起写进见证文件——这是本课能立住"internal 是否激活"这条判定的唯一手段。

**观测点绝不抛错**：探针里的 `safe()` 包了一层 try/catch，拿不到就记 `null`，
不让"根本没跑到这"和"跑到了但没拿到"混成同一个结果（L0/L3 都吃过反过来
做的亏）。

**结果未知的用例，统一用固定等待而不是轮询提前退出**——`_observe_fixed()`：
Windows 绝对路径、`file://` URL 两条用例事先不知道会成功还是失败，
用轮询等成功只能证明"这一刻还没成功"，证明不了"永远不会成功"；固定等
10 秒再看见证文件在不在、进程还活不活着、日志写了什么，三样一起如实记录，
判断留给断言。

**两种"加载失败"分开断言**：`test_cordis_unknown_builtin` 断言日志**包含**
cordis 自造的那句话；`test_nonexistent_bare_package` 断言日志**不包含**
那句话（应该是 Node 标准报错）。只判断"有没有报错"会把两种完全不同的
失败机制混成一件事——这条规矩来自 CLAUDE.md 的观测方法论第 5 条，本课是
第一次真正用上它。
