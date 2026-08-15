// probe-sidecar —— E5 用例 1/2 的靶子插件。
//
// apply() 期用 readFileSync 读同目录下的 sidecar.txt，存进闭包变量 `sidecar`，
// 模拟「apply 期快照」语义。handler 里绝不重新读文件——要测的就是这份快照
// 会不会因为 sidecar.txt 本身被改而更新（假说：不会，因为它从没进过 ESM
// loadCache），以及会不会因为插件代码本身被改（模块被重新 import、apply
// 重跑）而更新（假说：会）。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIR = path.dirname(fileURLToPath(import.meta.url));

// 模块顶层求值——只有这个模块被 HMR 重新 import 过，这个值才会变。
const moduleLoadedAt = new Date().toISOString();

// 代码版本标记。E5 用例2 改的就是这一行。
const MARKER = "v1";

export const name = "probe-sidecar";
export const inject = ["webServer"];

export function apply(ctx) {
  const appliedAt = new Date().toISOString();
  // apply 期读一次，存进闭包变量——这是本实验的核心：sidecar.txt 不是被
  // import 的模块，只有 apply 重跑时才会被重新读取。
  const sidecar = fs.readFileSync(path.join(DIR, "sidecar.txt"), "utf8").trim();

  ctx.effect(
    () =>
      ctx.webServer.register({
        kind: "exact",
        path: "/probe-sidecar",
        handler: (req, res) => {
          const text = JSON.stringify({ marker: MARKER, sidecar, appliedAt, moduleLoadedAt });
          res.writeHead(200, {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
            "content-length": Buffer.byteLength(text),
          });
          res.end(text);
        },
      }),
    "probe-sidecar: probe route",
  );
}
