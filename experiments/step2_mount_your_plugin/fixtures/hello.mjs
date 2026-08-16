/**
 * 第 2 步的教学插件 —— 一个插件的全部家当。
 *
 * 两件事：
 *   1. `inject` 声明「我要用观察器」，框架保证 apply 跑之前它已经就位
 *   2. `apply` 里说一句话，进事件流
 *
 * 没有 package.json，没有构建，没有依赖安装 —— 就这一个文件。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  // 先告诉观察器「是我在说话」，它会反查我在树上的 id
  const say = ctx.labObserver.for(ctx);

  say("我的 apply 被调用了");
}
