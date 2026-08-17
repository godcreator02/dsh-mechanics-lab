/**
 * 对照组插件：从头到尾不改，每个用例都原样放进 profile 目录，变的只有条目
 * 上那一行 `name`——所以凡是没跑起来的，问题都在 `name` 上。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("工具插件跑起来了");
}
