/**
 * ch2-greeter ——一个包身兼两职：
 *
 *   1. 它是**包**：`package.json` 声明了 `dsh.bundle.patch`，指向同目录的
 *      `cordis.patch.yml`。这个包一旦进了某个 profile 的 bundle 名单，那份
 *      patch 文件里写的条目就自动上树——不用手写 insert。
 *   2. 它也是那份 patch 文件指向的**插件模块**：`name: ch2-greeter` 找的就是
 *      这个文件，真正的 `apply` 长在这儿。
 *
 * 只干一件事：把自己收到的 `版本` 报出来。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 版本: config?.版本 ?? null });
}
