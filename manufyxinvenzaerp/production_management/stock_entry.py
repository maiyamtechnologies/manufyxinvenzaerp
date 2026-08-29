import frappe
from frappe import _
from frappe.utils import flt, now
from manufyxinvenzaerp.utils.decision_log import log_decision
from manufyxinvenzaerp.utils.dimension_formula import calculate_qty
from manufyxinvenzaerp.utils.reference_copy import copy_reference_fields_if_blank

FORMULA_GROUPS = {"Structurals", "Plates"}
REFERENCE_FIELDS = ["custom_drawing", "custom_duno_mark_no", "custom_customer_drawing_number", "custom_sales_order"]


def validate_stock_entry(doc, method):
	"""Recalculate qty for formula-group items. Show popup only when qty was manually edited."""
	for row in doc.items:
		_copy_from_material_request_item(row)

	_sync_batch_remarks(doc)
	validate_consumable_entry(doc)

	# For Manufacture, fill Sec Qty (Nos) on consumed rows proportional to the Kg consumed,
	# so the batch piece count is correctly reduced on submit. Done before totals + stock move.
	if doc.stock_entry_type == "Manufacture":
		_populate_manufacture_sec_qty(doc)

	# Always compute header totals regardless of SE type
	doc.custom_total_qty     = flt(sum(flt(r.qty) for r in doc.items), 3)
	doc.custom_total_sec_qty = flt(sum(flt(r.get("custom_sec_qty") or 0) for r in doc.items), 3)

	if doc.stock_entry_type not in {"Repack", "Material Receipt", "Material Issue"}:
		return

	manually_edited = []
	for row in doc.items:
		group = (row.get("custom_parent_item_group") or "").strip()
		if group not in FORMULA_GROUPS:
			continue
		formula_qty = flt(_calc_qty(row, group), 3)
		if not formula_qty:
			continue
		if flt(row.qty, 3) != formula_qty:
			manually_edited.append(row.item_code)
		row.qty = formula_qty

	if manually_edited:
		frappe.msgprint(
			_("Quantities for Structurals/Plates have been recalculated from dimensions."),
			indicator="orange",
		)


def _sync_batch_remarks(doc):
	"""Mirror each item row's assigned batch's own Batch Remarks (client
	change request Phase 6.3) onto its own custom_batch_remarks field.
	Applies to every Stock Entry type (not gated by the Structurals/Plates
	FORMULA_GROUPS check below, which is unrelated) -- one bulk query
	regardless of row count."""
	batch_nos = {r.batch_no for r in doc.items if r.get("batch_no")}
	if not batch_nos:
		return
	remarks_by_batch = dict(frappe.get_all(
		"Batch", filters={"name": ["in", list(batch_nos)]},
		fields=["name", "custom_batch_remarks"], as_list=True,
	))
	for row in doc.items:
		if row.get("batch_no"):
			row.custom_batch_remarks = remarks_by_batch.get(row.batch_no) or ""


def _copy_from_material_request_item(row):
	"""Copy drawing/DUNO/sales order references from the linked MR Item, same
	pattern as Purchase Order's/Purchase Receipt's _copy_from_mr_item -- covers
	the standard "Make Stock Entry" flow from a Material Request (client change
	request Phase 1.3). Project is already a core field on Stock Entry Detail
	so it needs no custom field, but core "Make" flows don't map it forward on
	their own -- copy it here too."""
	copy_reference_fields_if_blank(row, "Material Request Item", "material_request_item", REFERENCE_FIELDS)
	if not row.get("project") and row.get("material_request_item"):
		row.project = frappe.db.get_value("Material Request Item", row.material_request_item, "project")


def _refresh_sco_status_for_final_entry(doc):
	"""The Material Issue Plan's final ('Manufacture') Stock Entry is what finishes a
	Job Work Order -- submitting it puts the finished goods in stock, cancelling it
	takes them back out. Re-derive the order's status either way rather than latching
	it, so a cancelled final entry drops the order back to Working on its own.

	Transfers raised from the Material Issue Plan ('Send to Subcontractor' /
	'Material Transfer', tagged with custom_sco_ref) count here too: they are what
	STARTS a job, and are the point the Production Plan stops being Not Started --
	whether or not any operation has been logged against it yet. refresh_sco_status
	carries the plan along with the order."""
	sco_ref = doc.get("subcontracting_order") or doc.get("custom_sco_ref")
	if not sco_ref:
		return
	from manufyxinvenzaerp.subcontracting_management.overrides import refresh_sco_status

	refresh_sco_status(sco_ref)


def on_submit_stock_entry(doc, method):
	"""Reduce custom_sec_qty on batch for consumed items
	(Material Issue + Repack/Manufacture source rows)."""
	_refresh_sco_status_for_final_entry(doc)

	if doc.stock_entry_type == "Material Issue":
		for row in doc.items:
			if row.batch_no and flt(row.get("custom_sec_qty")):
				_reduce_batch_sec_qty(row.batch_no, row.custom_sec_qty)

	elif doc.stock_entry_type in ("Repack", "Manufacture"):
		# Consumed raw-material rows have a source warehouse and are not the
		# produced item; this excludes finished goods and scrap (received rows).
		for row in doc.items:
			if (
				row.s_warehouse
				and not row.is_finished_item
				and row.batch_no
				and flt(row.get("custom_sec_qty"))
			):
				_reduce_batch_sec_qty(row.batch_no, row.custom_sec_qty)

	elif doc.stock_entry_type == "Material Receipt":
		# Off-cuts coming back from a Return Excess Entry may already be spoken for:
		# another job can claim one through Excess Material Mapping's virtual picker
		# while it is still physically at the supplier. Collected here and reported
		# once at the end, so the user learns the paper reservation just became real.
		from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
			materialize_virtual_excess_claim,
		)

		materialized = []
		for row in doc.items:
			batch_nos = set()
			if row.batch_no:
				batch_nos.add(row.batch_no)
			# serial_and_batch_bundle is written via db_set during on_submit,
			# so the in-memory row won't have it — read fresh from DB
			bundle = frappe.db.get_value("Stock Entry Detail", row.name, "serial_and_batch_bundle")
			if bundle:
				entries = frappe.get_all(
					"Serial and Batch Entry",
					filters={"parent": bundle},
					fields=["batch_no"],
				)
				batch_nos.update(e.batch_no for e in entries if e.batch_no)
			if not batch_nos:
				continue
			updates = {}
			if row.get("custom_supplier"):
				updates["supplier"] = row.custom_supplier
			group = (row.get("custom_parent_item_group") or "").strip()
			if group in FORMULA_GROUPS:
				if row.get("custom_existing_supplier_invoice_no"):
					updates["custom_existing_supplier_invoice_no"] = row.custom_existing_supplier_invoice_no
				if row.get("custom_existing_invoice_wt"):
					updates["custom_existing_invoice_wt"] = row.custom_existing_invoice_wt
				if row.get("custom_existing_inward_date"):
					updates["custom_existing_inward_date"] = row.custom_existing_inward_date
			excess_row = row.get("custom_source_mip_excess_row")
			for batch_no in batch_nos:
				if updates:
					frappe.db.set_value("Batch", batch_no, updates)
				if excess_row:
					mp_name = materialize_virtual_excess_claim(excess_row, batch_no)
					if mp_name:
						materialized.append((batch_no, mp_name))

		if materialized:
			frappe.msgprint(
				_("These returned off-cuts were already reserved and are now backed by a real batch:")
				+ "<br>" + "<br>".join(
					_("Batch {0} → {1}").format(frappe.bold(b), frappe.utils.get_link_to_form("Material Planning", m))
					for b, m in materialized
				),
				title=_("Excess Claims Fulfilled"),
				indicator="green",
			)

	# Release reservations for all consumed batches
	_release_material_planning_reservations(doc)

	# Cut Sheet doctype: the sheet is cut the moment the first piece leaves, so its
	# balance goes onto the batch now (see _apply_cut_sheet_w2).
	_apply_cut_sheet_w2(doc)

	# When materials are sent to supplier (or routed via CNC warehouse), update SCO weight fields.
	# We track via custom_sco_ref (not the standard subcontracting_order) to avoid
	# ERPNext's validate_subcontract_order which throws when supplied_items is empty.
	if doc.stock_entry_type == "Send to Subcontractor" and doc.get("custom_sco_ref"):
		_update_sco_transferred_weight(doc.custom_sco_ref)
		_refresh_linked_mip_weight(sco_ref=doc.custom_sco_ref)

	if doc.stock_entry_type == "Material Transfer" and doc.get("custom_sco_ref"):
		_update_sco_transferred_weight(doc.custom_sco_ref)
		_update_sco_cnc_weight(doc.custom_sco_ref)
		_refresh_linked_mip_weight(sco_ref=doc.custom_sco_ref)

	# SHARED_SCO_JC: WO transfer tracking mirrors SCO tracking above.
	# custom_wo_ref is set on Material Transfer SEs created by our WO transfer buttons.
	if doc.stock_entry_type == "Material Transfer" and doc.get("custom_wo_ref"):
		_update_wo_transferred_weight(doc.custom_wo_ref)
		_update_wo_cnc_weight(doc.custom_wo_ref)
		_refresh_linked_mip_weight(wo_ref=doc.custom_wo_ref)

	# Finished-goods receipt (create_finished_goods_entry's "Make Final Stock Entry"
	# button) -- re-saving the linked MIP here is what actually triggers its own
	# validate()'s _maybe_mark_completed check now that FG stock has been received;
	# the MIP is otherwise never touched by this Stock Entry at all.
	if doc.stock_entry_type == "Manufacture" and doc.get("subcontracting_order"):
		_refresh_linked_mip_weight(sco_ref=doc.subcontracting_order)


def _reduce_batch_sec_qty(batch_no, consumed_qty):
	"""Take `consumed_qty` pieces off the batch, atomically.

	This used to read the figure, subtract in Python, and write it back. Two
	entries consuming the same batch at once both read the same starting value and
	the second write discarded the first: 10 - 3 and 10 - 4 submitted together
	leave 6, not 3. The batch's piece count then drifts permanently, and it is what
	every later transfer's proportional Sec Qty and every cut sheet's sizing are
	worked out from.

	Doing the arithmetic in the UPDATE means the database serialises the two, so
	each subtraction is applied to whatever the other left behind.

	The restore path on cancel passes a NEGATIVE quantity to add the pieces back,
	and subtracting a negative works the same way here -- both directions go
	through this one statement so they cannot drift apart.
	"""
	frappe.db.sql(
		"""UPDATE `tabBatch`
		   SET custom_sec_qty = ROUND(COALESCE(custom_sec_qty, 0) - %s, 3)
		   WHERE name = %s""",
		(flt(consumed_qty, 3), batch_no),
	)


# A cut is treated as finished once this much of its To Use (W1) weight has moved.
_CUT_SHEET_TOLERANCE_KG = 0.01


def _apply_cut_sheet_w2(doc, cancelling=False):
	"""Write each Cut Sheet's balance onto its batch on the FIRST transfer taken from
	that sheet, and take it back off if that transfer is cancelled.

	The trigger is the first transfer rather than the last, because that is when the
	sheet is physically cut: from that moment the plate in the rack IS the remnant,
	even though other jobs have not collected their pieces yet. Those pieces are still
	theirs -- the Cut Sheet keeps track of them independently of the batch's size.

	Which sheets this entry touched is read from the Material Planning rows behind it,
	since cancelling clears batch_no off the Stock Entry's own rows."""
	from manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet import (
		apply_w2_to_batch, revert_w2_from_batch,
	)

	mip_name = doc.get("custom_mip_ref")
	if not mip_name:
		return

	item_codes = {row.item_code for row in doc.items if row.item_code}
	if not item_codes:
		return

	mp_names = {r.material_planning for r in frappe.get_all(
		"Material Issue Plan Raw Material", filters={"parent": mip_name},
		fields=["material_planning"]) if r.material_planning}
	if not mp_names:
		return

	cut_sheets = {r.cut_sheet_ref for r in frappe.get_all(
		"Material Planning Material Mapping",
		filters={"parent": ["in", list(mp_names)], "item_code": ["in", list(item_codes)],
		         "cut_sheet_ref": ["!=", ""]},
		fields=["cut_sheet_ref"]) if r.cut_sheet_ref}

	for cs_name in cut_sheets:
		if not frappe.db.exists("Cut Sheet", cs_name):
			continue
		if cancelling:
			# Only undo what THIS entry did; another transfer may have been the one
			# that cut the sheet, and its write-back must stand.
			if frappe.db.get_value("Cut Sheet", cs_name, "w2_applied_stock_entry") == doc.name:
				revert_w2_from_batch(cs_name)
		elif _cut_sheet_creates_new_batch():
			_apply_cut_sheet_w2_as_new_batch(cs_name, doc.name)
		else:
			apply_w2_to_batch(cs_name, doc.name)


def _apply_cut_sheet_w2_as_new_batch(cut_sheet_name, stock_entry):
	"""New-batch mode for the Cut Sheet doctype (see _cut_sheet_creates_new_batch).

	Unlike the in-place version this cannot fire on the FIRST transfer. Emptying the
	batch while other jobs still have pieces to collect would take the plate out from
	under them, so it waits until everything the sheet promised has left the warehouse.
	Where a sheet is cut for one job -- the client's own worked example -- the first
	transfer is also the last, and the two versions fire at the same moment.

	If the repack cannot be made for any reason, the transfer that triggered it must
	still stand: the attempt is rolled back to a savepoint and the balance is written
	onto the batch the old way, with a message saying so."""
	from manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet import (
		apply_w2_to_batch,
	)

	cs = frappe.get_doc("Cut Sheet", cut_sheet_name)
	if cs.w2_applied or not cs.batch_no:
		return False
	if not (flt(cs.w2_length) or flt(cs.w2_width) or flt(cs.w2_sec_qty)):
		# No balance was planned -- the sheet is used up rather than leaving a remnant.
		return False

	remaining = flt(sum(flt(r.qty) for r in _batch_stock_by_warehouse(cs.batch_no)), 3)
	if remaining - flt(cs.w2_calc_qty) > _CUT_SHEET_TOLERANCE_KG:
		return False  # pieces still to be issued; the plate is not a remnant yet

	savepoint = "mfx_cut_sheet_repack"
	frappe.db.savepoint(savepoint)
	try:
		repack, new_batch = _repack_remnant_to_new_batch(
			cs.batch_no,
			{"length": cs.w2_length, "width": cs.w2_width, "sec_qty": cs.w2_sec_qty},
			cs.name,
		)
	except Exception as e:
		frappe.db.rollback(save_point=savepoint)
		frappe.msgprint(
			_("The balance of {0} could not be moved into a new batch ({1}), so batch {2} "
			  "has been resized in place instead.").format(cs.name, str(e), cs.batch_no),
			title=_("Cut Sheet Balance"), indicator="orange",
		)
		return apply_w2_to_batch(cut_sheet_name, stock_entry)

	frappe.db.set_value("Cut Sheet", cs.name, {
		"w2_applied": 1,
		"w2_applied_stock_entry": stock_entry,
		"w2_applied_on": now(),
		"w2_repack_entry": repack,
		"w2_batch_no": new_batch,
		"status": "Consumed",
	}, update_modified=False)
	log_decision(
		"Cut Sheet Balance",
		reference_doctype="Cut Sheet",
		reference_name=cs.name,
		item_code=cs.item_code,
		batch_no=cs.batch_no,
		new_batch_no=new_batch,
		previous_sec_qty=flt(cs.sheet_sec_qty),
		sec_qty=flt(cs.w2_sec_qty),
		qty=flt(cs.w2_calc_qty),
		details=_("Batch {0} emptied into new batch {1} carrying the balance ({2})." ).format(
			cs.batch_no, new_batch, repack),
	)
	frappe.msgprint(
		_("Batch {0} was cut per {1}. Its balance is now batch {2} ({3}).").format(
			frappe.bold(cs.batch_no), cs.name, frappe.bold(new_batch),
			frappe.utils.get_link_to_form("Stock Entry", repack)),
		title=_("Cut Sheet Balance"), indicator="green",
	)
	return True


def _cut_sheet_creates_new_batch():
	"""Manufyxinvenza Settings -> "Create New Batch for Cut Sheet Stock Entry".

	Off, which is how every site behaves today: the sheet's own batch is rewritten to
	the Balance (W2) dimensions once the cut has been transferred -- same batch, same
	name, new size. On: the batch is never rewritten. A Repack empties it into a NEW
	batch carrying W2, so a document already issued against the original still reads
	true, and the old name no longer describes something that is not there any more."""
	return bool(frappe.db.get_single_value(
		"Manufyxinvenza Settings", "create_new_batch_for_cut_sheet_stock_entry"
	))


def _batch_stock_by_warehouse(batch_no):
	"""Where a batch's stock physically sits and how much, from submitted bundles.

	Warehouse by warehouse rather than one total: a Repack has to name the warehouse
	it works in, and a plate that somehow sits in two places is not something to
	guess at."""
	return frappe.db.sql(
		"""
		SELECT sbe.warehouse AS warehouse, COALESCE(SUM(sbe.qty), 0) AS qty
		FROM `tabSerial and Batch Entry` sbe
		JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
		WHERE sbe.batch_no = %s AND sbb.docstatus = 1
		GROUP BY sbe.warehouse
		HAVING COALESCE(SUM(sbe.qty), 0) > %s
		""",
		(batch_no, _CUT_SHEET_TOLERANCE_KG),
		as_dict=True,
	)


def _repack_remnant_to_new_batch(batch_no, w2, source_label):
	"""Empty `batch_no` into a NEW batch carrying the balance (W2) dimensions.

	`w2` is {"length", "width", "sec_qty"} -- the off-cut's shape, entered by hand.
	Thickness, item and unit weight come from the batch and its item, since cutting
	changes length and width only.

	Two rows, one Repack:

	  out  the whole of what is physically left of the old batch. Its quantity is a
	       ledger fact, not a formula result, so the row deliberately carries NO
	       dimensions: validate_stock_entry recomputes qty from Length x Sec Qty for
	       Structurals and Plates, and with the plate's own 12000 mm on the row it
	       would try to move a full sheet that is no longer there. It does carry the
	       piece count, so the emptied batch drops to zero pieces -- and gets them
	       back if this is ever cancelled.
	  in   the balance, with W2's dimensions and Sec Qty. This row DOES carry its
	       group, so validate_stock_entry computes its Kg from those dimensions --
	       which is exactly the guarantee wanted: the new batch's size, piece count
	       and weight cannot disagree with each other.

	The difference between the two is the saw-cut loss, and a Repack absorbs it by
	design -- in and out are not required to match. That is what removes the rounding
	question the in-place version left open.

	Returns (stock_entry_name, new_batch_no). Raises on anything it will not guess at;
	callers run it inside a savepoint and fall back to rewriting the batch in place."""
	batch = frappe.db.get_value(
		"Batch", batch_no,
		["item", "custom_thickness", "custom_sec_qty", "custom_length", "custom_width"],
		as_dict=True,
	)
	if not batch or not batch.item:
		raise ValueError("Batch %s no longer exists" % batch_no)

	item = frappe.db.get_value(
		"Item", batch.item, ["custom_unit_weight", "custom_parent_item_group"], as_dict=True
	) or frappe._dict()

	stock = _batch_stock_by_warehouse(batch_no)
	if not stock:
		raise ValueError("Batch %s holds no stock to repack" % batch_no)
	if len(stock) > 1:
		raise ValueError(
			"Batch %s is spread across %d warehouses; a cut sheet's plate is expected in one"
			% (batch_no, len(stock))
		)

	warehouse = stock[0].warehouse
	remaining = flt(stock[0].qty, 3)

	group = (item.custom_parent_item_group or "").strip()
	unit_weight = flt(item.custom_unit_weight)
	w2_kg = flt(calculate_qty(
		group, flt(w2.get("length")), flt(w2.get("width")),
		flt(batch.custom_thickness), unit_weight, flt(w2.get("sec_qty")),
	) or 0, 3)
	if w2_kg <= _CUT_SHEET_TOLERANCE_KG:
		raise ValueError("No balance left on batch %s to carry into a new batch" % batch_no)
	if w2_kg - remaining > _CUT_SHEET_TOLERANCE_KG:
		raise ValueError(
			"Balance of %s Kg is more than the %s Kg still in %s"
			% (w2_kg, remaining, batch_no)
		)

	se = frappe.get_doc({
		"doctype": "Stock Entry",
		"stock_entry_type": "Repack",
		# Named from the warehouse rather than left to the site's default company.
		# They are the same thing on a single-company site and not on any other, and
		# when they differ ERPNext refuses the entry -- "Warehouse X does not belong
		# to company Y" -- which this would have answered by quietly resizing the
		# batch in place instead, the very thing the switch was turned on to avoid.
		"company": frappe.db.get_value("Warehouse", warehouse, "company"),
		"remarks": _("Cut Sheet balance ({0}): batch {1} repacked into its off-cut")
			.format(source_label, batch_no),
		"items": [
			{
				"item_code": batch.item,
				"qty": remaining,
				"s_warehouse": warehouse,
				"batch_no": batch_no,
				"custom_sec_qty": flt(batch.custom_sec_qty),
				"custom_unit_weight": unit_weight,
			},
			{
				"item_code": batch.item,
				"qty": w2_kg,
				"t_warehouse": warehouse,
				"is_finished_item": 1,
				"custom_parent_item_group": group,
				"custom_unit_weight": unit_weight,
				"custom_length": flt(w2.get("length")),
				"custom_width": flt(w2.get("width")),
				"custom_thickness": flt(batch.custom_thickness),
				"custom_sec_qty": flt(w2.get("sec_qty")),
			},
		],
	})
	# This entry moves a batch into its own off-cut. It is not a consumption, so the
	# reservations standing on that batch must survive it -- they are re-pointed at the
	# new batch below instead. The flag rides on the document object we submit, which is
	# the same object the on_submit hook is handed.
	se.flags.mfx_cut_sheet_repack = True
	se.insert(ignore_permissions=True)
	se.submit()

	new_batch = frappe.db.get_value(
		"Batch", {"reference_doctype": "Stock Entry", "reference_name": se.name}, "name"
	)
	if not new_batch:
		raise ValueError("Repack %s created no batch for the balance" % se.name)

	_repoint_reservations(batch_no, new_batch)
	return se.name, new_batch


def _repoint_reservations(old_batch, new_batch):
	"""Move any live reservation from the emptied batch onto the one that now holds
	the steel. Without this a row would go on reserving a batch with nothing in it --
	the in-place version never needed it, because there the name never changed."""
	moved = 0
	for child_dt, batch_field in (
		("Material Planning Material Mapping", "batch"),
		("Material Planning Available Raw Material", "batch_no"),
	):
		for name in frappe.get_all(
			child_dt, filters={batch_field: old_batch, "is_reserved": 1}, pluck="name"
		):
			frappe.db.set_value(child_dt, name, batch_field, new_batch, update_modified=False)
			moved += 1
	return moved


def _cancel_cut_sheet_repack(se_name, old_batch):
	"""Undo a balance repack when the transfer that triggered it is cancelled.

	`old_batch` is passed in rather than read back off the entry: cancelling clears
	batch_no from every row, so by the time this matters the document no longer says
	which batch it emptied."""
	if not se_name or not frappe.db.exists("Stock Entry", se_name):
		return False
	se = frappe.get_doc("Stock Entry", se_name)
	if se.docstatus != 1:
		return False

	new_batch = frappe.db.get_value(
		"Batch", {"reference_doctype": "Stock Entry", "reference_name": se.name}, "name"
	)
	if new_batch:
		# Anything taken out of the balance batch since means this cannot be unwound
		# quietly: say so here rather than let the cancellation fail on negative stock.
		out = flt(frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sbe.qty), 0)
			FROM `tabSerial and Batch Entry` sbe
			JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
			WHERE sbe.batch_no = %s AND sbb.docstatus = 1 AND sbe.qty < 0
			""",
			new_batch,
		)[0][0])
		if out:
			frappe.throw(
				_("Balance batch {0} has already been used, so the cut cannot be undone. "
				  "Reverse whatever consumed it first.").format(new_batch)
			)
		if old_batch:
			_repoint_reservations(new_batch, old_batch)

	se.cancel()
	return True


def _batch_total_kg_all_wh(batch_no):
	"""Total net stock (Kg) of a batch across all warehouses (submitted SBBs)."""
	return flt(frappe.db.sql(
		"""
		SELECT COALESCE(SUM(sbe.qty), 0)
		FROM `tabSerial and Batch Entry` sbe
		JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
		WHERE sbe.batch_no = %s AND sbb.docstatus = 1
		""",
		batch_no,
	)[0][0])


def _populate_manufacture_sec_qty(doc):
	"""Set custom_sec_qty (Nos) on Manufacture consumed rows in proportion to the Kg consumed.

	A consumed row removes consumed_kg from a batch that holds custom_sec_qty pieces across
	its total stock — so the pieces consumed = total_sec * consumed_kg / total_kg. Computed at
	validate (before stock moves) so on_submit can decrement the batch and on_cancel reverse it.
	Existing non-zero values are respected (manual entry / re-validate).
	"""
	for row in doc.items:
		if not (row.s_warehouse and not row.is_finished_item and row.batch_no):
			continue
		if flt(row.get("custom_sec_qty")):
			continue
		total_kg = _batch_total_kg_all_wh(row.batch_no)
		if not total_kg:
			continue
		total_sec = flt(frappe.db.get_value("Batch", row.batch_no, "custom_sec_qty"))
		if not total_sec:
			continue
		row.custom_sec_qty = flt(total_sec * (flt(row.qty) / total_kg), 3)


# Stock Entry types that move reserved material out of the warehouse it was reserved
# in, and therefore release (on submit) or restore (on cancel) the Material Planning
# reservations behind it. One constant so the two stay in step -- a type released on
# submit but not restored on cancel would strand the reservation.
#
# 'Send to Subcontractor' was missing from this list, which mattered more than the rest
# put together: it is THE primary transfer in this app's flow, moving reserved material
# from Stores to the supplier. The main path released nothing, so batches stayed
# reserved after their stock had physically gone and their free qty was under-reported
# to every later plan.
RESERVATION_RELEASING_SE_TYPES = {
	"Manufacture", "Material Transfer", "Material Issue", "Repack", "Send to Subcontractor",
}


def _linked_material_plannings(doc):
	"""Material Planning docs whose reservations belong to this consumption.

	Traced via Work Order → Production Plan → po_items.custom_material_planning, plus any
	direct custom_production_plan on the Stock Entry. Used to scope reservation release so a
	shared batch reserved by *other* MPs is never wrongly un-reserved.
	Empty set => caller falls back to legacy batch-wide (all-MP) behaviour.
	"""
	pp_names = set()
	wo = doc.get("work_order")
	if wo:
		pp = frappe.db.get_value("Work Order", wo, "production_plan")
		if pp:
			pp_names.add(pp)
	if doc.get("custom_production_plan"):
		pp_names.add(doc.get("custom_production_plan"))
	if doc.get("custom_mip_ref"):
		pp = frappe.db.get_value("Material Issue Plan", doc.get("custom_mip_ref"), "production_plan")
		if pp:
			pp_names.add(pp)
	# Also via the Subcontracting Order, on either field. The finished-goods entry
	# (create_finished_goods_entry) sets only the core `subcontracting_order` -- no
	# custom_mip_ref, no custom_sco_ref -- so without this it resolves to nothing and
	# the caller drops to the legacy fallback, which releases Material Mapping rows and
	# silently leaves every exact-match reservation held forever.
	for fieldname in ("custom_sco_ref", "subcontracting_order"):
		sco = doc.get(fieldname)
		if not sco:
			continue
		pp = frappe.db.get_value("Subcontracting Order", sco, "custom_production_plan")
		if pp:
			pp_names.add(pp)

	mps = set()
	for pp in pp_names:
		for mp in frappe.get_all(
			"Production Plan Item", filters={"parent": pp}, pluck="custom_material_planning"
		):
			if mp:
				mps.add(mp)
	return mps


_RESERVATION_EPSILON = 0.001


def _consumed_qty_by_batch(doc):
	"""How much of each batch this entry moved OUT, batch by batch.

	Only the outward side counts. A transfer carries the same batch twice -- out of
	the source warehouse and into the target -- and summing both would net to nothing,
	so the bundles are filtered to Outward. That is also the side the reservation was
	held against: the material stopped being available in the warehouse it was
	reserved in, which is the whole reason the reservation moves.

	Falls back to the rows' own batch_no where no bundle exists, for entries simple
	enough not to have one. Cancelled bundles are included deliberately -- on cancel
	that is the only record left of what moved."""
	moved = {}
	voucher_no = getattr(doc, "name", None)
	if voucher_no:
		for r in frappe.db.sql(
			"""
			SELECT sbe.batch_no AS batch_no, COALESCE(SUM(ABS(sbe.qty)), 0) AS qty
			FROM `tabSerial and Batch Entry` sbe
			JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
			WHERE sbb.voucher_no = %s
			  AND sbb.type_of_transaction = 'Outward'
			  AND sbe.batch_no IS NOT NULL
			GROUP BY sbe.batch_no
			""",
			voucher_no,
			as_dict=True,
		):
			moved[r.batch_no] = flt(flt(moved.get(r.batch_no, 0)) + flt(r.qty), 3)

	if not moved:
		for row in doc.items:
			if row.batch_no and not row.get("is_finished_item") and row.get("s_warehouse"):
				moved[row.batch_no] = flt(flt(moved.get(row.batch_no, 0)) + flt(row.qty), 3)

	return moved


def _reservation_rows(child_dt, batch_field, batch_no, extra_filters, fields):
	"""Rows reserving one batch, in the order they will give it up.

	Document order, then row order -- the same sequential rule used when a
	consolidated receipt is shared out. It matters that it is an order at all: spread
	a partial transfer proportionally across every row and each one is left holding a
	fraction it can never transfer cleanly, where filling one row at a time leaves
	whole reservations behind and the shortfall lands on the last."""
	filters = dict(extra_filters or {})
	filters[batch_field] = batch_no
	return frappe.get_all(
		child_dt, filters=filters, fields=fields, order_by="parent asc, idx asc"
	)


def _release_rows_by_qty(child_dt, rows, moved_qty, se_is_cnc_transfer):
	"""Take `moved_qty` Kg off these rows' reservations, one row at a time.

	A row gives up only what actually left. Where that covers its whole reservation
	the row is released outright; where it covers part, the row keeps the remainder
	and stays reserved, so a half-finished transfer no longer hands the other half
	back to the free pool.

	Returns (rows_released, rows_reduced) for the caller to report."""
	cleared = {"is_reserved": 0, "reserved_qty": 0, "shortfall_qty": 0, "reserved_on": None}
	remaining = flt(moved_qty, 3)
	released = reduced = 0

	for r in rows:
		if r.get("cnc_process") and not se_is_cnc_transfer:
			continue  # preserve CNC reservations when submitting a non-CNC SE
		held = flt(r.get("reserved_qty"), 3)
		if held <= _RESERVATION_EPSILON:
			# Reserved but holding nothing -- there is no quantity to reduce, so the
			# flag is simply cleared and nothing is charged against what moved.
			frappe.db.set_value(child_dt, r.name, cleared, update_modified=False)
			released += 1
			continue
		if remaining <= _RESERVATION_EPSILON:
			break
		take = min(held, remaining)
		left = flt(held - take, 3)
		if left <= _RESERVATION_EPSILON:
			frappe.db.set_value(child_dt, r.name, cleared, update_modified=False)
			released += 1
		else:
			frappe.db.set_value(child_dt, r.name, {"reserved_qty": left}, update_modified=False)
			reduced += 1
		remaining = flt(remaining - take, 3)

	return released, reduced


def _restore_rows_by_qty(child_dt, rows, moved_qty, qty_field):
	"""Put `moved_qty` Kg back, filling each row up to what it originally needed.

	The mirror image of _release_rows_by_qty, and deliberately in the OPPOSITE order:
	releasing fills from the front, so unwinding from the back returns the steel to
	the rows that gave it up, in the order they gave it. Cancelling the most recent
	transfer -- much the commonest case -- then lands exactly where it started.

	Cancel an older transfer while a later one still stands and the total is still
	right to the kilo, but it can come back on the wrong row of a shared batch. Making
	that exact as well would mean recording what every row gave up to every entry;
	the aggregate is what the free-stock figures are computed from, so the trade is
	worth naming rather than paying for.

	Restoring each row to its full requirement regardless -- which is what this used
	to do -- gave back more than was ever released whenever two transfers had been
	made and only one was cancelled."""
	remaining = flt(moved_qty, 3)
	restored = 0

	for r in reversed(rows):
		if remaining <= _RESERVATION_EPSILON:
			break
		full = flt(r.get(qty_field), 3)
		held = flt(r.get("reserved_qty"), 3) if r.get("is_reserved") else 0.0
		room = flt(full - held, 3)
		if room <= _RESERVATION_EPSILON:
			continue
		give = min(room, remaining)
		frappe.db.set_value(
			child_dt, r.name,
			{"is_reserved": 1, "reserved_qty": flt(held + give, 3),
			 "shortfall_qty": 0, "reserved_on": now()},
			update_modified=False,
		)
		remaining = flt(remaining - give, 3)
		restored += 1

	return restored


def _release_material_planning_reservations(doc):
	"""
	After a consumption Stock Entry is submitted, clear is_reserved on the Material Planning
	rows (both Material Mapping and Available Raw Material) whose batch was consumed — so the
	reserved qty no longer subtracts from free stock once the material is gone.

	Scoped to the Material Plannings linked to this consumption (via Work Order/Production Plan)
	so a batch shared with other MPs keeps those other reservations intact. When no link can be
	resolved, falls back to the legacy batch-wide behaviour on the Material Mapping table.
	"""
	if doc.stock_entry_type not in RESERVATION_RELEASING_SE_TYPES:
		return

	# A Cut Sheet balance repack empties a batch into its own off-cut. Nothing is
	# consumed, so every reservation standing on it is still owed material --
	# _repack_remnant_to_new_batch re-points them at the new batch itself.
	if doc.flags.get("mfx_cut_sheet_repack"):
		return

	moved_by_batch = _consumed_qty_by_batch(doc)
	if not moved_by_batch:
		return

	linked_mps = _linked_material_plannings(doc)
	fields = ["name", "idx", "parent", "cnc_process", "reserved_qty"]

	if linked_mps:
		# When a primary (non-CNC) SE is submitted, preserve CNC row reservations so
		# the CNC transfer can still run without needing to re-reserve. Only clear CNC
		# reservations if this SE itself is a CNC-destined transfer.
		cnc_warehouse = None
		if doc.get("custom_mip_ref"):
			cnc_warehouse = frappe.db.get_value(
				"Material Issue Plan", doc.get("custom_mip_ref"), "cnc_warehouse"
			)
		se_is_cnc_transfer = bool(
			cnc_warehouse and any(getattr(item, "t_warehouse", None) == cnc_warehouse for item in doc.items)
		)

		# Scoped release: only this consumption's own MP reservations, on both tables.
		for batch_no, moved in moved_by_batch.items():
			for child_dt, batch_field in (
				("Material Planning Material Mapping", "batch"),
				("Material Planning Available Raw Material", "batch_no"),
			):
				rows = _reservation_rows(
					child_dt, batch_field, batch_no,
					{"parent": ["in", list(linked_mps)], "is_reserved": 1}, fields,
				)
				if rows:
					_release_rows_by_qty(child_dt, rows, moved, se_is_cnc_transfer)
		return

	# Fallback (no Production Plan link): batch-wide release across BOTH tables.
	# It used to cover Material Mapping only, so an exact-match reservation whose entry
	# could not be traced to a plan stayed held forever, and the batch's free qty was
	# under-reported to every later plan even though its stock had gone.
	for batch_no, moved in moved_by_batch.items():
		for child_dt, batch_field in (
			("Material Planning Material Mapping", "batch"),
			("Material Planning Available Raw Material", "batch_no"),
		):
			rows = _reservation_rows(child_dt, batch_field, batch_no, {"is_reserved": 1}, fields)
			if rows:
				_release_rows_by_qty(child_dt, rows, moved, True)


def _refresh_linked_mip_weight(sco_ref=None, wo_ref=None):
	"""After SE submit/cancel, refresh the transferred_weight_kg on the linked MIP."""
	from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
		refresh_weight_summary,
	)
	try:
		if sco_ref:
			mip_name = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": sco_ref})
		elif wo_ref:
			mip_name = frappe.db.get_value("Material Issue Plan", {"work_order": wo_ref})
		else:
			return
		if mip_name:
			refresh_weight_summary(mip_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "MIP weight refresh failed")
		# Report 3 Finding H-02 / Phase 1 HP-04: surface this to the submitting
		# user instead of only recording it in the Error Log -- the Material
		# Issue Plan's displayed transferred weight can otherwise go silently
		# stale after this Stock Entry submit/cancel with no on-screen signal.
		frappe.msgprint(
			_(
				"Could not refresh the linked Material Issue Plan's transferred weight after "
				"this Stock Entry. Its displayed weight summary may be stale until it is "
				"manually refreshed."
			),
			indicator="orange",
			title=_("Material Issue Plan Refresh Failed"),
		)


def on_cancel_stock_entry(doc, method):
	"""When a Stock Entry is cancelled, batch stock returns — restore Material Planning
	reservations and the consumed Sec Qty (Nos) on the batch."""
	_restore_material_planning_reservations(doc)
	_restore_batch_sec_qty(doc)
	_refresh_sco_status_for_final_entry(doc)

	# Cut Sheet: the stock is back, so the batch must stop advertising the offcut's
	# dimensions. Runs after _restore_batch_sec_qty, which would otherwise overwrite
	# the Sec Qty this puts back.
	_apply_cut_sheet_w2(doc, cancelling=True)

	# Recalculate transferred weight on SCO if a relevant SE is cancelled
	if doc.stock_entry_type == "Send to Subcontractor" and doc.get("custom_sco_ref"):
		_update_sco_transferred_weight(doc.custom_sco_ref)
		_refresh_linked_mip_weight(sco_ref=doc.custom_sco_ref)

	if doc.stock_entry_type == "Material Transfer" and doc.get("custom_sco_ref"):
		_update_sco_transferred_weight(doc.custom_sco_ref)
		_update_sco_cnc_weight(doc.custom_sco_ref)
		_refresh_linked_mip_weight(sco_ref=doc.custom_sco_ref)

	# SHARED_SCO_JC: WO cancel mirrors SCO cancel above.
	if doc.stock_entry_type == "Material Transfer" and doc.get("custom_wo_ref"):
		_update_wo_transferred_weight(doc.custom_wo_ref)
		_update_wo_cnc_weight(doc.custom_wo_ref)
		_refresh_linked_mip_weight(wo_ref=doc.custom_wo_ref)


def _cancelled_row_batch_no(row, voucher_no):
	"""The batch a Stock Entry row moved, found even after cancellation.

	on_cancel runs AFTER ERPNext has cleared batch_no and unlinked the Serial and
	Batch Bundle from every row, so reading row.batch_no there matches nothing --
	which is why the reduction done on submit was never reversed. Batches were
	left holding every kilo they were received with and no Sec Nos at all, and a
	Sec Nos of zero cannot drive a transfer: the Material Issue Plan popup shows
	a dash and falls back to an editable Kg box. Three batches on this site were
	in that state, each reduced to exactly the figure its receipt line carried.

	The Bundle document survives cancellation and still names the row it belonged
	to, so it is what this reads. row.batch_no is still tried first: on the submit
	path it is set, and this same helper serves both so the two can never look at
	different batches.
	"""
	if row.get("batch_no"):
		return row.batch_no
	if row.get("serial_and_batch_bundle"):
		found = frappe.db.get_value(
			"Serial and Batch Entry", {"parent": row.serial_and_batch_bundle}, "batch_no"
		)
		if found:
			return found
	found = frappe.db.sql(
		"""
		SELECT sbe.batch_no
		FROM `tabSerial and Batch Bundle` sbb
		JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sbb.name
		WHERE sbb.voucher_type = 'Stock Entry'
		  AND sbb.voucher_no = %s
		  AND sbb.voucher_detail_no = %s
		LIMIT 1
		""",
		(voucher_no, row.name),
	)
	return found[0][0] if found else None


def _restore_batch_sec_qty(doc):
	"""Reverse the custom_sec_qty reduction done on submit, mirroring on_submit_stock_entry.

	The batch is resolved through _cancelled_row_batch_no rather than read off the
	row: by the time this runs the row no longer says which batch it moved."""
	if doc.stock_entry_type == "Material Issue":
		for row in doc.items:
			batch_no = _cancelled_row_batch_no(row, doc.name)
			if batch_no and flt(row.get("custom_sec_qty")):
				_reduce_batch_sec_qty(batch_no, -flt(row.custom_sec_qty))

	elif doc.stock_entry_type in ("Repack", "Manufacture"):
		for row in doc.items:
			if not (row.s_warehouse and not row.is_finished_item):
				continue
			batch_no = _cancelled_row_batch_no(row, doc.name)
			if batch_no and flt(row.get("custom_sec_qty")):
				_reduce_batch_sec_qty(batch_no, -flt(row.custom_sec_qty))


def _restore_material_planning_reservations(doc):
	"""
	Re-apply is_reserved=1 on the Material Planning rows whose batch was consumed by this SE
	(they were cleared on submit), mirroring _release_material_planning_reservations: scoped to
	the linked Material Plannings on both tables, or legacy batch-wide on Material Mapping when
	no Production Plan link exists. Only currently-unreserved rows with the batch are restored.
	"""
	if doc.stock_entry_type not in RESERVATION_RELEASING_SE_TYPES:
		return

	moved_by_batch = _consumed_qty_by_batch(doc)
	if not moved_by_batch:
		return

	linked_mps = _linked_material_plannings(doc)

	# Rows already holding part of their reservation are included, not just released
	# ones: a partial transfer left them reserved for the remainder, and cancelling it
	# has to top them back up rather than skip over them.
	for batch_no, moved in moved_by_batch.items():
		for child_dt, batch_field, qty_field in (
			("Material Planning Material Mapping", "batch", "qty"),
			("Material Planning Available Raw Material", "batch_no", "required_qty"),
		):
			extra = {"parent": ["in", list(linked_mps)]} if linked_mps else {}
			rows = _reservation_rows(
				child_dt, batch_field, batch_no, extra,
				["name", "idx", "parent", "is_reserved", "reserved_qty", qty_field],
			)
			if rows:
				_restore_rows_by_qty(child_dt, rows, moved, qty_field)


def _update_sco_transferred_weight(sco_name):
	"""Recompute SCO.custom_transferred_weight_kg:
	  - qty from submitted 'Send to Subcontractor' SEs to the supplier/WIP warehouse, PLUS
	  - qty from submitted 'Material Transfer' SEs that go CNC warehouse → supplier/WIP warehouse.
	Also refreshes Op-1 SOE's available_to_consume_kg if it is still in draft.

	supplier_warehouse resolution mirrors get_target_context in
	material_issue_plan.py: the Material Issue Plan's own field takes priority (it is
	what the transfer itself was actually resolved against), falling back to the SCO's
	core field for a Supplier Job/Supplier with Material flow. An Internal Job SCO has
	no Job Worker, so its supplier_warehouse never auto-sets (see
	CustomSubcontractingOrder._auto_set_supplier_warehouse) -- if BOTH are still blank
	(e.g. the user hasn't set MIP's Supplier / WIP Warehouse either), fall back further
	to matching on qty transferred out of the known source warehouse instead of into an
	unknown destination -- 'Send to Subcontractor'/'Material Transfer' Stock Entries
	tagged with this SCO's own custom_sco_ref are never used for anything else, so this
	is unambiguous even without a recorded destination warehouse."""
	mip = frappe.db.get_value(
		"Material Issue Plan", {"subcontracting_order": sco_name},
		["supplier_warehouse", "source_warehouse", "cnc_warehouse"], as_dict=True,
	)
	sco_supplier_warehouse = frappe.db.get_value("Subcontracting Order", sco_name, "supplier_warehouse")
	supplier_warehouse = (mip.supplier_warehouse if mip else "") or sco_supplier_warehouse
	cnc_warehouse = mip.cnc_warehouse if mip else None

	if supplier_warehouse:
		# Direct source → supplier/WIP transfers, matched on the known destination.
		r1 = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sed.qty), 0)
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.custom_sco_ref = %s
			  AND se.stock_entry_type = 'Send to Subcontractor'
			  AND se.docstatus = 1
			  AND sed.t_warehouse = %s
			""",
			(sco_name, supplier_warehouse),
		)
	else:
		# No destination warehouse recorded anywhere (Internal Job, WIP warehouse never
		# set) -- fall back to unfiltered qty for this SCO's own Send to Subcontractor
		# entries, safe since that entry type + ref combination is exclusive to this
		# transfer.
		r1 = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sed.qty), 0)
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.custom_sco_ref = %s
			  AND se.stock_entry_type = 'Send to Subcontractor'
			  AND se.docstatus = 1
			""",
			(sco_name,),
		)
	direct_qty = flt(r1[0][0]) if r1 and r1[0][0] else 0

	# CNC warehouse → supplier/WIP warehouse transfers
	cnc_to_supplier_qty = 0.0
	if cnc_warehouse and supplier_warehouse:
		r2 = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sed.qty), 0)
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.custom_sco_ref = %s
			  AND se.stock_entry_type = 'Material Transfer'
			  AND se.docstatus = 1
			  AND sed.s_warehouse = %s
			  AND sed.t_warehouse = %s
			""",
			(sco_name, cnc_warehouse, supplier_warehouse),
		)
		cnc_to_supplier_qty = flt(r2[0][0]) if r2 and r2[0][0] else 0
	elif cnc_warehouse:
		r2 = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sed.qty), 0)
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.custom_sco_ref = %s
			  AND se.stock_entry_type = 'Material Transfer'
			  AND se.docstatus = 1
			  AND sed.s_warehouse = %s
			""",
			(sco_name, cnc_warehouse),
		)
		cnc_to_supplier_qty = flt(r2[0][0]) if r2 and r2[0][0] else 0

	transferred = flt(direct_qty + cnc_to_supplier_qty, 3)
	frappe.db.set_value(
		"Subcontracting Order", sco_name, "custom_transferred_weight_kg", transferred
	)

	# Keep Op-1 SOE in sync while still in draft
	soe_op1 = frappe.db.get_value(
		"Supplier Operation Entry",
		{"subcontracting_order": sco_name, "sequence_id": 1, "docstatus": 0},
		"name",
	)
	if soe_op1:
		frappe.db.set_value(
			"Supplier Operation Entry", soe_op1, "available_to_consume_kg", transferred
		)

	from manufyxinvenzaerp.subcontracting_management.subcontracting import (
		_refresh_sco_drawing_transferred_weights,
	)
	_refresh_sco_drawing_transferred_weights(frappe.get_doc("Subcontracting Order", sco_name))


def _update_sco_cnc_weight(sco_name):
	"""Recompute SCO.custom_cnc_transferred_weight_kg:
	  net qty currently in the CNC warehouse = sent to CNC minus already forwarded to supplier.
	"""
	from manufyxinvenzaerp.subcontracting_management.subcontracting import _get_sco_transfer_warehouses

	supplier_warehouse = frappe.db.get_value("Subcontracting Order", sco_name, "supplier_warehouse")
	_, cnc_warehouse = _get_sco_transfer_warehouses(sco_name)
	if not cnc_warehouse:
		return

	r1 = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(sed.qty), 0)
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.custom_sco_ref = %s
		  AND se.stock_entry_type = 'Material Transfer'
		  AND se.docstatus = 1
		  AND sed.t_warehouse = %s
		""",
		(sco_name, cnc_warehouse),
	)
	sent_to_cnc = flt(r1[0][0]) if r1 and r1[0][0] else 0

	sent_to_supplier = 0.0
	if supplier_warehouse:
		r2 = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sed.qty), 0)
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.custom_sco_ref = %s
			  AND se.stock_entry_type = 'Material Transfer'
			  AND se.docstatus = 1
			  AND sed.s_warehouse = %s
			  AND sed.t_warehouse = %s
			""",
			(sco_name, cnc_warehouse, supplier_warehouse),
		)
		sent_to_supplier = flt(r2[0][0]) if r2 and r2[0][0] else 0

	cnc_qty = max(0.0, flt(sent_to_cnc - sent_to_supplier, 3))
	frappe.db.set_value(
		"Subcontracting Order", sco_name, "custom_cnc_transferred_weight_kg", cnc_qty
	)


def _update_wo_transferred_weight(wo_name):
	"""Recompute WO.custom_transferred_weight_kg and sync Op-1 JC available_to_consume_kg.
	Counts: source → WIP transfers PLUS CNC → WIP transfers (both via custom_wo_ref SEs).
	# SHARED_SCO_JC: mirrors _update_sco_transferred_weight
	"""
	wip_warehouse = frappe.db.get_value("Work Order", wo_name, "wip_warehouse")
	if not wip_warehouse:
		return

	# Source → WIP (any Material Transfer with custom_wo_ref going TO wip_warehouse,
	# excluding CNC→WIP which is counted separately to avoid double-counting)
	r1 = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(sed.qty), 0)
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.custom_wo_ref = %s
		  AND se.stock_entry_type = 'Material Transfer'
		  AND se.docstatus = 1
		  AND sed.t_warehouse = %s
		""",
		(wo_name, wip_warehouse),
	)
	direct_qty = flt(r1[0][0]) if r1 and r1[0][0] else 0

	transferred = flt(direct_qty, 3)
	frappe.db.set_value("Work Order", wo_name, "custom_transferred_weight_kg", transferred)

	# Sync Op-1 JC custom_available_to_consume_kg while still in draft
	jc_op1 = frappe.db.get_value(
		"Job Card",
		{"work_order": wo_name, "sequence_id": 1, "docstatus": 0},
		"name",
	)
	if jc_op1:
		frappe.db.set_value("Job Card", jc_op1, "custom_available_to_consume_kg", transferred)

	from manufyxinvenzaerp.subcontracting_management.subcontracting import (
		_refresh_wo_drawing_transferred_weights,
	)
	_refresh_wo_drawing_transferred_weights(frappe.get_doc("Work Order", wo_name))


def _update_wo_cnc_weight(wo_name):
	"""Recompute WO.custom_cnc_transferred_weight_kg:
	net qty currently in CNC warehouse = sent to CNC minus already forwarded to WIP.
	# SHARED_SCO_JC: mirrors _update_sco_cnc_weight
	"""
	from manufyxinvenzaerp.subcontracting_management.subcontracting import _get_wo_transfer_warehouses

	_, cnc_warehouse = _get_wo_transfer_warehouses(wo_name)
	wip_warehouse = frappe.db.get_value("Work Order", wo_name, "wip_warehouse")
	if not cnc_warehouse:
		return

	r1 = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(sed.qty), 0)
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.custom_wo_ref = %s
		  AND se.stock_entry_type = 'Material Transfer'
		  AND se.docstatus = 1
		  AND sed.t_warehouse = %s
		""",
		(wo_name, cnc_warehouse),
	)
	sent_to_cnc = flt(r1[0][0]) if r1 and r1[0][0] else 0

	sent_to_wip = 0.0
	if wip_warehouse:
		r2 = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(sed.qty), 0)
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.custom_wo_ref = %s
			  AND se.stock_entry_type = 'Material Transfer'
			  AND se.docstatus = 1
			  AND sed.s_warehouse = %s
			  AND sed.t_warehouse = %s
			""",
			(wo_name, cnc_warehouse, wip_warehouse),
		)
		sent_to_wip = flt(r2[0][0]) if r2 and r2[0][0] else 0

	cnc_qty = max(0.0, flt(sent_to_cnc - sent_to_wip, 3))
	frappe.db.set_value("Work Order", wo_name, "custom_cnc_transferred_weight_kg", cnc_qty)


def _calc_qty(row, group):
	l = flt(row.get("custom_length"))
	w = flt(row.get("custom_width"))
	t = flt(row.get("custom_thickness"))
	uw = flt(row.get("custom_unit_weight"))
	sq = flt(row.get("custom_sec_qty"))

	if group == "Structurals" and l and uw and sq:
		return (l / 1000) * uw * sq
	if group == "Plates" and l and w and t and uw and sq:
		return (l / 1000) * (w / 1000) * t * uw * sq
	return 0.0


# ── Consumable Entry ──────────────────────────────────────────────────────────
#
# An entry issuing consumables against a job -- welding rods, paint, gas -- rather
# than moving the job's own steel. The three fields on the form are a chain: the
# Sales Order narrows which Production Plans can be picked, the plan names the Job
# Work Order, and that is what every weight rollup downstream already keys on.


@frappe.whitelist()
def get_production_plans_for_sales_order(sales_order):
    """Production Plans raised against one Sales Order, newest first.

    A plain link filter cannot express this: a plan's order lives on its child rows
    (Production Plan Item.sales_order), not on the plan itself, so the list has to be
    fetched rather than filtered."""
    if not sales_order:
        return []
    names = frappe.get_all(
        "Production Plan Item",
        filters={"sales_order": sales_order, "docstatus": ["<", 2]},
        pluck="parent",
        distinct=True,
    )
    if not names:
        return []
    return frappe.get_all(
        "Production Plan",
        filters={"name": ["in", names], "docstatus": ["<", 2]},
        fields=["name", "status"],
        order_by="creation desc",
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def production_plan_query(doctype, txt, searchfield, start, page_len, filters):
    """Link-field search for Production Plan, restricted to one Sales Order.

    Frappe's own link search cannot do it: a plan's Sales Order sits on its child
    rows, so this joins through Production Plan Item. With no Sales Order given it
    returns nothing rather than everything -- the field is only ever shown once one
    has been chosen, and offering every plan on the site would invite exactly the
    mismatch validate_consumable_entry then refuses."""
    sales_order = (filters or {}).get("sales_order")
    if not sales_order:
        return []

    return frappe.db.sql(
        """
        SELECT DISTINCT pp.name, pp.status
        FROM `tabProduction Plan` pp
        JOIN `tabProduction Plan Item` ppi ON ppi.parent = pp.name
        WHERE ppi.sales_order = %(sales_order)s
          AND pp.docstatus < 2
          AND pp.name LIKE %(txt)s
        ORDER BY pp.creation DESC
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "sales_order": sales_order,
            "txt": "%%%s%%" % (txt or ""),
            "start": start or 0,
            "page_len": page_len or 20,
        },
    )


@frappe.whitelist()
def get_job_work_order_for_production_plan(production_plan):
    """The Job Work Order raised from a Production Plan, if there is one.

    Where a plan somehow has more than one, the earliest is returned along with how
    many there were, so the form can say so rather than pick one silently."""
    if not production_plan:
        return {}
    orders = frappe.get_all(
        "Subcontracting Order",
        filters={"custom_production_plan": production_plan, "docstatus": ["<", 2]},
        pluck="name",
        order_by="creation asc",
    )
    if not orders:
        return {}
    return {"job_work_order": orders[0], "count": len(orders)}


def validate_consumable_entry(doc):
    """A consumable entry has to say which job it is for, and mean it.

    Two refusals, both about the same thing -- consumables landing on the wrong
    job's cost, or on no job at all.

    Missing: the order and the plan are what the job work order is looked up from,
    and the job work order is what every weight rollup downstream keys on. An entry
    ticked as consumable with neither filled in issues stock against nothing. The
    form marks both mandatory as soon as the box is ticked, but Frappe enforces
    mandatory_depends_on in the browser only, so an import or an API call would
    otherwise walk straight past it.

    Mismatched: the form fills these in order and clears what sits below when
    something above changes, so a plan belonging to a different order should not
    arise from normal use -- but it survives a field edited after the fact."""
    if not doc.get("custom_consumable_entry"):
        return

    sales_order = doc.get("custom_consumable_sales_order")
    plan = doc.get("custom_consumable_production_plan")

    missing = []
    if not sales_order:
        missing.append(_("Sales Order"))
    if not plan:
        missing.append(_("Production Plan"))
    if missing:
        frappe.throw(
            _("A Consumable Entry needs {0}. It names the job the consumables are "
              "issued against; without it the stock is issued against nothing.")
            .format(_(" and ").join(missing)),
            title=_("Job Not Named"),
        )

    belongs = frappe.db.exists(
        "Production Plan Item", {"parent": plan, "sales_order": sales_order}
    )
    if not belongs:
        frappe.throw(
            _("Production Plan {0} is not against Sales Order {1}.").format(plan, sales_order),
            title=_("Plan and Order Do Not Match"),
        )
