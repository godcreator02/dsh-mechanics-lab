/**
 * 依赖链的中段：依赖 `labRegistry`，登记自己，并再提供一个服务 `labAlpha`。
 *
 * 它同时是消费者和提供者，所以 `lab-beta` 依赖它时构成二级依赖链。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-alpha-v1";

export const inject = ["labRegistry"];

export function apply(ctx, config) {
  const book = ctx.get("labRegistry");
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
        },
        null,
        2,
      ),
      "utf8",
    );
  }
}
