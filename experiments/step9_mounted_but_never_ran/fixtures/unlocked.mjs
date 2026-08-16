/**
 * 对照组 —— 跟 locked.mjs 逐行对得上，只有一处不同：**没有 inject 那一行**。
 *
 * 两个东西都改成运行时用 `ctx.get(名字)` 去取：取到就用，取不到就算了，
 * 不声明「我要等它」。见证文件里连带记下这两次取的结果。
 */

import { writeFileSync } from "node:fs";

export function apply(ctx, config) {
  const 钥匙 = ctx.get("开锁服务");
  const 观察器 = ctx.get("labObserver");

  writeFileSync(
    config.见证,
    JSON.stringify({
      跑了: true,
      拿到开锁服务: 钥匙 !== undefined && 钥匙 !== null,
      拿到观察器: Boolean(观察器),
    }),
    "utf8",
  );

  if (观察器) 观察器.for(ctx)("我跑起来了 —— 谁都没等");
}
