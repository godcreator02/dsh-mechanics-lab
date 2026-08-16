# 第 2 步 · 把自己写的东西挂上去

> 接着第 1 步来：你已经有一个能跑起来的空实例，它的 patch 文件里写着 `timer` 和
> `hmr` 两条。那两条是别人写好的东西——这一步让实例跑一段**你自己写的代码**。

```powershell
uv run pytest experiments/step2_mount_your_plugin/ -n 0   # 4 个用例，约 25 秒
```

---

## 要干什么

三件事，缺一件都不行：

1. 写一个模块，**导出一个叫 `apply` 的函数**
2. 在 patch 文件里**加一条**，指向那个模块
3. 起实例，**确认它真的跑了**

## 照着做

### 一、写那个模块

在你 profile 文件夹里新建 `hello-plugin.mjs`：

```js
import { writeFileSync } from "node:fs";

export function apply() {
  writeFileSync(
    new URL("./hello-ran.json", import.meta.url),
    JSON.stringify({ marker: "step2-hello-v1", appliedAt: new Date().toISOString() }, null, 2),
    "utf8",
  );
}
```

一个插件全部的必需家当就是**导出一个 `apply`**。实例挂上它的时候会调用这个函数，
参数这一步一个都用不到。

里面那几行只干一件事：**在自己旁边写一个 `hello-ran.json` 出来**。这纯粹是为了
让你能看见它跑过——不打日志，日志会被吞、被缓冲、被格式变化骗过去，文件在不在
是硬事实。

后缀写 `.mjs`，Node 就直接按 ESM 读它，不用再为它配别的文件。

### 二、patch 文件里加一条

在第 1 步那份 patch 文件**末尾追加**：

```yaml
- insert:
    - id: hello
      name: ./hello-plugin.mjs
```

加完整份文件长这样（上面两条是第 1 步写好的，原样留着）：

```yaml
- insert:
    - id: timer
      name: '@deepseek-ai/cordis-plugin-timer'

    - id: hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      config:
        root: []
        debounce: 100

- insert:
    - id: hello
      name: ./hello-plugin.mjs
```

新加的这一坨就是一个**条目**，两个字段各管一件事：

| 字段 | 是什么 | 怎么填 |
|---|---|---|
| `name` | DSH 拿它去找你那个模块 | 这里写相对路径，**相对 profile 文件夹算** |
| `id` | 你给这一条起的名字 | 随便起，只要在这份文件里不重名 |

`- insert:` 这行照着写就行，第 8 步才展开它到底是什么意思。

### 三、起实例

跟第 1 步一样把实例起起来。

## 你会看到什么

profile 文件夹里多出一个 `hello-ran.json`：

```json
{
  "marker": "step2-hello-v1",
  "appliedAt": "2026-08-16T13:55:32.891Z"
}
```

**这个文件出现，就等于 `apply` 被调用过了**——它是 `apply` 里那几行写出来的，
没有别的来路。`appliedAt` 是 `apply` 执行的那一刻，`marker` 是代码里写死的一个串，
改了它再跑一次，文件里跟着变，就能确认跑的是你刚改的那份代码。

想再确认一下因果，做两个动作：

- **把新加的那条 `insert` 删掉，删掉 `hello-ran.json`，重新起实例**——文件不会再
  出现。让你的代码跑起来的是 patch 文件里那一条，不是那个模块躺在文件夹里。
- **把 `id: hello` 改成任何一个词**（`id: 随便起的名字` 也行），重新起实例——文件
  照常出现。找模块看的是 `name`，`id` 只是你给这一条起的名字。

## 出错了往哪看

**先看实例还在不在。** 这一步的写错基本都会让实例**直接退出**，不会被悄悄跳过
——所以「实例还在跑」本身就是一半证据。实例退出时，看它最后那几行报错：

| 报错里有 | 意思 | 怎么办 |
|---|---|---|
| `ERR_MODULE_NOT_FOUND: Cannot find module '…'` | `name` 指的那个文件不在那儿 | 报错里带着它**去找的那个完整路径**，跟你文件的真实位置对一下 |
| `invalid plugin, expect function or object with an "apply" method` | 文件找到了，里面没有导出 `apply` | 检查是不是漏了 `export`、或者名字拼错了 |

第二种报错前面还会跟一行 `failed to apply loader entry hello (./hello-plugin.mjs)`，
你写的 `id` 和 `name` 都在里面——出问题的是哪一条不用猜。

**实例活着、但 `hello-ran.json` 就是不出现**，那是新加的那一条压根没生效：回去看
patch 文件的缩进，`- insert:` 底下是一个列表，`- id:` 那行要缩进进去。

## 这一步新出现的词

| 词 | 含义 |
|---|---|
| `apply` | 模块导出的那个函数。实例挂上这个插件时调用它 |
| 条目 | patch 文件里的一坨，描述「挂哪个模块」 |
| `name` | 条目上的字段，DSH 按它找模块 |
| `id` | 条目上的字段，你给这一条起的名字 |

## 这一步的用例

| 用例 | 验的是 |
|---|---|
| `test_your_plugin_actually_runs` | 加上那一条之后，`apply` 真的被调用了 |
| `test_nothing_runs_without_the_entry` | 不加那一条，模块放着也不会跑 |
| `test_id_is_yours_name_finds_the_module` | `id` 换成毫不相干的词，插件照常跑 |
| `test_a_wrong_name_stops_the_instance` | `name` 写错，实例直接退出并点名 |

## 下一步

**第 3 步 · 给它传配置**——条目上写 `config`，`apply` 里收到。
