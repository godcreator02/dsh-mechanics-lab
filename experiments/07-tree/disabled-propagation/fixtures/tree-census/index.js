/**
 * 普查员：给运行时的条目树拍快照，带 disabled 原文与 group 标记。
 *
 * `disabled` 字段记的是条目自己声明的原文，不是沿父链算出来的「有效」值——
 * group 的 disabled 例外正是要看「原文写了 disabled，但自己照样激活」这个
 * 组合，两者合成一个字段就验不出来了。
 */

import { writeFileSync } from "node:fs";

const MARKER = "disabled-propagation-census-v1";

const WATCHED_SERVICES = ["loader", "timer", "hmr", "logger", "webServer"];

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
  ctx.on("dispose", () => clearTimeout(handle));
}
