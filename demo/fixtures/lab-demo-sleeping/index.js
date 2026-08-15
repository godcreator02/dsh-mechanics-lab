/**
 * 演示件：条目上写了 `disabled: true` 的插件。
 *
 * 面板显示 **DISABLED**（灰）。注意它压根不会创建 fiber ——
 * 所以 DISABLED 严格说不是 FiberState 里的成员，是**条目级**状态。
 * 它和 PENDING 的区别很要紧：DISABLED 是人主动关的，PENDING 是依赖没到位。
 */
export function apply(ctx, config) {
  // 永远不会执行 —— 被禁用的条目不 init
}
