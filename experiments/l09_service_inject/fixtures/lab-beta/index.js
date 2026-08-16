/**
 * L3 依赖链的末端：**二级依赖**。
 *
 * 它要两个服务：`labRegistry`（根提供）和 `labAlpha`（中段提供）。
 * 所以它必然是三个里最后 apply 的 —— 不是因为写在最后，而是因为
 * 它等的东西最多。这正是「加载由服务可用性驱动」的直接体现。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-beta-v1";

export const inject = ["labRegistry", "labAlpha"];

export function apply(ctx, config) {
  const book = ctx.get("labRegistry");
  const alpha = ctx.get("labAlpha");

  // 同 lab-alpha：拿不到就如实记录，不抛错。理由见那边的注释。
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
          alphaMarker: alpha?.marker ?? null,
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
