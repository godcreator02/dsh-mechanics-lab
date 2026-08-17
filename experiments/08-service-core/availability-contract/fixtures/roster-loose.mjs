/**
 * 名册 · 宽松版 —— 跟 `registry` 里那个一样，**不管表里有没有东西**。
 *
 * 名字一占上，等着它的插件就能拿到它。表是空的也照给，
 * 「空表能不能用」由使用方自己去操心。
 *
 * 这个文件跟 `roster-strict.mjs` 只差一个方法，摆在一起看得最清楚。
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

    list() {
      return [...this.表.keys()].sort();
    }
  }

  new 名册(ctx);
  say("宽松名册开张", { 表里: 预置 });
}
