/**
 * l06-probe-bundle —— 本课唯一的教学插件，身兼两职：
 *
 *   1. **组合包**（profile bundle）：`package.json` 声明 `dsh.bundle.patch`，
 *      指向同目录的 `cordis.patch.yml`。列进某个 profile 的 `dsh.profile.bundles`
 *      之后，这份 patch 就是它对配方的贡献——跟官方 publish.md 的 hello-plugin
 *      一模一样的写法：一个包，patch 里的条目按包名引用自己。
 *   2. **它自己 patch 里指向的那个插件模块**：真正的 `apply` 就长在这个文件里。
 *
 * 探针职责：注册一条 HTTP 路由，把三个指纹吐出来，让测试从**进程外部**分辨
 * 「模块有没有被重新 import」和「这次挂着的是哪一版 config」——本课要验的
 * 冷热差别，光看响应码分不出来，必须看这三个字段：
 *
 *   marker          代码版本指纹，写死在源码里，除非改代码否则永远不变
 *   moduleLoadedAt  模块被 import 的那一刻（模块级常量）——只有**重新 import**
 *                   （比如整进程重启，或热重载换了 name/被禁用又启用）才会变
 *   appliedAt       **这次** apply 被调用的那一刻——只要 apply 被重跑就会变，
 *                   不需要重新 import 也能变（比如活层热重放只改 config 时）
 *   configRevision  回显 config.revision —— 用来看"当前挂着的是哪一版 config"
 *
 * 与本实验台的其它教学插件一样：观测点绝不抛错，client 侧探测（HTTP GET）
 * 天然满足这一点——请求不到就是连不上，不会把插件自己的异常和"没装上"混淆。
 */

export const inject = ["webServer"];

/** 代码版本指纹。改了这个文件本身才应该变。 */
const MARKER = "l06-probe-bundle-v1";

/**
 * 模块被 import 的时刻，模块级、只赋值一次。
 *
 * 只有整个模块被重新 import 时这个值才会变——冷重启是一种，代码热重载
 * （改了 name / 被禁用再启用）是另一种。纯粹的 config 变化不会碰它，
 * 这正是本课要拿它跟 appliedAt 对照的地方。
 */
const MODULE_LOADED_AT = new Date().toISOString();

export function apply(ctx, config) {
  // apply 被调用的时刻。每次 apply 重跑（哪怕模块没有重新 import）都会变。
  const appliedAt = new Date().toISOString();
  const route = config?.route ?? "/l06-probe/state";
  const revision = config?.revision ?? null;

  // 路由必须用 ctx.effect 包住：不包的话插件卸载后路由会泄漏、继续应答
  // （L13 的契约，这里先照做）。
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
    "l06-probe-bundle: state route",
  );
}
