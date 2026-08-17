/**
 * standalone.js —— 不成包的单文件插件，供 preset 用**相对路径**和**绝对路径**
 * 两种写法引用。
 *
 * 相对路径那条会把本文件拷进 preset 自己的目录（相对 specifier 锚在组合文件
 * 所在目录）；绝对路径那条直接指向 fixtures 里的这一份，用来验框架有没有替
 * 我们把带盘符的 Windows 路径转成 file URL——不转的话 Node 的 ESM loader 会
 * 报 `ERR_UNSUPPORTED_ESM_URL_SCHEME`。
 */

import { appendFileSync } from "node:fs";

export function apply(_ctx, config) {
  const out = config?.out;
  const label = config?.label ?? "standalone";
  if (typeof out === "string" && out.length > 0) {
    appendFileSync(out, `${JSON.stringify({ label, via: "standalone.js", at: new Date().toISOString() })}\n`, "utf8");
  }
}
