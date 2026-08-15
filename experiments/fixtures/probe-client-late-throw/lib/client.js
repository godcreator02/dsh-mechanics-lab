window.__ModuleLoader__.load({
  id: "probe-client-late-throw",
  factory: (require) => {
    const module = { exports: {} };
    module.exports = {
      inject: [],
      apply(ctx) {},
    };
    return module.exports;
  },
});
