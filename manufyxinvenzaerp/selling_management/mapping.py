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

	Owner: A6. What A6 makes it do: FG rows get Nos = Sales Order Nos - Billed
	(Nos), and Kg = Nos x (line Kg / line Nos), the last pending Nos taking the exact
	pending Kg.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import (
		make_sales_invoice as erpnext_make_sales_invoice,
	)

	# TODO(A6): FG rows by pending Nos.
	return erpnext_make_sales_invoice(
		source_name, target_doc=target_doc, args=args, ignore_permissions=ignore_permissions
	)


@frappe.whitelist()
def make_sales_invoice_from_dn(source_name, target_doc=None, args=None):
	"""Override of erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice.

	Owner: A6. What A6 makes it do: FG rows get Nos = the Delivery Note row's Nos -
	its Billed (Nos), and Kg from that row's own Kg per Nos, with the same last-piece
	rule.
	"""
	from erpnext.stock.doctype.delivery_note.delivery_note import (
		make_sales_invoice as erpnext_make_sales_invoice,
	)

	# TODO(A6): FG rows by unbilled Nos.
	return erpnext_make_sales_invoice(source_name, target_doc=target_doc, args=args)
