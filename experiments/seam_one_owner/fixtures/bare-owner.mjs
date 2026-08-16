/**
 * 占名字的第一种写法：**把一个普通对象挂到某个名字上**。
 *
 * 一行就够：
 *
 *     ctx.provide("名字", 那个对象);
 *
 * 之后别的插件写 `inject: ["名字"]`，就能拿到这个对象。这是最短的写法，
 * 也是没读过框架源码的人最可能自己写出来的那个。
 *
 * 名字和身份都从 config 来，所以同一个文件可以在一次实验里挂两次
 * —— 占同一个名字（撞车），或各占各的（对照）。
 */

import { writeFileSync } from "node:fs";

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  say(`我是 ${config.我是谁}，来占名字「${config.名字}」`, { 写法: "裸对象" });

  ctx.provide(config.名字, { 谁占的: config.我是谁 });

  // 走到这儿就说明占成功了。占失败的话上一行会抛，这行不会执行 ——
  // 所以见证文件出现与否，就是「占没占上」的判据。
  say(`占上了「${config.名字}」`);
  writeFileSync(
    config.见证,
    JSON.stringify({ 我是谁: config.我是谁, 写法: "裸对象", 占上了: config.名字 }, null, 2),
    "utf8",
  );
}
