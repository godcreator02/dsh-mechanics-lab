/**
 * 教学插件——一个包，声明了 `dsh.bundle`，但那一段只在包名进了 profile 的
 * `bundles` 名单时才生效，没进名单它就是个普通依赖。两种形态用同一个包。
 *
 * 它干四件事：
 *
 *   1. 报自己代码里写着的「版本」。这三个字就是它的代码，用例把「第一版」
 *      改成「第二版」——于是它再跑一次时说的话不一样，一眼分得出重来过没有。
 *   2. 报 `config` 里那个「版本」。跟上一条来路不同：那个改代码、这个改配方。
 *   3. 报身份三件套：模块 URL、树的 baseUrl、loadCache 里跟自己有关的 key。
 *   4. 报载入次数（模块顶层的计数器）和 `compute()` 的结果。
 */

import { compute } from "./helper.js";

/**
 * 模块顶层的状态，不是 fiber 的状态。热重载会把整个模块重新求值一遍，
 * 这一行也会重跑——于是它归零。
 */
let loads = 0;

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  loads += 1;

  say("我跑起来了", {
    版本: "第一版",
    配置版本: config?.版本 ?? null,
    载入次数: loads,
    算出来: compute(),
  });

  say("我的模块 URL", { url: import.meta.url });
  say("树的 baseUrl", { baseUrl: ctx.baseUrl ?? null });

  // ⚠️ 用 ctx.get 运行时取 loader，不写进 inject：loader 的 intercept 有
  // await 语义，声明依赖它会把本插件锁死在 PENDING。
  const loader = ctx.get("loader");
  const cache = loader?.internal?.loadCache;
  if (!cache) {
    say("loadCache", { 拿到了: false, 说明: "loader.internal 不在（没开 --expose-internals？）" });
  } else {
    const mine = [];
    for (const key of cache.keys()) {
      if (String(key).includes("hmr-linked")) mine.push(String(key));
    }
    say("loadCache 里跟我有关的 key", { 条数: mine.length, keys: mine });
  }

  // 心跳，默认不开（`config.心跳毫秒` 有值才开）：反复调用 compute() 并报出结果，
  // 用来回答「函数调用时会不会回头读磁盘」——不开的话「什么都没发生」有两种
  // 解释（拿到了旧值 / 压根没人调用），心跳把后一种排除掉。
  const ms = config?.心跳毫秒;
  if (ms) {
    let ticks = 0;
    const timer = setInterval(() => {
      ticks += 1;
      say("又算了一次", { 算出来: compute(), 第几次: ticks });
    }, ms);
    timer.unref?.();
    ctx.effect(() => () => clearInterval(timer), "hmr-linked: 心跳");
  }
}
