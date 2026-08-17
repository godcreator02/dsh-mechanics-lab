"""cross-layer-targeting · 后面的 patch 能改前面刚插进来的行

档次 ② ｜ 性质 🔬 发现型 ｜ 状态 ✅ 已验 ｜ 1 条用例 ｜ 不需要 web

## 判定

- **同一份 patch 数组里，后面的行能定位到前面 `insert` 刚创建的行。**
  `applyEntryPatches()` 的 `buildMap(insert)` 是有意为之：每插入一批条目就立刻把它们登记进
  `entryMap` 索引。文档没写这条（`docs/official/zh/user/develop/basic/publish.md:112-126` 只讲了
  四层顺序与整键覆盖，没提「同一叠内能不能改前面刚插的」），只能从
  `<npx 缓存>/node_modules/@deepseek-ai/cordis-plugin-include/src/index.ts:58-128` 读出来。
  `test_later_patch_can_target_earlier_insert` 已实测：`- insert:` 插入 `kid`（`n: 1`），紧接着
  一条裸 `- id: kid` 覆盖成 `n: 2`，最终 `config == {"n": 2}`
- **这条不只在同一层内成立，是跨层的。** 四层 patch（bundle 层 + 用户活层 + home 层 + `--patch`
  overlay）在传给 `applyEntryPatches` 之前会先拼成一个数组（`allPatches()`），所以用户活层能改到
  bundle 层刚 `insert` 进来的行，不需要它是 group。⚠️ 这半句是源码推理，本项没有独立起一套跨层
  fixture 去验——`layer-stack` 项的 `shared` 条目场景（同一个 id 被 bundle/profile/home/overlay
  四层依次覆盖）已经顺带体现了这个事实，本项不重复

## 观测方法

`dump-config` 和运行时挂载走的是同一个 `applyEntryPatches` 调用，一份纯静态的 patch（条目名是不需要
解析的占位符，不用 `link_plugin`）就够，不用拉真实例。
"""

from __future__ import annotations

from lab import dump_config


def test_later_patch_can_target_earlier_insert(lab_home):
    """`buildMap(insert)` 是有意为之：每次 insert 后立刻把新条目登记进索引，
    所以同一份 patch 列表里，后面的条目能找到前面 insert 刚插进来的那一行。
    """
    profile = lab_home.make_profile("later-targets-earlier", bundles=[])
    profile.write_patch("""# 同一叠内，后插改前插
- insert:
    - id: kid
      name: dummy-kid
      config:
        n: 1
- id: kid
  config:
    n: 2
""")

    dumped = dump_config(lab_home, profile.name)
    print(f"\n  kid 的 config：{dumped.config_of('kid')}")

    assert dumped.config_of("kid") == {"n": 2}, "后面那条 patch 应该改到了前面刚插进来的 kid"
