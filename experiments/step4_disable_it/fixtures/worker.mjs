/**
 * 第 4 步的教学插件 —— 跑起来就吱一声，好让人看出它到底跑没跑。
 *
 * 跟第 2 步那个一样简单：声明要用观察器，在 `apply` 里说一句话。
 * 这一步不改插件，只改 patch 文件里它那一条。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 收到的config: config ?? null });
}
