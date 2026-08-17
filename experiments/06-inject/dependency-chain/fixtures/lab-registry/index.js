/**
 * 提供 `labRegistry` 服务：一本「谁登记过」的账本，谁登记一笔就立刻整份落盘。
 *
 * 落盘时机就是真实的 apply 先后关系——账本内容本身就是活的调用顺序凭证，
 * 不用另外拼事件流时间戳。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-registry-v1";

export function apply(ctx, config) {
  const ledger = config?.ledger;
  if (!ledger) throw new Error("lab-registry: config.ledger（账本落盘路径）是必需的");

  const entries = [];
  const t0 = process.hrtime.bigint();

  const dump = () =>
    writeFileSync(
      ledger,
      JSON.stringify({ marker: MARKER, providedAt: new Date().toISOString(), entries }, null, 2),
      "utf8",
    );

  const book = {
    sign(who, note) {
      entries.push({
        who,
        note: note ?? null,
        ms: Number(process.hrtime.bigint() - t0) / 1e6,
        at: new Date().toISOString(),
      });
      dump();
    },
    list() {
      return entries.slice();
    },
  };

  ctx.provide("labRegistry", book);
  dump(); // 先落一次空账本，证明提供者自己先到位
}
