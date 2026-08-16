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
/**
 * 找一个条目的**父条目**。
 *
 * 条目树是分层的，但 `loader.entries()` 是扁平遍历（自己 + 所有嵌套子树），
 * 光看那个列表分不出谁在谁下面。层级恰恰是要紧的：配方热重放重新 compose 的
 * 是 **root include 的子树**，不在子树里的条目（比如兜底的 timer/hmr）不受影响。
 *
 * 取法照抄 loader 源码里 `getOuterStack` 的走法：`entry.parent` 是它所属的
 * EntryGroup，那个组的 `ctx.fiber.entry` 就是拥有这棵子树的条目；
 * 根组没有拥有者，返回 null。
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

/**
 * 历次 apply 的记录，**模块级**。
 *
 * 为什么必须是模块级 —— 普查员会被重挂。第一版把 record 建在 apply 里，
 * 于是每次重挂都从零开始、并把文件整个覆盖掉，结果是「settle 快照凭空消失」：
 * 定时器被 `dispose` 清掉，新的一轮又只写了 boot 快照。**工具把自己被重挂
 * 这件事藏住了。**
 *
 * 挪到模块级之后，重挂会往数组里多加一条，文件里因此看得见「这个条目被挂了
 * 几次」—— 从缺陷变成了一个有用的观测量。
 *
 * 模块级变量只在**模块被重新 import** 时才清空（代码热重载），条目重挂不清。
 * 这两件事的区别正好是 L11 的主题。
 */
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

  // 写整个数组：读的一方永远看得到全部历史，不用担心被后一次覆盖
  const flush = () => writeFileSync(out, JSON.stringify(records, null, 2), "utf8");
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
