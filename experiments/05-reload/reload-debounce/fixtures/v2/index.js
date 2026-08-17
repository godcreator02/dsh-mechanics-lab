/**
 * 教学插件「greeter」第二版——包的入口文件。
 *
 * 跟第一版比，三个文件（入口 / version.js / greeting.js）连同 package.json
 * 里的版本号一起变了。一次 checkout 要落下的就是这一批改动。
 */

import { version } from "./version.js";
import { greeting } from "./greeting.js";

export const inject = ["labObserver"];

export function apply(ctx) {
  const say = ctx.labObserver.for(ctx);

  // 三个字段来自三个不同的文件——万一某次只换了一半，这里立刻看得出来
  say("我跑起来了", { 版本: version, 招呼语: greeting, 入口: "第二版" });
}
