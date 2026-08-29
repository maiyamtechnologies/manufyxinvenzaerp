// Cut Sheet — client script.
//
// Item Code, Item Name, Item Group and Unit Weight all describe the batch being
// cut, so they follow FROM the batch rather than being picked independently — the
// server already refuses a batch/item mismatch (_fetch_batch_dimensions). Item Name
// / Parent Item Group / Unit Weight already cascade automatically once item_code is
// set (fetch_from: item_code.xxx in the doctype); this script's job is only to set
// item_code itself, and to preview the batch's own Length/Width/Thickness/Sec Qty
// immediately rather than leaving that whole section blank until the first Save.
//
// It also does two things the form previously left until Save:
//
//   * the weights. Sheet Qty, Qty per Nos, W1 Total, W2 Calc and the availability
//     figures are all derived from dimensions the user is typing, and showing them
//     only after a save meant planning a cut blind — enter the numbers, save, look,
//     adjust, save again. They are recalculated here as you type, with the SAME
//     formula the server uses (utils/dimension_formula.calculate_qty). The server
//     still recomputes every one of them in validate(): this is a live preview, not
//     the source of truth, and nothing here can persist a figure the server
//     disagrees with.
//
//   * hiding Width and Thickness on a Structurals sheet. The Structurals formula is
//     (Length / 1000) x Unit Weight x Nos — width and thickness are not in it, so
//     the fields only invited values that would be silently ignored. Shown for
//     Plates, where they are part of the formula.

frappe.ui.form.on("Cut Sheet", {
	setup(frm) {
		// Only the warehouses that actually hold this plate. The field offered every
		// warehouse on the site, and exactly one of them contains the batch -- the
		// split happens against the batch in the warehouse named here, so any other
		// choice names a place this sheet's own material is not.
		frm.set_query("warehouse", () => ({
			query: "manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet.cut_sheet_warehouse_query",
			filters: { batch_no: frm.doc.batch_no || "", company: frm.doc.company || "" },
		}));
	},

	refresh(frm) {
		_cs_lock_identity_fields(frm);
		_cs_toggle_dimension_fields(frm);
		_cs_recalculate(frm);
		_cs_lock_cut_fields(frm);
		_cs_release_button(frm);
		_cs_inactive_button(frm);
	},

	parent_item_group(frm) {
		_cs_toggle_dimension_fields(frm);
		_cs_recalculate(frm);
	},

	batch_no(frm) {
		if (!frm.doc.batch_no) {
			frm.set_value("sheet_length", 0);
			frm.set_value("sheet_width", 0);
			frm.set_value("sheet_thickness", 0);
			frm.set_value("sheet_sec_qty", 0);
			return;
		}

		frappe.db.get_value(
			"Batch",
			frm.doc.batch_no,
			["item", "custom_length", "custom_width", "custom_thickness", "custom_sec_qty"],
			(r) => {
				if (!r) return;
				if (r.item) frm.set_value("item_code", r.item);
				// Preview only -- validate() re-fetches these from the batch itself on
				// save regardless, so a stale value here can never actually be saved.
				frm.set_value("sheet_length", flt(r.custom_length));
				frm.set_value("sheet_width", flt(r.custom_width));
				frm.set_value("sheet_thickness", flt(r.custom_thickness));
				frm.set_value("sheet_sec_qty", flt(r.custom_sec_qty));
			}
		);
	},

	// Every input the weights depend on.
	sheet_length: _cs_recalculate,
	sheet_width: _cs_recalculate,
	sheet_thickness: _cs_recalculate,
	sheet_sec_qty: _cs_recalculate,
	unit_weight: _cs_recalculate,
	w1_length: _cs_recalculate,
	w1_width: _cs_recalculate,
	w1_sec_qty: _cs_recalculate,
});

// The server's calculate_qty (utils/dimension_formula.py), in JS. Returns 0 where
// that returns None -- the inputs for the group are not all in yet, and a blank
// figure is the honest answer while someone is still typing.
function _cs_qty(group, length, width, thickness, unit_weight, sec_qty) {
	length = flt(length); width = flt(width); thickness = flt(thickness);
	unit_weight = flt(unit_weight); sec_qty = flt(sec_qty);

	if (group === "Structurals") {
		if (length && unit_weight && sec_qty) return (length / 1000) * unit_weight * sec_qty;
		return 0;
	}
	if (group === "Plates") {
		if (length && width && thickness && unit_weight && sec_qty) {
			return (length / 1000) * (width / 1000) * thickness * unit_weight * sec_qty;
		}
		return 0;
	}
	return 0;
}

function _cs_lock_identity_fields(frm) {
	// Company, Item Code, Batch and Warehouse say WHAT is being cut. Every other
	// figure here is derived from that one plate in that one warehouse, so once the
	// sheet is saved they are fixed -- re-pointing it at another batch would keep
	// the cut, the allocations and the status while changing what they describe.
	// The server refuses it too (CutSheet._block_identity_changes); this is so the
	// form does not invite the edit in the first place.
	const saved = !frm.is_new();
	["company", "item_code", "batch_no", "warehouse"].forEach(f =>
		frm.set_df_property(f, "read_only", saved ? 1 : 0)
	);
}

function _cs_inactive_button(frm) {
	// A sheet raised by mistake had nowhere to go: deleting it loses the record it
	// was ever made, and leaving it Active keeps it in the picker as material to
	// cut. Inactive is neither -- kept for reference, offered nowhere.
	if (frm.is_new() || frm.doc.status === "Inactive") return;
	if ((frm.doc.allocations || []).length || frm.doc.w2_applied) return;

	frm.add_custom_button(__("Mark Inactive"), function () {
		frappe.prompt(
			[{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Reason"),
				reqd: 1,
				description: __("Why this sheet is being set aside. It is kept for exactly this question later."),
			}],
			function (values) {
				frappe.call({
					method: "manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet.mark_cut_sheet_inactive",
					args: { cut_sheet_name: frm.doc.name, reason: values.reason },
					freeze: true,
					freeze_message: __("Marking Inactive…"),
					callback() {
						frappe.show_alert({ message: __("Cut Sheet marked Inactive"), indicator: "orange" });
						frm.reload_doc();
					},
				});
			},
			__("Mark this Cut Sheet Inactive"),
			__("Mark Inactive")
		);
	});
}

// W1/W2 are locked once a job is planning from this sheet. The server refuses the
// change (CutSheet._block_cut_changes_while_claimed); this says so before anyone
// types, because a Cut Sheet looks perfectly editable otherwise and the reason it
// is not has nothing to do with this form — it is a Material Planning somewhere
// else holding the pieces.
const _CS_CUT_FIELDS = [
	"w1_length", "w1_width", "w1_sec_qty",
	"w2_length", "w2_width", "w2_sec_qty",
];

function _cs_lock_cut_fields(frm) {
	const allocs = frm.doc.allocations || [];
	const locked = !frm.is_new() && allocs.length > 0;

	_CS_CUT_FIELDS.forEach(f => frm.set_df_property(f, "read_only", locked ? 1 : 0));

	const $w = frm.fields_dict.w1_length && frm.fields_dict.w1_length.$wrapper;
	if (!$w) return;
	$w.find(".mfx-cs-lock-note").remove();
	if (!locked) return;

	const plans = Array.from(new Set(allocs.map(a => a.material_planning).filter(Boolean)));
	const reserved = allocs.some(a => a.is_reserved);
	$w.prepend(
		'<div class="mfx-cs-lock-note" style="margin-bottom:8px;padding:8px 12px;' +
		'background:#fff5f5;border-left:3px solid #c62828;border-radius:3px;' +
		'font-size:12px;color:#c62828;">' +
		"<b>" + __("In use — W1 and W2 are locked.") + "</b> " +
		__("{0} piece(s) are allocated to {1}. Changing the cut here would rewrite what that plan transfers, so it is refused.", [
			allocs.length,
			plans.length ? plans.join(", ") : __("a Material Planning"),
		]) +
		"<br>" +
		(reserved
			? __("Some of it is <b>reserved</b>: unreserve those rows on the Material Planning and take the batch off them first, then use Release Allocations.")
			: __("Use <b>Release Allocations</b> to hand the pieces back, then the sizes are editable again.")) +
		"</div>"
	);
}

function _cs_release_button(frm) {
	// W1 Sec Nos cannot be reduced below what jobs have already taken -- correct,
	// or the sheet would silently oversubscribe pieces someone is relying on. But
	// there was no way to undo those claims either, so re-cutting a plate meant
	// editing every claiming Material Planning by hand to find and clear the rows.
	// This is that step: release the claims, then the sizes are free to change.
	if (frm.is_new() || !(frm.doc.allocations || []).length) return;

	frm.add_custom_button(__("Release Allocations"), function () {
		const plans = Array.from(new Set(
			(frm.doc.allocations || []).map(a => a.material_planning).filter(Boolean)
		));
		frappe.confirm(
			__("Hand every allocated piece back to this sheet?<br><br>{0} row(s) across {1} will stop cutting from it, and its W1/W2 sizes become editable again.<br><br>Anything still reserved is refused — unreserve it on its Material Planning first.", [
				(frm.doc.allocations || []).length,
				plans.length ? plans.join(", ") : __("no plan"),
			]),
			function () {
				frappe.call({
					method: "manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet.release_all_cut_sheet_allocations",
					args: { cut_sheet_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Releasing allocations…"),
					callback(r) {
						const out = r.message || {};
						frappe.msgprint({
							title: __("Allocations Released"),
							message: __("{0} allocation(s) released from {1}. W1 and W2 can be changed now.", [
								out.released || 0,
								(out.plans || []).join(", ") || __("this sheet"),
							]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			}
		);
	});
}

function _cs_toggle_dimension_fields(frm) {
	// Width and Thickness are Plates-only inputs. On a Structurals sheet they are
	// not part of the formula, so they are hidden rather than left to be filled in
	// and ignored. Only ever hidden for Structurals: an unset group still shows
	// everything, because nothing is known yet about which formula applies.
	const structurals = frm.doc.parent_item_group === "Structurals";
	["sheet_width", "sheet_thickness", "w1_width", "w2_width"].forEach(function (f) {
		frm.toggle_display(f, !structurals);
	});
}

function _cs_recalculate(frm) {
	// Mirrors CutSheet._calculate on the server, field for field, so what the form
	// shows before a save is what the save will store.
	const group = frm.doc.parent_item_group;
	const uw = flt(frm.doc.unit_weight);

	const sheet_qty = _cs_qty(
		group, frm.doc.sheet_length, frm.doc.sheet_width, frm.doc.sheet_thickness,
		uw, flt(frm.doc.sheet_sec_qty) || 1
	);

	// W1 uses the SHEET's thickness, not one of its own -- a cut piece is as thick
	// as the plate it came off.
	const w1_qty_per_nos = _cs_qty(
		group, frm.doc.w1_length, frm.doc.w1_width, frm.doc.sheet_thickness, uw, 1
	);
	// At full precision from the dimensions, never (rounded per-piece x count) --
	// see the server's own note: one milligram is enough to make an exactly-covered
	// requirement look short.
	const w1_total_qty = _cs_qty(
		group, frm.doc.w1_length, frm.doc.w1_width, frm.doc.sheet_thickness,
		uw, frm.doc.w1_sec_qty
	);

	// W2 is what is LEFT of the sheet once W1 comes off it, not an independent
	// measurement -- deriving it is what stops the two halves disagreeing with the
	// sheet they came from.
	const w2_calc_qty = Math.max(sheet_qty - w1_total_qty, 0);

	const allocated_sec_qty = (frm.doc.allocations || []).reduce(
		(t, a) => t + flt(a.sec_qty), 0
	);
	const allocated_qty = (frm.doc.allocations || []).reduce((t, a) => t + flt(a.qty), 0);
	const available_sec_qty = flt(frm.doc.w1_sec_qty) - allocated_sec_qty;
	const available_qty = _cs_qty(
		group, frm.doc.w1_length, frm.doc.w1_width, frm.doc.sheet_thickness,
		uw, available_sec_qty
	);

	// set_value on read-only display fields, so the preview follows typing without
	// marking the form dirty over figures the server owns.
	const preview = {
		sheet_qty: sheet_qty,
		w1_qty_per_nos: w1_qty_per_nos,
		w1_total_qty: w1_total_qty,
		w2_calc_qty: w2_calc_qty,
		allocated_sec_qty: allocated_sec_qty,
		allocated_qty: allocated_qty,
		available_sec_qty: available_sec_qty,
		available_qty: available_qty,
	};
	Object.keys(preview).forEach(function (f) {
		const val = flt(preview[f], 3);
		if (flt(frm.doc[f], 3) !== val) {
			frm.doc[f] = val;
			frm.refresh_field(f);
		}
	});
}
