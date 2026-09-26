"""Recording the decisions people make about material, so they can be explained later.

The client's choice, given three options: log the decisions -- who reserved, who
reassigned, who rounded up, and why -- rather than every field change on every
document, which on a 500-drawing order would be large, slow and unreadable.

Two rules follow from that and are worth keeping:

  One entry per DECISION, not per row. Reserving a plan is one decision covering
  however many rows; it is recorded once, with the count and the total weight.
  Reassigning a batch is genuinely per row, so that is one entry each.

  Logging must never break the thing it is logging. A reservation that succeeded and
  then failed because its log entry could not be written would be strictly worse than
  no log at all, so every failure here is swallowed and reported to the error log
  instead.
"""

import frappe
from frappe.utils import flt

ACTIONS = {
    "Reserve",
    "Unreserve",
    "Reassign Batch",
    "Round Up at Transfer",
    "Cut Sheet Balance",
    "Return NA at Transfer",
}


def log_decision(
    action,
    reference_doctype=None,
    reference_name=None,
    details=None,
    row_reference=None,
    item_code=None,
    batch_no=None,
    new_batch_no=None,
    rows_affected=None,
    qty=None,
    sec_qty=None,
    previous_qty=None,
    previous_sec_qty=None,
    reason=None,
):
    """Record one decision. Returns the entry's name, or None if it could not be made.

    Who and when come free: the entry's own owner and creation are the person who was
    logged in and the moment it happened, which is exactly what is being asked for.
    """
    if action not in ACTIONS:
        frappe.log_error(
            title="Decision log: unknown action",
            message="%s is not one of %s" % (action, sorted(ACTIONS)),
        )
        return None

    try:
        entry = frappe.get_doc({
            "doctype": "Manufyx Decision Log",
            "action": action,
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "row_reference": row_reference,
            "item_code": item_code,
            "batch_no": batch_no,
            "new_batch_no": new_batch_no,
            "rows_affected": rows_affected,
            "qty": flt(qty, 3) if qty is not None else None,
            "sec_qty": flt(sec_qty, 3) if sec_qty is not None else None,
            "previous_qty": flt(previous_qty, 3) if previous_qty is not None else None,
            "previous_sec_qty": flt(previous_sec_qty, 3) if previous_sec_qty is not None else None,
            "reason": (reason or "").strip() or None,
            "details": details,
        })
        entry.insert(ignore_permissions=True)
        return entry.name
    except Exception:
        # Deliberately swallowed -- see the module docstring.
        frappe.log_error(
            title="Decision log: could not record %s" % action,
            message=frappe.get_traceback(),
        )
        return None
