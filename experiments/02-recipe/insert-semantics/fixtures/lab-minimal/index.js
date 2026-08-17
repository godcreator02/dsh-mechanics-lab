/**
 * 最小插件：只用来证明「apply 执行了、带着什么 config」。
 *
 * 不 inject 任何服务、不注册路由、不碰 UI——刻意做到最小，这样「插件被
 * 加载了」这件事就没有任何别的解释。观测手段是写一个见证文件，而不是
 * 打日志：日志可能被吞、被缓冲、被格式变化骗过去；文件存在与否是硬事实。
 */
import { writeFileSync } from "node:fs";

/** 代码版本指纹。改了这个值就能证明跑的是新代码。 */
const MARKER = "lab-minimal-v1";

/** 模块顶层求值：模块被 import 的时刻。 */
const moduleLoadedAt = new Date().toISOString();

/**
 * @param {object} ctx    插件上下文（本项不用它）
 * @param {object} config 活层条目里 `config:` 那一坨，原样送到这里
 */
export function apply(ctx, config) {
  const witness = config?.witness;
  if (!witness) {
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
