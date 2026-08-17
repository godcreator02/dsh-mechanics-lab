/**
 * 普查员：给运行时的条目树拍快照，带足够的字段回答「谁在谁的子树里」。
 *
 * `loader.entries()` 是扁平遍历（自己 + 所有嵌套子树），光看那个列表分不出
 * 层级。取父条目照抄 loader 源码 `getOuterStack` 的走法：`entry.parent` 是
 * 它所属的 EntryGroup，那个组的 `ctx.fiber.entry` 就是拥有这棵子树的条目；
 * 根组没有拥有者，返回 null。层级（深度）不是这里算出来的——普查员只记录
 * 每个条目自己的 `parent`，深度由测试代码沿着 `parent` 链自己走出来。
 */

import { writeFileSync } from "node:fs";

const MARKER = "hierarchy-census-v1";

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
    // 条目自己声明的 disabled 原文（不是沿父链算出来的「有效」值）。
    // group 的 disabled 例外要求把「原文」和「有效」分开记，合成一个字段就验不出来。
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

/** 历次 apply 的记录，模块级——普查员被重挂时不能把自己的记录跟着清空。 */
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
