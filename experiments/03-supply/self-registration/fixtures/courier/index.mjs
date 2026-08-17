/**
 * 负对照用的教学插件：包里声明了 `dsh.bundle`，但只 link 不装的话什么都不会
 * 发生。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 途径: config?.途径 });
}
