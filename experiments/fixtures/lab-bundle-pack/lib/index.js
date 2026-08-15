// lab-bundle-pack 的最小 host 插件 —— E4 冷热对照实验专用。
//
// 每次被挂载（apply 被调一次）就固定一个 appliedAt 时间戳，随路由响应带出去。
// bundle 层的 patch 文件只在 boot 时被读一次、没有 watcher 盯着，所以理论上：
// 只要挂载它的那个实例进程不重启，这个时间戳应该纹丝不动——这就是 E4 用来
// 判「冷」的探针。
//
// config 契约（供 cordis.patch.yml 的 config: 传入）：
//   variant     —— 任意字符串，原样回显，用来分辨挂的是哪一版 patch
//   probePath   —— 这个条目要注册的路由路径，默认 /bundled-probe
//                  （同一个包可以用不同 id + 不同 probePath 被挂载多次）

export const inject = ["webServer"];

const MARKER = "lab-bundle-pack@e4-fixture";

export function apply(ctx, rawConfig) {
  const config = rawConfig ?? {};
  const variant = config.variant ?? "v1";
  const probePath = config.probePath ?? "/bundled-probe";
  const appliedAt = new Date().toISOString();

  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: probePath,
        handler: (req, res) => {
          const text = JSON.stringify({
            marker: MARKER,
            variant,
            probePath,
            appliedAt,
          });
          res.writeHead(200, {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "content-length": Buffer.byteLength(text),
          });
          res.end(text);
        },
      }),
    `lab-bundle-pack: ${probePath} 路由`,
  );
}
