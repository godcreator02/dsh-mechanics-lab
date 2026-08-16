/**
 * 官方 publish 文档里 `dsh-hello-plugin/startup` 那种子路径引用的教学样板：
 * 这个包在 exports 里显式声明了 "./tool"，name 写成 "l03-subpath-declared/tool"
 * 应当能被加载到——对照组见 l03-subpath-undeclared（同名文件，但 exports 没声明）。
 */
import { writeFileSync } from "node:fs";

const MARKER = "l03-subpath-declared-tool-v1";

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) throw new Error("l03-subpath-declared/tool: config.witness 是必需的");
  writeFileSync(
    witness,
    JSON.stringify({ marker: MARKER, appliedAt: new Date().toISOString() }, null, 2),
    "utf8",
  );
}
