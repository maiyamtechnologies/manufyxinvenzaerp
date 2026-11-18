"""Payment Approval "Requested By" used to be a Link to User; it is now a Link to the new
Payment Requested By master (so a request can be raised for someone who is not a system
user). Turn every stored user id into a master record (named after the user, linked to
them), point the approvals at it, and fill the new approval summary fields
(approvals_received / pending_with) that the list filters use. Safe to re-run."""

import frappe

from manufyxinvenzaerp.accounts_management.doctype.payment_requested_by.payment_requested_by import (
    get_or_create_for_user,
)


def execute():
    rows = frappe.db.sql(
        "SELECT name, requested_by FROM `tabPayment Approval` WHERE IFNULL(requested_by, '') != ''", as_dict=True
    )
    cache = {}
    for r in rows:
        value = r.requested_by
        if frappe.db.exists("Payment Requested By", value):
            continue
        if value not in cache:
            # Old value is a user id (or "Administrator"); an unknown value becomes a plain name.
            if frappe.db.exists("User", value):
                cache[value] = get_or_create_for_user(value)
            else:
                doc = frappe.get_doc({"doctype": "Payment Requested By", "requester_name": value})
                doc.insert(ignore_permissions=True)
                cache[value] = doc.name
        frappe.db.set_value("Payment Approval", r.name, "requested_by", cache[value], update_modified=False)

    for name in frappe.get_all("Payment Approval", pluck="name"):
        doc = frappe.get_doc("Payment Approval", name)
        doc.set_approval_summary()
        frappe.db.set_value(
            "Payment Approval",
            name,
            {"approvals_received": doc.approvals_received, "pending_with": doc.pending_with},
            update_modified=False,
        )
