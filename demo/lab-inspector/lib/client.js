/**
 * lab-inspector — client 半边（Web GUI）。
 *
 * 在页面右侧贴一个只读面板，用卡片列出实验插件的状态。
 *
 * 状态名用 **Cordis 的 FiberState 原名**，不翻译 —— 这样面板上看到的词，
 * 和源码、日志、文档里的词是同一个。配色按语义分，绿色只给 ACTIVE：
 *
 *   ACTIVE            绿   加载完成、正在提供服务
 *   PENDING           黄   等 inject 声明的服务就位
 *   LOADING/UNLOADING 蓝   瞬态（回调执行中 / disposer 执行中）
 *   FAILED            红   回调或配置校验抛了错
 *   DISABLED/DISPOSED 灰   人主动关的 / 已移除
 *
 * 悬停卡片能看到该状态的一句话解释（原生 title，不是自造的交互）。
 *
 * 只读：没有按钮、没有点击、不发任何写请求。看得见摸不着。
 *
 * 手写成官方 client bundle 同款的 `window.__ModuleLoader__.load` 格式，
 * 所以这个包**不需要任何构建步骤**。
 */
window.__ModuleLoader__.load({
	id: "lab-inspector",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		const React = require("react");
		const h = React.createElement;

		//#region styles
		// 配色全部走框架的设计令牌（--dsw-alias-*），这样亮/暗主题自动跟随。
		// 每条都带 fallback 值，令牌哪天改名也不至于变成透明或黑块。
		const css = ""
			+ ".labi_panel{position:fixed;right:16px;top:72px;width:236px;max-height:calc(100vh - 120px);"
			+ "display:flex;flex-direction:column;gap:8px;z-index:40;"
			+ "background:var(--dsw-alias-bg-layer-2,#fff);border:1px solid var(--dsw-alias-border-l2,#e5e7eb);"
			+ "border-radius:10px;padding:12px;font-size:12px;line-height:1.5;"
			+ "font-family:inherit;box-shadow:0 6px 24px -12px rgba(0,0,0,.35)}"
			+ ".labi_head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;"
			+ "padding-bottom:8px;border-bottom:1px solid var(--dsw-alias-border-l2,#e5e7eb)}"
			+ ".labi_title{font-size:12px;font-weight:600;color:var(--dsw-alias-label-primary,#111)}"
			+ ".labi_count{font-size:11px;color:var(--dsw-alias-label-caption,#888);font-variant-numeric:tabular-nums}"
			+ ".labi_list{display:flex;flex-direction:column;gap:6px;overflow-y:auto;margin:0;padding:0;list-style:none}"
			+ ".labi_card{display:flex;align-items:flex-start;gap:8px;padding:8px 9px;border-radius:7px;"
			+ "border:1px solid var(--dsw-alias-border-l2,#e5e7eb);background:var(--dsw-alias-bg-layer-1,#fafafa)}"
			+ ".labi_dot{flex:none;width:8px;height:8px;border-radius:50%;margin-top:5px;"
			+ "background:var(--dsw-alias-label-dimmed,#9ca3af)}"
			+ ".labi_body{min-width:0;flex:1}"
			+ ".labi_name{font-weight:600;color:var(--dsw-alias-label-primary,#111);word-break:break-all}"
			+ ".labi_meta{color:var(--dsw-alias-label-caption,#888);font-size:11px;margin-top:1px;word-break:break-all}"
			+ ".labi_state{font-size:10px;margin-top:3px;letter-spacing:.06em;font-weight:600;"
			+ "color:var(--dsw-alias-label-dimmed,#9ca3af);font-family:ui-monospace,Consolas,monospace}"
			// ── 按 FiberState 分色：绿只给 ACTIVE，其余各按语义 ──
			+ '.labi_card[data-state="ACTIVE"]{border-color:var(--dsw-alias-state-success-primary,#16a34a);'
			+ "background:var(--dsw-alias-state-success-tertiary,#ecfdf3)}"
			+ '.labi_card[data-state="ACTIVE"] .labi_dot,'
			+ '.labi_card[data-state="ACTIVE"] .labi_name,'
			+ '.labi_card[data-state="ACTIVE"] .labi_state{color:var(--dsw-alias-state-success-primary,#16a34a)}'
			+ '.labi_card[data-state="ACTIVE"] .labi_dot{background:var(--dsw-alias-state-success-primary,#16a34a)}'
			+ '.labi_card[data-state="PENDING"]{border-color:var(--dsw-alias-state-warn-primary,#d97706)}'
			+ '.labi_card[data-state="PENDING"] .labi_dot{background:var(--dsw-alias-state-warn-primary,#d97706)}'
			+ '.labi_card[data-state="PENDING"] .labi_state{color:var(--dsw-alias-state-warn-primary,#d97706)}'
			+ '.labi_card[data-state="FAILED"]{border-color:var(--dsw-alias-state-error-primary,#dc2626);'
			+ "background:var(--dsw-alias-state-error-secondary,#fef2f2)}"
			+ '.labi_card[data-state="FAILED"] .labi_dot{background:var(--dsw-alias-state-error-primary,#dc2626)}'
			+ '.labi_card[data-state="FAILED"] .labi_name,'
			+ '.labi_card[data-state="FAILED"] .labi_state{color:var(--dsw-alias-state-error-primary,#dc2626)}'
			+ '.labi_card[data-state="LOADING"] .labi_dot,'
			+ '.labi_card[data-state="UNLOADING"] .labi_dot{background:var(--dsw-alias-state-business-primary,#2563eb)}'
			+ '.labi_card[data-state="LOADING"] .labi_state,'
			+ '.labi_card[data-state="UNLOADING"] .labi_state{color:var(--dsw-alias-state-business-primary,#2563eb)}'
			+ ".labi_empty{color:var(--dsw-alias-label-caption,#888);padding:6px 2px}"
			+ ".labi_err{color:var(--dsw-alias-state-error-primary,#dc2626);padding:6px 2px;word-break:break-all}"
			+ ".labi_foot{padding-top:6px;border-top:1px solid var(--dsw-alias-border-l2,#e5e7eb);"
			+ "color:var(--dsw-alias-label-caption,#888);font-size:10px;display:flex;justify-content:space-between;gap:6px}";

		const tagId = "lab-inspector/panel.css";
		if (typeof document !== "undefined"
			&& document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "lab-inspector";
			tag.dataset.pluginCss = tagId;
			tag.textContent = css;
			document.head.appendChild(tag);
		}
		//#endregion

		//#region component

		/**
		 * 每个状态的一句话解释，挂在原生 title 上（悬停可见）。
		 * 状态名本身用 Cordis 的 FiberState 原名，不翻译 —— 这样看到的词
		 * 和源码、日志、文档里的词是同一个。
		 */
		const STATE_HINT = {
			PENDING: "等 inject 声明的服务就位",
			LOADING: "插件回调正在执行（apply 运行中）",
			ACTIVE: "加载完成，正在提供服务",
			FAILED: "回调或配置校验抛了错",
			UNLOADING: "disposer 正在跑",
			DISPOSED: "已移除，不会再启动",
			DISABLED: "条目写了 disabled，压根没创建 fiber（人主动关的，不是依赖没到位）",
			NO_FIBER: "没被禁用却也没有 fiber —— 罕见，值得查",
		};

		/**
		 * 右侧只读状态面板。每 2 秒拉一次 host 的 /lab-inspector/state。
		 *
		 * 轮询而不是推送：这是教学演示件，2 秒的延迟无所谓，而轮询没有连接状态、
		 * 没有重连逻辑，代码少一半，读的人一眼能看完。
		 */
		function InspectorPanel() {
			const [state, setState] = React.useState(null);
			const [error, setError] = React.useState(null);

			React.useEffect(() => {
				let alive = true;
				const tick = () => {
					fetch("/lab-inspector/state", { cache: "no-store" })
						.then((res) => {
							if (!res.ok) throw new Error("HTTP " + res.status);
							return res.json();
						})
						.then((data) => {
							if (!alive) return;
							setState(data);
							setError(null);
						})
						.catch((err) => {
							if (alive) setError(String(err && err.message ? err.message : err));
						});
				};
				tick();
				const timer = setInterval(tick, 2000);
				return () => {
					alive = false;
					clearInterval(timer);
				};
			}, []);

			const entries = (state && state.entries) || [];
			const activeCount = entries.filter((e) => e.state === "ACTIVE").length;

			let body;
			if (error !== null) {
				body = h("div", { className: "labi_err" }, "读取失败：" + error);
			} else if (state === null) {
				body = h("div", { className: "labi_empty" }, "读取中…");
			} else if (entries.length === 0) {
				body = h("div", { className: "labi_empty" },
					"没有名字以 " + state.prefix + " 开头的插件");
			} else {
				body = h("ul", { className: "labi_list" }, entries.map((entry) =>
					h("li", {
						key: entry.id,
						className: "labi_card",
						"data-state": entry.state,
						title: entry.state + " — " + (STATE_HINT[entry.state] || "未知状态"),
					}, [
						h("span", { key: "dot", className: "labi_dot" }),
						h("div", { key: "body", className: "labi_body" }, [
							h("div", { key: "name", className: "labi_name" }, entry.name),
							// 条目 id 与包名不同时才显示 —— 它是树内地址，不是包名
							entry.id !== entry.name
								? h("div", { key: "id", className: "labi_meta" }, "id: " + entry.id)
								: null,
							h("div", { key: "state", className: "labi_state" }, entry.state),
						]),
					])
				));
			}

			return h("div", { className: "labi_panel" }, [
				h("div", { key: "head", className: "labi_head" }, [
					h("span", { key: "t", className: "labi_title" }, "实验插件"),
					h("span", { key: "c", className: "labi_count" },
						activeCount + " / " + entries.length + " ACTIVE"),
				]),
				h("div", { key: "body" }, body),
				state !== null
					? h("div", { key: "foot", className: "labi_foot" }, [
						h("span", { key: "p" }, "前缀 " + state.prefix),
						h("span", { key: "t" }, "只读"),
					])
					: null,
			]);
		}
		//#endregion

		//#region plugin body
		/** client 侧需要的服务：只要插槽注册表。 */
		const inject = ["slots"];

		/**
		 * client 插件体：把面板挂进 shell 叠加层。
		 *
		 * 选 `shell.overlay` 而不是 `details`：overlay 是叠加语义，不抢占任何
		 * 已有区域；`details` 那个座位是「坐上去就得自己渲染整块」的替换语义。
		 */
		function apply(ctx) {
			ctx.slots.inject("shell.overlay", () => ctx.slots.register({
				name: "shell.overlay",
				id: "lab-inspector-panel",
				order: 100,
			}, InspectorPanel));
		}
		//#endregion

		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	},
});
