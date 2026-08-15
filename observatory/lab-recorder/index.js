/**
 * lab-recorder — 观测台的采集器。
 *
 * 唯一必须住在被观测进程里的东西：订阅 Cordis 的生命周期事件，追加写 jsonl。
 * 看板是独立的 Python 服务，读这个文件。
 *
 * 三条设计约束：
 *
 * 1. **零 inject**。订阅事件只要 apply 的 ctx，写文件只要 node:fs，
 *    不依赖 webServer / loader / 任何服务。没有依赖就没有等待 —— 它会在很早的
 *    批次里挂上，漏掉的早期事件最少。
 *    （反面教材：lab-inspector 因为 inject 了 loader，被 loader 的 await 语义
 *    锁死在 PENDING，见 demo/README.md。）
 *
 * 2. **内存缓冲 + 定时 flush**，不是每个事件同步写盘。被观测的实验里有几百个
 *    状态转换，逐个同步写会明显改变时序；而我们测的是「什么变了什么没变」
 *    这类定性结论，不是精确耗时，所以宁可丢掉最后 250ms 也不污染时序。
 *
 * 3. **只记录，不判断**。事件原样落盘，过滤/聚合/解释全在看板那边做。
 *    采集器越笨越好 —— 它是唯一会影响被观测系统的部分。
 */

import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

/**
 * FiberState 的数字 → 名字。
 *
 * 必须自己写：`FiberState` 在 cordis 里是 TypeScript 的 `const enum`，
 * 编译后被内联成数字字面量，**运行时不存在这个对象**，import 不到。
 */
const FIBER_STATE = ["PENDING", "LOADING", "ACTIVE", "FAILED", "DISPOSED", "UNLOADING"];

const MARKER = "lab-recorder-v1";

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("lab-recorder: config.out（事件日志路径）是必需的");

  const flushMs = config?.flushMs ?? 250;

  mkdirSync(dirname(out), { recursive: true });
  // 每次挂载重开一个文件：一次运行一份日志，避免跨运行串味
  writeFileSync(out, "", "utf8");

  const t0 = process.hrtime.bigint();
  /** @type {object[]} */
  const buffer = [];
  let seq = 0;

  const push = (kind, payload) => {
    buffer.push({
      seq: seq++,
      // 相对本采集器挂载时刻的毫秒数，小数点后三位 —— 看得出几毫秒的窄窗口
      ms: Number(process.hrtime.bigint() - t0) / 1e6,
      at: new Date().toISOString(),
      kind,
      ...payload,
    });
  };

  /**
   * 从 fiber 反查它属于哪个 loader 条目。
   *
   * 不是所有 fiber 都对应条目 —— 插件内部用 ctx.plugin() 起的子 fiber
   * 没有 entry。那些照样记录（scope 标成 inner），由看板决定显不显示。
   */
  const describe = (fiber) => {
    const entry = fiber?.entry;
    if (entry?.options) {
      return { scope: "entry", id: entry.options.id ?? null, name: entry.options.name ?? null };
    }
    return { scope: "inner", id: null, name: fiber?.runtime?.name ?? null };
  };

  // ── 订阅 ────────────────────────────────────────────────────────────────
  // internal/status：fiber 生命周期状态每变一次触发一次，带旧状态。
  // 这是能抓住 LOADING 这种几毫秒窄窗口的唯一办法 —— 轮询必然错过。
  ctx.on("internal/status", (fiber, oldValue) => {
    push("status", {
      ...describe(fiber),
      from: FIBER_STATE[oldValue] ?? String(oldValue),
      to: FIBER_STATE[fiber?.state] ?? String(fiber?.state),
    });
  });

  // internal/plugin：fiber 被创建，或销毁时 uid 被清空
  ctx.on("internal/plugin", (fiber) => {
    push("plugin", { ...describe(fiber), uid: fiber?.uid ?? null });
  });

  const flush = () => {
    if (buffer.length === 0) return;
    const lines = buffer.map((e) => JSON.stringify(e)).join("\n") + "\n";
    buffer.length = 0;
    try {
      appendFileSync(out, lines, "utf8");
    } catch (err) {
      // 采集器绝不能把被观测系统搞崩
      ctx.logger?.warn?.("lab-recorder: 写日志失败 " + String(err));
    }
  };

  const timer = setInterval(flush, flushMs);
  // unref：别让这个定时器把进程钉住、导致实例该退出时退不出去
  timer.unref?.();

  push("recorder", { marker: MARKER, note: "采集开始（本行之前的事件未被记录）" });

  // ── 起点快照 ────────────────────────────────────────────────────────────
  // 采集器自己也是树上的一个条目，在它 apply 之前挂载的条目，其
  // PENDING→LOADING 已经发生完了（实测：lab-minimal 只赶上最后一跳）。
  // 而加载顺序由**服务可用性**驱动、不由书写顺序决定，所以没法把自己排到第一个。
  //
  // 补救：订阅之后立刻拍一张全树快照，记下每个条目此刻的状态。
  // 丢掉的仍然是**过程**，但至少起点是确切的，看板能据此画出完整的基线。
  //
  // 用 ctx.get 运行时取 loader，**不写进 inject** —— loader 的 intercept 有
  // await 语义（"keep dependent plugins pending while loader entries are still
  // loading"），声明依赖它会把本插件锁死在 PENDING（见 demo/README.md）。
  // 顺序上先订阅后快照：宁可重复也不漏，看板知道 snapshot 是补记不是实时。
  try {
    const loader = ctx.get("loader");
    if (loader?.entries) {
      let count = 0;
      for (const entry of loader.entries()) {
        const options = entry?.options ?? {};
        const fiber = entry?.fiber;
        push("snapshot", {
          scope: "entry",
          id: options.id ?? null,
          name: options.name ?? null,
          to: fiber ? FIBER_STATE[fiber.state] ?? String(fiber.state) : null,
          hasFiber: fiber !== undefined,
          disabled: Boolean(entry?.disabled),
        });
        count += 1;
      }
      push("recorder", { marker: MARKER, note: `起点快照完成，共 ${count} 个条目` });
    } else {
      push("recorder", { marker: MARKER, note: "拿不到 loader，跳过起点快照" });
    }
  } catch (err) {
    push("recorder", { marker: MARKER, note: "起点快照失败：" + String(err) });
  }

  // 卸载时停表并把尾巴刷干净
  ctx.effect(() => () => {
    clearInterval(timer);
    push("recorder", { marker: MARKER, note: "采集结束" });
    flush();
  }, "lab-recorder: flush timer");
}
