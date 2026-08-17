/**
 * preset-probe —— 把 `ctx.agentPresets` 的名册从进程内部吐到一个 HTTP 路由上。
 *
 * 为什么要探针而不是直接调 RPC：官方那套 `agentPreset.list` 走 typert gateway
 * 的 carrier envelope，wire 形状没有公开文档；而 host 平面挂一个插件、注入
 * `agentPresets` 服务、注册一条路由，是这个仓库已经用熟的观测手法
 * （`04-replay/cold-surfaces` 的 `replay-cold-bundle` 同款）。
 *
 * ⚠️ 名册**每次调用都重读磁盘**（`list()`/`resolve()` 都是 unmemoized），
 * 所以这条路由每 GET 一次就是一次新鲜的 discovery——用例可以在实例活着的时候
 * 往 `$DSH_HOME/.agent-presets/` 里放东西，再 GET 一次看它出不出现。
 *
 * 回显的字段刻意**不做筛选**：整行原样 JSON 化，外加一份 key 列表。本项是
 * 🔬 发现型，先如实记录 `AgentPreset` 到底长什么样，再谈断言什么。
 */

export const inject = ["webServer", "agentPresets"];

const MARKER = "preset-probe-v1";

/** 模块被 import 的时刻，模块级、只赋值一次。 */
const MODULE_LOADED_AT = new Date().toISOString();

/**
 * 一行名册的可序列化快照：整行摊平，外加它自己的 key 列表。
 *
 * 不用 `JSON.stringify(row)` 一把梭——行里可能带函数或不可枚举属性，那些会被
 * 静默丢掉，而「丢掉了什么」恰恰是本项要观察的。显式取 key 才看得见全貌。
 */
function snapshot(row) {
  const keys = Object.keys(row).sort();
  const plain = {};
  for (const key of keys) {
    const value = row[key];
    plain[key] = typeof value === "function" ? "<function>" : value;
  }
  return { keys, ...plain };
}

export function apply(ctx, config) {
  const appliedAt = new Date().toISOString();
  const route = config?.route ?? "/preset-probe/roster";

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
          const send = (payload) => {
            res.writeHead(200, {
              "content-type": "application/json; charset=utf-8",
              "cache-control": "no-cache",
            });
            res.end(JSON.stringify({ marker: MARKER, moduleLoadedAt: MODULE_LOADED_AT, appliedAt, ...payload }));
          };

          Promise.resolve()
            .then(() => ctx.agentPresets.list())
            .then((rows) => {
              send({
                ok: true,
                defaultId: ctx.agentPresets.defaultId ?? null,
                count: rows.length,
                rows: rows.map(snapshot),
              });
            })
            .catch((error) => {
              // 失败也回 200 + JSON：用例分辨「探针没挂上」和「名册读失败」
              // 靠的是响应体里的 ok 字段，不是状态码（dsh 对未匹配路径回
              // 200 + SPA 兜底 HTML，状态码本来就不可信）。
              send({ ok: false, error: String(error?.stack ?? error) });
            });
        },
      }),
    "preset-probe: roster route",
  );
}
