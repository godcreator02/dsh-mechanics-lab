/**
 * 靠观察器上报证明自己跑没跑的教学插件——`disabled` 相关用例要看的不只是
 * 「apply 执行没执行」，还有「fiber 建没建、状态走没走」，这些只有挂了
 * lab-recorder 才能看到，见证文件做不到。
 */

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  say("我跑起来了", { 收到的config: config ?? null });
}
