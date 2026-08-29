// `var`, not `const` -- see the note on the same line in purchase_order.js:
// both files are eval'd into one shared global script scope, and a repeated
// top-level `const` is a SyntaxError that discards the entire second file.
var FORMULA_GROUPS = ["Structurals", "Plates"];

function calc_total_weight(frm) {
	const total = (frm.doc.items || [])
		.filter(r => FORMULA_GROUPS.includes(r.custom_parent_item_group))
		.reduce((sum, r) => sum + (r.qty || 0), 0);
	frm.set_value("custom_total_weight", total);
}

frappe.ui.form.on("Purchase Receipt Item", {
	qty(frm, cdt, cdn) {
		calc_total_weight(frm);
	},

	custom_parent_item_group(frm, cdt, cdn) {
		calc_total_weight(frm);
	},

	items_remove(frm) {
		calc_total_weight(frm);
	},
});

// Inspection Call workflow (shared with Job Card / Supplier Operation Entry
// via manufyxinvenzaerp.production_management.inspection) — opt-in per Item
// (`custom_inspection_required`). The call date is captured per round via a
// popup and stored only on the call log row (and its linked Inspection
// Entry) — Purchase Receipt itself does not persist a separate date field.
// Both actions render as Button fields inside the Inspection tab (not the
// page toolbar), right above Inspection Status.
function _pr_inspection_state(frm) {
	const log = frm.doc.custom_inspection_call_log || [];
	const last = log.length ? log[log.length - 1] : null;
	const in_progress = last && last.round_status !== "Completed";
	return { log, last, in_progress };
}

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.is_new()) return;

		const { last, in_progress } = _pr_inspection_state(frm);
		let label = __("Create Inspection");
		if (in_progress && !last.inspection_entry) label = __("Create Inspection Entry");
		else if (in_progress && last.inspection_entry) label = __("View Inspection Entry");
		frm.set_df_property("custom_create_inspection_btn", "label", label);
	},

	custom_create_inspection_btn(frm) {
		const { last, in_progress } = _pr_inspection_state(frm);

		if (in_progress && last.inspection_entry) {
			frappe.set_route("Form", "Inspection Entry", last.inspection_entry);
			return;
		}

		if (in_progress && !last.inspection_entry) {
			frappe.call({
				method: "manufyxinvenzaerp.production_management.inspection.create_inspection_entry",
				args: { source_doctype: "Purchase Receipt", source_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating Inspection Entry…"),
				callback(r) {
					if (r.message) {
						frm.reload_doc();
						frappe.set_route("Form", "Inspection Entry", r.message);
					}
				},
			});
			return;
		}

		frappe.prompt(
			[{
				fieldname: "call_date",
				fieldtype: "Date",
				label: __("Inspection Call Date"),
				reqd: 1,
				default: frappe.datetime.get_today(),
			}],
			function (values) {
				frappe.call({
					method: "manufyxinvenzaerp.production_management.inspection.add_inspection_call",
					args: {
						source_doctype: "Purchase Receipt",
						source_name: frm.doc.name,
						call_date: values.call_date,
					},
					freeze: true,
					freeze_message: __("Logging inspection call…"),
					callback() {
						frappe.call({
							method: "manufyxinvenzaerp.production_management.inspection.create_inspection_entry",
							args: { source_doctype: "Purchase Receipt", source_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Creating Inspection Entry…"),
							callback(r) {
								frm.reload_doc();
								if (r.message) {
									frappe.set_route("Form", "Inspection Entry", r.message);
								}
							},
						});
					},
				});
			},
			__("Create Inspection"),
			__("Create")
		);
	},

	custom_update_inspection_call_date_btn(frm) {
		const { last } = _pr_inspection_state(frm);
		if (!last) return;

		frappe.prompt(
			[{
				fieldname: "call_date",
				fieldtype: "Date",
				label: __("Inspection Call Date"),
				reqd: 1,
				default: last.call_date,
			}],
			function (values) {
				frappe.call({
					method: "manufyxinvenzaerp.production_management.inspection.update_inspection_call_date",
					args: {
						source_doctype: "Purchase Receipt",
						source_name: frm.doc.name,
						call_date: values.call_date,
					},
					freeze: true,
					callback() {
						frm.reload_doc();
					},
				});
			},
			__("Update Inspection Call Date"),
			__("Update")
		);
	},
});

// After PR submission: show popup if any batches were auto-allocated to Material Planning
//
// This hung off "after_submit" for a long time and therefore never ran once: Frappe
// has no such form event. The ones it actually triggers around a save are
// after_save / before_submit / before_cancel / after_cancel (see
// frappe/public/js/frappe/form/form.js), and after_save fires for a submit too --
// the submit goes through the same savedoc path. So the receipt submitted, batches
// were allocated into the plan, and the popup that was supposed to say so was never
// reached; nor was the "nothing was allocated, here is why" branch below it, which
// is the one that mattered most.
//
// Guarded on docstatus so an ordinary draft save says nothing, and on a per-form
// flag so re-saving an already-submitted receipt does not show it again.
frappe.ui.form.on("Purchase Receipt", {
	after_save(frm) {
		if (frm.doc.docstatus !== 1) return;
		if (frm._mfx_alloc_popup_shown) return;
		frm._mfx_alloc_popup_shown = true;

		frappe.call({
			method: "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.get_pr_mp_allocations",
			args: { pr_name: frm.doc.name },
			callback(r) {
				let allocs = r.message || [];
				// Silence here was the whole difficulty: a receipt whose chain back to a
				// Material Planning is broken allocated nothing, said nothing, and left
				// the plan still showing the material as unavailable. Ask why instead.
				if (!allocs.length) {
					_mfx_pr_report_no_allocation(frm);
					return;
				}

				// Group by Material Planning for a clean display
				let by_mp = {};
				allocs.forEach(function(a) {
					if (!by_mp[a.material_planning]) by_mp[a.material_planning] = [];
					by_mp[a.material_planning].push(a);
				});

				// Allocated is NOT the same as reserved -- allocate_pr_stock_to_mp only
				// places the batch into Available Raw Materials / Material Mapping;
				// reserving it is still a separate, manual step on the Material
				// Planning, and nothing transfers via a Material Issue Plan until that
				// happens (_get_mp_reserved_batches only ever offers is_reserved=1 rows
				// for transfer). Say exactly that instead of claiming it's ready.
				let sections = Object.entries(by_mp).map(function([mp, rows]) {
					let mp_safe = frappe.utils.escape_html(mp);
					let mp_link = `<a href="/app/material-planning/${encodeURIComponent(mp)}" target="_blank"><b>${mp_safe}</b></a>`;
					let row_html = rows.map(function(r) {
						return `<tr>
							<td style="padding:3px 6px">${frappe.utils.escape_html(String(r.batch_no == null ? "" : r.batch_no))}</td>
							<td style="padding:3px 6px">${frappe.utils.escape_html(String(r.item_code == null ? "" : r.item_code))}</td>
							<td style="padding:3px 6px;text-align:right">${flt(r.qty, 3)} Kg</td>
							<td style="padding:3px 6px">${r.is_reserved ? __("Reserved") : __("Not Reserved Yet")}</td>
						</tr>`;
					}).join("");
					return `<p style="margin:10px 0 4px">Material Planning: ${mp_link}</p>
						<table class="table table-bordered table-condensed" style="font-size:11px;margin-bottom:4px">
							<thead><tr>
								<th>${__("Batch No")}</th>
								<th>${__("Item Code")}</th>
								<th>${__("Qty")}</th>
								<th>${__("Status")}</th>
							</tr></thead>
							<tbody>${row_html}</tbody>
						</table>`;
				}).join("");

				let any_unreserved = allocs.some(function(a) { return !a.is_reserved; });
				let mp_names = Object.keys(by_mp);

				// Allocated is not reserved, and only reserved rows are ever offered for
				// transfer -- so the instruction leads rather than trailing the tables in
				// grey. The plan opens from the dialog itself: being told to go and do
				// something is not the same as being able to.
				let lead = any_unreserved
					? `<p style="font-size:13px"><b>${__("Check and reserve these batches.")}</b> ` +
					  __("They were allocated against the Material Planning below, but a batch that is allocated is not yet reserved — and only reserved rows are offered for transfer on a Material Issue Plan.") +
					  `</p><p style="color:#555">${__("Reserve every row and the plan's status moves to <b>Batch Mapping Completed</b> on its own.")}</p>`
					: `<p style="font-size:13px">${__("Received batches were allocated against the Material Planning below, and are already reserved and ready for transfer.")}</p>`;

				let dialog_msg = frappe.msgprint({
					title: any_unreserved
						? __("Batches Allocated — Reserve Them")
						: __("Material Planning — Batches Allocated"),
					indicator: any_unreserved ? "orange" : "green",
					message: lead + sections,
					primary_action: mp_names.length === 1 ? {
						label: __("Open {0}", [mp_names[0]]),
						action() {
							dialog_msg.hide();
							frappe.set_route("Form", "Material Planning", mp_names[0]);
						},
					} : undefined,
				});
			},
		});
	},
});


// ── Allocation into Material Planning: why it did not happen, and how to run it again ──
//
// allocate_pr_stock_to_mp reaches its plan through receipt line -> order line -> request
// line -> the request's own plan. Break any link and the join finds nothing, allocation
// never runs, and until now nothing said so.

function _mfx_pr_report_no_allocation(frm) {
	frappe.call({
		method: "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.diagnose_mp_allocation",
		args: { pr_name: frm.doc.name },
		callback(r) {
			let d = r.message || {};
			// A receipt with no Material Request behind any line is an ordinary purchase,
			// not a planning failure. Saying nothing is right there.
			if (!(d.broken || []).length) return;
			if ((d.plans || []).length) return;

			let rows = d.broken.map(function(b) {
				return `<tr><td style="padding:3px 6px">${frappe.utils.escape_html(String(b[0]))}</td>` +
					`<td style="padding:3px 6px">${frappe.utils.escape_html(String(b[1]))}</td></tr>`;
			}).join("");
			frappe.msgprint({
				title: __("Nothing Allocated to Material Planning"),
				indicator: "orange",
				message: __("These lines do not trace back to a Material Planning, so no batch was allocated into one:") +
					`<table class="table table-bordered table-condensed" style="font-size:11px;margin:8px 0">
						<thead><tr><th>${__("Item")}</th><th>${__("Why")}</th></tr></thead>
						<tbody>${rows}</tbody></table>` +
					__("Allocation follows the chain <b>Receipt line → Purchase Order line → Material Request line → that request's Material Planning</b>. Raise the Purchase Order from the Material Request, and the Material Request from the plan's Unavailable Items, and the batches land in the plan on submit.") +
					"<br><br>" +
					__("If the chain is intact and this is a one-off, use <b>Allocate to Material Planning</b> on this receipt to run it again."),
			});
		},
	});
}

frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		frm.add_custom_button(__("Allocate to Material Planning"), function() {
			frappe.call({
				method: "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.retry_mp_allocation",
				args: { pr_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Allocating…"),
				callback(r) {
					let d = r.message || {};
					if (!(d.plans || []).length) {
						_mfx_pr_report_no_allocation(frm);
						return;
					}
					// filled_mapping counts rows the allocation filled IN PLACE -- Material
					// Mapping rows that were already sitting there waiting for a batch,
					// which is what a plan looks like after a re-check has moved its
					// requirements out of Unavailable Items. Leaving it out of this tally
					// reported "Nothing Left to Allocate" over a run that had just
					// rescued every row on the plan.
					let lines = (d.results || []).map(function(x) {
						let parts = [];
						if (x.added_exact) parts.push(__("{0} into Exact Match", [x.added_exact]));
						if (x.filled_mapping) parts.push(__("{0} filled in Material Mapping", [x.filled_mapping]));
						if (x.added_mapping) parts.push(__("{0} added to Material Mapping", [x.added_mapping]));
						return x.material_planning + ": " + (parts.length ? parts.join(", ") : __("nothing"));
					});
					let none = (d.results || []).every(function(x) {
						return !x.added_exact && !x.added_mapping && !x.filled_mapping;
					});
					frappe.msgprint({
						title: none ? __("Nothing Left to Allocate") : __("Allocated"),
						indicator: none ? "blue" : "green",
						message: (none
							? __("Every requirement these batches cover is already allocated — running it again has nothing left to match.")
							: __("Batches allocated:")) + "<br><br>" + lines.join("<br>"),
					});
				},
			});
		}, __("Material Planning"));
	},
});
