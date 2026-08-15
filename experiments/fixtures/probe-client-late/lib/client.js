// 只有 package.json 补上 dsh.client 声明（且 exports["./client"] 指到这个
// 文件）之后，client-modules 才会去扫它——这份文件从一开始就摆在磁盘上，
// 单纯「文件存在」不等于「被声明」。
window.__ModuleLoader__.load({
  id: "probe-client-late",
  factory: (require) => {
    const module = { exports: {} };
    module.exports = {
      inject: [],
      apply(ctx) {},
    };
    return module.exports;
  },
});
