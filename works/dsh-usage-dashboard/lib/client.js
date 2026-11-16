window.__ModuleLoader__.load({
	id: "dsh-usage-dashboard",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

		const React = require("react");
		const h = React.createElement;

		/* ── copy ──────────────────────────────────────────────────────────── */

		const NS = "usageDashboard";
		const zh = {
			"type.label": "用量与花费",
			"guide.title": "用量与花费",
			"guide.description": "Token 用量、缓存命中率与按峰谷价折算的花费",
			"header.chip": "今日 {cost}",
			"header.chipAria": "今日已花费 {cost}，点击查看用量统计",
			"header.title": "今日花费 {cost}（{tokens} tokens）",
			"state.loading": "正在统计会话日志…",
			"state.error": "统计失败：{message}",
			"state.retry": "重试",
			"action.refresh": "刷新",
			"action.refreshing": "刷新中…",
			"peak.on": "峰时",
			"peak.off": "谷时",
			"peak.onHint": "当前为峰时计费（价格为谷时的 2 倍）",
			"peak.offHint": "当前为谷时计费",
			"metric.cost": "总花费",
			"metric.tokens": "总 tokens",
			"metric.cacheHit": "缓存命中率",
			"metric.calls": "模型调用",
			"sections.trend": "每日花费",
			"sections.tokens": "每日 tokens",
			"sections.models": "按模型",
			"sections.sessions": "按会话",
			"sections.workspaces": "按工作区",
			"sections.hours": "按 UTC 小时",
			"legend.hit": "缓存命中",
			"legend.miss": "缓存未命中",
			"legend.out": "输出",
			"legend.peak": "峰时",
			"legend.off": "谷时",
			"col.model": "模型",
			"col.calls": "调用",
			"col.miss": "未命中",
			"col.hit": "命中",
			"col.out": "输出",
			"col.cost": "花费",
			"col.share": "占比",
			"col.session": "会话",
			"col.tokens": "Tokens",
			"col.day": "日期",
			"note.footer": "花费由 token 数按 DeepSeek 官方价目表折算（峰时 2×，谷时 1×，周末全谷时）。v4-flash / v4-pro 已按官方迁移说明并入 flash 价。",
			"note.scope": "共 {sessions} 个会话，{artifacts} 个日志文件，{bytes} MiB，扫描耗时 {ms} ms。",
			"note.unpriced": "以下模型不在价目表内，已按 flash 谷时价估算：{models}",
			"note.failures": "{count} 个日志文件读取失败。",
			"empty": "还没有可统计的会话日志。",
			"scope.all": "全部会话"
		};
		const en = {
			"type.label": "Usage & Spend",
			"guide.title": "Usage & Spend",
			"guide.description": "Token usage, cache-hit rate, and spend at peak / off-peak rates",
			"header.chip": "Today {cost}",
			"header.chipAria": "Spent {cost} today — open the usage dashboard",
			"header.title": "Today {cost} ({tokens} tokens)",
			"state.loading": "Reading session logs…",
			"state.error": "Could not read usage: {message}",
			"state.retry": "Retry",
			"action.refresh": "Refresh",
			"action.refreshing": "Refreshing…",
			"peak.on": "peak",
			"peak.off": "off-peak",
			"peak.onHint": "Peak billing right now (double the off-peak rate)",
			"peak.offHint": "Off-peak billing right now",
			"metric.cost": "Total spend",
			"metric.tokens": "Total tokens",
			"metric.cacheHit": "Cache-hit rate",
			"metric.calls": "Model calls",
			"sections.trend": "Daily spend",
			"sections.tokens": "Daily tokens",
			"sections.models": "By model",
			"sections.sessions": "By session",
			"sections.workspaces": "By workspace",
			"sections.hours": "By UTC hour",
			"legend.hit": "cache hit",
			"legend.miss": "cache miss",
			"legend.out": "output",
			"legend.peak": "peak",
			"legend.off": "off-peak",
			"col.model": "Model",
			"col.calls": "Calls",
			"col.miss": "Miss",
			"col.hit": "Hit",
			"col.out": "Output",
			"col.cost": "Spend",
			"col.share": "Share",
			"col.session": "Session",
			"col.tokens": "Tokens",
			"col.day": "Day",
			"note.footer": "Spend is computed from token counts using DeepSeek's published rate card (peak 2×, off-peak 1×, weekends wholly off-peak). Legacy v4-flash / v4-pro ids are billed at the flash card per DeepSeek's migration note.",
			"note.scope": "{sessions} sessions, {artifacts} log files, {bytes} MiB, scanned in {ms} ms.",
			"note.unpriced": "Not in the price card, estimated at the flash off-peak card: {models}",
			"note.failures": "{count} log file(s) failed to read.",
			"empty": "No session logs to account for yet.",
			"scope.all": "all sessions"
		};

		/* ── styles ────────────────────────────────────────────────────────── */

		/*
		 * Compact scale for a narrow right-hand pane (the shell may hand this page
		 * as little as ~360-420 px): 12 px base type, 16 px metric values, 10-12 px
		 * paddings, a 14 px section rhythm and 320x104 charts. Nothing here sets a
		 * block min-width, and the root is an inline-size query container, so the
		 * panel can never push the pane wider than the shell made it: tables use a
		 * fixed layout and every long string ellipsizes.
		 */
		const CSS = `
.udsh-root { display: flex; flex-direction: column; gap: 14px; padding: 12px 12px 24px; font-size: 12px; line-height: 1.45; color: var(--dsw-alias-label-primary); container-type: inline-size; }
.udsh-head { display: flex; align-items: center; gap: 6px; }
.udsh-headTitle { flex: 1 1 auto; min-width: 0; font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.udsh-pill { display: inline-flex; align-items: center; gap: 4px; height: 18px; padding: 0 7px; border-radius: 9px; font-size: 10px; line-height: 1; white-space: nowrap; background: var(--dsw-alias-fill-l2); color: var(--dsw-alias-label-secondary); }
.udsh-pillPeak { background: color-mix(in srgb, #d97706 18%, transparent); color: #b45309; }
body[data-ds-dark-theme] .udsh-pillPeak { color: #fbbf24; }
.udsh-pillOff { background: color-mix(in srgb, #059669 16%, transparent); color: #047857; }
body[data-ds-dark-theme] .udsh-pillOff { color: #34d399; }
.udsh-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex: none; }
.udsh-btn { height: 22px; padding: 0 8px; border: none; border-radius: 11px; cursor: pointer; font: inherit; font-size: 11px; white-space: nowrap; background: var(--dsw-alias-fill-l2); color: var(--dsw-alias-label-secondary); }
.udsh-btn:hover { background: var(--dsw-alias-interactive-bg-hover); }
.udsh-btn[disabled] { opacity: .5; cursor: default; }
.udsh-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.udsh-metric { min-width: 0; padding: 8px 10px; border: .5px solid var(--dsw-alias-border-l4); border-radius: 10px; background: var(--dsw-alias-bg-layer-1); }
.udsh-metricLabel { font-size: 10px; color: var(--dsw-alias-label-tertiary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.udsh-metricValue { margin-top: 1px; font-size: 16px; font-weight: 600; letter-spacing: -.2px; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.udsh-metricSub { margin-top: 1px; font-size: 10px; color: var(--dsw-alias-label-caption); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.udsh-section { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.udsh-sectionTitle { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; color: var(--dsw-alias-label-secondary); }
.udsh-sectionTitle::after { content: ""; flex: 1; height: 1px; background: var(--dsw-alias-border-l4); }
.udsh-legend { display: flex; flex-wrap: wrap; gap: 8px; font-size: 10px; color: var(--dsw-alias-label-tertiary); }
.udsh-legendItem { display: inline-flex; align-items: center; gap: 4px; }
.udsh-swatch { width: 7px; height: 7px; border-radius: 2px; flex: none; }
.udsh-chart { display: block; width: 100%; height: auto; min-width: 0; overflow: visible; }
.udsh-chart text { font-size: 9px; fill: var(--dsw-alias-label-tertiary); font-variant-numeric: tabular-nums; }
.udsh-grid { stroke: var(--dsw-alias-border-l4); stroke-width: 1; }
.udsh-table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 11px; }
.udsh-table th { padding: 2px 4px; border-bottom: .5px solid var(--dsw-alias-border-l4); font-size: 10px; font-weight: 500; color: var(--dsw-alias-label-tertiary); text-align: right; white-space: nowrap; }
.udsh-table td { padding: 3px 4px; text-align: right; font-variant-numeric: tabular-nums; border-bottom: .5px solid color-mix(in srgb, var(--dsw-alias-border-l4) 55%, transparent); }
.udsh-table th:first-child, .udsh-table td:first-child { text-align: left; }
.udsh-table tr:last-child td { border-bottom: none; }
.udsh-table--model th:first-child, .udsh-table--model td:first-child { width: 30%; }
.udsh-table--wide th:first-child, .udsh-table--wide td:first-child { width: 46%; }
.udsh-name { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.udsh-sub { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; color: var(--dsw-alias-label-caption); }
.udsh-bar { display: block; flex: none; width: 100%; height: 3px; border-radius: 2px; background: var(--dsw-alias-fill-l2); overflow: hidden; }
.udsh-bar > i { display: block; height: 100%; }
.udsh-cost { display: flex; flex-direction: column; gap: 2px; }
.udsh-costValue { white-space: nowrap; }
.udsh-note { font-size: 10px; line-height: 1.45; color: var(--dsw-alias-label-caption); }
.udsh-warn { font-size: 10px; color: #b45309; }
body[data-ds-dark-theme] .udsh-warn { color: #fbbf24; }
.udsh-hint { font-size: 11px; color: var(--dsw-alias-label-caption); }
.udsh-chip { display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 8px; border: none; border-radius: 12px; cursor: pointer; font: inherit; font-size: 12px; font-variant-numeric: tabular-nums; background: transparent; color: var(--dsw-alias-label-tertiary); }
.udsh-chip:hover { background: var(--dsw-alias-interactive-bg-hover); color: var(--dsw-alias-label-secondary); }
.udsh-chip .udsh-dot { width: 6px; height: 6px; background: #22c55e; }
.udsh-chip[data-peak="on"] .udsh-dot { background: #ef4444; }
@container (max-width: 400px) { .udsh-metrics { grid-template-columns: minmax(0, 1fr); } }
`;

		const TAG_ID = "dsh-usage-dashboard/dashboard.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(TAG_ID) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "dsh-usage-dashboard";
			tag.dataset.pluginCss = TAG_ID;
			tag.textContent = CSS;
			document.head.appendChild(tag);
		}

		/* ── formatting ────────────────────────────────────────────────────── */

		const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
		const grouped = new Intl.NumberFormat("en-US");

		function count(value) {
			const number = typeof value === "number" && Number.isFinite(value) ? value : 0;
			return number >= 100000 ? compact.format(number) : grouped.format(Math.round(number));
		}

		function usd(value, digits) {
			const number = typeof value === "number" && Number.isFinite(value) ? value : 0;
			if (number === 0) return "$0.00";
			if (number < 0.01) return "$" + number.toFixed(4);
			return "$" + number.toFixed(digits === undefined ? 2 : digits);
		}

		function usdPrecise(value) {
			const number = typeof value === "number" && Number.isFinite(value) ? value : 0;
			if (number === 0) return "$0.0000";
			return "$" + number.toFixed(number < 1 ? 4 : 2);
		}

		/** Axis label: two decimals at most, so the tick gutter stays narrow. */
		function usdAxis(value) {
			const number = typeof value === "number" && Number.isFinite(value) ? value : 0;
			return "$" + (number >= 1 ? number.toFixed(2) : number.toFixed(3));
		}

		function percent(value) {
			const number = typeof value === "number" && Number.isFinite(value) ? value : 0;
			return (number * 100).toFixed(1) + "%";
		}

		function dayLabel(day) {
			return day.slice(5);
		}

		/** Local wall-clock stamp; `—` when the log carried no usable time. */
		function timeLabel(epochMs) {
			if (typeof epochMs !== "number" || epochMs <= 0) return "—";
			const at = new Date(epochMs);
			const pad = (value) => String(value).padStart(2, "0");
			return at.getFullYear() + "-" + pad(at.getMonth() + 1) + "-" + pad(at.getDate()) + " " + pad(at.getHours()) + ":" + pad(at.getMinutes());
		}

		const COLORS = {
			hit: "#4d6bfe",
			miss: "#f59e0b",
			out: "#10b981",
			peak: "#ef4444",
			off: "#22c55e"
		};

		/* ── data access ───────────────────────────────────────────────────── */

		const ENDPOINT = "/api/usage-dashboard/stats";
		const REFRESH_MS = 60000;
		const store = { value: null, error: null, promise: null, listeners: new Set(), timer: null };

		function notify() {
			for (const listener of [...store.listeners]) listener();
		}

		/**
		 * One stats request. The promise is shared through `store.promise` so a
		 * panel and the header chip mounting together issue a single fetch, and a
		 * resolved value notifies every listener exactly once.
		 *
		 * @param {boolean} force - append `?refresh=1` to bypass the host cache.
		 * @returns {Promise<object|null>} the payload, or null after an error.
		 */
		function fetchStats(force) {
			const url = force === true ? ENDPOINT + "?refresh=1" : ENDPOINT;
			return fetch(url, { credentials: "same-origin", headers: { accept: "application/json" } })
				.then((response) => {
					if (!response.ok) throw new Error("HTTP " + response.status);
					return response.json();
				})
				.then((value) => {
					if (value && value.error !== undefined) throw new Error(String(value.error));
					store.value = value;
					store.error = null;
					notify();
					return value;
				})
				.catch((error) => {
					store.error = error instanceof Error ? error.message : String(error);
					notify();
					return null;
				})
				.finally(() => {
					store.promise = null;
				});
		}

		/** Join the in-flight request when there is one, otherwise start it. */
		function ensure(force) {
			if (store.promise !== null) return store.promise;
			store.promise = fetchStats(force);
			return store.promise;
		}

		function subscribe(listener) {
			store.listeners.add(listener);
			if (store.value === null && store.promise === null) void ensure(false);
			return () => {
				store.listeners.delete(listener);
			};
		}

		function snapshot() {
			return store.value;
		}

		/**
		 * The namespace-bound translator, subscribing to locale changes so a
		 * language switch re-renders the panel. Binding here rather than asking
		 * the slot framework for a `t` keeps the whole surface reading from one
		 * dictionary regardless of how the seat is composed.
		 *
		 * @param ctx - the client context owning the locale service.
		 * @returns a translate function bound to this dashboard's namespace.
		 */
		function useTranslator(ctx) {
			const translate = React.useMemo(() => ctx.locale.bind(NS), [ctx]);
			const [, bump] = React.useState(0);
			React.useEffect(() => {
				const listener = () => bump((value) => value + 1);
				ctx.on("locale/change", listener);
				return () => ctx.off("locale/change", listener);
			}, [ctx]);
			return translate;
		}

		/**
		 * The store subscription plus the 60 s poll. `active === false` keeps the
		 * subscription (so the chip still repaints) but stops the timer.
		 *
		 * @param {boolean} [active] - whether this seat should drive the poll.
		 * @returns {{data: object|null, error: string|null, refresh: Function}} the
		 *   current snapshot and a force-refresh trigger.
		 */
		function useUsage(active) {
			const [, bump] = React.useState(0);
			React.useEffect(() => subscribe(() => bump((value) => value + 1)), []);
			React.useEffect(() => {
				if (active === false) return undefined;
				void ensure(false);
				store.timer = setInterval(() => void ensure(false), REFRESH_MS);
				return () => {
					if (store.timer !== null) clearInterval(store.timer);
					store.timer = null;
				};
			}, [active]);
			return { data: snapshot(), error: store.error, refresh: (force) => ensure(force !== false) };
		}

		/* ── small presentational pieces ───────────────────────────────────── */

		function Pill(props) {
			return h("span", { className: "udsh-pill " + (props.peak ? "udsh-pillPeak" : "udsh-pillOff"), title: props.title },
				h("span", { className: "udsh-dot" }),
				props.children);
		}

		/**
		 * One headline figure. `title` repeats the untruncated detail so a narrow
		 * card can ellipsize its sub-line without losing the number entirely.
		 */
		function Metric(props) {
			return h("div", { className: "udsh-metric", title: props.title },
				h("div", { className: "udsh-metricLabel" }, props.label),
				h("div", { className: "udsh-metricValue" }, props.value),
				props.sub === undefined ? null : h("div", { className: "udsh-metricSub" }, props.sub));
		}

		function Section(props) {
			return h("section", { className: "udsh-section" },
				h("div", { className: "udsh-sectionTitle" }, props.title),
				props.legend !== undefined ? props.legend : null,
				props.children);
		}

		function Legend(props) {
			return h("div", { className: "udsh-legend" },
				props.items.map((item) => h("span", { className: "udsh-legendItem", key: item.label },
					h("i", { className: "udsh-swatch", style: { background: item.color } }),
					item.label)));
		}

		/* ── charts ────────────────────────────────────────────────────────── */

		/*
		 * Chart geometry. The viewBox scales to the container width with its aspect
		 * ratio KEPT — a stretched viewBox would shear every axis label — so the box
		 * only gets shorter as the pane narrows, never distorted.
		 */
		const VIEW_W = 320;
		const VIEW_H = 104;
		const PAD_L = 32;
		const PAD_R = 4;
		const PAD_T = 8;
		const PAD_B = 16;
		const PLOT_W = VIEW_W - PAD_L - PAD_R;
		const PLOT_H = VIEW_H - PAD_T - PAD_B;
		/** Fit the whole chart inside the box without distortion. */
		const FIT = "xMidYMid meet";

		/**
		 * Column slots drawn on the plot's x axis.
		 *
		 * @param buckets - number of columns (may be 1 for a single active day).
		 * @returns the slot width in viewBox units.
		 */
		function slotWidth(buckets) {
			return PLOT_W / Math.max(buckets, 1);
		}

		/**
		 * A column's width, capped so one lone bucket does not become a slab.
		 *
		 * @param slot - the slot width.
		 * @returns the bar width in viewBox units.
		 */
		function barWidth(slot) {
			return Math.max(2, Math.min(16, slot - 2));
		}

		/** The three horizontal grid lines and their money ticks. */
		function gridTicks(max, y, format) {
			return [0, 0.5, 1].map((fraction) => {
				const value = max * fraction;
				return h("g", { key: fraction },
					h("line", { className: "udsh-grid", x1: PAD_L, x2: VIEW_W - PAD_R, y1: y(value), y2: y(value) }),
					h("text", { x: PAD_L - 4, y: y(value) + 3, textAnchor: "end" }, format(value)));
			});
		}

		/** Day labels every fourth column, always including the last one. */
		function dayLabels(days, slot) {
			return days.map((day, index) =>
				index % 4 === 0 || index === days.length - 1
					? h("text", {
						key: "l" + day.day,
						x: PAD_L + index * slot + slot / 2,
						y: VIEW_H - 5,
						textAnchor: "middle"
					}, dayLabel(day.day))
					: null);
		}

		/**
		 * Daily spend: one stacked column per day, peak over off-peak, with the
		 * axis labelled and a tooltip per column.
		 */
		function SpendChart(props) {
			const days = props.days;
			const max = days.reduce((value, day) => Math.max(value, day.cost), 0) || 1;
			const slot = slotWidth(days.length);
			const barW = barWidth(slot);
			const y = (value) => PAD_T + PLOT_H - (value / max) * PLOT_H;

			const bars = days.map((day, index) => {
				const x = PAD_L + index * slot + (slot - barW) / 2;
				const peakH = (day.peakCost / max) * PLOT_H;
				const offH = (day.offPeakCost / max) * PLOT_H;
				return h("g", { key: day.day },
					h("title", null, day.day + "  " + usdPrecise(day.cost) + "  (" + count(day.calls) + " calls)"),
					offH > 0 ? h("rect", {
						x: x, y: y(day.peakCost + day.offPeakCost), width: barW, height: Math.max(1, offH),
						fill: COLORS.off, rx: 1
					}) : null,
					peakH > 0 ? h("rect", {
						x: x, y: y(day.peakCost), width: barW, height: Math.max(1, peakH),
						fill: COLORS.peak, rx: 1
					}) : null);
			});

			return h("svg", {
				className: "udsh-chart",
				viewBox: "0 0 " + VIEW_W + " " + VIEW_H,
				preserveAspectRatio: FIT,
				role: "img"
			}, gridTicks(max, y, usdAxis).concat(bars, dayLabels(days, slot)));
		}

		/**
		 * Daily tokens: three stacked series per day (cache hit, cache miss,
		 * output) on one scale, so a day's prompt composition and its output are
		 * comparable at a glance.
		 */
		function TokenChart(props) {
			const days = props.days;
			const total = (day) => day.tokens.cacheHit + day.tokens.cacheMiss + day.tokens.output;
			const max = days.reduce((value, day) => Math.max(value, total(day)), 0) || 1;
			const slot = slotWidth(days.length);
			const barW = barWidth(slot);
			const y = (value) => PAD_T + PLOT_H - (value / max) * PLOT_H;

			const bars = days.map((day, index) => {
				const x = PAD_L + index * slot + (slot - barW) / 2;
				let cursor = PAD_T + PLOT_H;
				const slice = (value, color, key) => {
					const height = (value / max) * PLOT_H;
					if (height <= 0) return null;
					cursor -= height;
					return h("rect", { key: key, x: x, y: cursor, width: barW, height: Math.max(1, height), fill: color });
				};
				return h("g", { key: day.day },
					h("title", null, day.day + "  hit " + count(day.tokens.cacheHit) + "  miss " + count(day.tokens.cacheMiss) + "  out " + count(day.tokens.output)),
					slice(day.tokens.cacheHit, COLORS.hit, "hit"),
					slice(day.tokens.cacheMiss, COLORS.miss, "miss"),
					slice(day.tokens.output, COLORS.out, "out"));
			});

			return h("svg", {
				className: "udsh-chart",
				viewBox: "0 0 " + VIEW_W + " " + VIEW_H,
				preserveAspectRatio: FIT,
				role: "img"
			}, gridTicks(max, y, count).concat(bars, dayLabels(days, slot)));
		}

		/** Hour-of-day spend as a 24-slot column chart on the UTC clock. */
		function HourChart(props) {
			const hours = props.hours;
			const max = hours.reduce((value, row) => Math.max(value, row.cost), 0) || 1;
			const slot = slotWidth(24);
			const barW = Math.max(2, slot - 2);
			const peakHours = new Set([1, 2, 3, 6, 7, 8, 9]);
			const bars = hours.map((row, index) => {
				const height = (row.cost / max) * PLOT_H;
				return h("rect", {
					key: row.hour,
					x: PAD_L + index * slot + (slot - barW) / 2,
					y: PAD_T + PLOT_H - height,
					width: barW,
					height: Math.max(row.cost > 0 ? 1 : 0, height),
					fill: peakHours.has(row.hour) ? COLORS.peak : COLORS.off,
					rx: 1
				}, h("title", null, String(row.hour).padStart(2, "0") + ":00 UTC  " + usdPrecise(row.cost)));
			});
			const labels = [0, 6, 12, 18].map((hour) =>
				h("text", { key: hour, x: PAD_L + hour * slot + slot / 2, y: VIEW_H - 5, textAnchor: "middle" },
					String(hour).padStart(2, "0")));
			return h("svg", {
				className: "udsh-chart",
				viewBox: "0 0 " + VIEW_W + " " + VIEW_H,
				preserveAspectRatio: FIT,
				role: "img"
			}, bars.concat(labels));
		}

		/* ── tables ────────────────────────────────────────────────────────── */

		/** A right-aligned spend cell: the figure over a share bar. */
		function CostCell(props) {
			return h("td", null,
				h("div", { className: "udsh-cost" },
					h("span", { className: "udsh-costValue" }, usdPrecise(props.cost)),
					h("span", { className: "udsh-bar" },
						h("i", { style: { width: Math.max(0, Math.min(1, props.share)) * 100 + "%", background: COLORS.hit } }))));
		}

		function ModelTable(props) {
			const models = props.models;
			const t = props.t;
			const maxCost = models.reduce((value, row) => Math.max(value, row.cost), 0) || 1;
			return h("table", { className: "udsh-table udsh-table--model" },
				h("thead", null, h("tr", null,
					h("th", null, t("col.model")),
					h("th", null, t("col.calls")),
					h("th", null, t("col.hit")),
					h("th", null, t("col.miss")),
					h("th", null, t("col.out")),
					h("th", null, t("col.cost")))),
				h("tbody", null, models.map((row) =>
					h("tr", { key: row.model },
						h("td", null,
							h("span", { className: "udsh-name", title: row.label + " (" + row.model + ")" }, row.label),
							h("span", { className: "udsh-sub" }, row.model)),
						h("td", null, count(row.calls)),
						h("td", null, count(row.tokens.cacheHit)),
						h("td", null, count(row.tokens.cacheMiss)),
						h("td", null, count(row.tokens.output)),
						h(CostCell, { cost: row.cost, share: row.cost / maxCost })))));
		}

		function SessionTable(props) {
			const sessions = props.sessions.slice(0, props.limit === undefined ? 12 : props.limit);
			const t = props.t;
			return h("table", { className: "udsh-table udsh-table--wide" },
				h("thead", null, h("tr", null,
					h("th", null, t("col.session")),
					h("th", null, t("col.calls")),
					h("th", null, t("col.tokens")),
					h("th", null, t("col.cost")))),
				h("tbody", null, sessions.map((row) =>
					h("tr", { key: row.sessionId },
						h("td", null,
							h("span", { className: "udsh-name", title: row.title + "\n" + (row.cwd || "") }, row.title),
							h("span", { className: "udsh-sub" }, timeLabel(row.lastAt) + " · " + (row.workspace || ""))),
						h("td", null, count(row.calls)),
						h("td", null, count(row.tokens.cacheHit + row.tokens.cacheMiss + row.tokens.output)),
						h("td", null, usdPrecise(row.cost))))));
		}

		/** One row per workspace: same shape as a session row, no header. */
		function WorkspaceTable(props) {
			const workspaces = props.workspaces;
			return h("table", { className: "udsh-table udsh-table--wide" },
				h("tbody", null, workspaces.map((row) =>
					h("tr", { key: row.workspace },
						h("td", null, h("span", { className: "udsh-name", title: row.workspace }, row.workspace)),
						h("td", null, count(row.sessions)),
						h("td", null, count(row.tokens.cacheHit + row.tokens.cacheMiss + row.tokens.output)),
						h("td", null, usdPrecise(row.cost))))));
		}

		/* ── the tab body ──────────────────────────────────────────────────── */

		function DashboardBody(props) {
			const t = useTranslator(props.ctx);
			const usage = useUsage(true);
			const data = usage.data;

			if (data === null && usage.error !== null) {
				return h("div", { className: "udsh-root" },
					h("div", { className: "udsh-warn" }, t("state.error", { message: usage.error })),
					h("button", { className: "udsh-btn", onClick: () => void usage.refresh(true) }, t("state.retry")));
			}
			if (data === null) {
				return h("div", { className: "udsh-root" }, h("div", { className: "udsh-hint" }, t("state.loading")));
			}

			// Normalize the payload once, and tolerate a partial one. This seat is
			// session-scoped, and a seat that throws can cost the shell a whole
			// region, so an unexpected response degrades to empty sections.
			const n = (value) => (typeof value === "number" && Number.isFinite(value) ? value : 0);
			const totals = data.totals || {};
			const tokens = totals.tokens || {};
			const source = data.source || {};
			const days = Array.isArray(data.days) ? data.days : [];
			const hours = Array.isArray(data.hours) ? data.hours : [];
			const models = Array.isArray(data.models) ? data.models : [];
			const sessions = Array.isArray(data.sessions) ? data.sessions : [];
			const workspaces = Array.isArray(data.workspaces) ? data.workspaces : [];
			const unpriced = Array.isArray(data.unpricedModels) ? data.unpricedModels : [];
			const promptTokens = n(tokens.cacheHit) + n(tokens.cacheMiss);
			const totalTokens = promptTokens + n(tokens.output);
			const tokenBreakdown = "hit " + count(tokens.cacheHit) + " · miss " + count(tokens.cacheMiss) + " · out " + count(tokens.output);

			const metrics = h("div", { className: "udsh-metrics" },
				h(Metric, { label: t("metric.cost"), value: usd(totals.cost, 2), sub: usdPrecise(totals.cost) }),
				h(Metric, { label: t("metric.tokens"), value: count(totalTokens), sub: tokenBreakdown, title: tokenBreakdown }),
				h(Metric, { label: t("metric.cacheHit"), value: percent(totals.cacheHitShare), sub: count(promptTokens) + " prompt" }),
				h(Metric, { label: t("metric.calls"), value: count(totals.calls), sub: count(totals.sessions) + " " + t("scope.all") }));

			const notes = [];
			notes.push(t("note.scope", {
				sessions: count(totals.sessions),
				artifacts: count(source.artifacts),
				bytes: ((source.bytes || 0) / 1024 / 1024).toFixed(1),
				ms: count(source.elapsedMs)
			}));
			if (unpriced.length > 0) notes.push(t("note.unpriced", { models: unpriced.join(", ") }));
			if (source.failures !== undefined && source.failures.length > 0) notes.push(t("note.failures", { count: source.failures.length }));

			return h("div", { className: "udsh-root" },
				h("div", { className: "udsh-head" },
					h("span", { className: "udsh-headTitle", title: t("type.label") }, t("type.label")),
					h(Pill, { peak: data.peakNow, title: data.peakNow ? t("peak.onHint") : t("peak.offHint") }, data.peakNow ? t("peak.on") : t("peak.off")),
					h("button", {
						className: "udsh-btn",
						disabled: store.promise !== null,
						onClick: () => void usage.refresh(true)
					}, store.promise !== null ? t("action.refreshing") : t("action.refresh"))),
				metrics,
				days.length === 0
					? h("div", { className: "udsh-hint" }, t("empty"))
					: h(React.Fragment, null,
						h(Section, {
							title: t("sections.trend"),
							legend: h(Legend, { items: [{ label: t("legend.peak"), color: COLORS.peak }, { label: t("legend.off"), color: COLORS.off }] })
						}, h(SpendChart, { days: days })),
						h(Section, {
							title: t("sections.tokens"),
							legend: h(Legend, { items: [{ label: t("legend.hit"), color: COLORS.hit }, { label: t("legend.miss"), color: COLORS.miss }, { label: t("legend.out"), color: COLORS.out }] })
						}, h(TokenChart, { days: days })),
						h(Section, { title: t("sections.hours") }, h(HourChart, { hours: hours }))),
				models.length > 0 ? h(Section, { title: t("sections.models") }, h(ModelTable, { models: models, t: t })) : null,
				sessions.length > 0 ? h(Section, { title: t("sections.sessions") }, h(SessionTable, { sessions: sessions, t: t, limit: 12 })) : null,
				workspaces.length > 1 ? h(Section, { title: t("sections.workspaces") }, h(WorkspaceTable, { workspaces: workspaces })) : null,
				h("div", { className: "udsh-note" }, t("note.footer")),
				h("div", { className: "udsh-note" }, notes.join(" ")),
				h("div", { className: "udsh-note" }, timeLabel(data.generatedAt)));
		}

		/* ── the header entry point ────────────────────────────────────────── */

		/*
		 * Every seat this plugin takes is strict-session-scoped, and the shell
		 * rethrows a slot *assembly* error past the boundaries it owns — an
		 * ordinary render error in a slot entry is contained, but a bad one can
		 * take a whole region down with it. This guard costs one class and removes
		 * that possibility: anything thrown inside a seat is swallowed, the seat
		 * renders nothing, and the rest of the interface is untouched.
		 */
		class SlotGuard extends React.Component {
			constructor(props) {
				super(props);
				this.state = { failed: false };
			}

			static getDerivedStateFromError() {
				return { failed: true };
			}

			componentDidCatch(error) {
				console.error("usage-dashboard: seat hidden after a render error", error);
			}

			render() {
				return this.state.failed ? null : this.props.children;
			}
		}

		function HeaderChip(props) {
			const t = useTranslator(props.ctx);
			const usage = useUsage(true);
			const data = usage.data;
			// Never trust the payload's shape here: this seat renders inside the
			// conversation header, so a malformed response must degrade to the
			// inert chip rather than raise.
			const today = data !== null && data.today !== undefined && data.today !== null ? data.today : null;
			const tokens = today !== null && today.tokens !== undefined && today.tokens !== null ? today.tokens : null;
			const peak = data !== null && data.peakNow === true;
			const cost = today !== null && typeof today.cost === "number" ? today.cost : null;
			const label = cost === null ? "…" : usd(cost, cost < 1 ? 4 : 2);
			const reading = cost !== null && tokens !== null;
			return h("button", {
				type: "button",
				className: "udsh-chip",
				"data-peak": peak ? "on" : "off",
				"aria-label": t("header.chipAria", { cost: label }),
				title: reading ? t("header.title", {
					cost: usd(cost, 4),
					tokens: count(
						(typeof tokens.cacheHit === "number" ? tokens.cacheHit : 0) +
						(typeof tokens.cacheMiss === "number" ? tokens.cacheMiss : 0) +
						(typeof tokens.output === "number" ? tokens.output : 0)
					)
				}) : t("state.loading"),
				onClick: () => props.openTab()
			},
				h("span", { className: "udsh-dot" }),
				h("span", null, t("header.chip", { cost: label })));
		}

		/* ── plugin body ───────────────────────────────────────────────────── */

		const KIND = "usage-dashboard";
		const ID = "dsh-usage-dashboard";

		const inject = ["slots", "locale", "sidebarRightTabs", "sidebarRight"];

		/*
		 * TEMPORARY DIAGNOSTIC — remove once the blank-conversation defect is
		 * understood. The shell reports a slot crash through `console.error` and
		 * rethrows assembly errors globally, and neither reaches anywhere an agent
		 * can read. So the newest failure is mirrored into the window title and
		 * localStorage, both of which can be read from outside the page.
		 */
		function installDiagnostics() {
			// The check harness supplies a bare `window` stub, so every capability is
			// probed rather than assumed.
			if (typeof window === "undefined" || typeof window.addEventListener !== "function") return;
			if (typeof document === "undefined" || typeof setInterval !== "function") return;
			if (typeof console === "undefined" || typeof console.error !== "function") return;
			if (window.__udshDiag === true) return;
			window.__udshDiag = true;
			// The shell owns the window title and rewrites it, so the last line is
			// re-asserted on a timer; whichever sample wins, the value is readable
			// from outside the page with no browser tooling.
			window.__udshDiagLine = "DIAG ready " + new Date().toISOString();
			const record = (what, error) => {
				let detail = "";
				try {
					if (error !== undefined && error !== null) {
						detail = error.stack !== undefined ? String(error.stack) : String(error.message !== undefined ? error.message : error);
					}
				} catch (ignored) {
					detail = "(unprintable)";
				}
				window.__udshDiagLine = what + ": " + detail.split("\n").slice(0, 6).join(" ¶ ") + " ¶ at " + new Date().toISOString();
				try { window.localStorage.setItem("dsh-udsh-diag", window.__udshDiagLine.slice(0, 1800)); } catch (ignored) { }
			};
			window.addEventListener("error", (event) => record("window.error", event.error !== undefined && event.error !== null ? event.error : event.message));
			window.addEventListener("unhandledrejection", (event) => record("unhandledrejection", event.reason));
			const original = console.error.bind(console);
			console.error = (...args) => {
				record("console.error", args.map((arg) => (arg !== null && typeof arg === "object" && arg.stack !== undefined ? arg.stack : String(arg))).join(" "));
				original(...args);
			};
			setInterval(() => {
				try { document.title = "DIAG " + window.__udshDiagLine.slice(0, 150); } catch (ignored) { }
			}, 500);
		}

		function apply(ctx) {
			installDiagnostics();
			const t = ctx.locale.bind(NS);
			ctx.effect(() => ctx.locale.register(NS, "zh", zh), "usage-dashboard: zh dictionary");
			ctx.effect(() => ctx.locale.register(NS, "en", en), "usage-dashboard: en dictionary");

			ctx.effect(() => ctx.sidebarRightTabs.register({
				id: ID,
				kind: KIND,
				priority: "builtin",
				title: () => t("type.label"),
				guide: [{
					order: 40,
					title: () => t("guide.title"),
					description: () => t("guide.description"),
					icon: (iconProps) => h("svg", {
						width: iconProps.size === undefined ? 16 : iconProps.size,
						height: iconProps.size === undefined ? 16 : iconProps.size,
						viewBox: "0 0 16 16",
						fill: "none",
						"aria-hidden": "true",
						className: iconProps.className
					},
						h("path", {
							d: "M2 13.2V9.4M6 13.2V5.6M10 13.2V8M14 13.2V3",
							stroke: "currentColor",
							strokeWidth: "1.6",
							strokeLinecap: "round"
						}))
				}]
			}), "usage-dashboard: tab type");

			ctx.effect(() => ctx.slots.inject("sidebar.right.pane.tab", () => ctx.slots.register({
				name: "sidebar.right.pane.tab",
				key: ID
			}, (bodyProps) => h(SlotGuard, null, h(DashboardBody, { ctx: ctx, useTabInfo: bodyProps.useTabInfo })))), "usage-dashboard: tab body");

			ctx.effect(() => ctx.slots.inject("conversation.session.header.actions", () => ctx.slots.register({
				name: "conversation.session.header.actions",
				id: "usage-dashboard-chip",
				order: 30
			}, () => h(SlotGuard, null, h(HeaderChip, {
				ctx: ctx,
				openTab: () => ctx.sidebarRight.openTab(KIND)
			})))), "usage-dashboard: header chip");
		}

		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});
