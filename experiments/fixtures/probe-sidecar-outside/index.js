// probe-sidecar-outside —— E5 用例3（可选/边界）的靶子插件。
//
// 这个插件的源码目录故意不放进 hmr 的 root 配置里。假说：hmr 的 chokidar
// watcher 压根不会看这个目录，所以就算它的代码被 import 过（进了 loadCache），
// 改动也不会触发任何重载——因为 chokidar 从一开始就没订阅这棵目录树。
const moduleLoadedAt = new Date().toISOString();
const MARKER = "v1";

export const name = "probe-sidecar-outside";
export const inject = ["webServer"];

export function apply(ctx) {
  const appliedAt = new Date().toISOString();
  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: "/probe-sidecar-outside",
        handler: (req, res) => {
          const text = JSON.stringify({ marker: MARKER, appliedAt, moduleLoadedAt });
          res.writeHead(200, {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "content-length": Buffer.byteLength(text),
          });
          res.end(text);
        },
      }),
    "probe-sidecar-outside: probe route",
  );
}
