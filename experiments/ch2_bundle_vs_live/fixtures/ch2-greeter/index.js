/**
 * ch2-greeter —— 这一项唯一的教学插件，同时它自己就是一个**包**。
 *
 * 一个包身兼两职：
 *
 *   1. 它是**包**：`package.json` 声明了 `dsh.bundle.patch`，指向同目录的
 *      `cordis.patch.yml`。这个包一旦进了某个 profile 的 bundle 名单，那份
 *      patch 文件里写的条目就自动上树 —— 不用谁去手写 insert。
 *   2. 它也是那份 patch 文件指向的**插件模块**：`name: ch2-greeter` 找的就是
 *      这个文件，真正的 `apply` 长在这儿。
 *
 * 它只干一件事：把自己收到的 `版本` 报出来。这一项要分辨的两种改动
 * （改 profile 那份 patch 文件 / 改包里这份 patch 文件）光看进程活没活分不出来，
 * 只有它自己报出来的内容能说清「此刻挂着的是哪一版」。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 版本: config?.版本 ?? null });
}
