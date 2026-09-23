// Delivery Note: finished goods delivered by the piece (sep14 FG plan, A5).
//
// On an FG row (custom_sec_uom = "Nos", set by the Sales Order mapper and by the
// server on save) the user types Qty (Nos) and the Kg follows; the Kg field itself is
// read-only there through a property setter. The Kg is asked of the server
// (selling_management.delivery_note.get_fg_rows_kg), which runs the same code as
// validate, so the batch pricing and the last-piece rule are never re-implemented
// here. The server sets them again on save regardless.
//
// "Get FG Batches" lists the drawing batches of the note's Sales Orders that hold
// pieces in the row's warehouse; the ticked ones become one row each, linked to their
// Sales Order line, and the unbatched row they replace is removed.

const A5_METHOD = "manufyxinvenzaerp.selling_management.delivery_note.";

// Ask the server for every row's Nos and Kg and put them on the form.
// fit_returns: on a new return, cut each row's Nos down to what is still out.
function a5_refresh_rows(frm, fit_returns) {
	if (frm.doc.docstatus !== 0 || !(frm.doc.items || []).length) return;
	return frappe.call({
		method: A5_METHOD + "get_fg_rows_kg",
		args: { doc: frm.doc, fit_returns: fit_returns ? 1 : 0 },
		callback(r) {
			const res = r.message || {};
			const errors = [];
			(frm.doc.items || []).forEach((row) => {
				const out = res[row.name];
				if (!out) return;
				if (!out.fg) {
					if (row.custom_sec_uom) {
						frappe.model.set_value(row.doctype, row.name, "custom_sec_uom", null);
					}
					return;
				}
				if (row.custom_sec_uom !== "Nos") {
					frappe.model.set_value(row.doctype, row.name, "custom_sec_uom", "Nos");
				}
				if (out.error) {
					errors.push(out.error);
					return;
				}
				if (out.kg !== undefined && flt(out.kg, 3) !== flt(row.qty, 3)) {
					// Setting qty through the model fires ERPNext's own qty handler,
					// which reprices the row and the totals.
					frappe.model.set_value(row.doctype, row.name, "qty", out.kg);
				}
				if (out.nos !== undefined && flt(out.nos) !== flt(row.custom_sec_qty)) {
					// Returns carry negative Nos; keep the sign the server set.
					frappe.model.set_value(row.doctype, row.name, "custom_sec_qty", out.nos);
				}
			});
			if (errors.length) {
				frappe.show_alert({ message: errors.join("<br>"), indicator: "orange" }, 10);
			}
		},
	});
}

function a5_has_fg_rows(frm) {
	return (frm.doc.items || []).some((row) => row.custom_sec_uom === "Nos");
}

function a5_add_batch_rows(frm, picked) {
	// Copy the Sales Order line's row (rate, accounts, GST fields ...) for each batch.
	const skip = [
		"name", "idx", "batch_no", "serial_no", "serial_and_batch_bundle", "qty", "stock_qty",
		"custom_sec_qty", "custom_drawing", "custom_duno_mark_no", "amount", "base_amount",
		"net_amount", "base_net_amount", "__islocal", "__unsaved", "docstatus", "parent",
		"parentfield", "parenttype", "doctype", "creation", "modified", "owner", "modified_by",
		"custom_billed_sec_qty", "billed_amt", "returned_qty", "installed_qty", "packed_qty",
	];
	const replaced = new Set();
	picked.forEach((p) => {
		const template = locals["Delivery Note Item"][p.template_row];
		if (!template) return;
		const row = frm.add_child("items");
		Object.keys(template).forEach((key) => {
			if (!skip.includes(key)) row[key] = template[key];
		});
		Object.assign(row, {
			batch_no: p.batch_no,
			use_serial_batch_fields: 1,
			custom_sec_uom: "Nos",
			custom_sec_qty: flt(p.nos),
			custom_drawing: p.drawing,
			custom_duno_mark_no: p.duno,
			qty: flt(p.kg, 3),
			stock_qty: flt(p.kg, 3) * flt(template.conversion_factor || 1),
			amount: flt(p.kg, 3) * flt(template.rate),
		});
		if (!template.batch_no) replaced.add(template.name);
	});
	// The unbatched row of each line is replaced by its batch rows.
	replaced.forEach((name) => frappe.model.clear_doc("Delivery Note Item", name));
	frm.doc.items = (frm.doc.items || []).filter((row) => !replaced.has(row.name));
	frm.doc.items.forEach((row, i) => (row.idx = i + 1));
	frm.refresh_field("items");
	frm.dirty();
	// Price every row from the server (the same code as save), then the totals.
	const call = a5_refresh_rows(frm);
	if (call) {
		call.then(() => {
			if (frm.cscript.calculate_taxes_and_totals) frm.cscript.calculate_taxes_and_totals();
		});
	}
}

function a5_get_fg_batches(frm) {
	frappe.call({
		method: A5_METHOD + "get_fg_batches",
		args: { doc: frm.doc },
		freeze: true,
		callback(r) {
			const batches = r.message || [];
			if (!batches.length) {
				frappe.msgprint({
					title: __("Get FG Batches"),
					indicator: "orange",
					message: __(
						"No drawing batch of this note's Sales Orders holds pieces in the rows' " +
							"warehouse. Book the pieces with the Final Stock Entry first, or check " +
							"the warehouse on the finished-goods rows."
					),
				});
				return;
			}
			const dialog = new frappe.ui.Dialog({
				title: __("Get FG Batches"),
				size: "extra-large",
				fields: [
					{
						fieldtype: "HTML",
						options: `<p class="text-muted">${__(
							"Tick the drawings to deliver and set their Nos. Each becomes one row, " +
								"linked to its Sales Order line; the Kg is the batch's Kg for those " +
								"pieces (the last pieces take exactly what is left)."
						)}</p>`,
					},
					{
						fieldname: "batches",
						fieldtype: "Table",
						cannot_add_rows: true,
						cannot_delete_rows: true,
						in_place_edit: true,
						data: batches,
						fields: [
							{ fieldname: "batch_no", label: __("Batch"), fieldtype: "Link", options: "Batch", read_only: 1, in_list_view: 1, columns: 2 },
							{ fieldname: "drawing", label: __("Drawing"), fieldtype: "Link", options: "Drawing", read_only: 1, in_list_view: 1, columns: 2 },
							{ fieldname: "duno", label: __("DUNO/Mark No"), fieldtype: "Data", read_only: 1, in_list_view: 1, columns: 1 },
							{ fieldname: "available_nos", label: __("Available NOS"), fieldtype: "Float", read_only: 1, in_list_view: 1, columns: 1 },
							{ fieldname: "available_kg", label: __("Available (Kg)"), fieldtype: "Float", precision: 3, read_only: 1, in_list_view: 1, columns: 1 },
							{ fieldname: "kg_per_nos", label: __("Kg per Nos"), fieldtype: "Float", precision: 3, read_only: 1, in_list_view: 1, columns: 1 },
							{ fieldname: "nos", label: __("Nos to Deliver"), fieldtype: "Int", in_list_view: 1, columns: 1 },
							{ fieldname: "sales_order", label: __("Sales Order"), fieldtype: "Link", options: "Sales Order", read_only: 1, in_list_view: 1, columns: 1 },
							{ fieldname: "kg", label: __("Kg"), fieldtype: "Float", precision: 3, read_only: 1 },
							{ fieldname: "so_detail", fieldtype: "Data", read_only: 1, hidden: 1 },
							{ fieldname: "template_row", fieldtype: "Data", read_only: 1, hidden: 1 },
							{ fieldname: "warehouse", fieldtype: "Link", options: "Warehouse", read_only: 1, hidden: 1 },
						],
					},
				],
				primary_action_label: __("Add Rows"),
				primary_action() {
					const grid = dialog.fields_dict.batches.grid;
					let picked = grid.get_selected_children();
					if (!picked.length) {
						frappe.msgprint(__("Tick at least one batch."));
						return;
					}
					const bad = picked.filter((p) => cint(p.nos) <= 0 || cint(p.nos) > flt(p.available_nos));
					if (bad.length) {
						frappe.msgprint(
							__("Nos to Deliver must be a whole number between 1 and the Available NOS: {0}",
								[bad.map((p) => p.batch_no).join(", ")])
						);
						return;
					}
					dialog.hide();
					a5_add_batch_rows(frm, picked);
				},
			});
			dialog.show();
		},
	});
}

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.doc.is_return && a5_has_fg_rows(frm)) {
			frm.add_custom_button(__("Get FG Batches"), () => a5_get_fg_batches(frm));
		}
	},
	onload_post_render(frm) {
		// A return made from a Delivery Note maps each row's full Nos (ERPNext only
		// nets the Kg of earlier returns); let the server set the Nos that are still
		// out and their Kg before the user edits.
		if (frm.is_new() && frm.doc.is_return && a5_has_fg_rows(frm)) {
			a5_refresh_rows(frm, true);
		}
	},
});

frappe.ui.form.on("Delivery Note Item", {
	custom_sec_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.custom_sec_uom !== "Nos" || !row.item_code) return;
		a5_refresh_rows(frm);
	},
	batch_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.custom_sec_uom === "Nos" && row.batch_no) a5_refresh_rows(frm);
	},
	warehouse(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.custom_sec_uom === "Nos" && row.batch_no) a5_refresh_rows(frm);
	},
	item_code(frm, cdt, cdn) {
		// A row added by hand: once ERPNext has fetched the item, learn whether it is
		// tracked by the piece (the server sets Nos as its Sec UOM, which locks the Kg).
		frappe.after_ajax(() => {
			const row = locals[cdt] && locals[cdt][cdn];
			if (row && row.item_code) a5_refresh_rows(frm);
		});
	},
});
