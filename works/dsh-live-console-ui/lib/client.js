window.__ModuleLoader__.load({
	id: "dsh-live-console-ui",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

		const React = require("react");
		const h = React.createElement;

		/* A compact header action that opens the external console page. */
		const CSS = `
.dsh-live-console-open { display: inline-flex; align-items: center; gap: 4px; height: 24px; padding: 0 8px; border: none; border-radius: 12px; background: transparent; color: var(--dsw-alias-label-tertiary); font: inherit; font-size: 12px; white-space: nowrap; cursor: pointer; }
.dsh-live-console-open:hover { background: var(--dsw-alias-interactive-bg-hover); color: var(--dsw-alias-label-secondary); }
.dsh-live-console-open:disabled { opacity: .5; cursor: default; }
.dsh-live-console-icon { font-size: 12px; line-height: 1; letter-spacing: -.5px; }
`;
		const TAG_ID = "dsh-live-console/open-button.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(TAG_ID) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "dsh-live-console";
			tag.dataset.pluginCss = TAG_ID;
			tag.textContent = CSS;
			document.head.appendChild(tag);
		}

		const URL_ENDPOINT = "/api/live-console/url";

		/**
		 * Ask the host for the capability-carrying console URL, then hand it to the
		 * Electron shell through `window.open` (the shipped window-open handler
		 * forwards absolute http(s) URLs to the default browser).
		 */
		async function openConsole() {
			try {
				const response = await fetch(URL_ENDPOINT, {
					credentials: "same-origin",
					headers: { accept: "application/json" },
				});
				if (!response.ok) throw new Error("HTTP " + response.status);
				const body = await response.json();
				if (body === null || typeof body !== "object" || typeof body.url !== "string" || body.url.length === 0) {
					throw new Error("the host returned no console URL");
				}
				window.open(body.url, "_blank", "noopener,noreferrer");
			} catch (error) {
				try {
					console.error("live-console: could not open the console", error);
				} catch {
					/* logging must never escalate */
				}
			}
		}

		function ConsoleButton() {
			return h(
				"button",
				{
					type: "button",
					className: "dsh-live-console-open",
					title: "打开 DSH Live Console（日志 / 进度 / 花费）",
					"aria-label": "打开 DSH Live Console",
					onClick: openConsole,
				},
				h("span", { className: "dsh-live-console-icon", "aria-hidden": "true" }, "▤"),
				h("span", null, "控制台"),
			);
		}

		const inject = ["slots"];

		/**
		 * Register one header action in every conversation header.
		 * @param {any} ctx - the client context.
		 */
		function apply(ctx) {
			ctx.effect(
				() =>
					ctx.slots.inject("conversation.session.header.actions", () =>
						ctx.slots.register(
							{
								name: "conversation.session.header.actions",
								id: "live-console-open",
								order: 35,
							},
							ConsoleButton,
						),
					),
				"live-console: open console button",
			);
		}

		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	},
});
