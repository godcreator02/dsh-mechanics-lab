"""entries-order · `loader.entries()` 的列表顺序不能当树用

档次 ② ｜ 性质 🔬 ｜ 状态 ⬜ 未覆盖 ｜ 0 条用例 ｜ 不需要 web

## 判定

- **待验，无独立用例支撑。** 现有的唯一记录是旧 `l08_tree_hierarchy` 的
  README「一个意外收获」一节：`test_isolate_gives_each_group_its_own_service_instance`
  多跑几次，同一份 patch 每次拍到的 `loader.entries()` 顺序都不一样——
  某一次幽灵条目 `timer` 排到了 `include` 前面，两个组各自的孩子也不是
  紧跟在父条目后面，而是等两个 group 都建完之后才成批出现。这条观察指向
  的结论是：`loader.entries()` 的出场顺序既不反映创建时间，也不反映树上
  的位置，只有 `parent` 字段能信。
- **这条观察不进本项的状态。** 它是 `test_isolate_gives_each_group_its_own_service_instance`
  这条用例的副产品——那条用例归 `08-service-core/isolate`，本组按纪律
  不能拿。本组自己（`hierarchy` / `disabled-propagation`）的用例目前只跑
  单次快照、不做多次重跑对比，没有针对「顺序稳不稳定」设计过断言，所以
  这条判定在本组里还没有独立证据。

任何依赖 `entries()` 顺序的断言都是脆的——顺序不稳定，且很容易写出一条
碰巧通过的断言（比如用列表下标比大小），下次重跑就会随机翻车。写断言
只能认 `parent` 字段算出的层级，不能认 `loader.entries()` 返回列表里的
先后位置。

## 没覆盖到的

- 一个能反复触发、专门断言「多次重跑同一份 patch，`loader.entries()`
  顺序不稳定」的用例。需要的实验设计：同一份 patch 多次拉起（或同一次
  运行里触发多轮 apply），比较每轮 `loader.entries()` 的出场顺序，正面
  断言顺序会变、而 `parent` 链算出的层级不变。
- 顺序不稳定的机制解释：旧 README 提到 `EntryGroup.update()` 用
  `Promise.allSettled` 并发创建同级条目，这只是一条未坐实的推测，没有
  对应源码引用或用例验证。
"""
