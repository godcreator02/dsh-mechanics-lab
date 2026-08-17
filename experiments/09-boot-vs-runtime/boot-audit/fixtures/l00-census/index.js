/**
 * 普查员：给运行时的树拍快照，服务 / 条目 / fiber 状态一次性序列化出来。
 *
 * 拍两张：apply 当下（"boot"）+ 延后 delayMs（"settle"）。本项只用它验证
 * boot 审计发生之前那一刻的服务表——不需要看第二张，但延后逻辑原样保留，
 * 便于以后需要时复用。
 */

import { writeFileSync } from "node:fs";

const MARKER = "l00-census-v1";
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

// 模块级：普查员被重挂时新一轮追加而不是清零，见 duplicate-id-timing 模块
// docstring 引用的那条「工具把自己被重挂这件事藏住了」的教训。
const records = [];

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("l00-census: config.out 是必需的");
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
