/**
 * 一个能跑的最小插件。这一项里它从头到尾没改过——每个用例都把这份文件
 * 原样放进 profile 目录，变的只有条目上那一行 `name`。凡是没跑起来的，
 * 问题都在 `name` 上。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("工具插件跑起来了");
}
