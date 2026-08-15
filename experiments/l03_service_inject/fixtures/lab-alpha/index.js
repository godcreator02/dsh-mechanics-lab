/**
 * L3 依赖链的中段：依赖 `labRegistry`，登记自己，并**再提供一个服务** `labAlpha`。
 *
 * 它同时是消费者和提供者，所以 `lab-beta` 依赖它时构成二级依赖链。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-alpha-v1";

/** 依赖声明写在**插件代码里**——这是主流写法（条目上也能写，见 L3 用例）。 */
export const inject = ["labRegistry"];

export function apply(ctx, config) {
  const book = ctx.get("labRegistry");

  // ⚠️ 拿不到服务时**不抛错**，如实记录。
  // 探针在观测点抛错会把两种完全不同的现象混成一种：
  //   「inject 没满足 → 根本没 apply」 vs 「apply 了但服务是 undefined」
  // 前者见证文件不出现，后者见证文件出现且 gotRegistry=false —— 必须能分开。
  const ledgerBefore = book ? book.list() : null;

  if (book) {
    book.sign("lab-alpha", config?.note ?? null);
    ctx.provide("labAlpha", { marker: MARKER, greet: () => "alpha 在这儿" });
  }

  if (config?.witness) {
    writeFileSync(
      config.witness,
      JSON.stringify(
        {
          marker: MARKER,
          appliedAt: new Date().toISOString(),
          /** apply 执行的那一刻，inject 声明的服务到底拿没拿到 */
          gotRegistry: book !== undefined && book !== null,
          /** 登记**之前**账本里已经有谁 —— 能看出自己是第几个到的 */
          ledgerBefore,
          config,
        },
        null,
        2,
      ),
      "utf8",
    );
  }
}
