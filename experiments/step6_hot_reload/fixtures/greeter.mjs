/**
 * 第 6 步的教学插件 —— 每次被调用都报一次自己写着的版本。
 *
 * 「第一版」这三个字就是这个插件的代码。用例把它改成「第二版」，
 * 于是插件再跑一次时说的话不一样 —— 一眼分得出这是第几次。
 */

export const inject = ["labObserver"];

export function apply(ctx) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 版本: "第一版" });
}
