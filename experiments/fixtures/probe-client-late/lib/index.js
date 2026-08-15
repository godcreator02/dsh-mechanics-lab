// probe-client-late —— E6 推论2 的靶子插件：先以「无 client 声明」的形态被
// 挂载（负判进 pkgMeta 缓存），之后 package.json 在磁盘上补上声明，看负判
// 缓存挡不挡得住热重载。
//
// probe 路由回显 apply 期收到的 config——用来独立确认「活层重放确实让这个
// 条目重新 apply 了一次」，把「负判缓存挡住 client 扫描」和「压根没重放」
// 这两件事分开验证。
export const name = "probe-client-late";
export const inject = ["webServer"];

export function apply(ctx, config) {
  const appliedAt = new Date().toISOString();
  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: "/probe-client-late",
        handler: (req, res) => {
          const text = JSON.stringify({ appliedAt, config: config ?? null });
          res.writeHead(200, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
          res.end(text);
        },
      }),
    "probe-client-late: probe route",
  );
}
