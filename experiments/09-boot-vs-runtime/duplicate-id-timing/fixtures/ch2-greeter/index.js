/**
 * 同时是包和插件模块本身：`package.json` 声明 `dsh.bundle.patch` 指向同目录
 * `cordis.patch.yml`；那份 patch 里 `name: ch2-greeter` 找的就是这个文件。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 版本: config?.版本 ?? null });
}
