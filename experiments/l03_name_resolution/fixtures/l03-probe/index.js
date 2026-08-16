/**
 * L3 的通用探针：除了 L1/L0 那三个指纹（marker / moduleLoadedAt / appliedAt），
 * 多探一件事——`ctx.get("loader").internal` 是否激活。
 *
 * 这件事优先级最高：`cordis-plugin-loader` 的 `EntryTree.import` 里，
 * `internal` 分支排在最前面。如果它激活，相对路径 / 绝对路径 / 裸包名
 * **全部走同一条路**（`internal.import(name, baseUrl, {})`，name 原样传入不做
 * 任何前缀判断），那"三条互不相通的解析路径"的说法就不成立——本课后面
 * 每一个用例的因果解释，都要先看这个字段才知道该往哪个分支上挂。
 *
 * 这个插件本身通过**裸包名**被加载（见 test_loader_internal_activated），
 * 所以它自己的加载成功与否不受这个问题影响，可以放心当第一个用例。
 */

import { writeFileSync } from "node:fs";

const MARKER = "l03-probe-v1";
const moduleLoadedAt = new Date().toISOString();

/** 观测点绝不抛错：拿不到就如实记 null。 */
function safe(fn) {
  try {
    const v = fn();
    return v === undefined ? null : v;
  } catch {
    return null;
  }
}

export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) throw new Error("l03-probe: config.witness 是必需的");

  const loader = safe(() => ctx.get("loader"));

  writeFileSync(
    witness,
    JSON.stringify(
      {
        marker: MARKER,
        moduleLoadedAt,
        appliedAt: new Date().toISOString(),
        // ctx.loader.internal 是否激活 —— 决定 name 解析走哪条分支
        loaderInternal: loader ? safe(() => loader.internal !== undefined) : null,
        // ctx.baseUrl 是相对路径解析的锚点，顺手记一笔
        baseUrl: safe(() => String(ctx.baseUrl ?? "")),
        config,
      },
      null,
      2,
    ),
    "utf8",
  );
}
