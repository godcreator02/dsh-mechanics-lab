/**
 * 报自己收到的「版本」，外加代码里改一次就能分辨「重来过没有」的那句话。
 * 撞车之后本项还要验「实例是不是仍然健康」，做法是改这个文件、看它还认不认
 * ——所以留着这句可改的标记，即使本项默认不去改它。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 版本: "代码第一版", 配置版本: config?.版本 ?? null });
}
