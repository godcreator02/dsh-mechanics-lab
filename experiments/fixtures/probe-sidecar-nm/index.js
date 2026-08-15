// probe-sidecar-nm —— E5 用例4 的靶子插件。
//
// 这个插件的 hmr root 故意指向 profile 的 node_modules 里那个指向本目录的
// junction（而不是这个源码真实目录本身）。假说：这样设置无效——改这份真实
// 源码不会触发重载。用户的 dshw 就踩过这个坑：watch root 必须是插件源码的
// 真实目录，指向 node_modules 里的链接不算数。
const moduleLoadedAt = new Date().toISOString();
const MARKER = "v1";

export const name = "probe-sidecar-nm";
export const inject = ["webServer"];

export function apply(ctx) {
  const appliedAt = new Date().toISOString();
  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: "/probe-sidecar-nm",
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
    "probe-sidecar-nm: probe route",
  );
}
