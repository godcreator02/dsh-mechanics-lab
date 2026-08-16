/**
 * 形态 A · 单文件插件 —— 供给轴上最短的路。
 *
 * 三个轴上的取值：
 *   - 供给轴：没有 package.json，靠活层条目里 `name: ./route-a.mjs` 这样的
 *     相对路径直接把 `import(name)` 指到这个文件。没有一层包装能挡，
 *     Node 解析到哪个文件，跑的就是哪个文件。
 *   - 激活轴：不自带任何 bundle 层声明（连声明的地方都没有），
 *     只能靠活层 insert 把条目立起来。
 *   - 版本钉法轴：换版本 = 直接改这个文件本身。没有 package.json 的
 *     version 字段可用，`CODE_VERSION` 这个常量就是唯一的版本痕迹——
 *     用例靠字符串替换把它从 "a-v1" 改成 "a-v2" 来模拟「改代码」。
 *
 * 存在的意义：证明「插件」这个词的下限有多低——不需要包、不需要清单，
 * 一个裸文件 + 一行相对路径就够格被树接纳。
 */

export const inject = ["labObserver"];

const CODE_VERSION = "a-v1";

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  say("我上树了", { 形态: "A", 代码版本: CODE_VERSION, 层版本: config?.层版本 ?? null });
}
