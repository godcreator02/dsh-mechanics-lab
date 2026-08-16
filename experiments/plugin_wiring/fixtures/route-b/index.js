/**
 * 形态 B · link 成包 —— 供给轴换了一层，激活轴没变。
 *
 * 三个轴上的取值：
 *   - 供给轴：有了最小的 package.json（name / exports 齐全），靠
 *     junction/link 把这个目录接进 profile 的 node_modules，`import(name)`
 *     解析的是包名 "route-b"，不再是相对路径。这是形态 A 到形态 C/D 之间的
 *     过渡态：像一个正经的包，但还没有 `dsh.bundle` 这个字段。
 *   - 激活轴：package.json 里**没有**声明 `dsh.bundle`，所以 boot 时的
 *     bundle 层自注册轮不到它——它没有自己的 patch 叠层可读。
 *     唯一能把条目立起来的办法是活层自己 insert 一条。
 *   - 版本钉法轴：跟形态 A 一样，换版本靠改这份源码本身；
 *     package.json 的 version 字段在这里只是摆设，没人读它来钉版本。
 *
 * 存在的意义：把「像一个包」和「被框架当成 bundle 自动接管」这两件事
 * 拆开——形态 B 证明单靠包装不会自动获得自注册资格，必须显式声明。
 */

export const inject = ["labObserver"];

const CODE_VERSION = "b-v1";

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  say("我上树了", { 形态: "B", 代码版本: CODE_VERSION, 层版本: config?.层版本 ?? null });
}
