/**
 * 教学插件「greeter」第一版——包的入口文件。
 *
 * 拆成三个文件：这个入口，加两个各只导出一个常量的小文件。拆开是有意的：
 * 换一次版本要同时改动好几个文件，那才是真实发版的形态。
 */

import { version } from "./version.js";
import { greeting } from "./greeting.js";

export const inject = ["labObserver"];

export function apply(ctx) {
  const say = ctx.labObserver.for(ctx);

  // 三个字段来自三个不同的文件——万一某次只换了一半，这里立刻看得出来
  say("我跑起来了", { 版本: version, 招呼语: greeting, 入口: "第一版" });
}
