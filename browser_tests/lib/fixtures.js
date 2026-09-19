// Test masters and the upload sheet for the finished-goods Kg / Nos browser test.
//
// Masters (items, customer, rate schedule) are created once through the API and reused
// on every run: they are set-up, not the flow under test. Every TRANSACTION in the spec
// is entered through the forms. All names start with "E2E" so they are easy to find
// and never collide with real data.

const path = require("path");
const fs = require("fs");
const ExcelJS = require("exceljs");
const { call, exists } = require("./frappe_ui");

const COMPANY = process.env.E2E_COMPANY || "Manufyx Invenza Private Limited";

const M = {
	customer: "E2E Customer",
	fgItem: "E2E-FG-STRUCT",
	plateItem: "E2E-PLATE10",
	platePrefix: "E2EP",
	rateSchedule: "E2E-RS20",
	jobNature: "Purlin",
	natureOfWork: "Auto Welding",
	stores: "Stores - MIPL",
	fgWarehouse: "Finished Goods - MIPL",
	wip: "Work In Progress - MIPL",
};

// The worked example of the sep14 plan (§6): one drawing, 10 Nos, 30 Kg per Nos.
const EXAMPLE = {
	nos: 10,
	perNos: 30,
	total: 300,
	ratePerKg: 20,
	// One plate per finished piece: T10 x W500 x L1000 at 7.85 = 39.25 Kg a piece.
	plate: { thickness: 10, width: 500, length: 1000, perPiece: 1 },
};

async function insertIfMissing(page, doc, name) {
	if (await exists(page, doc.doctype, name)) return false;
	await call(page, "frappe.client.insert", { doc });
	return true;
}

/** Create the reusable test masters if they are not there yet. */
async function ensureMasters(page) {
	const made = [];
	if (
		await insertIfMissing(
			page,
			{
				doctype: "Customer",
				customer_name: M.customer,
				customer_type: "Company",
				customer_group: "Commercial",
				territory: "India",
			},
			M.customer
		)
	)
		made.push(M.customer);

	if (
		await insertIfMissing(
			page,
			{
				doctype: "Item",
				item_code: M.fgItem,
				item_name: "E2E Fabricated Structure",
				item_group: "Fin Goods Item",
				custom_parent_item_group: "Finished Goods",
				stock_uom: "Kg",
				custom_secondary_uom: "Nos",
				gst_hsn_code: "841229",
				is_stock_item: 1,
				include_item_in_manufacturing: 1,
				has_batch_no: 1,
				create_new_batch: 0,
			},
			M.fgItem
		)
	)
		made.push(M.fgItem);

	if (
		await insertIfMissing(
			page,
			{
				doctype: "Item",
				item_code: M.plateItem,
				item_name: "E2E Plate 10 mm",
				item_group: "Plates child node",
				custom_parent_item_group: "Plates",
				stock_uom: "Kg",
				custom_secondary_uom: "Nos",
				custom_unit_weight: 7.85,
				gst_hsn_code: "72082510",
				is_stock_item: 1,
				include_item_in_manufacturing: 1,
				has_batch_no: 1,
				create_new_batch: 1,
				custom_batch_prefix: M.platePrefix,
				valuation_rate: 50,
			},
			M.plateItem
		)
	)
		made.push(M.plateItem);

	if (
		await insertIfMissing(
			page,
			{
				doctype: "Rate Schedule",
				rs_no: M.rateSchedule,
				type: "Outsource",
				job_nature: M.jobNature,
				details: "E2E browser test",
				rate_per_kg: EXAMPLE.ratePerKg,
			},
			M.rateSchedule
		)
	)
		made.push(M.rateSchedule);
	return made;
}

/** Write the BOM upload sheet for one drawing and return its path. */
async function writeSheet(dir, run) {
	const wb = new ExcelJS.Workbook();
	const ws = wb.addWorksheet("BOM Import");
	ws.addRow([
		"Assembly Group", "Customer Drawing Number", "DUNO/Mark No",
		"FG Item", "Total Qty", "Cust Weight (per Nos)", "Cust Weight (Total)",
		"Nature of Work", "Rate Schedule",
		"Item No", "Material Code", "Grade", "Thickness", "Width", "Length",
		"Reqd Raw Material Qty",
	]);
	const p = EXAMPLE.plate;
	ws.addRow([
		"E2E Assembly", run.drawingNumber, run.duno,
		M.fgItem, EXAMPLE.nos, EXAMPLE.perNos, EXAMPLE.total,
		M.natureOfWork, M.rateSchedule,
		"1", M.plateItem, "IS2062", p.thickness, p.width, p.length,
		p.perPiece,
	]);
	fs.mkdirSync(dir, { recursive: true });
	const file = path.join(dir, `${run.id}_bom_sheet.xlsx`);
	await wb.xlsx.writeFile(file);
	return file;
}

/** Identifiers unique to one run, so the spec can be re-run without clashes. */
function newRun() {
	const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(2, 14); // yymmddHHMMSS
	return {
		id: `E2E${stamp}`,
		drawingNumber: `E2E-DRG-${stamp}`,
		duno: `E2E${stamp.slice(-6)}`,
		poNo: `E2E-PO-${stamp}`,
	};
}

module.exports = { COMPANY, M, EXAMPLE, ensureMasters, writeSheet, newRun };
