/**
 * 这一项唯一的教学插件。它是一个**包**，声明了 `dsh.bundle` —— 但那一段只在
 * 包名进了 profile 的 `bundles` 名单时才生效，没进名单它就是个普通依赖。
 * 两种形态都用这同一个包（区别在用例怎么装它）。
 *
 * 它干四件事：
 *
 *   1. 报自己代码里写着的「版本」。这三个字就是它的代码，用例把「第一版」
 *      改成「第二版」—— 于是它再跑一次时说的话不一样，一眼分得出重来过没有。
 *   2. 报 `config` 里那个「版本」。跟上一条来路不同：那个改代码、这个改配方。
 *   3. 报**身份三件套**：模块 URL、树的 baseUrl、loadCache 里跟自己有关的 key。
 *      「junction 那头的代码算不算 node_modules 里的东西」，答案就藏在第一个里。
 *   4. 报**载入次数**（模块顶层的计数器）和 `compute()` 的结果。这两个是给
 *      ⑫⑬⑭ 用的，见下面各自的注释。
 */

import { compute } from "./helper.js";

/**
 * ⚠️ 模块顶层的状态，不是 fiber 的状态。
 *
 * 热重载会把整个模块重新求值一遍，这一行也会重跑 —— 于是它归零。⑬ 判的就是
 * 这个数：重载之后它报 1（模块是新的、旧状态没了），而不是 2（同一个模块实例
 * 又跑了一次 apply）。
 *
 * 反过来，同一个模块被两个条目挂着时（⑩ 那种），两次 apply 共享同一个模块
 * 实例，这个数会数到 2。同一个计数器，两种现象分得开。
 */
let loads = 0;

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  loads += 1;

  // 两个版本号来路不同，⑧ 靠它们分家：
  //   版本     —— 写死在这个文件里，改它就是「改代码」
  //   配置版本 —— 从条目的 config 来，改它是「改配方」
  // 活层那几条用例没给 config，那里它就是 null。
  say("我跑起来了", {
    版本: "第一版",
    配置版本: config?.版本 ?? null,
    载入次数: loads,
    算出来: compute(),
  });

  // 我自己是从哪个 URL 被加载的。经 junction 装进来的包，这里报出的是
  // 链接路径还是链接那头的真实路径，直接决定 hmr 那三处
  // `url.includes('/node_modules/')` 命不命中。
  say("我的模块 URL", { url: import.meta.url });

  // hmr 的 baseDir 由 `config.base || '.'` 相对它解析，root 又相对 baseDir。
  say("树的 baseUrl", { baseUrl: ctx.baseUrl ?? null });

  // ⚠️ 用 ctx.get 运行时取 loader，**不写进 inject**：loader 的 intercept 有
  // await 语义，声明依赖它会把本插件锁死在 PENDING（采集器文件头记着这个坑）。
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

  // ⑭ 专用，默认不开（`config.心跳毫秒` 有值才开）。
  //
  // 它反复调用 `compute()` 并把结果报出来 —— 用来回答「函数调用时会不会回头
  // 读磁盘」。没有它的话，「改了 helper.js 但什么都没发生」有两种解释：
  // 一种是调用拿到了旧值，另一种是压根没人调用。心跳把后一种排除掉。
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
