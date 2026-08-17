/**
 * 服务隔离用例：提供一个服务 `labFlavor`，值来自 `config.value`。
 *
 * 同一个服务名会在两个不同的 `isolate` 组里各挂一份、值不同——如果隔离
 * 真的生效，两组各自的消费者应当只看到自己组内那一份，互不干扰。
 * 如果隔离没生效（比如 isolate 配置写错），两个 `ctx.provide("labFlavor", …)`
 * 落在同一个上下文里，要么后者覆盖前者，要么框架直接报重复注册——
 * 两种结局都跟「隔离生效」长得不一样，用例足以分辨。
 */

const MARKER = "lab-flavor-v1";

export function apply(ctx, config) {
  const value = config?.value ?? null;
  ctx.provide("labFlavor", { marker: MARKER, value });
}
