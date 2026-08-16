/**
 * 用名册的那一方 —— **三个用例共用这同一个文件，一个字都不改**。
 *
 * 这是本项的关键：使用方这侧完全不知道对面是宽松版还是严格版，
 * 写法一模一样。命运不同，原因全在对面。
 */

import { writeFileSync } from "node:fs";

export const inject = ["labObserver", "labRoster"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  const 表里 = ctx.labRoster.list();

  say("我跑起来了，拿到名册了", { 表里 });
  writeFileSync(config.见证, JSON.stringify({ 我是: "使用方", 拿到名册了: true, 表里 }, null, 2), "utf8");
}
