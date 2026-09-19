"""Stock Reconciliation is blocked on this site (sep14 FG plan, D21).

The inventory here is fully customised -- dimensions, Sec Qty on batches, one
finished-goods batch per drawing with its Nos per warehouse -- and a Stock
Reconciliation rewrites the Kg without any of that. Corrections are made with a
Material Issue (remove) followed by a Material Receipt (add back) instead.
"""

import frappe
from frappe import _


def block_stock_reconciliation(doc, method=None):
	"""Stock Reconciliation validate hook (registered in hooks.py).

	Owner: A1. Wave 0 stub: does nothing, so saving behaves exactly as before.

	What A1 makes it do: throw, for every purpose including Opening Stock,
	"As the inventory module is completely customized, Stock Reconciliation cannot
	be used. Instead, use a Stock Entry of type Material Issue to remove the product
	from inventory, then a Material Receipt to add the updated stock."
	"""
	# TODO(A1): implement.
	pass
