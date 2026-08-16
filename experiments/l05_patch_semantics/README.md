# L5 · patch 的三种语义

**这一课回答：** `- insert:`（带/不带 id）与 `- id:`（覆盖已有条目）各是什么语义，
以及几条官方文档没写、只能实测的边界。

跑法：`uv run pytest experiments/l05_patch_semantics/`（约 19 秒，9 个用例）

---

## 唯一实现，唯一入口

三种语义只有一处实现——`cordis-plugin-include` 的 `applyEntryPatches()`
（`<npx 缓存>/node_modules/@deepseek-ai/cordis-plugin-include/src/index.ts:58-128`）：

```js
for (const patch of patches) {
  const { id, insert, name, ...overrides } = patch
  if (insert) {
    if (id) {
      const target = entryMap.get(id)
      if (!target) { warn('patch insert: entry %C not found', id); continue }
      if (!target.group) { warn('patch insert: entry %C is not a group', id); continue }
      target.config.push(...insert)     // ← 带 id：塞进该 group
    } else {
      data.push(...insert)               // ← 不带 id：追加进根组
    }
    buildMap(insert)                     // ← 让后面的 patch 能改刚插进来的行
    continue
  }
  if (!id) { warn('patch: id is required for non-insert patches'); continue }
  const target = entryMap.get(id)
  if (!target) { warn('patch: entry %C not found', id); continue }
  if (name && name !== target.name) { warn('patch: name mismatch ...'); continue }
  for (const [key, value] of Object.entries(overrides)) {
    if (key === 'id') continue
    target[key] = value                  // ← 覆盖：整键赋值，非深度合并
  }
}
```

**这个函数被两条路复用**（`dsh-app-boot/lib/index.js` 的注释原话：
*"the same single `applyEntryPatches` call the boot include makes"*）：

- `dsh --dump-config` 的 `renderConfigDump()` / `composeEntries()`
- 运行时真实挂载的 `Include.applyPatches()`

**这正是本课绝大多数用例能靠静态 `--dump-config` 验证、不用真的拉实例的原因**
——静态算出来的树，和真实挂载走的是**同一套** compose 逻辑，不是近似模拟。
9 个用例里只有 2 个必须拉实例：`disabled` 的 `!!js` 求值（求值发生在条目激活时，
dump 只保留表达式原文）和同 id 双挂载的 boot 期致命性（那是**挂载期**的查重，
dump 阶段还没查）。

⚠️ **一个工具坑**：`lab.dump_config()` 成功时会**静默丢弃 stderr**，而 patch 的警告
（`patch: entry ... not found` 这类）恰恰走 stderr、且从不影响退出码——
`renderConfigDump` 的默认 `warn` 只是 `process.stderr.write`，从不 `throw`。
本课在 `test_l05.py` 里自己包了一层 `dump_with_warnings()` 把 stderr 带出来，
**没有改 `lab/dump.py`**——公共脚手架不动，只是本课自己多留一份。

---

## 一、三种语义，一一实测

### 1. `insert:` 不带 id → 追加进根组

```yaml
- insert:
    - id: alpha
      name: dummy-alpha
    - id: beta
      name: dummy-beta
```

`dump.ids() == ["alpha", "beta"]`，按原样顺序进了根组。最基本的形态，
本课其余每个用例的第一步都在用它把测试条目铺进树里。

### 2. `insert:` 带 id → id 是「目标 group」，不是新条目的 id

这是最容易读错的一条。`insert: 带的 id 指向一个已存在的、`group: true` 的容器，
`insert` 列表塞进它的 `config` 数组——**不是**给新条目起名叫这个 id。

实测：目标存在但不是 group（普通条目，没有 `group: true`）——

```yaml
- insert:
    - id: leaf
      name: dummy-leaf
      config: {x: 1}
- id: leaf
  insert:
    - id: child
      name: dummy-child
```

结果：`child` 完全没被创建，`leaf` 自己毫发无损（`config` 还是 `{x: 1}`），
stderr 里多一行：

```
patch insert: entry "leaf" is not a group
```

**整条 patch 被跳过**，不是报错中断——这条规律在本课反复出现，见下面第三节。

### 3. `- id:` 覆盖：整键赋值，非深度合并

📗 官方文档写得很明确（`docs/official/zh/user/develop/basic/publish.md:123`）：

> 后应用的层按行胜出，且 patch 会替换目标行的整个 `config` 值，而不是深度合并各键。

推论（同文档 :125）：**覆盖时必须重述该行需要的每一个键，不能只写改动的那个**——
只写 `config: {x: 99}` 会让 `config` 变成只有 `x` 的新对象，原来 `config` 里的
别的键全部消失，因为整个 `config` 是被替换掉的，不是合并进去的。

本课用例 4（`test_later_patch_can_target_earlier_insert`）实测了这一条，
与文档一致，不再单独复述。

---

## 二、文档没写、只能实测的四条边界

### `null` 到底删不删键？—— 不删，字面赋值成 `null`

`applyEntryPatches` 的覆盖分支就是 `target[key] = value`，对 `null` 没有任何
特殊处理。真正「`isNullable(value)` 就 `delete candidate[key]`」的逻辑在
`cordis-plugin-loader` 的 `Entry.update(options, create, force)` 里
（`config/entry.ts:142-154`），但那段代码只在 `create === false` 时跑：

```js
const candidate = create ? options as EntryOptions : { ...previousOptions }
if (!create) {
  for (const [key, value] of Object.entries(options)) {
    if (isNullable(value)) delete candidate[key]
    else candidate[key] = value
  }
}
```

而 YAML 批量重载的调用链——`Include._apply` → `EntryGroup.update`
（`cordis-plugin-loader/src/config/group.ts:59-66`，遍历新配置逐个调用
`this.create(options)`）→ `EntryGroup.create()`（同文件 :20-30，
内部固定 `entry.update(options, true, true)`）——**永远传 `create=true`**，
走的是 `candidate = options` 整份顶替，根本不进那个 `delete` 分支。

实测（用例 3）：

```yaml
- insert:
    - id: solo
      name: dummy-solo
      disabled: true
- id: solo
  disabled: null
```

```python
solo 条目：{'id': 'solo', 'name': 'dummy-solo', 'disabled': None}
```

**键还在，值是字面 `None`（YAML/Python 的 `null`），不是被删除。** 这条对写 patch
的人有直接后果：想真的去掉一个键，`键: null` 做不到——那只是把值改成 `null`；
`disabled: null` 经 `Boolean(null) = false`，副作用上等价于「启用」，
不是「删除禁用配置」。

### 同一叠里，后面的 patch 能改前面 insert 刚插进来的条目

`buildMap(insert)` 是有意为之：每插入一批条目就立刻把它们登记进 `entryMap`
索引，所以同一份 patch 数组里，**后面的行能定位到前面 `insert` 刚创建的行**：

```yaml
- insert:
    - id: kid
      name: dummy-kid
      config: {n: 1}
- id: kid
  config: {n: 2}
```

实测（用例 4）：`kid` 的最终 `config == {"n": 2}`。而且这不只在**同一层**内成立——
四层 patch（bundle 层 + 用户活层 + home 层 + `--patch` overlay）在传给
`applyEntryPatches` 之前会先拼成**一个数组**（`allPatches()`），所以「后面」是
**跨层**的：用户活层能改到 bundle 层刚 `insert` 进来的行，不需要它是 group。

### 覆盖找不到 id：只警告 + 跳过这一条，同批其余 patch 照常生效

```yaml
- insert:
    - id: alpha
      name: dummy-alpha
      config: {x: 1}
- id: no-such-id
  config: {y: 2}
- id: alpha
  config: {x: 99}
```

实测（用例 5）：`no-such-id` 从未被创建，stderr 有
`patch: entry "no-such-id" not found`；但**第三条 patch 照常把 alpha 的 config
改成了 `{x: 99}`**——一条 patch 打空只跳过它自己，不拖累同一批里的其余 patch。

这跟「改配置没生效」是两种不同的现象，排查时别混：前者是这条 patch 的目标
从一开始就不存在（这里能看到明确的警告字符串），后者通常是目标存在但改动
没被感知到（比如活层没被 watcher 看到）。

### 野字段：patch 能塞任意键，且不报任何错误或警告

`applyEntryPatches` 和 `EntryOptions`（TS 接口）都没有字段白名单——覆盖分支
`target[key] = value` 是纯对象赋值，运行时没有类型检查。实测（用例 6）：

```yaml
- insert:
    - id: wild
      name: dummy-wild
- id: wild
  随便字段: "loader 不认识我"
  另一个字段: 42
```

两个野字段原样进了组合树，stderr 空白。这是 L2 已经在**声明层面**验过的结论
（条目只有六个字段，多的带着走不报错）在**patch 层面**的对应版本——两处结论
一致，但机制是两个不同的函数（声明层面是「随便写进 YAML 就没有过滤」，
patch 层面是 `applyEntryPatches` 覆盖分支同样不过滤）。

---

## 三、`disabled: !!js`：postmortem 0002 的活教材

### 官方事故复盘讲了什么

`docs/official/zh/postmortem/0002-js-expression-disabled-filesystem-tools.md`
记的是一次真实事故：ACP 组合想用 `disabled: !!js <条件>` 有条件地启用文件系统
插件，结果**文件系统插件永远被禁用**，而快照测试全绿通过（因为快照套件把
「工具不存在，报了确定性的 `UNKNOWN_TOOL` 错误」也当成了合法的、可复现的
预期输出）。

根因段（原文）：

> 实现时假设 `!!js` 适用于整个 Loader 配置项。实际只有 `entry.options.config`
> 使用它：`Entry._resolveConfig()` 对该字段进行插值，而 `Entry.disabled` 直接测试
> `entry.options.disabled`，**不经过插值**。YAML 标签在语法上合法，因此加载过程
> 不产生任何诊断信息。

也就是说：`!!js <表达式>` 被 Cordis Include 解析成一个表达式对象
（`{ __jsExpr: "<表达式>" }`），这个对象本身是 truthy——如果 `disabled` 字段
从不对它求值，那不管表达式写的是 `true` 还是 `false`，`Boolean(表达式对象)`
恒为 `true`，条目恒被禁用。这正是标题里「文件系统工具被永久禁用」的由来。

官方给的教训（原文）：

> 语法上被接受的配置值不一定在该位置被求值；应记录并验证具体对哪些字段进行插值。

### 当前代码：这条已经被修了

`cordis-plugin-loader/src/config/entry.ts:104-108` 的 `disabledOf()`：

```js
private disabledOf(options: EntryOptions): boolean {
  return isJsExpr(options.disabled)
    ? Boolean(this.evaluate(options.disabled.__jsExpr))
    : Boolean(options.disabled)
}
```

**这段代码明确对 `!!js` 表达式求值**——跟 postmortem 根因段描述的「直接测试
`options.disabled`、不插值」的状态不一样。GLOSSARY / SYLLABUS 已经记了这条
（当前支持 `!!js`），但 postmortem 文档本身**没有加「已修复」的追记**，
单看这篇 postmortem 会误以为 bug 仍在。

### 实测：用能分辨两种世界的写法验证

`!!js false` 和 `!!js true` 都是「语法合法的表达式对象」——如果 postmortem
描述的 bug 仍在，**两者都应该恒真**（对象本身 truthy），插件永远不加载；
如果已经修复，两者的加载结果应该**相反**：

| 表达式 | postmortem 描述的（bug）世界 | 当前代码（已修）世界 | 实测结果 |
|---|---|---|---|
| `!!js false` | 恒真 → 不加载 | 求值为 `false` → 加载 | ✅ **加载了** |
| `!!js true` | 恒真 → 不加载 | 求值为 `true` → 不加载 | ✅ **未加载** |

```
!!js false → 加载了：l05-patch-v1
!!js true → 未加载（12s 内没写见证文件）
```

两个结果相反，直接证明**当前部署确实在对 `disabled` 里的 `!!js` 求值**，
postmortem 描述的那个 bug 状态不是这个版本的真实行为。

**这是本课乃至整个实验台最干净的一次「语法合法 ≠ 该处被求值」教学案例**：
同一份 postmortem，既证明了「曾经有个字段被漏掉插值」，又（被这次实测）
证明了「后来被修好了，但事故记录本身没有随代码演进」。读源码判断某个字段
会不会被求值，永远比读一篇可能过期的事故报告可靠——即使那篇报告出自官方。

---

## 四、同 id 双挂载：boot 期是「起不来」，不是「回滚」

顺手验了一条 CLAUDE.md 已经记过、但没人在这门课里现场演示过的判定
（用例 8，标记可选，仍然写了，因为现场演示比转述可靠）。

`EntryGroup.update()` 的查重循环在 `try` 块**之外**
（`cordis-plugin-loader/src/config/group.ts:59-66`）：

```js
async update(config: EntryOptions[]) {
  const seen = new Set<string>()
  for (const options of config) {
    const id = this.tree.ensureId(options)
    if (seen.has(id)) throw new TypeError(`duplicate loader entry id: ${id}`)
    seen.add(id)
  }
  // …一个 create() 都还没调用，抛错已经发生
```

造法：两个独立的 `- insert:` 块（都不带 id，都追加进根组），但块里的条目
**id 相同**——`applyEntryPatches` 本身不去重（它只在 insert 时 `buildMap`
建索引，从不检查冲突），所以两个同 id 的条目会一起进最终的组合数组，
静态 dump 就能看到（本课用例 8 先验了这一步：dump 里 `id=dup` 的条目数是 2，
`applyEntryPatches` 阶段没有任何警告——冲突要留到挂载期才现形）。

实测（拉真实例）：

```
进程还活着？ False（退出码 1，死于 +0.5s）
日志：Error: dsh: plugin tree failed to load: failed to apply loader entry
      include (cordis:include): duplicate loader entry id: dup
      TypeError: duplicate loader entry id: dup
```

这一次撞在**首次 boot**：`assertEntriesActivated` 根本没机会跑到——
`EntryGroup.update` 从一开始就没有一个 `create()` 成功过，boot() 直接失败，
**整个进程死掉**。这跟「运行中热重放撞见同一个错误」是两条不同的路径
（那时只是这一次重放作废、旧条目继续跑，进程不受影响）——本课只验了
boot 期这一半，运行期热重放那一半留给 L14（配方热重放讲透之后才有工具去测
「重放失败到底回滚到哪一步」）。

---

## 五、这一课立住的词

- **`insert:` 目标是 group，不是新条目 id** —— 带 id 的 insert 塞进那个 group 的
  `config` 数组，不是给新条目起名
- **整键赋值** —— 覆盖 `config` 是整个值替换，不是深度合并各键
- **`null` 是字面赋值，不是删除** —— 覆盖调用链永远走 `create=true`，
  只有 `create=false`（本课范围外的另一条路径）才会真的 `delete` 键
- **跨层索引** —— `buildMap(insert)` 让同一份拼接后的 patch 数组里，
  后面的层能改到前面任何一层（含 bundle 层）刚插进来的行
- **打空跳过，不拖累同批** —— 找不到目标只警告，这条 patch 作废，
  其余 patch 该生效照样生效
- **语法合法 ≠ 该处被求值** —— `!!js` 只在 `config` 字段被插值这件事，
  一度因为 `disabled` 字段被漏掉而酿成真实事故（postmortem 0002），
  现在已经修好，但要靠读源码或实测确认，不能只读事故报告的结论

## 六、下一课

**L6 · bundle 层 vs 活层** —— 两层的冷热差别：改 bundle 的 patch 文件对正在跑的
实例有没有影响？`dsh plugin add` 按什么时机对账 `bundles` 名单？
