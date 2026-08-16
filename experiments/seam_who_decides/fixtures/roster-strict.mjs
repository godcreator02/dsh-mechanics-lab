/**
 * 名册 · 严格版 —— 跟宽松版**只差一个方法**：
 *
 *     [Service.check]() { return this.表.size > 0 }
 *
 * 这是框架留的一个钩子：「我这个服务现在算不算可用？」框架在决定
 * 「等着它的插件能不能开跑」之前会问一次，答否就当它不在。
 *
 * 名字照样占着、对象照样在，只是等着它的那些插件拿不到。
 */

import { Service } from "@deepseek-ai/cordis";

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  const 预置 = config.预置 ?? [];

  class 名册 extends Service {
    constructor(ctx) {
      super(ctx, "labRoster");
      this.表 = new Map(预置.map((id) => [id, { 来自: "预置" }]));
    }

    /** 表空就当自己不可用 —— 跟宽松版的唯一差别。 */
    [Service.check]() {
      return this.表.size > 0;
    }

    list() {
      return [...this.表.keys()].sort();
    }
  }

  new 名册(ctx);
  say("严格名册开张", { 表里: 预置 });
}
