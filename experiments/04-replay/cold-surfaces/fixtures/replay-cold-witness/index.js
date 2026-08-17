/**
 * 见证员：把每次 apply 收到的 config 原样记下来。
 *
 * 只关心一件事——「这个条目的 config 有没有变」。用途是验证「运行期改
 * `--patch` 指向的文件，实例会不会把新内容读进来」：如果不会，见证文件应当
 * 永远只有一条记录，且 `value` 字段停在启动时的初始值。
 *
 * 记录数组建在模块级，写文件时写整个数组——万一这个条目真被重挂了，重挂本身
 * 也该在见证文件里留痕，而不是被覆盖掉、变得跟「只 apply 过一次」一模一样。
 */
import { writeFileSync } from "node:fs";

const MARKER = "replay-cold-witness-v1";
const records = [];

export function apply(ctx, config) {
  const out = config?.out;
  if (!out) throw new Error("replay-cold-witness: config.out 是必需的");

  records.push({
    marker: MARKER,
    applyIndex: records.length,
    at: new Date().toISOString(),
    value: config?.value ?? null,
  });
  writeFileSync(out, JSON.stringify(records, null, 2), "utf8");
}
