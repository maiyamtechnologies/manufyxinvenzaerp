// Weighment Weight on the Delivery Note and the Packing Slip (client, 22 Oct 2026).
// The total is the sum of the rows as soon as any row has one; until then it is left
// for the user to type. The server does the same on save (selling_management/weighment.py).

function set_total_weighment_weight(frm) {
	const rows = (frm.doc.items || []).map((r) => flt(r.custom_weighment_weight));
	if (rows.some((w) => w)) {
		frm.set_value("custom_total_weighment_weight", flt(rows.reduce((a, b) => a + b, 0), 3));
	}
}

["Delivery Note", "Packing Slip"].forEach((doctype) => {
	frappe.ui.form.on(doctype, { items_remove: set_total_weighment_weight });
	frappe.ui.form.on(doctype + " Item", { custom_weighment_weight: set_total_weighment_weight });
});
