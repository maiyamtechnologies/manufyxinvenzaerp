// Data Works
//
// One-time go-live clean-up: delete the transactions and test data. Each button shows what it
// will do first, then asks for the site name. The work runs in the background and the log below
// follows it.

frappe.pages["data-works"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Data Works"),
		single_column: true,
	});
	new DataWorks(page);
};

const API = "manufyxinvenzaerp.data_works.engine.";

class DataWorks {
	constructor(page) {
		this.page = page;
		this.offset = 0;
		this.timer = null;
		this.$body = $('<div style="padding:4px 0 20px">').appendTo(page.main);
		this.load();
	}

	load() {
		frappe.call({ method: API + "get_state" }).then((r) => {
			this.state = r.message;
			this.render();
			if (this.state.status.state === "running") this.follow();
		});
	}

	render() {
		const s = this.state;
		this.$body.html(`
			<div class="text-muted" style="font-size:12px;margin-bottom:14px">
				${__("Each button shows what it will do, then asks you to type the site name. Take a backup first (Run everything does it for you).")}
			</div>
			<div class="dw-buttons" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px"></div>
			<div class="dw-status" style="margin-bottom:6px;font-weight:600"></div>
			<pre class="dw-log" style="min-height:160px;max-height:420px;overflow:auto;background:var(--control-bg);padding:10px;border-radius:6px;font-size:12px"></pre>`);
		const $b = this.$body.find(".dw-buttons");
		const add = (key, label, cls) =>
			$(`<button class="btn btn-sm ${cls}">${label}</button>`)
				.appendTo($b)
				.on("click", () => this.start(key, label));
		add("backup", __("Back up now"), "btn-default");
		s.steps.forEach((x) => add(x.step, __(x.label), "btn-default"));
		add("all", __("Run everything"), "btn-danger");
		this.show_status(s.status);
	}

	start(key, label) {
		const go = (lines, title) => {
			const d = new frappe.ui.Dialog({
				title: title,
				fields: [
					{ fieldtype: "HTML", fieldname: "what" },
					{
						fieldtype: "Data",
						fieldname: "site",
						label: __("Type the site name to confirm"),
						description: this.state.site,
						reqd: 1,
					},
				],
				primary_action_label: __("Run"),
				primary_action: (v) => {
					frappe
						.call({ method: API + "run", args: { step: key, confirm_site: v.site } })
						.then(() => {
							d.hide();
							this.offset = 0;
							this.$body.find(".dw-log").text("");
							this.follow();
						});
				},
			});
			d.fields_dict.what.$wrapper.html(
				`<div style="max-height:260px;overflow:auto;font-size:12px">${lines
					.map((l) => `<div>${frappe.utils.escape_html(l)}</div>`)
					.join("")}</div>`
			);
			d.show();
		};
		if (key === "backup") return go([__("Takes a database backup into the site's backups folder.")], label);
		frappe.call({ method: API + "preview", args: { step: key } }).then((r) => go(r.message.lines, r.message.title));
	}

	follow() {
		clearInterval(this.timer);
		const tick = () =>
			frappe.call({ method: API + "get_log", args: { offset: this.offset }, freeze: false }).then((r) => {
				const m = r.message;
				const $log = this.$body.find(".dw-log");
				if (m.lines.length) {
					$log.append(document.createTextNode(m.lines.join("\n") + "\n"));
					$log.scrollTop($log[0].scrollHeight);
				}
				this.offset = m.next;
				this.show_status(m.status);
				if (m.status.state !== "running") clearInterval(this.timer);
			});
		tick();
		this.timer = setInterval(tick, 2000);
	}

	show_status(st) {
		const colour = { running: "orange", done: "green", failed: "red", idle: "gray" }[st.state] || "gray";
		this.$body
			.find(".dw-status")
			.html(`<span class="indicator-pill ${colour}">${st.state}</span> ${st.step ? frappe.utils.escape_html(st.step) : ""}`);
	}
}
