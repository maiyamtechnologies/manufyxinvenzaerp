"""Sales Invoice hooks for finished goods invoiced by the piece.

sep14 FG plan, package A6. Invoices are in Kg (same UOM as the Sales Order and
the Delivery Note) but the user works in Nos: the Kg follows from the source line's
Kg per Nos, and the Sales Order line / Delivery Note row keep a Billed (Nos) total.
"""

import frappe
from frappe import _


def validate_sales_invoice(doc, method=None):
	"""Sales Invoice validate hook (registered in hooks.py).

	Owner: A6. Wave 0 stub: does nothing.

	What A6 makes it do: refuse Update Stock when any line is an FG item; on FG
	rows, whole Nos, Nos <= pending on the source (Sales Order line or Delivery Note
	row), Kg recalculated from Nos (last pending Nos = exact pending Kg), and an FG
	row must come from a Sales Order or a Delivery Note.
	"""
	# TODO(A6): implement.
	pass


def on_submit_sales_invoice(doc, method=None):
	"""Sales Invoice on_submit hook (registered in hooks.py).

	Owner: A6. Wave 0 stub: does nothing.

	What A6 makes it do: update custom_billed_sec_qty on the Sales Order line
	(every invoice) and on the Delivery Note row (DN-based invoices). Credit notes
	reduce it.
	"""
	# TODO(A6): implement.
	pass


def on_cancel_sales_invoice(doc, method=None):
	"""Sales Invoice on_cancel hook (registered in hooks.py).

	Owner: A6. Wave 0 stub: does nothing.

	What A6 makes it do: the reverse of on_submit_sales_invoice.
	"""
	# TODO(A6): implement.
	pass
