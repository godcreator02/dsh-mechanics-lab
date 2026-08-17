/**
 * disabled 用的教学插件：写见证文件证明 apply 执行过，外加回显运行平台——
 * 用来验证 `disabled` 写成 `!!js` 表达式时的条件求值确实按平台生效。
 */

import { writeFileSync } from "node:fs";

const MARKER = "disabled-v1";
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
        platform: process.platform,
        config,
      },
      null,
      2,
    ),
    "utf8",
  );
}
