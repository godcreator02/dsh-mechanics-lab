/**
 * 只用来证明「apply 执行了、带着什么 config」——写一份见证文件。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-patch-v1";
const moduleLoadedAt = new Date().toISOString();

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) {
    throw new Error("lab-patch: config.witness 是必需的");
  }

  writeFileSync(
    witness,
    JSON.stringify(
      {
        marker: MARKER,
        moduleLoadedAt,
        appliedAt: new Date().toISOString(),
        config,
      },
      null,
      2,
    ),
    "utf8",
  );
}
