/**
 * 用服务的那一方 —— 两个都用，然后把两边的答案摆在一起。
 *
 * `inject` 里写两个名字，框架保证两个都到位了才会跑 `apply`。
 * 从这一侧看，两种写法提供出来的东西**用法完全一样**：都是 `ctx.名字.方法()`。
 *
 * 唯一要问的问题是：调用 `你看得见谁()` 的时候，那两个服务各自报出了谁？
 */

import { writeFileSync } from "node:fs";

export const inject = ["labObserver", "labBare", "labKlass"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  // 我自己的条目 id —— 用来跟服务报出来的那个对照
  const 我是 = ctx.fiber?.entry?.options?.id ?? null;

  const 答案 = {
    我是,
    裸对象: { 写法: ctx.labBare.写法, 它看见谁: ctx.labBare.你看得见谁() },
    服务基类: { 写法: ctx.labKlass.写法, 它看见谁: ctx.labKlass.你看得见谁() },
  };

  say("两边都问过了", 答案);
  writeFileSync(config.见证, JSON.stringify(答案, null, 2), "utf8");
}
