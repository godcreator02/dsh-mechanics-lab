/**
 * 包解析的回退链是 exports["."] → main → 默认 index.js，三条路任意一条通就能
 * 被包名 resolve 到。这个包故意三条全断——没有 exports、没有 main，真正的
 * 代码又不叫 index.js（叫 plugin.js）。
 *
 * 用途：证明相对路径没有这条回退链。同一份代码：用包名引用（走 package.json
 * 解析）应当失败；用相对路径直接指到这个文件（走纯 URL 解析，不看
 * package.json）应当成功。
 */
import { writeFileSync } from "node:fs";

const MARKER = "fallback-plugin-v1";

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) throw new Error("fallback/plugin: config.witness 是必需的");
  writeFileSync(
    witness,
    JSON.stringify({ marker: MARKER, appliedAt: new Date().toISOString() }, null, 2),
    "utf8",
  );
}
