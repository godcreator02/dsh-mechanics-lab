/**
 * apply-runs 用的教学插件：一个 DSH 插件最少长什么样，全部家当就三样——
 * package.json 的 "type": "module"、exports["."] 指向本文件、导出一个
 * apply 函数。不 inject 任何服务、不注册路由、不碰 UI，这样「插件被
 * 加载了」这件事就没有任何别的解释。
 *
 * 观测手段是写一个见证文件，而不是打日志：日志可能被吞、被缓冲、被格式
 * 变化骗过去；文件存在与否是硬事实。
 */

import { writeFileSync } from "node:fs";

/** 代码版本指纹。改了这个值就能证明跑的是新代码。 */
const MARKER = "apply-runs-v1";

/** 模块顶层求值：模块被 import 的时刻。它变了说明模块被重新 import 过。 */
const moduleLoadedAt = new Date().toISOString();

/**
 * @param {object} ctx    插件上下文（本项不用它）
 * @param {object} config 活层条目里 `config:` 那一坨，原样送到这里
 */
export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) {
    // 没给见证文件路径就没法被观测到——直接吵出来，别静默失败
    throw new Error("lab-minimal: config.witness 是必需的");
  }

  writeFileSync(
    witness,
    JSON.stringify(
      {
        marker: MARKER,
        moduleLoadedAt,
        appliedAt: new Date().toISOString(),
        config,
      },
      null,
      2,
    ),
    "utf8",
  );
}
