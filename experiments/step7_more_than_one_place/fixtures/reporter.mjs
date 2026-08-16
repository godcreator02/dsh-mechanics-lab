/**
 * 第 7 步的教学插件 —— 把自己收到的 config 原样报出来。
 *
 * 跟第 3 步那个是同一件事：这一步要看的是「同一个条目在两处都被写到时，
 * 它最后收到的是哪一份」，判据只能是插件自己报出来的内容。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我收到的 config", { 类型: typeof config, 内容: config ?? null });
}
