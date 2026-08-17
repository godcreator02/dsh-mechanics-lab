/**
 * 跟 `tool.mjs` 一模一样的一份，只不过住在一个目录里——用来验「`name` 写成
 * 目录名会怎样」。目录里确实有 `index.mjs`，代码本身完全没问题。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("工具插件跑起来了");
}
