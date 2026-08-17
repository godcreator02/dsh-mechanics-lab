/**
 * field-vocabulary 用的教学插件：靠写见证文件证明 apply 执行过、
 * config 原样送达。除了 marker / moduleLoadedAt / appliedAt 三个指纹，
 * 没有别的行为——它自己不该成为任何一条判定的解释。
 */

import { writeFileSync } from "node:fs";

const MARKER = "field-vocabulary-v1";
const moduleLoadedAt = new Date().toISOString();

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) {
    throw new Error("lab-entry: config.witness 是必需的");
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
