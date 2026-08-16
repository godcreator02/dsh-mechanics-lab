/**
 * 第 3 步的教学插件：把 `apply` 收到的第二个参数原样写下来。
 *
 * 只做这一件事，别的什么都不干 —— 这样文件里出现的东西就只有一种解释：
 * 它是从条目的 `config` 来的。
 *
 * 落点写死在插件自己的目录里，**不从 config 里读** ——「一个 config 都不写」
 * 的场合也照样看得到结果。
 */

import { writeFileSync } from "node:fs";
import { join } from "node:path";

const MARKER = "step3-config-echo-v1";

/** 写在插件目录下，跟 index.js 并排 */
const OUTPUT = join(import.meta.dirname, "received-config.json");

export function apply(ctx, config) {
  writeFileSync(
    OUTPUT,
    JSON.stringify(
      {
        marker: MARKER,
        appliedAt: new Date().toISOString(),
        // `undefined` 放进 JSON 会让整个键消失，那样就分不清「收到 undefined」
        // 和「插件没写这个键」。所以先把类型单独记成字符串，再放原值。
        received: typeof config,
        config: config ?? null,
      },
      null,
      2,
    ),
    "utf8",
  );
}
