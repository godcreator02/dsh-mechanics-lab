/**
 * 这一项唯一的教学插件。它是一个**包**，但故意不声明 `dsh.bundle` ——
 * 这一项不测包自注册（那是第 10 项的事），条目一律写在活层，省掉两层同 id
 * 撞车那个坑。
 *
 * 它干两件事：
 *
 *   1. 报自己代码里写着的「版本」。这三个字就是它的代码，用例把「第一版」
 *      改成「第二版」—— 于是它再跑一次时说的话不一样，一眼分得出重来过没有。
 *   2. 报出自己的**身份三件套**：模块 URL、树的 baseUrl、loadCache 里跟自己
 *      有关的 key。这一项要判的「junction 那头的代码算不算 node_modules 里的
 *      东西」，答案就藏在第一个里 —— 被测对象自己报出自己的 URL，比从外面
 *      去问 loader 少一层猜。
 *
 * 三件套只在能拿到时报，拿不到就报拿不到：观测拿不到数据是一回事，
 * 把被观测的进程搞崩是另一回事。
 */

export const inject = ["labObserver"];

export function apply(ctx) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 版本: "第一版" });

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
    return;
  }
  const mine = [];
  for (const key of cache.keys()) {
    if (String(key).includes("hmr-linked")) mine.push(String(key));
  }
  say("loadCache 里跟我有关的 key", { 条数: mine.length, keys: mine });
}
