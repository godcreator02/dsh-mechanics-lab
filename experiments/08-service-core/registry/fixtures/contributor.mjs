/**
 * 往名册里塞一行的那一方 —— **注册方**。
 *
 * 它不占任何名字，只是 `inject` 名册、往里塞一行。所以想塞几个就挂几条，
 * 彼此之间不会撞车。
 *
 * 塞进去的 id 由 config 给，同一个文件可以挂多次。
 */

export const inject = ["labObserver", "labRoster"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  ctx.labRoster.register(config.我叫, { 来自: config.我叫 });

  say(`我往名册里塞了「${config.我叫}」`, { 塞完表里有: ctx.labRoster.list() });
}
