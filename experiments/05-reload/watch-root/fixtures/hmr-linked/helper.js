/**
 * 纯算法文件。它不导出插件、不碰 ctx、不注册任何东西——只是被 index.js
 * `import` 进去的一个函数。
 *
 * 改这个文件、`index.js` 一个字不动，用来问「hmr 关掉之后跑着的代码
 * 还能不能拿到新实现」。
 */

export function compute() {
  return "算法第一版";
}
