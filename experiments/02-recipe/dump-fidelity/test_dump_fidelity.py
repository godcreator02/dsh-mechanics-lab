"""dump-fidelity · 静态算出来的配方与运行时挂载是同一套逻辑

档次 ② ｜ 性质 📗 复述型（论证）｜ 状态 ⚠️ 部分 ｜ 0 条用例（无独立用例）｜ 不需要 web

## 判定

- **`--dump-config` 算出来的组合树与运行时真实挂载走的是同一套 compose 逻辑，不是近似模拟。** 这是
  本项目里多数「配方」类判定敢用静态 dump 代替拉真实例的全部依据，证据分两条：
  1. **源码层面**：`dsh --dump-config` 的 `renderConfigDump()`/`composeEntries()` 与运行时挂载的
     `Include.applyPatches()` 调用的是同一个 `applyEntryPatches()`
     （`<npx 缓存>/node_modules/@deepseek-ai/cordis-plugin-include/src/index.ts:58-128`），
     `dsh-app-boot/lib/index.js` 的注释原话是 *"the same single `applyEntryPatches` call the boot
     include makes"*——这条是引用型证据，没有独立用例覆盖它。`insert-semantics` / `override-semantics` /
     `cross-layer-targeting` / `layer-stack` 四项的静态用例全部隐含依赖这条前提才敢只用 dump 判定，
     不拉真实例
  2. **实测层面（半份）**：`test_effective_config_vs_entry_tree` 里 `assert recipe_ids <= tree_ids`
     这一断言——静态 dump 算出来的所有 id，运行时树上都真实存在。这条只验了「dump 里有的，运行时也
     有」，没有反向验证「运行时多出来的除了 `cordis:include` 之外没有别的」——那半句是 07-tree 分组
     `recipe-vs-tree` 项自己的判定，不是本项的，按「一个事实一个家」不在这里复述

## 观测方法

本项当前没有独立用例，两条证据都是从别处借来的：一条是纯源码引用，一条是另一项测试里的部分断言，
不为凑数在这里另起一套 fixture 重复验证同一件事的另一半。

## 没覆盖到的

要补成 ✅，独立用例需要正面验证「同一份 patch，静态 dump 出来的每个条目的 `config`，与运行时真的
挂载后该条目收到的 `config` 逐一相等」——现有素材只验了 id 集合的包含关系，没验 `config` 内容的逐条
一致性，这是留白。
"""
