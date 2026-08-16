/**
 * L1 已经验过包解析的回退链：exports["."] → main → 默认 index.js，
 * 三条路任意一条通就能被包名 resolve 到。这个包**故意三条全断**——
 * 没有 exports、没有 main，真正的代码又不叫 index.js（叫 plugin.js）。
 *
 * 用途：证明"相对路径没有这条回退链"。同一份代码：
 *   - 用**包名**引用（"l03-fallback"，走 package.json 解析）应当失败
 *   - 用**相对路径**直接指到这个文件（走纯 URL 解析，不看 package.json）
 *     应当成功——因为 URL 解析压根不知道也不关心有没有 exports/main。
 */
import { writeFileSync } from "node:fs";

const MARKER = "l03-fallback-plugin-v1";

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) throw new Error("l03-fallback/plugin: config.witness 是必需的");
  writeFileSync(
    witness,
    JSON.stringify({ marker: MARKER, appliedAt: new Date().toISOString() }, null, 2),
    "utf8",
  );
}
