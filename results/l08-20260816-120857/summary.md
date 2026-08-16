# l08 · 20260816-120857

跑于 2026-08-16 12:08:57（本地时间）

## 用例

### ✅ `test_group_builds_nested_subtree`  ·  6.11s

```
[lab] 实验台被 l04 占用中，排队等待…
[lab] 排队 3s 后拿到锁

  ── outer-group ⊃ {leaf-1, inner-group ⊃ leaf-2} ──
    · id=include              cordis:include                         state=2
        · id=census               l08-census                             state=2  ⊂include
        · id=outer-group          @deepseek-ai/cordis-plugin-group       state=2 [group]  ⊂include
            · id=leaf-1               l08-leaf                               state=2  ⊂outer-group
            · id=inner-group          @deepseek-ai/cordis-plugin-group       state=2 [group]  ⊂outer-group
                · id=leaf-2               l08-leaf                               state=2  ⊂inner-group
    · id=86b74f9e             @deepseek-ai/cordis-plugin-timer       state=2
    · id=646e3e7b             @deepseek-ai/cordis-plugin-hmr         state=2

  深度：outer-group=1  leaf-1=2  inner-group=2  leaf-2=3
  扁平列表里的出场顺序：['include', 'census', 'outer-group', 'leaf-1', 'inner-group', 'leaf-2', '86b74f9e', '646e3e7b']
  → 三层深的 leaf-2 和顶层的 census 摊在同一个列表里，没有 parent 字段分不出谁在谁下面
```

### ✅ `test_disabled_propagation[group \u81ea\u5df1\u4e0d\u53d7 disabled \u5f71\u54cd\uff0c\u5b69\u5b50\u5374\u56e0\u5b83\u800c\u505c-group-\n    - id: disabled-group\n      name: '@deepseek-ai/cordis-plugin-group'\n      group: true\n      disabled: true\n      config:\n        - id: child-under-disabled\n          name: l08-leaf\n-disabled-group-child-under-disabled]`  ·  6.11s

```
── group 自己不受 disabled 影响，孩子却因它而停 ──
    · id=include              cordis:include                         state=2
        · id=census-group         l08-census                             state=2  ⊂include
        · id=disabled-group       @deepseek-ai/cordis-plugin-group       state=2 [group, disabled(原文)]  ⊂include
            · id=child-under-disabled l08-leaf                               无 fiber  ⊂disabled-group
    · id=ff1316e0             @deepseek-ai/cordis-plugin-timer       state=2
    · id=10f3b40b             @deepseek-ai/cordis-plugin-hmr         state=2

  disabled-group：disabled(原文)=True  hasFiber=True  fiberState=2
  child-under-disabled：hasFiber=False  fiberState=None
```

### ✅ `test_disabled_propagation[\u5bf9\u7167\u7ec4\uff1a\u666e\u901a\u6761\u76ee\u88ab\u7981\u7528\uff0c\u81ea\u5df1\u5c31\u771f\u7684\u4e0d\u6fc0\u6d3b-plain-\n    - id: disabled-plain\n      name: l08-leaf\n      disabled: true\n-None-disabled-plain]`  ·  6.13s

```
── 对照组：普通条目被禁用，自己就真的不激活 ──
    · id=include              cordis:include                         state=2
        · id=census-plain         l08-census                             state=2  ⊂include
        · id=disabled-plain       l08-leaf                               无 fiber [disabled(原文)]  ⊂include
    · id=0f7a0781             @deepseek-ai/cordis-plugin-timer       state=2
    · id=eb0acdbf             @deepseek-ai/cordis-plugin-hmr         state=2

  disabled-plain：disabled(原文)=True  hasFiber=False
```

### ✅ `test_isolate_gives_each_group_its_own_service_instance`  ·  0.66s

```
── group-a{flavor-a, taster-a} / group-b{flavor-b, taster-b} ──
    （没有这张快照）

  group-a 的 taster 看到：{'marker': 'lab-flavor-taster-v1', 'appliedAt': '2026-08-16T04:08:56.811Z', 'sawValue': 'vanilla', 'sawProviderMarker': 'lab-flavor-v1'}
  group-b 的 taster 看到：{'marker': 'lab-flavor-taster-v1', 'appliedAt': '2026-08-16T04:08:56.811Z', 'sawValue': 'chocolate', 'sawProviderMarker': 'lab-flavor-v1'}
  → 隔离生效：两组各自看到自己的服务实例，没有互相覆盖
```

## 归档的观测产物

- `census-disabled-group.json` — 3,641 字节
- `census-disabled-plain.json` — 3,031 字节
- `census-isolate.json` — 2,647 字节
- `census-nesting.json` — 4,442 字节
- `witness-flavor-a.json` — 146 字节
- `witness-flavor-b.json` — 148 字节
