// Delivery Challan (Gate Pass) -- form script.
//
// Every server method below is written as a full literal dotted path on purpose.
// tests/test_whitelist_coverage scans these files with a regex that only matches a
// complete "manufyxinvenzaerp.…" path inside a single quoted string, so building
// the path by concatenation would hide it from the guard -- and the guard exists
// because a lost @frappe.whitelist() once shipped a dead button to the live site.

frappe.ui.form.on("Delivery Challan", {
	setup(frm) {
		frm.set_query("against_gate_pass", function () {
			return {
				query: "manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan.gate_pass_return_query",
				filters: { company: frm.doc.company },
			};
		});
	},

	refresh(frm) {
		dc_set_indicator(frm);
		dc_toggle_type_fields(frm);

		if (frm.doc.docstatus === 1) {
			dc_add_print_buttons(frm);
		}

		if (
			frm.doc.docstatus === 1 &&
			frm.doc.challan_type === "Returnable" &&
			frm.doc.status !== "Returned"
		) {
			frm.add_custom_button(
				__("Return Entry"),
				function () {
					frappe.model.open_mapped_doc({
						method: "manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan.make_return_entry",
						frm: frm,
					});
				},
				__("Create")
			);
		}

		if (
			frm.doc.docstatus === 1 &&
			frm.doc.challan_type === "Return Entry" &&
			frm.doc.against_gate_pass
		) {
			frm.add_custom_button(__("Original Gate Pass"), function () {
				frappe.set_route("Form", "Delivery Challan", frm.doc.against_gate_pass);
			});
		}
	},

	challan_type(frm) {
		if (frm.doc.challan_type !== "Return Entry") {
			frm.set_value("against_gate_pass", null);
		}
		if (frm.doc.challan_type !== "Returnable") {
			frm.set_value("expected_return_date", null);
		}
		dc_toggle_type_fields(frm);
	},

	against_gate_pass(frm) {
		// Return Entry: pull the supplier details and the still-pending items
		// from the chosen gate pass.
		if (frm.doc.challan_type !== "Return Entry" || !frm.doc.against_gate_pass) return;
		frappe.call({
			method: "manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan.get_return_entry_details",
			args: { source_name: frm.doc.against_gate_pass },
			freeze: true,
			freeze_message: __("Fetching gate pass details..."),
			callback(r) {
				const d = r && r.message;
				if (!d) return;
				// Assigned directly (not set_value) so the party_type / party handlers,
				// which blank dependent fields, do not wipe what was just filled.
				["company", "party_type", "party", "party_display_name", "party_address",
					"job_no", "ref_dc_no", "total_value_of_goods", "production_plan", "wo_date",
					"vehicle_no", "driver_name", "mobile_no"].forEach(function (f) {
					if (d[f] !== undefined && d[f] !== null) frm.doc[f] = d[f];
				});
				frm.clear_table("items");
				(d.items || []).forEach(function (it) {
					const row = frm.add_child("items");
					Object.keys(it).forEach(function (k) {
						if (it[k] !== null && it[k] !== undefined) row[k] = it[k];
					});
				});
				frm.refresh_fields();
				dc_recalculate_totals(frm);
			},
			error() {
				frm.set_value("against_gate_pass", null);
			},
		});
	},

	party_type(frm) {
		frm.set_value("party", null);
		frm.set_value("party_display_name", null);
		frm.set_value("party_address", null);
	},

	party(frm) {
		// Blank both first, so the server's fill-when-blank picks up the NEWLY
		// chosen party rather than leaving the previous one's details behind.
		frm.set_value("party_address", null);
		frm.set_value("party_display_name", null);

		if (!frm.doc.party || !frm.doc.party_type || frm.doc.party_type === "Other") return;

		// The server fills this at save, but the field's own description promises
		// it is auto-filled from the party -- so it must appear on selection, not
		// only after the first save.
		const field = { Supplier: "supplier_name", Customer: "customer_name" }[frm.doc.party_type];
		if (!field) return;
		frappe.db.get_value(frm.doc.party_type, frm.doc.party, field).then((r) => {
			const name = r && r.message && r.message[field];
			if (frm.doc.party) frm.set_value("party_display_name", name || frm.doc.party);
		});
	},

	items_add(frm) {
		dc_recalculate_totals(frm);
	},

	items_remove(frm) {
		dc_recalculate_totals(frm);
	},
});

frappe.ui.form.on("Delivery Challan Item", {
	qty(frm) {
		dc_recalculate_totals(frm);
	},

	weight_kg(frm) {
		dc_recalculate_totals(frm);
	},

	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code) return;
		frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom"]).then((r) => {
			const item = (r && r.message) || {};
			if (!row.material_description && item.item_name) {
				frappe.model.set_value(cdt, cdn, "material_description", item.item_name);
			}
			if (!row.uom && item.stock_uom) {
				frappe.model.set_value(cdt, cdn, "uom", item.stock_uom);
			}
		});
	},
});

function dc_recalculate_totals(frm) {
	let qty = 0;
	let weight = 0;
	(frm.doc.items || []).forEach(function (row) {
		qty += flt(row.qty);
		weight += flt(row.weight_kg);
	});
	frm.set_value("total_qty", flt(qty, 3));
	frm.set_value("total_weight_kg", flt(weight, 3));
}

function dc_toggle_type_fields(frm) {
	frm.toggle_reqd("expected_return_date", frm.doc.challan_type === "Returnable");
	frm.toggle_reqd("against_gate_pass", frm.doc.challan_type === "Return Entry");
}

function dc_set_indicator(frm) {
	if (frm.doc.docstatus !== 1) return;
	const colours = {
		"Material Out": "blue",
		"Material In": "blue",
		"Partially Returned": "orange",
		Overdue: "red",
		Returned: "green",
		Cancelled: "darkgrey",
	};
	const colour = colours[frm.doc.status];
	if (colour) {
		frm.page.set_indicator(__(frm.doc.status), colour);
	}
	if (frm.doc.status === "Overdue") {
		frm.dashboard.clear_headline();
		frm.dashboard.set_headline_alert(
			__("Material was due back on {0} and is still out.", [
				frappe.datetime.str_to_user(frm.doc.expected_return_date),
			]),
			"red"
		);
	}
}

function dc_add_print_buttons(frm) {
	frm.add_custom_button(__("Print Preview"), function () {
		frappe.call({
			method: "manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan.get_delivery_challan_html",
			args: { name: frm.doc.name },
			freeze: true,
			callback: function (r) {
				if (!r.message) return;
				const d = new frappe.ui.Dialog({
					title: __("Delivery Challan {0}", [frm.doc.name]),
					size: "large",
					fields: [{ fieldtype: "HTML", fieldname: "preview" }],
				});
				d.fields_dict.preview.$wrapper.html(r.message);
				d.show();
			},
		});
	});

	// Plain-text label: v16 escapes button labels (see mfx_with_icon).
	mfx_with_icon(frm.add_custom_button(
		__("PDF"),
		function () {
			open_url_post(
				"/api/method/manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan.download_delivery_challan_pdf",
				{ name: frm.doc.name }
			);
		}
	), "file");
}
