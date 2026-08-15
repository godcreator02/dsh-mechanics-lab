/**
 * 演示件：依赖一个永远不会出现的服务。
 *
 * 面板显示 **PENDING**（黄）——fiber 建出来了，但卡在「等 inject 声明的服务就位」。
 *
 * 这正是 PENDING 与 DISABLED 的分水岭：这个插件**没有**被任何人关掉，
 * 它只是在等一个不会来的东西。生产环境里看到 PENDING，八成是依赖写错了名字，
 * 或者提供方自己没起来。
 */

/** 一个不存在的服务名 —— 没有任何插件会 provide 它。 */
export const inject = ["压根不存在的服务"];

export function apply(ctx, config) {
  // 永远不会执行 —— inject 没满足，fiber 停在 PENDING
}
