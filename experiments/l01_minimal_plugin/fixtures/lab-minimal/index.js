/**
 * L1 的教学插件：一个 DSH 插件最少长什么样。
 *
 * 全部家当就三样：
 *   1. package.json 里 "type": "module"（用 ESM 写）
 *   2. package.json 里 exports["."] 指向本文件（Node 得能 resolve 到）
 *   3. 本文件导出一个 apply 函数
 *
 * 它不 inject 任何服务、不注册路由、不碰 UI —— 刻意做到最小，
 * 这样「插件被加载了」这件事就没有任何别的解释。
 *
 * 观测手段是**写一个见证文件**，而不是打日志：
 * 日志可能被吞、被缓冲、被格式变化骗过去；文件存在与否是硬事实。
 * 而且这样 L1 不需要 webServer，profile 只叠 dsh-base 就能跑，启动快得多。
 */

import { writeFileSync } from "node:fs";

/** 代码版本指纹。改了这个值就能证明跑的是新代码。 */
const MARKER = "l01-minimal-v1";

/** 模块顶层求值：模块被 import 的时刻。它变了说明模块被重新 import 过。 */
const moduleLoadedAt = new Date().toISOString();

/**
 * @param {object} ctx    插件上下文（本课不用它，L3 起才登场）
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
        // 把收到的 config 原样回显：用来验证活层写的 config 确实送达了 apply
        config,
      },
      null,
      2,
    ),
    "utf8",
  );
}
