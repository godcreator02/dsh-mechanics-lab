# 第 1 步 · 让一个空实例跑起来

> 2 个用例 ｜ 约 15 秒 ｜ 前置：手边有一个能跑的 DSH

## 要干什么

起一个**空实例**——一个跑着的 DSH 进程，里面除了它自己必须有的东西，什么都没有。

这是后面每一步的地基：从第 2 步开始，你写的每个插件都要挂进一个这样的实例里才能跑。
所以先把它立起来，确认它能起、能一直活着、停得掉。

一个实例由一个 **profile** 决定加载什么。profile 就是一个目录，住在 DSH home 的
`profiles/` 下（home 默认是 `~/.dsh`，也可以用 `DSH_HOME` 指到别处）。
本步要建的就是这么一个目录，里面**两个文件**。

## 照着做

### 1. 拿一个空目录当 home，建 profile 目录

拿新目录当 home，你平时那个 home 一点都不会被动到：

```powershell
$env:DSH_HOME = "D:\dsh-step1"
New-Item -ItemType Directory -Force "$env:DSH_HOME\profiles\hello"
```

`hello` 是 profile 的名字，随你起，**只有一个名字不能用：`web`**——那是官方主 profile 占着的。

### 2. 写第一个文件：`package.json`

```json
{
  "name": "dsh-profile-hello",
  "private": true,
  "dsh": { "profile": { "bundles": [] } }
}
```

它让这个目录成为一个 profile。`bundles` 留空就是「不额外加载任何东西」，本步不用改它。

### 3. 写第二个文件：`cordis.patch.yml`

```yaml
- insert:
    - id: timer
      name: '@deepseek-ai/cordis-plugin-timer'

    - id: hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
```

**照抄，两条都要写。** 它们是什么、为什么是它们，第 6 步再回头说；现在只需要知道
一个实例最少就得有这两条。

写法上有三点要留神，抄错了实例就起不来：

- 文件内容是一个 YAML 数组，最外层那个 `- insert:` 不能少
- `name` 那一行是包名，两边的引号别丢（`@` 开头的字符串在 YAML 里不带引号会出问题）
- 缩进照抄，YAML 认缩进

`cordis.yml` **不用你建**，dsh 启动时会自己写。

### 4. 起实例

```powershell
npx @deepseek-ai/dsh --profile hello
```

停它就在这个终端里按 `Ctrl+C`。

## 你会看到什么

**终端什么都不打印，光标停在那儿不返回。** 这就是成功——它没有报错、也没有退回提示符，
说明进程起来了并且一直活着。空实例没有网页界面，也不占端口，所以除了「它还在跑」之外
没有别的动静。

profile 目录里多出一个文件：

```
profiles/hello/
├─ package.json
├─ cordis.patch.yml
└─ cordis.yml        ← 这个是 dsh 自己写的
```

打开 `cordis.yml` 看一眼，里面只有几行英文注释和一个空数组，注释的最后一句是：

```yaml
# … Edit cordis.patch.yml, not this file.
[]
```

*Edit cordis.patch.yml, not this file* 就是给你的：**这个文件别改**，
每次启动都会被重写。你要写的一直是 `cordis.patch.yml`。

按 `Ctrl+C`，进程停下，终端回到提示符。**能起、能一直活、停得掉**——这一步就完成了。

## 出错了往哪看

实例起不来的样子很好认：**它没有停在那儿，而是打了一堆东西然后退回提示符。**
第一行 `Error:` 之后那句就是原因，往下的 `at …` 是调用栈，不用看。

最常见的一种，是两条只抄了一条。报错里会有这么一行：

```
@deepseek-ai/cordis-plugin-hmr: pending (waiting for service: timer)
```

`waiting for … timer` 点名了缺的东西——回去看 `cordis.patch.yml`，`timer` 那两行是不是漏了。
**两条要一起写。**

另外两种报错长得完全不一样，照这个对：

**`failed to parse … cordis.patch.yml: YAMLException: bad indentation …`**
——文件没写成合法的 YAML。它会把出问题那行原样印出来，底下一个 `^` 指着位置：

```
 1 | - insert:
 2 |     - id: timer
 3 |       name: @deepseek-ai/cordis-plugin-timer
-----------------^
```

照着 `^` 的位置改。缩进抄歪、包名没加引号，都会撞进这一条。

**`profile "hello" does not exist`**
——`--profile` 后面的名字跟目录名对不上，或者 `DSH_HOME` 没设成你建目录的那个。
先确认 `$env:DSH_HOME\profiles\<名字>` 这个目录真在。

改完文件重新跑第 4 步那条命令即可，不用清理什么。

## 自己跑一遍

本步的两个用例：一个验「照着抄就能起、盯 12 秒不退出、`cordis.yml` 自动出现」，
一个验「只抄 hmr 漏掉 timer 会启动失败，且日志点名 timer」。

```powershell
uv run pytest experiments/step1_run_an_instance/ -n 0
```

用例里的 `cordis.patch.yml` 内容跟上面给你抄的那段逐字一致。
