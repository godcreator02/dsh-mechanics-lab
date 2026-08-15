// probe-client-fresh —— E6 推论1 的靶子插件：一个从没在这个进程里挂载过的
// 全新包名，出生就带完整 dsh.client 声明。实例已经在跑的情况下才把它插进
// 活层，看它需不需要重启才能进 client 图。
export const name = "probe-client-fresh";
export const inject = ["webServer"];

export function apply(ctx) {
  const appliedAt = new Date().toISOString();
  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: "/probe-client-fresh",
        handler: (req, res) => {
          const text = JSON.stringify({ appliedAt });
          res.writeHead(200, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
          res.end(text);
        },
      }),
    "probe-client-fresh: probe route",
  );
}
