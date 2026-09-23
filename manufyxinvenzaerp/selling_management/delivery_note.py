"""Delivery Note hooks for finished goods sold in Kg, delivered by the piece.

sep14 FG plan, package A5. The user types Qty (Nos) on an FG row; the Kg comes
from the drawing batch (fg_stock), and the batch and the Sales Order line keep
their Nos in step.

Rules on a finished-goods row (an FG item that is batch-tracked):
	delivery  -- a batch of the row's Sales Order is mandatory (a batch tied to no
	             order is refused); whole Nos > 0;
	             Nos <= what the batch holds in the row's warehouse; the Nos of all
	             rows of one Sales Order line <= its pending Nos (R4); Kg = the
	             batch's Kg for those pieces (fg_stock pricing, last-piece rule).
	return    -- made from the Delivery Note (dn_detail), into the same batch;
	             Nos stored negative; Kg = -Nos x the original row's Kg per Nos, and
	             the last pieces returned take the exact Kg still out;
	             Nos <= delivered - earlier returns.
The Kg the user sees is read-only on these rows (property setter on custom_sec_uom),
and the server sets it on every save whatever was sent.

Delivered (Nos) on the Sales Order line and the batch Nos are always recounted
from submitted rows, never incremented, so the order in which notes, returns and
cancels happen cannot leave them wrong.

Legacy finished-goods items (no batch: FINGOODS001, or "Fabricated Structurs"
until the user switches its batch on) are left to behave as before, the same way
fg_stock leaves their Stock Entry rows alone (D13).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from manufyxinvenzaerp.production_management import fg_stock

SEC_UOM = "Nos"


# ── Small readers ─────────────────────────────────────────────────────────────


def is_tracked_fg_item(item_code):
	"""A finished-goods item on the Kg / Nos model: FG and batch-tracked."""
	return fg_stock._is_batch_fg_item(item_code)


def clear_sec(row):
	"""Drop the Nos UOM from a row that is not tracked by the piece.

	Sales Order Item.custom_sec_uom defaults to "Nos" and the mapper copies it by
	name onto every Delivery Note line; the property setter would then make that
	line's Kg read-only. Only FG rows tracked by the piece may keep it."""
	row.custom_sec_uom = None
	row.custom_sec_qty = 0


def _is_whole(nos):
	return flt(nos, 3) == cint(flt(nos, 3))


def so_line_nos(so_detail):
	"""The Sales Order line's Qty (Nos), 0 for a line taken before lines had Nos."""
	return flt(frappe.db.get_value("Sales Order Item", so_detail, "custom_sec_qty")) if so_detail else 0.0


def delivered_nos(so_detail, exclude_dn=None):
	"""Nos delivered against a Sales Order line, net of returns.

	Summed over submitted Delivery Note rows; return rows carry negative Nos and the
	so_detail of the line they came back from, so they net off by themselves."""
	return flt(frappe.db.sql(
		"""
		SELECT COALESCE(SUM(dni.custom_sec_qty), 0)
		FROM `tabDelivery Note Item` dni
		JOIN `tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dni.so_detail = %s AND dn.docstatus = 1 AND dn.name != %s
		""",
		(so_detail, exclude_dn or ""),
	)[0][0], 3)


def pending_nos(so_detail, exclude_dn=None):
	"""Nos of a Sales Order line still to deliver (Qty (Nos) - Delivered (Nos))."""
	return flt(so_line_nos(so_detail) - delivered_nos(so_detail, exclude_dn), 3)


def _returned(dn_detail, exclude_dn=None):
	"""(Nos, Kg) already returned against a Delivery Note row, as magnitudes."""
	nos, kg = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(dni.custom_sec_qty), 0), COALESCE(SUM(dni.qty), 0)
		FROM `tabDelivery Note Item` dni
		JOIN `tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dni.dn_detail = %s AND dn.docstatus = 1 AND dn.is_return = 1
			AND dn.name != %s
		""",
		(dn_detail, exclude_dn or ""),
	)[0]
	return abs(flt(nos, 3)), abs(flt(kg, 3))


def row_batch(row, voucher_no=None):
	"""The batch a Delivery Note row moves, also after submit / cancel.

	A row names its batch in batch_no while use_serial_batch_fields is on. Once
	ERPNext has built the Serial and Batch Bundle (on submit), or cleared the row on
	cancel, the bundle is where it is found; a cancelled bundle still names its row."""
	if row.get("batch_no"):
		return row.batch_no
	if row.get("serial_and_batch_bundle"):
		found = frappe.db.get_value(
			"Serial and Batch Entry", {"parent": row.serial_and_batch_bundle}, "batch_no"
		)
		if found:
			return found
	if voucher_no and row.get("name"):
		found = frappe.db.sql(
			"""
			SELECT sbe.batch_no
			FROM `tabSerial and Batch Bundle` sbb
			JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sbb.name
			WHERE sbb.voucher_type = 'Delivery Note' AND sbb.voucher_no = %s
				AND sbb.voucher_detail_no = %s
			LIMIT 1
			""",
			(voucher_no, row.name),
		)
		if found:
			return found[0][0]
	return None


# ── The row calculation (validate and the form share it) ──────────────────────


def compute_fg_rows(doc, throw=True, fit_returns=False):
	"""Check and price every finished-goods row of a Delivery Note by its Nos.

	Input:  doc (Delivery Note, saved or not); throw -- False collects the messages
	        instead of raising (the form asks this while the user types);
	        fit_returns -- on a return, cut a Nos larger than what is still out down
	        to it instead of refusing. Only the form asks for this, on a new return:
	        ERPNext maps the row's full Nos even after earlier returns.
	Output: {row.name: {"fg", "nos", "kg", "error"}} for every row; "fg" says
	        whether the row is tracked by the piece. Sets on doc as it goes:
	        qty / stock_qty (Kg), custom_sec_qty, custom_sec_uom, batch_no,
	        use_serial_batch_fields, custom_drawing, custom_duno_mark_no.

	Rows are taken in order, and each one takes its pieces from what the earlier
	rows of the same note left: two rows of one batch cannot both claim its last
	piece, and two rows of one Sales Order line share its pending Nos.
	"""
	is_return = cint(doc.get("is_return"))
	exclude = None if doc.is_new() else doc.name
	results = {}
	left_in_batch = {}  # (batch, warehouse) -> [nos, kg] still there for later rows
	left_on_line = {}   # so_detail -> Nos still pending for later rows
	left_on_dn_row = {}  # dn_detail -> [nos, kg] still returnable for later rows

	def fail(row, msg):
		if throw:
			frappe.throw(msg, title=_("Finished Goods Delivery"))
		results[row.name]["error"] = msg

	for row in doc.get("items"):
		if not is_tracked_fg_item(row.item_code):
			clear_sec(row)
			results[row.name] = {"fg": False, "error": None}
			continue

		row.custom_sec_uom = SEC_UOM
		results[row.name] = {"fg": True, "nos": flt(row.custom_sec_qty), "kg": flt(row.qty, 3), "error": None}
		label = _("Row {0} ({1})").format(row.idx, frappe.bold(row.item_code))
		nos = abs(flt(row.custom_sec_qty, 3))
		if nos <= 0 or not _is_whole(nos):
			fail(row, _("{0}: NOS must be a whole number of pieces greater than 0 (got {1}).")
				.format(label, flt(row.custom_sec_qty)))
			continue

		if is_return:
			kg, nos = _price_return_row(doc, row, nos, label, exclude, left_on_dn_row, fail, fit_returns)
			sign = -1
		else:
			kg = _price_delivery_row(doc, row, nos, label, exclude, left_in_batch, left_on_line, fail)
			sign = 1
		if kg is None:
			continue

		row.custom_sec_qty = sign * nos
		# qty is in the row's UOM; the Kg is the stock UOM (an FG item is stocked in Kg).
		cf = flt(row.conversion_factor) or 1
		row.qty = flt(sign * kg / cf, 3)
		row.stock_qty = flt(sign * kg, 3)
		row.use_serial_batch_fields = 1
		results[row.name].update({"nos": row.custom_sec_qty, "kg": row.qty})

	return results


def _batch_into_row(row, label, fail):
	"""Make sure the row names its batch in batch_no; returns the batch or None.

	A batch picked through the batch selector sits only in a draft bundle. It is
	moved into batch_no and the bundle dropped, so ERPNext rebuilds the bundle on
	submit with the Kg set here instead of the Kg the selector saw."""
	if not row.get("batch_no") and row.get("serial_and_batch_bundle"):
		batches = frappe.get_all(
			"Serial and Batch Entry", filters={"parent": row.serial_and_batch_bundle}, pluck="batch_no"
		)
		if len(set(batches)) == 1:
			row.batch_no = batches[0]
			row.serial_and_batch_bundle = None
	if not row.get("batch_no"):
		fail(row, _(
			"{0}: finished goods are delivered from their drawing batch, so a Batch No is "
			"mandatory. Use Get FG Batches to fill the batches of this order."
		).format(label))
		return None
	if frappe.db.get_value("Batch", row.batch_no, "item") != row.item_code:
		fail(row, _("{0}: batch {1} does not belong to this item.").format(label, row.batch_no))
		return None
	return row.batch_no


def _fill_drawing(row, batch_no):
	# Read-only reference fields on the row: which drawing these pieces are.
	info = frappe.db.get_value("Batch", batch_no, ["custom_drawing", "custom_duno_mark_no"], as_dict=True) or {}
	row.custom_drawing = info.get("custom_drawing")
	row.custom_duno_mark_no = info.get("custom_duno_mark_no")


def _price_delivery_row(doc, row, nos, label, exclude, left_in_batch, left_on_line, fail):
	"""Kg for an outgoing FG row, after every check; None when refused."""
	batch_no = _batch_into_row(row, label, fail)
	if not batch_no:
		return None

	batch_so = frappe.db.get_value("Batch", batch_no, "custom_sales_order")
	# Every FG batch our code creates (the Final Stock Entry, one per drawing) names
	# its Sales Order, and an FG Material Receipt only accepts an existing batch. A
	# batch without one was made by hand outside that flow: its pieces belong to no
	# order, so they cannot be delivered against one.
	if not batch_so:
		fail(row, _(
			"{0}: batch {1} is not tied to any Sales Order, so it is not a drawing batch "
			"made by the Final Stock Entry. Deliver from the drawing's batch (Get FG Batches)."
		).format(label, batch_no))
		return None
	if batch_so != row.get("against_sales_order"):
		fail(row, _(
			"{0}: batch {1} holds pieces made for Sales Order {2}, but this row is for {3}."
		).format(label, batch_no, batch_so, row.get("against_sales_order") or _("no Sales Order")))
		return None

	if not row.get("warehouse"):
		fail(row, _("{0}: the warehouse is mandatory.").format(label))
		return None

	if row.get("so_detail") and so_line_nos(row.so_detail):
		if row.so_detail not in left_on_line:
			left_on_line[row.so_detail] = pending_nos(row.so_detail, exclude)
		if nos > left_on_line[row.so_detail]:
			fail(row, _(
				"{0}: {1} Nos is more than is still to deliver on Sales Order {2} "
				"({3} Nos pending on that line, this note included)."
			).format(label, cint(nos), row.against_sales_order, cint(max(left_on_line[row.so_detail], 0))))
			return None
		left_on_line[row.so_detail] = flt(left_on_line[row.so_detail] - nos, 3)

	key = (batch_no, row.warehouse)
	if key not in left_in_batch:
		avail = fg_stock.fg_batch_available(batch_no, row.warehouse)
		left_in_batch[key] = [avail["nos"], avail["kg"]]
	left_nos, left_kg = left_in_batch[key]
	if nos > left_nos:
		fail(row, _("{0}: batch {1} holds {2} Nos in {3}; {4} Nos cannot be delivered.").format(
			label, batch_no, flt(left_nos, 3), row.warehouse, cint(nos)))
		return None
	kg = fg_stock._price_nos(left_nos, left_kg, nos)
	left_in_batch[key] = [flt(left_nos - nos, 3), flt(left_kg - kg, 3)]
	_fill_drawing(row, batch_no)
	return kg


def _price_return_row(doc, row, nos, label, exclude, left_on_dn_row, fail, fit=False):
	"""(Kg, Nos) as magnitudes for an FG return row, after every check; Kg is None
	when refused. With fit, a Nos above what is still out is cut down to it."""
	if not row.get("dn_detail"):
		fail(row, _(
			"{0}: a finished-goods return must be made from its Delivery Note (Create > "
			"Return), so the pieces go back into their batch at the weight they left with."
		).format(label))
		return None, nos

	orig = frappe.db.get_value(
		"Delivery Note Item", row.dn_detail,
		["parent", "qty", "stock_qty", "custom_sec_qty", "batch_no", "serial_and_batch_bundle", "name"],
		as_dict=True,
	)
	if not orig or not flt(orig.custom_sec_qty):
		fail(row, _("{0}: the Delivery Note row it returns has no NOS to return.").format(label))
		return None, nos

	orig_batch = row_batch(orig, orig.parent)
	given = row.get("batch_no") or (row_batch(row) if row.get("serial_and_batch_bundle") else None)
	if given and given != orig_batch:
		fail(row, _(
			"{0}: returned pieces go back into the batch they left from ({1}), not {2}."
		).format(label, orig_batch, given))
		return None, nos
	# Named in batch_no (not a bundle) so ERPNext builds the inward bundle on submit
	# with the Kg set here.
	row.batch_no = orig_batch
	row.serial_and_batch_bundle = None

	if row.dn_detail not in left_on_dn_row:
		ret_nos, ret_kg = _returned(row.dn_detail, exclude)
		orig_kg = abs(flt(orig.stock_qty or orig.qty, 3))
		left_on_dn_row[row.dn_detail] = [
			flt(abs(flt(orig.custom_sec_qty)) - ret_nos, 3), flt(orig_kg - ret_kg, 3),
		]
	left_nos, left_kg = left_on_dn_row[row.dn_detail]
	if fit and nos > left_nos > 0:
		nos = left_nos
	if nos > left_nos:
		fail(row, _(
			"{0}: {1} Nos cannot come back; {2} Nos of that delivery are still out "
			"(delivered less earlier returns)."
		).format(label, cint(nos), cint(max(left_nos, 0))))
		return None, nos

	if nos == left_nos:
		kg = left_kg  # the last pieces take the exact Kg still out
	else:
		per_nos = abs(flt(orig.stock_qty or orig.qty)) / abs(flt(orig.custom_sec_qty))
		kg = flt(nos * per_nos, 3)
	left_on_dn_row[row.dn_detail] = [flt(left_nos - nos, 3), flt(left_kg - kg, 3)]
	_fill_drawing(row, orig_batch)
	return kg, nos


# ── Hooks ─────────────────────────────────────────────────────────────────────


def validate_delivery_note(doc, method=None):
	"""Delivery Note validate hook (registered in hooks.py).

	Runs after ERPNext's validate (and India Compliance's), so any Kg changed here
	is priced again: amounts, taxes and the GST item columns.
	"""
	before = [(flt(r.qty, 3), flt(r.get("custom_sec_qty"), 3)) for r in doc.get("items")]
	compute_fg_rows(doc, throw=True)
	after = [(flt(r.qty, 3), flt(r.get("custom_sec_qty"), 3)) for r in doc.get("items")]
	if after != before:
		from manufyxinvenzaerp.selling_management.sales_invoice import refresh_totals

		refresh_totals(doc)


def _update_after_change(doc):
	"""Recount Delivered (Nos) on each Sales Order line and refresh each FG batch.

	Runs after ERPNext's own on_submit / on_cancel, so the stock ledger and this
	note's docstatus are already final and a plain recount gives the new figures."""
	lines, batches = set(), []
	for row in doc.get("items"):
		if not (row.get("custom_sec_uom") and is_tracked_fg_item(row.item_code)):
			continue
		if row.get("so_detail"):
			lines.add(row.so_detail)
		batch_no = row_batch(row, doc.name)
		if batch_no and batch_no not in batches:
			batches.append(batch_no)

	for so_detail in lines:
		frappe.db.set_value(
			"Sales Order Item", so_detail, "custom_delivered_sec_qty",
			delivered_nos(so_detail), update_modified=False,
		)
	for batch_no in batches:
		fg_stock.refresh_fg_batch(batch_no)

	# Delivered / Available on the Sales Order's Delivery Plan tab. Cannot fail the
	# note: refresh_plans_for_batches catches and logs.
	from manufyxinvenzaerp.selling_management.delivery_plan import refresh_plans_for_batches

	refresh_plans_for_batches(batches)


def on_submit_delivery_note(doc, method=None):
	"""Delivery Note on_submit hook (registered in hooks.py).

	Sales Order Item custom_delivered_sec_qty (net of returns) and
	fg_stock.refresh_fg_batch for every FG batch on the note.
	"""
	_update_after_change(doc)


def on_cancel_delivery_note(doc, method=None):
	"""Delivery Note on_cancel hook (registered in hooks.py).

	The same recount as on submit: the note is already cancelled in the database,
	so it simply drops out of the sums. The batch is read back from the row's bundle,
	because ERPNext has cleared batch_no off the rows by now.
	"""
	_update_after_change(doc)


# ── Form helpers (public/js/delivery_note.js) ─────────────────────────────────


def _doc_from_form(doc):
	if isinstance(doc, str):
		doc = frappe.parse_json(doc)
	doc = frappe.get_doc(doc)
	if not frappe.has_permission("Delivery Note", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


@frappe.whitelist()
def get_fg_rows_kg(doc, fit_returns=0):
	"""Nos and Kg of every row of an unsaved Delivery Note, for the form.

	Input:  doc (the Delivery Note as JSON).
	Output: {row_name: {"fg", "nos", "kg", "error"}}; "error" is the message the
	        server would refuse the row with, and "kg" is then the row's current Kg.

	Runs the same compute_fg_rows as validate, so the form and the server can never
	disagree on the last-piece Kg.
	"""
	return compute_fg_rows(_doc_from_form(doc), throw=False, fit_returns=cint(fit_returns))


@frappe.whitelist()
def get_fg_batches(doc):
	"""Finished-goods batches that can fill the FG rows of a Delivery Note.

	Input:  doc (the Delivery Note as JSON, saved or not).
	Output: [{batch_no, item_code, drawing, duno, warehouse, sales_order, so_detail,
	          template_row, available_nos, available_kg, kg_per_nos, nos, kg}]

	For every FG row of the note that comes from a Sales Order line, the batches of
	that item whose Sales Order is the row's and that hold pieces in the row's
	warehouse. One entry per (Sales Order line, batch): available_* is what the batch
	holds there less what other rows of this note already take from it, and nos is a
	proposal -- as many as the batch has, up to what the line still has pending after
	the rows already batched and the entries before it. template_row is the row the
	form copies (rate, accounts, ...) for the new batch row; the unbatched row is the
	one preferred, as the form removes it.
	"""
	doc = _doc_from_form(doc)
	if cint(doc.get("is_return")):
		return []
	exclude = None if doc.is_new() else doc.name

	lines = {}  # so_detail -> template row and figures
	taken_batch = {}  # (batch, warehouse) -> Nos already on batched rows of this note
	for row in doc.get("items"):
		if not is_tracked_fg_item(row.item_code):
			continue
		if row.get("batch_no"):
			key = (row.batch_no, row.warehouse)
			taken_batch[key] = taken_batch.get(key, 0) + abs(flt(row.custom_sec_qty))
		if not (row.get("against_sales_order") and row.get("so_detail") and row.get("warehouse")):
			continue
		line = lines.setdefault(row.so_detail, frappe._dict(
			sales_order=row.against_sales_order, item_code=row.item_code,
			warehouse=row.warehouse, template_row=row.name, on_note=0.0, batched=set(),
		))
		if row.get("batch_no"):
			line.on_note += abs(flt(row.custom_sec_qty))
			line.batched.add(row.batch_no)
		else:
			line.template_row = row.name  # the unbatched row is the one replaced

	out = []
	for so_detail, line in lines.items():
		line_nos = so_line_nos(so_detail)
		left = flt(pending_nos(so_detail, exclude) - line.on_note, 3) if line_nos else None
		batches = frappe.get_all(
			"Batch",
			filters={"item": line.item_code, "custom_sales_order": line.sales_order, "disabled": 0},
			fields=["name", "custom_drawing", "custom_duno_mark_no"],
			order_by="custom_duno_mark_no asc, name asc",
		)
		for b in batches:
			if b.name in line.batched:
				continue  # already on the note: its row is edited there
			avail = fg_stock.fg_batch_available(b.name, line.warehouse)
			nos_here = flt(avail["nos"] - taken_batch.get((b.name, line.warehouse), 0), 3)
			if nos_here <= 0:
				continue
			kg_here = avail["kg"] if nos_here == avail["nos"] else fg_stock._price_nos(
				avail["nos"], avail["kg"], nos_here)
			propose = nos_here if left is None else max(min(nos_here, left), 0)
			if left is not None:
				left = flt(left - propose, 3)
			out.append({
				"batch_no": b.name,
				"item_code": line.item_code,
				"drawing": b.custom_drawing,
				"duno": b.custom_duno_mark_no,
				"warehouse": line.warehouse,
				"sales_order": line.sales_order,
				"so_detail": so_detail,
				"template_row": line.template_row,
				"available_nos": nos_here,
				"available_kg": flt(kg_here, 3),
				"kg_per_nos": flt(kg_here / nos_here, 3) if nos_here else 0.0,
				"nos": propose,
				"kg": fg_stock._price_nos(nos_here, kg_here, propose),
			})
	return out
