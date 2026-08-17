/**
 * 提供一个服务 · 写法乙：**继承框架的服务基类**。
 *
 *     class 我的服务 extends Service {
 *       constructor(ctx) { super(ctx, "labKlass"); }
 *     }
 *
 * 方法体跟写法甲的那个对象一模一样，连字面都一样：报出此刻手上这份 ctx
 * 属于哪个条目。差别不在这行代码里，在框架怎么把服务交到调用方手上。
 */

import { Service } from "@deepseek-ai/cordis";
import { writeFileSync } from "node:fs";

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  class 我的服务 extends Service {
    constructor(ctx) {
      super(ctx, "labKlass");
      this.写法 = "服务基类";
    }

    /** 报出此刻手上这份 ctx 属于哪个条目。 */
    你看得见谁() {
      return this.ctx?.fiber?.entry?.options?.id ?? null;
    }
  }

  new 我的服务(ctx);
  say("labKlass 提供好了", { 写法: "服务基类" });
  writeFileSync(config.见证, JSON.stringify({ 写法: "服务基类", 提供了: "labKlass" }, null, 2), "utf8");
}
