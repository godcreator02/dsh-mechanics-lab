/**
 * 教学插件——一个包，声明了 `dsh.bundle`，但那一段只在包名进了 profile 的
 * `bundles` 名单时才生效，没进名单它就是个普通依赖。
 *
 * 它干四件事：
 *
 *   1. 报自己代码里写着的「版本」。用例把「第一版」改成「第二版」，一眼分得出
 *      重来过没有。
 *   2. 报 `config` 里那个「版本」——来路不同：那个改代码、这个改配方。
 *   3. 报身份三件套：模块 URL、树的 baseUrl、loadCache 里跟自己有关的 key。
 *   4. 报载入次数（模块顶层的计数器）和 `compute()` 的结果。
 */

import { compute } from "./helper.js";

/**
 * ⚠️ 模块顶层的状态，不是 fiber 的状态。热重载会把整个模块重新求值一遍，
 * 这一行也会重跑——于是它归零；同一个模块被两个条目挂着时，两次 apply
 * 共享同一个模块实例，这个数会数到 2。同一个计数器，两种现象分得开。
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
}
