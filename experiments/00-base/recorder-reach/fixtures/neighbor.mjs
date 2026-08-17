/**
 * 陪衬插件——存在的意义只有一个：给采集器一个「别人」可看。
 *
 * 全部内容两件事：
 *   1. 声明要用观察器 —— 框架保证它先就位，之后本文件才被调用
 *   2. 在 apply 里说一句话 —— 这句话进采集器那条事件流
 *
 * 没有 package.json，没有构建，没有依赖安装，就这一个文件。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  // 先把自己的 ctx 交给观察器，它据此反查「说话的是树上哪一条」
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了");
}
