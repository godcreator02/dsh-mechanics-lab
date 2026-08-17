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
 *      「junction 那头的代码算不算 node_modules 里的东西」，答案就藏在第一个里。
 *   4. 报载入次数（模块顶层的计数器）和 `compute()` 的结果。
 */

import { compute } from "./helper.js";

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

  // 我自己是从哪个 URL 被加载的。经 junction 装进来的包，这里报出的是链接
  // 路径还是链接那头的真实路径，直接决定 hmr 那三处
  // `url.includes('/node_modules/')` 命不命中。
  say("我的模块 URL", { url: import.meta.url });

  // hmr 的 baseDir 由 `config.base || '.'` 相对它解析，root 又相对 baseDir。
  say("树的 baseUrl", { baseUrl: ctx.baseUrl ?? null });

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
}
