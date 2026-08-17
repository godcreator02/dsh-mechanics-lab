/**
 * preset-probe（module-resolution 版）—— 在 `preset-discovery` 那份的基础上多
 * 一件事：对 config 点名的每个 preset id 调一次 `standingKeyFor()`，把成败与
 * 错误消息回显出来。
 *
 * 为什么用 `standingKeyFor()` 而不是真建一个会话：它的契约明写「ensuring the
 * mount composes plugins but starts no agent, no session, and no turn」——
 * **组合插件但不起 agent**。本项要问的正是「这一行的模块解析得到吗」，
 * 组合到位就够了，建会话是多余的重量。
 *
 * mount 失败会抛，错误消息里带的正是要观察的东西（模块解析失败长什么样、
 * 哪一行没激活）。失败的 standing 会被实现自己从缓存里摘掉，所以同一个 id
 * 可以重试——但成功的会被永久缓存，第二次 GET 拿到的是同一份。
 */

export const inject = ["webServer", "agentPresets"];

const MARKER = "preset-probe-mount-v1";

/** 模块被 import 的时刻，模块级、只赋值一次。 */
const MODULE_LOADED_AT = new Date().toISOString();

/** 一行名册的可序列化快照：整行摊平，外加它自己的 key 列表。 */
function snapshot(row) {
  const keys = Object.keys(row).sort();
  const plain = {};
  for (const key of keys) {
    const value = row[key];
    plain[key] = typeof value === "function" ? "<function>" : value;
  }
  return { keys, ...plain };
}

/**
 * 试着 ensure 一个 preset 的 standing mount。
 *
 * 错误消息整条留下（不截断、不归类）——「解析不到的模块报什么」是本项的观测
 * 对象本身，归类会把它抹掉。
 */
async function tryMount(ctx, id) {
  try {
    const key = await ctx.agentPresets.standingKeyFor(id);
    return { id, ok: true, key: key === undefined ? null : { ...key } };
  } catch (error) {
    return { id, ok: false, error: String(error?.message ?? error) };
  }
}

export function apply(ctx, config) {
  const appliedAt = new Date().toISOString();
  const route = config?.route ?? "/preset-probe/roster";
  const mountIds = Array.isArray(config?.mount) ? config.mount : [];

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
            .then(async () => {
              const rows = await ctx.agentPresets.list();
              const mounts = [];
              for (const id of mountIds) {
                mounts.push(await tryMount(ctx, id));
              }
              send({ ok: true, count: rows.length, rows: rows.map(snapshot), mounts });
            })
            .catch((error) => {
              send({ ok: false, error: String(error?.stack ?? error) });
            });
        },
      }),
    "preset-probe: roster + mount route",
  );
}
