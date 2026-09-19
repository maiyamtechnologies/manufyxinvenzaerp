// Helpers for driving Frappe desk forms the way a user does: type into the field,
// pick from the link dropdown, click the grid cell, press the toolbar buttons.
//
// Values are always entered through the controls (never frm.set_value), so the same
// client scripts, fetches and validations a user triggers run here too. Reading state
// back (cur_frm.doc, frappe.db) is done through the page, which is only observation.

const { expect } = require("@playwright/test");

const BASE_URL = process.env.FRAPPE_URL || "http://127.0.0.1:8000";

// ── session ───────────────────────────────────────────────────────────────────

/** Log in with FRAPPE_SID (an existing session cookie) or FRAPPE_USER / FRAPPE_PASSWORD. */
async function login(page) {
	const host = new URL(BASE_URL).hostname;
	if (process.env.FRAPPE_SID) {
		await page.context().addCookies([
			{ name: "sid", value: process.env.FRAPPE_SID, domain: host, path: "/", httpOnly: true },
		]);
	} else {
		const user = process.env.FRAPPE_USER || "Administrator";
		const pwd = process.env.FRAPPE_PASSWORD;
		if (!pwd) throw new Error("Set FRAPPE_PASSWORD (or FRAPPE_SID) to log in.");
		const r = await page.request.post(`${BASE_URL}/api/method/login`, {
			form: { usr: user, pwd },
		});
		expect(r.ok(), `login as ${user}`).toBeTruthy();
	}
	await page.goto(`${BASE_URL}/app`);
	await page.waitForFunction(() => window.frappe && frappe.session && frappe.session.user !== "Guest", null, {
		timeout: 30000,
	});
}

// ── server calls from the page (setup and read-back only) ────────────────────

/** frappe.call from inside the page, so the session and CSRF token are the user's own. */
async function call(page, method, args = {}) {
	const r = await page.evaluate(
		async ({ method, args }) => {
			const body = new URLSearchParams();
			for (const [k, v] of Object.entries(args)) {
				body.append(k, typeof v === "string" ? v : JSON.stringify(v));
			}
			const res = await fetch(`/api/method/${method}`, {
				method: "POST",
				headers: {
					"X-Frappe-CSRF-Token": frappe.csrf_token,
					Accept: "application/json",
					"Content-Type": "application/x-www-form-urlencoded",
				},
				body,
			});
			const data = await res.json().catch(() => ({}));
			if (!res.ok) {
				let msgs = [];
				try {
					msgs = JSON.parse(data._server_messages || "[]").map((m) => JSON.parse(m).message);
				} catch (e) {}
				return { __error: `${res.status} ${data.exc_type || ""}: ${msgs.join(" | ") || data.exception || ""}` };
			}
			return { message: data.message };
		},
		{ method, args }
	);
	if (r.__error) throw new Error(`${method} failed: ${r.__error.replace(/<[^>]+>/g, "")}`);
	return r.message;
}

async function getValue(page, doctype, filters, fieldname) {
	const r = await call(page, "frappe.client.get_value", { doctype, filters, fieldname });
	if (!r) return undefined;
	return Array.isArray(fieldname) ? r : r[fieldname];
}

async function getDoc(page, doctype, name) {
	return call(page, "frappe.client.get", { doctype, name });
}

async function exists(page, doctype, name) {
	return Boolean(await getValue(page, doctype, { name }, "name"));
}

// ── navigation and waits ─────────────────────────────────────────────────────

async function waitIdle(page, extra = 300) {
	// Frappe shows a freeze overlay for long calls and keeps an ajax counter.
	await page.waitForFunction(
		() => !document.querySelector(".freeze:not(.hide)") && !(window.frappe && frappe.request && frappe.request.ajax_count > 0),
		null,
		{ timeout: 120000 }
	);
	await page.waitForTimeout(extra);
}

async function openForm(page, doctype, name) {
	const slug = doctype.toLowerCase().replace(/ /g, "-");
	await page.goto(`${BASE_URL}/app/${slug}/${name ? encodeURIComponent(name) : "new"}`);
	await page.waitForFunction(
		(dt) => window.cur_frm && cur_frm.doctype === dt && cur_frm.fields_dict && cur_frm.layout,
		doctype,
		{ timeout: 60000 }
	);
	await waitIdle(page, 800);
}

async function docValue(page, fieldname) {
	return page.evaluate((f) => cur_frm.doc[f], fieldname);
}

async function docName(page) {
	return page.evaluate(() => cur_frm.doc.name);
}

// ── field entry ──────────────────────────────────────────────────────────────

function control(page, fieldname) {
	return page.locator(`.form-layout .frappe-control[data-fieldname="${fieldname}"]:visible`).first();
}

/** Make the tab that holds a field active, so the field is visible and clickable. */
async function showField(page, fieldname) {
	await page.evaluate((f) => {
		const field = cur_frm.fields_dict[f];
		if (!field) throw new Error("No field " + f);
		const tab = field.tab || (field.section && field.section.tab);
		if (tab && tab.set_active) tab.set_active();
		if (field.section && field.section.collapse) field.section.collapse(false);
	}, fieldname);
	await page.waitForTimeout(200);
}

/** Pick `value` from an open awesomplete dropdown under `scope`, or fail. */
async function pickFromDropdown(page, scope, value) {
	// Frappe's awesomplete renders options as div[role=option] (li on older versions).
	const list = scope.locator("ul[role='listbox'] [role='option'], ul[role='listbox'] li");
	await list.first().waitFor({ state: "visible", timeout: 15000 });
	const exact = list.filter({ has: page.locator(`strong:text-is("${value}")`) });
	await exact.first().waitFor({ state: "visible", timeout: 15000 });
	await exact.first().click();
}

/**
 * Type a value into a form field the way a user does. Link fields pick the exact
 * value from the dropdown; Check fields are clicked; Select fields are chosen.
 */
async function setField(page, fieldname, value) {
	await showField(page, fieldname);
	const df = await page.evaluate((f) => {
		const d = cur_frm.fields_dict[f].df;
		return { fieldtype: d.fieldtype };
	}, fieldname);
	const ctl = control(page, fieldname);
	await ctl.scrollIntoViewIfNeeded();

	if (df.fieldtype === "Check") {
		const box = ctl.locator("input[type='checkbox']");
		if ((await box.isChecked()) !== Boolean(value)) await box.click();
	} else if (df.fieldtype === "Select") {
		await ctl.locator("select").selectOption(String(value));
	} else if (df.fieldtype === "Link") {
		const input = ctl.locator("input");
		await input.click();
		await input.fill("");
		await input.pressSequentially(String(value), { delay: 20 });
		await pickFromDropdown(page, ctl, String(value));
		await input.blur();
	} else if (["Small Text", "Text", "Long Text"].includes(df.fieldtype)) {
		await ctl.locator("textarea").fill(String(value));
		await ctl.locator("textarea").blur();
	} else {
		const input = ctl.locator("input");
		await input.click();
		await input.fill(String(value));
		await input.press("Tab");
	}
	await waitIdle(page);
	if (df.fieldtype === "Link" || df.fieldtype === "Select" || df.fieldtype === "Data") {
		await expect.poll(() => docValue(page, fieldname), { message: `${fieldname} = ${value}` }).toBe(String(value));
	}
}

// ── child tables ─────────────────────────────────────────────────────────────

function gridRow(page, table, idx) {
	return page.locator(`.frappe-control[data-fieldname="${table}"] .grid-body .grid-row[data-idx="${idx}"]`).first();
}

async function gridRowCount(page, table) {
	return page.evaluate((t) => (cur_frm.doc[t] || []).length, table);
}

async function gridAddRow(page, table) {
	await showField(page, table);
	const before = await gridRowCount(page, table);
	const ctl = page.locator(`.frappe-control[data-fieldname="${table}"]`).first();
	await ctl.locator(".grid-add-row").first().click();
	await expect.poll(() => gridRowCount(page, table)).toBe(before + 1);
	return before + 1;
}

/** Type into a grid cell. Clicking the static cell turns the row editable, as for a user. */
async function gridSet(page, table, idx, fieldname, value) {
	const row = gridRow(page, table, idx);
	await row.scrollIntoViewIfNeeded();
	const cell = row.locator(`.grid-static-col[data-fieldname="${fieldname}"]`).first();
	await cell.click();
	const input = row.locator(`.grid-static-col[data-fieldname="${fieldname}"] input, .grid-static-col[data-fieldname="${fieldname}"] select`).first();
	await input.waitFor({ state: "visible", timeout: 10000 });
	const tag = await input.evaluate((el) => el.tagName);
	const fieldtype = await page.evaluate(
		({ t, f }) => frappe.meta.get_docfield(cur_frm.fields_dict[t].grid.doctype, f).fieldtype,
		{ t: table, f: fieldname }
	);
	if (tag === "SELECT") {
		await input.selectOption(String(value));
	} else if (fieldtype === "Link") {
		await input.fill("");
		await input.pressSequentially(String(value), { delay: 20 });
		await pickFromDropdown(page, row, String(value));
	} else if (fieldtype === "Check") {
		if ((await input.isChecked()) !== Boolean(value)) await input.click();
	} else {
		await input.fill(String(value));
		// Blur rather than Tab: Tab out of the last cell makes Frappe add a new row.
		await input.dispatchEvent("change");
		await input.evaluate((el) => el.blur());
	}
	await waitIdle(page);
}

async function gridValue(page, table, idx, fieldname) {
	return page.evaluate(
		({ t, i, f }) => ((cur_frm.doc[t] || [])[i - 1] || {})[f],
		{ t: table, i: idx, f: fieldname }
	);
}

// ── toolbar ──────────────────────────────────────────────────────────────────

async function save(page) {
	await page.keyboard.press("Control+s");
	await waitIdle(page, 800);
	await expectNoError(page, "save");
	await expect.poll(() => page.evaluate(() => !cur_frm.is_dirty() && !cur_frm.is_new())).toBeTruthy();
}

/** Submit through the primary button and the "Permanently Submit" confirmation. */
async function submit(page) {
	await page.locator(".page-actions .primary-action:visible").first().click();
	const yes = page.locator(".modal:visible .btn-primary:has-text('Yes')");
	await yes.first().waitFor({ state: "visible", timeout: 15000 });
	await yes.first().click();
	await waitIdle(page, 1000);
	await expectNoError(page, "submit");
	await expect.poll(() => page.evaluate(() => cur_frm.doc.docstatus), { timeout: 60000 }).toBe(1);
}

/** Click a custom button, optionally inside a dropdown group ("Create", "Transfer" ...). */
async function clickButton(page, label, group) {
	if (group) {
		const grp = page.locator(`.inner-group-button[data-label="${encodeURIComponent(group)}"] button, .inner-group-button:has(button:text-is("${group}")) button`).first();
		await grp.click();
		const item = page.locator(`.inner-group-button .dropdown-menu:visible .dropdown-item:text-is("${label}")`).first();
		await item.click();
	} else {
		await page.locator(`.page-actions button:text-is("${label}"):visible, .form-inner-toolbar button:text-is("${label}"):visible, .frappe-control button:text-is("${label}"):visible`).first().click();
	}
	await waitIdle(page, 800);
}

/** Whether the form currently offers a custom button (inside `group` when given). */
async function hasButton(page, label, group) {
	return page.evaluate(
		({ label, group }) => {
			const g = group ? cur_frm.custom_buttons && cur_frm.page.get_inner_group_button(__(group)) : null;
			if (group) {
				return Boolean(
					g && g.find(".dropdown-item").filter((i, e) => e.innerText.trim() === label).length
				);
			}
			return Boolean(cur_frm.custom_buttons && cur_frm.custom_buttons[label]);
		},
		{ label, group }
	);
}

// ── dialogs and messages ─────────────────────────────────────────────────────

function visibleModal(page) {
	return page.locator(".modal.show:visible").last();
}

/** Text of any open message dialog (msgprint / throw), or "". */
async function openMessages(page) {
	return page.evaluate(() =>
		Array.from(document.querySelectorAll(".modal.show .msgprint, .modal.show .modal-body .msgprint-dialog, .modal.show .frappe-confirm-message"))
			.map((e) => e.innerText.trim())
			.filter(Boolean)
			.join("\n")
	);
}

/** Fail with the dialog's own text when an error (red) dialog is showing. */
async function expectNoError(page, what) {
	const red = await page.evaluate(() => {
		const m = Array.from(document.querySelectorAll(".modal.show")).find(
			(d) => d.offsetParent !== null && d.querySelector(".modal-title .indicator.red, .indicator.red")
		);
		return m ? m.innerText.trim() : "";
	});
	if (red) throw new Error(`${what} failed: ${red.replace(/\s+/g, " ")}`);
}

/** Answer a frappe.confirm dialog with Yes. */
async function confirmYes(page) {
	const yes = page.locator(".modal.show:visible .modal-footer .btn-primary").last();
	await yes.waitFor({ state: "visible", timeout: 20000 });
	await yes.click();
	await page.waitForTimeout(500);
}

/**
 * The Sales Order's batched drawing steps open a live progress dialog whose
 * "Close & Reload" button only appears once the run is over. Wait for it, return what
 * the dialog reported, and close it (which reloads the order).
 */
async function finishProgressDialog(page, timeout = 15 * 60 * 1000) {
	const close = page.locator(".modal.show:visible .modal-footer .btn-primary:has-text('Close & Reload')").last();
	await close.waitFor({ state: "visible", timeout });
	const text = (await page.locator(".modal.show:visible").last().innerText()).replace(/\s+/g, " ");
	await close.click();
	await waitIdle(page, 1500);
	return text;
}

/** Attach a local file to an Attach field through the upload dialog, as a user does. */
async function attachFile(page, fieldname, filePath) {
	await showField(page, fieldname);
	const ctl = control(page, fieldname);
	await ctl.locator("button:has-text('Attach')").click();
	const dlg = page.locator(".modal.show:visible").last();
	const [chooser] = await Promise.all([
		page.waitForEvent("filechooser"),
		dlg.locator("button:has-text('My Device'), :text('My Device')").first().click(),
	]);
	await chooser.setFiles(filePath);
	// A single file uploads by itself; press Upload if the dialog is still asking.
	const upload = dlg.locator(".modal-footer .btn-primary:has-text('Upload')");
	await page.waitForTimeout(800);
	if (await upload.isVisible().catch(() => false)) await upload.click();
	await expect.poll(() => docValue(page, fieldname), { timeout: 60000 }).toBeTruthy();
	await waitIdle(page, 1000);
}

async function closeModals(page) {
	for (let i = 0; i < 4; i++) {
		const m = page.locator(".modal.show:visible .btn-modal-close, .modal.show:visible button.close").first();
		if (!(await m.count())) break;
		await m.click().catch(() => {});
		await page.waitForTimeout(300);
	}
}

module.exports = {
	BASE_URL,
	login,
	call,
	getValue,
	getDoc,
	exists,
	waitIdle,
	openForm,
	docValue,
	docName,
	control,
	showField,
	setField,
	pickFromDropdown,
	gridRow,
	gridRowCount,
	gridAddRow,
	gridSet,
	gridValue,
	save,
	submit,
	clickButton,
	hasButton,
	visibleModal,
	openMessages,
	expectNoError,
	confirmYes,
	finishProgressDialog,
	attachFile,
	closeModals,
};
