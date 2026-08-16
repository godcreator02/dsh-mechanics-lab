/**
 * L5 的教学插件：只用来证明「apply 执行了、带着什么 config」。
 *
 * 与 L2 的 lab-fields 几乎一样（都靠写见证文件证明 apply 执行过），
 * L5 单独起一份是因为本课的用例经常需要故意造出会撞车 / 会卡住的组合
 * （重复 id、!!js 条件禁用），不想跟别课的 fixture 混在一起。
 *
 * fixtures 在各课之间重复是有意的：一个实验目录就是完整的一课。见 CLAUDE.md。
 */

import { writeFileSync } from "node:fs";

const MARKER = "l05-patch-v1";
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
