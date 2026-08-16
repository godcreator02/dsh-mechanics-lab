/**
 * 第 5 步的教学插件 —— 跟第 2 步那个一样简单，只是换了句话。
 *
 * 这一步里它**从头到尾没改过**：每个用例都把这份文件原样放进 profile 目录，
 * 变的只有条目上那一行 `name`。所以凡是没跑起来的，问题都在 `name` 上。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("工具插件跑起来了");
}
