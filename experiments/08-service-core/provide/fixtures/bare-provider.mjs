/**
 * 提供一个服务 · 写法甲：**把一个普通对象挂到某个名字上**。
 *
 *     ctx.provide("labBare", 那个对象);
 *
 * 对象里放什么完全由你定。这里放了一个方法 `你看得见谁()`，让它报出
 * 「被调用的这一刻，我手上的 ctx 属于谁」——两种写法在这个问题上会分道扬镳。
 *
 * 为了跟写法乙公平对比，这个对象**自己存了一份 ctx**。所以两边都有 ctx，
 * 差别只剩一条：那份 ctx 会不会随调用方变。
 */

import { writeFileSync } from "node:fs";

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  const 服务 = {
    写法: "裸对象",

    /** 报出此刻手上这份 ctx 属于哪个条目。 */
    你看得见谁() {
      return this.ctx?.fiber?.entry?.options?.id ?? null;
    },

    ctx, // 自己存一份，跟写法乙对齐
  };

  ctx.provide("labBare", 服务);
  say("labBare 提供好了", { 写法: "裸对象" });
  writeFileSync(config.见证, JSON.stringify({ 写法: "裸对象", 提供了: "labBare" }, null, 2), "utf8");
}
