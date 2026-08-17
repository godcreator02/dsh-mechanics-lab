/**
 * 与 subpath-declared/tool.js 逐字节相同的代码，唯一区别是这个包的 exports
 * 里没有声明 "./tool"。文件本身货真价实存在于磁盘上——如果加载失败，失败
 * 原因只能是 exports 映射表把这条子路径挡在外面，不是文件不存在。
 */
import { writeFileSync } from "node:fs";

const MARKER = "subpath-undeclared-tool-v1";

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) throw new Error("subpath-undeclared/tool: config.witness 是必需的");
  writeFileSync(
    witness,
    JSON.stringify({ marker: MARKER, appliedAt: new Date().toISOString() }, null, 2),
    "utf8",
  );
}
