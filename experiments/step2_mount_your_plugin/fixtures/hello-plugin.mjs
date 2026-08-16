/**
 * 第 2 步的教学插件：一个插件最少长什么样。
 *
 * 全部家当就一样：**导出一个叫 apply 的函数**。
 * 实例挂上这个插件时会调用它，参数先不管，本步一个都用不到。
 *
 * 后缀写 .mjs，Node 就直接按 ESM 读这个文件，不用再为它配 package.json。
 *
 * 怎么让人看见它跑过：apply 里写一个文件出来，跟本文件并排放。
 * 不打日志——日志会被吞、被缓冲、被格式变化骗过去；文件在不在是硬事实。
 */

import { writeFileSync } from "node:fs";

/** 代码版本指纹。改了这个值就能证明跑的是新代码。 */
const MARKER = "step2-hello-v1";

export function apply() {
  writeFileSync(
    new URL("./hello-ran.json", import.meta.url),
    JSON.stringify({ marker: MARKER, appliedAt: new Date().toISOString() }, null, 2),
    "utf8",
  );
}
