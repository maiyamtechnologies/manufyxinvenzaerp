frappe.ui.form.on("Material Issue Plan", {
	refresh(frm) {
		// Once auto-completed (stock received + every excess row resolved --
		// see _maybe_mark_completed in material_issue_plan.py), lock the whole
		// document: no more edits, and skip adding the transfer/return/final-SE
		// action buttons below. The matching whitelisted endpoints also refuse
		// directly (_ensure_mip_editable), so this is UI convenience on top of
		// a real server-side lock, not the only thing enforcing it.
		// Added before the Completed lock below: opening the Job Work Order is
		// navigation, not an edit, and is just as useful on a finished plan.
		_add_open_sco_button(frm);

		if (frm.doc.status === "Completed") {
			frm.disable_form();
			frappe.show_alert({
				message: __("This Material Issue Plan is Completed and locked for further changes."),
				indicator: "green",
			});
			return;
		}

		frm.set_query("subcontracting_order", () => ({
			filters: { custom_production_plan: frm.doc.production_plan || "" },
		}));
		frm.set_query("work_order", () => ({
			filters: { production_plan: frm.doc.production_plan || "" },
		}));
		// Scope every warehouse field to the document's own Company — previously
		// unfiltered, showing every warehouse across every company. Group
		// warehouses are excluded too: they are only tree nodes (e.g. "All
		// Warehouses"), stock can never sit in one, so picking one here would set
		// a warehouse no transfer could ever move material into or out of.
		["source_warehouse", "supplier_warehouse", "cnc_warehouse", "excess_return_warehouse"].forEach((fieldname) => {
			frm.set_query(fieldname, () => ({
				filters: { company: frm.doc.company || "", is_group: 0 },
			}));
		});
		_lock_raw_materials_row_adding(frm);
		// Batches are now reassigned from Consolidate Items only, at the client's
		// request (Sep 2026). The Raw Materials toolbar button is no longer added and
		// its per-row button is hidden in the child doctype; both are kept, not deleted,
		// so they can be brought back. View All stays in the Raw Materials top toolbar.
		// _add_update_batch_button(frm);
		_add_view_all_raw_materials_button(frm);
		_add_consolidate_update_batch_button(frm);
		// The Manual button is removed at the client's request in favour of one
		// doctype-wise ERP Manual page (production_management/page/erp_manual),
		// added to a Workspace separately rather than linked from here. The
		// per-doctype material-issue-plan-manual page it used to open has since
		// been deleted outright -- all manual content now lives in ERP Manual.
		_add_transfer_buttons(frm);
		_add_download_button(frm);
		_render_excess_action_btn(frm);
		_add_final_stock_entry_button(frm);
		_add_process_loss_button(frm);
		_mip_paint_buttons(frm);

		// Recompute excess return totals on load so the summary fields are
		// always in sync with the child table rows (previously only recalculated
		// on field changes, leaving stale/zero values after save + reload).
		_mip_excess_totals(frm);
	},

	load_drawings_btn(frm) {
		_load_mip_drawings(frm);
	},

	refresh_raw_materials_btn(frm) {
		let rows = frm.doc.raw_materials || [];

		function do_refresh() {
			frappe.call({
				method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.refresh_mip_raw_materials_manual",
				args: { mip_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Refreshing raw materials..."),
				callback() {
					frm.reload_doc();
				},
			});
		}

		function maybe_confirm_then_refresh() {
			// Nothing transferred, but rows already exist -- batch mapping, excess
			// material mapping, cut sheet, or excess return edits may already be on
			// them. Refreshing rebuilds the table from scratch, so confirm first.
			if (rows.length) {
				frappe.confirm(
					__("Batch mapping, Excess Material Mapping, or other changes may already be made on these rows. Refreshing will remove all current rows and rebuild them fresh. Are you sure you want to continue?"),
					do_refresh
				);
			} else {
				do_refresh();
			}
		}

		// Live check against submitted Stock Entries -- deliberately NOT based on
		// raw_materials.transferred_qty on the currently-loaded doc, which only
		// gets (re)computed by a refresh itself and so reads stale (still 0) right
		// after a transfer if nothing has refreshed this table since. Server enforces
		// the same check too (refresh_mip_raw_materials_manual); this pre-flight call
		// is what avoids showing the "are you sure?" confirm before that hard block.
		frappe.call({
			method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.check_mip_raw_materials_refreshable",
			args: { mip_name: frm.doc.name },
			callback(r) {
				if (r.message && r.message.blocked) {
					frappe.msgprint({
						title: __("Cannot Refresh"),
						indicator: "red",
						message: r.message.message,
					});
					return;
				}
				maybe_confirm_then_refresh();
			},
		});
	},
});

// "Load Drawings" — sits right under the Production Plan field. Saves first if
// needed (a new/dirty doc has nothing to populate_from_production_plan against
// until it has a name), then loads every drawing + raw material.
function _load_mip_drawings(frm) {
	if (!frm.doc.production_plan) {
		frappe.msgprint(__("Select a Production Plan first."));
		return;
	}
	function _load() {
		frappe.call({
			method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.populate_from_production_plan",
			args: { mip_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Loading drawings from Production Plan..."),
			callback() { frm.reload_doc(); },
		});
	}
	if (frm.is_new() || frm.is_dirty()) {
		frm.save().then(_load);
	} else {
		_load();
	}
}

// "Make Final Stock Entry" — moved here from the Job Work Order (client change
// request). Creates a draft Manufacture Stock Entry that consumes the raw material
// belonging to the drawings the last operation has finished, and produces those
// drawings as finished goods. The stock-return workflow (Return Excess Entry)
// already lives on this doctype, so the finished-goods entry is raised from the
// same place.
function _add_final_stock_entry_button(frm) {
	if (frm.is_new() || !frm.doc.subcontracting_order) return;

	// Shown as soon as the LAST operation exists, not once every operation on every
	// drawing is done. A job of ten drawings that has finished four could not book
	// those four before, so finished steel sat at the supplier with nothing to show
	// for it until the last piece of the last drawing was painted.
	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.subcontracting.get_final_stock_entry_preview",
		args: { sco_name: frm.doc.subcontracting_order },
		callback(r) {
			let p = r.message;
			if (!p || !p.final_operation) return;
			frm.add_custom_button(__("Make Final Stock Entry"), function() {
				_show_final_stock_entry_preview(frm);
			});
			// Painted here, not in _mip_paint_buttons: this button is added from a
			// frappe.call callback, so it does not exist yet when that runs.
			window.mfx_paint_button && window.mfx_paint_button(frm, "Make Final Stock Entry", "primary");
		},
	});
}

// What is about to be booked, before anything is created. "Four of ten" is a fact
// somebody should see and agree with, not discover in a draft.
//
// The finished weight is decided HERE and nowhere else: on the draft Stock Entry the
// Kg is read-only, so this table is the one place a weighed figure can be entered.
// Beside it sits the steel the entry will consume for that drawing, and the difference
// between the two -- which is the whole point of the screen. Weight that goes in and
// does not come out is loss; weight that comes out above what went in is not a loss at
// all but a sign the Sales Order was written for too little.
function _show_final_stock_entry_preview(frm) {
	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.subcontracting.get_final_stock_entry_preview",
		args: { sco_name: frm.doc.subcontracting_order },
		freeze: true,
		freeze_message: __("Checking what is complete…"),
		callback(r) {
			let p = r.message || {};
			if (!p.final_operation) {
				frappe.msgprint({
					title: __("No Final Operation"),
					indicator: "orange",
					message: __("The final operation has not been created for this Job Work Order yet."),
				});
				return;
			}

			let lead = __("Last operation: <b>{0}</b> — {1} of {2} pieces completed across {3} drawing(s).", [
				p.final_operation.operation, flt(p.total_completed, 3),
				flt(p.total_planned, 3), (p.drawings || []).length]);

			let rows = (p.drawings || []).filter((d) => flt(d.ready_to_book) > 0);
			let editable = !!p.edit_fg_stock_kg;

			if (!p.can_create || !rows.length) {
				frappe.msgprint({
					title: __("Nothing to Book"),
					indicator: "orange",
					message: `<p>${lead}</p><p style="color:#555">${p.reason || ""}</p>`,
				});
				return;
			}

			let d = new frappe.ui.Dialog({
				title: __("Make Final Stock Entry"),
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "body" }],
				primary_action_label: __("Create Stock Entry"),
				primary_action() {
					let weights = _fse_collect_weights(d, rows);
					let over = _fse_overbooked(d, rows, weights);
					if (!over.length) {
						d.hide();
						_create_final_stock_entry(frm, weights);
						return;
					}
					// Booking more than was consumed is not refused -- it is usually right,
					// and it means the order is written for too little. It is confirmed,
					// because it also puts more finished goods in stock than the Sales
					// Order can deliver against.
					frappe.confirm(
						__("These drawings book more weight than the entry consumes:") +
							"<br><br>" + over.map((o) =>
								`<b>${frappe.utils.escape_html(o.duno)}</b> — +${format_number(o.kg, null, 3)} Kg`
							).join("<br>") +
							"<br><br>" +
							__("Update the weight in the Sales Order for correct billing. Create the stock entry anyway?"),
						() => { d.hide(); _create_final_stock_entry(frm, weights); }
					);
				},
			});

			_mfx_inject_fg_theme();
			d.$wrapper.addClass("mfx-fg-theme");
			d.fields_dict.body.$wrapper.html(
				`<div class="mfx-fg-pane">
					<div class="mfx-fg-head">${__("Finished Goods")}</div>
					<p style="margin-bottom:8px">${lead}</p>`
				+ _fse_table(rows, editable) + _fse_footnote(p, editable) +
				`</div>`
			);
			_fse_bind(d, rows);
			d.show();
		},
	});
}

// One row per drawing ready to book. The FG item is named once in the footnote rather
// than repeated down a column -- it is the same item on every row of a job.
function _fse_table(rows, editable) {
	let body = rows.map(function (dw, i) {
		let per_nos = flt(dw.cust_weight_per_nos);
		let nos = flt(dw.ready_to_book);
		let consumed = dw.consumed_rm_kg === null || dw.consumed_rm_kg === undefined
			? null : flt(dw.consumed_rm_kg);
		// Two rates side by side: what the customer says a piece weighs, which never
		// changes here, and what is actually being booked, which is the same figure
		// until somebody weighs it and types a different one.
		let cell = editable
			? `<input type="number" step="0.001" min="0" class="form-control input-xs fse-per-nos"
			          data-idx="${i}" value="${per_nos}"
			          style="text-align:right;height:24px;padding:2px 6px;font-size:11px;width:92px">`
			: `<span>${format_number(per_nos, null, 2)}</span>`;
		return `<tr data-idx="${i}">
			<td style="padding:3px 6px">
				<b>${frappe.utils.escape_html(String(dw.duno_mark_no || ""))}</b><br>
				<span style="color:#888">${frappe.utils.escape_html(String(dw.customer_drawing_number || dw.drawing || ""))}</span>
			</td>
			<td style="padding:3px 6px;text-align:right">${flt(dw.qty_to_manufacture, 3)}</td>
			<td style="padding:3px 6px;text-align:right">${flt(dw.completed_qty_nos, 3)}</td>
			<td style="padding:3px 6px;text-align:right">${flt(dw.already_booked, 3)}</td>
			<td style="padding:3px 6px;text-align:right;font-weight:600">${nos}</td>
			<td style="padding:3px 6px;text-align:right;color:#555">${format_number(per_nos, null, 2)}</td>
			<td style="padding:3px 6px;text-align:right">${cell}</td>
			<td style="padding:3px 6px;text-align:right" class="fse-consumed">${
				consumed === null ? "—" : format_number(consumed, null, 3)}</td>
			<td style="padding:3px 6px;text-align:right;font-weight:600" class="fse-fgtotal"></td>
			<td style="padding:3px 6px;text-align:right" class="fse-loss"></td>
		</tr>`;
	}).join("");

	return `<table class="table table-bordered table-condensed" style="font-size:11px;margin:8px 0">
		<thead><tr>
			<th>${__("DUNO / Drawing")}</th>
			<th style="text-align:right">${__("To Make")}</th>
			<th style="text-align:right">${__("Completed")}</th>
			<th style="text-align:right">${__("Already Booked")}</th>
			<th style="text-align:right">${__("Booking Now")}</th>
			<th style="text-align:right">${__("Cust Wt per Nos")}</th>
			<th style="text-align:right">${__("FG Wt per Nos")}</th>
			<th style="text-align:right">${__("Consumed RM Wt")}</th>
			<th style="text-align:right">${__("FG Total wt")}</th>
			<th style="text-align:right">${__("Loss")}</th>
		</tr></thead>
		<tbody>${body}</tbody>
		<tfoot><tr style="font-weight:600">
			<td style="padding:3px 6px">${__("Total")}</td>
			<td colspan="3"></td>
			<td style="padding:3px 6px;text-align:right" class="fse-t-nos"></td>
			<td colspan="2"></td>
			<td style="padding:3px 6px;text-align:right" class="fse-t-consumed"></td>
			<td style="padding:3px 6px;text-align:right" class="fse-t-fgtotal"></td>
			<td style="padding:3px 6px;text-align:right" class="fse-t-loss"></td>
		</tr></tfoot>
	</table>`;
}

function _fse_footnote(p, editable) {
	let note = __("On submission the raw material is consumed from the supplier warehouse and converted into finished goods. Where the finished weight is lower, the difference is recorded as process loss and shown in the report.");
	let edit = editable
		? __("Cust Wt per Nos is editable here — enter the weighed figure. This is the only place it can be set; on the stock entry itself it is read-only.")
		: __("Cust Wt per Nos is read-only: switch on <b>Edit FG Stock Kg</b> in Manufyxinvenza Settings to enter a weighed figure.");
	return `<p class="mfx-fg-note">${__("<b>{0} piece(s)</b> will be booked into finished goods, and only the raw material belonging to those drawings will be consumed. The rest stays at the supplier for a later entry.", [flt(p.total_ready, 3)])}</p>
		<p class="mfx-fg-note">${note}</p>
		<p class="mfx-fg-note-dim">${edit}</p>`;
}

// Recalculated on every keystroke: FG Total = Cust Wt per Nos x Booking Now, and the
// Loss beside it is the consumed steel less that figure.
function _fse_bind(d, rows) {
	let $w = d.fields_dict.body.$wrapper;
	let paint = function () {
		let t_nos = 0, t_consumed = 0, t_fg = 0, t_loss = 0, any_consumed = false;
		rows.forEach(function (dw, i) {
			let $tr = $w.find(`tr[data-idx="${i}"]`);
			let per_nos = flt($tr.find(".fse-per-nos").val() || dw.cust_weight_per_nos);
			let nos = flt(dw.ready_to_book);
			let fg = flt(per_nos * nos, 3);
			let consumed = dw.consumed_rm_kg === null || dw.consumed_rm_kg === undefined
				? null : flt(dw.consumed_rm_kg);

			$tr.find(".fse-fgtotal").text(format_number(fg, null, 3));
			t_nos += nos;
			t_fg += fg;

			if (consumed === null) {
				$tr.find(".fse-loss").text("—").css("color", "#999");
				return;
			}
			any_consumed = true;
			t_consumed += consumed;
			let loss = flt(consumed - fg, 3);
			t_loss += loss;
			if (loss > 0.0005) {
				$tr.find(".fse-loss").text(format_number(loss, null, 3)).css("color", "#a06000");
			} else if (loss < -0.0005) {
				$tr.find(".fse-loss")
					.html(`+${format_number(-loss, null, 3)}<br><span style="font-size:10px">${__("update Sales Order")}</span>`)
					.css("color", "#c0392b");
			} else {
				$tr.find(".fse-loss").text("—").css("color", "#999");
			}
		});
		$w.find(".fse-t-nos").text(flt(t_nos, 3));
		$w.find(".fse-t-consumed").text(any_consumed ? format_number(t_consumed, null, 3) : "—");
		$w.find(".fse-t-fgtotal").text(format_number(t_fg, null, 3));
		$w.find(".fse-t-loss")
			.text(any_consumed ? format_number(t_loss, null, 3) : "—")
			.css("color", t_loss < -0.0005 ? "#c0392b" : (t_loss > 0.0005 ? "#a06000" : "#999"));
	};
	$w.on("input change", ".fse-per-nos", paint);
	paint();
}

function _fse_collect_weights(d, rows) {
	let $w = d.fields_dict.body.$wrapper;
	let out = {};
	rows.forEach(function (dw, i) {
		let v = flt($w.find(`tr[data-idx="${i}"] .fse-per-nos`).val() || dw.cust_weight_per_nos);
		if (v > 0) out[dw.drawing] = v;
	});
	return out;
}

// Drawings booking more weight than the entry consumes for them.
function _fse_overbooked(d, rows, weights) {
	let out = [];
	rows.forEach(function (dw) {
		let consumed = dw.consumed_rm_kg;
		if (consumed === null || consumed === undefined) return;
		let fg = flt(flt(weights[dw.drawing] || dw.cust_weight_per_nos) * flt(dw.ready_to_book), 3);
		let diff = flt(flt(consumed) - fg, 3);
		if (diff < -0.0005) out.push({ duno: dw.duno_mark_no || dw.drawing, kg: -diff });
	});
	return out;
}

function _create_final_stock_entry(frm, weights) {
	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.subcontracting.create_finished_goods_entry",
		args: {
			sco_name: frm.doc.subcontracting_order,
			fg_weights_json: JSON.stringify(weights || {}),
		},
		freeze: true,
		freeze_message: __("Creating Final Stock Entry…"),
		callback: function (r) {
			if (!r.message) return;
			let se_name = r.message.name;
			let already = r.message.already_existed;
			frappe.msgprint({
				title: already ? __("Final Stock Entry Updated") : __("Final Stock Entry Created"),
				message: (already
						? __("A draft Final Stock Entry already existed for this Job Work Order and has been rebuilt with these figures. ")
						: "")
					+ __("Review and submit the stock entry: ") +
					'<a href="/app/stock-entry/' + encodeURIComponent(se_name) + '">' + se_name + "</a>",
				indicator: already ? "orange" : "green",
			});
		},
	});
}

// No manual rows on Raw Materials. Every row here is a snapshot of a reserved
// Material Planning row (source_table + source_row point back at it), so a
// hand-typed row describes a reservation that does not exist: it survives until
// the next Refresh Raw Materials, transfers nothing, and reconciles against
// nothing.
//
// material_issue_plan.json has carried `"cannot_add_rows": 1` on this table for
// a while and it has never done anything, which is worth spelling out because
// the JSON reads like the job is done. `cannot_add_rows` is NOT a property of
// the DocField doctype in Frappe v15.116.0 -- grep docfield.json, it is not
// there. It exists only as a runtime flag the browser reads off the grid object
// (frappe/public/js/frappe/form/grid.js: `this.cannot_add_rows || (this.df &&
// this.df.cannot_add_rows)`). Syncing the doctype drops the unknown key, so
// df.cannot_add_rows is undefined at runtime and Add Row keeps showing.
//
// Setting it on the grid object itself is the path grid.js actually reads. The
// JSON key is left in place: it is harmless, and it states the intent for
// whoever reads the doctype next.
function _lock_raw_materials_row_adding(frm) {
	let grid = frm.fields_dict["raw_materials"] && frm.fields_dict["raw_materials"].grid;
	if (!grid) return;
	grid.cannot_add_rows = true;
	// refresh() re-renders the footer that carries the Add Row link. Without it
	// the button stays on screen until something else redraws the grid.
	grid.refresh();
}

// "View All" — raw_materials can run past 100 rows, well beyond the grid's
// default page size, and the grid also hides several columns (Planned Item/
// Alternate, Batch) at normal width. Show every row and column in one popup,
// mirroring the same pattern used on Material Planning/Sales Order.
function _add_view_all_raw_materials_button(frm) {
	let grid = frm.fields_dict["raw_materials"] && frm.fields_dict["raw_materials"].grid;
	if (!grid || frm.is_new()) return;

	// "top" (.grid-custom-buttons), beside Update Batch. Two reasons it cannot
	// stay at the bottom: on a 100-row table the footer is a long scroll away
	// from the toolbar people are already using, and -- the same trap
	// _add_update_batch_button documents -- Frappe hides .grid-footer entirely
	// once every row fits on one page, which silently takes the button with it.
	grid.add_custom_button(
		frappe.utils.icon("view", "xs") + " " + __("View All"),
		() => _show_mip_raw_materials_popup(frm),
		"top"
	);
}

const _MIP_RAW_MATERIAL_COLS = [
	{ fieldname: "item_code",              label: "Item Code" },
	{ fieldname: "item_name",               label: "Item Name" },
	{ fieldname: "planned_item",             label: "Planned Item (Alternate)" },
	{ fieldname: "batch_no",                label: "Batch" },
	{ fieldname: "duno_mark_no",             label: "DUNO/Mark No" },
	{ fieldname: "customer_drawing_number",   label: "Cust Drawing Number" },
	{ fieldname: "sales_order",              label: "Sales Order" },
	{ fieldname: "material_planning",        label: "Material Planning" },
	{ fieldname: "parent_item_group",        label: "Item Group" },
	{ fieldname: "length",                  label: "Length (mm)" },
	{ fieldname: "width",                   label: "Width (mm)" },
	{ fieldname: "thickness",               label: "Thickness" },
	{ fieldname: "sec_qty",                 label: "NOS" },
	{ fieldname: "qty",                     label: "Weight (Kg)" },
	{ fieldname: "transferred_qty",          label: "Transferred Qty" },
	{ fieldname: "is_reserved",              label: "Reserved" },
	{ fieldname: "is_unavailable",           label: "Unavailable" },
	{ fieldname: "cnc_process",             label: "CNC Process" },
];

function _show_mip_raw_materials_popup(frm) {
	let rows = frm.doc.raw_materials || [];
	if (!rows.length) {
		frappe.msgprint(__("No data to display."));
		return;
	}

	let th_style = "white-space:nowrap;padding:6px 10px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;";
	let thead = "<tr>" + _MIP_RAW_MATERIAL_COLS.map(c =>
		`<th style="${th_style}">${__(c.label)}</th>`
	).join("") + "</tr>";

	function _render_tbody(filtered_rows) {
		return filtered_rows.map(function (row, idx) {
			let cells = _MIP_RAW_MATERIAL_COLS.map(function (c) {
				let val = row[c.fieldname];
				if (val === null || val === undefined) val = "";
				return `<td style="padding:5px 10px;white-space:nowrap;border-bottom:1px solid #f0f0f0;">${frappe.utils.escape_html(String(val))}</td>`;
			}).join("");
			let bg = idx % 2 !== 0 ? "background:#fafbfc;" : "";
			return `<tr style="${bg}">${cells}</tr>`;
		}).join("");
	}

	let filter_bar = `<div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;">
		<input id="_mip_vw_duno" type="text" placeholder="${__("Filter DUNO/Mark No…")}"
			style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:180px;">
		<input id="_mip_vw_item" type="text" placeholder="${__("Filter Item Code…")}"
			style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:180px;">
		<span id="_mip_vw_count" style="font-size:12px;color:#6c757d;"></span>
	</div>`;

	let table_html = `<div style="overflow:auto;max-height:65vh;">
		<table style="font-size:12px;border-collapse:collapse;width:100%;" id="_mip_vw_table">
			<thead style="position:sticky;top:0;z-index:1;">${thead}</thead>
			<tbody id="_mip_vw_tbody">${_render_tbody(rows)}</tbody>
		</table>
	</div>`;

	let d = new frappe.ui.Dialog({
		title: __("Raw Materials — {0} item(s)", [rows.length]),
		size: "extra-large",
	});
	d.$body.html(filter_bar + table_html);

	function _apply_filter() {
		let duno_q = (d.$body.find("#_mip_vw_duno").val() || "").toLowerCase();
		let item_q = (d.$body.find("#_mip_vw_item").val() || "").toLowerCase();
		let filtered = rows.filter(function(r) {
			let duno_ok = !duno_q || String(r.duno_mark_no || "").toLowerCase().includes(duno_q);
			let item_ok = !item_q || String(r.item_code || "").toLowerCase().includes(item_q);
			return duno_ok && item_ok;
		});
		d.$body.find("#_mip_vw_tbody").html(_render_tbody(filtered));
		d.$body.find("#_mip_vw_count").text(__("{0} of {1} shown", [filtered.length, rows.length]));
	}
	d.$body.find("#_mip_vw_duno").on("input", _apply_filter);
	d.$body.find("#_mip_vw_item").on("input", _apply_filter);

	d.show();
}

// "Update Batch" — reassign the batch (and optionally dimensions/Sec Qty) already
// selected for a raw-material row. Delegates entirely to Material Planning's own
// reassign_batch, which unreserves, applies the new batch, re-validates mapping
// availability, and re-reserves — this dialog only picks which row and what to change.
function _add_update_batch_button(frm) {
	let grid = frm.fields_dict["raw_materials"] && frm.fields_dict["raw_materials"].grid;
	if (!grid || frm.is_new()) return;

	// "top" (.grid-custom-buttons) rather than the default "bottom"
	// (.grid-buttons, inside .grid-footer) — Frappe hides .grid-footer
	// entirely for a read-only grid once every row fits on one page, which
	// would silently hide this button too if it lived in the bottom toolbar.
	grid.add_custom_button(
		frappe.utils.icon("edit", "xs") + " " + __("Update Batch"),
		() => _show_update_batch_dialog(frm),
		"top"
	);
}

// Per-row "Update Batch" button (Button field on the child doctype) -- opens the
// same dialog as the grid toolbar button, pre-filtered/pre-selected onto this row.
//
// Nothing else on this row is typed any more. Excess Return moved to the Excess
// Material Items table on this same document, and the cut plan to the Cut Sheet
// doctype, where a sheet's nesting is stated once against its batch and shared by
// every job drawing from it. The Cut Sheet sizes still shown on the row are read
// only, because they are what the transfer's Stock Entry carries.
frappe.ui.form.on("Material Issue Plan Raw Material", {
	update_batch_btn(frm, cdt, cdn) {
		_show_update_batch_dialog(frm, locals[cdt][cdn].name);
	},
});

// ── Transfer readiness pre-flight check ──────────────────────────────────────

function _check_transfer_readiness(frm, on_proceed) {
	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.get_mip_readiness_check",
		args: { mip_name: frm.doc.name },
		callback(r) {
			let d = r.message || {};
			// Off-cuts claimed through Excess Material Mapping that are still at the
			// supplier never reach the transfer list (there is no batch in the source
			// warehouse to move). Stashed on the form so the transfer popup can say so
			// outright, instead of the user hunting for a row that will never appear.
			// Not an "issue" -- it is a correct, finished state -- so it must be picked
			// up here, before the has_issues early return.
			frm.__mip_at_supplier = d.at_supplier || [];
			frm.__mip_supplier_warehouse = d.supplier_warehouse || "";
			if (!d.has_issues) {
				on_proceed();
				return;
			}

			// Build issue table
			function _rows(items, label, batch_col) {
				if (!items || !items.length) return "";
				let hdr = batch_col ? `<th>${__("Batch")}</th>` : "";
				let rows = items.map(function(it) {
					let bc = batch_col ? `<td>${it.batch || "-"}</td>` : "";
					return `<tr>
						<td>${it.material_planning}</td>
						<td>${it.table} / Row ${it.row}</td>
						<td>${it.item_code}</td>
						<td>${it.duno_mark_no || "-"}</td>
						${bc}
						<td>${it.qty} ${it.uom}</td>
					</tr>`;
				}).join("");
				return `<p style="margin:10px 0 4px;font-weight:bold">${label}</p>
					<table class="table table-bordered table-condensed" style="font-size:11px">
						<thead><tr>
							<th>${__("Material Planning")}</th>
							<th>${__("Table / Row")}</th>
							<th>${__("Item Code")}</th>
							<th>${__("DUNO/Mark No")}</th>
							${hdr}
							<th>${__("Qty")}</th>
						</tr></thead>
						<tbody>${rows}</tbody>
					</table>`;
			}

			let html = "";

			// CNC Process is a routing instruction, not a preference -- flagged material
			// must go to CNC before the supplier. With no CNC Warehouse there is nowhere
			// valid to send it, so this BLOCKS the transfer outright rather than offering
			// a "proceed anyway" that would physically move stock past the CNC step.
			let cnc = d.cnc_without_warehouse || [];
			if (cnc.length) {
				html += `<div style="border:1px solid #b91c1c;background:#fef2f2;border-radius:6px;padding:12px;margin-bottom:12px;">
					<p style="margin:0 0 6px;font-weight:bold;color:#b91c1c;font-size:13px;">
						🚫 ${__("Transfer blocked — CNC Warehouse is not set ({0} CNC item(s))", [cnc.length])}
					</p>
					<p style="margin:0 0 8px;color:#7f1d1d;">
						${__("These rows are marked <b>CNC Process</b>, so they must go to the <b>CNC Warehouse first</b>, and only then on to {0}. This Material Issue Plan has no CNC Warehouse, so there is nowhere valid to send them.", [frappe.utils.escape_html(frm.doc.supplier_warehouse || __("the supplier/WIP warehouse"))])}
					</p>
					<p style="margin:0;color:#7f1d1d;">
						${__("Fix it in one of two ways: set <b>CNC Warehouse</b> in the Warehouses section, or untick <b>CNC Process</b> on those rows in the Material Planning if the CNC step is not required.")}
					</p>
					${_rows(cnc, __("CNC rows affected"), true)}
				</div>`;
			}

			if (d.unmapped && d.unmapped.length) {
				html += _rows(d.unmapped, `⚠ ${__("Not Mapped / No Batch Assigned ({0} item(s)) — these will NOT be transferred", [d.unmapped.length])}`, false);
			}
			if (d.unreserved && d.unreserved.length) {
				// Reserving is a separate deliberate step on the Material Planning, and
				// unreserved stock is simply never offered for transfer -- with nothing
				// here to explain the gap. Name the plan and the weight so it is obvious
				// where to go and what is at stake.
				let per_mp = (d.unreserved_summary || []).map((s) =>
					`<li><a href="/app/material-planning/${encodeURIComponent(s.material_planning)}" target="_blank"><b>${frappe.utils.escape_html(s.material_planning)}</b></a> — ${s.rows} ${__("row(s)")}, ${format_number(s.qty, null, 3)} Kg</li>`
				).join("");
				html += `<div style="border:1px solid #f59e0b;background:#fffbeb;border-radius:6px;padding:12px;margin-bottom:12px;">
					<p style="margin:0 0 6px;font-weight:bold;color:#92400e;font-size:13px;">
						⚠ ${__("Stock is mapped in Material Planning but NOT reserved ({0} item(s))", [d.unreserved.length])}
					</p>
					<p style="margin:0 0 8px;color:#78350f;">
						${__("These batches are assigned but never reserved, so they will <b>not</b> be transferred and no Stock Entry will be made for them. Open the Material Planning below and run <b>Reserve Batches</b>, then transfer.")}
					</p>
					<ul style="margin:0 0 8px 18px;color:#78350f;">${per_mp}</ul>
					${_rows(d.unreserved, __("Rows awaiting reservation"), true)}
				</div>`;
			}
			if (d.unmapped && d.unmapped.length || d.unreserved && d.unreserved.length) {
				html += `<p style="margin-top:10px;color:#555">
					${__("Ensure stocks are purchased and mapped against Material Planning, or assign batches using the <b>Update Batch</b> option in the Material Issue Plan.")}
				</p>`;
			}

			// A missing CNC Warehouse is a hard stop -- no primary action at all, so the
			// only way on is to fix the routing. The other two issues merely skip rows,
			// which is a judgement call, so those keep "Proceed Anyway".
			let dialog = new frappe.ui.Dialog({
				title: cnc.length
					? __("Transfer Blocked — CNC Warehouse Required")
					: __("Transfer Readiness Check — Issues Found"),
				size: "large",
				fields: [{ fieldtype: "HTML", fieldname: "body", options: html }],
				primary_action_label: cnc.length ? __("Close") : __("Proceed Anyway"),
				primary_action() {
					dialog.hide();
					if (!cnc.length) on_proceed();
				},
			});
			if (!cnc.length) {
				dialog.set_secondary_action_label(__("Cancel"));
				dialog.set_secondary_action(() => dialog.hide());
			}
			dialog.show();
		},
	});
}

// ── Batch Plan PDF ────────────────────────────────────────────────────────────
// Simple, printable reference for the production/supplier team: for this item,
// this batch (with its Sec Qty) is what's planned, per drawing. The preview
// popup and the downloaded PDF render from the exact same server-built HTML
// (get_mip_batch_plan_html), so what you see is exactly what you download.

// Process Loss — the last step, and the one that lets a job close.
//
// 1,836 Kg went out, 116 was used, 1,450 came back. The other 270 is standing at
// the supplier under this job's name, and until it is returned or written off the
// warehouse says the job has material it does not have. Shown only once the Final
// Stock Entry exists: before that, material at the supplier is work in progress.
function _add_process_loss_button(frm) {
	if (frm.is_new() || frm.doc.status === "Completed") return;

	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.get_mip_process_loss_state",
		args: { mip_name: frm.doc.name },
		callback(r) {
			const s = r.message;
			if (!s || !s.final_entry_exists || s.remaining <= 0.001) return;

			frm.add_custom_button(__("Process Loss"), function () {
				_show_process_loss_dialog(frm, s);
			});
			// Red, and the only red button on the form: this one writes stock off.
			// Was a bare btn-danger; now goes through the app-wide palette so it
			// matches the red used elsewhere and survives a theme change.
			window.mfx_paint_button && window.mfx_paint_button(frm, "Process Loss", "danger");
		},
	});
}

function _show_process_loss_dialog(frm, s) {
	const money = (v) => format_number(v, null, 3);

	// The whole chain in one place, because "where did my 1,836 Kg go" is the
	// question being answered.
	let html =
		'<table class="table table-bordered" style="font-size:13px;margin-bottom:12px">' +
		`<tr><td>${__("Transferred to supplier")}</td><td style="text-align:right">${money(s.transferred)} Kg</td></tr>` +
		`<tr><td>${__("Used in Final Stock Entry")}</td><td style="text-align:right">${money(s.used_in_fg)} Kg</td></tr>` +
		`<tr><td>${__("Excess actually returned")}</td><td style="text-align:right">${money(s.returned)} Kg</td></tr>` +
		`<tr style="font-weight:700;background:#fff5f5"><td>${__("Still at the supplier — to write off")}</td>` +
		`<td style="text-align:right;color:#c62828">${money(s.remaining)} Kg</td></tr>` +
		"</table>";

	if (s.pending_return_kg > 0.001) {
		html +=
			'<div style="padding:10px 12px;background:#fff8e1;border-left:3px solid #f9a825;border-radius:3px;font-size:12px;margin-bottom:10px">' +
			"<b>" + __("{0} Kg is still declared to return and has not come back.", [money(s.pending_return_kg)]) + "</b><br>" +
			__("Make the Return Excess entry for it — or tick below to say it is not coming, and it will be written off with the rest.") +
			"</div>";
	}

	if (s.claimed && s.claimed.length) {
		html +=
			'<div style="padding:10px 12px;background:#fff5f5;border-left:3px solid #c62828;border-radius:3px;font-size:12px;margin-bottom:10px">' +
			"<b>" + __("Another plan is counting on this material:") + "</b><br>" +
			s.claimed.map(c => `${c.plan} — ${__("row")} ${c.idx} (${c.item_code}, ${money(c.qty)} Kg)`).join("<br>") +
			"<br>" + __("Unallocate it there before writing it off.") +
			"</div>";
	}

	if (s.over_threshold) {
		html +=
			'<div style="padding:10px 12px;background:#fff5f5;border-left:3px solid #c62828;border-radius:3px;font-size:12px;margin-bottom:10px">' +
			"<b>" + __("This is above {0}% of what was transferred.", [s.threshold_pct]) + "</b><br>" +
			__("A loss this size is not cutting loss — the supplier did not use the material effectively. That is a purchase return to recover payment, not a write-off. You can still proceed, but say so in the reason.") +
			"</div>";
	}

	const d = new frappe.ui.Dialog({
		title: __("Process Loss — Not Returned"),
		size: "large",
		fields: [
			{ fieldtype: "HTML", fieldname: "summary", options: html },
			{
				fieldtype: "Check",
				fieldname: "absorb_unreturned",
				label: __("The excess still awaiting return is not coming — write it off too"),
				depends_on: "eval:" + (s.pending_return_kg > 0.001),
				default: 0,
			},
			{
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Reason"),
				reqd: 1,
				description: __("What the supplier said happened to it — cutting loss, burning loss, short return."),
			},
		],
		primary_action_label: __("Write Off {0} Kg", [money(s.remaining)]),
		primary_action(values) {
			frappe.call({
				method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.create_mip_process_loss_entry",
				args: {
					mip_name: frm.doc.name,
					reason: values.reason,
					absorb_unreturned: values.absorb_unreturned ? 1 : 0,
				},
				freeze: true,
				freeze_message: __("Writing off process loss…"),
				callback(r) {
					if (!r.message) return;
					d.hide();
					frappe.msgprint({
						title: __("Process Loss Recorded"),
						message: __("{0} Kg written off. Stock Entry {1} created — submit it to take the material out of the supplier's warehouse.", [
							money(r.message.process_loss_kg), r.message.stock_entry,
						]),
						indicator: "orange",
					});
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function _add_open_sco_button(frm) {
	// Counterpart of the Job Work Order's "Open MIP" button: the two documents are
	// worked on together, so each one opens the other in a click.
	if (frm.is_new() || !frm.doc.subcontracting_order) return;
	frm.add_custom_button(__("Open Job Work Order"), function() {
		frappe.set_route("Form", "Subcontracting Order", frm.doc.subcontracting_order);
	});
}

// "Download" — one toolbar group, two documents. The batch-wise plan answers
// "what goes out, batch by batch, and for which drawings"; the consolidated one
// answers "how much of each item+batch in total", which is the sheet the store
// actually picks against. They are two views of the same transfer, so they live
// under one button rather than competing for space in the toolbar.
function _add_download_button(frm) {
	if (frm.is_new()) return;
	frm.add_custom_button(__("Batch wise PDF"), function() {
		_show_mip_plan_popup(frm, "batch");
	}, __("Download"));
	frm.add_custom_button(__("Consolidate item wise PDF"), function() {
		_show_mip_plan_popup(frm, "consolidate");
	}, __("Download"));
}

// Both plans render from server-built HTML and both download from a server-built
// PDF of that same HTML, so what is on screen is exactly what lands in the file.
// One function drives both because the only differences are which endpoint to
// call and what to put in the title.
const _MIP_PLAN_VARIANTS = {
	batch: {
		html_method: "get_mip_batch_plan_html",
		pdf_method: "download_mip_batch_plan_pdf",
		building: "Building batch plan…",
		title: "Batch Plan — {0}",
	},
	consolidate: {
		html_method: "get_mip_consolidate_plan_html",
		pdf_method: "download_mip_consolidate_plan_pdf",
		building: "Building consolidated plan…",
		title: "Consolidated Item Plan — {0}",
	},
};

function _show_mip_plan_popup(frm, variant) {
	const v = _MIP_PLAN_VARIANTS[variant];
	const base = "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.";
	frappe.call({
		method: base + v.html_method,
		args: { mip_name: frm.doc.name },
		freeze: true,
		freeze_message: __(v.building),
		callback: function(r) {
			if (!r.message) return;

			var dlg = new frappe.ui.Dialog({
				title: __(v.title, [frm.doc.name]),
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "content" }],
			});
			dlg.fields_dict.content.$wrapper.html(r.message);

			// "Download" in the dialog's top corner (next to the close icon) rather
			// than the usual bottom primary-action button, per how this was asked for.
			var $download = $(
				'<button class="btn btn-primary btn-sm" style="margin-right:8px">' + __("Download") + "</button>"
			);
			$download.on("click", function() {
				window.open(
					"/api/method/" + base + v.pdf_method + "?mip_name=" + encodeURIComponent(frm.doc.name),
					"_blank"
				);
			});
			dlg.header.find(".modal-actions").prepend($download);

			dlg.show();
		},
	});
}

// ── Button tones ─────────────────────────────────────────────────────────────
// See public/js/mfx_buttons.js for what each tone means. Called last in refresh
// so every button that is going to exist already does -- the two added from
// inside a frappe.call callback (Make Final Stock Entry, Process Loss) paint
// themselves at their own call site instead, because they arrive after this runs.
function _mip_paint_buttons(frm) {
	if (!window.mfx_paint_group) return;
	// "Select Materials to Transfer" lives INSIDE the Transfer group, so the thing
	// on screen is the group's own toggle -- frm.custom_buttons holds the hidden
	// dropdown item, and painting that colours nothing anyone can see.
	window.mfx_paint_group(frm, "Transfer", "primary");
	window.mfx_paint_button(frm, "Return Excess Entry", "primary");
	// Navigation and reports stay grey on purpose: Open Job Work Order, Download.
	window.mfx_paint_grid(frm, "raw_materials", { alt: ["Update Batch"] });
	window.mfx_paint_grid(frm, "consolidate_items", { alt: ["Update Batch"] });
}

// ── Transfer / CNC buttons ───────────────────────────────────────────────────

function _add_transfer_buttons(frm) {
	if (frm.is_new() || !frm.doc.source_warehouse) return;
	if (!frm.doc.subcontracting_order && !frm.doc.work_order) return;

	frm.add_custom_button(__("Select Materials to Transfer"), function() {
		_check_transfer_readiness(frm, function() {
			frappe.call({
				method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.get_mip_pending_items",
				args: { mip_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Loading pending materials…"),
				callback(r) { _show_mip_transfer_popup(frm, r.message || [], "primary"); },
			});
		});
	}, __("Transfer"));

	// Reference view of what this plan will hand over, per item + batch, before
	// any Stock Entry exists — the same Kg/Sec Nos figures the transfer popup
	// will show, with fractional totals called out.
	frm.add_custom_button(__("Validate Stock"), function() {
		frappe.call({
			method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.get_mip_pending_items",
			args: { mip_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Checking planned stock…"),
			callback(r) { _show_mip_stock_validation(r.message || []); },
		});
	}, __("Transfer"));

	if (frm.doc.cnc_warehouse) {
		// One call answers both buttons. "To CNC Warehouse" is shown only while CNC
		// rows are still waiting to move there -- it used to appear whenever a CNC
		// warehouse was merely set, so it lingered after everything had gone and could
		// only open an empty popup.
		frappe.call({
			method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.get_mip_cnc_button_state",
			args: { mip_name: frm.doc.name },
			callback(r) {
				var state = r.message || {};

				if (state.show_to_cnc) {
					frm.add_custom_button(__("To CNC Warehouse"), function() {
						_check_transfer_readiness(frm, function() {
							frappe.call({
								method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.get_mip_pending_items",
								args: { mip_name: frm.doc.name },
								freeze: true,
								freeze_message: __("Loading pending materials…"),
								callback(r) { _show_mip_transfer_popup(frm, r.message || [], "cnc"); },
							});
						});
					}, __("Transfer"));
				}

				if (state.show_cnc_forward) {
					// Second leg, and a separate Stock Entry by design: only material
					// that has physically arrived at CNC can be forwarded, and it can
					// be released in stages as machining finishes, so this opens the
					// same selection popup rather than moving everything at once.
					frm.add_custom_button(__("CNC to Supplier/WIP"), function() {
						frappe.call({
							method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.get_mip_cnc_pending_items",
							args: { mip_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Loading CNC material…"),
							callback(r) {
								let rows = r.message || [];
								if (!rows.length) {
									frappe.msgprint({
										title: __("Nothing at CNC"),
										message: __("No machined material is waiting at {0} to forward. Transfer material to CNC first, and make sure that Stock Entry is submitted.", [frappe.utils.escape_html(frm.doc.cnc_warehouse || "CNC")]),
										indicator: "orange",
									});
									return;
								}
								_show_mip_transfer_popup(frm, rows, "cnc_forward");
							},
						});
					}, __("Transfer"));
				}
			},
		});
	}
}

// Item Code filter only. DUNO/Mark No, Drawing, Sales Order and Customer Drawing No
// are deliberately NOT shown/filterable here: a row in this table is one reserved
// BATCH, and a single consolidated batch (bought once, allocated across many
// drawings' requirements -- see Consolidate Item / allocate_pr_stock_to_mp) can
// legitimately serve several DUNO/drawings at once, so no single value could be
// shown here without being misleading. A batch with no drawing tag at all (e.g. a
// purchase never traced back to one specific drawing) is still a perfectly valid
// row and is never excluded from this list on that basis.
// Read-only summary of the pending transfer rows: Kg and Sec Nos per item+batch.
// A fractional Sec Nos means one batch is shared across several drawings, so the
// whole-piece decision is still open — it is taken row by row in the transfer
// popup, not here.
function _show_mip_stock_validation(rows) {
	if (!rows.length) {
		frappe.msgprint({
			title: __("Validate Stock"),
			message: __("Nothing is pending transfer on this plan."),
			indicator: "orange",
		});
		return;
	}

	// Full width, no horizontal scrollbar: only the text columns wrap, numeric
	// columns stay nowrap + right-aligned so everything fits the wide dialog.
	let num = "text-align:right;white-space:nowrap;";
	let html = '<table class="table table-bordered table-condensed" style="font-size:12px;width:100%;table-layout:auto;margin-bottom:0;">';
	html += "<thead><tr>" + [
		[__("Item"), ""], [__("Batch"), ""], [__("DUNO/Mark No"), ""],
		[__("Planned Kg"), num], [__("Planned NOS"), num],
	].map(([h, st]) => '<th style="' + st + '">' + h + "</th>").join("") + "</tr></thead><tbody>";

	let fractional = 0;
	rows.forEach(function (d) {
		let sec = flt(d.custom_sec_qty, 3);
		let is_frac = Math.abs(sec - Math.round(sec)) > 0.001;
		if (is_frac) fractional++;
		html += "<tr>" +
			'<td style="white-space:nowrap;">' + frappe.utils.escape_html(d.item_code) + "</td>" +
			'<td style="word-break:break-all;">' + frappe.utils.escape_html(d.batch_no || "—") + "</td>" +
			'<td style="white-space:nowrap;">' + frappe.utils.escape_html(d.duno_mark_no || "—") + "</td>" +
			'<td style="' + num + '">' + flt(d.qty, 3) + "</td>" +
			'<td style="' + num + '">' + (is_frac
				? '<span style="color:#b45309;font-weight:600;">' + sec + "</span> " +
				  "<span class='text-muted'>(" + __("or {0} whole", [Math.ceil(sec - 0.001)]) + ")</span>"
				: sec) +
			"</td></tr>";
	});
	html += "</tbody></table>";

	if (fractional) {
		html += '<p class="text-muted" style="margin-top:10px;">' +
			__("{0} row(s) have a fractional NOS — one batch shared across several drawings. You can raise it to a whole number in the transfer popup; the extra weight is then recorded as excess to return.", [fractional]) +
			"</p>";
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
}

// Weight of an off-cut from what was measured -- client-side twin of
// utils/dimension_formula.calculate_qty, same as the Cut Sheet preview uses.
function _excess_weight(d, L, W, S) {
	var g = d.custom_parent_item_group;
	var t = flt(d.custom_thickness), uw = flt(d.custom_unit_weight);
	if (g === "Structurals") {
		if (L && uw && S) return (L / 1000) * uw * S;
	} else if (g === "Plates") {
		if (L && W && t && uw && S) return (L / 1000) * (W / 1000) * t * uw * S;
	}
	return null;
}

// ── Transfer popup theme ──────────────────────────────────────────────────────
//
// Light, like the rest of the desk: the popup is read for a long time while
// figures are checked row by row, and a dark panel was tiring for that. Only the
// tabs carry colour, in the client's green, so the two panes stay told apart at a
// glance without the whole dialog going dark.
//
// Scoped to .mip-transfer-theme so no other dialog in the desk is touched.
var MIP_THEME_CSS = `
/* Frappe's toast container uses z-index 1050, the same layer as a modal.
   Raise it only while this transfer popup is open so its warnings stay legible. */
body.mip-transfer-alerts-front #alert-container { z-index: 1060; }
.mip-transfer-theme .mip-tab {
	display:inline-block; padding:9px 22px; margin-right:14px; cursor:pointer;
	font-size:12px; font-weight:600; border-radius:8px 8px 0 0; position:relative; top:1px;
	background:#65a30d; color:#f7fee7; border:1px solid #65a30d; border-bottom:none;
	text-decoration:none;
}
.mip-transfer-theme .mip-tab:hover { background:#4d7c0f; color:#ffffff; text-decoration:none; }
.mip-transfer-theme .mip-tab.active {
	background:#ecfccb; color:#365314; border-color:#d9f99d; border-bottom:1px solid #ecfccb;
}
.mip-transfer-theme .mip-pane {
	background:#ecfccb; border:1px solid #d9f99d; border-radius:0 10px 10px 10px; padding:14px;
}
.mip-transfer-theme .mip-pane table tbody td { background:#ffffff; }
.mip-transfer-theme .mip-pane table thead th { background:#f4f5f7; }
/* A row with nothing left over. The dimension boxes are disabled, but a greyed
   box and a hover tooltip are not an answer to "why can't I type here" -- the
   row has to say so without being asked. */
.mip-transfer-theme tr.mfx-no-excess td { background:#fafafa; }
.mip-transfer-theme .mip-xs-none {
	display:block; font-size:10px; font-weight:600; line-height:1.3;
	color:#c62828; white-space:nowrap; margin-top:2px;
}
`;

function _mip_inject_theme() {
	if (document.getElementById("mip-transfer-theme-css")) return;
	$("<style id='mip-transfer-theme-css'>").text(MIP_THEME_CSS).appendTo(document.head);
}

// The Final Stock Entry popup, themed the same way the transfer one is but in blue --
// a different colour for a different step, so the two are never mistaken for each other
// at a glance. Same lightness ladder as MIP_THEME_CSS, sky in place of lime.
var MFX_FG_THEME_CSS = `
.mfx-fg-theme .mfx-fg-pane {
	background:#e0f2fe; border:1px solid #bae6fd; border-radius:10px; padding:14px;
}
.mfx-fg-theme .mfx-fg-head {
	display:inline-block; padding:7px 18px; margin-bottom:10px;
	font-size:12px; font-weight:600; border-radius:8px;
	background:#0284c7; color:#f0f9ff; border:1px solid #0284c7;
}
.mfx-fg-theme .mfx-fg-pane table { margin-bottom:10px; }
.mfx-fg-theme .mfx-fg-pane table tbody td { background:#ffffff; }
.mfx-fg-theme .mfx-fg-pane table thead th {
	background:#f0f9ff; color:#075985; border-bottom:2px solid #bae6fd;
}
.mfx-fg-theme .mfx-fg-pane table tfoot td { background:#bae6fd; color:#075985; }
.mfx-fg-theme .mfx-fg-note { color:#075985; font-size:11px; margin-bottom:4px; }
.mfx-fg-theme .mfx-fg-note-dim { color:#0369a1; font-size:11px; opacity:.85; }
.mfx-fg-theme input.fse-per-nos {
	border:1px solid #7dd3fc; background:#f0f9ff; border-radius:4px;
}
.mfx-fg-theme input.fse-per-nos:focus {
	border-color:#0284c7; background:#ffffff; box-shadow:0 0 0 2px rgba(2,132,199,.15);
}
`;

function _mfx_inject_fg_theme() {
	if (document.getElementById("mfx-fg-theme-css")) return;
	$("<style id='mfx-fg-theme-css'>").text(MFX_FG_THEME_CSS).appendTo(document.head);
}

function _show_mip_transfer_entry_created(frm, stock_entry_name) {
	const dialog = new frappe.ui.Dialog({
		title: __("Stock Entry Created"),
		fields: [{ fieldtype: "HTML", fieldname: "message" }],
		primary_action_label: __("Submit Stock Entry"),
		primary_action() {
			frappe.call({
				method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.submit_mip_transfer_entry",
				args: { mip_name: frm.doc.name, stock_entry_name: stock_entry_name },
				freeze: true,
				freeze_message: __("Submitting Stock Entry…"),
				callback(r) {
					if (!r.message || !r.message.name) return;
					dialog.hide();
					frappe.msgprint({
						title: __("Stock Entry Submitted"),
						message: __("Stock Entry {0} submitted successfully.",
							[frappe.utils.escape_html(r.message.name)]),
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
		secondary_action_label: __("Open Stock Entry"),
		secondary_action() {
			dialog.hide();
			frappe.set_route("Form", "Stock Entry", stock_entry_name);
		},
	});
	dialog.fields_dict.message.$wrapper.html(
		$("<p>").text(__("Stock Entry {0} created. Submit it to transfer the stock.",
			[stock_entry_name]))
	);
	dialog.show();
}

function _show_mip_transfer_popup(frm, pending_items, transfer_type) {
	var is_cnc_fwd = transfer_type === "cnc_forward";
	var items = is_cnc_fwd
		? pending_items
		: pending_items.filter(function(d) { return transfer_type === "cnc" ? d.cnc_process : !d.cnc_process; });
	if (!items.length) {
		frappe.msgprint({
			title: __("No Pending Items"),
			message: is_cnc_fwd ? __("Nothing is waiting at CNC to forward.")
				: transfer_type === "cnc" ? __("No pending CNC items to transfer.") : __("No pending items to transfer."),
			indicator: "orange",
		});
		return;
	}

	var item_code_options = Array.from(new Set(items.map((d) => d.item_code).filter(Boolean))).sort();

	// Searchable dropdown list — text input that opens a filtered option list on focus/type.
	// Returns { $el, getValue(), reset() }. Triggers a custom "mip:filter" event on $el
	// whenever the selected value changes (so callers bind a single event).
	function _make_search_list(options, placeholder) {
		var current_val = "";
		var uid = "mip_sl_" + Math.random().toString(36).slice(2);
		var $wrap = $('<div>').css({ position: "relative", marginBottom: "8px" });
		var $input = $('<input type="text" class="form-control form-control-sm" autocomplete="off">')
			.attr("placeholder", placeholder);
		var $drop = $('<div>').css({
			position: "absolute", top: "100%", left: 0, right: 0, zIndex: 9999,
			background: "#fff", border: "1px solid #d1d8dd", borderRadius: "4px",
			maxHeight: "200px", overflowY: "auto", display: "none",
			boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
		});
		$wrap.append($input, $drop);

		function _render(q) {
			var filtered = q ? options.filter(function(o) { return o.toLowerCase().includes(q.toLowerCase()); }) : options;
			$drop.empty();
			var $all = $('<div>').css({ padding: "6px 10px", cursor: "pointer", fontSize: "12px",
				color: "#6c757d", borderBottom: "1px solid #f0f0f0" }).text(__("All"));
			$all.on("mouseenter", function() { $(this).css("background", "#f0f4f7"); })
				.on("mouseleave", function() { $(this).css("background", ""); })
				.on("mousedown", function(e) {
					e.preventDefault();
					current_val = ""; $input.val(""); $drop.hide(); $wrap.trigger("mip:filter");
				});
			$drop.append($all);
			filtered.forEach(function(opt) {
				var $opt = $('<div>').css({ padding: "6px 10px", cursor: "pointer", fontSize: "12px" }).text(opt);
				$opt.on("mouseenter", function() { $(this).css("background", "#f0f4f7"); })
					.on("mouseleave", function() { $(this).css("background", ""); })
					.on("mousedown", function(e) {
						e.preventDefault();
						current_val = opt; $input.val(opt); $drop.hide(); $wrap.trigger("mip:filter");
					});
				$drop.append($opt);
			});
			if (filtered.length || !q) $drop.show(); else $drop.hide();
		}

		$input.on("focus", function() { _render($input.val()); });
		$input.on("blur",  function() { $drop.hide(); });
		$input.on("input", function() { current_val = ""; _render($input.val()); $wrap.trigger("mip:filter"); });

		return {
			$el: $wrap,
			getValue() { return current_val || $input.val() || ""; },
			reset() { current_val = ""; $input.val(""); $drop.hide(); },
		};
	}

	var item_search = _make_search_list(item_code_options, __("Search item code…"));

	var $filter_row = $("<div>").append(
		$("<div class='row'>").append(
			$("<div class='col-sm-4'>").append(item_search.$el)
		)
	);
	var $actions = $("<div style='margin-bottom:8px'>"
		+ "<button class='btn btn-xs btn-default mip-sel-all'>" + __("Select All") + "</button> "
		+ "<button class='btn btn-xs btn-default mip-desel-all'>" + __("Deselect All") + "</button>"
		+ "</div>");
	var $table = $("<table class='table table-bordered table-condensed' style='margin-bottom:0;font-size:12px'>"
		+ "<thead><tr>"
		+ "<th style='width:32px'></th>"
		+ "<th>" + __("Item") + "</th>"
		+ "<th>" + __("Batch") + "</th>"
		+ "<th class='text-right' style='white-space:nowrap'>" + __("Planned") + "</th>"
		+ "<th class='text-right' style='white-space:nowrap'>" + __("Transferred") + "</th>"
		+ "<th class='text-right' style='white-space:nowrap'>" + __("In Stock") + "</th>"
		+ "<th class='text-right' style='white-space:nowrap'>" + __("Available NOS") + "</th>"
		+ "<th class='text-right' style='white-space:nowrap'>" + __("NOS")
			+ "<div class='text-muted' style='font-weight:normal;font-size:10px'>" + __("edit to transfer part") + "</div></th>"
		+ "<th class='text-right' style='white-space:nowrap'>" + __("Transfer Qty (Kg)")
			+ "<div class='text-muted' style='font-weight:normal;font-size:10px'>" + __("from NOS") + "</div></th>"
		+ "</tr></thead><tbody></tbody></table>");

	var $tbody = $table.find("tbody");

	// Anything parked by a previous "Save and Close" comes back onto the rows it was
	// entered against. Fetched after the table is built, so it can simply replay the
	// same handlers a user would have triggered by typing.
	//
	// Scoped to THIS popup: all three park against the same consolidate rows, and this
	// one and the CNC-to-supplier popup key their rows identically (cnc_process is 0 in
	// both). A draft of "1 whole plate" saved against the stock in stores came back on
	// the CNC popup, which is looking at the far smaller amount that has reached the
	// CNC warehouse, and it opened refusing to transfer for want of stock.
	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.get_transfer_draft",
		args: { mip_name: frm.doc.name, transfer_type: is_cnc_fwd ? "cnc_forward" : transfer_type },
		callback: function(r) {
			var draft = r.message || {};
			if (!Object.keys(draft).length) return;
			var restored = 0;
			$tbody.find("tr").each(function() {
				var $tr = $(this);
				var d = items[parseInt($tr.data("idx"), 10)];
				if (!d) return;
				var saved = draft[d.item_code + "|" + (d.batch_no || "") + "|" + (d.cnc_process ? 1 : 0)];
				if (!saved) return;
				restored++;
				if (flt(saved.draft_sec_qty)) {
					// Fire the normal change handler rather than writing the figure
					// directly: it is what recalculates Kg and the surplus. Duplicating
					// that here would be a second copy to keep in step.
					$tr.find(".mip-sec-qty").val(flt(saved.draft_sec_qty, 3)).trigger("change");
				}
				// The off-cut was parked per item, against every batch row of it --
				// first one found answers for the item.
			if (!is_cnc_fwd && (flt(saved.draft_excess_length) || flt(saved.draft_excess_width) ||
				flt(saved.draft_excess_sec_qty))) {
					dlg._excess_plan = dlg._excess_plan || {};
					if (!dlg._excess_plan[d.item_code]) {
						dlg._excess_plan[d.item_code] = {
							length: flt(saved.draft_excess_length),
							width: flt(saved.draft_excess_width),
							sec_qty: flt(saved.draft_excess_sec_qty),
							return_warehouse: saved.draft_return_warehouse || "",
						};
					}
				}
			});
			if (restored) {
				frappe.show_alert({
					message: __("Restored a saved draft for {0} row(s).", [restored]),
					indicator: "blue",
				}, 6);
			}
		},
	});
	// Sec Nos is THE control, and Kg is derived from it -- steel moves in pieces and
	// the weight is a consequence of the piece count, so lowering Sec Nos is how a
	// partial transfer is made. Kg is therefore read-only: editing it directly would
	// ship a Stock Entry whose Sec Qty and weight disagree, and Supplier Operation
	// Entry consumption and the excess-return figures are both derived from Sec Qty.
	//
	// The exception is a row with no usable Kg-per-piece (dimensions missing, so Sec
	// Nos is 0 and editing it changes nothing). There Kg is the only way to transfer
	// part of a row, so it stays editable.
	items.forEach(function(d, idx) {
		d._planned_sec_qty = flt(d.custom_sec_qty);
		d._planned_qty = flt(d.qty);
		var is_frac = Math.abs(d._planned_sec_qty - Math.round(d._planned_sec_qty)) > 0.001;
		var done = flt(d.transferred_qty);
		// What this plan may take: physical stock less other plans' reservations (and a
		// Cut Sheet's W1 cap). "In Stock" below still shows the physical figure.
		var avail = flt(d.available_for_plan !== undefined ? d.available_for_plan : d.available_qty);
		var short = avail + 0.001 < flt(d.qty);
		// Sec Nos can only drive the weight when both are non-zero.
		var sec_drives_qty = d._planned_sec_qty > 0 && d._planned_qty > 0;

		$tbody.append(
			"<tr data-idx='" + idx + "' data-item='" + frappe.utils.escape_html(d.item_code || "") + "'>" +
			"<td class='text-center'><input type='checkbox' class='mip-item-chk'" + (short ? "" : " checked") + "></td>" +
			"<td>" + frappe.utils.escape_html(d.item_code) +
				(d.duno_mark_no ? "<div class='text-muted' style='font-size:11px'>" +
					frappe.utils.escape_html(d.duno_mark_no) + "</div>" : "") + "</td>" +
			"<td style='word-break:break-all'>" + frappe.utils.escape_html(d.batch_no || "—") + "</td>" +
			"<td class='text-right' style='white-space:nowrap'>" + format_number(flt(d.planned_qty), null, 3) + "</td>" +
			"<td class='text-right' style='white-space:nowrap'>" +
				(done > 0 ? "<span style='color:#15803d'>" + format_number(done, null, 3) + "</span>" : "—") + "</td>" +
			"<td class='text-right' style='white-space:nowrap'>" +
				(short ? "<span style='color:#b91c1c;font-weight:600'>" + format_number(flt(d.available_qty), null, 3) + "</span>"
				       : format_number(flt(d.available_qty), null, 3)) +
				(flt(d.reserved_for_others_kg) > 0.001
					? "<div class='text-muted' style='font-size:11px;white-space:nowrap'>" +
					  __("{0} reserved for other drawings or plans", [format_number(flt(d.reserved_for_others_kg), null, 3)]) +
					  "</div>"
					: "") + "</td>" +
			// The In Stock Kg in pieces, at this line's own piece weight (server:
			// _available_nos). A dash where there is no piece weight to divide by.
			"<td class='text-right' style='white-space:nowrap'>" +
				(d.available_nos === null || d.available_nos === undefined ? "—"
					: format_number(flt(d.available_nos), null, 3)) + "</td>" +
			"<td class='text-right'>" +
				(sec_drives_qty
					? "<input type='number' step='0.001' min='0' class='form-control input-xs text-right mip-sec-qty' " +
					  "style='width:100px;display:inline-block" + (is_frac ? ";border-color:#f59e0b" : "") + "' " +
					  "value='" + flt(d._planned_sec_qty, 3) + "'>" +
					  // Always name the planned figure -- once the box has been typed
					  // into there is otherwise nothing left on screen saying what the
					  // plan actually called for.
					  "<div class='text-muted' style='font-size:11px'>" +
						flt(d._planned_sec_qty, 3) + " " + __("(Plan)") +
						(is_frac ? " · " + __("or {0} whole", [Math.ceil(d._planned_sec_qty - 0.001)]) : "") +
					  "</div>"
					: "<span class='text-muted'>—</span>") +
			"</td>" +
			"<td class='text-right'>" +
				(sec_drives_qty
					? "<span class='mip-qty-text'>" + format_number(flt(d.qty), null, 3) + "</span>" +
					  "<input type='hidden' class='mip-qty' value='" + flt(d.qty, 3) + "'>"
					: "<input type='number' step='0.001' min='0' class='form-control input-xs text-right mip-qty' " +
					  "style='width:120px;display:inline-block' value='" + flt(d.qty, 3) + "'>") +
				"<div class='text-muted mip-qty-note' style='font-size:11px'>" +
					__("pending {0}", [format_number(flt(d.qty), null, 3)]) + "</div>" +
			"</td>" +
			"</tr>"
		);
	});

	// Only reachable on rows where Sec Nos cannot drive the weight (see above), so
	// this is the sole way to transfer part of such a row. Obvious limits only --
	// the authoritative check runs server-side at transfer.
	$tbody.on("change", "input.mip-qty", function() {
		var $input = $(this);
		var $row = $input.closest("tr");
		var d = items[parseInt($row.data("idx"), 10)];
		var v = flt($input.val());
		var max = Math.min(flt(d.qty), flt(d.available_for_plan !== undefined ? d.available_for_plan : d.available_qty));

		if (v <= 0) {
			frappe.show_alert({ message: __("Transfer qty must be greater than zero."), indicator: "red" }, 5);
			$input.val(flt(d.qty, 3));
			return;
		}
		if (v > max + 0.001) {
			frappe.show_alert({
				message: __("Only {0} can be transferred now (pending {1}, in stock {2}, reserved for other drawings or plans {3}).",
					[format_number(max, null, 3), format_number(flt(d.qty), null, 3), format_number(flt(d.available_qty), null, 3),
					 format_number(flt(d.reserved_for_others_kg), null, 3)]),
				indicator: "red",
			}, 7);
			$input.val(flt(max, 3));
			v = max;
		}
		d._transfer_qty = v;
		$row.find(".mip-qty-note").text(
			v + 0.001 < flt(d.qty)
				? __("partial · {0} will stay pending", [format_number(flt(d.qty) - v, null, 3)])
				: __("pending {0}", [format_number(flt(d.qty), null, 3)])
		);
	});

	// Re-derive Kg + excess from an edited Sec Nos, refusing anything the batch
	// cannot physically cover.
	$tbody.on("change", ".mip-sec-qty", function() {
		var $input = $(this);
		var $row = $input.closest("tr");
		var d = items[parseInt($row.data("idx"), 10)];
		var new_sec = flt($input.val());

		if (new_sec <= 0) {
			frappe.show_alert({ message: __("NOS must be greater than zero."), indicator: "red" }, 5);
			$input.val(flt(d.custom_sec_qty, 3));
			return;
		}
		frappe.call({
			method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.update_transfer_sec_qty",
			args: {
				mip_name: frm.doc.name,
				item_code: d.item_code,
				batch_no: d.batch_no || "",
				planned_sec_qty: d._planned_sec_qty,
				planned_qty: d._planned_qty,
				new_sec_qty: new_sec,
				cnc_process: d.cnc_process ? 1 : 0,
				// The CNC-to-supplier leg reads what is at CNC, not the source warehouse.
				transfer_type: is_cnc_fwd ? "cnc_forward" : transfer_type,
			},
			callback: function(r) {
				if (!r.message) return;
				var m = r.message;
				if (m.blocked) {
					frappe.msgprint({ title: __("Not Enough Stock"), message: m.message, indicator: "red" });
					$input.val(flt(d.custom_sec_qty, 3));
					return;
				}
				if (m.warning) {
					// Allowed, but it takes stock other rows were planned against.
					frappe.msgprint({ title: __("Stock Also Planned Elsewhere"), message: m.warning, indicator: "orange" });
				}
				d.custom_sec_qty = m.custom_sec_qty;
				d.qty = m.qty;
				d.round_up_excess_kg = m.round_up_excess_kg;
				d.round_up_excess_pieces = m.round_up_excess_pieces;
				// Sec Nos drives the weight, so push the recalculated Kg into both the
				// hidden field that gets submitted and the figure on screen.
				d._transfer_qty = flt(m.qty);
				$row.find(".mip-qty").val(flt(m.qty, 3));
				$row.find(".mip-qty-text").text(format_number(flt(m.qty), null, 3));
				$row.find(".mip-qty-note").text(
					flt(m.qty) + 0.001 < flt(d._planned_qty)
						? __("partial · {0} will stay pending", [format_number(flt(d._planned_qty) - flt(m.qty), null, 3)])
						: __("pending {0}", [format_number(flt(m.qty), null, 3)])
				);
				if (m.round_up_excess_kg > 0) {
					frappe.show_alert({
						message: __("{0} Kg extra will be issued and recorded as excess to return.", [flt(m.round_up_excess_kg, 3)]),
						indicator: "orange",
					}, 6);
				}
				// The numbers on screen are no longer the ones this popup opened
				// with, so the button says what actually happens next: stock is
				// re-checked server-side before any Stock Entry is created.
				_mark_sec_nos_edited();
			},
		});
	});

	function _apply_filters() {
		var item_q = item_search.getValue().toLowerCase();
		$tbody.find("tr").each(function() {
			var $row = $(this);
			$row.toggle(!item_q || String($row.data("item") || "").toLowerCase().includes(item_q));
		});
	}
	item_search.$el.on("mip:filter", _apply_filters);
	$actions.find(".mip-sel-all").on("click", function() { $tbody.find("tr:visible .mip-item-chk").prop("checked", true); });
	$actions.find(".mip-desel-all").on("click", function() { $tbody.find("tr:visible .mip-item-chk").prop("checked", false); });

	// Header strip: where this transfer stands overall, and anything that would
	// quietly reduce what actually moves -- stock not yet received, or reserved
	// material sitting on a Material Planning that nobody has reserved yet.
	var tot_planned = items.reduce(function(a, d) { return a + flt(d.planned_qty); }, 0);
	var tot_done    = items.reduce(function(a, d) { return a + flt(d.transferred_qty); }, 0);
	var tot_pending = items.reduce(function(a, d) { return a + flt(d.qty); }, 0);
	var short_rows  = items.filter(function(d) {
		return flt(d.available_for_plan !== undefined ? d.available_for_plan : d.available_qty) + 0.001 < flt(d.qty);
	});

	var summary = "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 12px;margin-bottom:10px;font-size:12px'>"
		+ "<b>" + __("Planned") + ":</b> " + format_number(tot_planned, null, 3) + " Kg"
		+ " &nbsp;·&nbsp; <b>" + __("Already transferred") + ":</b> <span style='color:#15803d'>"
		+ format_number(tot_done, null, 3) + " Kg</span>"
		+ " &nbsp;·&nbsp; <b>" + __("Pending now") + ":</b> " + format_number(tot_pending, null, 3) + " Kg"
		+ " &nbsp;·&nbsp; " + __("to") + " <b>" + frappe.utils.escape_html(
			transfer_type === "cnc" ? (frm.doc.cnc_warehouse || "-") : (frm.doc.supplier_warehouse || "-")) + "</b>"
		+ (is_cnc_fwd ? " &nbsp;·&nbsp; " + __("from") + " <b>" + frappe.utils.escape_html(frm.doc.cnc_warehouse || "-") + "</b>" : "")
		+ "</div>";

	if (short_rows.length) {
		var short_warehouse = is_cnc_fwd ? frm.doc.cnc_warehouse : frm.doc.source_warehouse;
		summary += "<div style='background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:10px 12px;margin-bottom:10px;font-size:12px;color:#7f1d1d'>"
			+ "⚠ <b>" + __("{0} item(s) do not have enough stock in {1} yet", [short_rows.length, frappe.utils.escape_html(short_warehouse || "-")]) + "</b><br>"
			+ (is_cnc_fwd
				? __("Their <b>In Stock</b> figure is below what is waiting to move from CNC. Submit the incoming CNC Stock Entry or transfer a smaller quantity.")
				: __("Their <b>In Stock</b> figure is below what is pending — usually the Purchase Receipt has not been made yet. These rows are left unticked; transfer the rest now and come back for them."))
			+ "</div>";
	}

	// CNC Process rows are filtered out of this popup by design -- they leave on their
	// own leg, to the CNC warehouse, and only reach the supplier after that. Saying
	// nothing left exactly the silent gap the at_supplier notice below exists to close.
	// On MIP-2026-00004 five rows totalling 472.615 Kg simply were not in this list;
	// the four that were got transferred, and the job ran to completion believing
	// everything had gone. The button that sends them sits in the same Transfer menu
	// this popup was opened from, so name it rather than leaving it to be found.
	var held_cnc = transfer_type === "primary"
		? pending_items.filter(function(d) { return d.cnc_process; })
		: [];
	if (held_cnc.length) {
		var held_kg = held_cnc.reduce(function(a, d) { return a + flt(d.qty); }, 0);
		summary += "<div style='background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:10px 12px;margin-bottom:10px;font-size:12px;color:#92400e'>"
			+ "⚙ <b>" + __("{0} CNC Process item(s) ({1} Kg) are not listed here",
				[held_cnc.length, format_number(held_kg, null, 3)]) + "</b><br>"
			+ __("They must go to <b>{0}</b> first, on their own transfer, and only reach {1} after that. Transferring this list does NOT send them — use <b>Transfer &rarr; To CNC Warehouse</b> for those rows.",
				[frappe.utils.escape_html(frm.doc.cnc_warehouse || __("the CNC warehouse")),
				 frappe.utils.escape_html(frm.doc.supplier_warehouse || __("the supplier"))])
			+ "</div>";
	}

	// Material already sitting at the supplier: an off-cut this plan claimed through
	// Excess Material Mapping while it was still at their end. There is nothing to
	// move -- it is already where the transfer would have sent it -- so the row is
	// absent from the list below by design, and this says so rather than leaving a
	// silent gap between what was planned and what is on offer.
	// Only on the legs that leave the source warehouse. The CNC-to-supplier leg does
	// not run the readiness check at all, so its stash would be whatever the last
	// transfer dialog left behind — and material already at the supplier says nothing
	// about what is waiting at CNC anyway.
	var at_supplier = is_cnc_fwd ? [] : (frm.__mip_at_supplier || []);
	if (at_supplier.length) {
		var at_rows = at_supplier.map(function(s) {
			return "<li>" + frappe.utils.escape_html(s.item_code)
				+ (s.duno_mark_no ? " · " + frappe.utils.escape_html(s.duno_mark_no) : "")
				+ " — " + format_number(flt(s.qty), null, 3) + " " + frappe.utils.escape_html(s.uom || "Kg")
				+ (s.source_mip ? " (" + __("from") + " " + frappe.utils.escape_html(s.source_mip) + ")" : "")
				+ "</li>";
		}).join("");
		summary += "<div style='background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:10px 12px;margin-bottom:10px;font-size:12px;color:#1e3a8a'>"
			+ "ℹ <b>" + __("{0} item(s) are already at {1} — no transfer needed", [
				at_supplier.length,
				frappe.utils.escape_html(frm.__mip_supplier_warehouse || frm.doc.supplier_warehouse || __("the supplier"))]) + "</b><br>"
			+ __("These are excess off-cuts this plan claimed through <b>Excess Material Mapping</b> while they were still at the supplier. They are not listed below because there is no stock in {0} to move.", [
				frappe.utils.escape_html(frm.doc.source_warehouse || __("the source warehouse"))])
			+ "<ul style='margin:6px 0 0 18px'>" + at_rows + "</ul>"
			+ "</div>";
	}

	// Two tabs. The first is the transfer itself, per batch; the second plans the
	// excess return for the same material CONSOLIDATED by item, because that is how
	// an off-cut is actually handled -- one item comes back as one shape, however
	// many batches it was drawn from. Asking per batch made the same item's excess
	// be entered two and three times over.
	// Folder tabs sitting on the panel: the inactive one sits back, the active one
	// shares its colour with the pane below and joins it with no line between, so
	// the body reads as the sheet the tab belongs to.
	_mip_inject_theme();
	var $tab_nav = $("<div style='padding-left:2px'>").append(
		$("<a href='#' class='mip-tab active' data-pane='transfer'>").text(__("Raw material to transfer")),
		$("<a href='#' class='mip-tab' data-pane='excess'>").text(__("Consolidate item for excess return plan"))
	);
	var $pane_transfer = $("<div class='mip-pane' data-pane='transfer'>")
		.append($(summary).addClass("mip-summary"), $filter_row, $actions, $table);
	var $pane_excess = $("<div class='mip-pane' data-pane='excess' style='display:none'>");
	var $content = $("<div>");
	if (!is_cnc_fwd) $content.append($tab_nav);
	$content.append($pane_transfer);
	if (!is_cnc_fwd) $content.append($pane_excess);

	$tab_nav.on("click", "a", function(e) {
		e.preventDefault();
		var pane = $(this).data("pane");
		$tab_nav.find("a").removeClass("active").filter("[data-pane='" + pane + "']").addClass("active");
		$content.find(".mip-pane").hide().filter("[data-pane='" + pane + "']").show();
		// Rebuilt on entry rather than kept in step continuously: it reads the
		// transfer tab's live figures, and those change with every tick and every
		// Sec Nos edit.
		if (pane === "excess") _render_excess_plan();
	});

	// ── Consolidated excess plan ──────────────────────────────────────────────
	//
	//   Excess Kg (system)  = Planned transfer weight - Planned drawing weight
	//   Difference          = Excess Kg (entered) - Excess Kg (system)
	//
	// Positive means more is coming back than the transfer created; negative means
	// part of the excess is unaccounted for. Neither blocks the transfer -- the
	// figure is there to be judged, not enforced.
	function _collect_excess_plan_state() {
		var by_item = {};
		$tbody.find("tr").each(function() {
			var $tr = $(this);
			if (!$tr.find(".mip-item-chk").prop("checked")) return;
			var d = items[parseInt($tr.data("idx"), 10)];
			if (!d) return;
			var e = by_item[d.item_code];
			if (!e) {
				e = by_item[d.item_code] = {
					item_code: d.item_code,
					item_name: d.item_name || d.item_code,
					group: d.custom_parent_item_group || "",
					thickness: flt(d.custom_thickness),
					unit_weight: flt(d.custom_unit_weight),
					drawing_kg: 0,
					transfer_kg: 0,
					batches: 0,
				};
			}
			e.drawing_kg += flt(d.drawing_planned_weight);
			e.transfer_kg += flt($tr.find(".mip-qty").val()) || flt(d.qty);
			e.batches += 1;
		});
		return by_item;
	}

	function _render_excess_plan() {
		var by_item = _collect_excess_plan_state();
		var codes = Object.keys(by_item).sort();
		if (!codes.length) {
			$pane_excess.html("<div class='text-muted' style='padding:20px 4px'>" +
				__("Tick the materials to transfer on the first tab. Whatever is selected there is consolidated here, one line per item.") +
				"</div>");
			return;
		}

		var th = "white-space:nowrap;padding:6px 8px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;";
		var html = "<div style='font-size:12px;color:#475569;margin-bottom:10px'>" +
			__("One line per item, with no batch reference: an off-cut comes back as one shape however many batches it was drawn from.") +
			"<br><b>" + __("Excess Kg (system)") + "</b> = " + __("Planned transfer weight − Planned drawing weight") +
			" &nbsp;·&nbsp; <b>" + __("Difference") + "</b> = " + __("Excess Kg (entered) − Excess Kg (system)") +
			" &nbsp;(" + __("positive = extra, negative = missing") + ")</div>" +
			"<div style='overflow-x:auto'><table class='table table-bordered table-condensed' style='margin-bottom:0;font-size:12px'>" +
			"<thead><tr>" +
				"<th style='" + th + "'>" + __("Item") + "</th>" +
				"<th style='" + th + "text-align:right'>" + __("Planned Drawing Wt") + "</th>" +
				"<th style='" + th + "text-align:right'>" + __("Planned Transfer Wt") + "</th>" +
				"<th style='" + th + "text-align:right'>" + __("Excess Kg") +
					"<div class='text-muted' style='font-weight:normal;font-size:10px'>" + __("system") + "</div></th>" +
				"<th style='" + th + "'>" + __("Length (mm)") + "</th>" +
				"<th style='" + th + "'>" + __("Width (mm)") + "</th>" +
				"<th style='" + th + "'>" + __("Thickness (mm)") + "</th>" +
				"<th style='" + th + "'>" + __("NOS") + "</th>" +
				"<th style='" + th + "text-align:right'>" + __("Excess Kg") +
					"<div class='text-muted' style='font-weight:normal;font-size:10px'>" + __("entered") + "</div></th>" +
				"<th style='" + th + "text-align:right'>" + __("Difference") + "</th>" +
			"</tr></thead><tbody>";

		codes.forEach(function(code) {
			var e = by_item[code];
			var sys = flt(e.transfer_kg - e.drawing_kg, 3);
			// Nothing was left over, so there is no off-cut to describe. The boxes are
			// closed rather than left open and ignored: an item transferred at exactly
			// its drawing weight used to accept a length and a piece count and report
			// them as a difference of the whole entered weight -- 162.112 mm and 4
			// pieces against 0.000 system excess reading "+9.662", which is an off-cut
			// nobody cut. A negative system figure is a shortfall, not an off-cut, so
			// it closes the boxes too.
			var no_excess = sys <= 0;
			// A row that stops having excess must not keep what was typed while it did.
			if (no_excess && dlg._excess_plan) delete dlg._excess_plan[code];
			var saved = (dlg._excess_plan || {})[code] || {};
			var why = no_excess
				? " title='" + __("No excess on this item — nothing to describe.") + "'"
				: "";
			// Said in the cell, in red, next to the figure it explains -- not left to
			// a tooltip nobody hovers. Zero and negative are different facts and must
			// not share a label: zero means the transfer matched the drawings exactly,
			// negative means less is going out than the drawings need, which is a
			// shortfall to go and look at, not an off-cut that happens to be absent.
			var no_excess_label = "";
			if (sys === 0) {
				no_excess_label = "<span class='mip-xs-none'>" + __("No excess material") + "</span>";
			} else if (sys < 0) {
				no_excess_label = "<span class='mip-xs-none'>" +
					__("Short by {0} Kg — no excess", [format_number(Math.abs(sys), null, 3)]) +
					"</span>";
			}
			var num = "<input type='number' step='0.001' min='0' class='form-control input-xs text-right ";
			function box(cls, width, value, also_disabled) {
				return num + cls + "' style='width:" + width + "px'" +
					((no_excess || also_disabled) ? " disabled" : "") + why +
					" value='" + (value || "") + "'>";
			}
			html += "<tr data-item='" + frappe.utils.escape_html(code) + "'" +
					(no_excess ? " class='mfx-no-excess'" : "") + ">" +
				"<td>" + frappe.utils.escape_html(code) +
					"<div class='text-muted' style='font-size:11px'>" +
						__("{0} batch row(s)", [e.batches]) + "</div></td>" +
				"<td class='text-right' style='white-space:nowrap'>" + format_number(e.drawing_kg, null, 3) + "</td>" +
				"<td class='text-right' style='white-space:nowrap'>" + format_number(e.transfer_kg, null, 3) + "</td>" +
				"<td class='text-right mip-xs-sys' style='white-space:nowrap;font-weight:600'>" +
					format_number(sys, null, 3) + no_excess_label + "</td>" +
				"<td>" + box("mip-xs-length", 100, flt(saved.length)) + "</td>" +
				// Width is only used by the Plates formula -- Structurals rows never
				// need it, so their Width box is read-only whatever the excess.
				"<td>" + box("mip-xs-width", 100, flt(saved.width), e.group === "Structurals") + "</td>" +
				"<td class='text-right' style='white-space:nowrap'>" + format_number(e.thickness, null, 2) + "</td>" +
				"<td>" + box("mip-xs-sec", 90, flt(saved.sec_qty)) + "</td>" +
				"<td class='text-right mip-xs-kg' style='white-space:nowrap;font-weight:600'>—</td>" +
				"<td class='text-right mip-xs-diff' style='white-space:nowrap;font-weight:600'>—</td>" +
			"</tr>";
		});
		html += "</tbody></table></div>";
		$pane_excess.html(html);
		$pane_excess.find("tr[data-item]").each(function() { _recalc_excess_row($(this), by_item); });
		$pane_excess.off("input.xs").on("input.xs", ".mip-xs-length, .mip-xs-width, .mip-xs-sec", function() {
			_recalc_excess_row($(this).closest("tr"), by_item);
		});
	}

	function _recalc_excess_row($row, by_item) {
		var e = by_item[$row.data("item")];
		if (!e) return;
		// A closed row has nothing to add up, and must not carry a figure from before
		// the transfer quantity changed under it.
		if ($row.hasClass("mfx-no-excess")) {
			if (dlg._excess_plan) delete dlg._excess_plan[e.item_code];
			$row.find(".mip-xs-kg").text("—");
			$row.find(".mip-xs-diff").text("—").css("color", "");
			return;
		}
		var L = flt($row.find(".mip-xs-length").val());
		var W = flt($row.find(".mip-xs-width").val());
		var S = flt($row.find(".mip-xs-sec").val());
		var entered = _excess_weight({
			custom_parent_item_group: e.group,
			custom_thickness: e.thickness,
			custom_unit_weight: e.unit_weight,
		}, L, W, S);
		var sys = flt(e.transfer_kg - e.drawing_kg, 3);

		// Remembered on the dialog, not only in the DOM: switching back to the
		// transfer tab re-renders this one from scratch.
		dlg._excess_plan = dlg._excess_plan || {};
		if (L || W || S) {
			dlg._excess_plan[e.item_code] = { length: L, width: W, sec_qty: S };
		} else {
			delete dlg._excess_plan[e.item_code];
		}

		if (entered === null) {
			$row.find(".mip-xs-kg").text("—");
			$row.find(".mip-xs-diff").text("—").css("color", "");
			return;
		}
		var diff = flt(entered - sys, 3);
		$row.find(".mip-xs-kg").text(format_number(entered, null, 3));
		$row.find(".mip-xs-diff")
			.text((diff > 0 ? "+" : "") + format_number(diff, null, 3))
			.attr("title", diff > 0 ? __("extra beyond the transfer") : diff < 0 ? __("missing") : "")
			.css("color", Math.abs(diff) < 0.001 ? "#15803d" : diff > 0 ? "#1d4ed8" : "#b91c1c");
	}

	var dlg = new frappe.ui.Dialog({
		title: is_cnc_fwd ? __("Select Materials — CNC to Supplier/WIP")
			: transfer_type === "cnc" ? __("Select Materials — To CNC Warehouse") : __("Select Materials to Transfer"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "content" }],
		primary_action_label: __("Transfer Selected"),
		secondary_action_label: __("Save and Close"),
		// Parks whatever has been typed and closes, without validating any of it --
		// the point is to step away mid-decision. Everything is re-checked server-side
		// when Transfer is pressed.
		secondary_action: function() {
			var draft = [];
			$tbody.find("tr").each(function() {
				var $tr = $(this);
				var d = items[parseInt($tr.data("idx"), 10)];
				if (!d) return;
				draft.push({
					item_code: d.item_code,
					batch_no: d.batch_no || "",
					cnc_process: d.cnc_process ? 1 : 0,
					custom_sec_qty: flt($tr.find(".mip-sec-qty").val()) || flt(d.custom_sec_qty),
				});
			});
			frappe.call({
				method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.save_transfer_draft",
				args: {
					mip_name: frm.doc.name,
					rows_json: JSON.stringify(draft),
					excess_plan_json: JSON.stringify(is_cnc_fwd ? {} : (dlg._excess_plan || {})),
					transfer_type: is_cnc_fwd ? "cnc_forward" : transfer_type,
				},
				freeze: true,
				freeze_message: __("Saving draft…"),
				callback: function(r) {
					dlg.hide();
					frappe.show_alert({
						message: __("Draft saved for {0} row(s). Reopen this popup to carry on.",
							[(r.message || {}).saved || 0]),
						indicator: "blue",
					}, 6);
					frm.reload_doc();
				},
			});
		},
		primary_action: function() {
			var selected = [];
			$tbody.find("tr").each(function() {
				var $tr = $(this);
				if (!$tr.find(".mip-item-chk").prop("checked")) return;
				var d = items[parseInt($tr.data("idx"), 10)];
				// Send whatever is in the Qty box, not the full pending figure --
				// that box IS the partial-transfer control.
				var qty = flt($tr.find(".mip-qty").val());
				selected.push($.extend({}, d, {
					qty: qty > 0 ? qty : flt(d.qty),
				}));
			});
			if (!selected.length) {
				frappe.msgprint(__("Please select at least one item."));
				return;
			}
			// Forwarding stock already received at CNC does not create another
			// off-cut. The source-warehouse legs alone plan and book excess.
			if (is_cnc_fwd) {
				_do_transfer(selected);
				return;
			}

			// The second tab's measured off-cut is mandatory for every
			// dimensioned item being moved: a Structurals/Plates row must have
			// its Excess Return dimensions entered before it can transfer, or
			// the off-cut leaves with no record of what is expected back. Other
			// groups (e.g. Nuts and Bolts) have no off-cut weight and are exempt.
			var excess_state = _collect_excess_plan_state();
			var missing = [];
			selected.forEach(function(s) {
				if (missing.indexOf(s.item_code) !== -1) return;
				var e = excess_state[s.item_code];
				if (!e) return;
				if (e.group !== "Structurals" && e.group !== "Plates") return;
				// Nothing is being sent beyond what the drawings called for, so
				// there is no off-cut to describe. Demanding dimensions here would
				// be asking for the shape of something that does not exist.
				if (flt(e.transfer_kg - e.drawing_kg, 3) <= 0) return;
				var plan = (dlg._excess_plan || {})[s.item_code] || {};
				var entered = _excess_weight({
					custom_parent_item_group: e.group,
					custom_thickness: e.thickness,
					custom_unit_weight: e.unit_weight,
				}, plan.length, plan.width, plan.sec_qty);
				if (entered === null) missing.push(s.item_code);
			});
			if (missing.length) {
				frappe.msgprint({
					title: __("Excess Return Not Entered"),
					message: __("Not allowed to transfer raw material without entering the excess return material return.")
						+ "<br>" + __("Enter the off-cut dimensions on the <b>Consolidate item for excess return plan</b> tab for: {0}",
							[missing.map(function(c) { return "<b>" + frappe.utils.escape_html(c) + "</b>"; }).join(", ")]),
					indicator: "orange",
				});
				return;
			}

			// Rounding Sec Nos up to whole pieces is expected -- it is the whole
			// point of this popup -- but it means issuing MORE than the plan
			// reserved, and that surplus comes back as excess. Say so plainly and
			// get a confirmation, rather than letting extra steel leave the rack on
			// the strength of a number the user may have typed without realising
			// what it implied.
			var over = selected.filter(function(s) {
				return flt(s.qty) > flt(s.planned_qty) + 0.001;
			});
			if (!over.length) {
				_do_transfer(selected);
				return;
			}

			var total_extra = 0;
			var rows = over.map(function(s) {
				var extra = flt(s.qty) - flt(s.planned_qty);
				total_extra += extra;
				return "<tr>"
					+ "<td style='padding:4px 10px 4px 0'>" + frappe.utils.escape_html(s.item_code) + "</td>"
					+ "<td style='padding:4px 10px 4px 0;color:#888'>" + frappe.utils.escape_html(s.batch_no || "-") + "</td>"
					+ "<td style='padding:4px 10px 4px 0;text-align:right'>" + format_number(flt(s.planned_qty), null, 3) + "</td>"
					+ "<td style='padding:4px 10px 4px 0;text-align:right'>" + format_number(flt(s.qty), null, 3) + "</td>"
					+ "<td style='padding:4px 0;text-align:right;color:#e8590c;font-weight:600'>+"
					+ format_number(extra, null, 3) + "</td></tr>";
			}).join("");

			frappe.confirm(
				__("These lines are being issued above what Material Planning reserved:")
				+ "<div style='overflow-x:auto;margin:10px 0'><table style='font-size:12px;border-collapse:collapse'>"
				+ "<thead><tr style='border-bottom:1px solid #ddd'>"
				+ "<th style='text-align:left;padding:4px 10px 4px 0'>" + __("Item") + "</th>"
				+ "<th style='text-align:left;padding:4px 10px 4px 0'>" + __("Batch") + "</th>"
				+ "<th style='text-align:right;padding:4px 10px 4px 0'>" + __("Planned") + "</th>"
				+ "<th style='text-align:right;padding:4px 10px 4px 0'>" + __("Transferring") + "</th>"
				+ "<th style='text-align:right;padding:4px 0'>" + __("Difference") + "</th>"
				+ "</tr></thead><tbody>" + rows + "</tbody></table></div>"
				+ __("The <b>{0} Kg</b> difference is recorded as <b>excess to return</b> on the Excess Material Items table, so it can be brought back once the job has cut what it needs. Stock is re-checked before anything moves.",
					[format_number(total_extra, null, 3)]),
				function() { _do_transfer(selected); }
			);
		},
	});

	function _do_transfer(selected) {
		{
			dlg.hide();
			// The CNC leg draws from the CNC warehouse, not the source warehouse, so
			// it has its own endpoint and its own pending/validation basis.
			frappe.call({
				method: is_cnc_fwd
					? "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.create_mip_cnc_partial_forward"
					: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.create_mip_partial_transfer",
				args: is_cnc_fwd
					? { mip_name: frm.doc.name, selected_items_json: JSON.stringify(selected) }
					: {
						mip_name: frm.doc.name,
						selected_items_json: JSON.stringify(selected),
						transfer_type: transfer_type,
						// One measured off-cut per item, from the second tab. Empty
						// when nothing was entered, and the server falls back to its
						// own placeholder shape exactly as before.
						excess_plan_json: JSON.stringify(dlg._excess_plan || {}),
					},
				freeze: true,
				freeze_message: __("Creating transfer entry…"),
				callback: function(r) {
					if (r.message) {
						_show_mip_transfer_entry_created(frm, r.message);
						frm.reload_doc();
					}
				},
			});
		}
	}

	function _mark_sec_nos_edited() {
		if (dlg._sec_edited) return;
		dlg._sec_edited = true;
		dlg.set_primary_action(__("Verify and Transfer"), dlg.primary_action);
	}

	dlg.$wrapper.addClass("mip-transfer-theme");
	dlg.$wrapper
		.on("shown.bs.modal", function() { $("body").addClass("mip-transfer-alerts-front"); })
		.on("hidden.bs.modal", function() { $("body").removeClass("mip-transfer-alerts-front"); });
	dlg.fields_dict.content.$wrapper.html($content);
	dlg.show();
}

// ── Excess Material Return ───────────────────────────────────────────────────

function _render_excess_action_btn(frm) {
	if (frm.is_new() || !frm.doc.excess_return_warehouse) return;
	if (!(frm.doc.excess_return_items || []).length) return;
	if (frm.is_dirty()) return;

	frm.add_custom_button(__("Return Excess Entry"), function() {
		_show_return_excess_dialog(frm);
	});
}

// "Return Excess Entry" -- review/edit the planned Qty and record a mandatory
// Reason for every row before the actual Material Receipt Stock Entry is
// created (client change request Phase 5.6). Structurals/Plates rows edit
// Length/Width/Sec Qty (Qty is always DERIVED for these groups -- Stock
// Entry's own validate_stock_entry hook recalculates Qty from dimensions on
// Material Receipt, so a directly-typed Qty would be silently discarded);
// every other group (e.g. Nuts and Bolts) edits Qty directly, matching how
// this same row already behaves everywhere else in this app (_mip_excess_calc
// below). Qty/dimensions + Reason entered here are saved back onto the
// excess_return_items row itself server-side, so re-opening this dialog
// later (or the grid) shows whatever was last entered.
function _show_return_excess_dialog(frm) {
	let rows = (frm.doc.excess_return_items || []).filter((r) => !r.stock_entry_created && flt(r.qty) > 0);
	if (!rows.length) {
		frappe.msgprint(__("No pending excess return rows to process. All rows already have a Stock Entry created, or no rows with Weight (Kg) > 0 exist."));
		return;
	}

	function _is_dim_driven(g) { return g === "Structurals" || g === "Plates"; }

	// Laid out the same way as the transfer popup's excess tab: one column per
	// dimension rather than three boxes stacked in a cell, and the same rules
	// about which of them an item actually uses -- Width belongs to the Plates
	// formula alone, and Thickness is the batch's for good, since cutting changes
	// Length and Width only.
	let num = "form-control input-xs text-right";
	let rows_html = rows.map(function(r) {
		let g = r.parent_item_group;
		let dim_driven = _is_dim_driven(g);
		let uses_width = g === "Plates";

		function box(cls, value, enabled) {
			return `<input type="number" step="0.001" min="0" class="${num} ${cls}"
				style="width:96px" value="${value ? flt(value, 3) : ""}"
				${enabled ? "" : "disabled"}>`;
		}

		let qty_cell = dim_driven
			? `<span class="_rex_qty_preview" style="font-weight:600">${format_number(flt(r.qty), null, 3)}</span>`
			: `<input type="number" step="0.001" min="0" class="${num} _rex_qty" style="width:96px" value="${flt(r.qty, 3)}">`;

		return `<tr data-name="${frappe.utils.escape_html(r.name)}" data-group="${frappe.utils.escape_html(g || "")}"
			data-thickness="${flt(r.thickness)}" data-unit-weight="${flt(r.unit_weight)}">
			<td style="padding:6px 8px">
				${frappe.utils.escape_html(r.item_code || "")}
				<div class="text-muted" style="font-size:11px">${frappe.utils.escape_html(g || "—")}</div>
			</td>
			<td style="padding:6px 8px">${box("_rex_length", r.length, dim_driven)}</td>
			<td style="padding:6px 8px">${box("_rex_width", r.width, dim_driven && uses_width)}</td>
			<td style="padding:6px 8px;text-align:right;white-space:nowrap">
				${flt(r.thickness) ? format_number(flt(r.thickness), null, 2) : "—"}</td>
			<td style="padding:6px 8px">${box("_rex_sec_qty", r.sec_qty, dim_driven)}</td>
			<td style="padding:6px 8px;text-align:right;white-space:nowrap">${qty_cell}</td>
			<td style="padding:6px 8px">
				<input type="text" class="form-control input-xs _rex_reason"
					placeholder="${__("Reason (required)…")}"
					value="${frappe.utils.escape_html(r.return_reason || "")}">
			</td>
		</tr>`;
	}).join("");

	let th = "padding:6px 8px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;white-space:nowrap;";
	let table_html = `<div class="text-muted" style="font-size:12px;margin-bottom:10px">
			${__("Measure the off-cut going back. Qty is calculated from the dimensions for Structurals and Plates — for anything else, type the weight directly.")}
			<br>${__("Width is used by Plates only, and Thickness is the batch's own and cannot be changed: a cut alters Length and Width, never Thickness.")}
		</div>
		<div style="overflow-x:auto">
		<table class="table table-bordered table-condensed" style="margin-bottom:0;font-size:12px">
		<thead><tr>
			<th style="${th}">${__("Item Code")}</th>
			<th style="${th}">${__("Length (mm)")}</th>
			<th style="${th}">${__("Width (mm)")}</th>
			<th style="${th}text-align:right">${__("Thickness (mm)")}</th>
			<th style="${th}">${__("NOS")}</th>
			<th style="${th}text-align:right">${__("Qty (Kg)")}</th>
			<th style="${th}min-width:240px">${__("Return Reason")}</th>
		</tr></thead>
		<tbody>${rows_html}</tbody>
	</table></div>`;

	let dialog = new frappe.ui.Dialog({
		title: __("Return Excess Entry — Review Qty & Reason"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "rows_html", options: table_html }],
		primary_action_label: __("Create Return Entry"),
		primary_action() {
			let payload = [];
			let missing_reason = [];
			let incomplete = [];
			dialog.$wrapper.find("tbody tr").each(function() {
				let $tr = $(this);
				let reason = ($tr.find("._rex_reason").val() || "").trim();
				let g = $tr.data("group");
				let item = ($tr.find("td").first().text() || "").trim().split("\n")[0];
				let entry = { name: $tr.data("name"), return_reason: reason };
				if (_is_dim_driven(g)) {
					entry.length = flt($tr.find("._rex_length").val());
					if (g === "Plates") entry.width = flt($tr.find("._rex_width").val());
					entry.sec_qty = flt($tr.find("._rex_sec_qty").val());
					// The same rule the rest of the app applies: a weight cannot be
					// produced without every input its own group's formula reads, and
					// a row that computes to nothing would be received as 0 Kg.
					let need = [];
					if (!entry.length) need.push(__("Length"));
					if (g === "Plates" && !entry.width) need.push(__("Width"));
					if (!entry.sec_qty) need.push(__("NOS"));
					if (!flt($tr.data("thickness")) && g === "Plates") need.push(__("Thickness (on the batch)"));
					if (need.length) incomplete.push(item + " — " + need.join(", "));
				} else {
					entry.qty = flt($tr.find("._rex_qty").val());
					if (entry.qty <= 0) incomplete.push(item + " — " + __("Qty"));
				}
				if (!reason) missing_reason.push(item);
				payload.push(entry);
			});
			if (incomplete.length) {
				frappe.msgprint({
					title: __("Measurements Incomplete"),
					message: __("These rows cannot produce a weight until every figure their group's formula needs is filled in:")
						+ "<ul style='margin:6px 0 0 18px'>"
						+ incomplete.map(function(t) { return "<li>" + frappe.utils.escape_html(t) + "</li>"; }).join("")
						+ "</ul>",
					indicator: "orange",
				});
				return;
			}
			if (missing_reason.length) {
				frappe.msgprint({
					title: __("Reason Required"),
					message: __("A Return Reason is what makes this stock explainable later. Enter one for: {0}",
						[missing_reason.map(function(t) { return "<b>" + frappe.utils.escape_html(t) + "</b>"; }).join(", ")]),
					indicator: "orange",
				});
				return;
			}
			frappe.confirm(
				__("This material will be received into the Finished Goods Warehouse ({0}). Continue?", [frappe.utils.escape_html(frm.doc.excess_return_warehouse)]),
				function () {
					dialog.hide();
					frappe.call({
						method: "manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer.create_mip_excess_return_entry",
						args: { mip_name: frm.doc.name, rows_json: JSON.stringify(payload) },
						freeze: true,
						freeze_message: __("Creating return entry…"),
						callback(r) {
							if (r.message) {
								frappe.msgprint({ title: __("Return Excess Entry Created"), message: __("Return Stock Entry: ") + '<a href="/app/stock-entry/' + encodeURIComponent(r.message) + '">' + r.message + "</a>", indicator: "green" });
								frm.reload_doc();
							}
						},
					});
				}
			);
		},
	});

	// Live Qty preview as the user edits Length/Width/Sec Qty on a dimension-driven row.
	dialog.$wrapper.find("tbody tr").each(function() {
		let $tr = $(this);
		let g = $tr.data("group");
		if (!_is_dim_driven(g)) return;
		function _refresh() {
			let L = flt($tr.find("._rex_length").val());
			let W = flt($tr.find("._rex_width").val());
			let S = flt($tr.find("._rex_sec_qty").val());
			let uw = flt($tr.data("unit-weight"));
			let T = flt($tr.data("thickness"));
			let qty = null;
			if (g === "Structurals" && L && uw && S) qty = (L / 1000) * uw * S;
			else if (g === "Plates" && L && W && T && uw && S) qty = (L / 1000) * (W / 1000) * T * uw * S;
			$tr.find("._rex_qty_preview").text(qty !== null ? format_number(flt(qty, 3), null, 3) : "—");
		}
		$tr.find("._rex_length, ._rex_width, ._rex_sec_qty").on("input", _refresh);
	});

	dialog.show();
}

// Weight auto-calc for excess_return_items — SCO Excess Material Item is a shared
// child doctype; each parent page (SCO, WO, and now Material Issue Plan) must
// register its own handlers for it to behave interactively on that form.
frappe.ui.form.on("SCO Excess Material Item", {
	item_code(frm, cdt, cdn) {
		if (frm.doctype !== "Material Issue Plan") return;
		var row = locals[cdt][cdn];
		if (row.stock_entry_created) {
			frappe.msgprint(__("This row is locked — Stock Entry already created."));
			return;
		}
		if (!row.item_code) return;
		frappe.db.get_value("Item", row.item_code,
			["custom_parent_item_group", "custom_unit_weight", "custom_secondary_uom", "stock_uom"],
			function(v) {
				if (!v) return;
				frappe.model.set_value(cdt, cdn, "parent_item_group", v.custom_parent_item_group || "");
				frappe.model.set_value(cdt, cdn, "unit_weight", v.custom_unit_weight || 0);
				frappe.model.set_value(cdt, cdn, "sec_uom", v.custom_secondary_uom || "");
				frappe.model.set_value(cdt, cdn, "uom", v.stock_uom || "");
			});
	},
	length(frm, cdt, cdn)    { if (frm.doctype === "Material Issue Plan" && !locals[cdt][cdn].stock_entry_created) _mip_excess_calc(frm, cdt, cdn); },
	width(frm, cdt, cdn)     { if (frm.doctype === "Material Issue Plan" && !locals[cdt][cdn].stock_entry_created) _mip_excess_calc(frm, cdt, cdn); },
	thickness(frm, cdt, cdn) { if (frm.doctype === "Material Issue Plan" && !locals[cdt][cdn].stock_entry_created) _mip_excess_calc(frm, cdt, cdn); },
	sec_qty(frm, cdt, cdn)   { if (frm.doctype === "Material Issue Plan" && !locals[cdt][cdn].stock_entry_created) _mip_excess_calc(frm, cdt, cdn); },
	enter_weight_instead_of_pieces(frm, cdt, cdn) {
		if (frm.doctype !== "Material Issue Plan") return;
		if (locals[cdt][cdn].stock_entry_created) return;
		// Recompute in whichever direction is now the live one, so the row is
		// consistent the moment the tick changes rather than at the next keystroke.
		_mip_excess_calc(frm, cdt, cdn);
		frm.fields_dict.excess_return_items.grid.refresh_row(cdn);
	},
	qty(frm, cdt, cdn) {
		if (frm.doctype !== "Material Issue Plan") return;
		var row = locals[cdt][cdn];
		if (!row.stock_entry_created) {
			if (row.enter_weight_instead_of_pieces) {
				// The typed weight is the truth now; the piece count follows from it.
				_mip_excess_sec_from_qty(frm, cdt, cdn);
			} else if (row.parent_item_group === "Nuts and Bolts" && row.unit_weight) {
				frappe.model.set_value(cdt, cdn, "sec_qty", flt(row.unit_weight * flt(row.qty), 3));
			}
		}
		_mip_excess_totals(frm);
	},
	// The way out of the "already reserved" block: release the claim, correct the
	// dimensions, then map the off-cut again from the Material Planning. Confirmed
	// first because releasing it puts the off-cut back in front of every other job's
	// picker, so the claiming plan can lose it to someone else.
	unlink_claim_btn(frm, cdt, cdn) {
		if (frm.doctype !== "Material Issue Plan") return;
		var row = locals[cdt][cdn];
		if (!row.mapped_material_planning) {
			frappe.msgprint(__("This excess item is not claimed by any Material Planning."));
			return;
		}
		frappe.confirm(
			__("Release <b>{0}</b> from Material Planning <b>{1}</b>?<br><br>Its reservation there will be dropped and the off-cut becomes available for any job to claim again.",
				[frappe.utils.escape_html(row.item_code || ""), frappe.utils.escape_html(row.mapped_material_planning)]),
			function() {
				frappe.call({
					method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.unlink_excess_claim",
					args: { mip_name: frm.doc.name, excess_row_name: row.name },
					freeze: true,
					freeze_message: __("Releasing claim…"),
					callback(r) {
						if (!r.message) return;
						frappe.show_alert({
							message: __("Claim released from {0}. Dimensions can now be edited.", [r.message.released_from]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			}
		);
	},
});

// Weight of ONE piece of this off-cut's shape. Both directions hang off it: pieces
// times this is the weight, weight divided by this is the pieces.
function _mip_excess_kg_per_piece(row) {
	var g = row.parent_item_group;
	if (g === "Structurals") {
		if (row.length && row.unit_weight) return (row.length / 1000) * row.unit_weight;
	} else if (g === "Plates") {
		if (row.length && row.width && row.thickness && row.unit_weight) {
			return (row.length / 1000) * (row.width / 1000) * row.thickness * row.unit_weight;
		}
	}
	return 0;
}

// Pieces -> weight, the usual direction: the shape and the count are known.
function _mip_excess_calc(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	if (row.enter_weight_instead_of_pieces) {
		// Ticked, the weight is what was typed, so the count is what follows.
		_mip_excess_sec_from_qty(frm, cdt, cdn);
		return;
	}
	var per = _mip_excess_kg_per_piece(row);
	if (per && row.sec_qty) frappe.model.set_value(cdt, cdn, "qty", flt(per * flt(row.sec_qty), 3));
	_mip_excess_totals(frm);
}

// Weight -> pieces, the other direction. Left fractional on purpose, the same way a
// Material Planning row's Sec Nos is: 18 Kg of a 4.90625 Kg piece is 3.669 of one,
// and rounding it up here would quietly claim a piece that is not being returned.
function _mip_excess_sec_from_qty(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	var per = _mip_excess_kg_per_piece(row);
	frappe.model.set_value(cdt, cdn, "sec_qty", per ? flt(flt(row.qty) / per, 3) : 0);
	_mip_excess_totals(frm);
}

function _mip_excess_totals(frm) {
	var tkg = 0, tnos = 0;
	(frm.doc.excess_return_items || []).forEach(function(r) { tkg += flt(r.qty); tnos += flt(r.sec_qty); });
	frm.set_value("excess_return_total_kg", flt(tkg, 3));
	frm.set_value("excess_return_total_nos", flt(tnos, 3));
}

// Rows matching the free-text Customer Drawing No / DUNO-Mark No / Sales Order
// filters (AND semantics, substring match; a blank filter matches everything) —
// same filter semantics as Production Plan's drawing picker (public/js/production_plan.js).
function _mip_row_matches_filters(r, f) {
	return (!f.cdn || String(r.customer_drawing_number || "").toLowerCase().includes(f.cdn))
		&& (!f.duno || String(r.duno_mark_no || "").toLowerCase().includes(f.duno))
		&& (!f.so || String(r.sales_order || "").toLowerCase().includes(f.so));
}

// Batch/purchase-reference cell — reservable rows show their batch (or "no batch"),
// unavailable/purchased rows show a link to the Purchase Receipt that fulfilled them.
function _mip_batch_cell_html(r) {
	if (r.batch_no) return frappe.utils.escape_html(r.batch_no);
	if (r.purchase_receipt) {
		return __("Purchased via {0}", [
			`<a href="/app/purchase-receipt/${encodeURIComponent(r.purchase_receipt)}" target="_blank">`
			+ `${frappe.utils.escape_html(r.purchase_receipt)}</a>`,
		]);
	}
	return r.is_unavailable
		? `<span style="color:#adb5bd;">${__("Pending Purchase")}</span>`
		: `<span style="color:#adb5bd;">${__("no batch")}</span>`;
}

// Builds the filter bar + results table ONCE into the dialog's "picker_html" field
// and returns a controller so the caller can update the highlighted row (on every
// click) and pre-fill filters (on preselect) without tearing down and rebuilding the
// filter inputs each time — rebuilding on every click would otherwise wipe out
// whatever the user had already typed into the filter boxes.
// Reservable rows (Material Mapping / Available Raw Material) are clickable and
// call `on_select`; Unavailable Item rows are shown dimmed for context only —
// they can't be reallocated here (must go through Material Request/Purchase).
function _mip_build_picker(dialog, all_rows, on_select) {
	let $wrap = dialog.fields_dict.picker_html.$wrapper;
	let selected_row_name = null;

	let filter_bar = `
		<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px;padding:8px 10px;background:#f8f9fa;border:1px solid #e9ecef;border-radius:4px;">
			<div style="display:flex;flex-direction:column;gap:3px;flex:1;min-width:140px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Customer Drawing No")}</label>
				<input id="_mip_ub_cdn" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;min-width:100px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("DUNO / Mark No")}</label>
				<input id="_mip_ub_duno" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;min-width:120px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">${__("Sales Order")}</label>
				<input id="_mip_ub_so" type="text" placeholder="${__("Filter…")}"
					style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:100%;">
			</div>
			<div style="display:flex;flex-direction:column;gap:3px;align-items:flex-start;justify-content:flex-end;padding-bottom:1px;">
				<label style="font-size:10px;font-weight:600;color:#6c757d;margin:0;">&nbsp;</label>
				<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
					<button class="btn btn-xs" id="_mip_ub_clear"
						style="background:#c62828;color:#fff;border-color:#c62828;">${__("Clear Filters")}</button>
					<span id="_mip_ub_count" style="font-size:12px;color:#6c757d;white-space:nowrap;"></span>
				</div>
			</div>
		</div>`;

	let th_style = "white-space:nowrap;padding:6px 10px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;";
	let cols = [
		["item_code", __("Item Code")],
		["duno_mark_no", __("DUNO/Mark No")],
		["customer_drawing_number", __("Cust Drawing No")],
		["sales_order", __("Sales Order")],
		["_batch", __("Batch / Purchase Ref")],
		["sec_qty", __("NOS")],
		["reqd_kg", __("Reqd Kg")],
		["qty", __("Qty (Kg)")],
	];
	let thead = "<tr>" + cols.map((c) => `<th style="${th_style}">${c[1]}</th>`).join("") + "</tr>";

	let table_html = `<div style="overflow-x:auto;">
		<table style="font-size:12px;border-collapse:collapse;width:100%;min-width:700px;">
			<thead style="position:sticky;top:0;z-index:1;">${thead}</thead>
			<tbody id="_mip_ub_tbody"></tbody>
		</table>
	</div>`;

	$wrap.html(filter_bar + `<div style="max-height:32vh;overflow-y:auto;border:1px solid #e9ecef;border-radius:4px;">${table_html}</div>`);

	function _render_rows(rows) {
		let $tbody = $wrap.find("#_mip_ub_tbody");
		$tbody.html(rows.map((r) => {
			let reservable = r.source_table !== "Material Planning Unavailable Item";
			let is_selected = r.name === selected_row_name;
			let row_style = reservable
				? `cursor:pointer;${is_selected ? "background:#e3f2fd;" : ""}`
				: "cursor:not-allowed;color:#adb5bd;background:#fafbfc;";
			let cells = [
				frappe.utils.escape_html(r.item_code || ""),
				frappe.utils.escape_html(r.duno_mark_no || ""),
				frappe.utils.escape_html(r.customer_drawing_number || ""),
				frappe.utils.escape_html(r.sales_order || ""),
				_mip_batch_cell_html(r),
				format_number(flt(r.sec_qty), null, 3),
				format_number(flt(r.reqd_kg), null, 3),
				format_number(flt(r.qty), null, 3),
			];
			return `<tr data-name="${frappe.utils.escape_html(r.name)}" data-reservable="${reservable ? 1 : 0}" style="${row_style}">`
				+ cells.map((c) => `<td style="padding:5px 10px;white-space:nowrap;border-bottom:1px solid #f0f0f0;">${c}</td>`).join("")
				+ "</tr>";
		}).join(""));
		$wrap.find("#_mip_ub_count").text(__("{0} shown", [rows.length]));

		$tbody.find("tr[data-reservable='1']").on("click", function() {
			let row = all_rows.find((r) => r.name === $(this).data("name"));
			if (row) on_select(row);
		});
	}

	function _get_filters() {
		return {
			cdn: (($wrap.find("#_mip_ub_cdn").val()) || "").toLowerCase().trim(),
			duno: (($wrap.find("#_mip_ub_duno").val()) || "").toLowerCase().trim(),
			so: (($wrap.find("#_mip_ub_so").val()) || "").toLowerCase().trim(),
		};
	}

	function _apply_filter() {
		let f = _get_filters();
		_render_rows(all_rows.filter((r) => _mip_row_matches_filters(r, f)));
	}

	$wrap.find("#_mip_ub_cdn, #_mip_ub_duno, #_mip_ub_so").on("input", _apply_filter);
	$wrap.find("#_mip_ub_clear").on("click", function() {
		$wrap.find("#_mip_ub_cdn, #_mip_ub_duno, #_mip_ub_so").val("");
		_apply_filter();
	});

	_render_rows(all_rows);

	return {
		// Highlight `row_name` as selected and re-render with whatever filters are
		// currently typed (does NOT reset the filter inputs).
		markSelected(row_name) {
			selected_row_name = row_name;
			_apply_filter();
		},
		// Pre-fill the filter inputs (used when opening via the per-row grid button)
		// and apply them immediately.
		setFilters(cdn, duno, so) {
			$wrap.find("#_mip_ub_cdn").val(cdn || "");
			$wrap.find("#_mip_ub_duno").val(duno || "");
			$wrap.find("#_mip_ub_so").val(so || "");
			_apply_filter();
		},
	};
}

const _MIP_ALLOC_FIELDS = [
	"current_batch", "current_sec_qty", "current_qty",
	"new_batch_no", "length", "width", "thickness", "sec_qty", "calculated_qty",
	"reserve_without_dimensions",
];
const _MIP_NEW_ALLOC_FIELDS = [
	"new_batch_no", "length", "width", "thickness", "sec_qty", "calculated_qty",
	"reserve_without_dimensions",
];

// "Update Batch" dialog — search/filter across every raw material row (reservable and
// purchased/unavailable, for context), pick one reservable row, review its current
// allocation (read-only) alongside an editable new-allocation panel, then reassign.
// `preselect_row_name` (optional) is the raw_materials row to open straight onto,
// used by the per-row grid button; the toolbar button opens it with nothing selected.
function _show_update_batch_dialog(frm, preselect_row_name) {
	let all_rows = frm.doc.raw_materials || [];
	if (!all_rows.length) {
		frappe.msgprint(__("No raw materials found. Use \"Refresh Raw Materials\" first."));
		return;
	}

	let selected_row = null;

	let dialog = new frappe.ui.Dialog({
		title: __("Update Batch"),
		size: "extra-large",
		fields: [
			{ fieldtype: "HTML", fieldname: "picker_html" },
			{ fieldtype: "HTML", fieldname: "no_selection_html" },
			{ fieldtype: "Section Break", label: __("Current Allocation") },
			{ fieldname: "current_batch", fieldtype: "Data", label: __("Current Batch / Purchase Ref"), read_only: 1 },
			{ fieldname: "current_sec_qty", fieldtype: "Float", label: __("Current NOS"), read_only: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "current_qty", fieldtype: "Float", label: __("Current Qty (Kg)"), read_only: 1 },
			{ fieldname: "reqd_kg", fieldtype: "Float", label: __("Reqd Kg"), read_only: 1,
				description: __("The drawing's own planned/required weight -- fixed, does not change no matter which batch/NOS is picked below.") },
			{ fieldtype: "HTML", fieldname: "transferred_notice_html" },
			{ fieldtype: "Section Break", label: __("New Allocation"), fieldname: "new_alloc_section" },
			{ fieldname: "new_batch_no", fieldtype: "Link", options: "Batch", label: __("New Batch"), reqd: 1,
				description: __("Length/Width/Thickness are fetched from the batch automatically.") },
			{ fieldname: "length", fieldtype: "Float", label: __("Length (mm)"), read_only: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "width", fieldtype: "Float", label: __("Width (mm)"), read_only: 1 },
			{ fieldname: "thickness", fieldtype: "Float", label: __("Thickness (mm)"), read_only: 1 },
			{ fieldname: "sec_qty", fieldtype: "Float", label: __("NOS") },
			{ fieldname: "calculated_qty", fieldtype: "Float", label: __("Calculated Qty (Kg)"), read_only: 1 },
			{ fieldname: "reserve_without_dimensions", fieldtype: "Check", label: __("Reserve Without Dimensions") },
		],
		primary_action_label: __("Reassign Batch"),
		primary_action(values) {
			if (!selected_row) {
				frappe.msgprint(__("Select a raw material row first."));
				return;
			}
			if (flt(selected_row.transferred_qty) > 0) {
				frappe.msgprint(__("This batch has already been transferred. Reassignment is not allowed."));
				return;
			}
			if (!values.new_batch_no) {
				frappe.msgprint(__("Select a New Batch."));
				return;
			}
			// Material Mapping: length/width/thickness are the row's REQUIRED (demand)
			// dimensions, a separate concept from the batch's own physical dimensions —
			// reassign_batch already fetches the batch's dims from the Batch record
			// directly for that table, so leave required dims untouched here.
			// Available Raw Material: there's no such split — length/width/thickness
			// there ARE the assigned batch's own dimensions, so send what we fetched.
			let dimensions = selected_row.source_table === "Material Planning Material Mapping"
				? {}
				: { length: values.length, width: values.width, thickness: values.thickness };
			frappe.call({
				method: "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.reassign_batch",
				args: {
					material_planning_name: selected_row.material_planning,
					source_table: selected_row.source_table,
					row_name: selected_row.source_row,
					new_batch_no: values.new_batch_no,
					dimensions: JSON.stringify(dimensions),
					sec_qty: values.sec_qty,
					reserve_without_dimensions: values.reserve_without_dimensions ? 1 : 0,
					material_issue_plan: frm.doc.name,
				},
				freeze: true,
				freeze_message: __("Reassigning batch..."),
				callback(r) {
					// Dialog stays open — the user reassigns several rows in one sitting;
					// they close it themselves (X / click-outside) when done.
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
					// refresh_mip_raw_materials rebuilds the raw_materials snapshot from
					// scratch, so every row gets a brand-new `.name` — re-locate the row via
					// its stable source_table/source_row reference (the underlying Material
					// Planning child row), not the MIP snapshot's own transient name.
					let reassigned_source_table = selected_row.source_table;
					let reassigned_source_row = selected_row.source_row;
					frappe.call({
						method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.refresh_mip_raw_materials",
						args: { mip_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Refreshing raw materials..."),
						callback() {
							frm.reload_doc().then(() => {
								// Mutate all_rows IN PLACE — _mip_build_picker/_select_row above
								// already closed over this same array, so this refreshes both
								// the picker table and this dialog's row lookups without
								// needing to rebuild the picker or reopen the dialog.
								all_rows.splice(0, all_rows.length, ...(frm.doc.raw_materials || []));
								let updated_row = all_rows.find((r) =>
									r.source_table === reassigned_source_table && r.source_row === reassigned_source_row
								);
								if (updated_row) {
									// Re-selecting shows the just-updated Current Allocation and
									// resets New Allocation inputs, ready for the next row.
									_select_row(updated_row);
								} else {
									picker.markSelected(null);
								}
							});
						},
					});
				},
			});
		},
	});

	dialog.fields_dict.no_selection_html.$wrapper.html(
		`<div style="color:#8d99a6;padding:8px 4px;font-size:12px;">`
		+ __("Select a reservable row above to review its current allocation and reassign a new batch.")
		+ `</div>`
	);
	dialog.fields_dict.transferred_notice_html.$wrapper.html("");

	function _toggle_allocation_fields(show, is_transferred) {
		_MIP_ALLOC_FIELDS.forEach((f) => dialog.fields_dict[f].toggle(show));
		dialog.fields_dict.no_selection_html.toggle(!show);
		// Hide "New Allocation" section and its fields if already transferred
		let block_edit = show && is_transferred;
		_MIP_NEW_ALLOC_FIELDS.forEach((f) => dialog.fields_dict[f].toggle(!block_edit));
		dialog.fields_dict.new_alloc_section && dialog.fields_dict.new_alloc_section.toggle && dialog.fields_dict.new_alloc_section.toggle(!block_edit);
		dialog.fields_dict.transferred_notice_html.toggle(block_edit);
		if (block_edit) {
			dialog.fields_dict.transferred_notice_html.$wrapper.html(
				`<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:10px 14px;margin:8px 0;color:#856404;">`
				+ `<b>${__("Already Transferred")}</b> — `
				+ __("This batch has been transferred to the Supplier / WIP Warehouse. Batch reassignment is not allowed after transfer.")
				+ `</div>`
			);
		} else {
			dialog.fields_dict.transferred_notice_html.$wrapper.html("");
		}
		// Show/hide the Reassign Batch button accordingly
		if (dialog.get_primary_btn) {
			dialog.get_primary_btn().toggle(!block_edit);
		}
	}

	// Length/Width/Thickness always come from the Batch record itself (custom_length/
	// custom_width/custom_thickness) — same as Material Planning's own Material Mapping
	// grid — never typed in by hand.
	function _fetch_batch_dims(batch_no) {
		if (!batch_no) {
			dialog.set_value("length", 0);
			dialog.set_value("width", 0);
			dialog.set_value("thickness", 0);
			dialog.set_value("calculated_qty", 0);
			return;
		}
		frappe.db.get_value("Batch", batch_no, ["custom_length", "custom_width", "custom_thickness"]).then((r) => {
			let d = r.message || {};
			dialog.set_value("length", flt(d.custom_length));
			dialog.set_value("width", flt(d.custom_width));
			dialog.set_value("thickness", flt(d.custom_thickness));
			_refresh_alloc_figures();
		});
	}
	dialog.fields_dict.new_batch_no.df.onchange = () => _fetch_batch_dims(dialog.get_value("new_batch_no"));

	// Weight of ONE piece of the chosen batch, in the row's own item group. The
	// inverse of _calc_new_qty: given a weight, how many pieces is that.
	function _kg_per_piece() {
		if (!selected_row) return 0;
		let g = selected_row.parent_item_group;
		let uw = flt(selected_row.unit_weight);
		let l = flt(dialog.get_value("length"));
		let w = flt(dialog.get_value("width"));
		let t = flt(dialog.get_value("thickness"));
		if (g === "Structurals" && l && uw) return (l / 1000) * uw;
		if (g === "Plates" && l && w && t && uw) return (l / 1000) * (w / 1000) * t * uw;
		return 0;
	}

	// Which figure is typed and which is worked out depends on the checkbox, so both
	// paths run through here rather than each caller deciding for itself.
	function _refresh_alloc_figures() {
		if (dialog.get_value("reserve_without_dimensions")) {
			// Which field holds "the Kg this row will reserve" differs by table.
			// Material Mapping reserves its requirement, and reqd_kg is a copy of it.
			// Exact Match's reqd_kg is overall_required_qty -- the WHOLE requirement,
			// which check_stock_availability may have split across several batches --
			// so the row's own share is qty (required_qty). Using reqd_kg there
			// overstates a split requirement by every other batch's share.
			let kg = flt(selected_row && (
				selected_row.source_table === "Material Planning Available Raw Material"
					? selected_row.qty
					: selected_row.reqd_kg));
			let per = _kg_per_piece();
			dialog.set_value("calculated_qty", flt(kg, 3));
			dialog.set_value("sec_qty", per ? flt(kg / per, 3) : 0);
		} else {
			_calc_new_qty();
		}
	}

	function _calc_new_qty() {
		if (!selected_row) return;
		if (dialog.get_value("reserve_without_dimensions")) return;
		let g = selected_row.parent_item_group;
		let uw = flt(selected_row.unit_weight);
		let l = flt(dialog.get_value("length"));
		let w = flt(dialog.get_value("width"));
		let t = flt(dialog.get_value("thickness"));
		let sec = flt(dialog.get_value("sec_qty"));
		let qty = 0;
		if (g === "Structurals" && l && uw && sec) {
			qty = (l / 1000) * uw * sec;
		} else if (g === "Plates" && l && w && t && uw && sec) {
			qty = (l / 1000) * (w / 1000) * t * uw * sec;
		}
		dialog.set_value("calculated_qty", flt(qty, 3));
	}
	dialog.fields_dict.sec_qty.df.onchange = () => _calc_new_qty();
	dialog.fields_dict.sec_qty.$input && dialog.fields_dict.sec_qty.$input.on("input", _calc_new_qty);

	// "Reserve Without Dimensions" mirrors Material Mapping's own toggle: when checked,
	// Sec Qty is no longer typed in — the row reserves its exact Required Qty in Kg and
	// Sec Nos is derived from it server-side (_apply_rwd_fractional_nos), left fractional
	// until someone rounds it to whole pieces at transfer time.
	function _toggle_rwd(checked) {
		// Ticked, the two figures swap roles: the row reserves its Required Qty in Kg
		// and Sec Nos is that weight expressed in pieces -- shown here rather than left
		// blank until the server works it out, so the fraction is visible before
		// anything is reserved. Untick it and Sec Nos is typed again, weight follows.
		dialog.fields_dict.sec_qty.df.read_only = checked ? 1 : 0;
		dialog.fields_dict.sec_qty.df.description = checked
			? __("Worked out from the Required Qty -- fractional on purpose; whole pieces are settled at transfer time.")
			: "";
		dialog.fields_dict.sec_qty.refresh();
		dialog.fields_dict.calculated_qty.df.description = checked
			? __("The row's own Required Qty. This is what gets reserved.")
			: __("Worked out from NOS and the batch's dimensions.");
		dialog.fields_dict.calculated_qty.refresh();
		if (!checked) dialog.set_value("sec_qty", 0);
		_refresh_alloc_figures();
	}
	dialog.fields_dict.reserve_without_dimensions.df.onchange = () =>
		_toggle_rwd(dialog.get_value("reserve_without_dimensions"));

	function _select_row(row) {
		selected_row = row;
		let is_transferred = flt(row.transferred_qty) > 0;
		dialog.set_value("current_batch", row.batch_no || (row.purchase_receipt ? __("Purchased via {0}", [row.purchase_receipt]) : __("(none)")));
		dialog.set_value("current_sec_qty", flt(row.sec_qty));
		dialog.set_value("current_qty", flt(row.qty));
		dialog.set_value("reqd_kg", flt(row.reqd_kg));
		dialog.set_value("new_batch_no", "");
		dialog.set_value("length", 0);
		dialog.set_value("width", 0);
		dialog.set_value("thickness", 0);
		dialog.set_value("sec_qty", 0);
		dialog.set_value("calculated_qty", 0);
		dialog.set_value("reserve_without_dimensions", 0);
		_toggle_allocation_fields(true, is_transferred);
		_toggle_rwd(0);
		picker.markSelected(row.name);
	}

	_toggle_allocation_fields(false, false);
	let picker = _mip_build_picker(dialog, all_rows, _select_row);

	// "Refresh Raw Materials" button inside the dialog header
	dialog.$wrapper.find(".modal-header .modal-title").after(
		`<button class="btn btn-xs btn-default mip-dlg-refresh" style="margin-left:12px;vertical-align:middle;">`
		+ frappe.utils.icon("refresh", "xs") + " " + __("Refresh Raw Materials")
		+ `</button>`
	);
	dialog.$wrapper.find(".mip-dlg-refresh").on("click", function() {
		frappe.call({
			method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.refresh_mip_raw_materials",
			args: { mip_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Refreshing raw materials..."),
			callback() {
				frm.reload_doc().then(() => {
					all_rows.splice(0, all_rows.length, ...(frm.doc.raw_materials || []));
					// Re-select the current row with updated data if one was selected
					if (selected_row) {
						let updated = all_rows.find((r) =>
							r.source_table === selected_row.source_table && r.source_row === selected_row.source_row
						);
						if (updated) _select_row(updated);
						else _toggle_allocation_fields(false, false);
					}
					frappe.show_alert({ message: __("Raw materials refreshed"), indicator: "green" });
				});
			},
		});
	});

	if (preselect_row_name) {
		let row = all_rows.find((r) => r.name === preselect_row_name);
		if (row) {
			picker.setFilters(row.customer_drawing_number, row.duno_mark_no, row.sales_order);
			_select_row(row);
		}
	}

	dialog.show();
}

// ── Consolidate Items: Update Batch ──────────────────────────────────────────
//
// The row-level Update Batch above moves ONE Material Planning child row. This moves
// a whole consolidate line -- every raw-material row merged into it, across however
// many Material Plannings they came from.
//
// It works because the reassignment is dimensionless: each member reserves its own
// required Kg and expresses the piece count as a fraction, so the only figure that has
// to reconcile is total Kg. What the user states per target batch is a piece count,
// which at the batch's own size gives that batch a weight; rows then fill the batches
// in table order.
//
// Two steps: Preview (read-only), then a confirmation listing every current
// reservation, then apply. This is now the ONLY place batches are reassigned on a
// Material Issue Plan -- the Raw Materials buttons are hidden. See
// manufyxinvenzaerp_features.md, section 20.

const _MIP_CB = "manufyxinvenzaerp.subcontracting_management.material_issue_plan_batch_update.";

function _add_consolidate_update_batch_button(frm) {
	let grid = frm.fields_dict["consolidate_items"] && frm.fields_dict["consolidate_items"].grid;
	if (!grid || frm.is_new()) return;

	// "top" is not a preference here, it is required: consolidate_items is read_only,
	// and Frappe hides .grid-footer entirely for a read-only grid whose rows all fit on
	// one page -- which would take a bottom-toolbar button with it. The per-row button
	// alongside it needs its own workaround for the same read-only grid; see below.
	grid.add_custom_button(
		frappe.utils.icon("edit", "xs") + " " + __("Update Batch"),
		() => _open_consolidate_update_batch(frm),
		"top"
	);
	_setup_consolidate_row_buttons(frm, grid);
}

// Per-row "Update Batch" on Consolidate Items, matching the one Raw Materials had.
//
// It cannot simply be a Button field left to Frappe. Frappe only builds a real
// control for a grid cell when the row is being edited, and this grid is read-only,
// so a plain Button column would render as an empty cell. Instead the cell's
// formatter draws the button itself, which works on a static row. Clicking a
// read-only row normally opens the row's detail view and swallows the click, so the
// click is caught in the capture phase -- before the row sees it -- and stopped.
function _setup_consolidate_row_buttons(frm, grid) {
	const formatter = function (value, df, options, doc) {
		if (!doc || !doc.batch_no || frm.is_new()) return "";
		// A line with anything shipped cannot be reassigned at all (refused whole on
		// the server), so say so in the cell rather than offer a button that fails.
		if (flt(doc.transferred_qty) > 0.001) {
			return `<span class="text-muted small" title="${__("Already transferred — this line cannot be reassigned.")}">${__("Transferred")}</span>`;
		}
		return `<button type="button" class="btn btn-xs mfx-action-btn-alt mfx-cb-row-btn"
			data-row="${frappe.utils.escape_html(doc.name)}" style="white-space:nowrap">${__("Update Batch")}</button>`;
	};

	// Rows copy their docfields from the meta the first time they render, so set it
	// on the meta for rows not yet drawn and on the grid for rows that already are.
	let meta_df = frappe.meta.get_docfield("Material Issue Plan Consolidate Item", "update_batch_btn");
	if (meta_df) meta_df.formatter = formatter;
	try {
		grid.update_docfield_property("update_batch_btn", "formatter", formatter);
	} catch (e) {
		// A row from before the field existed has no such docfield; the meta copy
		// above covers it on the next render.
	}

	if (!grid.wrapper[0].__mfx_cb_row_click) {
		grid.wrapper[0].addEventListener("click", function (e) {
			let btn = e.target.closest && e.target.closest(".mfx-cb-row-btn");
			if (!btn) return;
			e.preventDefault();
			e.stopPropagation();
			_open_consolidate_update_batch(frm, btn.getAttribute("data-row"));
		}, true);
		grid.wrapper[0].__mfx_cb_row_click = true;
	}
	grid.refresh();
}

// The same button inside the expanded row view, where Frappe does render the control.
frappe.ui.form.on("Material Issue Plan Consolidate Item", {
	update_batch_btn(frm, cdt, cdn) {
		_open_consolidate_update_batch(frm, cdn);
	},
});

// Every Update Batch entry point comes through here. Once a transfer or any other
// stock action exists on this plan the batch may not change (client decision,
// 14 Sep 2026), and the user is told so before a dialog opens rather than after
// filling it in. The server refuses the same case on preview and apply regardless.
function _open_consolidate_update_batch(frm, preselect_row_name) {
	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.check_mip_batch_change_allowed",
		args: { mip_name: frm.doc.name },
		callback(r) {
			let res = r.message || {};
			if (res.blocked) {
				frappe.msgprint({
					title: __("Batch Cannot Be Reassigned"),
					indicator: "red",
					message: res.message,
				});
				return;
			}
			_show_consolidate_update_batch_dialog(frm, preselect_row_name);
		},
	});
}

function _show_consolidate_update_batch_dialog(frm, preselect_row_name) {
	let lines = (frm.doc.consolidate_items || []).filter((r) => !!r.batch_no);
	if (!lines.length) {
		frappe.msgprint(__("No consolidated lines yet. Allocate batches on the Raw Materials tab first."));
		return;
	}

	let selected = null;
	let targets = [{}];
	// Resolved by the server per line, NOT taken from frm.doc.source_warehouse.
	// Every stock figure the server computes comes from the Material Planning's
	// for_warehouse, and the two are not always the same -- on some plans the Issue
	// Plan's is blank. Pricing candidates against the wrong one is invisible until
	// the numbers do not add up.
	let lineWarehouse = "";
	// Only batches with free stock in this plan's source warehouse are offered. A
	// zero-stock batch is precisely the case downstream validation does not catch.
	let candidates = [];
	// Candidates arrive one call after the line is picked. Without this the row renders
	// "nothing to reassign to" for the moment in between, which is a lie on every line.
	let candidatesLoaded = false;

	let d = new frappe.ui.Dialog({
		title: __("Update Batch — Consolidate Items"),
		size: "extra-large",
		fields: [
			{ fieldtype: "HTML", fieldname: "lines_html" },
			{ fieldtype: "Section Break", label: __("New Batches"), fieldname: "targets_section" },
			{ fieldtype: "HTML", fieldname: "targets_html" },
			{ fieldtype: "Section Break", label: __("What This Would Do"), fieldname: "result_section" },
			{ fieldtype: "HTML", fieldname: "result_html" },
		],
		primary_action_label: __("Preview"),
		primary_action() { _preview(); },
	});

	// The dialog is deliberately two steps. Applying commits as it goes -- the
	// reserve/unreserve helpers each commit internally, so a fan-out across several
	// plans cannot be rolled back as a unit -- and the only defence against that is
	// that the user has seen exactly what will happen first. So Reassign is not
	// reachable until a preview has come back clean, and ANY edit afterwards drops
	// back to Preview rather than applying a plan nobody looked at.
	let lastPlan = null;

	function _armPreview() {
		lastPlan = null;
		d.set_primary_action(__("Preview"), () => _preview());
	}

	// ── Line picker ──────────────────────────────────────────────────────────
	function _render_lines() {
		let th = "padding:6px 8px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;white-space:nowrap;";
		let rows = lines.map(function (r) {
			// A line with anything shipped cannot be reassigned at all, so it is shown
			// greyed rather than hidden -- "why is my line not in the list" is a worse
			// question than "why is it greyed".
			let done = flt(r.transferred_qty) > 0.001;
			let sel = selected && selected.name === r.name;
			let style = done
				? "cursor:not-allowed;color:#adb5bd;background:#fafbfc;"
				: "cursor:pointer;" + (sel ? "background:#e3f2fd;" : "");
			return `<tr data-name="${r.name}" data-ok="${done ? 0 : 1}" style="${style}">
				<td style="padding:5px 8px">${frappe.utils.escape_html(r.item_code || "")}</td>
				<td style="padding:5px 8px">${frappe.utils.escape_html(r.batch_no || "")}</td>
				<td style="padding:5px 8px;text-align:right">${r.source_rows || 0}</td>
				<td style="padding:5px 8px;text-align:right">${format_number(flt(r.qty), null, 3)}</td>
				<td style="padding:5px 8px;text-align:right">${format_number(flt(r.transferred_qty), null, 3)}</td>
				<td style="padding:5px 8px">${r.cnc_process ? __("CNC") : ""}</td>
			</tr>`;
		}).join("");

		d.fields_dict.lines_html.$wrapper.html(
			`<div style="max-height:26vh;overflow:auto;border:1px solid #e9ecef;border-radius:4px">
			<table style="width:100%;border-collapse:collapse;font-size:12px">
			<thead style="position:sticky;top:0;z-index:1"><tr>
				<th style="${th}">${__("Item")}</th><th style="${th}">${__("Batch")}</th>
				<th style="${th};text-align:right">${__("Rows")}</th>
				<th style="${th};text-align:right">${__("Reqd Kg")}</th>
				<th style="${th};text-align:right">${__("Issued Kg")}</th>
				<th style="${th}">${__("CNC")}</th>
			</tr></thead><tbody>${rows}</tbody></table></div>`
		);

		d.fields_dict.lines_html.$wrapper.find("tr[data-ok='1']").on("click", function () {
			_select_line($(this).data("name"));
		});
	}

	function _select_line(name) {
			selected = lines.find((x) => x.name === name);
			if (!selected) return;
			_armPreview();
			_render_lines();
			d.fields_dict.result_html.$wrapper.empty();
			// A fresh row, not the last line's. The batches offered are this item's, so
			// carrying the previous selection over left a plate's 12,000 x 2,500 and its
			// free weight sitting on an ISMB line -- and the picker, which matches what
			// is typed, then had nothing to show against a batch from another item.
			targets = [{}];
			candidates = [];
			candidatesLoaded = false;
			_render_targets();
			frappe.call({
				method: _MIP_CB + "get_consolidate_line_context",
				args: { mip_name: frm.doc.name, consolidate_row_name: selected.name },
				callback(ctx) {
					let c = ctx.message || {};
					lineWarehouse = c.warehouse || "";
					if (!lineWarehouse) {
						candidates = [];
						candidatesLoaded = true;
						_render_targets();
						frappe.show_alert({
							message: (c.warehouses || []).length > 1
								? __("The plans behind this line use different warehouses ({0}). They cannot be reassigned together.",
									[(c.warehouses || []).join(", ")])
								: __("No Raw Materials Warehouse is set on the linked Material Planning."),
							indicator: "red",
						}, 8);
						return;
					}
					frappe.call({
						method: _MIP_CB + "get_candidate_batches",
						args: { item_code: c.item_code, warehouse: lineWarehouse },
						callback(r) {
							candidates = r.message || [];
							candidatesLoaded = true;
							_render_targets();
						},
					});
				},
			});
	}

	// ── Target batches ───────────────────────────────────────────────────────
	function _render_targets() {
		if (!selected) {
			d.fields_dict.targets_html.$wrapper.html(
				`<div style="color:#8d99a6;font-size:12px;padding:6px 2px">`
				+ __("Pick a line above first.") + `</div>`);
			return;
		}
		let th = "padding:6px 8px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;white-space:nowrap;";
		let rows = targets.map(function (t, i) {
			return `<tr data-i="${i}">
				<td style="padding:4px 6px"><div class="_cb_batch_mount" data-i="${i}" style="width:260px"></div></td>
				<td style="padding:4px 6px"><input type="text" class="form-control input-xs text-right _cb_len" readonly tabindex="-1"
					style="width:95px;background:#f4f5f7;color:#495057;cursor:default" value="${t.length ? format_number(t.length, null, 3) : ""}"></td>
				<td style="padding:4px 6px"><input type="text" class="form-control input-xs text-right _cb_wid" readonly tabindex="-1"
					style="width:95px;background:#f4f5f7;color:#495057;cursor:default" value="${t.width ? format_number(t.width, null, 3) : ""}"></td>
				<td style="padding:4px 6px"><input type="number" step="0.001" class="form-control input-xs text-right _cb_pcs"
					style="width:85px" value="${t.pieces || ""}"></td>
				<td style="padding:4px 6px;font-size:11px;color:#6c757d;white-space:nowrap" class="_cb_info">${t._info || ""}</td>
				<td style="padding:4px 6px">${targets.length > 1
					? `<button class="btn btn-xs btn-default _cb_del">&times;</button>` : ""}</td>
			</tr>`;
		}).join("");

		d.fields_dict.targets_html.$wrapper.html(
			`<div style="font-size:12px;color:#6c757d;margin-bottom:6px">`
			+ __("Any batch with free stock is listed, whatever item or size it holds — send one ISMB800 in place of four ISMB200 if that is the plan. Length and Width are the batch's own and cannot be changed. Enter Pieces — Pieces × the batch's piece weight is how much of the batch this line may take.")
			+ `</div>
			<table style="border-collapse:collapse;font-size:12px"><thead><tr>
				<th style="${th}">${__("Batch")}</th><th style="${th}">${__("Length (mm)")}</th>
				<th style="${th}">${__("Width (mm)")}</th><th style="${th}">${__("Pieces")}</th>
				<th style="${th}">${__("Weight")}</th><th style="${th}"></th>
			</tr></thead><tbody>${rows}</tbody></table>
			<button class="btn btn-xs btn-default _cb_add" style="margin-top:8px">+ ${__("Add batch")}</button>`
			+ ((candidates || []).length || !candidatesLoaded ? "" :
				`<div style="color:#c0392b;font-size:11px;margin-top:8px">`
				+ __("No batch of any item has free stock in {0}. There is nothing to reassign this line to.",
					[frappe.utils.escape_html(lineWarehouse || "")])
				+ `</div>`)
			+ ((candidates || []).length === 1 && candidates[0].batch_no === selected.batch_no ?
				`<div style="color:#a06000;font-size:11px;margin-top:8px">`
				+ __("{0} is the only batch with free stock in {1}, and this line is already on it.",
					[frappe.utils.escape_html(candidates[0].batch_no),
					 frappe.utils.escape_html(lineWarehouse || "")])
				+ `</div>` : "")
		);

		let $w = d.fields_dict.targets_html.$wrapper;

		// A real Link control, not a <select>: the same searchable picker used
		// everywhere else in the desk, because 48 batches is a list you type into
		// rather than scroll. Its query is consolidate_batch_query, which narrows on
		// batch name or item code and shows item, free Kg and size beside each hit.
		$w.find("._cb_batch_mount").each(function () {
			let $mount = $(this);
			let i = $mount.data("i");
			let ctrl = frappe.ui.form.make_control({
				parent: $mount,
				render_input: true,
				df: {
					fieldtype: "Link",
					options: "Batch",
					fieldname: "_cb_batch_" + i,
					placeholder: __("Search batch or item…"),
					get_query() {
						return {
							query: _MIP_CB + "consolidate_batch_query",
							filters: { warehouse: lineWarehouse, item_code: selected.item_code },
						};
					},
					onchange() {
						let v = ctrl.get_value() || "";
						if (v === (targets[i].batch_no || "")) return;
						targets[i].batch_no = v;
						targets[i].length = targets[i].width = 0;
						_armPreview();
						_price(i);
					},
				},
			});
			ctrl.$wrapper.find(".control-label, .help-box").remove();
			ctrl.set_value(targets[i].batch_no || "");
			targets[i]._ctrl = ctrl;
		});
		$w.find("._cb_pcs").on("change", function () {
			let $tr = $(this).closest("tr"), i = $tr.data("i");
			targets[i].pieces = flt($tr.find("._cb_pcs").val());
			_armPreview();
			_price(i);
		});
		$w.find("._cb_add").on("click", function () { _armPreview(); targets.push({}); _render_targets(); });
		$w.find("._cb_del").on("click", function () {
			_armPreview();
			targets.splice($(this).closest("tr").data("i"), 1);
			_render_targets();
		});
	}

	// Live capacity for one target, so the user sees what a piece count is worth before
	// previewing the whole thing.
	function _price(i) {
		let t = targets[i];
		if (!t.batch_no) return;
		frappe.call({
			method: _MIP_CB + "get_batch_capacity",
			args: {
				batch_no: t.batch_no, warehouse: lineWarehouse,
				pieces: t.pieces || 0,
			},
			callback(r) {
				let p = r.message || {};
				if (!p.ok) { t._info = `<span style="color:#c62828">${p.error || __("Unknown batch")}</span>`; }
				else {
					t.length = p.length;
					t.width = p.width;
					let over = p.capacity_kg > p.free_kg + 0.001;
					t._info = __("{0} Kg", [format_number(p.capacity_kg, null, 3)])
						+ ` <span style="color:${over ? "#c62828" : "#6c757d"}">(`
						+ __("Total available Weight {0}", [format_number(p.free_kg, null, 3)]) + ")</span>";
				}
				_render_targets();
			},
		});
	}

	// Batch and piece count only. Length/Width are shown for reference but the server
	// always prices a batch at its own recorded size.
	function _targets_payload() {
		return targets.filter((t) => t.batch_no).map((t) => ({ batch_no: t.batch_no, pieces: t.pieces || 0 }));
	}

	// ── Preview ──────────────────────────────────────────────────────────────
	function _preview() {
		if (!selected) { frappe.msgprint(__("Pick a line first.")); return; }
		frappe.call({
			method: _MIP_CB + "preview_consolidate_batch_update",
			args: {
				mip_name: frm.doc.name,
				consolidate_row_name: selected.name,
				targets_json: JSON.stringify(_targets_payload()),
			},
			freeze: true,
			freeze_message: __("Checking…"),
			callback(r) {
				let res = r.message || {};
				_render_result(res);
				if (res.ok) {
					lastPlan = res;
					d.set_primary_action(__("Reassign Batch"), () => _confirm());
				} else {
					_armPreview();
				}
			},
		});
	}

	// ── Confirm, then apply ──────────────────────────────────────────────────
	function _confirm() {
		if (!lastPlan) { _preview(); return; }
		let g = lastPlan.group || {};
		let members = lastPlan.members || [];
		let tgt = lastPlan.targets || [];
		let esc = frappe.utils.escape_html;
		let fmt = (v) => format_number(flt(v), null, 3);
		let newBatches = tgt.map((t) => t.batch_no).join(", ");
		let reservedRows = members.filter((m) => m.is_reserved);
		let reservedKg = reservedRows.reduce((a, m) => a + flt(m.reserved_qty), 0);

		// Shown BEFORE anything moves: exactly what is reserved today, on which batch,
		// against which plan, and where each row will go. A line can reach across
		// several Material Plannings, and the person confirming usually opened only one
		// of them -- they must see every reservation that is about to be released.
		let th = "padding:5px 8px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;white-space:nowrap;";
		let td = "padding:4px 8px;border-bottom:1px solid #eef0f2;";
		let rows = members.map((m) => {
			let dest = (m.target_index === null || m.target_index === undefined)
				? "" : ((tgt[m.target_index] || {}).batch_no || "");
			return `<tr>
				<td style="${td}text-align:right;color:#6c757d">${m.idx}</td>
				<td style="${td}">${esc(m.duno_mark_no || "")}</td>
				<td style="${td}color:#6c757d">${esc(m.customer_drawing_number || "")}</td>
				<td style="${td}color:#6c757d">${esc(m.material_planning || "")}</td>
				<td style="${td}text-align:right;color:#6c757d">${m.mp_idx === null || m.mp_idx === undefined ? "—" : m.mp_idx}</td>
				<td style="${td}">${esc(m.batch_no || "")}</td>
				<td style="${td}">${m.is_reserved
					? `<span style="color:#1a7f4b;font-weight:600">${__("Reserved")}</span>`
					: `<span style="color:#8d99a6">${__("Not reserved")}</span>`}</td>
				<td style="${td}text-align:right">${m.is_reserved ? fmt(m.reserved_qty) : "—"}</td>
				<td style="${td}text-align:center;color:#8d99a6">→</td>
				<td style="${td}font-weight:600">${esc(dest)}</td>
				<td style="${td}text-align:right">${fmt(m.target_kg)}</td>
			</tr>`;
		}).join("");

		let plans = (lastPlan.material_plannings || []).map((p) =>
			`<li><b>${esc(p.material_planning)}</b> — `
			+ __("{0} row(s), {1} Kg", [p.rows, fmt(p.qty)]) + `</li>`).join("");

		let warn = (lastPlan.warnings || []).map((w) =>
			`<div style="margin-top:8px;padding:8px 10px;background:#fffbeb;border-left:3px solid #f59e0b;
			border-radius:3px;font-size:12px;color:#78350f">${w}</div>`).join("");

		let c = new frappe.ui.Dialog({
			title: __("Confirm Batch Reassignment"),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("Yes, Unreserve and Reassign"),
			primary_action() {
				c.hide();
				_apply();
			},
			secondary_action_label: __("No"),
			secondary_action() { c.hide(); },
		});

		c.fields_dict.body.$wrapper.html(
			`<div style="font-size:13px;margin-bottom:10px">`
			+ __("<b>{0}</b> row(s) of <b>{1}</b> ({2} Kg) are currently assigned to batch <b>{3}</b>. <b>{4}</b> of them are reserved, holding <b>{5} Kg</b>.",
				[members.length, esc(g.item_code || ""), fmt(g.total_kg), esc(g.batch_no || ""),
				 reservedRows.length, fmt(reservedKg)])
			+ `</div>
			<div style="font-weight:600;font-size:12px;margin-bottom:4px">${__("Current reservation and new assignment")}</div>
			<div style="max-height:40vh;overflow:auto;border:1px solid #e9ecef;border-radius:4px">
			<table style="width:100%;border-collapse:collapse;font-size:12px">
			<thead style="position:sticky;top:0;z-index:1"><tr>
				<th style="${th};text-align:right">${__("MIP Row")}</th>
				<th style="${th}">${__("DUNO/Mark")}</th>
				<th style="${th}">${__("Customer Drawing")}</th>
				<th style="${th}">${__("Material Planning")}</th>
				<th style="${th};text-align:right">${__("Plan Row")}</th>
				<th style="${th}">${__("Current Batch")}</th>
				<th style="${th}">${__("Status")}</th>
				<th style="${th};text-align:right">${__("Reserved Kg")}</th>
				<th style="${th}"></th>
				<th style="${th}">${__("New Batch")}</th>
				<th style="${th};text-align:right">${__("New Kg")}</th>
			</tr></thead><tbody>${rows}</tbody></table></div>

			<div style="margin-top:10px;font-size:12px">${__("Plans that will change:")}
				<ul style="margin:4px 0 0 18px">${plans}</ul></div>

			<div style="margin-top:10px;padding:10px 12px;background:#eef6ff;border-left:3px solid #2563eb;border-radius:3px;font-size:12px;color:#1e3a8a">
				${__("On <b>Yes</b>:")}
				<ol style="margin:4px 0 0 18px">
					<li>${__("The existing reservations above are <b>unreserved</b> from batch {0}.", [esc(g.batch_no || "")])}</li>
					<li>${__("Every row is assigned to the new batch {0}{1}.", [esc(newBatches),
						g.rwd_applies ? __(", without matching dimensions — each row reserves its own required Kg") : ""])}</li>
					<li>${__("Every row is <b>reserved again</b> against the new batch.")}</li>
				</ol>
			</div>`
			+ warn
		);
		c.show();
	}

	function _apply() {
		frappe.call({
			method: _MIP_CB + "apply_consolidate_batch_update",
			args: {
				mip_name: frm.doc.name,
				consolidate_row_name: selected.name,
				targets_json: JSON.stringify(_targets_payload()),
				plan_hash: lastPlan.plan_hash,
			},
			freeze: true,
			freeze_message: __("Reassigning and re-reserving…"),
			callback(r) {
				let m = r.message || {};
				if (!m.ok) return;
				d.hide();
				let done = __("Unreserved {0} row(s) from <b>{1}</b> and reserved them on <b>{2}</b> ({3} Kg).",
					[m.rows, frappe.utils.escape_html(m.from_batch || ""),
					 frappe.utils.escape_html((m.to_batches || []).join(", ")),
					 format_number(flt(m.qty), null, 3)]);
				if ((m.warnings || []).length) {
					frappe.msgprint({
						title: __("Reassigned, with warnings"),
						indicator: "orange",
						message: done + "<ul style='margin:8px 0 0 18px'>"
							+ (m.warnings).map((w) => `<li>${w}</li>`).join("") + "</ul>",
					});
				} else {
					frappe.show_alert({ message: done, indicator: "green" }, 8);
				}
				frm.reload_doc();
			},
		});
	}

	function _render_result(res) {
		let html = "";
		let g = res.group || {};

		html += `<div style="font-size:12px;margin-bottom:10px">`
			+ __("This line covers <b>{0}</b> row(s) totalling <b>{1} Kg</b>, across <b>{2}</b> Material Planning(s).",
				[g.rows || 0, format_number(flt(g.total_kg), null, 3), g.plans || 0])
			+ (g.rwd_applies
				? " " + __("They would be reassigned without dimensions — each row reserving its own required Kg.")
				: " " + __("This item group does not use dimensionless reserving."))
			+ `</div>`;

		(res.material_plannings || []).forEach(function (p) {
			html += `<div style="font-size:12px;color:#495057">• <b>${frappe.utils.escape_html(p.material_planning)}</b> — `
				+ __("{0} row(s), {1} Kg", [p.rows, format_number(flt(p.qty), null, 3)]) + `</div>`;
		});

		(res.blockers || []).forEach(function (b) {
			html += `<div style="margin-top:8px;padding:8px 10px;background:#fef2f2;border-left:3px solid #b91c1c;
				border-radius:3px;font-size:12px;color:#7f1d1d">${b}</div>`;
		});
		(res.warnings || []).forEach(function (w) {
			html += `<div style="margin-top:8px;padding:8px 10px;background:#fffbeb;border-left:3px solid #f59e0b;
				border-radius:3px;font-size:12px;color:#78350f">${w}</div>`;
		});

		if ((res.targets || []).length) {
			let th = "padding:5px 8px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;";
			html += `<table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:12px">
				<thead><tr><th style="${th}">${__("Batch")}</th>
				<th style="${th};text-align:right">${__("Weight")}</th>
				<th style="${th};text-align:right">${__("Total Batch Weight")}</th>
				<th style="${th};text-align:right">${__("Assigned")}</th>
				<th style="${th};text-align:right">${__("Rows")}</th>
				<th style="${th};text-align:right">${__("Excess")}</th></tr></thead><tbody>`
				+ (res.targets).map(function (t) {
					return `<tr><td style="padding:5px 8px">${frappe.utils.escape_html(t.batch_no)}</td>
					<td style="padding:5px 8px;text-align:right">${format_number(flt(t.capacity_kg), null, 3)}</td>
					<td style="padding:5px 8px;text-align:right">${format_number(flt(t.free_kg), null, 3)}</td>
					<td style="padding:5px 8px;text-align:right;font-weight:600">${format_number(flt(t.assigned_kg), null, 3)}</td>
					<td style="padding:5px 8px;text-align:right">${t.assigned_rows}</td>
					<td style="padding:5px 8px;text-align:right;color:${flt(t.leftover_kg) > 0.001 ? "#a8620a" : "#6c757d"}">
						${format_number(flt(t.leftover_kg), null, 3)}</td></tr>`;
				}).join("") + `</tbody></table>`;
		}

		// Which row lands on which batch. Essential once there is more than one
		// target: a row is never split and the cursor never goes back, so the cut
		// point is a consequence of table order that has to be visible BEFORE
		// applying, not discovered afterwards.
		if ((res.members || []).length) {
			let multi = (res.targets || []).length > 1;
			let th = "padding:5px 8px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;";
			html += `<div style="margin-top:12px;font-size:12px;font-weight:600">`
				+ __("Rows on this line") + `</div>
				<div style="max-height:24vh;overflow:auto;border:1px solid #e9ecef;border-radius:4px;margin-top:4px">
				<table style="width:100%;border-collapse:collapse;font-size:12px"><thead style="position:sticky;top:0;z-index:1"><tr>
				<th style="${th};text-align:right">${__("MIP Row")}</th>
				<th style="${th}">${__("DUNO/Mark")}</th>
				<th style="${th}">${__("Customer Drawing")}</th>
				<th style="${th}">${__("Material Planning")}</th>
				<th style="${th};text-align:right">${__("Plan Row")}</th>
				<th style="${th};text-align:right">${__("Kg")}</th>
				<th style="${th}">${__("Goes to")}</th></tr></thead><tbody>`
				+ (res.members).map(function (m) {
					let unplaced = m.target_index === null || m.target_index === undefined;
					let dest = unplaced
						? `<span style="color:#b91c1c">${__("not placed")}</span>`
						: frappe.utils.escape_html((res.targets[m.target_index] || {}).batch_no || "");
					return `<tr style="${unplaced ? "background:#fef2f2" : ""}">
						<td style="padding:4px 8px;text-align:right;color:#6c757d">${m.idx}</td>
						<td style="padding:4px 8px">${frappe.utils.escape_html(m.duno_mark_no || "")}</td>
						<td style="padding:4px 8px;color:#6c757d">${frappe.utils.escape_html(m.customer_drawing_number || "")}</td>
						<td style="padding:4px 8px;color:#6c757d">${frappe.utils.escape_html(m.material_planning || "")}</td>
						<td style="padding:4px 8px;text-align:right;color:#6c757d">${m.mp_idx === null || m.mp_idx === undefined ? "—" : m.mp_idx}</td>
						<td style="padding:4px 8px;text-align:right">${format_number(flt(m.target_kg), null, 3)}</td>
						<td style="padding:4px 8px">${multi || unplaced ? dest : `<span style="color:#6c757d">${dest}</span>`}</td>
					</tr>`;
				}).join("") + `</tbody></table></div>`;
		}

		html += `<div style="margin-top:12px;padding:8px 10px;border-radius:3px;font-size:12px;`
			+ (res.ok
				? `background:#e3f3ea;color:#1a7f4b">` + __("This reassignment is valid.")
					+ " " + __("Choose <b>Reassign Batch</b> to apply it.")
				: `background:#f4f5f7;color:#495057">` + __("Nothing would be changed."))
			+ `</div>`;

		d.fields_dict.result_html.$wrapper.html(html);
	}

	_render_lines();
	_render_targets();
	d.show();

	if (preselect_row_name) {
		let line = lines.find((x) => x.name === preselect_row_name);
		if (line && flt(line.transferred_qty) > 0.001) {
			frappe.msgprint(__("This line has already been transferred and cannot be reassigned."));
		} else if (line) {
			_select_line(preselect_row_name);
		}
	}
}
