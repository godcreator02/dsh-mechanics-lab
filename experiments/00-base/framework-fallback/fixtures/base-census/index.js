/**
 * 树的普查员：从进程内部给 loader 上的整棵条目树拍快照。
 *
 * 存在的理由：`--dump-config` 只能告诉你「配方算出来是什么」，看不到框架在
 * boot 结束之后才补上的条目（那些条目不在任何 patch 文件里）。要看见它们，
 * 只能从进程内部往外看——本项要看见的正是框架自己补的 timer/hmr。
 *
 * 拍两张快照：
 *   boot   —— apply 被调用的当下，boot() 还没返回，框架的兜底还没触发。
 *   settle —— 延后 delayMs 之后，boot() 早已返回，兜底该触发的都触发了。
 */

import { writeFileSync } from "node:fs";

const MARKER = "base-census-v1";

const WATCHED_SERVICES = ["loader", "timer", "hmr", "logger", "webServer"];

/**
 * 找一个条目的**父条目**。根组没有拥有者，返回 null——框架兜底补的条目
 * 就落在这里：跟 `include` 平级，不在它的子树里。
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
    entries: loader === undefined ? null : [...loader.entries()].map(censusEntry),
  };
}

const records = [];

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("base-census: config.out 是必需的");
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
  ctx.on("dispose", () => clearTimeout(handle));
}
