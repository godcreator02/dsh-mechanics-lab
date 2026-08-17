/**
 * 纯算法文件。它不导出插件、不碰 ctx、不注册任何东西——只是被 index.js
 * `import` 进去的一个函数。
 *
 * 这一项改的就是这个文件，一个字都不碰 index.js：看重来的是这个文件，
 * 还是整个插件入口。
 */

export function compute() {
  return "算法第一版";
}
