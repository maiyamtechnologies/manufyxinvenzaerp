"""Delivery Note hooks for finished goods sold in Kg, delivered by the piece.

sep14 FG plan, package A5. The user types Qty (Nos) on an FG row; the Kg comes
from the drawing batch (fg_stock.kg_for_nos), and the batch and the Sales Order
line keep their Nos in step.
"""

import frappe
from frappe import _


def validate_delivery_note(doc, method=None):
	"""Delivery Note validate hook (registered in hooks.py).

	Owner: A5. Wave 0 stub: does nothing.

	What A5 makes it do, on FG rows: batch mandatory and belonging to the row's
	Sales Order; whole Nos > 0, Nos <= batch available in the warehouse, and the Nos
	per Sales Order line <= its pending Nos; Kg = fg_stock.kg_for_nos. On returns:
	Nos negated, Kg from the original row's Kg per Nos (last piece takes the exact
	remainder), Nos <= delivered minus earlier returns, same batch.
	"""
	# TODO(A5): implement.
	pass


def on_submit_delivery_note(doc, method=None):
	"""Delivery Note on_submit hook (registered in hooks.py).

	Owner: A5. Wave 0 stub: does nothing.

	What A5 makes it do: update Sales Order Item custom_delivered_sec_qty (net of
	returns) and fg_stock.refresh_fg_batch for every FG batch on the note.
	"""
	# TODO(A5): implement.
	pass


def on_cancel_delivery_note(doc, method=None):
	"""Delivery Note on_cancel hook (registered in hooks.py).

	Owner: A5. Wave 0 stub: does nothing.

	What A5 makes it do: the reverse of on_submit_delivery_note -- recompute the
	Sales Order lines' Delivered (Nos) and refresh the FG batches.
	"""
	# TODO(A5): implement.
	pass
