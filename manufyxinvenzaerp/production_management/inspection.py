"""Inspection Call / QC workflow shared by Job Card, Supplier Operation Entry, and
Purchase Receipt.

For Supplier Operation Entry (one document = one operation instance), inspection
applies when the source Process Planning row's Inspection Mandatory checkbox was
set — copied onto the SOE at creation time as `custom_inspection_mandatory`
(client change request Phase 4.3; supersedes the old hardcoded "Fitup
Inspection"/"Final Inspection" operation-name check, which is kept only as
Job Card's fallback below -- Job Card's own inspection hooks are disabled
per Phase 0.4, so that branch is unreachable dead code, not a live path).
Submitting an SOE ("operation completion") only requires that at least one
Inspection Call has been logged for it -- not that the linked Inspection Entry
has reached "Completed" -- since the client wants the QC team notified/engaged
before an operation is marked done, not a full sign-off gate. For Purchase
Receipt (one document = many item lines), inspection is opt-in per Item
(`custom_inspection_required`) and results are recorded per line in Inspection
Entry's `items` child table rather than as a single scalar result; its own gate
is unchanged and still requires `custom_inspection_status == "Completed"`.

Manufacturing/Purchasing logs an Inspection Call Date on the source document
(round-tracked in the shared `custom_inspection_call_log` child table); QC
records the actual result on a separate "Inspection Entry" document, including
its own `status` (Open/Working/Completed) set manually by the inspector before
submitting. On submit, the parent's `custom_inspection_status` simply mirrors
that entry's `status` — it is not independently re-derived from rework/reject
qty, since the inspector's own status choice is authoritative.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

INSPECTION_OPERATIONS = ("Fitup Inspection", "Final Inspection")


# ─── Applicability ────────────────────────────────────────────────────────────

def _inspection_applicable(doc):
	"""Whether the Inspection Call workflow applies to this document at all."""
	if doc.doctype == "Purchase Receipt":
		return any(
			frappe.db.get_value("Item", row.item_code, "custom_inspection_required")
			for row in (doc.items or [])
		)
	if doc.doctype == "Supplier Operation Entry":
		return bool(doc.get("custom_inspection_mandatory"))
	# Job Card only -- dead code path, its inspection hooks are disabled (Phase 0.4).
	return doc.operation in INSPECTION_OPERATIONS


def validate_soe_inspection(doc, method):
	_validate_inspection_call_log(doc)


def validate_purchase_receipt_inspection(doc, method):
	_validate_inspection_call_log(doc)


def _validate_inspection_call_log(doc):
	if not _inspection_applicable(doc):
		return
	for idx, row in enumerate(doc.get("custom_inspection_call_log") or [], start=1):
		if not row.round_no:
			row.round_no = idx


def before_submit_soe_inspection_gate(doc, method):
	_before_submit_inspection_gate(doc)


def _before_submit_inspection_gate(doc):
	if not _inspection_applicable(doc):
		return
	if doc.doctype == "Supplier Operation Entry":
		if not (doc.get("custom_inspection_call_log") or []):
			frappe.throw(
				_("At least one Inspection Call must be created before submitting this {0} for the "
				  "<b>{1}</b> operation.").format(doc.doctype, doc.operation),
				title=_("Inspection Call Required"),
			)
		return
	if (doc.custom_inspection_status or "") != "Completed":
		frappe.throw(
			_("Inspection Status must be <b>Completed</b> before submitting this {0} for the "
			  "<b>{1}</b> operation.").format(doc.doctype, doc.operation),
			title=_("Inspection Not Completed"),
		)


# ─── Whitelisted API (called from supplier_operation_entry.js /
#     purchase_receipt.js) ────────────────────────────────────────────────────

@frappe.whitelist()
def add_inspection_call(source_doctype, source_name, call_date=None):
	"""Log a new inspection call round. `call_date` is normally passed in
	directly (Purchase Receipt's popup-driven flow, which doesn't persist a
	separate call-date field on the document); falls back to the source
	doc's own `custom_inspection_call_date` field for Job Card/SOE. Blocked
	while a round is already logged and not yet Completed.

	For Supplier Operation Entry, also blocked when nothing is actually pending
	inspection yet (inspection_items all at qty_nos 0 -- e.g. everything already
	accepted in a prior round, nothing new logged in the Consumption Log since).
	Without this check, the Operation Entry's "Create Inspection"
	button would add a new Pending round here, then immediately fail in
	create_inspection_entry's own identical check right after -- leaving an
	orphan Pending round with no Inspection Entry that can never be completed
	(nothing is pending) and that then blocks any FUTURE real inspection call too
	(the round-in-progress check above)."""
	doc = _get_source_doc(source_doctype, source_name)

	call_date = call_date or doc.custom_inspection_call_date
	if not call_date:
		frappe.throw(_("Select an Inspection Call Date."))

	existing = doc.get("custom_inspection_call_log") or []
	if any(row.round_status != "Completed" for row in existing):
		frappe.throw(_("Inspection already in progress, complete it to create new inspection."))

	if source_doctype == "Supplier Operation Entry":
		pending_items = [row for row in (doc.get("inspection_items") or []) if flt(row.qty_nos) > 0]
		if not pending_items:
			frappe.throw(_(
				"All items have already completed inspection -- nothing new is pending. "
				"Log more Nos as completed in the Consumption Log first."
			))

	doc.append("custom_inspection_call_log", {
		"round_no": len(existing) + 1,
		"call_date": call_date,
		"round_status": "Pending",
	})
	if doc.custom_inspection_status == "Open":
		doc.custom_inspection_status = "Working"
	doc.save()

	return doc.name


@frappe.whitelist()
def update_inspection_call_date(source_doctype, source_name, call_date):
	"""Update the call date of the most recently logged inspection round, and
	propagate it onto the linked Inspection Entry (if one has been created)."""
	if not call_date:
		frappe.throw(_("Select a date."))

	doc = _get_source_doc(source_doctype, source_name)
	log = doc.get("custom_inspection_call_log") or []
	if not log:
		frappe.throw(_("No inspection call has been logged yet."))

	last_row = log[-1]
	frappe.db.set_value("Inspection Call Log", last_row.name, "call_date", call_date)
	if last_row.inspection_entry:
		frappe.db.set_value("Inspection Entry", last_row.inspection_entry, "call_date", call_date)

	return call_date


@frappe.whitelist()
def create_inspection_entry(source_doctype, source_name):
	"""Create a draft Inspection Entry prefilled from the latest pending
	inspection call round, and link it back onto that round. Returns the new
	Inspection Entry name for the client to route to."""
	doc = _get_source_doc(source_doctype, source_name)

	pending_row = None
	for row in reversed(doc.get("custom_inspection_call_log") or []):
		if row.round_status == "Pending" and not row.inspection_entry:
			pending_row = row
			break
	if not pending_row:
		frappe.throw(_("Click <b>Create Inspection</b> to log a call before creating an Inspection Entry."))

	sales_order, customer = _resolve_traceability(doc)

	entry_data = {
		"doctype": "Inspection Entry",
		"source_doctype": source_doctype,
		"round_no": pending_row.round_no,
		"call_date": pending_row.call_date,
		"sales_order": sales_order,
		"customer": customer,
	}

	if source_doctype == "Purchase Receipt":
		entry_data["purchase_receipt"] = source_name
		entry_data["supplier"] = doc.supplier
		entry_data["items"] = [
			{
				"item_code": row.item_code,
				"qty": row.qty,
				"pr_item_row": row.name,
			}
			for row in doc.items
			if frappe.db.get_value("Item", row.item_code, "custom_inspection_required")
		]
	else:
		if source_doctype == "Job Card":
			work_order = doc.work_order
			production_plan = frappe.db.get_value("Work Order", work_order, "production_plan") if work_order else ""
			subcontracting_order = ""
			supplier = ""
		else:
			work_order = doc.work_order
			production_plan = doc.production_plan
			subcontracting_order = doc.subcontracting_order
			supplier = doc.supplier

		entry_data.update({
			"job_card": source_name if source_doctype == "Job Card" else None,
			"supplier_operation_entry": source_name if source_doctype == "Supplier Operation Entry" else None,
			"operation": doc.operation,
			"work_order": work_order,
			"subcontracting_order": subcontracting_order,
			"production_plan": production_plan,
			"supplier": supplier,
			# An internal operation has a Contractor instead of a Supplier; the entry
			# shows whichever the Operation Entry has.
			"contractor": doc.get("contractor") if source_doctype == "Supplier Operation Entry" else None,
		})

		if source_doctype == "Supplier Operation Entry":
			# Carry over whatever is currently pending in the SOE's own inspection_items
			# (Consumption Log total minus what's already been accepted) as this entry's
			# review rows -- the inspector enters Accepted/Rejected Qty per drawing here
			# instead of one overall Total Checked Qty.
			soe_items = [
				{
					"drawing": row.drawing,
					"customer_drawing_number": row.customer_drawing_number,
					"qty_nos": row.qty_nos,
				}
				for row in (doc.get("inspection_items") or [])
				if flt(row.qty_nos) > 0
			]
			if not soe_items:
				frappe.throw(_("Nothing is pending inspection yet -- log some Nos as completed in the Consumption Log first."))
			entry_data["soe_items"] = soe_items

	entry = frappe.get_doc(entry_data).insert(ignore_mandatory=True)

	frappe.db.set_value("Inspection Call Log", pending_row.name, "inspection_entry", entry.name)

	return entry.name


@frappe.whitelist()
def create_soe_inspection(soe_name, call_date):
	"""The Operation Entry's Create Inspection popup: log the call round for
	`call_date` and create its Inspection Entry, in the one request -- so a refusal
	in the second step (nothing pending, say) rolls the round back with it and can
	never leave an orphan Pending round behind.

	A round already logged without an entry (from before this popup) is reused, with
	the date picked here. A round that already has its entry is refused: that entry is
	where the inspection is finished."""
	if not call_date:
		frappe.throw(_("Select an Inspection Call Date."))

	soe = _get_source_doc("Supplier Operation Entry", soe_name)
	if soe.docstatus != 0:
		frappe.throw(_("Inspection is created while the Operation Entry is still a draft."))

	open_rows = [r for r in (soe.get("custom_inspection_call_log") or []) if r.round_status != "Completed"]
	with_entry = next((r for r in open_rows if r.inspection_entry), None)
	if with_entry:
		frappe.throw(
			_("Inspection {0} is still open -- complete it before creating a new one.").format(
				frappe.bold(with_entry.inspection_entry)),
			title=_("Inspection In Progress"),
		)

	if open_rows:
		frappe.db.set_value("Inspection Call Log", open_rows[-1].name, "call_date", call_date)
	else:
		add_inspection_call("Supplier Operation Entry", soe_name, call_date=call_date)

	return create_inspection_entry("Supplier Operation Entry", soe_name)


def on_submit_inspection_entry(doc, method):
	"""Propagate the QC result back to the parent Job Card/SOE/Purchase Receipt:
	mark the round Completed on the call log, and set the overall Inspection
	Status to whatever the user manually set on this Inspection Entry's own
	`status` field (Open/Working/Completed) — the parent mirrors the entry,
	it does not re-derive Working/Completed on its own from reject/rework
	qty, since the user's own status choice is authoritative. For a Purchase
	Receipt, also push each line's accept/reject qty + remarks down onto
	that Purchase Receipt Item row, and (client change request Phase 6.3) the
	same per-row remarks onto the specific Batch that row's inspection was
	actually about -- Job Card/SOE inspections have no batch concept (they
	concern an in-progress manufacturing operation, not a specific purchased
	material batch), so this only applies to the Purchase Receipt branch."""
	parent_doctype = doc.source_doctype
	if parent_doctype == "Job Card":
		parent_name = doc.job_card
	elif parent_doctype == "Supplier Operation Entry":
		parent_name = doc.supplier_operation_entry
	else:
		parent_name = doc.purchase_receipt
	if not parent_name:
		return

	rows = frappe.get_all(
		"Inspection Call Log",
		filters={"parenttype": parent_doctype, "parent": parent_name, "inspection_entry": doc.name},
		fields=["name"],
		limit=1,
	)
	if not rows:
		return

	if parent_doctype == "Purchase Receipt":
		# Two different remarks are in play and they are not interchangeable.
		#
		# `remarks` below is the DOCUMENT-level summary written onto the Inspection
		# Call Log at the end of this function, and joining every row's note is the
		# right thing there -- it describes the inspection as a whole.
		#
		# A BATCH is different. It gets its own row's note, or the inspector's
		# overall note, and nothing else. It used to fall back to this joined
		# summary, so a batch that passed cleanly was branded with a defect
		# recorded against a different item on the same receipt -- and that text
		# then followed the batch into Material Planning and Stock Entry. Quality
		# traceability saying something untrue is worse than saying nothing.
		remarks = doc.overall_remarks or "; ".join(row.remarks for row in doc.items if row.remarks) or ""
		batch_fallback = doc.overall_remarks or ""
		for row in doc.items:
			if not row.pr_item_row:
				continue
			frappe.db.set_value(
				"Purchase Receipt Item",
				row.pr_item_row,
				{
					"custom_inspection_accepted_qty": flt(row.accept_qty),
					"custom_inspection_rejected_qty": flt(row.reject_qty),
					"custom_inspection_remarks": row.remarks or "",
				},
			)
			for row_batch_no in _resolve_pr_item_batch_nos(row.pr_item_row):
				frappe.db.set_value(
					"Batch", row_batch_no, "custom_batch_remarks",
					row.remarks or batch_fallback,
				)
	elif parent_doctype == "Supplier Operation Entry":
		remarks = doc.overall_remarks or doc.rework_remarks or ""
		_apply_soe_inspection_results(doc)
	else:
		remarks = doc.overall_remarks or doc.rework_remarks or ""

	new_status = doc.status or "Working"

	frappe.db.set_value(
		"Inspection Call Log",
		rows[0].name,
		{"round_status": "Completed", "remarks": remarks},
	)
	frappe.db.set_value(parent_doctype, parent_name, "custom_inspection_status", new_status)
	# inspection_complete_date is set on the Inspection Entry itself at save-time
	# (InspectionEntry._set_inspection_complete_date), not here on submit — it should
	# reflect when Status was actually saved as Completed, not the later submit moment.


# ─── Private helpers ─────────────────────────────────────────────────────────

def _apply_soe_inspection_results(entry):
	"""Add each soe_items row's Accepted Qty onto the source SOE's own Drawing
	Details completed_qty_nos (additive across inspection rounds, keyed by drawing),
	so accepted quantity can proceed to the next operation. Rejected Qty is not
	written anywhere here -- the SOE's own inspection_items table re-derives what's
	still pending on its next save (raw Consumption Log total minus the
	now-updated completed_qty_nos -- see subcontracting._sync_soe_inspection_items),
	so a rejection simply reappears there for rework the moment it's logged again."""
	accept_by_drawing = defaultdict(float)
	for row in (entry.get("soe_items") or []):
		if row.drawing and flt(row.accept_qty) > 0:
			accept_by_drawing[row.drawing] += flt(row.accept_qty)
	if not accept_by_drawing:
		return

	soe = frappe.get_doc("Supplier Operation Entry", entry.supplier_operation_entry)
	changed = False
	for row in (soe.drawing_details or []):
		add = accept_by_drawing.get(row.drawing or "")
		if add:
			row.completed_qty_nos = flt(flt(row.completed_qty_nos) + add, 3)
			changed = True
	if not changed:
		return

	if soe.docstatus == 1:
		# Normally inspection completes while the SOE is still draft -- this only runs
		# if the SOE was already submitted first. A plain doc.save() would hit
		# Frappe's update-after-submit guard on completed_qty_nos, so patch the numbers
		# directly instead and re-run the same propagation on_submit_supplier_operation_entry
		# already does once, by hand.
		from manufyxinvenzaerp.subcontracting_management.subcontracting import (
			_propagate_available_to_next,
			_propagate_drawing_nos_to_next,
			_update_sco_drawing_item_completion,
		)

		for row in soe.drawing_details:
			frappe.db.set_value(
				"SOE Drawing Detail", row.name, "completed_qty_nos", row.completed_qty_nos,
				update_modified=False,
			)
		soe.total_completed_nos = flt(sum(flt(r.completed_qty_nos) for r in soe.drawing_details), 3)
		frappe.db.set_value(
			"Supplier Operation Entry", soe.name, "total_completed_nos", soe.total_completed_nos,
			update_modified=False,
		)
		_propagate_available_to_next(soe)
		_propagate_drawing_nos_to_next(soe)
		_update_sco_drawing_item_completion(soe)
	else:
		soe.save(ignore_permissions=True)


def _resolve_pr_item_batch_nos(pr_item_row):
	"""Batch(es) a Purchase Receipt Item row actually received, for the Batch
	Remarks propagation (client change request Phase 6.3). This site's
	Purchase Receipt Items use the v15 Serial and Batch Bundle model, not the
	older direct `batch_no` column on the row (confirmed empty in practice --
	receiving goes through `serial_and_batch_bundle` -> Serial and Batch
	Entry), so resolve via the bundle's own entries; falls back to the row's
	own `batch_no` first in case a caller ever inserts one directly (e.g.
	`use_serial_batch_fields`). A row can span more than one batch if the
	bundle was split, so returns a list."""
	row = frappe.db.get_value(
		"Purchase Receipt Item", pr_item_row, ["batch_no", "serial_and_batch_bundle"], as_dict=True
	)
	if not row:
		return []
	if row.batch_no:
		return [row.batch_no]
	if row.serial_and_batch_bundle:
		return frappe.get_all(
			"Serial and Batch Entry", filters={"parent": row.serial_and_batch_bundle}, pluck="batch_no"
		)
	return []


def _get_source_doc(source_doctype, source_name):
	if source_doctype not in ("Job Card", "Supplier Operation Entry", "Purchase Receipt"):
		frappe.throw(_("Invalid source doctype {0}").format(source_doctype))

	doc = frappe.get_doc(source_doctype, source_name)
	if not _inspection_applicable(doc):
		if source_doctype == "Purchase Receipt":
			frappe.throw(_("None of the items on this Purchase Receipt require inspection."))
		frappe.throw(
			_("This action is only available for the <b>Fitup Inspection</b> and "
			  "<b>Final Inspection</b> operations.")
		)
	return doc


def _resolve_traceability(doc):
	"""Sales Order + Customer for a Job Card/SOE, via its drawing details
	(both already carry a per-row `sales_order`), falling back to the linked
	Work Order's `sales_order` field. For a Purchase Receipt, via the first
	item row's `custom_sales_order`."""
	if doc.doctype == "Purchase Receipt":
		sales_order = ""
		for row in doc.items or []:
			if row.get("custom_sales_order"):
				sales_order = row.custom_sales_order
				break
		customer = frappe.db.get_value("Sales Order", sales_order, "customer") if sales_order else ""
		return sales_order, customer

	drawing_rows = doc.get("custom_drawing_details") or doc.get("drawing_details") or []
	sales_order = ""
	for row in drawing_rows:
		if row.get("sales_order"):
			sales_order = row.sales_order
			break
	if not sales_order and doc.get("work_order"):
		sales_order = frappe.db.get_value("Work Order", doc.work_order, "sales_order") or ""

	customer = frappe.db.get_value("Sales Order", sales_order, "customer") if sales_order else ""
	return sales_order, customer
