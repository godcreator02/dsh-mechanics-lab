// 特定包装的 CJS——本实验不需要真的渲染 UI，能被 client-modules 扫进图、
// 能被 HTTP 取到就够了。
window.__ModuleLoader__.load({
  id: "probe-client-fresh",
  factory: (require) => {
    const module = { exports: {} };
    module.exports = {
      inject: [],
      apply(ctx) {},
    };
    return module.exports;
  },
});
