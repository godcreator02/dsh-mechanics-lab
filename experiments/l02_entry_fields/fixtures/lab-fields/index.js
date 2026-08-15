/**
 * L2 的教学插件：观测条目字段的效果。
 *
 * 与 L1 的 lab-minimal 几乎一样（都靠写见证文件证明 apply 执行过），
 * 差别是这里额外回显运行平台 —— 用来验证 `disabled` 写成 `!!js` 表达式时
 * 的条件求值确实按平台生效。
 *
 * fixtures 在各课之间重复是**有意的**：一个实验目录就是完整的一课，
 * 改这一课也弄不坏另一课。见 CLAUDE.md。
 */

import { writeFileSync } from "node:fs";

const MARKER = "l02-fields-v1";
const moduleLoadedAt = new Date().toISOString();

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) {
    throw new Error("lab-fields: config.witness 是必需的");
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
