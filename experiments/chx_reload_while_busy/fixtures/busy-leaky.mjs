/**
 * 干活的插件 —— **清理写漏**的那一版。
 *
 * 跟 `busy-clean.mjs` 逐行对得上，**只差最后那段 `ctx.effect`**：
 * 这一版起完定时器就不管了，没把取消动作登记给框架。
 *
 * 于是拆这个条目时，框架不知道有个定时器该停 —— 它照样会触发，
 * 而那时新的一份可能已经上任了。事件流里就会出现**两个标记**。
 *
 * 这是真实插件最容易犯的错：清理漏了一样东西，症状不是报错，
 * 是「两份并存，而且看起来一切正常」。
 */

const 标记 = "leaky-" + Math.random().toString(36).slice(2, 6);
const 干活毫秒 = 5000;

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我上任了", { 标记, 版本: "第一版" });

  say("开始干活", { 标记 });
  setTimeout(() => {
    say("干完了", { 标记 });
  }, 干活毫秒);

  ctx.provide("busyJob", { 标记, 版本: "第一版" });

  // ⚠️ 这里**故意不写** ctx.effect —— 定时器没人管，拆条目时不会被取消
}
