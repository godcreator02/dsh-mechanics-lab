/**
 * 硬依赖一个根本不存在的服务——制造一个永远停在 PENDING 的条目，
 * 用来测 boot 末尾那道审计（`assertEntriesActivated`）到底管不管。
 *
 * `writeFileSync` 是个诱饵：见证文件出现了才说明它被激活过，
 * 而本插件存在的意义正是它不该出现。
 */

import { writeFileSync } from "node:fs";

export const inject = ["definitelyNotAService"];

export function apply(ctx, config) {
  if (config?.witness) {
    writeFileSync(config.witness, JSON.stringify({ appliedAt: new Date().toISOString() }), "utf8");
  }
}
