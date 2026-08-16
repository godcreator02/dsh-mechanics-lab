/**
 * L7 的普查员：从 `fixtures/l00-census` 拷来改造（跨课重复是特性，见 CLAUDE.md）。
 *
 * L0 的普查员只回答「树里有没有配方外的幽灵条目」。L7 要多问一件事：
 * **`cordis:include` 条目自己的 `config.patches`，是不是那份「配方」的真身？**
 * 所以在 L0 的基础上加了一件事——每张快照里，如果这一条恰好是 `cordis:include`，
 * 额外把它的 `config.patches` 摘出来（不是整体 `JSON.stringify`：`!!js` 表达式解析后
 * 可能是不可序列化的求值单元，摘要只取 op 类型 + 涉及的 id/name，足够拿来对账）。
 *
 * 另加了一张可选的第三快照 `settle2`（`config.delayMs2`）——用来验证「活层文件
 * 改了之后，`include` 的 `config.patches` 是不是真的跟着变」，不用起 web 服务，
 * 纯靠时间错位（先拍一张、测试代码这时去改活层文件、再拍一张）。
 */

import { writeFileSync } from "node:fs";

/** 代码版本指纹。 */
const MARKER = "l07-census-v1";

/** 关心的服务名，跟 L0 一致。 */
const WATCHED_SERVICES = ["loader", "timer", "hmr", "logger", "webServer"];

/** 找一个条目的父条目（做法照抄 l00-census，见那边的详细注释）。 */
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
 *
 * 不整体 `JSON.stringify`：条目的 `config` 里可能有 `!!js` 表达式，dsh 的 patch
 * 方言把它解析成一个不透明的求值单元，直接序列化容易失真甚至抛错。这里只取
 * 「这条操作是什么类型、牵涉哪些 id/name」，足够用来对账「配方里写的东西是不是
 * 真的出现在这里」。
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

/**
 * 历次 apply 的记录，**模块级**，写文件时写整个数组。
 * 理由跟 l00-census 一模一样：工具不能靠「被重挂」把自己的问题藏住。
 */
const records = [];

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("l07-census: config.out 是必需的");
  const delayMs = config?.delayMs ?? 1500;
  const delayMs2 = config?.delayMs2; // 可选：第三张快照，测「活层改了之后变没变」

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
  // 不 unref，理由同 l00-census：这些定时器要撑住事件循环，
  // 直到自己 flush 完、清掉自己，之后进程活不活着就是别人的事了。
  ctx.on("dispose", () => handles.forEach(clearTimeout));
}
