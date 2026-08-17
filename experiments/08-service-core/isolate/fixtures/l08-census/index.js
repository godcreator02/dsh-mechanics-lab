/**
 * 普查员：遍历 `loader.entries()`，给每个条目记 id / name / parent / disabled
 * 原文 / group / hasFiber / fiberState，拍两张快照（apply 当下 + 延后 delayMs）。
 *
 * `entry.parent` 是这个条目所属的 EntryGroup，那个组的 `ctx.fiber.entry` 就是
 * 拥有这棵子树的条目——根组没有拥有者，返回 null。取法照抄 loader 源码
 * `getOuterStack` 的走法。
 *
 * 本项只用它确认 `isolate` 用例的树形状（group-a / group-b 各自的孩子），
 * 不依赖它做任何断言——判定全靠 lab-flavor-taster 的见证文件。
 */

import { writeFileSync } from "node:fs";

const MARKER = "l08-census-v1";
const WATCHED_SERVICES = ["loader", "timer", "hmr", "logger", "webServer", "labFlavor"];

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
    group: entry.options?.group === true,
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
  if (!out) throw new Error("l08-census: config.out 是必需的");
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
