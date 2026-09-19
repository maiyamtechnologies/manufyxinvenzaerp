// Sales Invoice: finished goods invoiced by the piece (sep14 FG plan, A6).
//
// On an FG row (custom_sec_uom = "Nos", set by the mapper and by validate) the user
// types Qty (Nos) and the Kg follows; the Kg field itself is read-only there through
// a property setter. The Kg is asked of the server (selling_management.sales_invoice
// .get_fg_row_kg), which runs the same code as validate, so the last-piece rule and
// the Kg per Nos of the Sales Order line / Delivery Note row are never re-implemented
// here. The server recomputes it again on save regardless.

frappe.ui.form.on("Sales Invoice", {
	update_stock(frm) {
		// The server refuses it too; this only saves the user a failed save.
		if (!frm.doc.update_stock) return;
		const fg = (frm.doc.items || []).filter((row) => row.custom_sec_uom);
		if (!fg.length) return;
		frm.set_value("update_stock", 0);
		frappe.msgprint({
			title: __("Finished Goods Invoice"),
			indicator: "orange",
			message: __(
				"Update Stock cannot be used on an invoice with finished-goods items. " +
					"Deliver them with a Delivery Note and invoice from it or from the Sales Order."
			),
		});
	},
});

frappe.ui.form.on("Sales Invoice Item", {
	custom_sec_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.custom_sec_uom || !row.item_code) return;
		frappe.call({
			method: "manufyxinvenzaerp.selling_management.sales_invoice.get_fg_row_kg",
			args: { doc: frm.doc, row_name: cdn },
			callback(r) {
				const res = r.message || {};
				if (res.error) {
					frappe.show_alert({ message: res.error, indicator: "orange" }, 8);
					return;
				}
				if (res.kg !== undefined && flt(res.kg, 3) !== flt(row.qty, 3)) {
					// Setting qty through the model fires ERPNext's own qty handler,
					// which reprices the row and the totals.
					frappe.model.set_value(cdt, cdn, "qty", res.kg);
				}
				if (res.nos !== undefined && flt(res.nos) !== flt(row.custom_sec_qty)) {
					// Credit notes carry negative Nos; keep the sign the server set.
					frappe.model.set_value(cdt, cdn, "custom_sec_qty", res.nos);
				}
			},
		});
	},
});
