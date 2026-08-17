/**
 * 旁观者 —— 不被重载，只负责每秒查一次那个服务、报它拿到了什么。
 *
 * 这一条回答的是「调用方看到的是什么」：重载前后它拿到的标记变没变、
 * 中间有没有一段拿不到（`undefined`）的窗口。
 *
 * 关键写法：**运行时 `ctx.get()` 取，不写进 `inject`**。
 * 写进 inject 的话，被观测的那个服务一撤销，这个旁观者自己也会被牵连
 * （它会退回等待状态、停止工作），那就什么都看不到了 —— 仪器不能跟着被测对象一起倒。
 */

const 标记 = "watcher-" + Math.random().toString(36).slice(2, 6);

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);
  const 每隔毫秒 = config?.每隔毫秒 ?? 1000;

  say("旁观者上任", { 标记 });

  let 第几次 = 0;
  const 定时器 = setInterval(() => {
    第几次 += 1;
    const 拿到的 = ctx.get("busyJob");
    say("查了一次", {
      第几次,
      // 服务在不在，以及在的话是哪一份 —— 这两个分开记，
      // 因为「拿不到」和「拿到了旧的」是两种完全不同的情况
      服务在吗: 拿到的 !== undefined && 拿到的 !== null,
      拿到谁: 拿到的?.标记 ?? null,
    });
  }, 每隔毫秒);

  // 旁观者自己要清理干净 —— 它是仪器，不该在实验里留下自己的尾巴
  ctx.effect(() => () => clearInterval(定时器), "watcher: 轮询定时器");
}
