/**
 * 依赖链的末端：二级依赖。要两个服务——`labRegistry`（根提供）和
 * `labAlpha`（中段提供）。拿到几个算几个都不算数，`inject` 是全有全无。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-beta-v1";

export const inject = ["labRegistry", "labAlpha"];

export function apply(ctx, config) {
  const book = ctx.get("labRegistry");
  const alpha = ctx.get("labAlpha");
  const ledgerBefore = book ? book.list() : null;

  if (book) book.sign("lab-beta", alpha ? alpha.greet() : "（没拿到 labAlpha）");

  if (config?.witness) {
    writeFileSync(
      config.witness,
      JSON.stringify(
        {
          marker: MARKER,
          appliedAt: new Date().toISOString(),
          gotRegistry: book !== undefined && book !== null,
          gotAlpha: alpha !== undefined && alpha !== null,
          ledgerBefore,
        },
        null,
        2,
      ),
      "utf8",
    );
  }
}
