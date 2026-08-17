/**
 * 对照插件：代码里**不声明** `inject`，运行时按需 `ctx.get()`。
 *
 * 用来验证「不声明依赖就不等」——apply 立刻跑，服务不在就是 undefined，不阻塞。
 */

import { writeFileSync } from "node:fs";

export function apply(ctx, config) {
  const registry = ctx.get("labRegistry");

  if (config?.witness) {
    writeFileSync(
      config.witness,
      JSON.stringify(
        {
          marker: "lab-open-v1",
          appliedAt: new Date().toISOString(),
          gotRegistry: registry !== undefined && registry !== null,
        },
        null,
        2,
      ),
      "utf8",
    );
  }
}
