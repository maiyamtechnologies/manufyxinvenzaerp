// Bring a client BOM upload sheet up to the current template before it is imported.
//
// Older sheets (before the sep14 finished-goods change) carry ONE customer weight,
// "Total Weight (KG)", which is the weight of one piece, and have no Nature of Work or
// Rate Schedule columns. The importer now reads "Cust Weight (per Nos)" and
// "Cust Weight (Total)", and would take an old "Total Weight (KG)" as the Total — so
// the sheet is corrected here rather than uploaded as it is:
//
//   Total Weight (KG)      -> renamed Cust Weight (per Nos)   (it is one piece's weight)
//   Cust Weight (Total)    -> added, = per Nos x Total Qty on the drawing's first row
//   Nature of Work         -> added if missing, on the drawing's first row
//   Rate Schedule          -> added if missing, on the drawing's first row
//   FG Item                -> replaced when `fgItem` is given (the item must be Kg + batch)
//   Thickness              -> cleared on rows of `structuralItems` (Structurals have none;
//                             Verify Raw Materials refuses the sheet otherwise)
//
// The source file is never modified; a corrected copy is written to `outPath`.

const ExcelJS = require("exceljs");

const norm = (v) => String(v == null ? "" : v).trim().toLowerCase();
const cellText = (c) => {
	const v = c && c.value;
	if (v && typeof v === "object") {
		if ("result" in v) return v.result; // formula
		if ("richText" in v) return v.richText.map((t) => t.text).join("");
		if ("text" in v) return v.text;
	}
	return v;
};
const round3 = (x) => Math.round(Number(x) * 1000) / 1000;

async function prepareSheet(srcPath, outPath, opts = {}) {
	const wb = new ExcelJS.Workbook();
	await wb.xlsx.readFile(srcPath);
	const ws = wb.worksheets[0];
	const header = ws.getRow(1);

	const col = {}; // normalised header -> column number
	header.eachCell({ includeEmpty: false }, (c, n) => {
		col[norm(cellText(c))] = n;
	});
	let lastCol = Math.max(...Object.values(col));
	const addColumn = (title) => {
		lastCol += 1;
		header.getCell(lastCol).value = title;
		col[norm(title)] = lastCol;
		return lastCol;
	};
	const need = (key) => {
		if (!col[key]) throw new Error(`Sheet has no "${key}" column: ${srcPath}`);
		return col[key];
	};

	const changes = [];
	// One piece's weight: the new header, or the old single weight column renamed.
	if (!col["cust weight (per nos)"]) {
		const old = col["total weight (kg)"] || col["weight per pcs (kg)"] || col["total weight"];
		if (!old) throw new Error("Sheet has neither Cust Weight (per Nos) nor Total Weight (KG)");
		const oldTitle = cellText(header.getCell(old));
		header.getCell(old).value = "Cust Weight (per Nos)";
		delete col[norm(oldTitle)];
		col["cust weight (per nos)"] = old;
		changes.push(`"${oldTitle}" renamed to "Cust Weight (per Nos)" (it holds one piece's weight)`);
	}
	const totalCol = col["cust weight (total)"] || addColumn("Cust Weight (Total)");
	if (totalCol === lastCol && !changes.some((c) => c.includes("Total)"))) changes.push('"Cust Weight (Total)" added = per Nos x Total Qty');
	const nowCol = col["nature of work"] || (opts.natureOfWork && (changes.push(`"Nature of Work" added (${opts.natureOfWork})`), addColumn("Nature of Work")));
	const rsCol = col["rate schedule"] || (opts.rateSchedule && (changes.push(`"Rate Schedule" added (${opts.rateSchedule})`), addColumn("Rate Schedule")));

	const cdnCol = need("customer drawing number");
	const qtyCol = need("total qty");
	const perCol = col["cust weight (per nos)"];
	const fgCol = col["fg item"] || col["fg item code"];
	const dunoCol = col["duno/mark no"] || col["duno mark no"];
	const matCol = need("material code");
	const thkCol = col["thickness"];
	const itemNoCol = col["item no"];
	const structural = new Set(opts.structuralItems || []);

	// Header values live on the FIRST row of each drawing (the importer reads them there).
	const drawings = new Map();
	ws.eachRow({ includeEmpty: false }, (row, r) => {
		if (r === 1) return;
		const cdn = String(cellText(row.getCell(cdnCol)) || "").trim();
		if (!cdn || !cellText(row.getCell(matCol))) return;
		if (opts.fgItem && fgCol && cellText(row.getCell(fgCol))) row.getCell(fgCol).value = opts.fgItem;
		const mat = String(cellText(row.getCell(matCol))).trim();
		if (thkCol && structural.has(mat) && Number(cellText(row.getCell(thkCol)) || 0)) {
			changes.push(
				`Thickness ${cellText(row.getCell(thkCol))} cleared on sheet row ${r} (${cdn} / ${mat}, item ${
					itemNoCol ? cellText(row.getCell(itemNoCol)) : "?"
				}): Structurals do not use Thickness`
			);
			row.getCell(thkCol).value = null;
		}
		if (drawings.has(cdn)) {
			drawings.get(cdn).rows += 1;
			return;
		}
		const nos = Number(cellText(row.getCell(qtyCol)) || 0);
		const perNos = round3(cellText(row.getCell(perCol)) || 0);
		const total = round3(perNos * nos);
		row.getCell(totalCol).value = total;
		if (nowCol && !cellText(row.getCell(nowCol))) row.getCell(nowCol).value = opts.natureOfWork;
		if (rsCol && !cellText(row.getCell(rsCol))) row.getCell(rsCol).value = opts.rateSchedule;
		drawings.set(cdn, {
			cdn,
			duno: dunoCol ? String(cellText(row.getCell(dunoCol)) || "").trim() : "",
			fgItem: fgCol ? cellText(row.getCell(fgCol)) : "",
			nos,
			perNos,
			total,
			rows: 1,
		});
	});
	if (opts.fgItem) changes.push(`FG Item set to ${opts.fgItem} on every row`);

	await wb.xlsx.writeFile(outPath);
	const list = [...drawings.values()];
	return {
		outPath,
		changes,
		drawings: list,
		totalNos: list.reduce((s, d) => s + d.nos, 0),
		totalKg: round3(list.reduce((s, d) => s + d.total, 0)),
	};
}

module.exports = { prepareSheet };
