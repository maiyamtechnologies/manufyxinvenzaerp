// Finished goods in Kg and Nos — browser test of the CORE flow (sep14 plan).
//
// Every transaction is entered through the desk forms: fields typed, rows added in the
// grids, toolbar and custom buttons pressed, dialogs answered — as a user does.
//
// Input is the client's own BOM upload sheet (E2E_SHEET, default: "updated BOM manufact.xlsx" in
// ~/Downloads). Older sheets are first brought up to the current template by
// lib/sheet.js (Cust Weight per Nos / Total, Nature of Work, Rate Schedule, and the FG
// item switched to a Kg + batch finished-goods item); the corrected copy is uploaded,
// the original is never touched.
//
// The documents it creates are REAL and stay on the site for inspection. Test masters
// (E2E-FG-STRUCT, E2E-PLATE10, E2E Customer, E2E-RS20) are created once and reused.
//
// Run:   cd apps/manufyxinvenzaerp/browser_tests
//        FRAPPE_PASSWORD=... npx playwright test       (or FRAPPE_SID=<session id>)
//        HEADED=1 ...  to watch it in a browser window.

const { test, expect } = require("@playwright/test");
const os = require("os");
const path = require("path");
const fs = require("fs");
const ui = require("./lib/frappe_ui");
const { M, ensureMasters, newRun } = require("./lib/fixtures");
const { prepareSheet } = require("./lib/sheet");

const SOURCE_SHEET =
	process.env.E2E_SHEET || path.join(os.homedir(), "Downloads", "updated BOM manufact.xlsx");
const ARTIFACTS = path.join(__dirname, "artifacts");
const RATE_PER_KG = 100; // selling rate on the Sales Order line

const run = newRun();
const S = {}; // names of the documents created, filled in as the flow goes

test.describe.configure({ mode: "serial" });

test("finished goods Kg and Nos: core flow", async ({ page }) => {
	test.info().annotations.push({ type: "run", description: run.id });
	await ui.login(page);

	await test.step("masters", async () => {
		const made = await ensureMasters(page);
		console.log("masters created:", made.length ? made.join(", ") : "none (already there)");
	});

	let sheet;
	await test.step("upload sheet brought up to the current template", async () => {
		fs.mkdirSync(ARTIFACTS, { recursive: true });
		// Which materials are Structurals comes from the item master, not the code.
		const structuralItems = (
			await ui.call(page, "frappe.client.get_list", {
				doctype: "Item",
				filters: { custom_parent_item_group: "Structurals" },
				fields: ["name"],
				limit_page_length: 0,
			})
		).map((r) => r.name);
		sheet = await prepareSheet(SOURCE_SHEET, path.join(ARTIFACTS, `${run.id}_bom_sheet.xlsx`), {
			fgItem: M.fgItem,
			natureOfWork: M.natureOfWork,
			rateSchedule: M.rateSchedule,
			structuralItems,
		});
		console.log(`sheet: ${sheet.drawings.length} drawings, ${sheet.totalNos} Nos, ${sheet.totalKg} Kg`);
		sheet.changes.forEach((c) => console.log("  sheet:", c));
	});

	await test.step("Sales Order: finished-goods line in Kg with the Nos", async () => {
		if (process.env.E2E_SO) {
			// Resume an earlier run: every later step skips what is already done.
			S.salesOrder = process.env.E2E_SO;
			await ui.openForm(page, "Sales Order", S.salesOrder);
			console.log("Sales Order (resumed):", S.salesOrder);
		} else {
			await ui.openForm(page, "Sales Order");
			await ui.setField(page, "customer", M.customer);
			await ui.setField(page, "delivery_date", displayDate(30));
			await ui.setField(page, "po_no", run.poNo);
			if ((await ui.gridRowCount(page, "items")) === 0) await ui.gridAddRow(page, "items");
			await ui.gridSet(page, "items", 1, "item_code", M.fgItem);
			await ui.gridSet(page, "items", 1, "qty", sheet.totalKg);
			await ui.gridSet(page, "items", 1, "custom_sec_qty", sheet.totalNos);
			await ui.gridSet(page, "items", 1, "rate", RATE_PER_KG);
			await ui.save(page);
			S.salesOrder = await ui.docName(page);
			console.log("Sales Order:", S.salesOrder);
		}
		expect(await ui.gridValue(page, "items", 1, "qty")).toBeCloseTo(sheet.totalKg, 3);
		expect(await ui.gridValue(page, "items", 1, "custom_sec_qty")).toBe(sheet.totalNos);
	});

	await test.step("Drawing Import: attach, Load Items, Verify Raw Materials", async () => {
		if (!(await ui.docValue(page, "custom_bom_excel_file"))) {
			await ui.attachFile(page, "custom_bom_excel_file", sheet.outPath);
		}
		if (!(await page.evaluate(() => (cur_frm.doc.custom_duno_items || []).length))) {
		await ui.control(page, "custom_bom_action_btns").locator("button:has-text('Load Items')").click();
		await ui.waitIdle(page, 1500);
		await ui.expectNoError(page, "Load Items");
		// "Loaded with Warnings" (orange) reports sheet problems; log them and carry on —
		// Verify Raw Materials is the gate that decides whether they block.
		const loadMsg = await ui.openMessages(page);
		if (loadMsg) console.log("  Load Items said:", loadMsg.replace(/\s+/g, " "));
		await ui.closeModals(page);
		}
		await expect.poll(() => page.evaluate(() => (cur_frm.doc.custom_duno_items || []).length)).toBe(sheet.drawings.length);

		// Both customer weights reached every Drawing List row.
		const rows = await page.evaluate(() =>
			cur_frm.doc.custom_duno_items.map((r) => ({ duno: r.duno_mark_no, nos: r.total_quantity, per: r.weight_per_pcs, total: r.total_weight }))
		);
		for (const d of sheet.drawings) {
			const r = rows.find((x) => x.duno === d.duno);
			expect(r, `Drawing List row for ${d.duno}`).toBeTruthy();
			expect(r.per).toBeCloseTo(d.perNos, 3);
			expect(r.total).toBeCloseTo(d.total, 3);
		}

		if (await ui.docValue(page, "custom_raw_materials_verified")) return;
		await ui.showField(page, "custom_rm_verify_btn");
		await ui.control(page, "custom_rm_verify_btn").locator("button:has-text('Verify Raw Materials')").click();
		await ui.waitIdle(page, 2000);
		const verifyMsg = (await ui.openMessages(page)) || "";
		const verified = await ui.docValue(page, "custom_raw_materials_verified");
		if (!verified) throw new Error("Verify Raw Materials did not pass:\n" + verifyMsg);
		if (verifyMsg) console.log("  Verify said:", verifyMsg.replace(/\s+/g, " ").slice(0, 400));
		await ui.closeModals(page);
	});

	await test.step("Create Drawing", async () => {
		if (await page.evaluate(() => cur_frm.doc.custom_duno_items.every((r) => r.drawing))) return;
		await ui.clickButton(page, "Create Drawing", "Drawing");
		await ui.confirmYes(page);
		console.log("  Create Drawing:", (await ui.finishProgressDialog(page)).slice(0, 200));
		await expect
			.poll(() => page.evaluate(() => cur_frm.doc.custom_duno_items.filter((r) => r.drawing).length))
			.toBe(sheet.drawings.length);
	});

	await test.step("submit the Sales Order", async () => {
		if ((await ui.docValue(page, "docstatus")) === 0) await ui.submit(page);
	});

	await test.step("Submit Drawing, Mark as Final Revision, Create and Submit BOM", async () => {
		for (const label of ["Submit Drawing", "Mark as Final Revision", "Create and Submit BOM"]) {
			if (!(await ui.hasButton(page, label, "Drawing"))) continue; // already done
			await ui.clickButton(page, label, "Drawing");
			await ui.confirmYes(page);
			console.log(`  ${label}:`, (await ui.finishProgressDialog(page)).slice(0, 200));
		}
		S.drawings = await page.evaluate(() => cur_frm.doc.custom_duno_items.map((r) => ({ duno: r.duno_mark_no, drawing: r.drawing })));
		const boms = await ui.call(page, "frappe.client.get_list", {
			doctype: "BOM",
			filters: { custom_drawing: ["in", S.drawings.map((d) => d.drawing)], docstatus: 1 },
			fields: ["name", "custom_drawing", "quantity", "custom_sec_qty", "custom_cust_weight_total"],
			limit_page_length: 100,
		});
		expect(boms.length, "one submitted BOM per drawing").toBe(sheet.drawings.length);
		// BOM quantity is Kg (the drawing's Cust Weight (Total)) and carries the Nos.
		for (const b of boms) {
			const d = sheet.drawings.find((x) => x.duno === S.drawings.find((s) => s.drawing === b.custom_drawing).duno);
			expect(b.quantity).toBeCloseTo(d.total, 3);
			expect(b.custom_sec_qty).toBe(d.nos);
		}
		S.boms = boms;
		console.log(`  ${boms.length} BOMs in Kg with their Nos`);
	});
});

// A date N days from today in the site's display format (dd-mm-yyyy).
function displayDate(days) {
	const d = new Date(Date.now() + days * 86400000);
	const dd = String(d.getDate()).padStart(2, "0");
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const fmt = process.env.E2E_DATE_FORMAT || "dd-mm-yyyy";
	return fmt.replace("yyyy", d.getFullYear()).replace("mm", mm).replace("dd", dd);
}
