// Stock Entry: finished-goods rows in Kg with Nos per drawing batch (sep14 FG plan, A4).
//
// Finished goods are stocked in Kg and counted in Nos, one batch per drawing. On an FG
// row the Nos is what the user types; the Kg follows from it:
//   - Material Transfer / Issue: Kg = the batch's Kg for that many pieces in the source
//     warehouse (the last pieces take exactly what is left), read-only;
//   - Manufacture (Final Stock Entry): Kg = Nos x Cust Weight (per Nos), read-only when
//     "Edit FG Stock Kg" is off, otherwise a default the weighed figure may replace;
//   - Material Receipt: Kg typed (a re-weigh).
// The server (fg_stock.validate_fg_stock_entry_rows) sets the same figures on save, so
// this is only there to show them before saving.
//
// Stock Entry's other client logic lives in the "Stock Entry-dimensional-weight-logic"
// Client Script (setup.py); this file only adds the FG part.

const FG_GROUP = "Finished Goods";
const FG_METHOD = "manufyxinvenzaerp.production_management.fg_stock.";

function _fg_purpose(frm) {
	return frm.doc.purpose || frm.doc.stock_entry_type;
}

function _fg_is_row(row) {
	return row && row.custom_parent_item_group === FG_GROUP;
}

function _fg_takes_out(frm) {
	return ["Material Transfer", "Material Issue"].includes(_fg_purpose(frm));
}

function _fg_is_produced(frm, row) {
	return _fg_purpose(frm) === "Manufacture" && row.t_warehouse && !row.s_warehouse;
}

// Kg is locked where the server derives it and would overwrite anything typed.
function _fg_kg_locked(frm, row) {
	if (!_fg_is_row(row)) return false;
	if (_fg_takes_out(frm)) return true;
	return _fg_is_produced(frm, row) && frm._fg_settings && !frm._fg_settings.edit_fg_stock_kg;
}

function _fg_apply_read_only(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid || frm.doc.docstatus !== 0) return;
	(grid.grid_rows || []).forEach((grid_row) => {
		const row = grid_row.doc;
		if (_fg_is_row(row)) {
			grid_row.toggle_editable("qty", !_fg_kg_locked(frm, row));
		}
	});
}

function _fg_load_settings(frm) {
	if (frm._fg_settings) {
		_fg_apply_read_only(frm);
		return;
	}
	frappe.call({
		method: FG_METHOD + "get_fg_settings",
		callback(r) {
			frm._fg_settings = r.message || { edit_fg_stock_kg: true };
			_fg_apply_read_only(frm);
		},
	});
}

function _fg_set_kg(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!_fg_is_row(row) || frm.doc.docstatus !== 0) return;
	const nos = flt(row.custom_sec_qty);
	if (nos <= 0) return;

	if (_fg_takes_out(frm)) {
		if (!row.batch_no || !row.s_warehouse) return;
		frappe.call({
			method: FG_METHOD + "get_fg_kg_for_nos",
			args: { batch_no: row.batch_no, warehouse: row.s_warehouse, nos: nos },
			callback(r) {
				const m = r.message;
				if (!m) return;
				if (nos > flt(m.nos)) {
					frappe.show_alert({
						message: __("Row {0}: batch {1} holds only {2} Nos in {3}.",
							[row.idx, row.batch_no, flt(m.nos), row.s_warehouse]),
						indicator: "red",
					}, 7);
					return;
				}
				frappe.model.set_value(cdt, cdn, "qty", flt(m.kg, 3));
			},
		});
	} else if (_fg_is_produced(frm, row)) {
		// With the setting on, the typed (weighed) Kg stands; only an empty Kg is filled.
		const editable = !frm._fg_settings || frm._fg_settings.edit_fg_stock_kg;
		if (editable && flt(row.qty)) return;
		frappe.call({
			method: FG_METHOD + "get_fg_planned_kg",
			args: { nos: nos, drawing: row.custom_drawing || null, batch_no: row.batch_no || null },
			callback(r) {
				if (r.message && flt(r.message.kg)) {
					frappe.model.set_value(cdt, cdn, "qty", flt(r.message.kg, 3));
				}
			},
		});
	}
}

frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		_fg_load_settings(frm);
	},
	stock_entry_type(frm) {
		_fg_apply_read_only(frm);
	},
});

frappe.ui.form.on("Stock Entry Detail", {
	custom_sec_qty(frm, cdt, cdn) {
		_fg_set_kg(frm, cdt, cdn);
	},
	batch_no(frm, cdt, cdn) {
		_fg_set_kg(frm, cdt, cdn);
	},
	s_warehouse(frm, cdt, cdn) {
		_fg_set_kg(frm, cdt, cdn);
		_fg_apply_read_only(frm);
	},
	t_warehouse(frm, cdt, cdn) {
		_fg_apply_read_only(frm);
	},
	custom_parent_item_group(frm) {
		// Set once the item is picked (fetched by the Client Script), so this is when
		// a new row becomes known as finished goods.
		_fg_apply_read_only(frm);
	},
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const grid_row = frm.fields_dict.items.grid.grid_rows_by_docname[cdn];
		if (grid_row && _fg_is_row(row) && frm.doc.docstatus === 0) {
			grid_row.toggle_editable("qty", !_fg_kg_locked(frm, row));
		}
	},
});
