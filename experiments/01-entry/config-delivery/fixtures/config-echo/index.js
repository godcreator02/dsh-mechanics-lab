/**
 * config-delivery 用的教学插件：把 apply() 收到的第二个参数原样报出来。
 *
 * 输出落在 `process.cwd()`（dsh 子进程的 cwd 就是 profile 目录，各 profile
 * 互不相同），**不从 config 里读落点**——这样连「一个 config 都不写」的场合
 * 也能看到结果。`received: typeof config` 单独记一笔类型，是因为 `undefined`
 * 放进 JSON 会让整个键消失，不这样区分就分不清「收到了 undefined」和
 * 「插件根本没写这个键」。
 */

import { writeFileSync } from "node:fs";
import { join } from "node:path";

const MARKER = "config-delivery-v1";
const OUTPUT = join(process.cwd(), "received-config.json");

export function apply(ctx, config) {
  writeFileSync(
    OUTPUT,
    JSON.stringify({ marker: MARKER, received: typeof config, config: config ?? null }, null, 2),
    "utf8",
  );
}
