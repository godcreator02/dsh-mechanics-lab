/**
 * 依赖 `labRegistry` 的消费者。依赖声明写在**插件代码里**——这是主流写法，
 * 条目上也能写（本项就是要验条目级 `inject` 与代码级声明的关系）。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-alpha-v1";

export const inject = ["labRegistry"];

export function apply(ctx, config) {
  const book = ctx.get("labRegistry");

  // ⚠️ 拿不到服务时不抛错，如实记录。探针在观测点抛错会把两种完全不同的
  // 现象混成一种：「inject 没满足 → 根本没 apply」 vs 「apply 了但服务是
  // undefined」——前者见证文件不出现，后者见证文件出现且 gotRegistry=false，
  // 必须能分开。
  if (book) {
    book.sign("lab-alpha", config?.note ?? null);
  }

  if (config?.witness) {
    writeFileSync(
      config.witness,
      JSON.stringify(
        {
          marker: MARKER,
          appliedAt: new Date().toISOString(),
          gotRegistry: book !== undefined && book !== null,
          config,
        },
        null,
        2,
      ),
      "utf8",
    );
  }
}
