// ── Process Planning: Supplier/Contractor per operation ─────────────────────
// Work Type decides which master the row's party comes from; the server derives
// the same mapping (production_plan.PARTY_TYPE_BY_WORK_TYPE) and is the backstop.
const MFX_PARTY_TYPE_BY_WORK_TYPE = { "Subcontractor": "Supplier", "Internal Jobcard": "Contractor" };

function mfx_setup_process_planning_party(frm) {
	let grid = frm.fields_dict.custom_process_planning && frm.fields_dict.custom_process_planning.grid;
	if (!grid) return;
	// Mandatory on a DRAFT plan only. The table cannot be edited once submitted, so a
	// plan submitted before this column existed would otherwise be refused every later
	// Update with a field nobody can fill. The server enforces it at submit.
	grid.update_docfield_property("party", "reqd", frm.doc.docstatus === 0 ? 1 : 0);
	frm.set_query("party", "custom_process_planning", function(doc, cdt, cdn) {
		let row = locals[cdt][cdn];
		return row.party_type === "Supplier" ? { filters: { disabled: 0 } } : {};
	});
	// Rows created before the column existed, or by the server from the BOM routing,
	// may not carry a party type yet. Set straight on the row rather than through
	// set_value, so opening a plan does not mark it as changed.
	(frm.doc.custom_process_planning || []).forEach(function(row) {
		let expected = MFX_PARTY_TYPE_BY_WORK_TYPE[row.work_type] || "";
		if (row.party_type !== expected && !row.party) row.party_type = expected;
	});
}

frappe.ui.form.on("Process Planning", {
	work_type(frm, cdt, cdn) {
		// A party chosen under the other Work Type is the wrong kind of party, so it is
		// cleared rather than carried across -- a Supplier cannot do an internal job.
		let row = locals[cdt][cdn];
		let expected = MFX_PARTY_TYPE_BY_WORK_TYPE[row.work_type] || "";
		if (row.party_type !== expected) {
			frappe.model.set_value(cdt, cdn, "party", "");
			frappe.model.set_value(cdt, cdn, "party_type", expected);
		}
	},
});

frappe.ui.form.on("Production Plan", {
	refresh(frm) {
		mfx_setup_process_planning_party(frm);

		// ── Hide all standard filter / MRP sections not used in this workflow ──
		frm.toggle_display([
			// Get items filter section
			"get_items_from",
			"item_code",
			"customer",
			"warehouse",
			"project",
			"from_date",
			"to_date",
			"get_sales_orders",
			"sales_orders",
			"get_material_request",
			"material_requests",
			"get_items",
			// Sub assembly section
			"get_sub_assembly_items",
			"sub_assembly_items",
			"from_delivery_date",
			"to_delivery_date",
			"combine_sub_items",
			"skip_available_sub_assembly_item",
			"sub_assembly_warehouse",
			// MRP Planning section
			"download_materials_request_plan_section_section",
			"download_materials_required",
			"material_request_planning",
			"include_non_stock_items",
			"include_subcontracted_items",
			"consider_minimum_order_qty",
			"include_safety_stock",
			"ignore_existing_ordered_qty",
			"column_break_25",
			"for_warehouse",
			"get_items_for_mr",
			"transfer_materials",
			// Raw Materials section
			"section_break_27",
			"mr_items",
			// Other Details
			"other_details",
			"total_planned_qty",
			"total_produced_qty",
			"column_break_32",
			"status",
			"warehouses",
			"sales_order_status",
			"combine_items",
			// BOM Raw Material references
			"section_break_25",
			"prod_plan_references",
			// Sub Assembly Items section header (content already hidden above)
			"section_break_24",
			"section_break_ucc4",
			"section_break_g4ip",
			"column_break_igxl",
			// Orphaned section/filter headers
			"filters",
			"sales_orders_detail",
			"material_request_detail",
			"column_break1",
			"column_break2",
			// Custom BOM raw material sections (not needed in this workflow)
			"custom_bom_raw_materials_section",
			"custom_bom_raw_materials",
			"custom_available_raw_materials_section",
			"custom_available_raw_materials",
			"custom_get_raw_materials_for_purchase",
		], false);

		// ── "Add Drawings" button above po_items grid ────────────────────────
		frappe.after_ajax(function() {
			let items_field = frm.fields_dict["po_items"];
			if (!items_field) return;
			let $fw = $(items_field.$wrapper);
			if (frm.doc.docstatus !== 0) {
				$fw.find(".pp-add-drawings-btn-row").remove();
				return;
			}
			if ($fw.find(".pp-add-drawings-btn-row").length) return;
			let $row = $('<div class="pp-add-drawings-btn-row" style="margin-bottom:10px;padding:4px 0;">');
			let $btn = $('<button class="btn btn-sm btn-primary">' + __("Add Drawings") + '</button>');
			$btn.on("click", function() { _show_pp_drawings_picker(frm); });
			$row.append($btn);
			$fw.find(".form-grid").before($row);
		});

		// ── Auto-fill Process Planning from Standard Manufacturing Routing ─────
		if (frm.doc.docstatus === 0
			&& (!frm.doc.custom_process_planning || !frm.doc.custom_process_planning.length)) {
			_pp_autofill_from_standard_routing(frm);
		}

		// ── Inject "Bulk Update" button above the Process Planning grid
		frappe.after_ajax(function() {
			let proc_field = frm.fields_dict["custom_process_planning"];
			if (!proc_field) return;
			let $fw = $(proc_field.$wrapper);
			if (frm.doc.docstatus !== 0) {
				$fw.find(".pp-bulk-btn-row").remove();
				return;
			}
			if ($fw.find(".pp-bulk-btn-row").length) return; // already injected

			let $row = $('<div class="pp-bulk-btn-row" style="margin-bottom:10px;padding:4px 0;">');
			let $btn = $('<button class="btn btn-sm btn-default">' + __("Set Work Type") + '</button>');
			$btn.on("click", function() { _show_bulk_update_dialog(frm); });
			$row.append($btn);
			$fw.find(".form-grid").before($row);
		});
	},
});

frappe.ui.form.on("Production Plan Item", {
	bom_no(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.bom_no) {
			frappe.model.set_value(cdt, cdn, "custom_drawing", "");
			frappe.model.set_value(cdt, cdn, "custom_duno_mark_no", "");
			return;
		}
		frappe.db.get_value(
			"BOM",
			row.bom_no,
			["custom_drawing", "custom_duno_mark_no", "custom_customer_drawing_number"],
			function(d) {
				if (!d) return;
				frappe.model.set_value(cdt, cdn, "custom_drawing", d.custom_drawing || "");
				frappe.model.set_value(cdt, cdn, "custom_duno_mark_no", d.custom_duno_mark_no || "");
				frappe.model.set_value(cdt, cdn, "custom_customer_drawing_number", d.custom_customer_drawing_number || "");
				_pp_mirror_fg_kg(frm, cdt, cdn);
			}
		);
		// Auto-fill Process Planning table from BOM routing operations
		_pp_autofill_operations(frm, row.bom_no);
	},

	// The planner types pieces; the Kg follows (sep14 FG plan, D5).
	custom_sec_qty(frm, cdt, cdn) {
		_pp_mirror_fg_kg(frm, cdt, cdn);
	},

	// Same contract as the BOM's own handler: the Rate Schedule belongs to the
	// drawing, so editing it on this row edits the Drawing and its BOM too. Ask
	// before overwriting a schedule the drawing already has. The propagation runs
	// server-side on save (rate_schedule_sync.on_update_production_plan).
	custom_rate_schedule(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		window.mfx_confirm_rate_schedule_change({
			drawing: row.custom_drawing,
			new_schedule: row.custom_rate_schedule,
			source_doctype: "Production Plan Item",
			source_name: row.name,
			on_decline: (current) =>
				frappe.model.set_value(cdt, cdn, "custom_rate_schedule", current || ""),
		});
	},
});

// Planned Qty (Kg) = Cust Weight (Total) x Qty (Nos) / drawing Nos, for display
// only. The server (production_plan.apply_fg_nos) recalculates it on every save and
// is the one that counts; this just saves the planner a round trip to see the Kg.
function _pp_mirror_fg_kg(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row || !row.custom_drawing) return;
	frappe.db.get_value("Drawing", row.custom_drawing,
		["no_of_qty_to_manufacture", "customer_provided_wt", "weight_per_pcs"],
		function(d) {
			if (!d) return;
			let drawing_nos = flt(d.no_of_qty_to_manufacture);
			let total = flt(d.customer_provided_wt, 3);
			if (!drawing_nos || !total) return;
			let per_nos = flt(d.weight_per_pcs, 3) || flt(total / drawing_nos, 3);
			frappe.model.set_value(cdt, cdn, "custom_sec_uom", "Nos");
			frappe.model.set_value(cdt, cdn, "custom_customer_weight_kg", total);
			frappe.model.set_value(cdt, cdn, "custom_cust_weight_per_nos", per_nos);
			if (flt(row.custom_sec_qty) > 0) {
				frappe.model.set_value(cdt, cdn, "planned_qty",
					flt(total * flt(row.custom_sec_qty) / drawing_nos, 3));
			}
		}
	);
}

function _pp_autofill_operations(frm, bom_no) {
	if (!bom_no) return;
	frappe.call({
		method: "manufyxinvenzaerp.production_plan_management.production_plan.get_operations_from_routing",
		args: { bom_no: bom_no },
		callback(r) {
			if (!r.message || !r.message.length) return;
			let existing = new Set(
				(frm.doc.custom_process_planning || []).map(row => row.operation_name)
			);
			r.message.forEach(function(op) {
				if (!existing.has(op)) {
					let new_row = frm.add_child("custom_process_planning");
					new_row.operation_name = op;
					existing.add(op);
				}
			});
			frm.refresh_field("custom_process_planning");
		},
	});
}

function _pp_autofill_from_standard_routing(frm) {
	frappe.call({
		method: "manufyxinvenzaerp.production_plan_management.production_plan.get_standard_routing_operations",
		callback(r) {
			if (!r.message || !r.message.length) return;
			// Double-check still empty (user may have added rows while call was in-flight)
			if (frm.doc.custom_process_planning && frm.doc.custom_process_planning.length) return;
			r.message.forEach(function(op) {
				let row = frm.add_child("custom_process_planning");
				row.operation_name = op;
			});
			frm.refresh_field("custom_process_planning");
		},
	});
}


// ── PP Drawings Picker Dialog ─────────────────────────────────────────────────

function _show_pp_drawings_picker(frm) {
	let _all_rows = [];
	let _search_mode = "sales_order"; // or "material_planning" -- Sales Order is the default (client change request Phase 3.1)

	let d = new frappe.ui.Dialog({
		title: __("Add Drawings to Production Plan"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "Select",
				fieldname: "search_mode",
				label: __("Search By"),
				options: "Material Planning\nSales Order",
				default: "Sales Order",
				change() {
					_search_mode = d.get_value("search_mode") === "Sales Order"
						? "sales_order" : "material_planning";
					_all_rows = [];
					_ppd_render_results(d, [], _search_mode, frm.doc.name);
					// Toggle link fields
					d.set_df_property("mp_value", "hidden",
						_search_mode === "material_planning" ? 0 : 1);
					d.set_df_property("so_value", "hidden",
						_search_mode === "sales_order" ? 0 : 1);
					d.refresh();
				},
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Link",
				fieldname: "mp_value",
				label: __("Material Planning"),
				options: "Material Planning",
				hidden: 1,
			},
			{
				fieldtype: "Link",
				fieldname: "so_value",
				label: __("Sales Order"),
				options: "Sales Order",
				hidden: 0,
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Button",
				fieldname: "search_btn",
				label: __("Search"),
				click() {
					_ppd_do_search(frm, d, _search_mode, function(rows) {
						_all_rows = rows;
						_ppd_render_results(d, rows, _search_mode, frm.doc.name);
					});
				},
			},
			{ fieldtype: "Section Break" },
			{
				fieldtype: "HTML",
				fieldname: "results_html",
			},
		],
		primary_action_label: __("Insert Selected"),
		primary_action() {
			_ppd_do_insert(frm, d, _all_rows);
		},
	});

	_ppd_render_results(d, [], _search_mode, frm.doc.name);
	d.show();
}


function _ppd_do_search(frm, d, search_mode, on_done) {
	let value = search_mode === "material_planning"
		? d.get_value("mp_value")
		: d.get_value("so_value");

	if (!value) {
		frappe.msgprint(__(
			search_mode === "material_planning"
				? "Select a Material Planning first."
				: "Select a Sales Order first."
		));
		return;
	}

	frappe.call({
		method: "manufyxinvenzaerp.production_plan_management.production_plan.get_pp_drawings_for_picker",
		args: {
			search_type: search_mode,
			search_value: value,
			pp_name: frm.doc.name || "",
		},
		freeze: true,
		freeze_message: __("Loading drawings…"),
		callback(r) {
			let rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint(__("No drawings found."));
				on_done([]);
				return;
			}
			on_done(rows);
		},
		error() {
			on_done([]);
		},
	});
}


function _ppd_render_results(d, all_rows, search_mode, pp_name) {
	let $wrap = d.fields_dict["results_html"]
		&& d.fields_dict["results_html"].$wrapper;
	if (!$wrap) return;

	if (!all_rows || !all_rows.length) {
		$wrap.html(
			`<div style="color:#8d99a6;padding:20px 8px;text-align:center;font-size:12px;">
				${__("Use the search controls above to load drawings.")}
			</div>`
		);
		return;
	}

	// Split into categories
	let free_rows    = all_rows.filter(r => !r.already_in_this_pp && !r.already_in_pp && r.mp_complete);
	let this_pp_rows = all_rows.filter(r => r.already_in_this_pp);
	let other_pp_rows = all_rows.filter(r => !r.already_in_this_pp && r.already_in_pp);
	let incomplete_rows = all_rows.filter(r => !r.already_in_this_pp && !r.already_in_pp && !r.mp_complete);

	// Stamp _orig_idx only on free rows (used to retrieve the row on Insert)
	free_rows.forEach((r, i) => { r._orig_idx = i; });

	let show_mp_col = true; // always show Material Planning column

	// Column header helper — free rows have no Reference column; disabled tables do
	let header_cols = _ppd_header_cols(show_mp_col, false, undefined, undefined, false);

	// Section: selectable free rows
	let free_html = _ppd_free_rows_html(free_rows, show_mp_col);

	let _ref_min = _ppd_min_width(true);

	// Section: incomplete MP rows
	let incomplete_html = "";
	if (incomplete_rows.length) {
		incomplete_html = `
			<div style="margin-top:14px;" id="_ppd_incomplete_section">
				<div style="font-size:12px;font-weight:600;color:#c62828;padding:6px 4px 4px;display:flex;align-items:center;gap:6px;">
					<span>&#9888;</span>
					${__("{0} drawing(s) blocked — MP not yet processed", [incomplete_rows.length])}
				</div>
				<div style="overflow-x:auto;">
					<div style="min-width:${_ref_min}px;">
						${_ppd_header_cols(show_mp_col, true, undefined, undefined, true)}
						<div id="_ppd_incomplete_list" style="border:1px solid #ffcdd2;border-top:none;border-radius:0 0 4px 4px;max-height:25vh;overflow-y:auto;">
							${_ppd_disabled_rows_html(incomplete_rows, show_mp_col, "incomplete", "")}
						</div>
					</div>
				</div>
			</div>`;
	}

	// Section: already in this PP
	let this_pp_html = "";
	if (this_pp_rows.length) {
		this_pp_html = `
			<div style="margin-top:14px;" id="_ppd_this_pp_section">
				<div style="font-size:12px;font-weight:600;color:#2e7d32;padding:6px 4px 4px;display:flex;align-items:center;gap:6px;">
					<span>&#10003;</span>
					${__("{0} drawing(s) already in this Production Plan", [this_pp_rows.length])}
				</div>
				<div style="overflow-x:auto;">
					<div style="min-width:${_ref_min}px;">
						${_ppd_header_cols(show_mp_col, false, "#e8f5e9", "#c8e6c9", true)}
						<div id="_ppd_this_pp_list" style="border:1px solid #c8e6c9;border-top:none;border-radius:0 0 4px 4px;max-height:25vh;overflow-y:auto;">
							${_ppd_disabled_rows_html(this_pp_rows, show_mp_col, "this_pp", pp_name || "")}
						</div>
					</div>
				</div>
			</div>`;
	}

	// Section: in another PP
	let other_pp_html = "";
	if (other_pp_rows.length) {
		other_pp_html = `
			<div style="margin-top:14px;" id="_ppd_other_pp_section">
				<div style="font-size:12px;font-weight:600;color:#e65100;padding:6px 4px 4px;display:flex;align-items:center;gap:6px;">
					<span>&#9888;</span>
					${__("{0} drawing(s) fully planned in other Production Plans — no pieces left", [other_pp_rows.length])}
				</div>
				<div style="overflow-x:auto;">
					<div style="min-width:${_ref_min}px;">
						${_ppd_header_cols(show_mp_col, false, "#fff3e0", "#ffe0b2", true)}
						<div id="_ppd_other_pp_list" style="border:1px solid #ffe0b2;border-top:none;border-radius:0 0 4px 4px;max-height:25vh;overflow-y:auto;">
							${_ppd_disabled_rows_html(other_pp_rows, show_mp_col, "other_pp", "")}
						</div>
					</div>
				</div>
			</div>`;
	}

	let mp_filter_col = show_mp_col ? `
		<div style="display:flex;flex-direction:column;gap:3px;min-width:100px;">
			<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Material Planning")}</label>
			<input id="_ppd_f_mp" type="text" placeholder="${__("Filter…")}"
				style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
		</div>` : "";

	let html = `
		<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px;padding:8px 10px;background:#f8f9fa;border:1px solid #e9ecef;border-radius:4px;">
			<div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:130px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Customer Drawing No")}</label>
				<input id="_ppd_f_cdn" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;min-width:80px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("DUNO / Mark No")}</label>
				<input id="_ppd_f_duno" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:120px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Item Name")}</label>
				<input id="_ppd_f_item" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;min-width:90px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Sales Order")}</label>
				<input id="_ppd_f_so" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:100px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Customer")}</label>
				<input id="_ppd_f_cust" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			${mp_filter_col}
			<div style="display:flex;flex-direction:column;gap:3px;align-items:flex-start;justify-content:flex-end;padding-bottom:1px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">&nbsp;</label>
				<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
					<button class="btn btn-xs" id="_ppd_sel_all"
						style="background:#2e7d32;color:#fff;border-color:#2e7d32;">${__("Select All")}</button>
					<button class="btn btn-xs btn-default" id="_ppd_unsel_all">${__("Unselect All")}</button>
					<button class="btn btn-xs" id="_ppd_clear_filter"
						style="background:#c62828;color:#fff;border-color:#c62828;">${__("Clear Filters")}</button>
					<label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;color:#495057;margin:0;white-space:nowrap;">
						<input type="checkbox" id="_ppd_search_all" style="cursor:pointer;">
						${__("Search all tables")}
					</label>
					<span id="_ppd_count" style="font-size:12px;color:#6c757d;white-space:nowrap;"></span>
				</div>
			</div>
		</div>
		<div id="_ppd_free_section">
			<div style="overflow-x:auto;">
				<div style="min-width:${_ppd_min_width(false)}px;">
					${header_cols}
					<div id="_ppd_free_list"
						style="max-height:35vh;overflow-y:auto;border:1px solid #e9ecef;border-top:none;border-radius:0 0 4px 4px;">
						${free_html}
					</div>
				</div>
			</div>
		</div>
		${incomplete_html}
		${this_pp_html}
		${other_pp_html}`;

	$wrap.html(html);

	// Wire up events
	function _count() {
		let total   = $wrap.find(".ppd-chk").length;
		let checked = $wrap.find(".ppd-chk:checked").length;
		$wrap.find("#_ppd_count").text(checked + " / " + total + " " + __("selected"));
	}

	function _get_filters() {
		return {
			cdn:  ($wrap.find("#_ppd_f_cdn").val()  || "").toLowerCase().trim(),
			duno: ($wrap.find("#_ppd_f_duno").val() || "").toLowerCase().trim(),
			item: ($wrap.find("#_ppd_f_item").val() || "").toLowerCase().trim(),
			so:   ($wrap.find("#_ppd_f_so").val()   || "").toLowerCase().trim(),
			cust: ($wrap.find("#_ppd_f_cust").val() || "").toLowerCase().trim(),
			mp:   ($wrap.find("#_ppd_f_mp").val()   || "").toLowerCase().trim(),
		};
	}

	function _row_matches(r, f) {
		return (!f.cdn  || String(r.customer_drawing_number || "").toLowerCase().includes(f.cdn))
			&& (!f.duno || String(r.duno_mark_no || "").toLowerCase().includes(f.duno))
			&& (!f.item || String(r.item_name || "").toLowerCase().includes(f.item))
			&& (!f.so   || String(r.sales_order || "").toLowerCase().includes(f.so))
			&& (!f.cust || (String(r.customer_name || "") + " " + String(r.customer || "")).toLowerCase().includes(f.cust))
			&& (!f.mp   || String(r.material_planning || "").toLowerCase().includes(f.mp));
	}

	function _apply_filter() {
		// Preserve checked state before re-render
		let checked_set = new Set();
		$wrap.find(".ppd-chk").each(function() {
			if ($(this).prop("checked")) checked_set.add(parseInt($(this).data("orig")));
		});

		let f = _get_filters();
		let visible = free_rows.filter(r => _row_matches(r, f));
		$wrap.find("#_ppd_free_list").html(_ppd_free_rows_html(visible, show_mp_col));

		// Restore checked state
		$wrap.find(".ppd-chk").each(function() {
			if (checked_set.has(parseInt($(this).data("orig")))) {
				$(this).prop("checked", true);
			}
		});

		// Optionally filter disabled tables
		let search_all = $wrap.find("#_ppd_search_all").prop("checked");
		if (search_all) {
			let has_filter = Object.values(f).some(v => v);
			if ($wrap.find("#_ppd_this_pp_list").length) {
				let vis = has_filter ? this_pp_rows.filter(r => _row_matches(r, f)) : this_pp_rows;
				$wrap.find("#_ppd_this_pp_list").html(_ppd_disabled_rows_html(vis, show_mp_col, "this_pp", pp_name || ""));
			}
			if ($wrap.find("#_ppd_other_pp_list").length) {
				let vis = has_filter ? other_pp_rows.filter(r => _row_matches(r, f)) : other_pp_rows;
				$wrap.find("#_ppd_other_pp_list").html(_ppd_disabled_rows_html(vis, show_mp_col, "other_pp", ""));
			}
			if ($wrap.find("#_ppd_incomplete_list").length) {
				let vis = has_filter ? incomplete_rows.filter(r => _row_matches(r, f)) : incomplete_rows;
				$wrap.find("#_ppd_incomplete_list").html(_ppd_disabled_rows_html(vis, show_mp_col, "incomplete", ""));
			}
		} else {
			// Restore all disabled rows to full (unfiltered) when checkbox is unchecked
			if ($wrap.find("#_ppd_this_pp_list").length)
				$wrap.find("#_ppd_this_pp_list").html(_ppd_disabled_rows_html(this_pp_rows, show_mp_col, "this_pp", pp_name || ""));
			if ($wrap.find("#_ppd_other_pp_list").length)
				$wrap.find("#_ppd_other_pp_list").html(_ppd_disabled_rows_html(other_pp_rows, show_mp_col, "other_pp", ""));
			if ($wrap.find("#_ppd_incomplete_list").length)
				$wrap.find("#_ppd_incomplete_list").html(_ppd_disabled_rows_html(incomplete_rows, show_mp_col, "incomplete", ""));
		}

		_count();
	}

	const _filter_selector = "#_ppd_f_cdn, #_ppd_f_duno, #_ppd_f_item, #_ppd_f_so, #_ppd_f_cust, #_ppd_f_mp";
	$wrap.on("input",  _filter_selector, _apply_filter);
	$wrap.on("change", ".ppd-chk",       _count);
	$wrap.on("change", "#_ppd_search_all", _apply_filter);
	$wrap.on("click",  "#_ppd_clear_filter", function() {
		$wrap.find(_filter_selector).val("");
		_apply_filter();
	});
	$wrap.on("click",  "#_ppd_sel_all", function() {
		$wrap.find(".ppd-chk").prop("checked", true);
		_count();
	});
	$wrap.on("click", "#_ppd_unsel_all", function() {
		$wrap.find(".ppd-chk").prop("checked", false);
		_count();
	});

	_count();
}


// Pixel widths for each column (all fixed — enables reliable horizontal scroll)
const _PPD_COLS = [
	{ label: "",              w: 20,  key: "chk"  },
	{ label: "Drawing No",   w: 155, key: "cdn"  },
	{ label: "DUNO/Mark",    w: 70,  key: "duno" },
	{ label: "Item Name",    w: 120, key: "item" },
	{ label: "Sales Order",  w: 155, key: "so"   },
	{ label: "Customer",     w: 95,  key: "cust" },
	{ label: "Mat. Planning",w: 110, key: "mp"   },
	{ label: "Nos Left",     w: 70,  key: "qty", align: "center" },
];
// "left / drawing" in pieces for a drawing row, e.g. "6 / 10": a drawing can be
// split over several plans (D16), so what matters is what is still unplanned.
function _ppd_qty_text(r) {
	if (r.fg_nos_tracked) {
		return String(flt(r.nos_left || 0, 3)) + " / " + String(flt(r.drawing_nos || 0, 3));
	}
	return String(flt(r.qty_to_manufacture || 0, 2));
}

const _PPD_COL_GAP = 8;   // gap between columns
const _PPD_PAD     = 8;   // left/right padding inside header and rows

function _ppd_min_width(include_ref) {
	let w = _PPD_COLS.reduce((s, c) => s + c.w, 0)
	        + (_PPD_COLS.length - 1) * _PPD_COL_GAP
	        + 2 * _PPD_PAD;
	if (include_ref) w += _PPD_COL_GAP + 140; // Reference column
	return w;
}

function _ppd_col_widths(show_mp_col, include_ref) {
	let cols = _PPD_COLS.map(c => ({ ...c, flex: `0 0 ${c.w}px` }));
	if (include_ref) cols.push({ label: "Reference", w: 140, flex: "0 0 140px" });
	return cols;
}


function _ppd_header_cols(show_mp_col, is_warning, bg_color, border_color, include_ref) {
	bg_color     = bg_color     || "#f4f5f7";
	border_color = border_color || "#e9ecef";
	let color = is_warning ? "#c62828" : "#6c757d";
	let cols  = _PPD_COLS.slice(); // copy base columns
	if (include_ref) cols.push({ label: "Reference", w: 140 });
	let spans = cols.map(c => {
		let align = c.align === "center" ? "text-align:center;" : "";
		// first col (checkbox) gets no label
		if (c.key === "chk") return `<span style="flex:0 0 ${c.w}px;"></span>`;
		return `<span style="flex:0 0 ${c.w}px;font-size:11px;font-weight:600;color:${color};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;${align}">${__(c.label)}</span>`;
	}).join("");
	return `<div style="display:flex;gap:${_PPD_COL_GAP}px;padding:6px ${_PPD_PAD}px;background:${bg_color};border:1px solid ${border_color};border-radius:4px 4px 0 0;">${spans}</div>`;
}


function _ppd_cell(val, col, extra_style) {
	let align = col.align === "center" ? "text-align:center;" : "";
	return `<span style="flex:0 0 ${col.w}px;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;${align}${extra_style || ""}" title="${val}">${val}</span>`;
}

function _ppd_free_rows_html(rows, show_mp_col) {
	if (!rows.length) {
		return `<div style="color:#6c757d;padding:12px 8px;font-size:12px;">${__("No drawings match.")}</div>`;
	}
	let [C_CHK, C_CDN, C_DUNO, C_ITEM, C_SO, C_CUST, C_MP, C_QTY] = _PPD_COLS;
	return rows.map(function(r) {
		let cdn  = frappe.utils.escape_html(r.customer_drawing_number || "—");
		let duno = frappe.utils.escape_html(String(r.duno_mark_no || "—"));
		let item = frappe.utils.escape_html(r.item_name || r.item_code || "");
		let so   = frappe.utils.escape_html(r.sales_order || "—");
		let cust = frappe.utils.escape_html(r.customer_name || r.customer || "");
		let mp   = frappe.utils.escape_html(r.material_planning || "—");
		let qty  = _ppd_qty_text(r);
		return `<label style="display:flex;align-items:center;gap:${_PPD_COL_GAP}px;padding:6px ${_PPD_PAD}px;cursor:pointer;border-bottom:1px solid #f0f0f0;user-select:none;">
			<input type="checkbox" class="ppd-chk" data-orig="${r._orig_idx}" style="flex:0 0 ${C_CHK.w}px;width:${C_CHK.w}px;height:${C_CHK.w}px;cursor:pointer;">
			${_ppd_cell(cdn,  C_CDN,  "font-size:12px;font-weight:500;color:#212529;")}
			${_ppd_cell(duno, C_DUNO, "font-size:12px;color:#495057;")}
			${_ppd_cell(item, C_ITEM, "color:#495057;")}
			${_ppd_cell(so,   C_SO,   "color:#6c757d;")}
			${_ppd_cell(cust, C_CUST, "color:#6c757d;")}
			${_ppd_cell(mp,   C_MP,   "color:#6c757d;")}
			${_ppd_cell(qty,  C_QTY,  "color:#6c757d;")}
		</label>`;
	}).join("");
}


function _ppd_disabled_rows_html(rows, show_mp_col, type, pp_name) {
	let [C_CHK, C_CDN, C_DUNO, C_ITEM, C_SO, C_CUST, C_MP, C_QTY] = _PPD_COLS;
	let C_REF = { w: 140 };
	return rows.map(function(r) {
		let cdn  = frappe.utils.escape_html(r.customer_drawing_number || "—");
		let duno = frappe.utils.escape_html(String(r.duno_mark_no || "—"));
		let item = frappe.utils.escape_html(r.item_name || r.item_code || "");
		let so   = frappe.utils.escape_html(r.sales_order || "—");
		let cust = frappe.utils.escape_html(r.customer_name || r.customer || "");
		let mp   = frappe.utils.escape_html(r.material_planning || "—");
		let qty  = _ppd_qty_text(r);

		let badge = "";
		let chk_checked = "";
		let chk_opacity = "opacity:0.4;";
		let tc = "#bbb"; // default text colour

		if (type === "this_pp") {
			let ref = frappe.utils.escape_html(pp_name || "");
			// No tick — just show the PP reference number
			badge = `<span style="flex:0 0 ${C_REF.w}px;font-size:11px;color:#2e7d32;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${ref}">${ref}</span>`;
			chk_checked = "checked";
			chk_opacity = "opacity:0.6;";
			tc = "#555";
		} else if (type === "other_pp") {
			let ref = frappe.utils.escape_html(r.already_in_pp || "");
			badge = `<span style="flex:0 0 ${C_REF.w}px;font-size:11px;color:#e65100;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${ref}">${ref}</span>`;
		} else if (type === "incomplete") {
			badge = `<span style="flex:0 0 ${C_REF.w}px;font-size:11px;color:#c62828;font-weight:600;">${__("MP not processed")}</span>`;
		}

		return `<div style="display:flex;align-items:center;gap:${_PPD_COL_GAP}px;padding:6px ${_PPD_PAD}px;border-bottom:1px solid #f0f0f0;background:#fafafa;">
			<input type="checkbox" disabled ${chk_checked}
			       style="flex:0 0 ${C_CHK.w}px;width:${C_CHK.w}px;height:${C_CHK.w}px;cursor:not-allowed;${chk_opacity}">
			${_ppd_cell(cdn,  C_CDN,  `font-size:12px;font-weight:500;color:${tc};`)}
			${_ppd_cell(duno, C_DUNO, `font-size:12px;color:${tc};`)}
			${_ppd_cell(item, C_ITEM, `color:${tc};`)}
			${_ppd_cell(so,   C_SO,   `color:${tc};`)}
			${_ppd_cell(cust, C_CUST, `color:${tc};`)}
			${_ppd_cell(mp,   C_MP,   `color:${tc};`)}
			${_ppd_cell(qty,  C_QTY,  `color:${tc};`)}
			${badge}
		</div>`;
	}).join("");
}


function _ppd_do_insert(frm, d, all_rows) {
	// Only process free rows that are checked
	let free_rows = all_rows.filter(r => !r.already_in_this_pp && !r.already_in_pp && r.mp_complete);

	let selected = [];
	d.$body.find(".ppd-chk:checked").each(function() {
		let orig = parseInt($(this).data("orig"));
		if (!isNaN(orig) && free_rows[orig]) selected.push(free_rows[orig]);
	});

	if (!selected.length) {
		frappe.msgprint(__("Select at least one drawing to insert."));
		return;
	}

	// ── Warehouse consistency check ───────────────────────────────────────────
	let new_warehouses = [...new Set(selected.map(s => s.for_warehouse || ""))];
	if (new_warehouses.length > 1) {
		frappe.msgprint({
			title: __("Different Raw Material Warehouses"),
			message: __("Different raw material warehouses cannot be selected in one Production Plan. Please select drawings from the same warehouse only."),
			indicator: "red",
		});
		return;
	}
	let new_wh = new_warehouses[0] || "";
	let existing_wh = frm.doc.custom_raw_material_warehouse || "";
	if (existing_wh && new_wh && existing_wh !== new_wh) {
		frappe.msgprint({
			title: __("Different Raw Material Warehouses"),
			message: __("The drawings you selected use warehouse <b>{0}</b>, but this Production Plan already has warehouse <b>{1}</b> set. Different raw material warehouses cannot be used in one Production Plan.", [new_wh, existing_wh]),
			indicator: "red",
		});
		return;
	}

	// Remove Frappe's blank placeholder rows before inserting
	let grid = frm.fields_dict.po_items && frm.fields_dict.po_items.grid;
	if (grid) {
		(frm.doc.po_items || [])
			.filter(r => !r.item_code && !r.bom_no)
			.forEach(function(r) {
				let gr = (grid.grid_rows || []).find(x => x.doc && x.doc.name === r.name);
				if (gr) gr.remove();
			});
	}

	// Skip BOMs already in the table
	let existing_boms = new Set((frm.doc.po_items || []).map(r => r.bom_no).filter(Boolean));
	let to_add  = selected.filter(s => !existing_boms.has(s.bom_no));
	let skipped = selected.length - to_add.length;

	// Fetch per-drawing planned RM weights, keyed by "mp_name|duno_mark_no"
	let mp_duno_pairs = [...new Map(
		to_add.map(s => {
			let mp   = s.material_planning || "";
			let duno = s.duno_mark_no || "";
			return [mp + "|" + duno, { mp, duno }];
		})
	).values()];

	function _finish_insert(weights) {
		to_add.forEach(function(s) {
			let wt_key = (s.material_planning || "") + "|" + (s.duno_mark_no || "");
			let child = frm.add_child("po_items");
			child.item_code                      = s.item_code || "";
			child.item_name                      = s.item_name || "";
			child.bom_no                         = s.bom_no || "";
			child.stock_uom                      = s.uom || "";
			child.sales_order                    = s.sales_order || "";
			child.custom_customer                = s.customer || "";
			child.custom_drawing                 = s.drawing || "";
			child.custom_duno_mark_no            = s.duno_mark_no || "";
			child.custom_customer_drawing_number = s.customer_drawing_number || "";
			child.custom_material_planning       = s.material_planning || "";
			if (s.fg_nos_tracked) {
				// Planned in pieces (sep14 FG plan, D5/D16): default to every piece no
				// other plan has claimed. The Kg shown here mirrors the server, which
				// recalculates it on save (apply_fg_nos) -- the one place it is decided.
				child.custom_sec_qty             = flt(s.nos_left);
				child.custom_sec_uom             = "Nos";
				child.custom_customer_weight_kg  = flt(s.cust_weight_total, 3);
				child.custom_cust_weight_per_nos = flt(s.cust_weight_per_nos, 3);
				child.planned_qty                = s.drawing_nos
					? flt(flt(s.cust_weight_total) * flt(s.nos_left) / flt(s.drawing_nos), 3) : 0;
			} else {
				child.planned_qty                = flt(s.qty_to_manufacture) || 1;
			}
			child.custom_planned_rm_weight_kg    = flt(weights[wt_key] || 0, 3);
		});
		frm.refresh_field("po_items");

		if (new_wh) {
			frm.set_value("custom_raw_material_warehouse", new_wh);
		}

		d.hide();

		let msg = __("{0} drawing(s) added to Production Plan.", [to_add.length]);
		if (skipped) msg += "  " + __("{0} already in table — skipped.", [skipped]);
		frappe.show_alert({ message: msg, indicator: "green" }, 5);

		frm.save();
	}

	if (mp_duno_pairs.length) {
		frappe.call({
			method: "manufyxinvenzaerp.production_plan_management.production_plan.get_mp_planned_weights",
			args: { mp_duno_pairs: JSON.stringify(mp_duno_pairs) },
			callback: function(r) { _finish_insert(r.message || {}); },
			error:    function()  { _finish_insert({}); },
		});
	} else {
		_finish_insert({});
	}
}


// ── Process Planning Bulk Update Dialog ───────────────────────────────────────

function _show_bulk_update_dialog(frm) {
	if (!frm.doc.custom_process_planning || !frm.doc.custom_process_planning.length) {
		frappe.msgprint(__("No operations in the Process Planning table to update."));
		return;
	}

	let selected_type = null;

	let d = new frappe.ui.Dialog({
		title: __("Bulk Update – Work Type"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "bulk_options_html",
				options: `
<div style="padding: 12px 0;">
  <label style="display:flex;align-items:center;gap:10px;cursor:pointer;margin-bottom:14px;font-size:14px;">
    <input type="checkbox" id="_bulk_subcontractor" style="width:16px;height:16px;cursor:pointer;">
    <span>${__("All operations by Subcontractor")}</span>
  </label>
  <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:14px;">
    <input type="checkbox" id="_bulk_internal" style="width:16px;height:16px;cursor:pointer;">
    <span>${__("All operations by Internal Jobcard")}</span>
  </label>
</div>`,
			},
		],
		primary_action_label: __("Update"),
		primary_action() {
			if (!selected_type) {
				frappe.msgprint(__("Please select one option before updating."));
				return;
			}
			let work_type = selected_type === "subcontractor" ? "Subcontractor" : "Internal Jobcard";
			(frm.doc.custom_process_planning || []).forEach(function(row) {
				frappe.model.set_value(row.doctype, row.name, "work_type", work_type);
			});
			frm.refresh_field("custom_process_planning");


			frm.save().then(function() {
				frappe.show_alert({ message: __("All rows updated to: {0}", [work_type]), indicator: "green" }, 4);
			});
			d.hide();
		},
	});

	d.show();

	// Mutually exclusive checkbox behaviour
	let $sub = d.$wrapper.find("#_bulk_subcontractor");
	let $int = d.$wrapper.find("#_bulk_internal");

	$sub.on("change", function() {
		if ($sub.prop("checked")) {
			$int.prop("checked", false);
			selected_type = "subcontractor";
		} else {
			selected_type = null;
		}
	});
	$int.on("change", function() {
		if ($int.prop("checked")) {
			$sub.prop("checked", false);
			selected_type = "internal";
		} else {
			selected_type = null;
		}
	});
}
