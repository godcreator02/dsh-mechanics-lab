/**
 * 占名字的第二种写法：**继承框架的服务基类**。
 *
 *     class 座位 extends Service {
 *       constructor(ctx) { super(ctx, "名字"); }
 *     }
 *
 * 注意 `super(ctx, "名字")` —— 占名这个动作就发生在构造函数里，
 * 造出来的那一刻名字就归它了。DSH 自己的那些可替换能力全走这条路。
 *
 * 这个文件跟 `bare-owner.mjs` 做的是同一件事，只是换了写法。
 * 两个文件摆在一起是为了回答一个问题：**独占是不是这种写法特有的？**
 */

import { Service } from "@deepseek-ai/cordis";
import { writeFileSync } from "node:fs";

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  say(`我是 ${config.我是谁}，来占名字「${config.名字}」`, { 写法: "服务基类" });

  class 座位 extends Service {
    constructor(ctx) {
      super(ctx, config.名字);
      this.谁占的 = config.我是谁;
    }
  }

  new 座位(ctx);

  // 同 bare-owner：能走到这儿就是占上了
  say(`占上了「${config.名字}」`);
  writeFileSync(
    config.见证,
    JSON.stringify({ 我是谁: config.我是谁, 写法: "服务基类", 占上了: config.名字 }, null, 2),
    "utf8",
  );
}
