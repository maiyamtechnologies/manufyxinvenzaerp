frappe.ui.form.on("Supplier Operation Entry", {
	refresh(frm) {
		// SOE Inspection Item is shared with the Inspection Entry, where each drawing
		// gets its Feedback and Rework Remarks. Here the table only lists what is
		// waiting for inspection, so those two columns are not shown.
		const grid = frm.fields_dict.inspection_items && frm.fields_dict.inspection_items.grid;
		if (grid && !grid.__mfx_result_cols_hidden) {
			["feedback", "rework_remarks"].forEach((f) => grid.update_docfield_property(f, "hidden", 1));
			grid.__mfx_result_cols_hidden = true;
			grid.reset_grid();
		}

		const btn = frm.fields_dict.create_inspection_btn;
		if (btn && btn.$input) {
			// Dark: the one action on this tab that hands the work over to QC.
			btn.$input.removeClass("btn-default btn-xs").addClass("btn-primary btn-sm");
		}
		if (frm.is_new() || !frm.doc.custom_inspection_mandatory) return;

		const open_entry = _soe_open_inspection_entry(frm);
		frm.toggle_display("create_inspection_btn", frm.doc.docstatus === 0 && !open_entry);
		if (open_entry) {
			frm.add_custom_button(__("View Inspection Entry"), function () {
				frappe.set_route("Form", "Inspection Entry", open_entry);
			}, __("Inspection"));
		}
	},

	create_inspection_btn(frm) {
		_soe_create_inspection_dialog(frm);
	},
});

// The Inspection Entry of the round still in progress, if there is one.
function _soe_open_inspection_entry(frm) {
	const row = (frm.doc.custom_inspection_call_log || []).find(
		(r) => r.round_status !== "Completed" && r.inspection_entry
	);
	return row ? row.inspection_entry : null;
}

// Create Inspection: pick the call date, see the drawings that go to QC (what the
// Inspection Items table has pending -- the same quantities as always), confirm.
// One server call logs the round and creates the Inspection Entry together.
function _soe_create_inspection_dialog(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the Operation Entry first, so the pending drawings are up to date."));
		return;
	}
	const pending = (frm.doc.inspection_items || []).filter((r) => flt(r.qty_nos) > 0);
	if (!pending.length) {
		frappe.msgprint({
			title: __("Nothing to Inspect"),
			message: __("Nothing is pending inspection. Log completed NOS in the Consumption Log first."),
			indicator: "orange",
		});
		return;
	}

	const esc = frappe.utils.escape_html;
	const th = "padding:6px 8px;text-align:left;font-weight:600;color:var(--text-muted);border-bottom:1px solid var(--border-color)";
	const td = "padding:6px 8px;border-bottom:1px solid var(--border-color)";
	const rows_html = pending.map((r) => `<tr>
			<td style="${td}">${esc(r.drawing || "")}</td>
			<td style="${td}">${esc(r.customer_drawing_number || "")}</td>
			<td style="${td};text-align:right">${flt(r.qty_nos, 3)}</td>
		</tr>`).join("");
	const total = pending.reduce((s, r) => s + flt(r.qty_nos), 0);

	const dialog = new frappe.ui.Dialog({
		title: __("Create Inspection"),
		fields: [
			{ fieldname: "call_date", fieldtype: "Date", label: __("Inspection Call Date"),
			  reqd: 1, default: frappe.datetime.get_today() },
			{ fieldname: "drawings", fieldtype: "HTML" },
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			frappe.call({
				method: "manufyxinvenzaerp.production_management.inspection.create_soe_inspection",
				args: { soe_name: frm.doc.name, call_date: values.call_date },
				freeze: true,
				freeze_message: __("Creating Inspection Entry…"),
				callback(r) {
					if (r.message) {
						dialog.hide();
						frm.reload_doc();
						frappe.set_route("Form", "Inspection Entry", r.message);
					}
				},
			});
		},
	});
	dialog.fields_dict.drawings.$wrapper.html(`
		<div style="font-size:12px;color:var(--text-muted);margin:4px 0 6px">
			${__("These drawings will be sent for inspection:")}</div>
		<table style="width:100%;font-size:12px;border-collapse:collapse">
			<thead><tr>
				<th style="${th}">${__("Drawing")}</th>
				<th style="${th}">${__("Cust Drawing No")}</th>
				<th style="${th};text-align:right">${__("Completed NOS")}</th>
			</tr></thead>
			<tbody>${rows_html}</tbody>
			<tfoot><tr>
				<td style="padding:6px 8px;font-weight:600" colspan="2">${__("Total")}</td>
				<td style="padding:6px 8px;text-align:right;font-weight:600">${flt(total, 3)}</td>
			</tr></tfoot>
		</table>`);
	dialog.show();
}
