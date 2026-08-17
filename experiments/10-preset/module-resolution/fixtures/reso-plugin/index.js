/**
 * reso-plugin —— 被 preset 用**裸包名**引用的教学插件。
 *
 * 它自己什么能力都不提供：本项要问的是「这一行的模块解析得不得到」，
 * 插件干什么无关紧要，干得越少越不会引入别的失败原因（inject 任何服务都会
 * 引入「等不到就不激活」这条噪声，而 mount 期恰好会因为「有行没激活」整个失败）。
 *
 * 唯一的动作是往见证文件追加一行，证明 `apply` 真的跑过——只看
 * `standingKeyFor()` 没抛，只能说明「组合成功」，见证文件才说明「代码真执行了」。
 */

import { appendFileSync } from "node:fs";

export function apply(_ctx, config) {
  const out = config?.out;
  const label = config?.label ?? "bare";
  if (typeof out === "string" && out.length > 0) {
    appendFileSync(out, `${JSON.stringify({ label, via: "reso-plugin", at: new Date().toISOString() })}\n`, "utf8");
  }
}
