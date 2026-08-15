/**
 * lab-probe-basic —— E3 最小探针插件。
 *
 * 唯一职责：挂一条 `GET /probe-basic` 路由，回显 marker / appliedAt / config。
 * apply() 每次被重新调用（条目被 dispose 后重新挂载，或热重放整段重建 fiber）
 * 都会重新执行到这里，`appliedAt` 就会跳到新的时间戳——这是本实验判断
 * 「活层改动到底有没有真的重新挂载这个条目」的唯一外部可观测信号。
 *
 * 路由必须包在 ctx.effect 里：条目被卸载（disabled: true / 从活层删掉）时，
 * ctx.effect 的清理函数会把路由摘掉。不包的话卸载后路由还会继续应答，
 * 会让实验读到假阳性（明明条目已经死了，探针却还是 200）。
 */
export const inject = ["webServer"];

/** 代码版本标记，写死在源码里，用来确认在跑的确实是这份 fixture。 */
const MARKER = "lab-probe-basic-v1";

export function apply(ctx, config = {}) {
  // apply 执行时刻——条目每被重新挂载一次，这个值就会重新求值一次。
  const appliedAt = new Date().toISOString();

  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: "/probe-basic",
        handler: (req, res) => {
          const text = JSON.stringify({
            marker: MARKER,
            appliedAt,
            config,
          });
          res.writeHead(200, {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "content-length": Buffer.byteLength(text),
          });
          res.end(text);
        },
      }),
    "lab-probe-basic: /probe-basic route",
  );
}
