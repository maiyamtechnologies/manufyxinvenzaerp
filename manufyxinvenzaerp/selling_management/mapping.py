"""Overrides of ERPNext's Sales Order / Delivery Note mappers for finished goods.

Registered under override_whitelisted_methods in hooks.py, so the "Create >
Delivery Note / Sales Invoice" buttons land here instead of in ERPNext (Frappe's
make_mapped_doc resolves the override before calling the method).

Wave 0: every function calls the ERPNext original with the same arguments and
returns its result unchanged, so nothing behaves differently until its owner fills
it in. Owners (sep14 FG plan): make_delivery_note -> A5; the two invoice
functions -> A6. Each must keep the original's signature, because Frappe passes the
request's arguments straight through.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from manufyxinvenzaerp.production_management.fg_stock import is_fg_item


@frappe.whitelist()
def make_delivery_note(source_name, target_doc=None, kwargs=None):
	"""Override of erpnext.selling.doctype.sales_order.sales_order.make_delivery_note.

	Owner: A5. FG lines (batch-tracked FG items) map with Qty (Nos) = pending Nos:
	Sales Order Nos - Delivered (Nos) - the Nos of that line already on the target
	note ("Get Items From" appends).

	ERPNext decides which lines to map by Kg (delivered_qty < qty). For an FG line the
	Nos decide instead (R4, D10):
		- a line with no Nos pending is dropped, even if ERPNext still sees Kg pending
		  (the pieces all went, a little lighter than ordered);
		- a line with Nos pending is mapped even when ERPNext skipped it because its
		  Kg is already fully delivered (the pieces were heavier). Whether that extra
		  Kg may go is left to ERPNext's over-delivery allowance on submit, the only
		  Kg limit.
	ERPNext's other filters (rows picked in the "select items" dialog, delivery
	dates, drop-ship lines, reserved stock) still apply to the FG lines added back.

	An FG row carries no batch yet, so its Kg is only a placeholder: the user picks
	batches with Get FG Batches, and validate prices every batch row by its Nos.
	Non-FG lines stay as ERPNext maps them, less the Nos UOM the mapper copied.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import (
		make_delivery_note as erpnext_make_delivery_note,
	)

	from manufyxinvenzaerp.selling_management import delivery_note as dn

	existing = _count_items(target_doc)
	doc = erpnext_make_delivery_note(source_name, target_doc=target_doc, kwargs=kwargs)
	so = frappe.get_doc("Sales Order", source_name)
	line_idx = {d.name: d.idx for d in so.items}

	on_note = {}  # so_detail -> Nos already on the note (earlier rows)
	mapped = set()  # Sales Order lines ERPNext mapped this time
	drop = []
	for i, row in enumerate(doc.get("items")):
		if i < existing:
			if row.get("so_detail") and row.get("custom_sec_uom"):
				on_note[row.so_detail] = on_note.get(row.so_detail, 0) + abs(flt(row.custom_sec_qty))
			continue
		if row.get("so_detail"):
			mapped.add(row.so_detail)
		if not dn.is_tracked_fg_item(row.item_code):
			dn.clear_sec(row)
			continue
		_unbatched_fg_row(row)
		if not (row.get("so_detail") and dn.so_line_nos(row.so_detail)):
			# A line taken before lines carried Nos: the user types them.
			row.custom_sec_qty = 0
			continue
		pending = cint(max(dn.pending_nos(row.so_detail) - on_note.get(row.so_detail, 0), 0))
		if not pending:
			drop.append(row)
			continue
		row.custom_sec_qty = pending
		on_note[row.so_detail] = on_note.get(row.so_detail, 0) + pending

	for row in drop:
		doc.remove(row)

	added = _add_fg_lines_skipped_by_kg(doc, so, kwargs, mapped, on_note)

	if (drop or added) and not doc.get("items"):
		frappe.throw(_("All the finished-goods pieces on this order are already delivered."))
	if added:
		# New rows go in Sales Order line order, after anything already on the note.
		new_rows = sorted(doc.items[existing:], key=lambda r: line_idx.get(r.get("so_detail"), 0))
		doc.items = doc.items[:existing] + new_rows
	for i, row in enumerate(doc.get("items"), start=1):
		row.idx = i
	if added:
		# The added rows need what ERPNext's own set_missing_values gave the others
		# (cost center, expense account, taxes); their batch stays empty, see
		# _unbatched_fg_row.
		doc.run_method("set_missing_values")
		doc.run_method("calculate_taxes_and_totals")
	elif drop:
		doc.run_method("calculate_taxes_and_totals")
	return doc


def _unbatched_fg_row(row):
	"""An FG row as mapped: Nos UOM, no batch until the user picks one.

	An empty string, not None, and the batch fields off: ERPNext's
	set_missing_item_details otherwise fills a FIFO batch of ANY order into the row
	on save, which the user never chose (Get FG Batches turns the fields back on)."""
	from manufyxinvenzaerp.selling_management import delivery_note as dn

	row.custom_sec_uom = dn.SEC_UOM
	row.batch_no = ""
	row.use_serial_batch_fields = 0


def _add_fg_lines_skipped_by_kg(doc, so, kwargs, mapped, on_note):
	"""Append the FG lines ERPNext left out although they still have Nos pending.

	ERPNext skips a line once its delivered Kg reaches the ordered Kg; with pieces
	heavier than ordered that happens before the last pieces go. Returns the number
	of rows added. Mirrors ERPNext's other item filters so the "select items" dialog
	and the delivery-date filter behave the same for these lines.
	"""
	from frappe.model.mapper import get_mapped_doc

	from manufyxinvenzaerp.selling_management import delivery_note as dn

	if isinstance(kwargs, str):
		kwargs = frappe.parse_json(kwargs)
	if not kwargs:
		kwargs = {
			"for_reserved_stock": frappe.flags.args and frappe.flags.args.for_reserved_stock,
			"skip_item_mapping": frappe.flags.args and frappe.flags.args.skip_item_mapping,
		}
	kwargs = frappe._dict(kwargs)
	if kwargs.skip_item_mapping:
		return 0
	filtered = kwargs.get("filtered_children") or []
	dates = frappe.flags.args and frappe.flags.args.get("delivery_dates")

	added = 0
	for line in so.items:
		if line.name in mapped or not dn.is_tracked_fg_item(line.item_code):
			continue
		if cint(line.delivered_by_supplier) or (filtered and line.name not in filtered):
			continue
		if dates and cstr(line.delivery_date) not in dates:
			continue
		if kwargs.for_reserved_stock and flt(line.get("stock_reserved_qty")):
			continue  # ERPNext maps reserved lines through its own reservation path
		line_nos = flt(line.get("custom_sec_qty"))
		if not line_nos:
			continue
		pending = cint(max(dn.pending_nos(line.name) - on_note.get(line.name, 0), 0))
		if not pending:
			continue

		row = get_mapped_doc(
			"Sales Order Item",
			line.name,
			{
				"Sales Order Item": {
					"doctype": "Delivery Note Item",
					"field_map": {"rate": "rate", "name": "so_detail", "parent": "against_sales_order"},
				}
			},
			ignore_permissions=True,
		)
		_unbatched_fg_row(row)
		row.custom_sec_qty = pending
		# Placeholder Kg at the ordered weight per piece; the batch rows replace it.
		row.qty = flt(pending * flt(line.qty) / line_nos, 3)
		row.stock_qty = flt(row.qty * flt(row.conversion_factor or 1), 3)
		doc.append("items", row)
		on_note[line.name] = on_note.get(line.name, 0) + pending
		added += 1
	return added


@frappe.whitelist()
def make_sales_invoice_from_so(source_name, target_doc=None, args=None, ignore_permissions=False):
	"""Override of erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice.

	Owner: A6. FG rows get Nos = Sales Order Nos - Billed (Nos), and Kg = Nos x
	(line Kg / line Nos); mapping always proposes everything still pending, so the
	last-piece rule makes that the exact pending Kg (R2). Non-FG rows are ERPNext's.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import (
		make_sales_invoice as erpnext_make_sales_invoice,
	)

	existing = _count_items(target_doc)
	doc = erpnext_make_sales_invoice(
		source_name, target_doc=target_doc, args=args, ignore_permissions=ignore_permissions
	)
	return _apply_fg_nos_to_invoice(doc, existing)


@frappe.whitelist()
def make_sales_invoice_from_dn(source_name, target_doc=None, args=None):
	"""Override of erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice.

	Owner: A6. FG rows get Nos = the Delivery Note row's Nos (net of returns) - its
	Billed (Nos), capped by what is unbilled on the Sales Order line, and Kg from that
	row's own Kg per Nos, with the same last-piece rule.
	"""
	from erpnext.stock.doctype.delivery_note.delivery_note import (
		make_sales_invoice as erpnext_make_sales_invoice,
	)

	existing = _count_items(target_doc)
	doc = erpnext_make_sales_invoice(source_name, target_doc=target_doc, args=args)
	return _apply_fg_nos_to_invoice(doc, existing)


def _count_items(target_doc):
	"""Rows already on the invoice before this mapping ("Get Items From" appends)."""
	if not target_doc:
		return 0
	if isinstance(target_doc, str):
		target_doc = frappe.parse_json(target_doc)
	return len(target_doc.get("items") or [])


def _apply_fg_nos_to_invoice(doc, existing):
	"""Set Nos and Kg on the FG rows just mapped onto a Sales Invoice.

	The rows already on the invoice (index < existing) are left as the user has them;
	they still count against the pending Nos, because compute_fg_rows walks the rows
	in order. Each new FG row is first given the whole pending Nos of its source, then
	priced by the same compute_fg_rows validate uses. A row with nothing left by the
	piece is dropped (ERPNext only knows the Kg side).
	"""
	from manufyxinvenzaerp.selling_management import sales_invoice as si

	if not doc.get("items"):
		# Nothing pending on the Kg side either: ERPNext's own empty result stands.
		return doc

	is_return = cint(doc.get("is_return"))
	sign = -1 if is_return else 1
	ledger = si._Ledger()
	drop = []
	for i, row in enumerate(doc.get("items")):
		if i < existing:
			for dt, name in si._tracked_sources(ledger, row):
				ledger.take(dt, name, row.get("custom_sec_qty"), row.get("qty"))
			continue
		if not is_fg_item(row.item_code):
			si._clear_sec(row)
			continue
		sources = si._tracked_sources(ledger, row)
		if not sources:
			si._clear_sec(row)
			continue
		pending = None
		for dt, name in sources:
			billed_nos, billed_kg = ledger.billed(dt, name)
			limit_nos, _limit_kg = si._limit(ledger.source(dt, name), billed_nos, billed_kg, is_return)
			pending = limit_nos if pending is None else min(pending, limit_nos)
		pending = cint(max(flt(pending), 0))
		if not pending:
			drop.append(row)
			continue
		row.custom_sec_uom = si.SEC_UOM
		row.custom_sec_qty = sign * pending
		for dt, name in sources:
			# Reserve these pieces so a second row of the same line sees less.
			ledger.take(dt, name, row.custom_sec_qty, 0)

	for row in drop:
		doc.remove(row)
	if drop and not doc.get("items"):
		frappe.throw(_("All the finished-goods pieces on this document are already invoiced."))
	for i, row in enumerate(doc.get("items"), start=1):
		row.idx = i

	# Price every FG row by its Nos (new and existing alike, in order), then redo the
	# totals that ERPNext worked out from its own Kg.
	si.compute_fg_rows(doc, throw=False)
	si.refresh_totals(doc)
	return doc
