/**
 * 纯算法文件。它不导出插件、不碰 ctx、不注册任何东西——只是被 index.js
 * `import` 进去的一个函数。本项用例不改它，只是 index.js 依赖它才能跑。
 */

export function compute() {
  return "算法第一版";
}
