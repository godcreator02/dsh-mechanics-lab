# 第 3 步 · 给它传配置

上一步你写了一个导出 `apply` 的模块，在 patch 文件里加了一条 `insert` 把它挂上去，
起实例，确认它真的跑了。**这一步只多做一件事：在那条条目上写 `config`，让 `apply` 收到它。**

前面几个词一句话回顾：**profile** 是一套实例配置，**patch 文件**是它目录下的
`cordis.patch.yml` —— 你日常动的就是这个文件；文件里 `- id: ... / name: ...` 那一段是一条
**条目**，`id` 是它的名字，`name` 是要加载的模块。

跑法：`uv run pytest experiments/step3_pass_config/ -n 0`（约 11 秒，5 个用例）

---

## 一、要干什么

把插件里那些「换个地方跑就要改一改」的值 —— 问候语、重试次数、开关、路径 ——
从代码里挪出来，写进 patch 文件。改的时候只改那一行，不动代码。

`apply` 一直有两个参数，第 2 步只用了第一个：

```js
export function apply(ctx, config) {}
//                    ↑     ↑
//                    先不管  这一步的主角
```

**条目上 `config:` 底下写什么，`apply` 的第二个参数就收到什么。** 就这一句，这一步讲完了。
剩下的是照着做一遍，亲眼看见它到了。

## 二、照着做

### 1. 让插件把收到的 config 写出来

光在 `apply` 里 `console.log` 一下也行，但日志会被吞、会被缓冲。写文件更硬：
文件在不在、里面是什么，一眼就能判。

把你第 2 步那个插件的 `index.js` 改成这样（完整文件，本步的教学插件就是它，
在 `fixtures/config-echo/`）：

```js
import { writeFileSync } from "node:fs";
import { join } from "node:path";

const OUTPUT = join(import.meta.dirname, "received-config.json");

export function apply(ctx, config) {
  writeFileSync(OUTPUT, JSON.stringify({ received: typeof config, config: config ?? null }, null, 2), "utf8");
}
```

它把收到的第二个参数原样抄进插件目录下的 `received-config.json`，跟 `index.js` 并排。
**落点写死在代码里、不从 `config` 里读** —— 这样连「一个 `config` 都不写」的场合也照样看得到结果。

`received: typeof config` 那一行是特意加的：`undefined` 放进 JSON 会让整个键消失，
不单独记一下类型，就分不清「收到了 `undefined`」和「插件根本没写这个键」。

### 2. 在条目上写 config

patch 文件里你那条 `insert`，加三行：

```yaml
- insert:
    - id: config-echo
      name: config-echo
      config:
        greeting: 你好
        retries: 3
        verbose: true
```

⚠️ **`config` 跟 `id`、`name` 是同一层缩进** —— 它是这条条目的一个字段。缩进错一格，
它就不再属于这条条目了。

### 3. 起实例，打开那个文件

跟第 2 步一样起实例，然后看插件目录下的 `received-config.json`。

## 三、你会看到什么

### 1. 写什么就收到什么

```json
{
  "received": "object",
  "config": { "greeting": "你好", "retries": 3, "verbose": true }
}
```

键名、值、类型，一个不差。中文键也一样。

### 2. 不限于一层扁平的键值

嵌套对象、数组、`null`、小数都原样送达，写 `config` 时不用迁就任何形状：

```yaml
config:
  服务器: { 主机: "127.0.0.1", 端口: 3090 }
  名单: ["甲", "乙", { 丙: [1, 2, 3] }]
  空值: null
  小数: 3.14
```

插件想要什么结构，你就在这儿写什么结构。

### 3. 改了值，重起一次就是新的

把 `greeting` 改成别的、重新起一次实例，`received-config.json` 里就是新值 ——
插件代码一个字没动。这就是把可调的东西挪进 `config` 的全部好处。

### 4. 没写 `config` 的时候，第二个参数是 `undefined`

```json
{ "received": "undefined", "config": null }
```

**把键名拼错（比如写成 `cofnig`）结果完全一样。** patch 文件里多写一个没人认识的键，
既不报错也不警告，插件照常跑起来 —— 只是拿不到配置。

所以写插件时，`config` 要当成「可能没有」来接：

```js
const greeting = config?.greeting ?? "Hello";
```

## 四、出错了往哪看

按现象分三种，查的地方完全不同：

| 现象 | 多半是什么 |
|---|---|
| `received-config.json` 根本没出现 | 不是 `config` 的问题 —— 插件压根没跑起来。回第 2 步那套查法 |
| 文件出现了，`received` 是 `"undefined"` | `config` 这个键没落到这条条目上：拼错了、缩进错了一格、或者写到了别的条目底下 |
| 收到的值跟你写的不一样 | YAML 的类型规则：`3` 是数字、`"3"` 是字符串、`true` 是布尔、`"true"` 是字符串。加引号跟不加引号是两个东西 |

第二行那种最难受，因为**没有任何报错** —— 全靠你自己盯着 `received` 那个字段看。
所以这一步的教学插件才把类型单独记出来：分不清「收到 `undefined`」和「收到空对象」，
就没法判到底是哪一头出了问题。

## 五、这一步立住的词

- **`config`** — 条目的一个字段，写在 `id` / `name` 同一层；里面的内容原样进 `apply` 的第二个参数

## 六、下一步

**第 4 步 · 临时关掉它** —— 不删条目，让它这次先别跑。

---

本页的判定由 `test_step3.py` 的 5 个用例支撑：原样送达（含中文键）、嵌套结构不变形、
改了重起收到新值、没写 / 写错键名都是 `undefined`。
