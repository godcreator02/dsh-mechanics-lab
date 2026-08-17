/**
 * 普查员：读整棵树，外加对 `cordis:include` 条目做一件专门的事——摘出它自己
 * 的 `config.patches`。那正是「配方」这个概念的真身：四层 patch 合成之后的
 * 完整列表，原样塞进这一个条目的 config 里，不是运行时算出来又扔掉的中间结果。
 *
 * 不整体 `JSON.stringify` 那份 `config.patches`：条目的 `config` 里可能有
 * `!!js` 表达式，dsh 的 patch 方言把它解析成一个不透明的求值单元，直接序列化
 * 容易失真甚至抛错。摘要只取「这条 patch 操作是 insert 还是 override、涉及哪些
 * id/name」，足够用来对账「配方里写的东西是不是真的出现在树上」。
 *
 * 支持一张可选的第三快照 `settle2`（`config.delayMs2`）：不起 web 服务也能
 * 验证「活层文件改了之后，`include` 的 `config.patches` 跟着变了没有」——先拍
 * 一张，调用方这时去改活层文件，再拍一张，两张一比。
 */

import { writeFileSync } from "node:fs";

/** 代码版本指纹。 */
const MARKER = "replay-recipe-census-v1";

const WATCHED_SERVICES = ["loader", "timer", "hmr", "logger", "webServer"];

/** 找一个条目的父条目——cordis 没有直接暴露这个关系，得从 fiber 链上摸。 */
function parentIdOf(entry) {
  try {
    return entry.parent?.ctx?.fiber?.entry?.options?.id ?? null;
  } catch {
    return null; // 观测点绝不抛错
  }
}

/**
 * 把 `config.patches` 里的一条 patch 操作压成可读摘要。
 *
 * 一条 patch 操作只有两种形状（`cordis-plugin-include` 的 PatchOptions）：
 *   - `{ insert: [...] }` —— 插入若干新条目
 *   - `{ id, config?, disabled?, ... }` —— 覆盖已有条目
 */
function summarizePatch(patch) {
  try {
    if (patch && Array.isArray(patch.insert)) {
      return { op: "insert", ids: patch.insert.map((e) => e?.id ?? e?.name ?? null) };
    }
    if (patch && typeof patch === "object" && "id" in patch) {
      return { op: "override", id: patch.id };
    }
    return { op: "unknown", keys: patch && typeof patch === "object" ? Object.keys(patch) : null };
  } catch {
    return { op: "error" }; // 观测点绝不抛错
  }
}

function censusEntry(entry) {
  const fiber = entry.fiber;
  const base = {
    id: entry.options?.id ?? null,
    name: entry.options?.name ?? null,
    parent: parentIdOf(entry),
    disabled: entry.options?.disabled === true,
    hasFiber: fiber !== undefined,
    fiberState: fiber === undefined ? null : fiber.state,
    inject: fiber === undefined ? null : Object.keys(fiber.inject ?? {}),
  };
  // 只有 include 条目才有意义摘 patches —— 那正是「配方」的真身所在。
  if (entry.options?.name === "cordis:include") {
    let patches;
    try {
      patches = entry.options?.config?.patches;
    } catch {
      patches = undefined; // 观测点绝不抛错
    }
    base.includePatches = {
      present: patches !== undefined,
      count: Array.isArray(patches) ? patches.length : null,
      summary: Array.isArray(patches) ? patches.map(summarizePatch) : null,
    };
  }
  return base;
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

/** 历次 apply 的记录，模块级，写文件时写整个数组——重挂本身也该在记录里留痕。 */
const records = [];

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("replay-recipe-census: config.out 是必需的");
  const delayMs = config?.delayMs ?? 1500;
  const delayMs2 = config?.delayMs2; // 可选：第三张快照

  const record = {
    marker: MARKER,
    applyIndex: records.length,
    delayMs,
    delayMs2: delayMs2 ?? null,
    snapshots: [takeSnapshot(ctx, "boot")],
  };
  records.push(record);

  const flush = () => writeFileSync(out, JSON.stringify(records, null, 2), "utf8");
  flush();

  const handles = [];
  handles.push(
    setTimeout(() => {
      record.snapshots.push(takeSnapshot(ctx, "settle"));
      flush();
    }, delayMs),
  );
  if (delayMs2 !== undefined) {
    handles.push(
      setTimeout(() => {
        record.snapshots.push(takeSnapshot(ctx, "settle2"));
        flush();
      }, delayMs2),
    );
  }
  // 不 unref：这些定时器要撑住事件循环直到自己 flush 完、清掉自己，
  // 之后进程活不活着就是别人的事了。
  ctx.on("dispose", () => handles.forEach(clearTimeout));
}
