/**
 * L0 的普查员：给**运行时的那棵树**拍快照。
 *
 * 为什么需要它 —— `--dump-config` 只能告诉你「配方算出来是什么」，
 * 而 L0 要回答的恰恰是「运行时的树跟配方一不一样」。这两者不是一回事：
 * 框架会在 boot 结束**之后**往树里补条目，那些条目不在任何 patch 文件里，
 * 静态 dump 永远看不见。要看见它们，只能从进程内部往外看。
 *
 * 拍两张快照，这是本插件全部的设计：
 *
 *   boot   —— apply 被调用的当下。这时 boot() 还没返回，框架的补丁还没打。
 *   settle —— 延后 delayMs 之后。这时 boot() 早已返回，补的条目都到位了。
 *
 * 两张一比，凭空多出来的就是**幽灵条目**（配方里没有、树里却有的条目）。
 *
 * 延后用 Node 原生 setTimeout，不用 `ctx.setTimeout` —— 后者是 timer 服务提供的，
 * 而 timer 在不在正是本课要测的东西，拿被测对象当测量工具就循环论证了。
 */

import { writeFileSync } from "node:fs";

/** 代码版本指纹。 */
const MARKER = "l00-census-v1";

/** 关心的服务名。DSH 的服务表很长，只探跟「最小环境」有关的这几个。 */
const WATCHED_SERVICES = ["loader", "timer", "hmr", "logger", "webServer"];

/**
 * 把一个条目压成可序列化的普查记录。
 *
 * fiber 是插件生命周期的载体：`entry.fiber === undefined` 意味着这个条目
 * 还没有（或不再有）活的实例 —— 跟「fiber 存在但状态不是 ACTIVE」是两回事，
 * 所以两者分开记，绝不合成一个字段。
 */
function censusEntry(entry) {
  const fiber = entry.fiber;
  return {
    id: entry.options?.id ?? null,
    name: entry.options?.name ?? null,
    disabled: entry.options?.disabled === true,
    hasFiber: fiber !== undefined,
    fiberState: fiber === undefined ? null : fiber.state,
    // inject 是「这个条目在等哪些服务」。PENDING 卡住时这里就是原因。
    inject: fiber === undefined ? null : Object.keys(fiber.inject ?? {}),
  };
}

function takeSnapshot(ctx, phase) {
  const loader = ctx.get("loader");
  const services = {};
  for (const name of WATCHED_SERVICES) {
    services[name] = ctx.get(name) !== undefined;
  }
  return {
    phase,
    at: new Date().toISOString(),
    services,
    // loader 拿不到就如实记 null，绝不 throw —— 观测点抛错会把
    // 「根本没跑到这」和「跑到了但没拿到」混成同一个结果（L3 吃过这个亏）。
    entries: loader === undefined ? null : [...loader.entries()].map(censusEntry),
  };
}

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("l00-census: config.out 是必需的");
  const delayMs = config?.delayMs ?? 1500;

  const record = {
    marker: MARKER,
    delayMs,
    snapshots: [takeSnapshot(ctx, "boot")],
  };
  const flush = () => writeFileSync(out, JSON.stringify(record, null, 2), "utf8");
  flush();

  const handle = setTimeout(() => {
    record.snapshots.push(takeSnapshot(ctx, "settle"));
    flush();
  }, delayMs);
  // 不 unref：这个定时器要能撑住事件循环。本课有一问就是「谁保持进程活着」，
  // 而普查员自己必须**不**成为那个答案 —— 所以它在 flush 完就把定时器清掉，
  // 之后进程还活不活着，就完全是别人的事了。
  ctx.on("dispose", () => clearTimeout(handle));
}
