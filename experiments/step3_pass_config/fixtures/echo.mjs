/**
 * 第 3 步的教学插件 —— 把自己收到的 config 原样报出来。
 *
 * 跟第 2 步那个只差一行：`apply` 的第二个参数带上了。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  // 单独报一次类型：undefined 进 JSON 会让整个键消失，
  // 不记类型就分不清「收到了 undefined」和「压根没报这个字段」
  say("我收到的 config", { 类型: typeof config, 内容: config ?? null });
}
