/**
 * 最小构成的插件：只有 apply()，靠见证文件证明加载成功。
 *
 * 用于验证「Node 能不能 resolve 到入口」这条边界——测试代码会把这份代码
 * 复制到不同名字的入口文件（`index.js` / `plugin.js`）并搭配不同的
 * package.json 变体，验证 exports / main / 默认 index.js 三条回退路。
 */

import { writeFileSync } from "node:fs";

const MARKER = "name-resolution-minimal-v1";

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) {
    throw new Error("minimal: config.witness 是必需的");
  }

  writeFileSync(
    witness,
    JSON.stringify({ marker: MARKER, appliedAt: new Date().toISOString() }, null, 2),
    "utf8",
  );
}
