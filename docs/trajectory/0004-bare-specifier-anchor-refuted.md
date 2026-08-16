# 裸包名锚点的机制解释推翻

> 了断于 2026-08-16 ｜ 推翻 ｜ 冻结

## 背景

L0（全景课）实测到一个现象：条目的 `name` 写成官方包的裸包名（如
`@deepseek-ai/cordis-plugin-timer`），**不用 link 进 profile 的 `node_modules`**
也能加载。而实验台自己的教学插件不 link 就加载不了。

当时读源码给出的解释是：`dsh-app-boot` 的 `mountRootInclude()` 里有个
`HostResolvedRootInclude` 子类，专门把裸包名以 **dsh 安装目录**（`bareModuleBaseUrl`）
为锚去解析。这个解释写进了课程 README 与术语表，标为「已实测」。

## 结论与边界

**那段代码从未执行，解释是错的。** `bareModuleBaseUrl` 是 `boot()` 的第 5 个参数，
而唯一调用点只传 4 个，它恒为 `undefined`，于是 `builtins.include` 永远是朴素版
`Include`——`HostResolvedRootInclude` 是真实存在但从不激活的死代码。

真实机制是**标准 Node parent-walk 加一层共享 `node_modules`**：`$DSH_HOME/profiles/`
下有一份符号链接农场，profile 目录向上遍历一层就撞见它。

边界：**结论没变，机制变了**。「官方包不用 link、自己的 fixture 必须 link」这个
外部行为完全不受影响，所有依赖这个行为的用例继续有效。本次只核到「农场存在且
timer 在其中」，**没有**验证农场的维护时机（`healScaffoldModuleFallback` 何时被调、
安装位置变了是否真的重指），那部分仍是读源码得来的。

## 经过

顺调用链核查。`boot()` 的签名有 5 个参数：

```js
async function boot(binName, absoluteConfigPath, patches, prepare, bareModuleBaseUrl)
```

而 `dsh/lib/profile-boot-DG5t9aNs.js` 里唯一的调用点：

```js
const ctx = await boot(NAME, rootConfig, structuredClone(allPatches(composed)), (hostCtx) => {…})
//                                                                             ↑ 第 4 个，到此为止
```

于是 `mountRootInclude()` 里 `bareModuleBaseUrl === void 0` 恒成立，走的是三元表达式
的另一支。

替代解释随后被实测证实。查假 home 下的 `profiles/node_modules`：

```
条目数：252
@deepseek-ai\cordis-plugin-timer -> C:\…\npm-cache\_npx\…\@deepseek-ai\cordis-plugin-timer
@deepseek-ai\cordis-plugin-hmr   -> …（junction）
```

profile 住在 `$DSH_HOME/profiles/<名字>/`，Node 的模块解析向上一层就是这份农场。
锚点仍是 profile 目录，算法仍是标准包解析，没有任何特殊锚点。

物证：核查命令与输出无原始归档（在会话中一次性执行），**农场本身可原地复核**——
跑过任意一课后 `.testhome/<课>/profiles/node_modules` 即在。修正后的表述在
commit `48ec21c`。

## 依据

`dsh-app-boot` 里 `prepareProfile` 头部注释自己写明了双锚点设计：

> Module resolution is two-anchor by construction: a bundle name resolves first from
> the dsh installation…, then from the profile directory. The Loader's `baseUrl` is
> the profile directory, … while the maintained flat fallback directory
> `$DSH_HOME/profiles/node_modules` (one symlink per package …) makes every in-box
> plugin Node-resolvable from any profile through the ordinary parent-walk.

关键词是 **ordinary parent-walk**——官方自己就说这是普通的向上遍历，不是特殊机制。
读源码时只读了 `mountRootInclude` 的函数体、没读这段注释，也没追调用点。

## 代价与遗留

一条标着「已实测」的判定，实测部分（官方包不用 link）是真的，机制解释是假的。
这种混合形态最难被发现——外部行为对得上，没有任何用例会失败。

教训已固化进工作手册：**从源码得出机制解释，必须追到调用点确认参数真的传了。**
可选参数尤其危险，它的默认分支往往才是实际走的那条。

那段死代码有很强的迷惑性：专门的子类名、`isAbsolute()` 判断、详尽的 JSDoc。
**越是写得好的代码，越容易让人忘记问「它到底被调用了吗」。**

遗留：仓库里其余「读源码得出」的机制解释**没有系统性复查过调用点**，同类错误
可能还有。未实施。
