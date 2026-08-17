/**
 * module-state-reset 专用教学插件。
 *
 * 模块顶层放一个计数器 `let loads = 0`，每次 `apply` 时加一并报出来。
 * 热重载会把整个模块重新求值，这一行也跟着重跑——「重载之后计数器是不是
 * 回到 1」就是本项要验的判定本身。
 *
 * 报的「版本」是代码里的字面量，用来确认重载确实发生过（新代码生效了）：
 * 版本变了不代表状态被保住，这正是本项要拆穿的地方。
 */

const 版本 = "第一版";
let loads = 0;

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  loads += 1;
  say("apply 了", { 版本, 载入次数: loads });
}
