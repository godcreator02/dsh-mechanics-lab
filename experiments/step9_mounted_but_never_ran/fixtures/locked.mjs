/**
 * 第 9 步的教学插件 —— 它要用一个叫「开锁服务」的东西，而那个东西没有任何人提供。
 *
 * 跟前几步那些插件的唯一差别，就是 `inject` 那一行里多出来的一项。
 *
 * `apply` 里做两件事：
 *   1. 往磁盘写一个见证文件 —— 这个文件出现，就证明 apply 真的跑过
 *   2. 照旧向观察器说一句话
 *
 * 为什么要额外写见证文件：这一步里实例会起不来，事件流未必来得及落盘，
 * 而「apply 到底跑没跑」这个判定不能挂在一条可能丢的通道上。
 */

import { writeFileSync } from "node:fs";

export const inject = ["labObserver", "开锁服务"];

export function apply(ctx, config) {
  writeFileSync(config.见证, JSON.stringify({ 跑了: true }), "utf8");

  ctx.labObserver.for(ctx)("我跑起来了");
}
