/**
 * 拍一张运行时快照的教学插件：给「裸包名 / 相对路径的 name 到底解析到了
 * 没有」这个问题提供一个比见证文件更直接的信号——settle 快照里能看到
 * timer / hmr 是不是真的到了 ACTIVE。
 *
 * 延后用 Node 原生 setTimeout，不用 `ctx.setTimeout`——后者是 timer 服务
 * 提供的，而 timer 在不在正是要测的东西，拿被测对象当测量工具会循环论证。
 */

import { writeFileSync } from "node:fs";

const MARKER = "census-v1";

function censusEntry(entry) {
  const fiber = entry.fiber;
  return {
    id: entry.options?.id ?? null,
    name: entry.options?.name ?? null,
    fiberState: fiber === undefined ? null : fiber.state,
  };
}

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("census: config.out 是必需的");
  const delayMs = config?.delayMs ?? 1500;

  const flush = (entries) =>
    writeFileSync(out, JSON.stringify({ marker: MARKER, at: new Date().toISOString(), entries }, null, 2), "utf8");

  const handle = setTimeout(() => {
    const loader = ctx.get("loader");
    flush(loader === undefined ? null : [...loader.entries()].map(censusEntry));
  }, delayMs);
  ctx.on("dispose", () => clearTimeout(handle));
}
