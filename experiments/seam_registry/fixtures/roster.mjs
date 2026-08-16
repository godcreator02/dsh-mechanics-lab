/**
 * 名册 —— **声明方**：占住名字的那一个，肚子里有一张表。
 *
 * 上一项立住了「一个名字一个主人」。想让多个实现并存，办法不是去打破那条规矩，
 * 而是**别让它们争名字**：只有这个文件去占 `labRoster`，别人往它的表里塞。
 *
 * 注意 `register()` 里那句 `this.ctx.effect(...)`：
 * 上一项测出来，服务方法里的 `this.ctx` 属于**调用方**，所以这个 effect 挂在
 * 塞东西的那个插件身上——它下线，它那一行自己就没了，不用名册去管。
 */

import { Service } from "@deepseek-ai/cordis";
import { writeFileSync } from "node:fs";

export const inject = ["labObserver"];

export function apply(ctx, config) {
  const say = ctx.labObserver.for(ctx);

  class 名册 extends Service {
    constructor(ctx) {
      super(ctx, "labRoster");
      this.表 = new Map();
    }

    /** 往表里塞一行。返回的 disposer 挂在调用方身上。 */
    register(id, 值) {
      if (this.表.has(id)) {
        throw new Error(`名册里已经有「${id}」了`);
      }
      const 表 = this.表;
      return this.ctx.effect(function* () {
        表.set(id, 值);
        yield () => 表.delete(id);
      }, "labRoster.register()");
    }

    /** 表里现在有哪些行。 */
    list() {
      return [...this.表.keys()].sort();
    }
  }

  new 名册(ctx);
  say("名册开张了，表是空的");
  writeFileSync(config.见证, JSON.stringify({ 我是: "名册", 开张时表里: [] }, null, 2), "utf8");
}
