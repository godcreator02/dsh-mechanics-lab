/**
 * 依赖 `labRegistry` 的消费者。依赖声明写在代码里（`export const inject`）——
 * 这是主流写法，条目上也能写（见 01-entry/inject-field）。
 *
 * 拿不到服务时**不抛错**，如实记录 `gotRegistry`。探针在观测点抛错会把两种
 * 完全不同的现象混成一种：「inject 没满足 → 根本没 apply」 vs
 * 「apply 了但服务是 undefined」——前者见证文件不出现，后者出现且
 * `gotRegistry: false`，必须能分开。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-alpha-v1";

export const inject = ["labRegistry"];

export function apply(ctx, config) {
  const book = ctx.get("labRegistry");

  if (book) {
    book.sign("lab-alpha", config?.note ?? null);
  }

  if (config?.witness) {
    writeFileSync(
      config.witness,
      JSON.stringify(
        {
          marker: MARKER,
          appliedAt: new Date().toISOString(),
          gotRegistry: book !== undefined && book !== null,
        },
        null,
        2,
      ),
      "utf8",
    );
  }
}
