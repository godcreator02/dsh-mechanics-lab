/**
 * 第 8 步的教学插件 —— 把自己收到的 config 原样报出来。
 *
 * 跟第 3 步那个一样：这一步不改插件，只改 patch 文件里它那一条。
 * 判定全落在它报出来的内容上 —— 改没改成，问它本人最准。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我收到的 config", { 内容: config ?? null });
}
