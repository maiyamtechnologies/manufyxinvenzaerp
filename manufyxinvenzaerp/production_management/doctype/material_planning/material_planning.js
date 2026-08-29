// ── Upload / Download helper for child table toolbars ──────────────────────
function _add_io_buttons(frm, fieldname) {
	var grid = frm.fields_dict[fieldname] && frm.fields_dict[fieldname].grid;
	if (!grid) return;

	// Download — export current rows as CSV
	var $dl = grid.add_custom_button(
		__("Download"),
		function () {
			var rows = frm.doc[fieldname] || [];
			if (!rows.length) { frappe.msgprint(__("No data to download.")); return; }
			var cols = (grid.docfields || []).filter(function (f) {
				return f.fieldtype !== "Column Break" && f.fieldtype !== "Section Break"
					&& f.fieldtype !== "Button" && f.in_list_view;
			});
			if (!cols.length) {
				cols = (grid.docfields || []).filter(function (f) {
					return f.fieldtype !== "Column Break" && f.fieldtype !== "Section Break" && f.fieldtype !== "Button";
				});
			}
			var headers = cols.map(function (f) { return f.label || f.fieldname; });
			var lines = [headers.join(",")];
			rows.forEach(function (row) {
				var vals = cols.map(function (f) {
					var v = String(row[f.fieldname] === null || row[f.fieldname] === undefined ? "" : row[f.fieldname]);
					if (v.indexOf(",") >= 0 || v.indexOf("\n") >= 0 || v.indexOf('"') >= 0) {
						v = '"' + v.replace(/"/g, '""') + '"';
					}
					return v;
				});
				lines.push(vals.join(","));
			});
			var blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
			var url = URL.createObjectURL(blob);
			var a = document.createElement("a");
			a.href = url; a.download = fieldname + ".csv";
			document.body.appendChild(a); a.click();
			document.body.removeChild(a); URL.revokeObjectURL(url);
		}
	);
	// default button style (no color override)

	// Upload — commented out (not yet active)
	// var $ul = grid.add_custom_button(
	// 	__("Upload"),
	// 	function () {
	// 		var $input = $('<input type="file" accept=".csv" style="display:none">');
	// 		$input.on("change", function () {
	// 			var file = this.files[0];
	// 			if (!file) return;
	// 			var reader = new FileReader();
	// 			reader.onload = function (e) {
	// 				var text = e.target.result;
	// 				var lines = text.split(/\r?\n/).filter(function (l) { return l.trim(); });
	// 				if (lines.length < 2) {
	// 					frappe.msgprint(__("CSV must have a header row and at least one data row."));
	// 					return;
	// 				}
	// 				var headers = lines[0].split(",").map(function (h) { return h.trim().toLowerCase().replace(/ /g, "_"); });
	// 				var cols = grid.docfields || [];
	// 				var header_map = {};
	// 				headers.forEach(function (h, i) {
	// 					var match = cols.find(function (f) {
	// 						return f.fieldname === h || (f.label || "").toLowerCase().replace(/ /g, "_") === h;
	// 					});
	// 					if (match) header_map[i] = match.fieldname;
	// 				});
	// 				var added = 0;
	// 				for (var r = 1; r < lines.length; r++) {
	// 					var vals = lines[r].split(",");
	// 					var child = frm.add_child(fieldname);
	// 					vals.forEach(function (v, i) { if (header_map[i]) child[header_map[i]] = v.trim(); });
	// 					added++;
	// 				}
	// 				frm.refresh_field(fieldname);
	// 				frappe.show_alert({ message: __("{0} row(s) added.", [added]), indicator: "green" }, 4);
	// 			};
	// 			reader.readAsText(file);
	// 		});
	// 		$input.trigger("click");
	// 	}
	// );
}

// Every Status that means "this row has material against it" — including rows
// fulfilled from another job's excess, which may carry no batch for weeks while
// the off-cut is still at the supplier. Mirrors MAPPED_BATCH_STATUSES in
// material_planning.py, last two entries being the pre-rename spellings kept so
// documents saved before the rename still total correctly.
// Must match MAPPED_BATCH_STATUSES in material_planning.py exactly — that tuple is
// the source of truth, and this is a hand-copy of it for the form's own sums.
// tests/verify_mapped_status_lists_match.py compares the two and fails if they drift.
//
// They did drift: "Cut Sheet Mapped" was added on the server and not here, so the
// form's Difference in Kg silently skipped every cut-sheet row. On MP-2026-00042
// that hid the whole difference — three cut-sheet rows carrying 1,131.822 Kg of
// excess, reported as "+0.000 Kg (17 of 20 mapped)" while the Job Work Order, which
// totals server-side, showed the 1,131.822 correctly. Two documents disagreeing
// about the same number, with the correct one nowhere on the plan itself.
const _MP_MAPPED_STATUSES = [
	"Mapped",
	"Excess Mapped",
	"Excess Mapped (At Supplier)",
	"Excess Mapped (Pending Return)",
	"Cut Sheet Mapped",
	"Virtual (At Supplier)",
	"Claimed (Pending Return)",
];

function _MP_IS_MAPPED_STATUS(value) {
	return _MP_MAPPED_STATUSES.indexOf(value) !== -1;
}

function _update_weight_summary(frm) {
	let total_raw = 0;
	(frm.doc.raw_materials || []).forEach(r => {
		let g = r.parent_item_group || "";
		if (g === "Structurals" || g === "Plates") total_raw += flt(r.qty);
	});

	let total_exact = 0;
	(frm.doc.available_raw_materials || []).forEach(r => { total_exact += flt(r.required_qty); });

	let expected_mapping = 0;
	let cross_mapped = 0;
	let mapping_rows = frm.doc.material_mapping || [];
	mapping_rows.forEach(r => {
		expected_mapping += flt(r.qty);
		cross_mapped    += flt(r.batch_calc_qty);
	});

	// Diff: only consider rows that have been mapped
	let mapped_expected = 0;
	let mapped_cross    = 0;
	mapping_rows.forEach(r => {
		if (_MP_IS_MAPPED_STATUS(r.batch_mapped)) {
			mapped_expected += flt(r.qty);
			mapped_cross    += flt(r.batch_calc_qty);
		}
	});

	let diff = mapped_cross - mapped_expected;

	frm.set_value("total_weight_plates_structurals", flt(total_raw, 3));
	frm.set_value("weight_exact_raw_material",       flt(total_exact, 3));
	frm.set_value("expected_weight_material_mapping", flt(expected_mapping, 3));
	frm.set_value("weight_cross_item_mapped",         flt(cross_mapped, 3));

	// Render the coloured difference HTML
	let $wrap = frm.fields_dict["diff_weight_html"] && frm.fields_dict["diff_weight_html"].$wrapper;
	if (!$wrap) return;

	let html = "";

	// Show difference as soon as at least one Material Mapping row is mapped
	let any_mapped = mapping_rows.some(r => _MP_IS_MAPPED_STATUS(r.batch_mapped));

	if (!any_mapped) {
		$wrap.html("");
		return;
	}

	if (!mapped_expected && !mapped_cross) {
		$wrap.html("");
		return;
	}

	let sign    = diff >= 0 ? "+" : "";
	let color   = diff >= 0 ? "#2e7d32" : "#c62828";
	let val_str = sign + flt(diff, 3).toFixed(3) + " Kg";

	let mapped_count = mapping_rows.filter(r => _MP_IS_MAPPED_STATUS(r.batch_mapped)).length;
	let total_count  = mapping_rows.length;
	html = `<div style="margin-top:6px;">
		<label class="control-label" style="font-size:11px;color:#8d99a6;">
			Difference in Kg — Batch Mapped Items
			<span style="font-weight:400;color:#aaa;">(${mapped_count} of ${total_count} mapped)</span>
		</label>
		<div style="font-size:15px;font-weight:700;color:${color};margin-top:2px;">${val_str}</div>`;

	if (diff > 0) {
		html += `<div style="margin-top:8px;padding:8px 12px;background:#f1f8e9;border-left:3px solid #66bb6a;border-radius:3px;font-size:12px;color:#33691e;">
			<b>Excess material:</b> If this material is transferred to the supplier, ensure they return the excess quantity.
		</div>`;
	}
	html += "</div>";
	$wrap.html(html);
}

frappe.ui.form.on("Material Planning", {

	update_so_diff_btn(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Please save the document before updating the Sales Order."));
			return;
		}
		frappe.call({
			method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.update_so_difference_kg",
			args: { mp_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Updating Difference Kg in Sales Order…"),
			callback(r) {
				if (r.message) {
					frappe.show_alert({
						message: __("{0} Sales Order Drawing row(s) updated.", [r.message.updated]),
						indicator: "green",
					}, 5);
				}
			},
		});
	},

	refresh(frm) {
		// Both per-doctype manual buttons (this one and Material Issue Plan's) are
		// removed at the client's request in favour of one doctype-wise ERP Manual
		// page (production_management/page/erp_manual), added to a Workspace
		// separately rather than linked from here. The pages they used to open --
		// material-planning-manual and material-planning-case-studies -- have
		// since been deleted outright; ERP Manual is the only manual now.

		// Always keep the Stock Analysis tab visible regardless of table data
		frm.set_df_property("tab_stock_analysis", "hidden", 0); // fieldname stays, label changed to "Stock Details"
		frm.set_df_property("section_raw_materials", "hidden", 0);
		frm.set_df_property("section_available_raw_materials", "hidden", 0);
		frm.set_df_property("section_material_mapping", "hidden", 0);
		frm.set_df_property("section_unavailable_items", "hidden", 0);

		// BOM search: supports name, item, item_name, and DUNO/Mark No
		frm.set_query("bom_no", "bom_items", function() {
			return {
				query: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.search_bom",
			};
		});

		// Only batches holding stock in this plan's own Raw Materials Warehouse. With
		// no query at all the field offered every batch on the site, so a plan built for
		// one warehouse could be mapped to a batch sitting in another -- the reservation
		// went through, because a reservation is paper, and the stock check then
		// reported the whole requirement as a shortfall against a batch holding ten
		// tonnes in the wrong shed.
		//
		// Not filtered by item on purpose: satisfying an ISMB400 requirement from an
		// ISA100 bar is the cross-mapping this table is for.
		frm.set_query("batch", "material_mapping", function() {
			// Raw Materials Warehouse is not a mandatory field, and without it the list
			// is empty with nothing on screen to say why. Said once per form, not once
			// per keystroke.
			if (!frm.doc.for_warehouse && !frm._mfx_warned_no_wh) {
				frm._mfx_warned_no_wh = true;
				frappe.show_alert({
					message: __("Set the Raw Materials Warehouse first — batches are offered from it."),
					indicator: "orange",
				}, 7);
			}
			return {
				query: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.material_mapping_batch_query",
				filters: { warehouse: frm.doc.for_warehouse || "" },
			};
		});

		// Color-code Consolidate Item's "Difference (Required − Purchase)":
		// red when under-purchased (purchase < required, a positive
		// difference — still short), green when over-purchased (purchase >
		// required, a negative difference — surplus).
		//
		// NOTE: df.formatter (the usual custom-grid-cell-formatter extension
		// point) does NOT work here — frappe.form.formatters.Float never
		// calls _apply_custom_formatter at all (unlike Data/Select), so a
		// per-field formatter on a Float column is silently ignored by
		// Frappe's own grid renderer. Confirmed live: the pre-existing
		// batch_mapped status-pill formatter below uses the same df.formatter
		// pattern and only happens to work because that field is a Data
		// field, not Float. Styling the cell DOM directly after render is the
		// only mechanism that actually works for a Float column -- deferred
		// to the same setTimeout below the grid rows are already rendered.

		let has_raw = !!(frm.doc.raw_materials || []).length;
		let has_avail = !!(frm.doc.available_raw_materials || []).length;
		let has_mapping = !!(frm.doc.material_mapping || []).length;
		let has_unavail = !!(frm.doc.unavailable_items || []).length;

		// Button visibility
		frm.set_df_property("get_raw_materials_btn",  "hidden", 0);
		frm.set_df_property("verify_raw_materials_btn", "hidden", has_raw ? 0 : 1);
		frm.set_df_property("check_stock_btn",         "hidden", has_raw     ? 0 : 1);
		// "Update & Map Exact Matches" moved to the Consolidate Item grid
		// (client feedback) -- always hidden here now, regardless of
		// unavailable_items state.
		frm.set_df_property("update_exact_match_btn",  "hidden", 1);
		frm.set_df_property("finalize_mapping_btn",    "hidden", has_mapping ? 0 : 1);

		// Lock the SO picker and Show Drawings button once stock has been checked
		// (raw materials fetched + at least one stock analysis table populated)
		let so_locked = has_raw && (has_avail || has_mapping || has_unavail);
		frm.set_df_property("so_bom_import",     "read_only", so_locked ? 1 : 0);
		frm.set_df_property("show_drawings_btn", "hidden",    so_locked ? 1 : 0);

		// Add icons to inline form buttons (no color override)
		function _style_btn(fieldname, icon, label) {
			let $btn = frm.fields_dict[fieldname] && frm.fields_dict[fieldname].$input;
			if (!$btn || !$btn.length) return;
			$btn.html(frappe.utils.icon(icon, "sm") + "&nbsp;" + __(label));
		}
		setTimeout(function () {
			_style_btn("get_raw_materials_btn",  "refresh", "Get Raw Materials");
			_style_btn("verify_raw_materials_btn", "check", "Verify Raw Materials");
			_style_btn("check_stock_btn",        "search",  "Check Stock Availability");
			_style_btn("update_exact_match_btn", "tick",    "Update & Map Exact Matches");
			_style_btn("finalize_mapping_btn",   "move",    "Move to Unavailable Items");

			// "View All" injected next to each section's action button
			function _inject_view_all($anchor_input, css_class, fieldname) {
				if (!$anchor_input || !$anchor_input.length) return;
				$anchor_input.closest(".frappe-control").find("." + css_class).remove();
				let $va = $('<button class="btn btn-default btn-sm ' + css_class + '" style="margin-left:8px;"></button>');
				$va.html(frappe.utils.icon("eye", "sm") + "&nbsp;" + __("View All"));
				$va.on("click", function () { _show_table_popup(frm, fieldname); });
				$anchor_input.after($va);
			}

			let $raw_btn  = frm.fields_dict["get_raw_materials_btn"]  && frm.fields_dict["get_raw_materials_btn"].$input;
			let $chk_btn  = frm.fields_dict["check_stock_btn"]        && frm.fields_dict["check_stock_btn"].$input;
			let $fin_btn  = frm.fields_dict["finalize_mapping_btn"]   && frm.fields_dict["finalize_mapping_btn"].$input;
			let $upd_btn  = frm.fields_dict["update_exact_match_btn"] && frm.fields_dict["update_exact_match_btn"].$input;

			_inject_view_all($raw_btn,  "view-all-raw-btn", "raw_materials");
			_inject_view_all($chk_btn,  "view-all-arm-btn", "available_raw_materials");
			_inject_view_all($fin_btn,  "view-all-mm-btn",  "material_mapping");
			_inject_view_all($upd_btn,  "view-all-ui-btn",  "unavailable_items");
		}, 50);

		// Colour-coded Status badge on Material Mapping rows
		let _mm_meta = frappe.get_meta("Material Planning Material Mapping");
		if (_mm_meta && _mm_meta.fields) {
			let _status_df = _mm_meta.fields.find(function(f) { return f.fieldname === "batch_mapped"; });
			if (_status_df) {
				_status_df.formatter = function(value) {
					if (!value) return "";
					// Render the actual status. This used to print "Not Mapped" for
					// ANY value other than "Mapped", which meant a row fulfilled from
					// another job's excess — genuinely mapped, just with no batch
					// against it yet — was shown as if nothing had been done to it.
					let colour = value === "Mapped" ? "green"
						: _MP_IS_MAPPED_STATUS(value) ? "blue"
						: "red";
					return `<span class="indicator-pill ${colour}" style="display:inline-block;font-size:11px;padding:2px 8px">${__(value)}</span>`;
				};
			}
		}

		// Disable add/delete rows on all auto-populated tables
		["raw_materials", "available_raw_materials", "material_mapping", "unavailable_items"].forEach(function (tbl) {
			let g = frm.fields_dict[tbl] && frm.fields_dict[tbl].grid;
			if (!g) return;
			g.cannot_add_rows = true;
			g.df.cannot_delete_rows = true;
			g.refresh();
		});

		// Lock BOM Items once a Production Plan exists OR any stock is reserved
		let has_any_reserved = (frm.doc.available_raw_materials || []).some(r => r.is_reserved)
			|| (frm.doc.material_mapping || []).some(r => r.is_reserved);

		if (frm.doc.production_plan || has_any_reserved) {
			frm.set_df_property("bom_items", "read_only", 1);
			let bom_grid = frm.fields_dict["bom_items"] && frm.fields_dict["bom_items"].grid;
			if (bom_grid) {
				bom_grid.df.read_only = 1;
				bom_grid.cannot_add_rows = true;
				bom_grid.df.cannot_delete_rows = true;
				bom_grid.refresh();
			}
			if (has_any_reserved && !frm.doc.production_plan) {
				frm.set_df_property("bom_items", "description",
					"⚠ BOM Items are locked because stock is already reserved. Unreserve all batches before modifying BOMs.");
			}
		}

		// Grid toolbar buttons — guard against duplicates on re-render
		if (!frm._grid_btns_added) {
			frm._grid_btns_added = true;

			// Upload/Download on all four tables
			["raw_materials", "available_raw_materials", "material_mapping", "unavailable_items"].forEach(function (tbl) {
				_add_io_buttons(frm, tbl);
			});



			// Reserve / Unreserve on Material Mapping (Alternate Stock)
			_add_reservation_buttons(frm);

			// Reserve / Unreserve on Available Raw Materials (Exact Match)
			_add_exact_match_reservation_buttons(frm);

			// Create Material Request — moved from Unavailable Items to Consolidate
			// Item (client change request Phase 2.4): Consolidate Item is now the
			// purchasing-facing table, deduped by item_code across every drawing.
			if (frm.fields_dict["consolidate_items"]) {
				frm.fields_dict["consolidate_items"].grid.add_custom_button(
					frappe.utils.icon("buying", "xs") + " " + __("Create Material Request"),
					function () { _show_consolidate_material_request_dialog(frm); }
				);
				// "Update & Map Exact Matches" — moved here from Unavailable Items
				// (client feedback): for every Consolidate Item row not already
				// covered by an active Material Request, drop the row and re-check
				// stock against the underlying Unavailable Item rows, updating
				// Available Raw Materials / Material Mapping accordingly.
				frm.fields_dict["consolidate_items"].grid.add_custom_button(
					frappe.utils.icon("tick", "xs") + " " + __("Update & Map Exact Matches"),
					function () { _update_exact_match_from_consolidate(frm); }
				);
			}

			// Auto Purchase section — visible only when Manufyxinvenza Settings enables it
			frappe.db.get_single_value("Manufyxinvenza Settings", "auto_purchase_from_material_planning")
				.then(function(enabled) {
					if (!enabled) return;
					frm.set_df_property("custom_auto_purchase_section",           "hidden", 0);
					frm.set_df_property("custom_auto_suggest_dimensions_btn",     "hidden", 0);
					frm.set_df_property("custom_auto_purchase_supplier",          "hidden", 0);
					frm.refresh_fields(["custom_auto_purchase_section", "custom_auto_suggest_dimensions_btn",
						"custom_auto_purchase_supplier", "custom_auto_purchase_btn"]);
				});
		}

		_update_weight_summary(frm);

		// "Create → Production Plan" was here, and was the only button in the Create
		// group -- withdrawn at the client's request on 2026-08-26: the Production Plan
		// is raised by hand, and picking its drawings there rather than inheriting every
		// BOM on the plan is the point. Nothing else changes; the plan is still what the
		// Production Plan's own drawing picker reads from.
		//
		// The server method it called, make_production_plan, is deliberately left in
		// place: it is whitelisted, covered by test_e2e_material_planning, and is what
		// this would be rebuilt on if the button is ever wanted back.

		// ── Check Mapping ───────────────────────────────────────────────────
		//
		// Status is no longer set by hand. It follows the reservations on every save
		// (_auto_update_planning_status), in both directions -- so "Batch Mapping
		// Completed" cannot outlive the reservations that earned it, which is how
		// MP-2026-00010 came to read complete with none of its six rows reserved.
		//
		// The deeper checks that button used to run are still worth having, so they
		// live on here under a name that says what they do. Reopen Mapping is gone:
		// unreserve a row and the status falls on its own.
		if (!frm.doc.__islocal && frm.doc.docstatus !== 2) {
			frm.add_custom_button(__("Check Mapping"), function () {
				_run_batch_mapping_complete(frm);
			});
		}

		// ── Validate Stock — planned Kg / Sec Nos per item, for reference ───
		if (!frm.doc.__islocal) {
			frm.add_custom_button(__("Validate Stock"), function () {
				_show_planned_stock_validation(frm);
			});
		}
	},
});

// Reference view of everything this plan has committed, per item + batch: how
// many Kg and how many Sec Nos, against what the batch actually holds. A
// fractional Sec Nos total is highlighted rather than hidden — it means several
// drawings share that bar/sheet, and someone has to decide at transfer time
// whether to hand over the lower or the higher whole piece count.
function _show_planned_stock_validation(frm) {
	frappe.call({
		method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.validate_planned_stock",
		args: { material_planning_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Checking planned stock…"),
		callback(r) {
			let rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint({
					title: __("Validate Stock"),
					message: __("No batches are assigned on this plan yet."),
					indicator: "orange",
				});
				return;
			}

			// Full width, no horizontal scrollbar: only the two text columns are
			// allowed to wrap, every numeric column is nowrap + right-aligned so
			// the whole table settles inside the extra-large dialog.
			let num = "text-align:right;white-space:nowrap;";
			let html = '<table class="table table-bordered table-condensed" style="font-size:12px;width:100%;table-layout:auto;margin-bottom:0;">';
			html += "<thead><tr>" + [
				[__("Item"), ""], [__("Batch"), ""], [__("Planned Kg"), num],
				[__("Planned Sec Nos"), num], [__("Drawings"), num],
				[__("Batch Stock (Kg)"), num], [__("Short By"), num],
			].map(([h, st]) => '<th style="' + st + '">' + h + "</th>").join("") + "</tr></thead><tbody>";

			rows.forEach(function (d) {
				let sec = d.is_fractional
					? '<span style="color:#b45309;font-weight:600;">' + flt(d.planned_sec_qty, 3) +
					  "</span> <span class='text-muted'>(" + __("or {0} whole", [flt(d.whole_sec_qty, 0)]) + ")</span>"
					: flt(d.planned_sec_qty, 3);
				let short = d.short_by > 0
					? '<span style="color:#b91c1c;font-weight:600;">' + flt(d.short_by, 3) + "</span>"
					: "—";
				html += "<tr>" +
					'<td style="white-space:nowrap;">' + frappe.utils.escape_html(d.item_code) + "</td>" +
					'<td style="word-break:break-all;">' + frappe.utils.escape_html(d.batch) + "</td>" +
					'<td style="' + num + '">' + flt(d.planned_qty, 3) + "</td>" +
					'<td style="' + num + '">' + sec + "</td>" +
					'<td style="' + num + '">' + d.drawings + "</td>" +
					'<td style="' + num + '">' + flt(d.batch_stock_qty, 3) + "</td>" +
					'<td style="' + num + '">' + short + "</td>" +
					"</tr>";
			});
			html += "</tbody></table>";

			let fractional = rows.filter((d) => d.is_fractional).length;
			let short_rows = rows.filter((d) => d.short_by > 0).length;
			let notes = [];
			if (fractional) {
				notes.push(__("{0} item(s) have a fractional Sec Nos — one batch shared across several drawings. Choose whole pieces when you transfer; the surplus is recorded as excess to return.", [fractional]));
			}
			if (short_rows) {
				notes.push(__("{0} item(s) need more Kg than the batch currently holds.", [short_rows]));
			}
			if (notes.length) {
				html += '<p class="text-muted" style="margin-top:10px;">' + notes.join("<br>") + "</p>";
			}

			// A plain msgprint caps its own width and forces the table to scroll
			// sideways; an extra-large Dialog fits every column on screen.
			let dlg = new frappe.ui.Dialog({
				title: __("Validate Stock"),
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "content" }],
			});
			dlg.fields_dict.content.$wrapper.html(html);
			dlg.show();
		},
	});
}

// ── Batch Mapping Completed — run validation then set status ────────────────
function _run_batch_mapping_complete(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the document first — the check runs against what is stored."));
		return;
	}
	frappe.call({
		method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.complete_batch_mapping",
		args: { mp_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Validating batch mapping…"),
		callback(r) {
			if (!r.message) return;
			let d = r.message;
			if (d.status === "ok") {
				frappe.msgprint({
					title: __("Mapping Is Sound"),
					indicator: "green",
					message: __("No overlapping or over-allocated batches, and nothing left unmapped.") +
						"<br><br>" +
						__("This plan's status is <b>{0}</b>, which follows the reservations by itself — reserve every row and it reads Batch Mapping Completed; unreserve one and it goes back to Working.", [d.planning_status || ""]),
				});
			} else {
				// Show issues in a formatted dialog
				let issue_html = d.issues.map(function(iss, i) {
					return `<tr>
						<td style="padding:4px 6px;vertical-align:top;color:#888">${i + 1}</td>
						<td style="padding:4px 6px">${iss}</td>
					</tr>`;
				}).join("");
				frappe.msgprint({
					title: __("{0} Issue(s) Found", [d.issues.length]),
					indicator: "red",
					message: `
						<p style="margin-bottom:8px">${__("The mapping on this plan has these problems:")}</p>
						<table style="width:100%;font-size:12px;border-collapse:collapse">
							<tbody>${issue_html}</tbody>
						</table>
						<p style="margin-top:10px;color:#555">${__("Fix them and run <b>Check Mapping</b> again. The status looks after itself — it reads Batch Mapping Completed once every row is reserved.")}</p>
					`,
				});
			}
		},
	});
}

// Batch availability warning popup shown before save
function _show_batch_warning_popup(warnings) {
	let lines = warnings.map(function(w) {
		return `<tr>
			<td>${w.idx || ""}</td>
			<td>${w.item_code}</td>
			<td>${w.item_name || ""}</td>
			<td>${w.batch}</td>
			<td>${w.required_qty} ${w.uom}</td>
			<td>${w.batch_stock} ${w.uom}</td>
			<td>${w.available_to_reserve} ${w.uom}</td>
			<td style="color:red;font-weight:bold">${w.shortfall_qty} ${w.uom}</td>
		</tr>`;
	}).join("");
	frappe.msgprint({
		title: __("Batch Stock Warning — Insufficient Stock"),
		indicator: "orange",
		message: `<p>${__("The following Material Mapping rows have insufficient batch stock for full reservation:")}</p>
			<table class="table table-bordered table-condensed" style="font-size:12px">
				<thead><tr>
					<th>${__("Row")}</th>
					<th>${__("Item Code")}</th>
					<th>${__("Item Name")}</th>
					<th>${__("Batch")}</th>
					<th>${__("Required")}</th>
					<th>${__("Batch Stock")}</th>
					<th>${__("Available to Reserve")}</th>
					<th>${__("Shortfall")}</th>
				</tr></thead>
				<tbody>${lines}</tbody>
			</table>
			<p class="text-muted" style="margin-top:8px">
				<b>${__("Action required:")}</b>
				${__("Assign a different batch with sufficient stock, or click")}
				<b>${__("Move to Unavailable Items")}</b>
				${__("to handle the shortfall separately.")}
			</p>`,
	});
}

frappe.ui.form.on("Material Planning", {
	after_save(frm) {
		// Show "Check Stock Availability" summary popup
		if (frm._check_stock_summary) {
			let s = frm._check_stock_summary;
			frm._check_stock_summary = null;

			let rows_html = `
				<table class="table table-bordered" style="font-size:13px;margin-top:8px;">
					<tbody>
						<tr style="background:#f6fff6;">
							<td style="padding:8px 12px;width:80%;">
								${__("Exact match found — added to <b>Available Raw Materials (Exact Match)</b>")}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;color:green;">${s.avail}</td>
						</tr>
						<tr style="background:${s.mapping ? "#fffbf0" : ""};">
							<td style="padding:8px 12px;">
								${__("Added to <b>Material Mapping (Alternate Stock)</b>")}
								${s.mapping ? `<br><span class="text-muted" style="font-size:11px;">
									${s.shortfall_mapping ? `<span style="color:#e65100;">&#9888; ${s.shortfall_mapping} row(s) from partial stock — NOS/Kg not fully available</span><br>` : ""}
									${__("Assign a batch manually to cover each row")}
								</span>` : ""}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;color:${s.mapping ? "orange" : "green"};">${s.mapping}</td>
						</tr>
						<tr style="background:${s.unavail ? "#fff5f5" : ""};">
							<td style="padding:8px 12px;">
								${__("Added to <b>Unavailable Items (No Stock — Needs Purchase)</b>")}
								${s.preserved_ordered ? `<br><span class="text-muted" style="font-size:11px;">
									${__("includes {0} row(s) left untouched — already on an active Material Request", [s.preserved_ordered])}
								</span>` : ""}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;color:${s.unavail ? "red" : "green"};">${s.unavail}</td>
						</tr>
					</tbody>
				</table>
				${s.avail ? `<div style="margin-top:10px;padding:8px 12px;background:#e8f4fd;border-left:4px solid #2490ef;border-radius:3px;font-size:12px;">
					<b>${__("Next step:")}</b> ${__("Reserve stock against <b>Available Raw Materials (Exact Match)</b> before proceeding, to lock the matched batches and avoid duplication across other Material Plans.")}
				</div>` : ""}`;

			frappe.msgprint({
				title: __("Check Stock Availability — Summary"),
				indicator: s.avail ? "green" : (s.mapping ? "orange" : "red"),
				message: rows_html,
			});
			return;
		}

		// Show "Move to Unavailable Items" summary popup
		if (frm._finalize_mapping_summary) {
			let s = frm._finalize_mapping_summary;
			frm._finalize_mapping_summary = null;

			let reservation_detail = "";
			if (s.mapped) {
				reservation_detail = `
					<div style="margin-top:6px;display:flex;gap:12px;flex-wrap:wrap;">
						<span style="font-size:11px;background:#e8f5e9;color:#2e7d32;padding:3px 8px;border-radius:10px;font-weight:600;">
							&#10003; ${s.reserved} Reserved
						</span>
						<span style="font-size:11px;background:${s.not_reserved ? "#fff8e1" : "#e8f5e9"};color:${s.not_reserved ? "#e65100" : "#2e7d32"};padding:3px 8px;border-radius:10px;font-weight:600;">
							&#9675; ${s.not_reserved} Not Reserved
						</span>
					</div>
					${s.not_reserved ? `<div style="margin-top:6px;font-size:11px;color:#e65100;padding:4px 0;">
						&#9888; Reserve the unresolved batches to avoid duplication mapping across other Material Plans.
					</div>` : ""}`;
			}

			let rows_html = `
				<table class="table table-bordered" style="font-size:13px;margin-top:8px;">
					<tbody>
						<tr style="background:${s.mapped ? "#f6fff6" : ""};">
							<td style="padding:8px 12px;width:80%;">
								${__("Rows remaining in <b>Material Mapping (Alternate Stock)</b>")}
								<br><span class="text-muted" style="font-size:11px;">${s.mapped} batch${s.mapped !== 1 ? "es" : ""} assigned</span>
								${reservation_detail}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;color:${s.mapped ? "green" : ""};">${s.mapped}</td>
						</tr>
						<tr style="background:${s.unavail ? "#fff5f5" : ""};">
							<td style="padding:8px 12px;">
								${__("Moved to <b>Unavailable Items (No Stock — Needs Purchase)</b>")}
								${s.unavail ? `<br><span class="text-muted" style="font-size:11px;">${__("No batch assigned — create a Material Request to purchase")}</span>` : ""}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;color:${s.unavail ? "red" : "green"};">${s.unavail}</td>
						</tr>
					</tbody>
				</table>
				${_split_details_html(s.split_details)}`;

			frappe.msgprint({
				title: __("Move to Unavailable Items — Summary"),
				indicator: s.unavail ? "orange" : "green",
				message: rows_html,
			});
			return;
		}

		// Show "Update Exact Match" summary popup if stashed by the button handler
		if (frm._update_exact_summary) {
			let s = frm._update_exact_summary;
			frm._update_exact_summary = null;

			let arm_added = s.arm_rows_added;
			let row_range = "";
			if (arm_added === 1) {
				row_range = __("{0} row added to Exact Match table", [arm_added]);
			} else if (arm_added > 1) {
				row_range = __("{0} rows added to Exact Match table", [arm_added]);
			}

			let rows_html = `
				<table class="table table-bordered" style="font-size:13px;margin-top:8px;">
					<tbody>
						<tr>
							<td style="padding:8px 12px;width:80%;">
								${__("Total items checked from <b>Unavailable Items</b>")}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;">${s.unavail_total}</td>
						</tr>
						<tr style="background:#f6fff6;">
							<td style="padding:8px 12px;">
								${__("Exact match found — added to <b>Available Raw Materials (Exact Match)</b>")}
								${row_range ? `<br><span class="text-muted" style="font-size:11px;">(${row_range})</span>` : ""}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;color:green;">${s.matched_count}</td>
						</tr>
						<tr style="background:${s.mapping_added ? "#fffbf0" : ""};">
							<td style="padding:8px 12px;">
								${__("Added to <b>Material Mapping (Alternate Stock)</b>")}
								${s.mapping_added ? `<br><span class="text-muted" style="font-size:11px;">${__("Batch items with no exact match — assign a batch manually")}</span>` : ""}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;color:${s.mapping_added ? "orange" : "green"};">${s.mapping_added}</td>
						</tr>
						<tr style="background:${s.still_unavail ? "#fff5f5" : ""};">
							<td style="padding:8px 12px;">
								${__("Kept in <b>Unavailable Items (No Stock — Needs Purchase)</b>")}
								${s.still_unavail ? `<br><span class="text-muted" style="font-size:11px;">${__("Non-batch items with insufficient stock — create a Material Request")}</span>` : ""}
							</td>
							<td style="padding:8px 12px;font-weight:700;text-align:center;color:${s.still_unavail ? "red" : "green"};">${s.still_unavail}</td>
						</tr>
					</tbody>
				</table>`;

			frappe.msgprint({
				title: __("Update Exact Match — Summary"),
				indicator: s.matched_count ? "green" : (s.still_unavail ? "red" : "orange"),
				message: rows_html,
			});
			return; // skip batch warning check this save cycle
		}

		// Batch stock warning after any other save that has mapping rows
		if (!frm.doc.for_warehouse) return;
		let has_unresolved = (frm.doc.material_mapping || []).some(r => r.batch);
		if (!has_unresolved) return;

		frappe.call({
			method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.check_mapping_batch_availability",
			args: { doc: frm.doc },
			callback(r) {
				let warnings = (r && r.message) || [];
				if (warnings.length) {
					_show_batch_warning_popup(warnings);
				}
			},
		});
	},
});

// Cross-check Sec Qty (Nos) vs Qty (Kg) on raw_materials — shared by the
// automatic run after "Get Raw Materials" and the standalone "Verify Raw
// Materials" button next to it.
function _run_verify_raw_materials(frm, opts) {
	opts = opts || {};
	frappe.call({
		method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.verify_raw_materials",
		args: { doc: frm.doc },
		freeze: !opts.silent_freeze,
		freeze_message: __("Verifying Nos vs Qty…"),
		callback(r) {
			if (!r.message) return;
			let { checked, issues } = r.message;

			if (!issues.length) {
				let msg = opts.success_message || __("All {0} row(s) verified — Nos and Qty match.", [checked]);
				frappe.show_alert({ message: msg, indicator: "green" }, 5);
				return;
			}

			let rows_html = issues.map(function(row) {
				let formula_cell = row.formula_ok
					? `<span style="color:#888;">—</span>`
					: `<span style="color:#c0392b;font-weight:600;">${__("Expected")} ${row.checked_field === "sec_qty" ? "Sec Qty" : "Qty"} = ${row.formula_expected}</span>`;
				let so_cell = row.so_expected_sec_qty === null
					? `<span style="color:#888;">—</span>`
					: (row.so_ok
						? `<span style="color:#2e7d32;">${__("OK")}</span>`
						: `<span style="color:#c0392b;font-weight:600;">${__("SO requires Sec Qty")} = ${row.so_expected_sec_qty}</span>`);
				return `<tr>
					<td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">${row.idx}</td>
					<td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">${frappe.utils.escape_html(row.item_number)}</td>
					<td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">${frappe.utils.escape_html(row.item_code || "")}</td>
					<td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">${frappe.utils.escape_html(row.customer_drawing_number)}</td>
					<td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">${row.sec_qty}</td>
					<td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">${row.qty}</td>
					<td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">${formula_cell}</td>
					<td style="padding:5px 10px;border-bottom:1px solid #f0f0f0;">${so_cell}</td>
				</tr>`;
			}).join("");

			let html = `<div style="overflow:auto;max-height:60vh;">
				<table style="font-size:12px;border-collapse:collapse;width:100%;">
					<thead><tr style="background:#f4f5f7;">
						<th style="padding:6px 10px;text-align:left;">${__("Row")}</th>
						<th style="padding:6px 10px;text-align:left;">${__("Item No")}</th>
						<th style="padding:6px 10px;text-align:left;">${__("Material Code")}</th>
						<th style="padding:6px 10px;text-align:left;">${__("Drawing")}</th>
						<th style="padding:6px 10px;text-align:left;">${__("Sec Qty (Nos)")}</th>
						<th style="padding:6px 10px;text-align:left;">${__("Qty (Kg)")}</th>
						<th style="padding:6px 10px;text-align:left;">${__("Formula Check")}</th>
						<th style="padding:6px 10px;text-align:left;">${__("Sales Order Check")}</th>
					</tr></thead>
					<tbody>${rows_html}</tbody>
				</table>
			</div>`;

			let d = new frappe.ui.Dialog({
				title: __("{0} of {1} row(s) need attention", [issues.length, checked]),
				size: "extra-large",
			});
			d.$body.html(html);
			d.show();
		},
	});
}

frappe.ui.form.on("Material Planning", {
	check_stock_btn(frm) {
		if (!frm.doc.for_warehouse) {
			frappe.msgprint(__("Set 'Raw Materials Warehouse' before checking stock."));
			return;
		}
		if (!(frm.doc.raw_materials || []).length) {
			frappe.msgprint(__("Get Raw Materials first before checking stock."));
			return;
		}

		let _run = function() {
			frappe.call({
				method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.check_stock_availability",
				args: { doc: frm.doc },
				freeze: true,
				freeze_message: __("Checking stock…"),
				callback(r) {
					if (!r.message) return;
					let result = r.message;

					frm.clear_table("raw_materials");
					(result.raw_materials || []).forEach(function(row) {
						let child = frm.add_child("raw_materials");
						Object.keys(row).forEach(function(k) { if (k !== "name" && k !== "idx") child[k] = row[k]; });
					});
					frm.refresh_field("raw_materials");

					frm.clear_table("available_raw_materials");
					(result.available_raw_materials || []).forEach(function(row) {
						let child = frm.add_child("available_raw_materials");
						Object.keys(row).forEach(function(k) { if (k !== "name" && k !== "idx") child[k] = row[k]; });
					});
					frm.refresh_field("available_raw_materials");

					frm.clear_table("material_mapping");
					(result.material_mapping || []).forEach(function(row) {
						let child = frm.add_child("material_mapping");
						Object.keys(row).forEach(function(k) { if (k !== "name" && k !== "idx") child[k] = row[k]; });
						if (!child.batch_mapped) child.batch_mapped = child.batch ? "Mapped" : "Not Mapped";
					});
					frm.refresh_field("material_mapping");

					frm.clear_table("unavailable_items");
					(result.unavailable_items || []).forEach(function(row) {
						let child = frm.add_child("unavailable_items");
						Object.keys(row).forEach(function(k) { if (k !== "name" && k !== "idx") child[k] = row[k]; });
					});
					frm.refresh_field("unavailable_items");

					let mapping = (result.material_mapping || []).length;
					let unavail = (result.unavailable_items || []).length;
					let avail   = (result.available_raw_materials || []).length;
					let shortfall_mapping = result.shortfall_mapping_count || 0;

					frm.set_df_property("finalize_mapping_btn",   "hidden", mapping  ? 0 : 1);
					frm.set_df_property("update_exact_match_btn", "hidden", 1);

					_update_weight_summary(frm);

					// Stash summary for after_save popup
					frm._check_stock_summary = {
						avail, mapping, unavail, shortfall_mapping,
						preserved_ordered: result.preserved_ordered_count || 0,
					};
					frm.save();
				},
			});
		};

		let has_exact_reserved   = (frm.doc.available_raw_materials || []).some(r => r.is_reserved);
		let has_mapping_reserved = (frm.doc.material_mapping || []).some(r => r.is_reserved);
		if (has_exact_reserved || has_mapping_reserved) {
			let which = [];
			if (has_exact_reserved)   which.push(__("<b>Available Raw Materials (Exact Match)</b>"));
			if (has_mapping_reserved) which.push(__("<b>Material Mapping (Alternate Stock)</b>"));
			frappe.msgprint({
				title: __("Cannot Re-check Stock"),
				indicator: "red",
				message: __("Stocks are already reserved in: {0}. Unreserve all reservations before re-checking.", [which.join(", ")]),
			});
			return;
		}

		// Evaluate all conditions up front and show ONE combined confirm
		let has_exact_batch = (frm.doc.available_raw_materials || []).some(r => r.batch_no);
		let has_work        = (frm.doc.material_mapping || []).length || (frm.doc.unavailable_items || []).length;
		let has_reserved    = (frm.doc.material_mapping || []).some(r => r.is_reserved);

		if (!has_exact_batch && !has_work) {
			_run();
			return;
		}

		let points = [];
		if (has_exact_batch) {
			points.push(__("Batches already mapped in <b>Available Raw Materials (Exact Match)</b> will be updated."));
		}
		if (has_work && has_reserved) {
			points.push(__("All mapping work in <b>Material Mapping</b> including <b>RESERVED rows</b> will be cleared — unreserve first if you want to keep them."));
		} else if (has_work) {
			points.push(__("All current mapping work in <b>Material Mapping</b> and <b>Unavailable Items</b> will be cleared."));
		}

		let msg = "<p>" + __("Re-checking stock will do the following:") + "</p><ul style='margin:6px 0 0 16px;'>"
			+ points.map(p => `<li style="margin-bottom:4px;">${p}</li>`).join("")
			+ "</ul><p style='margin-top:8px;'>" + __("Continue?") + "</p>";

		frappe.confirm(msg, _run);
	},

	verify_raw_materials_btn(frm) {
		if (!(frm.doc.raw_materials || []).length) {
			frappe.msgprint(__("No raw materials to verify. Click 'Get Raw Materials' first."));
			return;
		}
		_run_verify_raw_materials(frm, {});
	},

	finalize_mapping_btn(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("There is unsaved changes, save it to move items to unavailable item table."));
			return;
		}
		if (!(frm.doc.material_mapping || []).length) {
			frappe.msgprint(__("No items in Material Mapping to finalize."));
			return;
		}
		// A row also qualifies for finalizing when it HAS a batch but under-covers
		// the requirement (Structurals/Plates only, not already reserved) — that
		// partial mapping's shortfall still needs to move to purchase.
		let unmapped = (frm.doc.material_mapping || []).filter(function(r) {
			if (!r.batch) return true;
			let group = r.batch_parent_item_group || r.parent_item_group || "";
			return !r.is_reserved && flt(r.sec_qty)
				&& (r.parent_item_group === "Structurals" || r.parent_item_group === "Plates")
				&& flt(r.batch_calc_qty) < flt(r.qty);
		});
		if (!unmapped.length) {
			frappe.msgprint(__("No items to move to purchase table, all are mapped."));
			return;
		}
		frappe.call({
			method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.finalize_mapping",
			args: { doc: frm.doc },
			freeze: true,
			freeze_message: __("Moving unmapped items to Unavailable…"),
			callback(r) {
				if (!r.message) return;
				let result = r.message;

				frm.clear_table("material_mapping");
				(result.material_mapping || []).forEach(function(row) {
					let child = frm.add_child("material_mapping");
					Object.keys(row).forEach(function(k) { if (k !== "name" && k !== "idx") child[k] = row[k]; });
					if (!child.batch_mapped) child.batch_mapped = child.batch ? "Mapped" : "Not Mapped";
				});
				frm.refresh_field("material_mapping");

				// Merge newly-unmapped rows with existing unavailable items
				// (de-duplicate by item_code+bom_no+duno_mark_no — omitting
				// duno_mark_no here would wrongly collapse the same item's
				// shortfalls from two different drawings into one row)
				let existing = (frm.doc.unavailable_items || []).filter(r => r.item_code);
				let dedup_key = r => `${r.item_code}|${r.bom_no || ""}|${r.duno_mark_no || ""}`;
				let existing_keys = new Set(existing.map(dedup_key));
				let new_rows = (result.unavailable_items || []).filter(r => !existing_keys.has(dedup_key(r)));
				frm.clear_table("unavailable_items");
				existing.concat(new_rows).forEach(function(row) {
					let child = frm.add_child("unavailable_items");
					Object.keys(row).forEach(function(k) { if (k !== "name" && k !== "idx") child[k] = row[k]; });
				});
				frm.refresh_field("unavailable_items");

				let mapped       = (result.material_mapping || []).length;
				let reserved     = (result.material_mapping || []).filter(r => r.is_reserved).length;
				let not_reserved = mapped - reserved;
				let unavail      = (frm.doc.unavailable_items || []).length;

				frm.set_df_property("finalize_mapping_btn",   "hidden", mapped  ? 0 : 1);
				frm.set_df_property("update_exact_match_btn", "hidden", 1);

				_update_weight_summary(frm);

				frm._finalize_mapping_summary = {
					mapped, reserved, not_reserved, unavail,
					split_details: result.split_details || [],
				};
				frm.save();
			},
		});
	},

	update_exact_match_btn(frm) {
		let all_items = frm.doc.unavailable_items || [];
		if (!all_items.length) {
			frappe.msgprint(__("No unavailable items to check."));
			return;
		}
		if (!frm.doc.for_warehouse) {
			frappe.msgprint(__("Set 'Raw Materials Warehouse' before checking stock."));
			return;
		}

		// Capture row count before adding so we can report which rows were appended
		let arm_before    = (frm.doc.available_raw_materials || []).length;
		let unavail_total = all_items.length;

		frappe.call({
			method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.move_to_exact_match",
			args: {
				doc: frm.doc,
				item_codes: JSON.stringify(all_items.map(r => r.item_code).filter(Boolean)),
			},
			freeze: true,
			freeze_message: __("Checking stock for unavailable items…"),
			callback(r) {
				if (!r.message) return;
				let { matched, failed, still_unavailable } = r.message;

				const SKIP_KEYS = new Set([
					"name", "idx", "doctype", "parent", "parenttype", "parentfield",
					"__islocal", "__dirty", "__run_link_triggers", "__unsaved",
				]);

				// Matched → add to Available Raw Materials (Exact Match)
				let matched_codes = new Set(matched.map(m => m.item_code));
				matched.forEach(function(row) {
					let child = frm.add_child("available_raw_materials");
					Object.keys(row).forEach(k => { if (k !== "name" && k !== "idx") child[k] = row[k]; });
				});
				frm.refresh_field("available_raw_materials");

				// Failed (batch items with no matching stock) → Material Mapping, assign batch manually
				let failed_set = new Set(failed || []);
				let failed_rows = all_items.filter(r => failed_set.has(r.item_code));
				failed_rows.forEach(function(row) {
					let child = frm.add_child("material_mapping");
					Object.keys(row).forEach(function(k) {
						if (!SKIP_KEYS.has(k)) child[k] = row[k];
					});
					child.batch_mapped = "Not Mapped";
					child.batch = "";
					child.planned_item = "";
				});
				frm.refresh_field("material_mapping");

				// Still unavailable (non-batch items with no plain stock) → stay in Unavailable Items
				let still_set = new Set(still_unavailable || []);
				let still_rows = all_items.filter(r => still_set.has(r.item_code));
				frm.clear_table("unavailable_items");
				still_rows.forEach(function(row) {
					let child = frm.add_child("unavailable_items");
					Object.keys(row).forEach(function(k) {
						if (!SKIP_KEYS.has(k)) child[k] = row[k];
					});
				});
				frm.refresh_field("unavailable_items");

				frm.set_df_property("update_exact_match_btn", "hidden", 1);
				frm.set_df_property("finalize_mapping_btn", "hidden",
					(frm.doc.material_mapping || []).length ? 0 : 1);

				_update_weight_summary(frm);

				// Stash summary so after_save can show the popup once the form is stable
				frm._update_exact_summary = {
					unavail_total:    unavail_total,
					matched_count:    all_items.filter(function(r) { return matched_codes.has(r.item_code); }).length,
					arm_rows_added:   matched.length,
					arm_before:       arm_before,
					mapping_added:    failed_rows.length,
					still_unavail:    still_rows.length,
				};

				frm.save();
			},
		});
	},

	get_raw_materials_btn(frm) {
		if (!frm.doc.bom_items || !frm.doc.bom_items.length) {
			frappe.msgprint(__("Add at least one BOM in the 'Selected BOMs' tab first."));
			return;
		}
		if (!frm.doc.company) {
			frappe.msgprint(__("Set Company before fetching raw materials."));
			return;
		}

		// Block immediately if any stock is reserved in either table
		let has_exact_reserved   = (frm.doc.available_raw_materials || []).some(r => r.is_reserved);
		let has_mapping_reserved = (frm.doc.material_mapping || []).some(r => r.is_reserved);
		if (has_exact_reserved || has_mapping_reserved) {
			let tables = [];
			if (has_exact_reserved)   tables.push(__("Available Raw Materials (Exact Match)"));
			if (has_mapping_reserved) tables.push(__("Material Mapping (Alternate Stock)"));
			frappe.msgprint({
				title: __("Cannot Refetch Raw Materials"),
				indicator: "red",
				message: __("Stock is already reserved in: <b>{0}</b>.<br>Unreserve it first before refetching raw materials.", [tables.join(", ")]),
			});
			return;
		}

		let _fetch = function() {
			frappe.call({
				method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.get_raw_materials",
				args: { doc: frm.doc },
				freeze: true,
				freeze_message: __("Exploding BOMs…"),
				callback(r) {
					if (!r.message) return;
					if (!r.message.length) {
						frappe.msgprint(__("No raw materials found. Check that the BOMs have sub-items."));
						return;
					}
					frm.clear_table("raw_materials");
					r.message.forEach(function(row) {
						let child = frm.add_child("raw_materials");
						Object.keys(row).forEach(function(k) {
							if (k !== "name" && k !== "idx") child[k] = row[k];
						});
					});
					frm.refresh_field("raw_materials");

					// Clear all stock-analysis tables — user must re-run Check Stock
					frm.clear_table("available_raw_materials");
					frm.refresh_field("available_raw_materials");
					frm.clear_table("material_mapping");
					frm.refresh_field("material_mapping");
					frm.clear_table("unavailable_items");
					frm.refresh_field("unavailable_items");

					frm.set_df_property("check_stock_btn",        "hidden", 0);
					frm.set_df_property("finalize_mapping_btn",   "hidden", 1);
					frm.set_df_property("update_exact_match_btn", "hidden", 1);

					_update_weight_summary(frm);

					_run_verify_raw_materials(frm, {
						silent_freeze: true,
						success_message: __("{0} raw material row(s) loaded — Nos and Qty verified OK.", [r.message.length]),
					});
					frm.save();
				},
			});
		};

		let has_any_data = (frm.doc.raw_materials || []).length
			|| (frm.doc.available_raw_materials || []).length
			|| (frm.doc.material_mapping || []).length
			|| (frm.doc.unavailable_items || []).length;

		if (!has_any_data) {
			_fetch();
			return;
		}

		// Check for active Material Requests linked to this plan before confirming --
		// lists ALL of them, not just the first found (a Material Planning can now
		// have multiple, one per supplier, from the multi-supplier consolidated
		// purchase flow).
		let has_unavail = (frm.doc.unavailable_items || []).length;
		let _check_mr_then_confirm = function() {
			if (!has_unavail || frm.doc.__islocal) {
				_show_confirm();
				return;
			}
			frappe.db.get_list(
				"Material Request",
				{ filters: { custom_material_planning: frm.doc.name, docstatus: ["!=", 2] }, fields: ["name"] }
			).then(function(rows) {
				if (rows && rows.length) {
					let links = rows.map((r) =>
						'<a href="/app/material-request/' + encodeURIComponent(r.name) + '">' + r.name + "</a>").join(", ");
					frappe.msgprint({
						title: __("Cannot Refetch Raw Materials"),
						indicator: "red",
						message: __("Material Request(s) {0} are already created against Unavailable Items.<br>Cancel them first before refetching raw materials.", [links]),
					});
					return;
				}
				_show_confirm();
			});
		};

		let _show_confirm = function() {
			frappe.confirm(
				__("This will replace the existing raw materials list.<br><br>"
					+ "Rows in <b>Available Raw Materials (Exact Match)</b>, "
					+ "<b>Material Mapping (Alternate Stock)</b>, and "
					+ "<b>Unavailable Items (No Stock — Needs Purchase)</b> "
					+ "will also be removed. Continue?"),
				_fetch
			);
		};

		_check_mr_then_confirm();
	},
});

// ── SO Drawing picker — "Show Drawings" button ───────────────────────────────

frappe.ui.form.on("Material Planning", {
	show_drawings_btn(frm) {
		let so = frm.doc.so_bom_import;
		if (!so) {
			frappe.msgprint(__("Select a Sales Order first."));
			return;
		}
		frappe.call({
			method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.get_so_drawings_for_bom_picker",
			args: { so_name: so, mp_name: frm.doc.name || "" },
			freeze: true,
			freeze_message: __("Loading drawings…"),
			callback(r) {
				let drawings = r.message || [];
				if (!drawings.length) {
					frappe.msgprint(__("No submitted BOMs found for Sales Order {0}.", [so]));
					return;
				}
				_show_drawings_picker_dialog(frm, so, drawings);
			},
		});
	},
});

function _show_drawings_picker_dialog(frm, so_name, drawings) {

	// Split into selectable (free) and already-mapped (used in another MP)
	var free_drawings = drawings.filter(function(d) { return !d.already_used_in; });
	var used_drawings = drawings.filter(function(d) { return !!d.already_used_in; });

	// Stamp _orig_idx only on free drawings (used in Insert action)
	free_drawings.forEach(function(d, i) { d._orig_idx = i; });

	function _free_rows_html(rows) {
		if (!rows.length) {
			return '<div style="color:#6c757d;padding:12px 8px;">' + __("No drawings match.") + "</div>";
		}
		return rows.map(function(d) {
			let cdn  = frappe.utils.escape_html(d.customer_drawing_number || "—");
			let duno = frappe.utils.escape_html(String(d.duno_mark_no || "—"));
			let bom  = frappe.utils.escape_html(d.bom_no || "");
			let item = frappe.utils.escape_html(d.item_name || d.item_code || "");
			return `<label style="display:flex;align-items:center;gap:10px;padding:6px 4px;cursor:pointer;border-bottom:1px solid #f0f0f0;user-select:none;">
				<input type="checkbox" class="mp-dchk" data-bom="${bom}" data-orig="${d._orig_idx}"
				       style="width:15px;height:15px;flex-shrink:0;cursor:pointer;" checked>
				<span style="flex:0 0 260px;font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${cdn}</span>
				<span style="flex:0 0 120px;font-size:12px;color:#495057;">${duno}</span>
				<span style="flex:0 0 130px;font-size:11px;color:#6c757d;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${item}</span>
				<span style="flex:1;font-size:11px;color:#aaa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${bom}</span>
			</label>`;
		}).join("");
	}

	function _used_rows_html(rows) {
		return rows.map(function(d) {
			let cdn     = frappe.utils.escape_html(d.customer_drawing_number || "—");
			let duno    = frappe.utils.escape_html(String(d.duno_mark_no || "—"));
			let bom     = frappe.utils.escape_html(d.bom_no || "");
			let item    = frappe.utils.escape_html(d.item_name || d.item_code || "");
			let used_in = frappe.utils.escape_html(d.already_used_in || "");
			return `<div style="display:flex;align-items:center;gap:10px;padding:6px 4px;border-bottom:1px solid #f0f0f0;background:#fafafa;">
				<input type="checkbox" disabled
				       style="width:15px;height:15px;flex-shrink:0;cursor:not-allowed;opacity:0.4;">
				<span style="flex:0 0 260px;font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#bbb;">${cdn}</span>
				<span style="flex:0 0 120px;font-size:12px;color:#bbb;">${duno}</span>
				<span style="flex:0 0 130px;font-size:11px;color:#bbb;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${item}</span>
				<span style="flex:1;font-size:11px;color:#ccc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${bom}</span>
				<span style="flex:0 0 160px;font-size:11px;color:#e65100;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
				      title="${used_in}">${used_in}</span>
			</div>`;
		}).join("");
	}

	let has_used = used_drawings.length > 0;
	let free_height = has_used ? "35vh" : "55vh";

	let header_html = `
		<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap;">
			<input id="_mpd_search" type="text" placeholder="${__("Search Customer Drawing ID or DUNO/Mark No…")}"
				style="flex:1;min-width:200px;border:1px solid #d1d8dd;border-radius:4px;padding:5px 10px;font-size:12px;">
			<button class="btn btn-xs btn-default" id="_mpd_sel_all">${__("Select All")}</button>
			<button class="btn btn-xs btn-default" id="_mpd_unsel_all">${__("Unselect All")}</button>
			<span id="_mpd_count" style="font-size:12px;color:#6c757d;"></span>
		</div>
		<div style="display:flex;gap:10px;padding:5px 4px;background:#f4f5f7;border-radius:4px;margin-bottom:4px;font-size:11px;font-weight:600;color:#6c757d;">
			<span style="flex:0 0 15px;"></span>
			<span style="flex:0 0 260px;">${__("Customer Drawing ID")}</span>
			<span style="flex:0 0 120px;">${__("DUNO / Mark No")}</span>
			<span style="flex:0 0 130px;">${__("Item Name")}</span>
			<span style="flex:1;">${__("BOM No")}</span>
		</div>`;

	let free_section_html = `<div id="_mpd_list"
		style="max-height:${free_height};overflow-y:auto;border:1px solid #e9ecef;border-radius:4px;padding:4px 8px;">
		${_free_rows_html(free_drawings)}
	</div>`;

	let used_section_html = "";
	if (has_used) {
		used_section_html = `
			<div style="margin-top:14px;">
				<div style="font-size:12px;font-weight:600;color:#e65100;padding:6px 4px 4px;display:flex;align-items:center;gap:6px;">
					<span>&#9888;</span>
					${__("{0} drawing(s) already mapped in another Material Planning — cannot be selected", [used_drawings.length])}
				</div>
				<div style="display:flex;gap:10px;padding:5px 4px;background:#fff3e0;border-radius:4px 4px 0 0;border:1px solid #ffe0b2;font-size:11px;font-weight:600;color:#6c757d;">
					<span style="flex:0 0 15px;"></span>
					<span style="flex:0 0 260px;">${__("Customer Drawing ID")}</span>
					<span style="flex:0 0 120px;">${__("DUNO / Mark No")}</span>
					<span style="flex:0 0 130px;">${__("Item Name")}</span>
					<span style="flex:1;">${__("BOM No")}</span>
					<span style="flex:0 0 160px;color:#e65100;">${__("Used In MP")}</span>
				</div>
				<div style="max-height:20vh;overflow-y:auto;border:1px solid #ffe0b2;border-top:none;border-radius:0 0 4px 4px;padding:4px 8px;">
					${_used_rows_html(used_drawings)}
				</div>
			</div>`;
	}

	let d = new frappe.ui.Dialog({
		title: __("Select Drawings — {0}", [so_name]),
		size: "extra-large",
		primary_action_label: __("Insert"),
		primary_action() {
			let selected = [];
			d.$body.find(".mp-dchk:checked").each(function() {
				let orig = parseInt($(this).data("orig"));
				if (!isNaN(orig)) selected.push(free_drawings[orig]);
			});

			if (!selected.length) {
				frappe.msgprint(__("Select at least one drawing."));
				return;
			}

			// Skip BOMs already in the table
			let existing = new Set((frm.doc.bom_items || []).map(r => r.bom_no));
			let to_add  = selected.filter(s => !existing.has(s.bom_no));
			let skipped = selected.length - to_add.length;

			to_add.forEach(function(s) {
				let child = frm.add_child("bom_items");
				child.bom_no                  = s.bom_no;
				child.item_code               = s.item_code  || "";
				child.item_name               = s.item_name  || "";
				child.drawing                 = s.drawing    || "";
				child.duno_mark_no            = s.duno_mark_no            || "";
				child.customer_drawing_number = s.customer_drawing_number || "";
				child.sales_order             = s.sales_order || "";
				child.customer                = s.customer   || "";
				child.qty_to_manufacture      = s.qty_to_manufacture || 1;
				child.uom                     = s.uom        || "";
			});
			frm.refresh_field("bom_items");

			d.hide();
			let msg = __("{0} BOM(s) added.", [to_add.length]);
			if (skipped) msg += "  " + __("{0} already in table — skipped.", [skipped]);
			frappe.show_alert({ message: msg, indicator: "green" }, 5);
		},
	});

	d.$body.html(header_html + free_section_html + used_section_html);

	function _update_count() {
		let total   = d.$body.find(".mp-dchk").length;
		let checked = d.$body.find(".mp-dchk:checked").length;
		d.$body.find("#_mpd_count").text(checked + " / " + total + " " + __("selected"));
	}

	function _apply_filter() {
		let q = (d.$body.find("#_mpd_search").val() || "").toLowerCase();
		let visible = q
			? free_drawings.filter(function(dd) {
				return String(dd.customer_drawing_number || "").toLowerCase().includes(q)
					|| String(dd.duno_mark_no || "").toLowerCase().includes(q)
					|| String(dd.bom_no || "").toLowerCase().includes(q)
					|| String(dd.item_name || "").toLowerCase().includes(q);
			})
			: free_drawings.slice();
		d.$body.find("#_mpd_list").html(_free_rows_html(visible));
		_update_count();
	}

	d.$body.on("input",  "#_mpd_search",  _apply_filter);
	d.$body.on("change", ".mp-dchk",      _update_count);
	d.$body.on("click",  "#_mpd_sel_all", function() {
		d.$body.find(".mp-dchk").prop("checked", true);
		_update_count();
	});
	d.$body.on("click", "#_mpd_unsel_all", function() {
		d.$body.find(".mp-dchk").prop("checked", false);
		_update_count();
	});

	_update_count();
	d.show();
}

// Auto-fill BOM row details from the linked Drawing when bom_no is set
frappe.ui.form.on("Material Planning BOM Item", {
	bom_no(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.bom_no) return;
		frappe.call({
			method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.get_bom_info",
			args: { bom_no: row.bom_no },
			callback(r) {
				if (!r.message) return;
				let d = r.message;
				frappe.model.set_value(cdt, cdn, "item_code",               d.item_code || "");
				frappe.model.set_value(cdt, cdn, "item_name",               d.item_name || "");
				frappe.model.set_value(cdt, cdn, "drawing",                 d.drawing || "");
				frappe.model.set_value(cdt, cdn, "duno_mark_no",            d.duno_mark_no || 0);
				frappe.model.set_value(cdt, cdn, "customer_drawing_number", d.customer_drawing_number || "");
				frappe.model.set_value(cdt, cdn, "sales_order",             d.sales_order || "");
				frappe.model.set_value(cdt, cdn, "customer",                d.customer || "");
				frappe.model.set_value(cdt, cdn, "qty_to_manufacture",      d.qty_to_manufacture || 0);
				frappe.model.set_value(cdt, cdn, "uom",                     d.uom || "");
			},
		});
	},
});

// Add to Mapping dialog — user assigns a batch per unavailable item
function _show_add_to_mapping_dialog(frm, selected_rows) {
	let fields = [];

	selected_rows.forEach(function (row, idx) {
		fields.push({
			fieldtype: "Section Break",
			label: `${row.item_code} — ${row.item_name || ""}`,
		});
		fields.push({
			fieldname: `batch_${idx}`,
			fieldtype: "Link",
			label: __("Assign Batch"),
			options: "Batch",
		});
	});

	let d = new frappe.ui.Dialog({
		title: __("Add to Material Mapping"),
		fields: fields,
		primary_action_label: __("Add"),
		primary_action(values) {
			let to_map = [];
			selected_rows.forEach(function (row, idx) {
				let batch = values[`batch_${idx}`];
				if (batch) to_map.push({ row: row, batch: batch });
			});

			if (!to_map.length) {
				frappe.msgprint(__("Assign at least one batch to proceed."));
				return;
			}

			let mapped_codes = new Set(to_map.map(m => m.row.item_code));

			// Add rows to material_mapping; use frappe.model.set_value for batch
			// so the existing "batch" field handler auto-fills planned_item
			const SKIP_KEYS = new Set([
				"name", "idx", "doctype", "parent", "parenttype", "parentfield",
				"__islocal", "__dirty", "__run_link_triggers", "__unsaved",
			]);
			to_map.forEach(function (m) {
				let child = frm.add_child("material_mapping");
				Object.keys(m.row).forEach(function (k) {
					if (!SKIP_KEYS.has(k)) child[k] = m.row[k];
				});
				// set_value triggers the batch → planned_item handler
				frappe.model.set_value(child.doctype, child.name, "batch", m.batch);
			});
			frm.refresh_field("material_mapping");

			// Remove mapped items from unavailable_items
			let remaining = (frm.doc.unavailable_items || []).filter(r => !mapped_codes.has(r.item_code));
			frm.clear_table("unavailable_items");
			remaining.forEach(function (row) {
				let child = frm.add_child("unavailable_items");
				Object.keys(row).forEach(function (k) {
					if (k !== "name" && k !== "idx") child[k] = row[k];
				});
			});
			frm.refresh_field("unavailable_items");

			// Update button visibility to match new table state
			let has_mapping  = !!(frm.doc.material_mapping   || []).length;
			let has_unavail  = !!(frm.doc.unavailable_items   || []).length;
			frm.set_df_property("finalize_mapping_btn",   "hidden", has_mapping  ? 0 : 1);
			frm.set_df_property("update_exact_match_btn", "hidden", 1);
			setTimeout(function () {
				let $fin = frm.fields_dict["finalize_mapping_btn"] && frm.fields_dict["finalize_mapping_btn"].$input;
				if ($fin && $fin.length) {
					$fin.html(frappe.utils.icon("move", "sm") + "&nbsp;" + __("Move to Unavailable Items"));
				}
			}, 50);

			d.hide();
			frappe.show_alert({
				message: __("{0} item(s) moved to Material Mapping.", [mapped_codes.size]),
				indicator: "blue",
			}, 5);
		},
	});

	d.show();
}

// Material Request creation dialog
function _show_material_request_dialog(frm) {
	let items = (frm.doc.unavailable_items || []).filter(r => r.item_code);
	if (!items.length) {
		frappe.msgprint(__("No unavailable items to request."));
		return;
	}
	if (frm.is_dirty()) {
		frm.save()
			.then(function() { _build_material_request_dialog(frm, items); })
			.catch(function() { frappe.msgprint(__("Please save the document successfully before creating a Material Request.")); });
	} else {
		_build_material_request_dialog(frm, items);
	}
}

function _build_material_request_dialog(frm, items) {

	let fields = [
		{
			fieldname: "items_section",
			fieldtype: "Section Break",
			label: __("Select Items to Request"),
			description: __("Tick the items you want to include in the Material Request."),
		},
	];

	items.forEach(function (row, idx) {
		let display_item = row.alternate_item ? row.alternate_item : `${row.item_code} — ${row.item_name || ""}`;
		let display_qty  = row.alternate_item && row.alternate_quantity
			? `${flt(row.alternate_quantity).toFixed(3)} Kg`
			: `${row.qty} ${row.uom || ""}`;
		let alt_suffix   = row.alternate_item ? ` (Alt for ${row.item_code})` : "";
		fields.push({
			fieldname: "item_" + idx,
			fieldtype: "Check",
			label: `${display_item} | Qty: ${display_qty}${alt_suffix}`,
			default: 1,
		});
	});

	let d = new frappe.ui.Dialog({
		title: __("Create Material Request"),
		fields: fields,
		primary_action_label: __("Create"),
		primary_action(values) {
			let selected = [];
			items.forEach(function (row, idx) {
				if (values["item_" + idx]) {
					selected.push(row.item_code);
				}
			});

			if (!selected.length) {
				frappe.msgprint(__("Select at least one item."));
				return;
			}

			frappe.call({
				method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.make_material_request",
				args: {
					material_planning_name: frm.doc.name,
					selected_items: JSON.stringify(selected),
				},
				freeze: true,
				freeze_message: __("Creating Material Request…"),
				callback(r) {
					if (r.message) {
						d.hide();
						frappe.show_alert({
							message: __("Material Request {0} created.", [r.message]),
							indicator: "green",
						}, 5);
						frappe.set_route("Form", "Material Request", r.message);
					}
				},
			});
		},
	});

	d.show();
}

// "Update & Map Exact Matches" — Consolidate Item version (client feedback:
// moved off Unavailable Items, which is now a collapsed staging section).
// Runs entirely server-side against the saved doc; just reload afterwards.
function _update_exact_match_from_consolidate(frm) {
	if (!(frm.doc.consolidate_items || []).length) {
		frappe.msgprint(__("No consolidated items to check."));
		return;
	}
	if (!frm.doc.for_warehouse) {
		frappe.msgprint(__("Set 'Raw Materials Warehouse' before checking stock."));
		return;
	}
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the document first."));
		return;
	}
	frappe.call({
		method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.update_exact_match_from_consolidate",
		args: { mp_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Checking stock for consolidated items…"),
		callback(r) {
			if (!r.message) return;
			let { checked, matched, moved_to_mapping, still_unavailable, skipped_ordered } = r.message;
			frm.reload_doc();
			let parts = [];
			if (matched) parts.push(__("{0} matched to Available Raw Materials", [matched]));
			if (moved_to_mapping) parts.push(__("{0} moved to Material Mapping (assign batch manually)", [moved_to_mapping]));
			if (still_unavailable) parts.push(__("{0} still unavailable", [still_unavailable]));
			if (skipped_ordered && skipped_ordered.length) {
				parts.push(__("{0} left as-is (already on an active Material Request)", [skipped_ordered.length]));
			}
			frappe.msgprint({
				title: __("Consolidated Stock Check"),
				indicator: "blue",
				message: (parts.length ? parts.join("<br>") : __("Nothing to update.")),
			});
		},
	});
}

// Material Request creation dialog — Consolidate Item version (client change
// request Phase 2.4). Mirrors _show_material_request_dialog/_build_material_request_dialog
// above, but sources rows from the deduped-by-item_code consolidate_items table
// and posts to make_material_request_from_consolidate instead.
function _show_consolidate_material_request_dialog(frm) {
	let items = (frm.doc.consolidate_items || []).filter(r => r.item_code);
	if (!items.length) {
		frappe.msgprint(__("No consolidated items to request."));
		return;
	}
	if (frm.is_dirty()) {
		frm.save()
			.then(function() { _build_consolidate_material_request_dialog(frm, items); })
			.catch(function() { frappe.msgprint(__("Please save the document successfully before creating a Material Request.")); });
	} else {
		_build_consolidate_material_request_dialog(frm, items);
	}
}

function _build_consolidate_material_request_dialog(frm, items) {
	let fields = [
		{
			fieldname: "items_section",
			fieldtype: "Section Break",
			label: __("Select Items to Request"),
			description: __("Tick the items you want to include in the Material Request."),
		},
	];

	items.forEach(function (row, idx) {
		let qty = flt(row.purchase_kg) || flt(row.required_kg);
		// Name the item that will actually be ORDERED. With an Alternate Item set,
		// make_material_request_from_consolidate raises the line for the alternate
		// and the Kg describes that alternate too -- labelling it with the original
		// item read as though the wrong thing was about to be bought.
		let label = row.alternate_item
			? `${row.alternate_item} | Qty: ${qty.toFixed(3)} Kg  (alternate for ${row.item_code})`
			: `${row.item_code} — ${row.item_name || ""} | Qty: ${qty.toFixed(3)} Kg`;
		fields.push({
			fieldname: "item_" + idx,
			fieldtype: "Check",
			label: label,
			default: 1,
		});
	});

	let d = new frappe.ui.Dialog({
		title: __("Create Material Request"),
		fields: fields,
		primary_action_label: __("Create"),
		primary_action(values) {
			let selected = [];
			items.forEach(function (row, idx) {
				if (values["item_" + idx]) {
					selected.push(row.item_code);
				}
			});

			if (!selected.length) {
				frappe.msgprint(__("Select at least one item."));
				return;
			}

			frappe.call({
				method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.make_material_request_from_consolidate",
				args: {
					material_planning_name: frm.doc.name,
					selected_items: JSON.stringify(selected),
				},
				freeze: true,
				freeze_message: __("Creating Material Request…"),
				callback(r) {
					if (r.message) {
						d.hide();
						frappe.show_alert({
							message: __("Material Request {0} created.", [r.message]),
							indicator: "green",
						}, 5);
						frappe.set_route("Form", "Material Request", r.message);
					}
				},
			});
		},
	});

	d.show();
}

// ── Alternate dimension UI helpers ───────────────────────────────────────────

function _apply_alternate_dim_ui(frm, cdt, cdn, group, child_doctype, grid_fieldname) {
	// child_doctype/grid_fieldname default to Unavailable Item's own for
	// backward compatibility with existing call sites; Consolidate Item's
	// alternate-item section (added alongside it) passes its own.
	child_doctype = child_doctype || "Material Planning Unavailable Item";
	grid_fieldname = grid_fieldname || "unavailable_items";

	let get_df = function(fn) {
		return frappe.meta.get_docfield(child_doctype, fn, frm.doc.name);
	};

	// Defaults: hide all, not required
	let cfg = {
		alternate_length:    { hidden: 1, reqd: 0 },
		alternate_width:     { hidden: 1, reqd: 0 },
		alternate_thickness: { hidden: 1, reqd: 0 },
		alternate_sec_qty:   { hidden: 1, reqd: 0 },
	};

	if (group === "Structurals") {
		cfg.alternate_length.hidden  = 0; cfg.alternate_length.reqd  = 1;
		cfg.alternate_sec_qty.hidden = 0; cfg.alternate_sec_qty.reqd = 1;
	} else if (group === "Plates") {
		cfg.alternate_length.hidden    = 0; cfg.alternate_length.reqd    = 1;
		cfg.alternate_width.hidden     = 0; cfg.alternate_width.reqd     = 1;
		cfg.alternate_thickness.hidden = 0; cfg.alternate_thickness.reqd = 1;
		cfg.alternate_sec_qty.hidden   = 0; cfg.alternate_sec_qty.reqd   = 1;
	}

	Object.keys(cfg).forEach(function(fn) {
		let df = get_df(fn);
		if (df) { df.hidden = cfg[fn].hidden; df.reqd = cfg[fn].reqd; }
	});

	frm.refresh_field(grid_fieldname);
}

function _recalc_alternate_quantity(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let group = row.alternate_parent_item_group || "";
	let L  = flt(row.alternate_length);
	let W  = flt(row.alternate_width);
	let T  = flt(row.alternate_thickness);
	let S  = flt(row.alternate_sec_qty);
	let UW = flt(row.alternate_unit_weight);

	let qty = 0;
	if (group === "Structurals" && L && UW && S) {
		qty = (L / 1000) * UW * S;
	} else if (group === "Plates" && L && W && T && UW && S) {
		qty = (L / 1000) * (W / 1000) * T * UW * S;
	}
	frappe.model.set_value(cdt, cdn, "alternate_quantity", qty);
}

frappe.ui.form.on("Material Planning Unavailable Item", {
	form_render(frm, cdt, cdn) {
		// Restore field visibility when an existing row is expanded
		let row = locals[cdt][cdn];
		_apply_alternate_dim_ui(frm, cdt, cdn, row.alternate_parent_item_group || null);
	},

	alternate_item(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.alternate_item) {
			frappe.model.set_value(cdt, cdn, "alternate_length",            0);
			frappe.model.set_value(cdt, cdn, "alternate_width",             0);
			frappe.model.set_value(cdt, cdn, "alternate_thickness",         0);
			frappe.model.set_value(cdt, cdn, "alternate_sec_qty",           0);
			frappe.model.set_value(cdt, cdn, "alternate_unit_weight",       0);
			frappe.model.set_value(cdt, cdn, "alternate_quantity",          0);
			frappe.model.set_value(cdt, cdn, "alternate_parent_item_group", "");
			_apply_alternate_dim_ui(frm, cdt, cdn, null);
			return;
		}
		frappe.db.get_value(
			"Item",
			row.alternate_item,
			["custom_parent_item_group", "custom_unit_weight"],
			function(d) {
				if (!d) return;
				let group = d.custom_parent_item_group || "";
				frappe.model.set_value(cdt, cdn, "alternate_parent_item_group", group);
				frappe.model.set_value(cdt, cdn, "alternate_unit_weight", flt(d.custom_unit_weight));
				_apply_alternate_dim_ui(frm, cdt, cdn, group);
				_recalc_alternate_quantity(frm, cdt, cdn);
			}
		);
	},

	alternate_length(frm, cdt, cdn)    { _recalc_alternate_quantity(frm, cdt, cdn); },
	alternate_width(frm, cdt, cdn)     { _recalc_alternate_quantity(frm, cdt, cdn); },
	alternate_thickness(frm, cdt, cdn) { _recalc_alternate_quantity(frm, cdt, cdn); },
	alternate_sec_qty(frm, cdt, cdn)   { _recalc_alternate_quantity(frm, cdt, cdn); },
	alternate_unit_weight(frm, cdt, cdn) { _recalc_alternate_quantity(frm, cdt, cdn); },
});

// Consolidate Item's own "Alternate Item" section -- unlike Unavailable Item's,
// this does NOT duplicate Length/Width/Thickness/Sec Qty for the alternate
// item. Once Alternate Item is set, the row's own (shared) Length/Width/
// Thickness/Sec Qty fields are simply reinterpreted as describing the
// ALTERNATE item's dimensions (their depends_on in the JSON already switches
// on doc.alternate_item to gate visibility off the alternate item's own
// Parent Item Group) -- only the alternate item's Unit Weight needs a
// separate lookup, since it can differ from the original item's. Purchase Kg /
// Difference Kg then recalculate off that same shared Length/Width/Thickness/
// Sec Qty using whichever group/unit weight applies -- see
// _recalc_consolidate_item (mirrors the server-side
// material_planning_consolidate_item.recalculate).
frappe.ui.form.on("Material Planning Consolidate Item", {
	alternate_item(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.alternate_item) {
			frappe.model.set_value(cdt, cdn, "alternate_unit_weight",       0);
			frappe.model.set_value(cdt, cdn, "alternate_parent_item_group", "");
			frm.refresh_field("consolidate_items");
			_recalc_consolidate_item(frm, cdt, cdn);
			return;
		}
		frappe.db.get_value(
			"Item",
			row.alternate_item,
			["custom_parent_item_group", "custom_unit_weight"],
			function(d) {
				if (!d) return;
				frappe.model.set_value(cdt, cdn, "alternate_parent_item_group", d.custom_parent_item_group || "");
				frappe.model.set_value(cdt, cdn, "alternate_unit_weight", flt(d.custom_unit_weight));
				frm.refresh_field("consolidate_items");
				_recalc_consolidate_item(frm, cdt, cdn);
			}
		);
	},
});

// Recalculate Calc Qty (Kg) from assigned batch dimensions × sec qty
function _recalc_batch_qty(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let group = row.batch_parent_item_group || "";
	let L  = flt(row.batch_length);
	let W  = flt(row.batch_width);
	let T  = flt(row.batch_thickness);
	let S  = flt(row.batch_sec_qty);
	let UW = flt(row.batch_unit_weight);

	let qty = 0;
	if (group === "Structurals" && L && UW && S) {
		qty = (L / 1000) * UW * S;
	} else if (group === "Plates" && L && W && T && UW && S) {
		qty = (L / 1000) * (W / 1000) * T * UW * S;
	} else if (group === "Nuts and Bolts" && S && UW) {
		qty = flt(S * UW, 3);
	}
	frappe.model.set_value(cdt, cdn, "batch_calc_qty", flt(qty, 3));
}

function _kg_per_nos(group, L, W, T, UW) {
	L = flt(L); W = flt(W); T = flt(T); UW = flt(UW);
	if (group === "Structurals" && L && UW) return (L / 1000) * UW;
	if (group === "Plates" && L && W && T && UW) return (L / 1000) * (W / 1000) * T * UW;
	if (group === "Nuts and Bolts" && UW) return UW;
	return 0;
}

// Mirror of the server-side _apply_rwd_fractional_nos / _sec_nos_for_weight:
// a "Reserve stock without dimensions" row reserves exactly its Required Qty in
// Kg, and Sec Nos is that weight expressed in pieces of the assigned batch --
// deliberately fractional (2.5 stays 2.5). Nothing is rounded here; turning a
// fraction into whole pieces is a transfer-time decision made on the Material
// Issue Plan, which books the surplus as excess to return.
function _calc_rwd_preview(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row.reserve_without_dimensions || !row.batch) return;

	let kg_per_nos = _kg_per_nos(row.batch_parent_item_group, row.batch_length, row.batch_width, row.batch_thickness, row.batch_unit_weight);
	frappe.model.set_value(cdt, cdn, "batch_calc_qty", flt(row.qty, 3));
	frappe.model.set_value(cdt, cdn, "batch_sec_qty", kg_per_nos ? flt(flt(row.qty) / kg_per_nos, 3) : 0);
}

// Fetch and populate batch stock summary (total / reserved / free) for a mapping row
// Cross-table batch conflict check.
// Calls on_clean() only if no conflict found; shows a blocking popup and
// clears the batch field if the same batch is already used in the other table.
function _check_cross_table_batch_conflict(frm, batch_no, calling_table, cdt, cdn, on_clean) {
	if (!batch_no || !frm.doc.for_warehouse || !frm.doc.name ||
		String(frm.doc.name).startsWith("new-")) {
		on_clean && on_clean();
		return;
	}
	frappe.call({
		method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.get_batch_cross_table_usage",
		args: { batch_no, mp_name: frm.doc.name, warehouse: frm.doc.for_warehouse },
		callback(r) {
			if (!r.message) { on_clean && on_clean(); return; }
			let d = r.message;

			let conflict_rows  = calling_table === "material_mapping" ? d.arm_rows  : d.mm_rows;
			let conflict_total = calling_table === "material_mapping" ? d.arm_total : d.mm_total;
			let conflict_label = calling_table === "material_mapping"
				? __("Exact Match") : __("Material Mapping");

			if (!conflict_rows || !conflict_rows.length) { on_clean && on_clean(); return; }

			// Build row-by-row detail
			let row_lines = conflict_rows.map(r =>
				__("Row {0} ({1}) — {2} Kg {3}", [
					r.idx, r.item_code, flt(r.qty, 3),
					r.is_reserved ? __("(Reserved)") : __("(Not Reserved)"),
				])
			).join("<br>");

			let msg = __("Batch <b>{0}</b> is already used in the <b>{1}</b> table:", [batch_no, conflict_label])
				+ "<br>" + row_lines
				+ "<br><br>"
				+ __("Total allocated in {0}: <b>{1} Kg</b>", [conflict_label, flt(conflict_total, 3)])
				+ "<br>"
				+ __("Stock in warehouse: <b>{0} Kg</b>", [flt(d.total_qty, 3)])
				+ "<br>"
				+ __("Reserved by other plans: <b>{0} Kg</b>", [flt(d.reserved_by_others, 3)])
				+ "<br>"
				+ __("Available after above allocations: <b>{0} Kg</b>", [flt(d.available_qty, 3)])
				+ "<br><br><b>"
				+ __("The same batch cannot be used in both tables. Remove it from one table first.")
				+ "</b>";

			frappe.msgprint({ title: __("Batch Already Used"), message: msg, indicator: "red" });

			// Clear the batch field in the current row
			if (calling_table === "material_mapping") {
				frappe.model.set_value(cdt, cdn, "batch", "");
				frappe.model.set_value(cdt, cdn, "planned_item", "");
			} else {
				frappe.model.set_value(cdt, cdn, "batch_no", "");
			}
		},
	});
}

function _fetch_batch_stock_summary(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row.batch || !frm.doc.for_warehouse) return;
	frappe.call({
		method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.get_batch_stock_summary",
		args: {
			batch_no: row.batch,
			warehouse: frm.doc.for_warehouse,
			mp_name: frm.doc.name || "",
		},
		callback(r) {
			if (!r.message) return;
			let d = r.message;
			frappe.model.set_value(cdt, cdn, "batch_total_qty",    flt(d.total_qty,    3));
			frappe.model.set_value(cdt, cdn, "batch_reserved_qty", flt(d.reserved_qty, 3));
			frappe.model.set_value(cdt, cdn, "batch_free_qty",     flt(d.free_qty,     3));
		},
	});
}

// Table 3: batch field events on Material Mapping rows
frappe.ui.form.on("Material Planning Material Mapping", {
	form_render(frm, cdt, cdn) {
		// Refresh stock summary whenever a row is expanded
		let row = locals[cdt][cdn];
		if (row.batch) {
			_fetch_batch_stock_summary(frm, cdt, cdn);
		}
	},

	batch(frm, cdt, cdn) {
		let row = locals[cdt][cdn];

		// Block batch change on reserved rows — revert to DB value and show error
		if (row.is_reserved) {
			frappe.msgprint(__("This row is reserved. Unreserve it before changing the batch."));
			if (row.name && !String(row.name).startsWith("new-")) {
				frappe.db.get_value(
					"Material Planning Material Mapping",
					row.name,
					"batch",
					function (d) {
						frappe.model.set_value(cdt, cdn, "batch", (d && d.batch) || "");
						frappe.model.set_value(cdt, cdn, "planned_item", "");
					}
				);
			} else {
				frappe.model.set_value(cdt, cdn, "batch", "");
				frappe.model.set_value(cdt, cdn, "planned_item", "");
			}
			return;
		}

		if (!row.batch) {
			frappe.model.set_value(cdt, cdn, "planned_item", "");
			frappe.model.set_value(cdt, cdn, "batch_length", 0);
			frappe.model.set_value(cdt, cdn, "batch_width", 0);
			frappe.model.set_value(cdt, cdn, "batch_thickness", 0);
			frappe.model.set_value(cdt, cdn, "batch_unit_weight", 0);
			frappe.model.set_value(cdt, cdn, "batch_parent_item_group", "");
			frappe.model.set_value(cdt, cdn, "batch_sec_qty", 0);
			frappe.model.set_value(cdt, cdn, "batch_calc_qty", 0);
			frappe.model.set_value(cdt, cdn, "batch_total_qty", 0);
			frappe.model.set_value(cdt, cdn, "batch_reserved_qty", 0);
			frappe.model.set_value(cdt, cdn, "batch_free_qty", 0);
			frappe.model.set_value(cdt, cdn, "batch_mapped", "Not Mapped");
			frappe.model.set_value(cdt, cdn, "cut_sheet", 0);
			frappe.model.set_value(cdt, cdn, "cut_sheet_ref", "");
			frappe.model.set_value(cdt, cdn, "cut_sheet_avail_sec_qty", 0);
			return;
		}

		// Cross-table conflict check — all dimension/stock fetching runs only if clean
		let _batch_selected = row.batch;
		_check_cross_table_batch_conflict(frm, _batch_selected, "material_mapping", cdt, cdn, function() {
			// No conflict — proceed with normal batch setup
			frappe.model.set_value(cdt, cdn, "batch_mapped", "Mapped");
			_fetch_batch_stock_summary(frm, cdt, cdn);

			frappe.db.get_value(
				"Batch",
				_batch_selected,
				["custom_length", "custom_width", "custom_thickness"],
				function(d) {
					if (!d) return;
					frappe.model.set_value(cdt, cdn, "batch_length",    flt(d.custom_length));
					frappe.model.set_value(cdt, cdn, "batch_width",     flt(d.custom_width));
					frappe.model.set_value(cdt, cdn, "batch_thickness", flt(d.custom_thickness));
					_recalc_batch_qty(frm, cdt, cdn);
					_mp_apply_cut_sheet_to_row(frm, cdt, cdn);
				}
			);

			frappe.call({
				method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.get_batch_item",
				args: { batch_no: _batch_selected },
				callback(r) {
					if (!r.message) return;
					let item_code = r.message;
					frappe.model.set_value(cdt, cdn, "planned_item", item_code);

					frappe.db.get_value(
						"Item",
						item_code,
						["custom_unit_weight", "custom_parent_item_group"],
						function(d) {
							if (!d) return;
							frappe.model.set_value(cdt, cdn, "batch_unit_weight",        flt(d.custom_unit_weight));
							frappe.model.set_value(cdt, cdn, "batch_parent_item_group",  d.custom_parent_item_group || "");
							_recalc_batch_qty(frm, cdt, cdn);
							_mp_apply_cut_sheet_to_row(frm, cdt, cdn);
							let group = d.custom_parent_item_group || "";
							if (group === "Structurals" || group === "Plates") {
								frappe.show_alert({
									message: __("Batch selected — enter <b>Sec Qty (NOS)</b> to calculate the required weight."),
									indicator: "blue",
								}, 6);
							}
						}
					);
				},
			});
		});
	},

	batch_sec_qty(frm, cdt, cdn) {
		_recalc_batch_qty(frm, cdt, cdn);
		_update_weight_summary(frm);
	},

	reserve_without_dimensions(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.reserve_without_dimensions) {
			_calc_rwd_preview(frm, cdt, cdn);
		} else {
			frappe.model.set_value(cdt, cdn, "batch_sec_qty", 0);
			frappe.model.set_value(cdt, cdn, "batch_calc_qty", 0);
			// On a Cut Sheet row, switching back to whole pieces should offer a
			// starting count rather than leaving the row empty for the user to
			// work out by hand.
			if (row.cut_sheet_ref) _mp_apply_cut_sheet_to_row(frm, cdt, cdn);
		}
		frm.fields_dict["material_mapping"].grid.refresh_row(cdn);
	},

	unreserve_btn(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.is_reserved) return;
		frappe.confirm(
			__("Unreserve batch <b>{0}</b> for item <b>{1}</b> (Row {2})? This clears the reservation on this row only.",
				[row.batch || "", row.item_code, row.idx]),
			function () {
				frappe.call({
					method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.unreserve_batches",
					args: { material_planning_name: frm.doc.name, row_names: JSON.stringify([row.name]) },
					freeze: true,
					freeze_message: __("Unreserving…"),
					callback(r) {
						frm._grid_btns_added = false;
						frm.reload_doc();
						frappe.show_alert({ message: __("Row unreserved."), indicator: "orange" }, 4);
					},
				});
			}
		);
	},
});

frappe.ui.form.on("Material Planning Material Mapping", {
	excess_material_mapping_btn(frm, cdt, cdn) {
		_show_excess_material_mapping_dialog(frm, locals[cdt][cdn]);
	},
	// "Select Item" — the same picker, reached from the Excess Material tick rather
	// than the section button, so the row you are filling is already the target.
	select_excess_item_btn(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.batch) {
			frappe.msgprint({
				title: __("This Row Already Has a Batch"),
				message: __("Excess Material is for rows with no batch of their own. Clear the batch first, or use <b>Update Batch</b> to change what it draws from."),
				indicator: "orange",
			});
			return;
		}
		_show_excess_material_mapping_dialog(frm, row);
	},
	excess_material(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.excess_material && row.batch) {
			frappe.model.set_value(cdt, cdn, "excess_material", 0);
			frappe.msgprint(__("This row already has a batch, so it does not need excess material."));
		}
	},
});

function _mp_apply_cut_sheet_to_row(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!row.batch) {
		frappe.model.set_value(cdt, cdn, "cut_sheet", 0);
		frappe.model.set_value(cdt, cdn, "cut_sheet_ref", "");
		frappe.model.set_value(cdt, cdn, "cut_sheet_avail_sec_qty", 0);
		return;
	}
	frappe.call({
		method: "manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet.get_cut_sheet_for_batch",
		args: { batch_no: row.batch, exclude_row: row.name },
		callback(r) {
			let cs = r.message;
			if (!cs) {
				frappe.model.set_value(cdt, cdn, "cut_sheet", 0);
				frappe.model.set_value(cdt, cdn, "cut_sheet_ref", "");
				frappe.model.set_value(cdt, cdn, "cut_sheet_avail_sec_qty", 0);
				return;
			}
			frappe.model.set_value(cdt, cdn, "cut_sheet", 1);
			frappe.model.set_value(cdt, cdn, "cut_sheet_ref", cs.name);
			frappe.model.set_value(cdt, cdn, "cut_sheet_avail_sec_qty", flt(cs.available_sec_qty));
			if (row.is_reserved) return;

			// The row describes the PIECE, not the plate it came off.
			frappe.model.set_value(cdt, cdn, "batch_mapped", "Cut Sheet Mapped");
			frappe.model.set_value(cdt, cdn, "batch_parent_item_group", cs.parent_item_group || "");
			frappe.model.set_value(cdt, cdn, "batch_length", flt(cs.w1_length));
			frappe.model.set_value(cdt, cdn, "batch_width", flt(cs.w1_width));
			frappe.model.set_value(cdt, cdn, "batch_thickness", flt(cs.sheet_thickness));
			frappe.model.set_value(cdt, cdn, "batch_unit_weight", flt(cs.unit_weight));
			// Suggest a piece count when the row has none yet: enough whole pieces to
			// cover what this row needs, capped at what the sheet still has. Only ever
			// a suggestion — the client's rule is that the figure is entered by hand,
			// so an existing value is never touched.
			if (!row.reserve_without_dimensions && !flt(row.batch_sec_qty)
					&& flt(cs.w1_qty_per_nos) && flt(row.qty)) {
				let needed = Math.ceil(flt(row.qty) / flt(cs.w1_qty_per_nos));
				let suggestion = Math.min(needed, flt(cs.available_sec_qty));
				if (suggestion > 0) {
					frappe.model.set_value(cdt, cdn, "batch_sec_qty", suggestion);
					row.batch_sec_qty = suggestion;
				}
			}

			if (row.reserve_without_dimensions) {
				// Fractional mode: the row reserves exactly what it needs, shown as a
				// fraction of a W1 piece. _calc_rwd_preview owns both figures.
				_calc_rwd_preview(frm, cdt, cdn);
				return;
			}

			// Whole-piece mode. Computed from the dimensions, not count x the rounded
			// per-piece Kg -- that loses a milligram per piece and can make a
			// requirement of exactly N pieces' weight look uncovered.
			let _n = flt(row.batch_sec_qty);
			let _g = cs.parent_item_group;
			let _kg = 0;
			if (_g === "Structurals") _kg = (flt(cs.w1_length) / 1000) * flt(cs.unit_weight) * _n;
			else if (_g === "Plates") _kg = (flt(cs.w1_length) / 1000) * (flt(cs.w1_width) / 1000) * flt(cs.sheet_thickness) * flt(cs.unit_weight) * _n;
			else if (_g === "Nuts and Bolts") _kg = _n * flt(cs.unit_weight);
			if (_kg) frappe.model.set_value(cdt, cdn, "batch_calc_qty", flt(_kg, 3));
			// This runs at the tail of two separate lookups, so announce it once.
			if (row.__cut_sheet_announced !== cs.name) {
				row.__cut_sheet_announced = cs.name;
				frappe.show_alert({
					message: __("Batch {0} is cut per {1} — W1 {2} × {3}, {4} piece(s) free. Enter Sec Nos in PIECES.", [
						row.batch, cs.name, flt(cs.w1_length), flt(cs.w1_width), flt(cs.available_sec_qty)]),
					indicator: "blue",
				}, 7);
			}
		},
	});
}

frappe.ui.form.on("Material Planning Material Mapping", {
});

// Shared helper: build the partial-reservation warning table HTML
function _partial_reservation_html(partial) {
	let lines = partial.map(function(p) {
		let batch_cell = p.batch || __("(non-batch)");
		let reserved_by = flt(p.reserved_by_others);
		let reserved_by_cell = reserved_by > 0
			? `<span style="color:orange;font-weight:bold">${reserved_by} ${p.uom}</span>`
			: `0 ${p.uom}`;
		return `<tr>
			<td>${p.item_code}</td>
			<td>${p.item_name || ""}</td>
			<td>${batch_cell}</td>
			<td>${p.required_qty} ${p.uom}</td>
			<td>${flt(p.batch_stock)} ${p.uom}</td>
			<td>${reserved_by_cell}</td>
			<td>${p.reserved_qty} ${p.uom}</td>
			<td style="color:red;font-weight:bold">${p.shortfall_qty} ${p.uom}</td>
		</tr>`;
	}).join("");
	return `<p>${__("Some items had insufficient free stock. Partial quantities were reserved:")}</p>
		<table class="table table-bordered table-condensed" style="font-size:12px">
			<thead><tr>
				<th>${__("Item Code")}</th><th>${__("Item Name")}</th><th>${__("Batch")}</th>
				<th>${__("Required")}</th><th>${__("Total Stock")}</th>
				<th>${__("Reserved by Others")}</th>
				<th>${__("Reserved")}</th><th>${__("Shortfall")}</th>
			</tr></thead>
			<tbody>${lines}</tbody>
		</table>`;
}

// Rows skipped entirely because the batch's source Purchase Receipt hasn't
// completed inspection yet (client change request Phase 6.2) — a distinct
// case from a partial/shortfall reservation: nothing at all was reserved for
// these rows, they stay exactly as they were before this call.
function _blocked_reservation_html(blocked) {
	let lines = blocked.map(function(b) {
		return `<tr>
			<td>${b.item_code}</td>
			<td>${b.item_name || ""}</td>
			<td>${b.batch || ""}</td>
			<td>${b.reason}</td>
		</tr>`;
	}).join("");
	return `<p>${__("Some rows were skipped -- their batch's source Purchase Receipt hasn't completed inspection yet:")}</p>
		<table class="table table-bordered table-condensed" style="font-size:12px">
			<thead><tr>
				<th>${__("Item Code")}</th><th>${__("Item Name")}</th><th>${__("Batch")}</th><th>${__("Reason")}</th>
			</tr></thead>
			<tbody>${lines}</tbody>
		</table>`;
}

// Breakdown table for rows split by finalize_mapping() — an under-covering
// alternate mapping shrunk to what it can actually fulfil, with the rest
// moved to Unavailable Items / purchase.
function _split_details_html(split_details) {
	if (!split_details || !split_details.length) return "";
	let lines = split_details.map(function(d) {
		let covers_cell = d.dropped
			? `<span style="color:red;font-weight:bold">0 Nos — not usable</span>`
			: `<span style="color:green;font-weight:bold">${d.usable_nos} Nos (${d.usable_kg} Kg)</span>`;
		let excess_cell = d.dropped
			? "—"
			: (flt(d.excess_kg) > 0 ? `<span style="color:#e65100;font-weight:bold">+${d.excess_kg} Kg</span>` : "0 Kg");
		return `<tr>
			<td>${d.idx}</td>
			<td>${d.item_code}</td>
			<td>${d.duno_mark_no || ""}</td>
			<td>${d.alternate}</td>
			<td>${covers_cell}</td>
			<td>${excess_cell}</td>
			<td style="color:red;font-weight:bold">${d.shortfall_nos} Nos (${d.shortfall_kg} Kg)</td>
		</tr>`;
	}).join("");
	return `<p style="margin-top:12px;">${__("Partially-mapped rows — split between what the alternate batch can fulfil and what still needs purchase:")}</p>
		<table class="table table-bordered table-condensed" style="font-size:12px">
			<thead><tr>
				<th>${__("Row")}</th><th>${__("Item")}</th><th>${__("DUNO/Mark No")}</th><th>${__("Alternate")}</th>
				<th>${__("Covers")}</th><th>${__("Excess (→ Diff in Kg)")}</th><th>${__("Moved to Purchase")}</th>
			</tr></thead>
			<tbody>${lines}</tbody>
		</table>`;
}

// Reserve / Unreserve toolbar buttons on the Material Mapping grid
function _add_reservation_buttons(frm) {
	let grid = frm.fields_dict["material_mapping"] && frm.fields_dict["material_mapping"].grid;
	if (!grid) return;

	grid.add_custom_button(
		frappe.utils.icon("lock", "xs") + " " + __("Reserve"),
		function () {
			let has_batch = (frm.doc.material_mapping || []).some(r => r.batch && !r.is_reserved);
			if (!has_batch) {
				frappe.msgprint(__("No un-reserved rows with a batch to reserve."));
				return;
			}

			// Validate: all dimensional batch rows must have Sec Qty entered —
			// unless the row is flagged to reserve stock without dimensions.
			let missing_sec = (frm.doc.material_mapping || []).filter(function(r) {
				let group = r.batch_parent_item_group || "";
				return r.batch && !r.is_reserved && !r.reserve_without_dimensions
					&& (group === "Structurals" || group === "Plates")
					&& !flt(r.batch_sec_qty);
			});
			if (missing_sec.length) {
				let items = missing_sec.map(r => `Row ${r.idx}: ${r.item_code} (Batch: ${r.batch})`).join("<br>");
				frappe.msgprint({
					title: __("Sec Qty Required"),
					indicator: "red",
					message: __("Enter <b>Sec Qty (NOS)</b> for the following rows before reserving:<br><br>{0}", [items]),
				});
				return;
			}

			frappe.confirm(__("Reserve all batches assigned in Material Mapping?"), function () {
				let do_reserve = function() {
					frappe.call({
						method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.reserve_batches",
						args: { material_planning_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Reserving batches…"),
						callback(r) {
							if (!r.message) return;
							frm._grid_btns_added = false;
							frm.reload_doc();
							let partial = r.message.partial || [];
							let blocked = r.message.blocked || [];
							let html = "";
							if (partial.length) html += _partial_reservation_html(partial);
							if (blocked.length) html += _blocked_reservation_html(blocked);
							if (html) {
								frappe.msgprint({
									title: __("Reservation Notices"),
									indicator: "orange",
									message: html,
								});
							} else {
								frappe.show_alert({ message: __("Batches reserved."), indicator: "green" }, 4);
							}
						},
					});
				};
				if (frm.is_dirty()) {
					frm.save().then(do_reserve).catch(function() {
						frappe.msgprint(__("Save failed. Fix any errors before reserving."));
					});
				} else {
					do_reserve();
				}
			});
		}
	);

	grid.add_custom_button(
		frappe.utils.icon("unlock", "xs") + " " + __("Unreserve"),
		function () {
			let reserved = (frm.doc.material_mapping || []).filter(r => r.is_reserved);
			if (!reserved.length) {
				frappe.msgprint(__("No reserved rows to unreserve."));
				return;
			}
			let fields = [{ fieldtype: "Section Break", label: __("Select rows to unreserve") }];
			reserved.forEach(function (row, idx) {
				fields.push({
					fieldname: "row_" + idx,
					fieldtype: "Check",
					label: `${row.item_code} — Batch: ${row.batch || ""}`,
					default: 1,
				});
			});

			let d = new frappe.ui.Dialog({
				title: __("Unreserve Batches"),
				fields: fields,
				primary_action_label: __("Unreserve"),
				primary_action(values) {
					let targets = [];
					reserved.forEach(function (row, idx) {
						if (values["row_" + idx]) targets.push(row.name);
					});
					if (!targets.length) { frappe.msgprint(__("Select at least one row.")); return; }
					frappe.call({
						method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.unreserve_batches",
						args: { material_planning_name: frm.doc.name, row_names: JSON.stringify(targets) },
						freeze: true,
						freeze_message: __("Unreserving…"),
						callback(r) {
							d.hide();
							frm._grid_btns_added = false;
							frm.reload_doc();
							frappe.show_alert({ message: __("Batches unreserved."), indicator: "orange" }, 4);
						},
					});
				},
			});
			d.show();
		}
	);

	grid.add_custom_button(
		frappe.utils.icon("refresh", "xs") + " " + __("Excess Material Mapping"),
		function () { _show_excess_material_mapping_dialog(frm); }
	);
}

// ── Excess Material Mapping dialog (client change request Phase 2.3) ───────
// Lists batches recovered via the excess-material-return flow (off-cuts from
// another job, sitting in this MP's warehouse) and lets the user manually map
// one in instead of buying fresh raw material.
//
// Two entry points share this one dialog:
//   - The Material Mapping grid's own toolbar button (existing_row omitted) --
//     "Add & Reserve" creates a brand NEW Material Mapping row, optionally
//     linked to an Unavailable Item row to shrink its shortfall.
//   - The per-row "Excess Material Mapping" button on an existing Material
//     Mapping row (existing_row passed in) -- the item filter defaults to
//     that row's own item_code but can be changed to browse any item's
//     excess batches, and "Add & Reserve" calls the same reassign_batch RPC
//     "Update Batch" already uses, reserving straight into THAT row instead
//     of creating a new one (picking a different item's batch substitutes
//     it in via planned_item, same as Update Batch already supports).
// Either way, if the picked batch came from the excess-return flow, the
// server-side call marks the source SCO Excess Material Item row with where
// it ended up (_mark_excess_item_mapped), so Material Issue Plan can show
// it's been reused instead of looking like it's still sitting unused.
function _show_excess_material_mapping_dialog(frm, existing_row) {
	if (!frm.doc.for_warehouse) {
		frappe.msgprint(__("Set 'Raw Materials Warehouse' before mapping excess material."));
		return;
	}
	let unavailable = existing_row ? [] : (frm.doc.unavailable_items || []).filter(r => r.item_code);

	let dialog_fields = [];
	if (!existing_row) {
		dialog_fields.push(
			{
				fieldtype: "Select",
				fieldname: "unavailable_item_row",
				label: __("Link to Unavailable Item (optional)"),
				options: [""].concat(unavailable.map((r, idx) =>
					`${idx}::${r.item_code} — ${r.duno_mark_no || ""} (Reqd: ${flt(r.qty)} Kg)`)),
				description: __("Pick one to auto-fill traceability and reduce that shortfall by the amount "
					+ "mapped here; leave blank to add a standalone row not tied to a specific requirement."),
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Data",
				fieldname: "item_filter",
				label: __("Filter by Item Code"),
			},
		);
	} else {
		dialog_fields.push({
			fieldtype: "Data",
			fieldname: "item_filter",
			label: __("Filter by Item Code"),
			default: existing_row.item_code,
			description: __("Starts on this row's own item; clear or change it to browse excess of any item -- picking a different item substitutes it in (recorded as Planned Item, same as Update Batch)."),
		});
	}
	dialog_fields.push(
		{ fieldtype: "Section Break" },
		{
			fieldtype: "HTML",
			fieldname: "excess_legend",
			options: `<div style="font-size:12px;color:#888;margin-bottom:4px;">${__("Returned Batch")} = ${__("physically back in your own warehouse")}. ${__("Not Yet Returned")} = ${__("still just a row in some Material Issue Plan's Excess Material Items table -- not in any warehouse yet, simply because it has not been walked back to stock. Claim as many pieces as you need; the rest stays free for other jobs, and claiming creates no Stock Entry. Off-cuts marked Billed to Consume are never offered here: they are charged to their own job and consumed at the supplier.")}</div>`,
		},
		{ fieldtype: "HTML", fieldname: "excess_html" },
		{ fieldtype: "Section Break" },
		{
			fieldtype: "Float",
			fieldname: "sec_qty_to_use",
			label: __("Sec Qty to Use"),
			description: __("How many pieces to take. Whatever you leave stays free for another job to claim."),
		},
		{ fieldtype: "Column Break" },
		{
			fieldtype: "Float",
			fieldname: "kg_preview",
			label: __("Kg (calculated)"),
			read_only: 1,
		},
	);

	let d = new frappe.ui.Dialog({
		title: existing_row ? __("Excess Material Mapping — Row {0}", [existing_row.idx]) : __("Excess Material Mapping"),
		size: "extra-large",
		fields: dialog_fields,
		primary_action_label: __("Add & Reserve"),
		primary_action(values) {
			if (d._selected_virtual) {
				let unavailable_row_name = null;
				if (!existing_row && values.unavailable_item_row) {
					let idx = parseInt(values.unavailable_item_row.split("::")[0], 10);
					unavailable_row_name = unavailable[idx] && unavailable[idx].name;
				}
				frappe.call({
					method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.claim_virtual_excess_mapping",
					args: {
						mp_name: frm.doc.name,
						excess_row_name: d._selected_virtual.excess_row,
						row_name: existing_row ? existing_row.name : null,
						unavailable_item_row: unavailable_row_name,
						sec_qty: flt(values.sec_qty_to_use),
					},
					freeze: true,
					freeze_message: __("Claiming excess held at supplier…"),
					callback(r) {
						if (!r.message) return;
						d.hide();
						frm._grid_btns_added = false;
						frm.reload_doc();
						frappe.show_alert({ message: __("Excess material (at supplier) claimed and reserved."), indicator: "green" }, 4);
					},
				});
				return;
			}

			if (!d._selected_batch) {
				frappe.msgprint(__("Select a batch or an 'At Supplier' row first."));
				return;
			}
			let sec_qty = flt(values.sec_qty_to_use);
			if (!sec_qty) {
				frappe.msgprint(__("Enter Sec Qty to use."));
				return;
			}

			if (existing_row) {
				frappe.call({
					method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.reassign_batch",
					args: {
						material_planning_name: frm.doc.name,
						source_table: "Material Planning Material Mapping",
						row_name: existing_row.name,
						new_batch_no: d._selected_batch.batch_no,
						sec_qty: sec_qty,
					},
					freeze: true,
					freeze_message: __("Mapping and reserving…"),
					callback(r) {
						d.hide();
						let warnings = (r.message && r.message.warnings) || [];
						if (warnings.length) {
							frappe.msgprint({
								title: __("Reallocation Warnings"),
								indicator: "orange",
								message: warnings.map((w) => w.reason || `${w.item_code} (${w.batch}): ${__("short by")} ${w.shortfall_qty}`).join("<br>"),
							});
						}
						frm._grid_btns_added = false;
						frm.reload_doc();
						frappe.show_alert({ message: __("Excess material mapped and reserved."), indicator: "green" }, 4);
					},
				});
				return;
			}

			let unavailable_row_name = null;
			if (values.unavailable_item_row) {
				let idx = parseInt(values.unavailable_item_row.split("::")[0], 10);
				unavailable_row_name = unavailable[idx] && unavailable[idx].name;
			}
			frappe.call({
				method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.add_excess_material_mapping",
				args: {
					mp_name: frm.doc.name,
					batch_no: d._selected_batch.batch_no,
					sec_qty: sec_qty,
					unavailable_item_row: unavailable_row_name,
				},
				freeze: true,
				freeze_message: __("Mapping and reserving…"),
				callback(r) {
					if (!r.message) return;
					d.hide();
					frm._grid_btns_added = false;
					frm.reload_doc();
					frappe.show_alert({ message: __("Excess material mapped and reserved."), indicator: "green" }, 4);
				},
			});
		},
	});

	function _load(item_filter) {
		frappe.call({
			method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.get_available_excess_batches",
			args: { mp_name: frm.doc.name, item_code: item_filter || null },
			freeze: true,
			freeze_message: __("Loading excess material…"),
			callback(r) {
				let batches = (r.message || []).map(row => Object.assign({ _kind: "batch" }, row));
				frappe.call({
					method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.get_available_virtual_excess_items",
					args: { mp_name: frm.doc.name, item_code: item_filter || null },
					callback(r2) {
						let virtual = (r2.message || []).map(row => Object.assign({ _kind: "virtual" }, row));
						_render(batches.concat(virtual));
					},
				});
			},
		});
	}

	function _render(rows) {
		let $wrap = d.fields_dict.excess_html.$wrapper;
		if (!rows.length) {
			$wrap.html(`<div style="padding:20px;text-align:center;color:#888;">${__("No excess material (returned, or still pending in an Excess Material Items table) found for this filter.")}</div>`);
			return;
		}
		let th = "white-space:nowrap;padding:6px 10px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;";
		let td = "padding:5px 10px;white-space:nowrap;border-bottom:1px solid #f0f0f0;";
		let cols = [__("Item Code"), __("Item Name"), __("Source"), __("Batch / MIP"), __("L (mm)"), __("W (mm)"), __("T (mm)"), __("Planned Sec Nos"), __("Free Sec Nos"), __("Free (Kg)"), __("Supplier")];
		let thead = "<tr>" + cols.map(c => `<th style="${th}">${c}</th>`).join("") + "</tr>";
		let tbody = rows.map((r, i) => {
			if (r._kind === "batch") {
				return `
			<tr data-idx="${i}" style="cursor:pointer;">
				<td style="${td}">${frappe.utils.escape_html(r.item_code)}</td>
				<td style="${td}">${frappe.utils.escape_html(r.item_name || "")}</td>
				<td style="${td}">${__("Returned Batch")}</td>
				<td style="${td}">${frappe.utils.escape_html(r.batch_no)}</td>
				<td style="${td}">${format_number(flt(r.length), null, 1)}</td>
				<td style="${td}">${format_number(flt(r.width), null, 1)}</td>
				<td style="${td}">${format_number(flt(r.thickness), null, 1)}</td>
				<td style="${td}">${format_number(flt(r.batch_sec_qty), null, 3)}</td>
				<td style="${td};font-weight:600;">${format_number(flt(r.batch_sec_qty), null, 3)}</td>
				<td style="${td}">${format_number(flt(r.free_qty), null, 3)}</td>
				<td style="${td}">-</td>
			</tr>`;
			}
			// Everything offered here is an off-cut that has not come back yet; the
			// ones that never will are Billed to Consume and are not offered at all.
			let source_label = __("Not Yet Returned (Pending)");
			return `
			<tr data-idx="${i}" style="cursor:pointer;">
				<td style="${td}">${frappe.utils.escape_html(r.item_code)}</td>
				<td style="${td}">${frappe.utils.escape_html(r.item_name || "")}</td>
				<td style="${td};color:#b8860b;">${frappe.utils.escape_html(source_label)}</td>
				<td style="${td}">${frappe.utils.escape_html(r.mip_name)}</td>
				<td style="${td}">${format_number(flt(r.length), null, 1)}</td>
				<td style="${td}">${format_number(flt(r.width), null, 1)}</td>
				<td style="${td}">${format_number(flt(r.thickness), null, 1)}</td>
				<td style="${td}">${format_number(flt(r.planned_sec_qty != null ? r.planned_sec_qty : r.sec_qty), null, 3)}</td>
				<td style="${td};font-weight:600;color:${flt(r.available_sec_qty) < flt(r.planned_sec_qty) ? "#b8860b" : "inherit"};">${format_number(flt(r.available_sec_qty != null ? r.available_sec_qty : r.sec_qty), null, 3)}</td>
				<td style="${td}">${format_number(flt(r.available_qty != null ? r.available_qty : r.qty), null, 3)}</td>
				<td style="${td}">${frappe.utils.escape_html(r.supplier || "-")}</td>
			</tr>`;
		}).join("");
		$wrap.html(`<div style="overflow-x:auto;max-height:32vh;overflow-y:auto;border:1px solid #e9ecef;border-radius:4px;">
			<table style="font-size:12px;border-collapse:collapse;width:100%;min-width:800px;">
				<thead style="position:sticky;top:0;">${thead}</thead>
				<tbody>${tbody}</tbody>
			</table></div>`);

		$wrap.find("tr[data-idx]").on("click", function() {
			let row = rows[parseInt($(this).data("idx"), 10)];
			d._selected_batch = null;
			d._selected_virtual = null;
			if (row._kind === "batch") {
				d._selected_batch = row;
				let default_sec_qty = (row.batch_sec_qty && row.free_qty)
					? Math.min(flt(row.batch_sec_qty), flt(row.free_qty))
					: flt(row.batch_sec_qty);
				d.set_df_property("sec_qty_to_use", "read_only", 0);
				d.set_value("sec_qty_to_use", default_sec_qty);
			} else {
				d._selected_virtual = row;
				// Partial claims: an off-cut is shared out in pieces like a Cut Sheet,
				// so this is editable and defaults to everything still free.
				d.set_df_property("sec_qty_to_use", "read_only", 0);
				d.set_value("sec_qty_to_use", flt(row.available_sec_qty || row.sec_qty));
				d.set_value("kg_preview", flt(row.qty, 3));
			}
			_update_kg_preview();
			$wrap.find("tr").css("background", "");
			$(this).css("background", "#e3f2fd");
		});
	}

	function _update_kg_preview() {
		if (d._selected_virtual) {
			let per = flt(d._selected_virtual.qty_per_nos);
			let n = flt(d.get_value("sec_qty_to_use"));
			d.set_value("kg_preview", flt(per && n ? per * n : d._selected_virtual.qty, 3));
			return;
		}
		let row = d._selected_batch;
		if (!row) return;
		let sec_qty = flt(d.get_value("sec_qty_to_use"));
		let kg = _kg_per_nos(row.parent_item_group, row.length, row.width, row.thickness, row.unit_weight) * sec_qty;
		d.set_value("kg_preview", flt(kg, 3));
	}

	d.fields_dict.sec_qty_to_use.df.onchange = _update_kg_preview;
	d.fields_dict.item_filter.df.onchange = () => _load(d.get_value("item_filter"));

	d.show();
	_load(existing_row ? existing_row.item_code : null);
}

// Column definitions for each table's View All popup
const _TABLE_VIEW_CONFIG = {
	raw_materials: {
		title: "Raw Materials",
		cols: [
			{ fieldname: "item_number",       label: "Item No" },
			{ fieldname: "sales_order",       label: "Sales Order" },
			{ fieldname: "item_code",         label: "Item Code" },
			{ fieldname: "item_name",         label: "Item Name" },
			{ fieldname: "bom_no",                    label: "Source BOM" },
			{ fieldname: "duno_mark_no",              label: "DUNO/Mark No" },
			{ fieldname: "customer_drawing_number",   label: "Cust Drawing Number" },
			{ fieldname: "parent_item_group",         label: "Item Group" },
			{ fieldname: "length",            label: "Length (mm)" },
			{ fieldname: "width",             label: "Width (mm)" },
			{ fieldname: "thickness",         label: "Thickness" },
			{ fieldname: "sec_qty",           label: "Sec Qty" },
			{ fieldname: "sec_uom",           label: "Sec UOM" },
			{ fieldname: "qty",               label: "Required Qty" },
			{ fieldname: "uom",               label: "UOM" },
			{ fieldname: "available_qty",     label: "Available Qty" },
			{ fieldname: "shortage_qty",      label: "Shortage Qty" },
			{ fieldname: "unit_weight",       label: "Unit Weight" },
			{ fieldname: "material_spec",     label: "Material Spec" },
			{ fieldname: "warehouse",         label: "Warehouse" },
			{ fieldname: "store_location",    label: "Store Location" },
		],
	},
	available_raw_materials: {
		title: "Available Raw Materials (Exact Match)",
		cols: [
			{ fieldname: "item_number",       label: "Item No" },
			{ fieldname: "sales_order",       label: "Sales Order" },
			{ fieldname: "item_code",         label: "Item Code" },
			{ fieldname: "item_name",         label: "Item Name" },
			{ fieldname: "duno_mark_no",            label: "DUNO/Mark No" },
			{ fieldname: "customer_drawing_number", label: "Cust Drawing Number" },
			{ fieldname: "batch_no",          label: "Batch No" },
			{ fieldname: "parent_item_group", label: "Item Group" },
			{ fieldname: "length",            label: "Length (mm)" },
			{ fieldname: "width",             label: "Width (mm)" },
			{ fieldname: "thickness",         label: "Thickness" },
			{ fieldname: "sec_qty",           label: "Sec Qty" },
			{ fieldname: "sec_uom",           label: "Sec UOM" },
			{ fieldname: "required_qty",      label: "Required Qty" },
			{ fieldname: "available_qty",     label: "Available Qty" },
			{ fieldname: "uom",               label: "UOM" },
			{ fieldname: "is_reserved",       label: "Reserved" },
			{ fieldname: "reserved_qty",      label: "Reserved Qty" },
			{ fieldname: "shortfall_qty",     label: "Shortfall Qty" },
			{ fieldname: "warehouse",         label: "Warehouse" },
		],
	},
	material_mapping: {
		title: "Material Mapping (Alternate Stock)",
		cols: [
			{ fieldname: "item_number",       label: "Item No" },
			{ fieldname: "sales_order",       label: "Sales Order" },
			{ fieldname: "item_code",         label: "Item Code" },
			{ fieldname: "item_name",         label: "Item Name" },
			{ fieldname: "duno_mark_no",            label: "DUNO/Mark No" },
			{ fieldname: "customer_drawing_number", label: "Cust Drawing Number" },
			{ fieldname: "qty",               label: "Req Qty" },
			{ fieldname: "uom",               label: "UOM" },
			{ fieldname: "parent_item_group", label: "Item Group" },
			{ fieldname: "length",            label: "Length (mm)" },
			{ fieldname: "width",             label: "Width (mm)" },
			{ fieldname: "thickness",         label: "Thickness" },
			{ fieldname: "sec_qty",           label: "Required Sec Qty" },
			{ fieldname: "batch",             label: "Batch" },
			{ fieldname: "batch_mapped",      label: "Status" },
			{ fieldname: "batch_length",      label: "Batch Length" },
			{ fieldname: "reserve_without_dimensions", label: "Reserve w/o Dimensions" },
			{ fieldname: "batch_sec_qty",     label: "Batch Sec Qty" },
			{ fieldname: "batch_calc_qty",    label: "Calc Qty (Kg)" },
			{ fieldname: "is_reserved",       label: "Reserved" },
			{ fieldname: "reserved_qty",      label: "Reserved Qty" },
		],
	},
	unavailable_items: {
		title: "Unavailable Items (No Stock — Needs Purchase)",
		cols: [
			{ fieldname: "item_number",        label: "Item No" },
			{ fieldname: "sales_order",        label: "Sales Order" },
			{ fieldname: "item_code",          label: "Item Code" },
			{ fieldname: "item_name",          label: "Item Name" },
			{ fieldname: "duno_mark_no",             label: "DUNO/Mark No" },
			{ fieldname: "customer_drawing_number",  label: "Cust Drawing Number" },
			{ fieldname: "qty",                label: "Required Qty" },
			{ fieldname: "uom",                label: "UOM" },
			{ fieldname: "parent_item_group",  label: "Item Group" },
			{ fieldname: "length",             label: "Length (mm)" },
			{ fieldname: "width",              label: "Width (mm)" },
			{ fieldname: "thickness",          label: "Thickness" },
			{ fieldname: "sec_qty",            label: "Sec Qty" },
			{ fieldname: "sec_uom",            label: "Sec UOM" },
			{ fieldname: "unit_weight",        label: "Unit Weight" },
			{ fieldname: "alternate_item",     label: "Alt Item" },
			{ fieldname: "alternate_quantity", label: "Alt Qty (Kg)" },
		],
	},
};

// Filters offered above every View All popup. Shared by all four tables: which
// ones actually appear is decided per table from the rows themselves, so a table
// that does not carry a field never shows a box for it.
const _VIEW_FILTERS = [
	{ fieldname: "item_code",               placeholder: "Filter Item Code…",           width: 150 },
	{ fieldname: "item_name",               placeholder: "Filter Item Name…",           width: 160 },
	{ fieldname: "duno_mark_no",            placeholder: "Filter DUNO/Mark No…",        width: 180 },
	{ fieldname: "customer_drawing_number", placeholder: "Filter Cust Drawing Number…", width: 200 },
];

// Generic View All popup — read-only, all configured columns, scrollable
function _show_table_popup(frm, fieldname) {
	let cfg  = _TABLE_VIEW_CONFIG[fieldname];
	if (!cfg) return;
	let rows = frm.doc[fieldname] || [];
	if (!rows.length) {
		frappe.msgprint(__("No data to display."));
		return;
	}

	let th_style = "white-space:nowrap;padding:6px 10px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;";
	let thead = "<tr>" + cfg.cols.map(c =>
		`<th style="${th_style}">${__(c.label)}</th>`
	).join("") + "</tr>";

	function _render_tbody(filtered_rows) {
		return filtered_rows.map(function (row, idx) {
			let cells = cfg.cols.map(function (c) {
				let val = row[c.fieldname];
				if (val === null || val === undefined) val = "";
				return `<td style="padding:5px 10px;white-space:nowrap;border-bottom:1px solid #f0f0f0;">${frappe.utils.escape_html(String(val))}</td>`;
			}).join("");
			let bg = idx % 2 !== 0 ? "background:#fafbfc;" : "";
			return `<tr style="${bg}">${cells}</tr>`;
		}).join("");
	}

	// Only offer a filter the table can actually answer. Every popup shares this
	// list, but the tables do not all carry every field -- Available Raw
	// Materials has no drawing number, for one -- and a box that can only ever
	// return nothing is worse than no box at all.
	let active_filters = _VIEW_FILTERS.filter(f =>
		rows.some(r => r[f.fieldname] !== undefined && r[f.fieldname] !== null && r[f.fieldname] !== "")
	);

	let input_style = "border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;";
	let filter_bar = `<div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;flex-wrap:wrap;">
		${active_filters.map(f => `<input type="text" class="_vw_filter" data-fieldname="${f.fieldname}"
			placeholder="${__(f.placeholder)}" style="${input_style}width:${f.width}px;">`).join("")}
		<span id="_vw_count" style="font-size:12px;color:#6c757d;"></span>
		<button class="btn btn-xs btn-default" id="_vw_clear" style="font-size:11px;">${__("Clear")}</button>
	</div>`;

	let table_html = `<div style="overflow:auto;max-height:65vh;">
		<table style="font-size:12px;border-collapse:collapse;width:100%;" id="_vw_table">
			<thead style="position:sticky;top:0;z-index:1;">${thead}</thead>
			<tbody id="_vw_tbody">${_render_tbody(rows)}</tbody>
		</table>
	</div>`;

	let d = new frappe.ui.Dialog({
		title: __(cfg.title + " — {0} item(s)", [rows.length]),
		size: "extra-large",
	});
	d.$body.html(filter_bar + table_html);

	function _apply_filter() {
		// Every box that has something typed in it must match — narrowing by item
		// code AND mark number is the whole point of having more than one.
		let queries = [];
		d.$body.find("._vw_filter").each(function() {
			let q = (this.value || "").trim().toLowerCase();
			if (q) queries.push([this.dataset.fieldname, q]);
		});
		let filtered = queries.length ? rows.filter(function(r) {
			return queries.every(([fieldname, q]) =>
				String(r[fieldname] === null || r[fieldname] === undefined ? "" : r[fieldname])
					.toLowerCase().includes(q)
			);
		}) : rows;
		d.$body.find("#_vw_tbody").html(_render_tbody(filtered));
		d.$body.find("#_vw_count").text(filtered.length + " / " + rows.length + " " + __("rows"));
	}
	d.$body.find("._vw_filter").on("input", _apply_filter);
	d.$body.find("#_vw_clear").on("click", function() {
		d.$body.find("._vw_filter").val("");
		_apply_filter();
	});
	_apply_filter();
	d.show();
}

// ── Available Raw Material child table events ────────────────────────────────
frappe.ui.form.on("Material Planning Available Raw Material", {
	form_render(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Make skip checkbox read-only for reserved rows in the expanded row view
		let df = frappe.meta.get_docfield("Material Planning Available Raw Material", "skip_auto_suggest_batch", cdn);
		if (df) df.read_only = row.is_reserved ? 1 : 0;
		frm.fields_dict["available_raw_materials"].grid.refresh_row(cdn);
	},

	batch_no(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.batch_no) return;
		_check_cross_table_batch_conflict(frm, row.batch_no, "available_raw_materials", cdt, cdn, null);
	},

	skip_auto_suggest_batch(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.is_reserved && row.skip_auto_suggest_batch) {
			frappe.model.set_value(cdt, cdn, "skip_auto_suggest_batch", 0);
			frappe.show_alert({
				message: __("Cannot skip a reserved batch. Unreserve it first."),
				indicator: "orange",
			}, 4);
		}
	},

	unreserve_btn(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.is_reserved) return;
		frappe.confirm(
			__("Unreserve batch <b>{0}</b> for item <b>{1}</b> (Row {2})? This clears the reservation on this row only.",
				[row.batch_no || "", row.item_code, row.idx]),
			function () {
				frappe.call({
					method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.unreserve_exact_match_batches",
					args: { material_planning_name: frm.doc.name, row_names: JSON.stringify([row.name]) },
					freeze: true,
					freeze_message: __("Unreserving…"),
					callback(r) {
						frm._grid_btns_added = false;
						frm.reload_doc();
						frappe.show_alert({ message: __("Row unreserved."), indicator: "orange" }, 4);
					},
				});
			}
		);
	},
});

// Reserve / Unreserve toolbar buttons on the Available Raw Materials (Exact Match) grid
function _add_exact_match_reservation_buttons(frm) {
	let grid = frm.fields_dict["available_raw_materials"] && frm.fields_dict["available_raw_materials"].grid;
	if (!grid) return;

	grid.add_custom_button(
		frappe.utils.icon("lock", "xs") + " " + __("Reserve"),
		function () {
			let has_unreserved = (frm.doc.available_raw_materials || []).some(r => !r.is_reserved);
			if (!has_unreserved) {
				frappe.msgprint(__("No un-reserved rows to reserve."));
				return;
			}
			frappe.confirm(__("Reserve all batches in Available Raw Materials (Exact Match)?"), function () {
				let do_reserve = function() {
					frappe.call({
						method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.reserve_exact_match_batches",
						args: { material_planning_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Reserving batches…"),
						callback(r) {
							if (!r.message) return;
							frm._grid_btns_added = false;
							frm.reload_doc();
							let partial = r.message.partial || [];
							let blocked = r.message.blocked || [];
							let html = "";
							if (partial.length) {
								let partial_codes = new Set(partial.map(p => p.item_code));
								let already_in_mapping = (frm.doc.material_mapping || []).some(row => partial_codes.has(row.item_code));
								let note = already_in_mapping
									? `<div style="margin-top:10px;padding:8px 12px;background:#e8f4fd;border-left:4px solid #2490ef;border-radius:3px;font-size:12px;">
											<b>${__("Next step:")}</b> ${__("Shortfall rows are already in <b>Material Mapping (Alternate Stock)</b>. Assign a batch to each row to cover the gap, then reserve.")}
										</div>`
									: `<div style="margin-top:10px;padding:8px 12px;background:#fff8e1;border-left:4px solid #f9a825;border-radius:3px;font-size:12px;">
											<b>${__("Tip:")}</b> ${__("Re-run <b>Check Stock Availability</b> to automatically add shortfall rows to Material Mapping.")}
										</div>`;
								html += _partial_reservation_html(partial) + note;
							}
							if (blocked.length) html += _blocked_reservation_html(blocked);
							if (html) {
								frappe.msgprint({
									title: __("Reservation Notices"),
									indicator: "orange",
									message: html,
								});
							} else {
								frappe.show_alert({ message: __("Batches reserved."), indicator: "green" }, 4);
							}
						},
					});
				};
				if (frm.is_dirty()) {
					frm.save().then(do_reserve).catch(function() {
						frappe.msgprint(__("Save failed. Fix any errors before reserving."));
					});
				} else {
					do_reserve();
				}
			});
		}
	);

	grid.add_custom_button(
		frappe.utils.icon("unlock", "xs") + " " + __("Unreserve"),
		function () {
			let reserved = (frm.doc.available_raw_materials || []).filter(r => r.is_reserved);
			if (!reserved.length) {
				frappe.msgprint(__("No reserved rows to unreserve."));
				return;
			}
			let fields = [{ fieldtype: "Section Break", label: __("Select rows to unreserve") }];
			reserved.forEach(function (row, idx) {
				fields.push({
					fieldname: "row_" + idx,
					fieldtype: "Check",
					label: `${row.item_code} — Batch: ${row.batch_no || ""}`,
					default: 1,
				});
			});

			let d = new frappe.ui.Dialog({
				title: __("Unreserve Exact Match Batches"),
				fields: fields,
				primary_action_label: __("Unreserve"),
				primary_action(values) {
					let targets = [];
					reserved.forEach(function (row, idx) {
						if (values["row_" + idx]) targets.push(row.name);
					});
					if (!targets.length) { frappe.msgprint(__("Select at least one row.")); return; }
					frappe.call({
						method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.unreserve_exact_match_batches",
						args: { material_planning_name: frm.doc.name, row_names: JSON.stringify(targets) },
						freeze: true,
						freeze_message: __("Unreserving…"),
						callback(r) {
							d.hide();
							frm._grid_btns_added = false;
							frm.reload_doc();
							frappe.show_alert({ message: __("Batches unreserved."), indicator: "orange" }, 4);
						},
					});
				},
			});
			d.show();
		}
	);

	grid.add_custom_button(
		frappe.utils.icon("edit", "xs") + " " + __("Reassign Batch"),
		function () {
			_show_exact_match_reassign_dialog(frm);
		}
	);
}


// ── Auto Purchase (Manufyxinvenza Settings) ──────────────────────────────
frappe.ui.form.on("Material Planning", {
	custom_auto_suggest_dimensions_btn(frm) {
		_run_auto_suggest_dimensions(frm);
	},
	custom_auto_purchase_btn(frm) {
		_run_auto_purchase(frm);
	},
});

// Opening guess for the Consolidate Item table: the largest size among the
// requirements each row covers, and the Sec Qty that matches the weight needed.
// Confirms first when rows already carry dimensions -- re-running it must not
// quietly overwrite sizes someone has typed.
function _run_auto_suggest_dimensions(frm) {
	if (!(frm.doc.consolidate_items || []).length) {
		frappe.msgprint(__("There are no Consolidate Items to suggest dimensions for."));
		return;
	}
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the document first — suggestions are written straight to the rows."));
		return;
	}

	var filled = (frm.doc.consolidate_items || []).filter(function(r) {
		return flt(r.length) || flt(r.width) || flt(r.thickness) || flt(r.sec_qty);
	});

	function go() {
		frappe.call({
			method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.auto_suggest_consolidate_dimensions",
			args: { material_planning_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Suggesting dimensions…"),
			callback: function(r) {
				var m = r.message || {};
				var up = m.updated || [], sk = m.skipped || [];
				frm.reload_doc();
				if (!up.length && !sk.length) {
					frappe.msgprint(__("Nothing to suggest."));
					return;
				}
				var html = "";
				if (up.length) {
					html += "<b>" + __("Suggested for {0} item(s)", [up.length]) + "</b>"
						+ "<table class='table table-bordered table-condensed' style='margin-top:8px;font-size:12px'>"
						+ "<thead><tr><th>" + __("Item") + "</th><th class='text-right'>" + __("Length") + "</th>"
						+ "<th class='text-right'>" + __("Sec Qty") + "</th>"
						+ "<th class='text-right'>" + __("Required") + "</th>"
						+ "<th class='text-right'>" + __("Purchase") + "</th></tr></thead><tbody>";
					up.forEach(function(u) {
						html += "<tr><td>" + frappe.utils.escape_html(u.item_code) + "</td>"
							+ "<td class='text-right'>" + format_number(u.length, null, 0) + "</td>"
							+ "<td class='text-right'>" + format_number(u.sec_qty, null, 3) + "</td>"
							+ "<td class='text-right'>" + format_number(u.required_kg, null, 3) + "</td>"
							+ "<td class='text-right'>" + format_number(u.purchase_kg, null, 3) + "</td></tr>";
					});
					html += "</tbody></table>"
						+ "<div class='text-muted' style='font-size:11px'>"
						+ __("Length is the largest size these requirements need, so every piece can be cut from it. Adjust and save.")
						+ "</div>";
				}
				if (sk.length) {
					html += "<div style='margin-top:10px'><b>" + __("Skipped") + "</b><ul style='margin:4px 0 0 -18px'>";
					sk.forEach(function(x) {
						html += "<li>" + frappe.utils.escape_html(x.item_code || "?") + " — "
							+ frappe.utils.escape_html(x.reason || "") + "</li>";
					});
					html += "</ul></div>";
				}
				frappe.msgprint({ title: __("Auto Suggest Item Dimensions"), message: html, indicator: "blue" });
			},
		});
	}

	if (filled.length) {
		frappe.confirm(
			__("{0} of {1} row(s) already have dimensions or Sec Qty. Overwrite them with the suggestion?",
				[filled.length, (frm.doc.consolidate_items || []).length]),
			go
		);
	} else {
		go();
	}
}


function _run_auto_purchase(frm) {
	if (!frm.doc.custom_auto_purchase_supplier) {
		frappe.msgprint({ title: __("Supplier Required"), message: __("Please set the Supplier field before running Auto Purchase."), indicator: "orange" });
		return;
	}
	if (!frm.doc.for_warehouse) {
		frappe.msgprint({ title: __("Warehouse Required"), message: __("Please set the Raw Materials Warehouse before running Auto Purchase."), indicator: "orange" });
		return;
	}
	if (!(frm.doc.consolidate_items || []).length) {
		frappe.msgprint({ title: __("No Items"), message: __("No consolidated items to purchase."), indicator: "orange" });
		return;
	}
	frappe.confirm(
		__("This will automatically create and submit a Material Request, Purchase Order, and Purchase Receipt for ALL consolidated items. Continue?"),
		function() {
			if (frm.is_dirty()) {
				frappe.call({
					method: "frappe.client.save",
					args: { doc: frm.doc },
					freeze: true, freeze_message: __("Saving…"),
					callback(r) {
						if (r.message) { frappe.model.sync(r.message); frm.refresh(); }
						_do_auto_purchase(frm);
					},
				});
			} else {
				_do_auto_purchase(frm);
			}
		}
	);
}

function _do_auto_purchase(frm) {
	frappe.call({
		method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.auto_purchase_from_mp",
		args: { material_planning_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating MR → PO → PR…"),
		callback(r) {
			if (r.message) {
				var m = r.message;
				frappe.msgprint({
					title: __("Auto Purchase Complete"),
					message:
						__("Material Request: ") + '<a href="/app/material-request/' + encodeURIComponent(m.mr) + '">' + m.mr + '</a><br>' +
						__("Purchase Order: ")   + '<a href="/app/purchase-order/'   + encodeURIComponent(m.po) + '">' + m.po + '</a><br>' +
						__("Purchase Receipt: ") + '<a href="/app/purchase-receipt/' + encodeURIComponent(m.pr) + '">' + m.pr + '</a>',
					indicator: "green",
				});
				frm._grid_btns_added = false;
				frm.reload_doc();
			}
		},
	});
}

// ── Consolidate Item: live Purchase Kg / Difference Kg calc ────────────────
function _recalc_consolidate_item(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	// When Alternate Item is set, Length/Width/Thickness/Sec Qty describe THAT
	// item instead of the original -- only the group (which dims apply) and
	// unit weight need to switch to the alternate item's own.
	let group       = row.alternate_item ? row.alternate_parent_item_group : row.parent_item_group;
	let unit_weight = row.alternate_item ? row.alternate_unit_weight       : row.unit_weight;
	// _kg_per_nos already returns 0 unless its own group's required dimensions are
	// present, so multiplying by Sec Qty here reproduces the full Structurals/Plates/
	// Nuts-and-Bolts formula without re-deriving the group branching.
	let kg_per_nos = _kg_per_nos(group, row.length, row.width, row.thickness, unit_weight);
	let purchase_kg = flt(kg_per_nos * flt(row.sec_qty), 3);
	frappe.model.set_value(cdt, cdn, "purchase_kg", purchase_kg);
	frappe.model.set_value(cdt, cdn, "difference_kg", flt(purchase_kg - flt(row.required_kg), 3));
}

frappe.ui.form.on("Material Planning Consolidate Item", {
	length(frm, cdt, cdn) { _recalc_consolidate_item(frm, cdt, cdn); },
	width(frm, cdt, cdn) { _recalc_consolidate_item(frm, cdt, cdn); },
	thickness(frm, cdt, cdn) { _recalc_consolidate_item(frm, cdt, cdn); },
	sec_qty(frm, cdt, cdn) { _recalc_consolidate_item(frm, cdt, cdn); },
});

// ── Reassign Batch dialog for Available Raw Materials (Exact Match) ────────
// Adapted from Material Issue Plan's "Update Batch" dialog
// (material_issue_plan.js:_show_update_batch_dialog / _mip_build_picker) — the
// backend `reassign_batch` already supports this table as a source_table, only
// the UI was missing. Unlike MIP's row shape, Available Raw Material rows live
// directly on this doc (no source_table/source_row indirection, no "already
// transferred" concept) but also carry no unit_weight of their own, so it's
// fetched live from the Item whenever a row (or a cross-item batch) is picked.
const _AM_ALLOC_FIELDS = [
	"current_batch", "current_sec_qty", "current_qty",
	"new_batch_no", "length", "width", "thickness", "sec_qty", "calculated_qty",
	"reserve_without_dimensions",
];

function _am_row_matches_filters(r, f) {
	return (!f.cdn || String(r.customer_drawing_number || "").toLowerCase().includes(f.cdn))
		&& (!f.duno || String(r.duno_mark_no || "").toLowerCase().includes(f.duno))
		&& (!f.so || String(r.sales_order || "").toLowerCase().includes(f.so));
}

function _am_build_picker(dialog, all_rows, on_select) {
	let $wrap = dialog.fields_dict.picker_html.$wrapper;
	let selected_row_name = null;

	let filter_bar = `
		<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px;padding:8px 10px;background:#f8f9fa;border:1px solid #e9ecef;border-radius:4px;">
			<div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:140px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Customer Drawing No")}</label>
				<input id="_am_ub_cdn" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;min-width:100px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("DUNO / Mark No")}</label>
				<input id="_am_ub_duno" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;min-width:120px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Sales Order")}</label>
				<input id="_am_ub_so" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;align-items:flex-start;justify-content:flex-end;padding-bottom:1px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">&nbsp;</label>
				<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
					<button class="btn btn-xs" id="_am_ub_clear"
						style="background:#c62828;color:#fff;border-color:#c62828;">${__("Clear Filters")}</button>
					<span id="_am_ub_count" style="font-size:12px;color:#6c757d;white-space:nowrap;"></span>
				</div>
			</div>
		</div>`;

	let th_style = "white-space:nowrap;padding:6px 10px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;";
	let cols = [
		["item_code", __("Item Code")],
		["duno_mark_no", __("DUNO/Mark No")],
		["customer_drawing_number", __("Cust Drawing No")],
		["sales_order", __("Sales Order")],
		["batch_no", __("Batch No")],
		["sec_qty", __("Sec Qty")],
		["required_qty", __("Required Qty (Kg)")],
		["is_reserved", __("Reserved")],
	];
	let thead = "<tr>" + cols.map((c) => `<th style="${th_style}">${c[1]}</th>`).join("") + "</tr>";

	let table_html = `<div style="overflow-x:auto;">
		<table style="font-size:12px;border-collapse:collapse;width:100%;min-width:700px;">
			<thead style="position:sticky;top:0;z-index:1;">${thead}</thead>
			<tbody id="_am_ub_tbody"></tbody>
		</table>
	</div>`;

	$wrap.html(filter_bar + `<div style="max-height:32vh;overflow-y:auto;border:1px solid #e9ecef;border-radius:4px;">${table_html}</div>`);

	function _render_rows(rows) {
		let $tbody = $wrap.find("#_am_ub_tbody");
		$tbody.html(rows.map((r) => {
			let is_selected = r.name === selected_row_name;
			let row_style = `cursor:pointer;${is_selected ? "background:#e3f2fd;" : ""}`;
			let cells = [
				frappe.utils.escape_html(r.item_code || ""),
				frappe.utils.escape_html(r.duno_mark_no || ""),
				frappe.utils.escape_html(r.customer_drawing_number || ""),
				frappe.utils.escape_html(r.sales_order || ""),
				frappe.utils.escape_html(r.batch_no || "—"),
				format_number(flt(r.sec_qty), null, 3),
				format_number(flt(r.required_qty), null, 3),
				r.is_reserved ? `<span style="color:#2e7d32;font-weight:600;">${__("Yes")}</span>` : __("No"),
			];
			return `<tr data-name="${frappe.utils.escape_html(r.name)}" style="${row_style}">`
				+ cells.map((c) => `<td style="padding:5px 10px;white-space:nowrap;border-bottom:1px solid #f0f0f0;">${c}</td>`).join("")
				+ "</tr>";
		}).join(""));
		$wrap.find("#_am_ub_count").text(__("{0} shown", [rows.length]));

		$tbody.find("tr").on("click", function() {
			let row = all_rows.find((r) => r.name === $(this).data("name"));
			if (row) on_select(row);
		});
	}

	function _get_filters() {
		return {
			cdn: (($wrap.find("#_am_ub_cdn").val()) || "").toLowerCase().trim(),
			duno: (($wrap.find("#_am_ub_duno").val()) || "").toLowerCase().trim(),
			so: (($wrap.find("#_am_ub_so").val()) || "").toLowerCase().trim(),
		};
	}

	function _apply_filter() {
		let f = _get_filters();
		_render_rows(all_rows.filter((r) => _am_row_matches_filters(r, f)));
	}

	$wrap.find("#_am_ub_cdn, #_am_ub_duno, #_am_ub_so").on("input", _apply_filter);
	$wrap.find("#_am_ub_clear").on("click", function() {
		$wrap.find("#_am_ub_cdn, #_am_ub_duno, #_am_ub_so").val("");
		_apply_filter();
	});

	_render_rows(all_rows);

	return {
		markSelected(row_name) {
			selected_row_name = row_name;
			_apply_filter();
		},
		setFilters(cdn, duno, so) {
			$wrap.find("#_am_ub_cdn").val(cdn || "");
			$wrap.find("#_am_ub_duno").val(duno || "");
			$wrap.find("#_am_ub_so").val(so || "");
			_apply_filter();
		},
	};
}

function _show_exact_match_reassign_dialog(frm, preselect_row_name) {
	let all_rows = frm.doc.available_raw_materials || [];
	if (!all_rows.length) {
		frappe.msgprint(__("No rows in Available Raw Materials (Exact Match)."));
		return;
	}

	let selected_row = null;
	let selected_group = null;
	let selected_unit_weight = 0;

	let dialog = new frappe.ui.Dialog({
		title: __("Reassign Batch — Available Raw Materials (Exact Match)"),
		size: "extra-large",
		fields: [
			{ fieldtype: "HTML", fieldname: "picker_html" },
			{ fieldtype: "HTML", fieldname: "no_selection_html" },
			{ fieldtype: "Section Break", label: __("Current Allocation") },
			{ fieldname: "current_batch", fieldtype: "Data", label: __("Current Batch"), read_only: 1 },
			{ fieldname: "current_sec_qty", fieldtype: "Float", label: __("Current Sec Qty (Nos)"), read_only: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "current_qty", fieldtype: "Float", label: __("Current Required Qty (Kg)"), read_only: 1 },
			{ fieldtype: "HTML", fieldname: "cross_item_notice_html" },
			{ fieldtype: "Section Break", label: __("New Allocation"), fieldname: "new_alloc_section" },
			{ fieldname: "new_batch_no", fieldtype: "Link", options: "Batch", label: __("New Batch"), reqd: 1,
				description: __("Length/Width/Thickness are fetched from the batch automatically.") },
			{ fieldname: "length", fieldtype: "Float", label: __("Length (mm)"), read_only: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "width", fieldtype: "Float", label: __("Width (mm)"), read_only: 1 },
			{ fieldname: "thickness", fieldtype: "Float", label: __("Thickness (mm)"), read_only: 1 },
			{ fieldname: "sec_qty", fieldtype: "Float", label: __("Sec Qty (Nos)") },
			{ fieldname: "calculated_qty", fieldtype: "Float", label: __("Calculated Qty (Kg)"), read_only: 1 },
			{ fieldname: "reserve_without_dimensions", fieldtype: "Check", label: __("Reserve Without Dimensions") },
		],
		primary_action_label: __("Reassign Batch"),
		primary_action(values) {
			if (!selected_row) {
				frappe.msgprint(__("Select a row first."));
				return;
			}
			if (!values.new_batch_no) {
				frappe.msgprint(__("Select a New Batch."));
				return;
			}
			frappe.call({
				method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.reassign_batch",
				args: {
					material_planning_name: frm.doc.name,
					source_table: "Material Planning Available Raw Material",
					row_name: selected_row.name,
					new_batch_no: values.new_batch_no,
					dimensions: JSON.stringify({ length: values.length, width: values.width, thickness: values.thickness }),
					sec_qty: values.sec_qty,
					reserve_without_dimensions: values.reserve_without_dimensions ? 1 : 0,
				},
				freeze: true,
				freeze_message: __("Reassigning batch…"),
				callback(r) {
					let warnings = (r.message && r.message.warnings) || [];
					if (warnings.length) {
						frappe.msgprint({
							title: __("Reallocation Warnings"),
							indicator: "orange",
							message: warnings.map((w) =>
								w.reason || `${w.item_code} (${w.batch}): ${__("short by")} ${w.shortfall_qty}`
							).join("<br>"),
						});
					}
					let reassigned_row_name = selected_row.name;
					frm._grid_btns_added = false;
					frm.reload_doc().then(() => {
						all_rows.splice(0, all_rows.length, ...(frm.doc.available_raw_materials || []));
						let updated_row = all_rows.find((r) => r.name === reassigned_row_name);
						if (updated_row) {
							_select_row(updated_row);
						} else {
							picker.markSelected(null);
							_toggle_allocation_fields(false);
							frappe.msgprint({
								title: __("Moved to Material Mapping"),
								indicator: "blue",
								message: __("The new batch belongs to a different item — this row moved to Material Mapping (Alternate Stock)."),
							});
						}
					});
				},
			});
		},
	});

	dialog.fields_dict.no_selection_html.$wrapper.html(
		`<div style="color:#8d99a6;padding:8px 4px;font-size:12px;">`
		+ __("Select a row above to review its current allocation and reassign a new batch.")
		+ `</div>`
	);
	dialog.fields_dict.cross_item_notice_html.$wrapper.html("");

	function _toggle_allocation_fields(show) {
		_AM_ALLOC_FIELDS.forEach((f) => dialog.fields_dict[f].toggle(show));
		dialog.fields_dict.no_selection_html.toggle(!show);
	}

	function _calc_new_qty() {
		if (!selected_row) return;
		let kg_per_nos = _kg_per_nos(selected_group, dialog.get_value("length"), dialog.get_value("width"), dialog.get_value("thickness"), selected_unit_weight);
		dialog.set_value("calculated_qty", flt(kg_per_nos * flt(dialog.get_value("sec_qty")), 3));
	}

	function _fetch_batch_dims_and_item(batch_no) {
		if (!batch_no) {
			dialog.set_value("length", 0);
			dialog.set_value("width", 0);
			dialog.set_value("thickness", 0);
			dialog.set_value("calculated_qty", 0);
			dialog.fields_dict.cross_item_notice_html.$wrapper.html("");
			return;
		}
		frappe.db.get_value("Batch", batch_no, ["item", "custom_length", "custom_width", "custom_thickness"]).then((r) => {
			let d = r.message || {};
			dialog.set_value("length", flt(d.custom_length));
			dialog.set_value("width", flt(d.custom_width));
			dialog.set_value("thickness", flt(d.custom_thickness));

			let batch_item = d.item;
			let is_cross_item = selected_row && batch_item && batch_item !== selected_row.item_code;
			dialog.fields_dict.cross_item_notice_html.$wrapper.html(
				is_cross_item
					? `<div style="background:#e3f2fd;border:1px solid #2490ef;border-radius:4px;padding:8px 12px;margin:6px 0;color:#0d47a1;font-size:12px;">`
						+ __("This batch belongs to a different item ({0}) — on save this row will move to Material Mapping (Alternate Stock).", [batch_item])
						+ `</div>`
					: ""
			);

			if (batch_item) {
				frappe.db.get_value("Item", batch_item, ["custom_unit_weight", "custom_parent_item_group"]).then((r2) => {
					let id = r2.message || {};
					selected_unit_weight = flt(id.custom_unit_weight);
					selected_group = id.custom_parent_item_group || (selected_row && selected_row.parent_item_group);
					_calc_new_qty();
				});
			} else {
				_calc_new_qty();
			}
		});
	}
	dialog.fields_dict.new_batch_no.df.onchange = () => _fetch_batch_dims_and_item(dialog.get_value("new_batch_no"));
	dialog.fields_dict.sec_qty.df.onchange = () => _calc_new_qty();
	dialog.fields_dict.sec_qty.$input && dialog.fields_dict.sec_qty.$input.on("input", _calc_new_qty);

	function _toggle_rwd(checked) {
		dialog.fields_dict.sec_qty.df.read_only = checked ? 1 : 0;
		dialog.fields_dict.sec_qty.refresh();
		if (checked) dialog.set_value("sec_qty", 0);
	}
	dialog.fields_dict.reserve_without_dimensions.df.onchange = () =>
		_toggle_rwd(dialog.get_value("reserve_without_dimensions"));

	function _select_row(row) {
		selected_row = row;
		selected_group = row.parent_item_group;
		selected_unit_weight = 0;
		frappe.db.get_value("Item", row.item_code, "custom_unit_weight").then((r) => {
			selected_unit_weight = flt((r.message || {}).custom_unit_weight);
		});
		dialog.set_value("current_batch", row.batch_no || __("(none)"));
		dialog.set_value("current_sec_qty", flt(row.sec_qty));
		dialog.set_value("current_qty", flt(row.overall_required_qty || row.required_qty));
		dialog.set_value("new_batch_no", "");
		dialog.set_value("length", 0);
		dialog.set_value("width", 0);
		dialog.set_value("thickness", 0);
		dialog.set_value("sec_qty", 0);
		dialog.set_value("calculated_qty", 0);
		dialog.set_value("reserve_without_dimensions", 0);
		dialog.fields_dict.cross_item_notice_html.$wrapper.html("");
		_toggle_allocation_fields(true);
		_toggle_rwd(0);
		picker.markSelected(row.name);
	}

	_toggle_allocation_fields(false);
	let picker = _am_build_picker(dialog, all_rows, _select_row);

	if (preselect_row_name) {
		let row = all_rows.find((r) => r.name === preselect_row_name);
		if (row) {
			picker.setFilters(row.customer_drawing_number, row.duno_mark_no, row.sales_order);
			_select_row(row);
		}
	}

	dialog.show();
}

// ── Cut Sheet live preview (both raw-material tables) ────────────────────────
// A cut plan can now be decided here at planning time and seeds the Material
// Issue Plan's own row. This is immediate feedback only: the authoritative Kg
// recompute is material_planning.py's validate() -> _sync_cut_sheet_calc, and
// the actual transfer cap / batch resize happen on the Material Issue Plan side.
// Thickness comes from the batch, never from the requirement — a cut changes
// Length and Width, never how thick the steel is.
function _mp_recalc_cut_sheet_qty(cdt, cdn, prefix) {
	let row = locals[cdt][cdn];
	let g = row.batch_parent_item_group || row.parent_item_group;
	let T = row.batch_thickness || row.thickness;
	let uw = row.batch_unit_weight || row.unit_weight;
	let L = row[prefix + "_length"], W = row[prefix + "_width"], S = row[prefix + "_sec_qty"];
	let qty = null;
	if (g === "Structurals") {
		if (L && uw && S) qty = (L / 1000) * uw * S;
	} else if (g === "Plates") {
		if (L && W && T && uw && S) qty = (L / 1000) * (W / 1000) * T * uw * S;
	}
	frappe.model.set_value(cdt, cdn, prefix + "_calc_qty", qty !== null ? flt(qty, 3) : 0);
}

["Material Planning Material Mapping", "Material Planning Available Raw Material"].forEach(function (dt) {
	frappe.ui.form.on(dt, {
		use_length(frm, cdt, cdn)      { _mp_recalc_cut_sheet_qty(cdt, cdn, "use"); },
		use_width(frm, cdt, cdn)       { _mp_recalc_cut_sheet_qty(cdt, cdn, "use"); },
		use_sec_qty(frm, cdt, cdn)     { _mp_recalc_cut_sheet_qty(cdt, cdn, "use"); },
		balance_length(frm, cdt, cdn)  { _mp_recalc_cut_sheet_qty(cdt, cdn, "balance"); },
		balance_width(frm, cdt, cdn)   { _mp_recalc_cut_sheet_qty(cdt, cdn, "balance"); },
		balance_sec_qty(frm, cdt, cdn) { _mp_recalc_cut_sheet_qty(cdt, cdn, "balance"); },
	});
});
