/**
 * 服务隔离用例：消费 `labFlavor`，把看到的值写进见证文件。
 *
 * `inject` 硬依赖 `labFlavor`（`inject-hard-dependency` 立住的规矩）：服务不到位
 * 就不 apply。所以见证文件出现本身就说明「在这个组的隔离上下文里，`labFlavor`
 * 服务是可解析的」；文件里的 `sawValue` 说明解析到的是**哪一份**。
 */

import { writeFileSync } from "node:fs";

const MARKER = "lab-flavor-taster-v1";

export const inject = ["labFlavor"];

export function apply(ctx, config) {
  const flavor = ctx.get("labFlavor");
  if (config?.witness) {
    writeFileSync(
      config.witness,
      JSON.stringify(
        {
          marker: MARKER,
          appliedAt: new Date().toISOString(),
          sawValue: flavor ? flavor.value : null,
          sawProviderMarker: flavor ? flavor.marker : null,
        },
        null,
        2,
      ),
      "utf8",
    );
  }
}
