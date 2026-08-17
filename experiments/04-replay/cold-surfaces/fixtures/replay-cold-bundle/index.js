/**
 * replay-cold-bundle —— 身兼两职：
 *
 *   1. **组合包**（profile bundle）：`package.json` 声明 `dsh.bundle.patch`，
 *      指向同目录的 `cordis.patch.yml`。列进某个 profile 的
 *      `dsh.profile.bundles` 之后，这份 patch 就是它对配方的贡献——跟官方
 *      publish.md 的 hello-plugin 一模一样的写法：一个包，patch 里的条目
 *      按包名引用自己。
 *   2. **它自己 patch 里指向的那个插件模块**：真正的 `apply` 就长在这个文件里。
 *
 * 探针路由把三个指纹吐出来，让测试从进程外部分辨「模块有没有被重新
 * import」和「这次挂着的是哪一版 config」：
 *
 *   marker          代码版本指纹，写死在源码里，除非改代码否则永远不变
 *   moduleLoadedAt  模块被 import 的那一刻（模块级常量）——只有重新 import
 *                   （整进程重启，或代码热重载）才会变
 *   appliedAt       这次 apply 被调用的那一刻——只要 apply 被重跑就会变，
 *                   不需要重新 import 也能变（比如活层热重放只改 config 时）
 *   configRevision  回显 config.revision——当前挂着的是哪一版 config
 */

export const inject = ["webServer"];

const MARKER = "replay-cold-bundle-v1";

/** 模块被 import 的时刻，模块级、只赋值一次。 */
const MODULE_LOADED_AT = new Date().toISOString();

export function apply(ctx, config) {
  const appliedAt = new Date().toISOString();
  const route = config?.route ?? "/replay-cold-bundle/state";
  const revision = config?.revision ?? null;

  // 路由必须用 ctx.effect 包住：不包的话插件卸载后路由会泄漏、继续应答。
  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: route,
        handler: (req, res) => {
          if (req.method !== "GET" && req.method !== "HEAD") {
            res.writeHead(405);
            res.end();
            return;
          }
          res.writeHead(200, {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-cache",
          });
          res.end(
            JSON.stringify({
              marker: MARKER,
              moduleLoadedAt: MODULE_LOADED_AT,
              appliedAt,
              configRevision: revision,
            }),
          );
        },
      }),
    "replay-cold-bundle: state route",
  );
}
