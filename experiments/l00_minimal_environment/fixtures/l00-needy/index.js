/**
 * L0 的「永远等不到」插件：硬依赖一个根本不存在的服务。
 *
 * 用途只有一个 —— 制造一个**永远停在 PENDING** 的条目，
 * 用来测 boot 末尾那道审计（`assertEntriesActivated`）到底管不管。
 *
 * inject 写成数组形式 = 硬依赖：服务不到位，apply 就永远不会被调用。
 * 所以下面那句 writeFileSync 是个诱饵：见证文件**出现了**才说明它被激活过，
 * 而本插件存在的意义正是它不该出现。
 */

import { writeFileSync } from "node:fs";

export const inject = ["definitelyNotAService"];

export function apply(ctx, config) {
  if (config?.witness) {
    writeFileSync(config.witness, JSON.stringify({ appliedAt: new Date().toISOString() }), "utf8");
  }
}
