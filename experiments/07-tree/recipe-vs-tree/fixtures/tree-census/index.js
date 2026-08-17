/**
 * 普查员：给运行时的条目树拍快照。
 *
 * `--dump-config` 只能告诉你「配方算出来是什么」，看不见框架在 boot 期之后
 * 自己往树里补的条目——那些条目不在任何 patch 文件里，静态 dump 看不到，
 * 只能从进程内部往外看。
 *
 * 拍两张快照：
 *   boot   —— apply 被调用的当下，框架的补丁还没打。
 *   settle —— 延后 delayMs 之后，boot() 早已返回，补的条目都到位了。
 *
 * 延后用 Node 原生 setTimeout，不用 `ctx.setTimeout`——后者是 timer 服务提供的，
 * 而 timer 在不在正是这一层要观测的东西之一，拿被测对象当测量工具会循环论证。
 */

import { writeFileSync } from "node:fs";

const MARKER = "recipe-vs-tree-census-v1";

const WATCHED_SERVICES = ["loader", "timer", "hmr", "logger", "webServer"];

/**
 * 找一个条目的父条目。`entry.parent` 是它所属的 EntryGroup，那个组的
 * `ctx.fiber.entry` 就是拥有这棵子树的条目；根组没有拥有者，返回 null。
 * 取法照抄 loader 源码 `getOuterStack` 的走法。
 */
function parentIdOf(entry) {
  try {
    return entry.parent?.ctx?.fiber?.entry?.options?.id ?? null;
  } catch {
    return null; // 观测点绝不抛错
  }
}

function censusEntry(entry) {
  const fiber = entry.fiber;
  return {
    id: entry.options?.id ?? null,
    name: entry.options?.name ?? null,
    parent: parentIdOf(entry),
    disabled: entry.options?.disabled === true,
    hasFiber: fiber !== undefined,
    fiberState: fiber === undefined ? null : fiber.state,
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
    // loader 拿不到就如实记 null，绝不 throw——观测点抛错会把「根本没跑到这」
    // 和「跑到了但没拿到」混成同一个结果。
    entries: loader === undefined ? null : [...loader.entries()].map(censusEntry),
  };
}

/**
 * 历次 apply 的记录，模块级变量。普查员会被重挂（改配置、代码热重载都会），
 * 挂在 apply() 局部会把「被重挂」这件事自己藏起来——文件被整个覆盖，前一轮
 * 的 settle 快照凭空消失。挪到模块级，重挂会往数组里多加一条记录，从缺陷
 * 变成一个可观测量：从这个字段能看出这个条目被挂了几次。
 */
const records = [];

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("tree-census: config.out 是必需的");
  const delayMs = config?.delayMs ?? 1500;

  const record = {
    marker: MARKER,
    applyIndex: records.length,
    delayMs,
    snapshots: [takeSnapshot(ctx, "boot")],
  };
  records.push(record);

  const flush = () => writeFileSync(out, JSON.stringify(records, null, 2), "utf8");
  flush();

  const handle = setTimeout(() => {
    record.snapshots.push(takeSnapshot(ctx, "settle"));
    flush();
  }, delayMs);
  // 不 unref：定时器要撑住事件循环直到自己 flush 完、清掉自己，之后进程
  // 活不活着就是别人的事了。
  ctx.on("dispose", () => clearTimeout(handle));
}
