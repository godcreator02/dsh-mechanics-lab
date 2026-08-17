/**
 * 把自己收到的 config 原样报给 lab-recorder。
 *
 * 用于「同一个条目在 profile 层与 home 层都被写到时，它最后收到的是哪一份」
 * 这类判定——判据只能是插件自己报出来的内容，写进哪个文件是我们做的事，
 * 收到什么是它说的事，两边摆在一起才叫对上了。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我收到的 config", { 类型: typeof config, 内容: config ?? null });
}
