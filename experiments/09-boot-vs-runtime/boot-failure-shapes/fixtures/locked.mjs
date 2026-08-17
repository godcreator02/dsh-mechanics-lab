/**
 * 硬依赖一个叫「开锁服务」的东西，而那个东西没有任何人提供。
 *
 * `apply` 里做两件事：写一个见证文件（apply 真跑过的证据——实例可能起不来，
 * 事件流未必来得及落盘，这个判定不能挂在一条可能丢的通道上），再向观察器
 * 说一句话。
 */

import { writeFileSync } from "node:fs";

export const inject = ["labObserver", "开锁服务"];

export function apply(ctx, config) {
  writeFileSync(config.见证, JSON.stringify({ 跑了: true }), "utf8");

  ctx.labObserver.for(ctx)("我跑起来了");
}
