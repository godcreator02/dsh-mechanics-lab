// probe-client-late-throw —— E6 附加用例的靶子插件：package.json 一开始就
// 带 dsh.client 声明，但 exports 里缺 "./client"——resolveMeta() 里
// clientExportOf() 会 throw，这条路径不会把负判写进 pkgMeta 缓存（跟
// probe-client-late 的「无声明→缓存 null」不是一回事）。假说：补上
// exports["./client"] 之后，不用重启，下一次活层重放就能生效。
export const name = "probe-client-late-throw";
export const inject = ["webServer"];

export function apply(ctx, config) {
  const appliedAt = new Date().toISOString();
  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: "/probe-client-late-throw",
        handler: (req, res) => {
          const text = JSON.stringify({ appliedAt, config: config ?? null });
          res.writeHead(200, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
          res.end(text);
        },
      }),
    "probe-client-late-throw: probe route",
  );
}
