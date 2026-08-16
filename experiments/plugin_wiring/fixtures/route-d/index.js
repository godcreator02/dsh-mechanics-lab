/**
 * 形态 D · 装了、但没进 bundles 名单 —— 「声明」跟「激活」是两件事。
 *
 * 三个轴上的取值：
 *   - 供给轴：跟形态 C 一样靠 link 成包、`import("route-d")` 解析包名。
 *     包本身跟正经安装没有任何区别——link 进了 profile 的
 *     node_modules，`import` 解析得到、`dsh.bundle` 字段也声明了。
 *   - 激活轴：这正是本形态要讲的重点——**声明了 `dsh.bundle` 不等于
 *     一定会自注册**，还要看 profile 的 `dsh.profile.bundles` 名单
 *     有没有点它的名字。用例故意不把 route-d 列进名单，于是
 *     `cordis.patch.yml` 里那条 `id: route-d-selfmounted` 永远不会
 *     被 boot 读到、永远不会上树。
 *     条目真正上树靠的是活层另外单独 insert 的 `id: route-d`
 *     （`层版本: d-live1`）——跟包自带的那条是完全不同的两个条目。
 *   - 版本钉法轴：跟形态 C 一样，代码版本改 `CODE_VERSION`；
 *     但包自带的那份 `层版本` 因为从未被激活，改不改都没有可观测效果，
 *     活层 insert 里的 `层版本` 才是真正生效的那份。
 *
 * 存在的意义：把「装了这个包」「包自己声明了 bundle」「这个 bundle
 * 真的被激活」三件事拆成三个独立开关，证明只有全部拨对才会自注册。
 */

export const inject = ["labObserver"];

const CODE_VERSION = "d-v1";

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  say("我上树了", { 形态: "D", 代码版本: CODE_VERSION, 层版本: config?.层版本 ?? null });
}
