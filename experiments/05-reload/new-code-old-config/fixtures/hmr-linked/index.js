/**
 * 教学插件——一个包，声明了 `dsh.bundle`，条目由包自己那份 patch 生。
 *
 * 报两个版本号，来路不同：
 *   版本     —— 写死在这个文件里，改它是「改代码」
 *   配置版本 —— 从条目的 config 来，改它是「改配方」
 * 本项用例同一时刻改这两处，看重载之后拿到的是哪一头的新值。
 */

import { compute } from "./helper.js";

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", {
    版本: "第一版",
    配置版本: config?.版本 ?? null,
    算出来: compute(),
  });
}
