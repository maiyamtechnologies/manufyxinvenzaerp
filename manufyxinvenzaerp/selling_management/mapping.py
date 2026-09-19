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
from frappe.utils import cint, flt

from manufyxinvenzaerp.production_management.fg_stock import is_fg_item


@frappe.whitelist()
def make_delivery_note(source_name, target_doc=None, kwargs=None):
	"""Override of erpnext.selling.doctype.sales_order.sales_order.make_delivery_note.

	Owner: A5. What A5 makes it do: FG lines map with Qty (Nos) = pending Nos
	(Sales Order Nos - Delivered (Nos)), Kg from the batches; non-FG lines unchanged.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import (
		make_delivery_note as erpnext_make_delivery_note,
	)

	# TODO(A5): FG lines by pending Nos.
	return erpnext_make_delivery_note(source_name, target_doc=target_doc, kwargs=kwargs)


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
