# 计划：experiments/ 按遭遇顺序重组

方案正本是 `.god-flow/drafts/experiments-by-encounter.md`——十组的划分、每项验什么、
档次与覆盖状态全在那里，本计划不复述，只管**怎么把现有 32 个目录搬成新树**。

## 目标形态

```
experiments/
├─ conftest.py            不动
├─ lab/                   不动
├─ 00-base/
│   └─ <项名>/
│       ├─ README.md
│       ├─ test_<项名下划线版>.py
│       └─ fixtures/
├─ 01-entry/ … 09-boot-vs-runtime/
```

组目录是纯抽屉：**不放 README、不放 `__init__.py`、不放共享 fixtures**。

## 阶段

| 阶段 | 谁 | 干什么 |
|---|---|---|
| 一 | 主会话 | 清场、落本计划 |
| 二 | 十个 agent 并行 | 一组一个 agent，建本组所有项、迁移用例、写 README、搬 fixtures |
| 三 | 主会话 | 跑全套用例、修、提交、删旧目录、改写 SYLLABUS、删 site |

## 阶段二的硬约束

每个 agent 只负责**一个组**，且：

1. **不 commit、不 `git add`。** 提交统一在阶段三做
2. **不跑 pytest。** conftest 的会话锁只允许一套实验在跑，端口 3090–3099 是全局的，
   并行跑会排队串行化还可能互相踩。语法自查用 `uv run python -m py_compile <文件>`
3. **只在自己那个组目录下写文件。** 不碰别的组、不碰 `lab/`、不碰 `conftest.py`
4. **不删任何旧目录、不改任何旧文件。** 旧的原样留着，阶段三统一删
5. **不改 `docs/`、不改 `site/`。** 只读

## 迁移不是搬家

多数项要从**几个旧目录**收集用例，也有一个旧文件被拆进**几个项**的。逐项照下面的
取材表来，取材表里没列到的旧用例，在交回的报告里点名说明它该归哪一项——
**宁可报上来，不要自作主张塞进本组**。

### 判定要跟着用例一起搬

旧目录分两种，处理方式不同：

- **有 README 的**（`l0*`、`step1`–`step3`、`seam_*`、`plugin_wiring`）：README 里
  是已经写好的判定，按项拆开搬进新 README
- **没有 README 的**（`step4`–`step9`、`ch0_*`、`ch2_*`、`chx_*`）：判定只活在
  `site/*.html` 里。**去那里把判定读出来**，写进新 README。这一步做漏了就是丢结论

### 去教学腔

旧用例的 docstring 全是教学口吻，新树里一律不要：

| 旧写法 | 为什么不要 |
|---|---|
| 「第 6 步 · 改了代码想立刻生效」 | 序号是教学顺序，新树没有教学顺序 |
| 「你不用做任何事，跑一下看输出就行」 | 对读者说话。用例是实验装置，不是课件 |
| 「前面几步每改一次插件都得把实例停掉重开」 | 引用相邻课，新树里没有「相邻」 |
| 「这一步同时立起两样东西」 | 同上 |

新的模块 docstring 写三件事：**这一项验什么机制**、**怎么观测的**（信号落在哪、
为什么选它）、**已知的坑**（有就写，没有就不写）。用例函数的 docstring 写这条用例
断言什么，不写「跑跑看」。

### README 的形态

```markdown
# <项名> · <一句话说清验的是什么机制>

> 档次 ① / 性质 🔬 / 状态 ✅ / 用例 N 条 / 需不需要 web

## 判定

- **一句话结论。** 支撑它的证据出处（用例名、或源码路径、或 docs/official 的路径+行号）

## 观测方法

信号落在哪、为什么是这个信号、什么信号是错的（如果踩过）

## 没覆盖到的

有就写，没有就整节删掉
```

判定要标状态：**待验 / 已实测 / 已推翻**。引用官方文档标出处与行号。

### 命名与唯一性

- 项目录名连字符：`name-resolution`
- 测试文件名下划线：`test_name_resolution.py`
- **两个名字都必须全局唯一**——项目录名是假 home 与归档标签的来源，重名会让两项
  共用一个 home（只在并行下发作）；测试文件重名 pytest 直接报 import file mismatch
- fixtures 一项一份，**跨项重复是特性不是冗余**，该复制就复制

### 需要端口的项

用到 `free_port` / `dsh-web-app` 的项，在测试文件顶上打 `@pytest.mark.xdist_group`，
组名用项名。不用端口的项不打。

---

## 取材表

「来源」列写的是旧目录与其中的用例名。**用例可以重写，判定不许重新发明**——
旧的跑绿了就是成立的，搬过去保持断言强度。

### 00-base

| 项 | 来源 |
|---|---|
| `recorder-reach` | `ch0_observer` 全部 3 条 |
| `minimal-profile` | `l00` 的 `test_profile_minimal_files` / `test_empty_bundles_boots` / `test_who_keeps_process_alive`；`ch0_minimal` 全部 2 条；`step1` 全部 2 条（三处是同一判定的三份实现，择优合成一份） |
| `framework-fallback` | `l07` 的 `test_include_is_the_only_ghost` 里兜底那部分；`l00` 里兜底 timer/hmr 的部分 |
| `baseline-profile` | `l00` 的 `test_baseline_profile` |
| `isolation-guarantees` | 无来源，⬜ 未覆盖。只建目录与 README，README 里写清要验什么、为什么还没验，**不要造用例** |

### 01-entry

| 项 | 来源 |
|---|---|
| `field-vocabulary` | `l02` 的 `test_entry_field_vocabulary` / `test_unknown_field_is_carried_but_ignored`；`l01` 的 `test_id_and_name_are_different_things` |
| `config-delivery` | `l02` 的 `test_config_is_arbitrary_json`；`l01` 的 `test_config_reaches_apply`；`step3` 全部 3 条 |
| `disabled` | `l02` 的 `test_disabled_keeps_entry_but_skips_apply` / `test_disabled_accepts_js_expression`；`step4` 全部 3 条；`l05` 的 `test_disabled_js_expression_is_evaluated` |
| `name-resolution` | `l03` 全部 7 条；`l00` 的 `test_bare_name_resolution` / `test_relative_name_resolution`；`l01` 的 `test_resolution_is_the_real_boundary`；`step5` 的 `test_the_same_file_with_the_right_name_just_runs`（另两条归 09 组，别拿） |
| `inject-field` | `l09` 的 `test_entry_level_inject_vs_code_level` |

### 02-recipe

| 项 | 来源 |
|---|---|
| `layer-stack` | `l04` 全部 6 条；`step7` 的前 3 条（`test_same_id_in_both_places_will_not_start` 归 09 组，别拿） |
| `insert-semantics` | `l05` 的 `test_insert_without_id_appends_to_root` / `test_insert_with_id_targeting_non_group_warns_and_skips`；`l01` 的 `test_entry_lands_in_composed_tree` |
| `override-semantics` | `l05` 的 `test_null_sets_key_to_null_not_delete` / `test_missing_id_warns_and_skips_rest_still_applies` / `test_arbitrary_fields_pass_through_patch`；`step8` 的前 2 条与第 4 条（`test_inserting_the_same_id_twice` 归 09 组） |
| `cross-layer-targeting` | `l05` 的 `test_later_patch_can_target_earlier_insert` |
| `dump-fidelity` | `l05` 模块 docstring 里那段论证（dump 与挂载走同一个 `applyEntryPatches`）；`l00` 的 `test_effective_config_vs_entry_tree` 中属于「静态算的等于运行时挂的」那一半。⚠️ 这一项现在只有论证没有独立用例，**照实写成 ⚠️ 部分**，不要为了凑数造用例 |

### 03-supply

| 项 | 来源 |
|---|---|
| `four-ways` | `ch2_four_ways` 的 `test_four_ways_mount_the_same_entry` |
| `self-registration` | `ch2_bundle_vs_live` 的 `test_a_package_mounts_itself`；`ch2_four_ways` 的 `test_the_package_alone_registers_nothing` |
| `pinned-worktree` | `ch2_worktree` 的 a / b / d 三条（`test_c_one_checkout_is_one_reload` 归 05 组，别拿） |
| `supply-x-activation` | `plugin_wiring` 的 `test_six_routes_all_land` / `test_all_routes_reload_on_code_change` / `test_checkout_moves_code_but_not_the_bundle_layer` |
| `install-command` | `ch2_four_ways` 的 `test_installing_rewrites_the_profile_manifest`。⚠️ 纪律禁止真跑 `dsh plugin` 子命令，对账时机那条只走源码引用 |
| `client-side` | 无用例，⬜。素材在 `.god-flow/drafts/l16-client-plugin.md`，README 里写清要验什么，**不要造用例** |

### 04-replay

| 项 | 来源 |
|---|---|
| `replay-mechanism` | `l07` 的 `test_include_config_holds_full_recipe` / `test_recipe_hot_reload_updates_include_config` |
| `cold-surfaces` | `l06` 的 `test_bundle_patch_and_bundles_list_are_cold` / `test_two_registration_paths_are_independent`；`l04` 的 `test_running_overlay_not_hot_reloaded`；`plugin_wiring` 的 `test_bundle_layer_needs_a_restart_but_live_layer_does_not`；`ch2_bundle_vs_live` 的 `test_one_layer_is_hot_the_other_is_cold` |
| `replay-granularity` | 无用例，⬜。README 里写清观测方法论（信号必须落在被改动的那个条目上），**不要造用例** |

### 05-reload

`chx_hmr_across_junction` 一个文件 14 条判定，本组要拆它。编号是那个文件里的 ①–⑭。

| 项 | 来源 |
|---|---|
| `watch-root` | `step6` 全部 5 条；`chx_hmr` 的 ①②⑥⑭ |
| `ignore-rules` | `chx_hmr` 的 ③④⑤⑦⑨ |
| `reload-unit` | `chx_hmr` 的 ⑩⑫ |
| `new-code-old-config` | `chx_hmr` 的 ⑧ |
| `reload-debounce` | `ch2_worktree` 的 `test_c_one_checkout_is_one_reload` |
| `cold-reads` | ⚠️ **来源待定**：SYLLABUS 说「改 apply 期 `readFileSync` 读的文件是冷的」已验证，但不确定用例在哪。全仓找一遍，找到就搬、标 ✅；找不到就标 ⬜ 并在报告里说明 |
| `reload-while-busy` | `chx_reload_while_busy` 的 `test_what_happens_to_the_work_in_flight` / `test_what_the_caller_sees` / `test_reload_does_not_hang_the_tree`（`test_the_leaky_one_leaves_a_ghost` 归 08 组，别拿） |
| `client-swap` | 无用例，⬜ |
| `hmr-self` | 无用例，⬜。README 写清实验设计要点：必须单轮观测、每轮改动前重启、要有「改别的条目」的对照组 |

`chx_hmr` 的 ⑪ 归 09 组、⑬ 归 08 组，本组别拿。

### 06-inject

| 项 | 来源 |
|---|---|
| `inject-hard-dependency` | `l09` 的 `test_missing_provider`；`step9` 的 `test_waiting_for_a_service_that_never_comes` / `test_without_inject_it_runs` |
| `activation-order` | `l09` 的 `test_dependency_chain_loads_in_service_order` / `test_write_order_does_not_decide_load_order` |
| `dependency-chain` | `l09` 的 `test_missing_middle_breaks_only_second_level` / `test_pending_dependent_seen_through_recorder` |
| `teardown-chain` | 无用例，⬜ |

⚠️ `l09` 的 `test_boot_outcome_for_unsatisfiable_inject` 归 09 组，别拿。
⚠️ `l09` 的 README 里记着一个必须搬过来的坑：`start_instance(wait_http=False)` 立即返回、
不做存活检查，判断启动失败必须自己看 `inst.alive()`，靠 `except LabError` 是无效的。

### 07-tree

| 项 | 来源 |
|---|---|
| `recipe-vs-tree` | `l07` 的 `test_include_is_the_only_ghost`；`l00` 的 `test_effective_config_vs_entry_tree` |
| `hierarchy` | `l08` 的 `test_group_builds_nested_subtree` |
| `disabled-propagation` | `l08` 的 `test_disabled_propagation` |
| `entries-order` | ⚠️ **来源待定**：`l08` 模块 docstring 记着「entries() 顺序不稳定，只有 parent 能信」，但可能没有独立用例。查一遍，有就搬、没有就标 ⬜ 并在报告里说明 |

### 08-service-core

| 项 | 来源 |
|---|---|
| `provide` | `seam_provide_a_service` 全部 2 条 |
| `one-owner` | `seam_one_owner` 全部 3 条 |
| `registry` | `seam_registry` 全部 3 条 |
| `availability-contract` | `seam_who_decides` 全部 3 条 |
| `isolate` | `l08` 的 `test_isolate_gives_each_group_its_own_service_instance`。⚠️ 负面对照未测，README 里标出来 |
| `leak-on-reload` | `chx_reload_while_busy` 的 `test_the_leaky_one_leaves_a_ghost` |
| `module-state-reset` | `chx_hmr_across_junction` 的 ⑬ |
| `effect-vs-raw` / `disposer-order` / `effect-inventory` | 无用例，⬜。`effect-inventory` 的 README 写清 `fiber.getEffects()` 是决定性的观测工具，它把「watcher 还在不在」从间接推断变成直接观测 |

### 09-boot-vs-runtime

本组是**同一种反常在两个时机的两种下场**，所以每一项都要成对：boot 期怎样、运行期怎样。

| 项 | 来源 |
|---|---|
| `boot-audit` | `l00` 的 `test_pending_at_boot_is_fatal`；`l09` 的 `test_boot_outcome_for_unsatisfiable_inject` |
| `boot-failure-shapes` | `step5` 的 `test_a_wrong_name_kills_the_instance` / `test_the_others_ran_before_everything_came_down`；`step9` 的 `test_same_verdict_as_step1` |
| `duplicate-id-timing` | boot 侧：`l05` 的 `test_duplicate_id_at_boot_is_fatal`、`l06` 的 `test_duplicate_id_across_bundle_and_live_layer_kills_boot`、`ch2_bundle_vs_live` 的 `test_same_id_in_both_layers_will_not_start`、`step7` 的 `test_same_id_in_both_places_will_not_start`、`step8` 的 `test_inserting_the_same_id_twice`（五份是同一判定的五份实现，择优合成）；运行期侧：`chx_hmr_across_junction` 的 ⑪ |
| `pending-timing` | 无用例，⬜。boot 侧的结论已经由 `boot-audit` 立住，本项缺的是运行期那一半 |
| `loader-self-deadlock` | 无用例，⬜ |
| `externals-exit` | 无用例，⬜ |

---

## 阶段三验收

- `uv run pytest` 全套跑绿，且**用例总数不少于重组前**
- `out/testhome/` 下没有两项共用一个 home 的情况
- 拿一个有特征的短语 grep 全仓，只命中一处
- `docs/SYLLABUS.md` 已换成覆盖清单，教学装置删干净
- `site/` 与项目根 `index.html` 已删，且删之前判定已回收进各项 README
- 旧的 32 个目录已删干净
