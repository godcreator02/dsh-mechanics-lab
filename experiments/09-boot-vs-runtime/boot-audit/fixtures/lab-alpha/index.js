/**
 * 依赖 `labRegistry`（硬依赖，写在代码里），登记自己后再提供 `labAlpha`。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-alpha-v1";

export const inject = ["labRegistry"];

export function apply(ctx, config) {
  const book = ctx.get("labRegistry");

  // 拿不到服务时不抛错，如实记录——观测点抛错会把「inject 没满足，根本没
  // apply」和「apply 了但服务是 undefined」混成同一个结果。
  const ledgerBefore = book ? book.list() : null;

  if (book) {
    book.sign("lab-alpha", config?.note ?? null);
    ctx.provide("labAlpha", { marker: MARKER, greet: () => "alpha 在这儿" });
  }

  if (config?.witness) {
    writeFileSync(
      config.witness,
      JSON.stringify(
        {
          marker: MARKER,
          appliedAt: new Date().toISOString(),
          gotRegistry: book !== undefined && book !== null,
          ledgerBefore,
          config,
        },
        null,
        2,
      ),
      "utf8",
    );
  }
}
