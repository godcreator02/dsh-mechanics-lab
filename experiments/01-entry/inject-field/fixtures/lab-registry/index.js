/**
 * 依赖链的根：提供 `labRegistry` 服务，一本「谁来登记过」的账本。
 * 它自己不依赖任何人，是本项唯一需要的服务提供者。
 *
 * 账本每登记一笔就整份落盘，所以见证文件里的顺序就是实际的 apply 顺序。
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

  // ctx.provide 返回一个 disposer；fiber 卸载时服务自动撤销，
  // 所以这里不用自己 ctx.effect 包——provide 本身就是个 effect。
  ctx.provide("labRegistry", book);

  // 先落一次空账本：证明「服务提供者自己先到位」这件事
  dump();
}
