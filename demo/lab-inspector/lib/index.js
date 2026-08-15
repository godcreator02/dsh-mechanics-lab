/**
 * lab-inspector — host 半边。
 *
 * 干一件事：把当前组合树里「我们的插件」的状态，经一个只读路由暴露出去。
 *   GET /lab-inspector/state  →  { at, prefix, entries: [{id, name, state, ...}] }
 *
 * 响应里把**两类互不相干的概念严格分开**，绝不混进同一个字段：
 *
 *   fiberState  —— Cordis 官方的 fiber 生命周期状态，原名不翻译
 *                  （`@deepseek-ai/cordis` 的 FiberState，见 lib/types/fiber.d.ts）
 *                  PENDING / LOADING / ACTIVE / FAILED / DISPOSED / UNLOADING
 *                  **没有 fiber 时是 null**，不是某个自造的状态名
 *
 *   disabled / hasFiber —— 条目级事实，本面板自己看的，**不属于 FiberState**
 *
 * 为什么非分不可：「条目被禁用」和「fiber 停在 PENDING」在界面上都表现为
 * 「没在跑」，但前者是人主动关的、后者是依赖没到位，排查方向完全相反。
 * 把自造的 DISABLED 塞进 fiberState 字段，等于伪造了一个官方不存在的状态，
 * 读的人会以为 Cordis 有七个状态。
 *
 * 只读：本插件不提供任何改变状态的接口。教学演示件，看得见摸不着。
 */

/**
 * 需要的 host 服务：只声明 webServer。
 *
 * ⚠️ **故意不把 `loader` 写进 inject**，虽然本插件确实要用它。原因是 loader 的
 * intercept 契约里有一条 `await`：「Keep dependent plugins pending while loader
 * entries are still loading」——声明依赖 loader 的插件，会被挂在 PENDING 上
 * 等所有 loader 条目加载完。
 *
 * 而本插件**自己就是 loader 的一个条目**，于是就等成了死结：它等 loader 加载完，
 * loader 要加载完得先把它加载完。实测症状是 host 半边永远不 apply、路由 404，
 * 而且**日志里一个字都没有**（PENDING 不是错误，没人会为它报警）。
 *
 * 解法是在 apply 里用 `ctx.get("loader")` 运行时取——那时 loader 服务早就在了。
 */
export const inject = ["webServer"];

/** 代码版本指纹，出现在 /state 响应里，方便确认跑的是哪一版。 */
const MARKER = "lab-inspector-v2";

/**
 * FiberState 的数字 → 名字。
 *
 * 必须自己写这张表：`FiberState` 在 cordis 里是 TypeScript 的 `const enum`，
 * 编译后会被内联成数字字面量，**运行时根本不存在这个对象**，import 不到。
 */
const FIBER_STATE_NAMES = ["PENDING", "LOADING", "ACTIVE", "FAILED", "DISPOSED", "UNLOADING"];

export function apply(ctx, config) {
  /** 只列名字以此开头的条目。默认 `lab-`，正好覆盖本实验台的教学插件。 */
  const prefix = config?.prefix ?? "lab-";
  /** 路由路径，避免和别的插件撞车。 */
  const route = config?.route ?? "/lab-inspector/state";

  const snapshot = () => {
    const entries = [];
    // 运行时取 loader，不走 inject（理由见文件头）。请求进来时它必然已就位。
    const loader = ctx.get("loader");
    if (!loader) return { marker: MARKER, at: new Date().toISOString(), prefix, entries, error: "loader 服务不可用" };

    for (const entry of loader.entries()) {
      const options = entry.options ?? {};
      const name = options.name;
      if (typeof name !== "string" || !name.startsWith(prefix)) continue;

      // disabled 是 getter：它会沿父链追溯，祖先被禁用时也返回 true
      const disabled = Boolean(entry.disabled);
      const fiber = entry.fiber;
      const stateCode = fiber ? fiber.state : null;

      entries.push({
        id: options.id ?? name,
        name,

        // ── 第一类：Cordis 官方的 FiberState ────────────────────────────
        // 没有 fiber 时为 null（不是某个状态名）—— 因为「没有 fiber」压根
        // 不是 FiberState 的成员，硬塞一个自造的名字进来就是混淆两套概念。
        fiberState: stateCode === null ? null : FIBER_STATE_NAMES[stateCode] ?? "UNKNOWN_" + stateCode,
        fiberStateCode: stateCode,

        // ── 第二类：条目级事实，本面板自己看的，不属于 FiberState ────────
        hasFiber: fiber !== undefined,
        disabled,
        // 声明式的禁用写法（可能是布尔，也可能是 !!js 表达式对象）
        disabledDeclared: options.disabled ?? null,
        hasConfig: options.config !== undefined && options.config !== null,
      });
    }
    entries.sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
    return { marker: MARKER, at: new Date().toISOString(), prefix, entries };
  };

  // 路由必须用 ctx.effect 包住：不包的话插件卸载后路由会泄漏、继续应答。
  // 这正是 L5 要实测的那条契约，这里先照做。
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
          res.end(JSON.stringify(snapshot()));
        },
      }),
    "lab-inspector: state route",
  );
}
