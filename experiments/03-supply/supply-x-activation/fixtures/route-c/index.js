/**
 * 形态 C · 正经安装、走 bundle 层自注册——三个轴第一次同时用满。
 *
 * 三个轴上的取值：
 *   - 供给轴：跟形态 B 一样靠 link 成包、`import("route-c")` 解析包名。
 *   - 激活轴：package.json 里声明了 `dsh.bundle.patch`，指向同目录的
 *     `cordis.patch.yml`。只要 profile 把 route-c 列进
 *     `dsh.profile.bundles`，boot 时框架会自己去读那份 patch、把里面
 *     `insert:` 的条目叠进配方——这个条目不是活层写的，是包自己
 *     带来的。活层这边什么都不用做，条目就已经在树上了。
 *   - 版本钉法轴：换版本要动两处——代码本身的 `CODE_VERSION`，和
 *     `cordis.patch.yml` 里 `层版本: c-r1` 那一行（它代表包自带的
 *     那份「出厂配置」，不是活层能覆盖的默认值）。
 *
 * 存在的意义：跟形态 B 对照，证明「声明 dsh.bundle + 被列进
 * bundles 名单」这两个条件同时成立才会自注册——少一个都不行。
 * 形态 D 补的就是「声明了但没被列进名单」那一半反例。
 */

export const inject = ["labObserver"];

const CODE_VERSION = "c-v1";

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  say("我上树了", { 形态: "C", 代码版本: CODE_VERSION, 层版本: config?.层版本 ?? null });
}
