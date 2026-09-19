"""Stock Reconciliation is blocked on this site (sep14 FG plan, D21).

The inventory here is fully customised -- dimensions, Sec Qty on batches, one
finished-goods batch per drawing with its Nos per warehouse -- and a Stock
Reconciliation rewrites the Kg without any of that. Corrections are made with a
Material Issue (remove) followed by a Material Receipt (add back) instead.
"""

import frappe
from frappe import _

# One wording, shown by the form (public/js/stock_reconciliation.js) and thrown
# here. Keep the two identical.
BLOCKED_MESSAGE = (
	"As the inventory module is completely customized, Stock Reconciliation cannot be "
	"used. Instead, use a Stock Entry of type Material Issue to remove the product from "
	"inventory, then a Material Receipt to add the updated stock."
)


def block_stock_reconciliation(doc, method=None):
	"""Stock Reconciliation validate hook (registered in hooks.py): always refuse.

	Every purpose is refused, Opening Stock included. The form already disables
	Save, but this is what actually stops an entry made by import, by the API, or
	by Item's own "Opening Stock" field (ERPNext raises a Stock Reconciliation
	from it for items without batches; that field is hidden, and this covers the
	case where it is filled anyway).
	"""
	frappe.throw(_(BLOCKED_MESSAGE), title=_("Stock Reconciliation Not Used"))
