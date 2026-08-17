// 占位入口。本项从不引用 "."，只引用 "./tool" 子路径——这个文件存在
// 只是为了让 package.json 的 exports["."] 有个真实目标，不参与任何用例。
export function apply() {}
