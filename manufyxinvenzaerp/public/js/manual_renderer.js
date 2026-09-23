// Shared renderer for the app's manual pages.
//
// Extracted from the Material Planning manual when a second manual (Material Issue
// Plan) was added: the two differ only in their content, so duplicating ~500 lines
// of layout, scrollspy and CSS would have meant every later fix landing twice.
//
// A manual page supplies its own sections array plus the hero text:
//
//   manufyx_render_manual(page, {
//       kicker: "Material Issue Plan", heading: "...", intro: "...",
//       sections: [...],
//   });
//
// A section is {id, title, kicker, purpose, fields[], steps[], calcs[], examples[],
// notes[], buttons[]} -- every part optional. kind:"overview" renders the hero card,
// and only Material Planning's overview draws the flow diagram (set flow:false to
// leave it out).

function manufyx_render_manual(page, opts) {
	try {
		_mfx_render_manual_inner(page, opts);
	} catch (e) {
		// Same reasoning as the tree renderer -- see _mfx_render_error.
		_mfx_render_error(page, e);
		throw e;
	}
}

function _mfx_render_manual_inner(page, opts) {
	_mfx_inject_styles();

	let sections = opts.sections || [];
	let nav_html = sections.map(
		// No real "#..." href on purpose -- Frappe's router intercepts anchor
		// clicks with hash hrefs and tries to resolve them as a page route
		// (showing a "Page #mpm-... not found" dialog), even with
		// preventDefault() in our own handler below. Navigation is done purely
		// via the click handler + scrollIntoView instead.
		(s) => `<a href="javascript:void(0)" class="mpm-nav-link" data-id="${s.id}">${frappe.utils.escape_html(s.title)}</a>`
	).join("");

	let sections_html = sections.map(_mfx_render_section).join("");

	page.main.html(`
		<div class="mpm-root">
			<header class="mpm-hero">
				<div class="mpm-hero-kicker">${frappe.utils.escape_html(opts.kicker || "")}</div>
				<h1>${frappe.utils.escape_html(opts.heading || "")}</h1>
				<p>${opts.intro || ""}</p>
			</header>
			<div class="mpm-body">
				<nav class="mpm-nav">${nav_html}</nav>
				<main class="mpm-content">${sections_html}</main>
			</div>
		</div>
	`);

	_mfx_setup_scrollspy(page, sections);
}

// ─── Tree manual (ERP Manual — doctype-wise categories, each with its own
// tables/topics as sub-tabs) ─────────────────────────────────────────────────
//
//   manufyx_render_manual_tree(page, {
//       heading: "...", intro: "...", welcome: {title, body},
//       categories: [
//           { id: "material-planning", label: "Material Planning",
//             children: [ {id, title, kicker, purpose, fields, ...}, ... ] },
//           ...
//       ],
//   });
//
// A category with an empty children array is a soft "coming soon" placeholder --
// it still shows in the tree (so the intended shape is visible) but expanding it
// shows a one-line note instead of throwing on an empty list.
//
// One content pane, one thing shown at a time -- picking a leaf swaps the pane
// rather than scrolling a single long page, since a doctype-wise manual is meant
// to be looked something up in, not read start to finish like the walkthroughs.

function manufyx_render_manual_tree(page, opts) {
	try {
		_mfx_render_manual_tree_inner(page, opts);
	} catch (e) {
		// A manual that fails renders BLANK otherwise -- Frappe swallows the throw
		// and the user is left with an empty white page and no clue why. Put the
		// error where they will actually see it, and re-throw so it still reaches
		// the console for anyone with DevTools open.
		_mfx_render_error(page, e);
		throw e;
	}
}

function _mfx_render_error(page, e) {
	let msg = (e && (e.stack || e.message)) || String(e);
	try {
		page.main.html(
			'<div style="margin:24px;padding:20px;border:1px solid #C6462F;border-radius:10px;' +
				'background:#FBEAE6;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Arial,sans-serif">' +
				'<div style="font-weight:700;color:#C6462F;margin-bottom:8px">' +
				__("This manual page failed to render") +
				"</div>" +
				'<pre style="white-space:pre-wrap;font-size:12px;color:#4A4550;margin:0">' +
				frappe.utils.escape_html(msg) +
				"</pre></div>"
		);
	} catch (_) {
		// page.main itself is unusable -- nothing more we can do here.
	}
}

function _mfx_render_manual_tree_inner(page, opts) {
	_mfx_inject_styles();
	_mfx_inject_tree_styles();

	let categories = opts.categories || [];

	page.main.html(`
		<div class="mpm-root erpm-root">
			<header class="mpm-hero">
				<h1>${frappe.utils.escape_html(opts.heading || "")}</h1>
				<p>${opts.intro || ""}</p>
			</header>
			<div class="mpm-body erpm-body">
				<nav class="erpm-tree"></nav>
				<main class="mpm-content erpm-content"></main>
			</div>
		</div>
	`);

	let $tree = page.main.find(".erpm-tree");
	let $content = page.main.find(".erpm-content");

	function render_welcome() {
		let w = opts.welcome || {};
		$content.html(`
			<section class="mpm-card mpm-overview">
				<div class="mpm-kicker">${__("ERP Manual")}</div>
				<h2>${frappe.utils.escape_html(w.title || "")}</h2>
				<p class="mpm-purpose">${w.body || ""}</p>
			</section>
		`);
	}

	function select_child(cat, child) {
		$tree.find(".erpm-child-link").removeClass("active");
		$tree.find(`.erpm-child-link[data-cat="${cat.id}"][data-child="${child.id}"]`).addClass("active");
		if (!child._stub) {
			$content.html(_mfx_render_section(child));
			return;
		}
		$content.html(`
			<section class="mpm-card">
				<div class="mpm-kicker">${frappe.utils.escape_html(cat.label)}</div>
				<h2>${frappe.utils.escape_html(child.title)}</h2>
				<p class="mpm-purpose">${__("Not written up yet — this category is placed here to show where it will sit once it is.")}</p>
			</section>
		`);
	}

	function render_tree() {
		$tree.html(categories.map((cat) => {
			let children = cat.children && cat.children.length
				? cat.children
				: [{ id: "coming-soon", title: __("Coming Soon"), _stub: true }];
			return `
			<div class="erpm-cat" data-cat="${cat.id}">
				<div class="erpm-cat-label">
					<span class="erpm-cat-arrow">▸</span>
					<span>${frappe.utils.escape_html(cat.label)}</span>
				</div>
				<div class="erpm-children">
					${children.map((child) => `
						<a href="javascript:void(0)" class="erpm-child-link" data-cat="${cat.id}" data-child="${child.id}">
							${frappe.utils.escape_html(child.title)}
						</a>
					`).join("")}
				</div>
			</div>`;
		}).join(""));

		$tree.find(".erpm-cat-label").on("click", function () {
			let $cat_el = $(this).closest(".erpm-cat");
			let was_open = $cat_el.hasClass("open");
			$cat_el.toggleClass("open");
			// Opening a category with nothing shown yet also shows its first child --
			// otherwise clicking a category label does nothing visible on its own,
			// which reads as broken rather than as "now expand a sub-item".
			if (!was_open) {
				let cat = categories.find((c) => c.id === $cat_el.data("cat"));
				let first = (cat.children && cat.children[0]) || { id: "coming-soon", title: __("Coming Soon"), _stub: true };
				select_child(cat, first);
			}
		});
		$tree.find(".erpm-child-link").on("click", function (e) {
			e.stopPropagation();
			let cat_id = $(this).data("cat");
			let child_id = $(this).data("child");
			let cat = categories.find((c) => c.id === cat_id);
			let child = (cat.children || []).find((c) => c.id === child_id) || { id: child_id, title: __("Coming Soon"), _stub: true };
			$(this).closest(".erpm-cat").addClass("open");
			select_child(cat, child);
		});
	}

	render_tree();
	render_welcome();
}

function _mfx_render_section(s) {
	if (s.kind === "overview") {
		return `
		<section id="mpm-${s.id}" class="mpm-card mpm-overview">
			<div class="mpm-kicker">${frappe.utils.escape_html(s.kicker)}</div>
			<h2>${frappe.utils.escape_html(s.title)}</h2>
			<p class="mpm-purpose">${s.purpose}</p>
			${s.flow === false ? "" : _mfx_render_flow_diagram()}
		</section>`;
	}

	let parts = [];
	parts.push(`<div class="mpm-kicker">${frappe.utils.escape_html(s.kicker || "")}</div>`);
	parts.push(`<h2>${frappe.utils.escape_html(s.title)}</h2>`);
	if (s.purpose) parts.push(`<p class="mpm-purpose">${s.purpose}</p>`);

	if (s.fields && s.fields.length) {
		parts.push(`
			<h3>${s.kind === "glossary" ? __("Terms") : __("Fields")}</h3>
			<table class="mpm-field-table">
				<tbody>
					${s.fields.map((f) => `
						<tr>
							<td class="mpm-field-name">${frappe.utils.escape_html(f.name)}</td>
							<td class="mpm-field-note">${f.note}</td>
						</tr>
					`).join("")}
				</tbody>
			</table>
		`);
	}

	if (s.steps && s.steps.length) {
		parts.push(`
			<h3>${__("How It Works")}</h3>
			<ol class="mpm-steps">
				${s.steps.map((step) => `<li>${step}</li>`).join("")}
			</ol>
		`);
	}

	if (s.calcs && s.calcs.length) {
		parts.push(`
			<h3>${__("Worked Example")}</h3>
			<div class="mpm-calcs">
				${s.calcs.map(_mfx_render_calc).join("")}
			</div>
		`);
	}

	if (s.examples && s.examples.length) {
		parts.push(`
			<h3>${__("Examples")}</h3>
			<div class="mpm-examples">
				${s.examples.map((ex) => `
					<div class="mpm-example mpm-example-${ex.type}">
						<div class="mpm-example-icon">${ex.type === "do" ? "✓" : "✕"}</div>
						<div class="mpm-example-body">
							<div class="mpm-example-label">${frappe.utils.escape_html(ex.label)}</div>
							<div class="mpm-example-text">${ex.text}</div>
						</div>
					</div>
				`).join("")}
			</div>
		`);
	}

	if (s.buttons && s.buttons.length) {
		parts.push(`
			<h3>${__("Buttons")}</h3>
			<div class="mpm-buttons">
				${s.buttons.map((b) => `
					<div class="mpm-button-row">
						<span class="mpm-button-pill">${frappe.utils.escape_html(b.name)}</span>
						<span class="mpm-button-note">${b.note}</span>
					</div>
				`).join("")}
			</div>
		`);
	}

	if (s.notes && s.notes.length) {
		parts.push(`
			<div class="mpm-notes">
				${s.notes.map((n) => `<div class="mpm-note">${n}</div>`).join("")}
			</div>
		`);
	}

	return `<section id="mpm-${s.id}" class="mpm-card">${parts.join("\n")}</section>`;
}

function _mfx_render_calc(c) {
	let dim_rows = [];
	if (c.length !== undefined) dim_rows.push(["Length", c.length + " mm"]);
	if (c.width !== undefined) dim_rows.push(["Width", c.width + " mm"]);
	if (c.thickness !== undefined) dim_rows.push(["Thickness", c.thickness + " mm"]);
	dim_rows.push(["NOS", c.sec_qty]);
	dim_rows.push(["Unit Weight", c.unit_weight]);

	return `
	<div class="mpm-calc">
		<div class="mpm-calc-title">${frappe.utils.escape_html(c.title)}</div>
		<div class="mpm-calc-item">${frappe.utils.escape_html(c.item)} <span>· ${frappe.utils.escape_html(c.group)}</span></div>
		<table class="mpm-calc-dims">
			${dim_rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}
		</table>
		<div class="mpm-calc-formula">${c.formula}</div>
		<div class="mpm-calc-result">= ${c.result} Kg</div>
		${c.note ? `<div class="mpm-calc-note">${c.note}</div>` : ""}
	</div>`;
}

function _mfx_render_flow_diagram() {
	return `
	<div class="mpm-flow">
		<div class="mpm-flow-box mpm-flow-start">${__("Raw Materials")}</div>
		<div class="mpm-flow-arrow">↓ ${__("Check Stock Availability")}</div>
		<div class="mpm-flow-split">
			<div class="mpm-flow-box mpm-flow-good">${__("Available Raw Materials")}<span>${__("exact size, ready to reserve")}</span></div>
			<div class="mpm-flow-box mpm-flow-mid">${__("Material Mapping")}<span>${__("needs cutting, substitution, or excess reuse")}</span></div>
			<div class="mpm-flow-box mpm-flow-bad">${__("Unavailable Items")}<span>${__("nothing in stock")}</span></div>
		</div>
		<div class="mpm-flow-arrow">↓ ${__("grouped by item code")}</div>
		<div class="mpm-flow-box mpm-flow-mid">${__("Consolidate Item")}<span>${__("one line per item, ready to purchase")}</span></div>
		<div class="mpm-flow-arrow">↓ ${__("Create Material Request → Purchase Order → Purchase Receipt")}</div>
		<div class="mpm-flow-box mpm-flow-good">${__("Allocated back automatically")}<span>${__("into Available Raw Materials or Material Mapping")}</span></div>
	</div>`;
}

function _mfx_setup_scrollspy(page, sections) {
	let $links = page.main.find(".mpm-nav-link");

	$links.on("click", function (e) {
		e.preventDefault();
		let id = $(this).data("id");
		let $target = page.main.find("#mpm-" + id);
		if ($target.length) {
			$target[0].scrollIntoView({ behavior: "smooth", block: "start" });
		}
	});

	// Sections come from the caller rather than a global -- this file is loaded
	// app-wide (app_include_js), so a hardcoded MP_MANUAL_SECTIONS reference here
	// broke every OTHER manual page: that constant only exists once Material
	// Planning's own page script has been fetched by the router, which never
	// happens while viewing a different manual.
	let target_els = (sections || []).map((s) => page.main.find("#mpm-" + s.id)[0]).filter(Boolean);
	if (!target_els.length || !window.IntersectionObserver) return;

	let observer = new IntersectionObserver(
		(entries) => {
			entries.forEach((entry) => {
				if (entry.isIntersecting) {
					let id = entry.target.id.replace("mpm-", "");
					$links.removeClass("active");
					page.main.find(`.mpm-nav-link[data-id="${id}"]`).addClass("active");
				}
			});
		},
		{ root: null, rootMargin: "-15% 0px -70% 0px", threshold: 0 }
	);
	target_els.forEach((el) => observer.observe(el));
}

function _mfx_inject_styles() {
	if (document.getElementById("mpm-styles")) return;
	let style = document.createElement("style");
	style.id = "mpm-styles";
	style.innerHTML = `
		.mpm-root {
			--mpm-bg: #FBEDE8;
			--mpm-card-bg: #FFFFFF;
			--mpm-heading: #3B1730;
			--mpm-accent: #E8613C;
			--mpm-accent-soft: #FCE3D8;
			--mpm-text: #4A4550;
			--mpm-text-muted: #948C97;
			--mpm-good: #1F9254;
			--mpm-good-bg: #E7F6EE;
			--mpm-bad: #C6462F;
			--mpm-bad-bg: #FBEAE6;
			--mpm-border: #F0DDD5;
			background: var(--mpm-bg);
			min-height: 100%;
			margin: -15px -25px;
			padding: 0 0 60px 0;
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
			color: var(--mpm-text);
		}
		.mpm-hero {
			text-align: center;
			padding: 56px 20px 40px;
			max-width: 720px;
			margin: 0 auto;
		}
		.mpm-hero-kicker {
			text-transform: uppercase;
			letter-spacing: 2px;
			font-size: 12px;
			font-weight: 700;
			color: var(--mpm-accent);
			margin-bottom: 10px;
		}
		.mpm-hero h1 {
			font-family: Georgia, "Times New Roman", serif;
			font-weight: 700;
			font-size: 40px;
			color: var(--mpm-heading);
			margin: 0 0 14px;
		}
		.mpm-hero p {
			font-size: 15px;
			color: var(--mpm-text-muted);
			line-height: 1.6;
			margin: 0;
		}
		.mpm-body {
			display: flex;
			max-width: 1100px;
			margin: 0 auto;
			padding: 0 20px;
			gap: 32px;
			align-items: flex-start;
		}
		.mpm-nav {
			position: sticky;
			top: 20px;
			flex: 0 0 220px;
			display: flex;
			flex-direction: column;
			gap: 2px;
			background: var(--mpm-card-bg);
			border: 1px solid var(--mpm-border);
			border-radius: 12px;
			padding: 10px;
			max-height: calc(100vh - 40px);
			overflow-y: auto;
		}
		.mpm-nav-link {
			display: block;
			padding: 9px 12px;
			border-radius: 8px;
			font-size: 13px;
			font-weight: 500;
			color: var(--mpm-text);
			text-decoration: none;
			border-left: 3px solid transparent;
			transition: background .15s, color .15s;
		}
		.mpm-nav-link:hover {
			background: var(--mpm-accent-soft);
			color: var(--mpm-heading);
			text-decoration: none;
		}
		.mpm-nav-link.active {
			background: var(--mpm-accent-soft);
			color: var(--mpm-accent);
			border-left-color: var(--mpm-accent);
			font-weight: 700;
		}
		.mpm-content {
			flex: 1;
			min-width: 0;
			display: flex;
			flex-direction: column;
			gap: 24px;
		}
		.mpm-card {
			background: var(--mpm-card-bg);
			border: 1px solid var(--mpm-border);
			border-radius: 16px;
			padding: 32px 36px;
			box-shadow: 0 2px 10px rgba(59, 23, 48, 0.04);
			scroll-margin-top: 20px;
		}
		.mpm-kicker {
			text-transform: uppercase;
			letter-spacing: 1.5px;
			font-size: 11px;
			font-weight: 700;
			color: var(--mpm-accent);
			margin-bottom: 6px;
		}
		.mpm-card h2 {
			font-family: Georgia, "Times New Roman", serif;
			font-weight: 700;
			font-size: 26px;
			color: var(--mpm-heading);
			margin: 0 0 14px;
		}
		.mpm-card h3 {
			font-size: 14px;
			font-weight: 700;
			color: var(--mpm-heading);
			text-transform: uppercase;
			letter-spacing: .5px;
			margin: 26px 0 12px;
		}
		.mpm-purpose {
			font-size: 15px;
			line-height: 1.7;
			color: var(--mpm-text);
			margin: 0;
		}
		.mpm-field-table {
			width: 100%;
			border-collapse: collapse;
		}
		.mpm-field-table tr {
			border-top: 1px solid var(--mpm-border);
		}
		.mpm-field-table tr:first-child { border-top: none; }
		.mpm-field-table td {
			padding: 10px 0;
			vertical-align: top;
			font-size: 13.5px;
			line-height: 1.6;
		}
		.mpm-field-name {
			width: 240px;
			font-weight: 700;
			color: var(--mpm-heading);
			padding-right: 20px !important;
		}
		.mpm-field-note { color: var(--mpm-text); }
		.mpm-steps {
			margin: 0;
			padding-left: 22px;
			font-size: 14px;
			line-height: 1.8;
			color: var(--mpm-text);
		}
		.mpm-steps li { margin-bottom: 6px; }
		.mpm-calcs {
			display: flex;
			flex-direction: column;
			gap: 16px;
		}
		.mpm-calc {
			background: #fffaf7;
			border: 1.5px dashed var(--mpm-accent);
			border-radius: 12px;
			padding: 18px 20px;
		}
		.mpm-calc-title {
			font-weight: 700;
			font-size: 13.5px;
			color: var(--mpm-heading);
			margin-bottom: 8px;
		}
		.mpm-calc-item {
			font-size: 13px;
			font-weight: 600;
			color: var(--mpm-accent);
			margin-bottom: 10px;
		}
		.mpm-calc-item span { font-weight: 400; color: var(--mpm-text-muted); }
		.mpm-calc-dims {
			border-collapse: collapse;
			margin-bottom: 12px;
		}
		.mpm-calc-dims td {
			font-size: 12.5px;
			padding: 3px 14px 3px 0;
			color: var(--mpm-text);
		}
		.mpm-calc-dims td:first-child { color: var(--mpm-text-muted); }
		.mpm-calc-formula {
			font-family: "SFMono-Regular", Consolas, Menlo, monospace;
			font-size: 12.5px;
			line-height: 1.6;
			color: var(--mpm-text);
			background: var(--mpm-accent-soft);
			border-radius: 8px;
			padding: 10px 12px;
			margin-bottom: 10px;
		}
		.mpm-calc-result {
			font-size: 18px;
			font-weight: 700;
			color: var(--mpm-good);
		}
		.mpm-calc-note {
			margin-top: 10px;
			font-size: 12.5px;
			line-height: 1.6;
			color: var(--mpm-text-muted);
			font-style: italic;
		}
		.mpm-examples {
			display: flex;
			flex-direction: column;
			gap: 14px;
		}
		.mpm-example {
			display: flex;
			gap: 14px;
			padding: 16px 18px;
			border-radius: 12px;
			align-items: flex-start;
		}
		.mpm-example-do { background: var(--mpm-good-bg); }
		.mpm-example-dont { background: var(--mpm-bad-bg); }
		.mpm-example-icon {
			flex: 0 0 26px;
			width: 26px;
			height: 26px;
			border-radius: 50%;
			display: flex;
			align-items: center;
			justify-content: center;
			font-weight: 700;
			font-size: 14px;
			color: #fff;
			margin-top: 1px;
		}
		.mpm-example-do .mpm-example-icon { background: var(--mpm-good); }
		.mpm-example-dont .mpm-example-icon { background: var(--mpm-bad); }
		.mpm-example-label {
			font-weight: 700;
			font-size: 13.5px;
			margin-bottom: 4px;
		}
		.mpm-example-do .mpm-example-label { color: var(--mpm-good); }
		.mpm-example-dont .mpm-example-label { color: var(--mpm-bad); }
		.mpm-example-text {
			font-size: 13.5px;
			line-height: 1.65;
			color: var(--mpm-text);
		}
		.mpm-buttons {
			display: flex;
			flex-direction: column;
			gap: 10px;
		}
		.mpm-button-row {
			display: flex;
			align-items: flex-start;
			gap: 14px;
			font-size: 13.5px;
			line-height: 1.6;
		}
		.mpm-button-pill {
			flex: 0 0 auto;
			white-space: nowrap;
			background: var(--mpm-heading);
			color: #fff;
			font-size: 12px;
			font-weight: 600;
			padding: 5px 12px;
			border-radius: 20px;
		}
		.mpm-button-note { color: var(--mpm-text); padding-top: 3px; }
		.mpm-notes { margin-top: 22px; display: flex; flex-direction: column; gap: 10px; }
		.mpm-note {
			font-size: 13px;
			line-height: 1.6;
			color: var(--mpm-heading);
			background: var(--mpm-accent-soft);
			border-radius: 10px;
			padding: 12px 16px;
		}
		.mpm-flow {
			margin-top: 28px;
			display: flex;
			flex-direction: column;
			align-items: center;
			gap: 6px;
		}
		.mpm-flow-box {
			background: #fff;
			border: 1.5px solid var(--mpm-border);
			border-radius: 12px;
			padding: 12px 18px;
			text-align: center;
			font-weight: 700;
			font-size: 13.5px;
			color: var(--mpm-heading);
			min-width: 220px;
		}
		.mpm-flow-box span {
			display: block;
			font-weight: 400;
			font-size: 11.5px;
			color: var(--mpm-text-muted);
			margin-top: 3px;
		}
		.mpm-flow-start { background: var(--mpm-heading); color: #fff; }
		.mpm-flow-good { border-color: var(--mpm-good); background: var(--mpm-good-bg); }
		.mpm-flow-mid { border-color: var(--mpm-accent); background: var(--mpm-accent-soft); }
		.mpm-flow-bad { border-color: var(--mpm-bad); background: var(--mpm-bad-bg); }
		.mpm-flow-arrow {
			font-size: 12px;
			color: var(--mpm-text-muted);
			font-weight: 600;
			margin: 2px 0;
		}
		.mpm-flow-split {
			display: flex;
			gap: 14px;
			flex-wrap: wrap;
			justify-content: center;
		}
		@media (max-width: 900px) {
			.mpm-body { flex-direction: column; }
			.mpm-nav { position: static; flex: none; width: 100%; flex-direction: row; overflow-x: auto; max-height: none; }
		}
	`;
	document.head.appendChild(style);
}

function _mfx_inject_tree_styles() {
	if (document.getElementById("erpm-styles")) return;
	let style = document.createElement("style");
	style.id = "erpm-styles";
	style.innerHTML = `
		.erpm-body { align-items: flex-start; }
		.erpm-tree {
			position: sticky;
			top: 20px;
			flex: 0 0 260px;
			background: var(--mpm-card-bg);
			border: 1px solid var(--mpm-border);
			border-radius: 12px;
			padding: 10px;
			max-height: calc(100vh - 40px);
			overflow-y: auto;
		}
		.erpm-cat { margin-bottom: 2px; }
		.erpm-cat-label {
			display: flex;
			align-items: center;
			gap: 8px;
			padding: 9px 10px;
			border-radius: 8px;
			font-size: 13px;
			font-weight: 700;
			color: var(--mpm-heading);
			cursor: pointer;
			user-select: none;
		}
		.erpm-cat-label:hover { background: var(--mpm-accent-soft); }
		.erpm-cat-arrow {
			display: inline-block;
			width: 10px;
			color: var(--mpm-accent);
			transition: transform .15s;
		}
		.erpm-cat.open > .erpm-cat-label .erpm-cat-arrow { transform: rotate(90deg); }
		.erpm-children {
			display: none;
			flex-direction: column;
			padding-left: 22px;
		}
		.erpm-cat.open > .erpm-children { display: flex; }
		.erpm-child-link {
			display: block;
			padding: 7px 10px;
			border-radius: 6px;
			font-size: 12.5px;
			color: var(--mpm-text);
			text-decoration: none;
			border-left: 2px solid transparent;
		}
		.erpm-child-link:hover { background: var(--mpm-accent-soft); color: var(--mpm-heading); text-decoration: none; }
		.erpm-child-link.active {
			background: var(--mpm-accent-soft);
			color: var(--mpm-accent);
			border-left-color: var(--mpm-accent);
			font-weight: 700;
		}
		.erpm-content { min-height: 300px; }
		@media (max-width: 900px) {
			.erpm-tree { position: static; flex: none; width: 100%; max-height: none; }
		}
	`;
	document.head.appendChild(style);

}

// Publish the two entry points explicitly.
//
// Loaded as a plain <script> these are already globals, so this is redundant --
// but this file is now pulled in through manufyxinvenzaerp.bundle.js, and esbuild
// wraps a bundle's contents in its own scope, where a top-level `function` is NOT
// a global and every manual page would fail its "renderer not loaded" guard.
// Assigning to window works identically under both loading modes.
window.manufyx_render_manual = manufyx_render_manual;
window.manufyx_render_manual_tree = manufyx_render_manual_tree;
