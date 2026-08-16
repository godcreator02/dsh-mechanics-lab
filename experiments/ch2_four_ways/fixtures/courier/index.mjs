/**
 * 第 9 项的教学插件 —— 四种交付途径共用的**同一份代码**。
 *
 * 它只做一件事：把自己收到的 `config.途径` 原样报给观察器。于是「我是用哪种
 * 途径挂上去的」这件事，由插件自己说出来，而不是由我们从旁边推断。
 *
 * ⚠️ 这个文件被两种方式用到，一个字都不改：
 *   * 途径①：这个文件本身被拷进 profile 目录，条目的 `name` 写它的相对路径
 *   * 途径②③④：它是同目录那个包的入口（见 package.json 的 exports）
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 途径: config?.途径 });
}
