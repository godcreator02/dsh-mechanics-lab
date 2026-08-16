/**
 * L8 的普查员：从 L0 的 `l00-census` 原样拷来改造（跨课重复是设计允许的）。
 *
 * L0 已经把 `parentIdOf()` 的取法立住并实测过：`entry.parent` 是这个条目所属的
 * EntryGroup，那个组的 `ctx.fiber.entry` 就是拥有这棵子树的条目——根组没有
 * 拥有者，返回 null。L8 直接复用这套取法，不做任何修改。
 *
 * 相对 L0 的唯一实质变化：`WATCHED_SERVICES` 加了 `labFlavor`（L8 的 isolate
 * 用例要看它在不在），marker 换成 l08 自己的版本号，方便从见证文件分辨
 * 是哪一课的普查员写的。
 */

import { writeFileSync } from "node:fs";

/** 代码版本指纹。 */
const MARKER = "l08-census-v1";

/** 关心的服务名。 */
const WATCHED_SERVICES = ["loader", "timer", "hmr", "logger", "webServer", "labFlavor"];

/**
 * 找一个条目的**父条目**。照抄 loader 源码 `getOuterStack` 的走法：
 * `entry.parent` 是它所属的 EntryGroup，那个组的 `ctx.fiber.entry` 就是
 * 拥有这棵子树的条目；根组没有拥有者，返回 null。
 *
 * L8 的核心问题就是靠这个字段回答的——`loader.entries()` 本身是扁平遍历，
 * 不带这个字段就分不出谁在谁的子树里。
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
    // 条目自己声明的 disabled 原文（不是沿父链算出来的「有效」值）。
    // 「原文写了 disabled 但照样激活」正是 group 例外要验的现象，
    // 两者必须分开记，合成一个字段就没法验了。
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

/** 历次 apply 的记录，模块级——理由与 L0 完全一致，见 l00-census 的注释。 */
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
