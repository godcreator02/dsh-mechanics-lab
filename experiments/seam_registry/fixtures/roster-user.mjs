/**
 * 用名册的那一方 —— **使用方**。
 *
 * 它只 `inject` 名册这一个名字，**不认识任何一个注册方**。这是有意的：
 * 从这一侧看，「表里有几行」跟「我能不能跑起来」是两件不相干的事。
 *
 * 它每隔一小会儿把表内容报一次，所以事件流里留下的是一串表快照——
 * 有东西被塞进来、或者有东西下线，都能从快照的变化上直接读出来。
 */

import { writeFileSync } from "node:fs";

export const inject = ["labObserver", "labRoster"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  const 报一次 = () => say("表里现在有", ctx.labRoster.list());

  // 第一次立刻报：它记录的是「我 apply 的这一刻表里有什么」
  报一次();
  writeFileSync(
    config.见证,
    JSON.stringify({ 我是: "使用方", apply时表里: ctx.labRoster.list() }, null, 2),
    "utf8",
  );

  const 表 = setInterval(报一次, 300);
  表.unref?.(); // 别把进程钉住
  ctx.effect(() => () => clearInterval(表), "使用方的轮询");
}
