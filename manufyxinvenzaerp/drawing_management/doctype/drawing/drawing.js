// Blue for the two forward steps in the drawing's life (submit it, then make its
// BOM); amber for the two that redo or overwrite a decision already made. Painting
// by label is a no-op for a button that is not on screen, so this can be called
// from anywhere without first working out which buttons exist.
function _drawing_paint_buttons(frm) {
	if (!window.mfx_paint_button) return;
	window.mfx_paint_button(frm, "Mark as Final Revision", "primary");
	window.mfx_paint_button(frm, "Create Revision", "alt");
	window.mfx_paint_button(frm, "Update Customer Weight", "alt");
	// "Create BOM" sits inside the Create dropdown, so the group's own toggle is
	// what is on screen -- painting the button would colour a hidden menu item.
	window.mfx_paint_group(frm, "Create", "primary");
}

frappe.ui.form.on("Drawing", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Working") {
			frm.add_custom_button(__("Mark as Final Revision"), function () {
				frappe.confirm(
					__("Mark this drawing as <b>Final Revision</b>? This cannot be undone."),
					function () {
						frappe.call({
							method: "manufyxinvenzaerp.drawing_management.drawing_utils.mark_as_final_revision",
							args: { drawing_name: frm.doc.name },
							freeze: true,
							callback: function () {
								frm.reload_doc();
							},
						});
					}
				);
			});
		}

        if (frm.doc.docstatus === 1 && frm.doc.status === "Final Revision") {
            frappe.call({
                method: "manufyxinvenzaerp.drawing_management.doctype.drawing.drawing.check_existing_bom",
                args: {
                    drawing_name: frm.doc.name
                },
                callback: function (r) {
                    if (r.message) {
                        return;
                    }

                    // ✅ Only show button if no BOM exists
                    frm.add_custom_button(__("Create BOM"), function () {
                        frappe.confirm(
                            __("Create a BOM for <b>" + (frm.doc.fg_item_name || frm.doc.fg_item_code) + "</b>?"),
                            function () {
                                frappe.call({
                                    method: "manufyxinvenzaerp.drawing_management.drawing_utils.create_bom_from_drawing",
                                    args: { drawing_name: frm.doc.name },
                                    freeze: true,
                                    callback: function (r) {
                                        if (r.message) {
                                            frappe.msgprint({
                                                title: __("BOM Created"),
                                                message: __("BOM created") + ': <a href="/app/bom/' +
                                                    encodeURIComponent(r.message) + '" target="_blank">' +
                                                    r.message + "</a>",
                                                indicator: "green",
                                            });
                                            frm.reload_doc();
                                        }
                                    },
                                });
                            }
                        );
                    }, __("Create"));
                    // Arrives after refresh has finished, so it paints itself.
                    _drawing_paint_buttons(frm);

                }
            });
        }

		// Revising a drawing is cancel-then-amend. Doing it with the standard Cancel
		// button walks Frappe into the Sales Order and out again to every other drawing
		// on it -- "Cancel All Documents", twenty-one of them, to revise one. This does
		// the pair in a single step and lands you on the draft.
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Create Revision"), function () {
				frappe.confirm(
					__("Cancel <b>{0}</b> and open revision {1} as a draft?<br><br>Its Sales Order row is released now and re-attached to the new revision when you submit it.",
					   [frm.doc.name, (frm.doc.rev_no || 0) + 1]),
					function () {
						frappe.call({
							method: "manufyxinvenzaerp.drawing_management.drawing_utils.create_revision",
							args: { drawing_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Creating revision..."),
							callback: function (r) {
								if (r.message) {
									frappe.set_route("Form", "Drawing", r.message);
								}
							},
						});
					}
				);
			});
		}

		if (!frm.is_new() && frm.doc.docstatus < 2) {
			frm.add_custom_button(__("Update Customer Weight"), function () {
				_drawing_update_customer_weight(frm);
			});
		}

		// Filter the picker by Type only when one is chosen. Filtering on an empty
		// Type matched only schedules whose own Type is blank, so an imported drawing
		// -- which arrives with a schedule but no Type -- offered an empty list.
		frm.set_query("rate_schedule", function () {
			return frm.doc.type ? { filters: { type: frm.doc.type } } : {};
		});

		frm.set_query("batch", "items", function (doc, cdt, cdn) {
			var row = locals[cdt][cdn];
			return {
				query: "manufyxinvenzaerp.drawing_management.drawing_utils.get_batches_for_drawing_item",
				filters: { item_code: row.material_code },
			};
		});

		update_totals(frm);
		_drawing_paint_buttons(frm);

		// Items grid: Download (always) and Upload (draft only) — bottom-right of table
		setTimeout(function () {
			var grid = frm.fields_dict["items"] && frm.fields_dict["items"].grid;
			if (!grid || !grid.wrapper) return;

			var $dl = grid.wrapper.find(".grid-download");
			var $ul = grid.wrapper.find(".grid-upload");

			$dl.off("click.drawing").removeClass("hidden")
				.on("click.drawing", function () { drawing_download_items_csv(frm); return false; });

			$ul.off("click.drawing");
			if (frm.doc.docstatus === 0) {
				$ul.removeClass("hidden")
					.on("click.drawing", function () { drawing_upload_items_dialog(frm); return false; });
			} else {
				$ul.addClass("hidden");
			}
		}, 0);
	},

	customer(frm) {
		frm.set_value("customer_no", frm.doc.customer || "");
	},

	// Type and Rate Schedule describe the same thing from two directions: Type
	// narrows the picker when choosing by hand, and is read back off the schedule
	// when one arrives ready-made from a BOM import. Each only touches the other
	// when they actually disagree, so setting one cannot loop into clearing the other.
	type(frm) {
		if (!frm.doc.rate_schedule) return;
		frappe.db.get_value("Rate Schedule", frm.doc.rate_schedule, "type").then(function (r) {
			var rs_type = (r && r.message && r.message.type) || "";
			// Only drop the schedule if the new Type genuinely excludes it.
			if (frm.doc.type && rs_type && rs_type !== frm.doc.type) {
				frm.set_value("rate_schedule", "");
			}
		});
	},

	rate_schedule(frm) {
		if (!frm.doc.rate_schedule) {
			["rs_job_nature", "rs_details", "rs_work_content", "rs_job_reference", "rs_rate_per_kg"].forEach(function (f) {
				frm.set_value(f, "");
			});
			return;
		}
		// Type belongs to the schedule, so mirror it here rather than expecting the
		// user to have set it first -- an imported drawing never did.
		frappe.db.get_value("Rate Schedule", frm.doc.rate_schedule, "type").then(function (r) {
			var rs_type = (r && r.message && r.message.type) || "";
			if (rs_type && rs_type !== frm.doc.type) frm.set_value("type", rs_type);
		});
	},

	sales_order(frm) {
		if (!frm.doc.sales_order) {
			frm.set_value("project", "");
			return;
		}
		frappe.db.get_value("Sales Order", frm.doc.sales_order, "project", function (r) {
			if (r && r.project) frm.set_value("project", r.project);
		});
	},
});

// Update Customer Weight (sep14 FG plan, D15). The customer states the weight of
// ONE piece, so that is what is asked for; the Total over all pieces -- the figure
// every downstream document carries -- is worked out and shown live before saving.
function _drawing_update_customer_weight(frm) {
	var nos = flt(frm.doc.no_of_qty_to_manufacture);
	var cur_per = flt(frm.doc.weight_per_pcs) || (nos ? flt(flt(frm.doc.customer_provided_wt) / nos, 3) : 0);
	var cur_total = flt(frm.doc.customer_provided_wt);
	var fmt = function (v) { return format_number(flt(v, 3), null, 3); };

	var d = new frappe.ui.Dialog({
		title: __("Update Customer Weight"),
		fields: [
			{
				fieldname: "new_weight_per_nos",
				fieldtype: "Float",
				precision: 3,
				label: __("New Cust Weight (per Nos)"),
				reqd: 1,
				default: cur_per,
				description: __("Enter the weight of ONE piece. Total = this × {0} Nos. Current: {1} Kg per Nos, {2} Kg total.",
					[nos, fmt(cur_per), fmt(cur_total)]),
				onchange: function () { _show_new_total(); },
			},
			{ fieldname: "new_total_html", fieldtype: "HTML" },
		],
		primary_action_label: __("Update"),
		primary_action: function (values) {
			d.hide();
			frappe.call({
				method: "manufyxinvenzaerp.drawing_management.drawing_utils.update_customer_provided_weight",
				args: { drawing_name: frm.doc.name, new_weight_per_nos: values.new_weight_per_nos },
				freeze: true,
				freeze_message: __("Updating weight and cascading to linked documents…"),
				callback: function (r) {
					if (!r.message) return;
					_drawing_weight_result(r.message);
					frm.reload_doc();
				},
			});
		},
	});

	function _show_new_total() {
		var per = flt(d.get_value("new_weight_per_nos"));
		d.fields_dict.new_total_html.$wrapper.html(
			'<div style="font-size:13px;">' + __("New total") + ": <b>" + fmt(per * nos) + " Kg</b> (" +
			fmt(per) + " × " + nos + " Nos)</div>"
		);
	}
	d.show();
	_show_new_total();
}

function _drawing_weight_result(m) {
	var esc = frappe.utils.escape_html;
	var fmt = function (v) { return format_number(flt(v, 3), null, 3); };
	var html = __("Cust Weight (per Nos) changed from {0} to {1} Kg; Cust Weight (Total) from {2} to {3} Kg ({4} Nos).",
		[fmt(m.old_weight_per_nos), fmt(m.new_weight_per_nos), fmt(m.old_weight), fmt(m.new_weight), m.nos]);
	html += "<br><br>" + __("Sales Order updated: {0}", [m.sales_order_updated ? __("Yes") : __("No")]) +
		"<br>" + __("Production Plan Items updated: {0} (draft plans recalculated in Kg: {1})",
			[m.production_plan_items_updated, m.draft_production_plans_recalculated]) +
		"<br>" + __("Drawing rows (Job Work Order / Material Issue Plan) updated: {0}", [m.drawing_rows_updated]) +
		"<br>" + __("Job Work Orders re-totalled: {0}", [m.subcontracting_orders_updated]) +
		"<br>" + __("Material Issue Plans refreshed: {0}", [m.material_issue_plans_updated]) +
		"<br>" + __("Operation Entry drawing rows updated: {0}", [m.operation_entry_rows_updated]) +
		"<br>" + __("BOMs updated: {0}", [m.boms_updated]);

	if ((m.draft_job_work_orders_recalculated || []).length) {
		html += "<br><br>" + __("Draft Job Work Orders recalculated (Kg, rate and amount): {0}",
			[m.draft_job_work_orders_recalculated.map(esc).join(", ")]);
	}
	if ((m.submitted_job_work_orders || []).length) {
		html += '<br><br><span style="color:var(--orange-600,#d97706);">' +
			__("Submitted Job Work Orders keep their quantity and amount: {0}. Amend them if they must follow the new weight.",
				[m.submitted_job_work_orders.map(esc).join(", ")]) + "</span>";
	}
	// The order was taken on the old weight, so a difference is expected: reported
	// in orange, never blocked.
	(m.sales_order_lines || []).forEach(function (l) {
		if (!flt(l.difference_kg, 3) && !flt(l.difference_nos, 3)) return;
		html += '<br><br><span style="color:var(--orange-600,#d97706);">' +
			__("Sales Order {0}, {1}: ordered {2} Kg / {3} Nos, drawings now {4} Kg / {5} Nos — difference {6} Kg, {7} Nos.",
				[esc(l.sales_order), esc(l.item_code), fmt(l.ordered_kg), l.ordered_nos, fmt(l.drawings_kg),
				 l.drawings_nos, fmt(l.difference_kg), l.difference_nos]) + "</span>";
	});
	html += "<br><br>" + __("Batch allocation/reservation was <b>not</b> changed automatically — reallocate manually if needed.");

	frappe.msgprint({ title: __("Customer Weight Updated"), indicator: "green", message: html });
}

frappe.ui.form.on("Drawing Item", {
	material_code(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (!row.material_code) return;
		frappe.db.get_value(
			"Item",
			row.material_code,
			["item_name", "item_group", "description", "custom_material_spec",
			 "custom_unit_weight", "custom_secondary_uom", "custom_parent_item_group", "stock_uom"],
			function (r) {
				if (!r) return;
				frappe.model.set_value(cdt, cdn, "material_name", r.item_name || "");
				frappe.model.set_value(cdt, cdn, "item_group", r.item_group || "");
				frappe.model.set_value(cdt, cdn, "parent_item_group", r.custom_parent_item_group || "");
				frappe.model.set_value(cdt, cdn, "raw_material_description", r.description || "");
				frappe.model.set_value(cdt, cdn, "material_spec", r.custom_material_spec || "");
				frappe.model.set_value(cdt, cdn, "unit_weight", r.custom_unit_weight || 0);
				frappe.model.set_value(cdt, cdn, "sec_uom", r.custom_secondary_uom || "");
				frappe.model.set_value(cdt, cdn, "uom", r.stock_uom || "");
				setTimeout(function () { drawing_calculate_qty(frm, cdt, cdn); drawing_calculate_totals(frm, cdt, cdn); }, 300);
			}
		);
	},

	batch(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (!row.batch) return;
		frappe.db.get_value(
			"Batch",
			row.batch,
			["custom_thickness", "custom_length", "custom_width"],
			function (r) {
				if (!r) return;
				if (r.custom_thickness) frappe.model.set_value(cdt, cdn, "thickness", r.custom_thickness);
				if (r.custom_length) frappe.model.set_value(cdt, cdn, "length", r.custom_length);
				if (r.custom_width) frappe.model.set_value(cdt, cdn, "width", r.custom_width);
				drawing_calculate_qty(frm, cdt, cdn);
				drawing_calculate_totals(frm, cdt, cdn);
			}
		);
	},

	thickness(frm, cdt, cdn) { drawing_calculate_qty(frm, cdt, cdn); drawing_calculate_totals(frm, cdt, cdn); },
	length(frm, cdt, cdn) { drawing_calculate_qty(frm, cdt, cdn); drawing_calculate_totals(frm, cdt, cdn); },
	width(frm, cdt, cdn) { drawing_calculate_qty(frm, cdt, cdn); drawing_calculate_totals(frm, cdt, cdn); },
	sec_qty(frm, cdt, cdn) { drawing_calculate_qty(frm, cdt, cdn); drawing_calculate_totals(frm, cdt, cdn); },
	unit_weight(frm, cdt, cdn) { drawing_calculate_qty(frm, cdt, cdn); drawing_calculate_totals(frm, cdt, cdn); },

	qty(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if ((row.parent_item_group || "") === "Nuts and Bolts" && row.unit_weight) {
			frappe.model.set_value(cdt, cdn, "sec_qty", flt(row.qty * row.unit_weight, 3));
		}
		update_totals(frm);
		drawing_calculate_totals(frm, cdt, cdn);
	},
});

function drawing_calculate_qty(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	var group = row.parent_item_group;
	var qty = null;

	if (group === "Structurals") {
		if (row.length && row.unit_weight && row.sec_qty) {
			qty = (row.length / 1000) * row.unit_weight * row.sec_qty;
		} else {
			drawing_warn_missing_fields(row, group);
		}
	} else if (group === "Plates") {
		if (row.length && row.width && row.thickness && row.unit_weight && row.sec_qty) {
			qty = (row.length / 1000) * (row.width / 1000) * row.thickness * row.unit_weight * row.sec_qty;
		} else {
			drawing_warn_missing_fields(row, group);
		}
	} else if (group === "Nuts and Bolts") {
		// qty (NOS) is manual; recalculate sec_qty (KG) when unit_weight changes
		if (row.qty && row.unit_weight) {
			frappe.model.set_value(cdt, cdn, "sec_qty", flt(row.qty * row.unit_weight, 3));
			update_totals(frm);
		}
		return;
	}

	if (qty !== null) {
		frappe.model.set_value(cdt, cdn, "qty", flt(qty, 3));
		update_totals(frm);
	}
}

function drawing_calculate_totals(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	var no_of_qty = flt(frm.doc.no_of_qty_to_manufacture);
	var group = row.parent_item_group || "";

	if (group === "Nuts and Bolts") {
		var nab_total_qty = flt(row.qty * no_of_qty, 3);
		frappe.model.set_value(cdt, cdn, "total_qty", nab_total_qty);
		frappe.model.set_value(cdt, cdn, "total_sec_qty", flt(nab_total_qty * row.unit_weight, 3));
		return;
	}

	var total_sec_qty = flt(flt(row.sec_qty) * no_of_qty, 3);
	frappe.model.set_value(cdt, cdn, "total_sec_qty", total_sec_qty);

	var total_qty = 0;
	if (group === "Structurals") {
		if (row.length && row.unit_weight && total_sec_qty) {
			total_qty = flt((row.length / 1000) * row.unit_weight * total_sec_qty, 3);
		}
	} else if (group === "Plates") {
		if (row.length && row.width && row.thickness && row.unit_weight && total_sec_qty) {
			total_qty = flt((row.length / 1000) * (row.width / 1000) * row.thickness * row.unit_weight * total_sec_qty, 3);
		}
	}
	frappe.model.set_value(cdt, cdn, "total_qty", total_qty);
}

function update_totals(frm) {
	var total_weight = 0;
	(frm.doc.items || []).forEach(function (row) {
		var uom = (row.uom || "").toLowerCase();
		var sec_uom = (row.sec_uom || "").toLowerCase();
		if (uom === "kg" || uom === "kgs") {
			total_weight += flt(row.qty);
		} else if (sec_uom === "kg" || sec_uom === "kgs") {
			total_weight += flt(row.sec_qty);
		}
	});
	frm.set_value("total_weight", flt(total_weight, 3));
	render_items_summary(frm);
}

function render_items_summary(frm) {
	var wrapper = frm.fields_dict["items_summary_html"] &&
	              frm.fields_dict["items_summary_html"].$wrapper;
	if (!wrapper) return;
	var rows = frm.doc.items || [];
	if (!rows.length) {
		wrapper.html('<p class="text-muted">' + __("No items.") + "</p>");
		return;
	}
	var cols = [
		["Item No", "item_number"], ["Material Code", "material_code"], ["Material Name", "material_name"],
		["Item Group", "item_group"], ["Material Spec", "material_spec"],
		["Thickness", "thickness"], ["Length", "length"], ["Width", "width"],
		["NOS", "sec_qty"], ["Sec UOM", "sec_uom"],
		["Qty ", "qty"], ["UOM", "uom"]
	];
	var html = '<div style="overflow-x:auto;overflow-y:auto;max-height:320px;width:100%;">';
	html += '<table class="table table-bordered table-condensed" style="font-size:12px;white-space:nowrap;min-width:1200px;">';
	html += '<thead style="position:sticky;top:0;background:#f5f5f5;z-index:1;">';
	html += "<tr>" + cols.map(function (c) {
		var minw = (c[1] === "material_code" || c[1] === "material_name") ? ' style="min-width:160px;"' : '';
		return "<th" + minw + ">" + frappe.utils.escape_html(c[0]) + "</th>";
	}).join("") + "</tr></thead>";
	html += "<tbody>";
	rows.forEach(function (row) {
		html += "<tr>" + cols.map(function (c) {
			var val = row[c[1]] != null ? row[c[1]] : "";
			return "<td>" + frappe.utils.escape_html(String(val)) + "</td>";
		}).join("") + "</tr>";
	});
	html += "</tbody></table></div>";
	wrapper.html(html);
}

function drawing_warn_missing_fields(row, group) {
	var missing = [];
	if (group === "Structurals") {
		if (!row.length) missing.push("Length");
		if (!row.unit_weight) missing.push("Unit Weight");
		if (!row.sec_qty) missing.push("NOS");
	} else if (group === "Plates") {
		if (!row.length) missing.push("Length");
		if (!row.width) missing.push("Width");
		if (!row.thickness) missing.push("Thickness");
		if (!row.unit_weight) missing.push("Unit Weight");
		if (!row.sec_qty) missing.push("NOS");
	}
	if (missing.length) {
		frappe.show_alert({
			message: __("Row {0}: Missing for {1} formula: {2}", [row.idx, group, missing.join(", ")]),
			indicator: "orange",
		});
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// CSV Upload / Download helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Download a blank Drawing Items CSV template with three sample rows.
 * Columns: item_number, material_code, sec_qty, thickness, length, width
 */
function drawing_download_csv_template() {
	var HEADERS = ["item_number", "material_code", "sec_qty", "thickness", "length", "width"];
	var LABELS  = ["Item Number", "Item Code",     "NOS", "Thickness (mm)", "Length (mm)", "Width (mm)"];
	var SAMPLES = [
		["1", "ISMBX250X125", "2", "",   "1500", ""],
		["2", "PLATE12",      "1", "12", "1500", "2000"],
		["3", "BOLTM24",      "2", "",   "",     ""],
	];

	var lines = [
		HEADERS.join(","),
		"# " + LABELS.join(",") + "  ← (labels for reference — do not include this row in your upload)"
	];
	SAMPLES.forEach(function(r) { lines.push(r.join(",")); });

	_drawing_trigger_csv_download(lines.join("\n"), "drawing_items_template.csv");
}

/**
 * Download the current items table as a CSV file.
 */
function drawing_download_items_csv(frm) {
	var items = frm.doc.items || [];
	if (!items.length) {
		frappe.msgprint(__("No items to download."));
		return;
	}

	var COLS = [
		["item_number",    "item_number"],
		["material_code",  "material_code"],
		["material_name",  "material_name"],
		["parent_item_group", "parent_item_group"],
		["sec_qty",        "sec_qty"],
		["sec_uom",        "sec_uom"],
		["thickness",      "thickness"],
		["length",         "length"],
		["width",          "width"],
		["unit_weight",    "unit_weight"],
		["qty",            "qty"],
		["uom",            "uom"],
	];

	var lines = [COLS.map(function(c) { return c[0]; }).join(",")];
	items.forEach(function(row) {
		var cells = COLS.map(function(c) {
			var v = row[c[1]];
			if (v == null) v = "";
			// Wrap in quotes if the value contains a comma or quote
			var s = String(v);
			if (s.indexOf(",") !== -1 || s.indexOf('"') !== -1) {
				s = '"' + s.replace(/"/g, '""') + '"';
			}
			return s;
		});
		lines.push(cells.join(","));
	});

	var doc_id = frm.doc.name || "drawing";
	_drawing_trigger_csv_download(lines.join("\n"), doc_id + "_items.csv");
}

function drawing_upload_items_dialog(frm) {
	new frappe.ui.FileUploader({
		as_dataurl: true,
		allow_multiple: false,
		restrictions: { allowed_file_types: [".csv"] },
		on_success: function (file) {
			var csv_content = frappe.utils.get_decoded_string(file.dataurl);
			frappe.call({
				method: "manufyxinvenzaerp.drawing_management.drawing_utils.parse_drawing_items_csv",
				args: { csv_content: csv_content },
				freeze: true,
				freeze_message: __("Processing CSV…"),
				callback: function (r) {
					if (!r.message || !r.message.length) return;
					frm.clear_table("items");
					r.message.forEach(function (row_data) {
						var child = frm.add_child("items");
						$.extend(locals[child.doctype][child.name], row_data);
					});
					frm.refresh_field("items");
					update_totals(frm);
					frappe.show_alert({
						message: __("{0} item(s) loaded from CSV.", [r.message.length]),
						indicator: "green",
					}, 5);
				},
			});
		},
	});
}

/** Trigger a browser CSV download from a plain-text string. */
function _drawing_trigger_csv_download(csv_text, filename) {
	var blob = new Blob([csv_text], { type: "text/csv;charset=utf-8;" });
	var url  = URL.createObjectURL(blob);
	var a    = document.createElement("a");
	a.href     = url;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	setTimeout(function () {
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}, 100);
}
