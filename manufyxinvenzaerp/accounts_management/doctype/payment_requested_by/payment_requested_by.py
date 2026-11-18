# Copyright (c) 2026, Manufyxinvenza and Contributors
# License: GNU General Public License v3. See license.txt

"""Payment Requested By -- the people a Payment Approval can be raised for.

Anyone may raise a Payment Approval on behalf of a person who is not a system user
(a site engineer, a store keeper...), so "Requested By" is a small master of names
instead of a User link. A name may optionally point at a system user; Payment Approvals
raised by that user then default to it."""

import frappe
from frappe.model.document import Document


class PaymentRequestedBy(Document):
    def validate(self):
        self.requester_name = (self.requester_name or "").strip()


def get_or_create_for_user(user):
    """The Payment Requested By record for a system user: the one linked to them, else
    one named after them (created on first use)."""
    existing = frappe.db.get_value("Payment Requested By", {"user": user}, "name")
    if existing:
        return existing
    full_name = frappe.db.get_value("User", user, "full_name") or user
    name = full_name
    if frappe.db.exists("Payment Requested By", name):
        # Same display name already used by someone else: fall back to the user id.
        if frappe.db.get_value("Payment Requested By", name, "user") not in (None, "", user):
            name = f"{full_name} ({user})"
        else:
            frappe.db.set_value("Payment Requested By", name, "user", user)
            return name
    doc = frappe.get_doc({"doctype": "Payment Requested By", "requester_name": name, "user": user})
    doc.insert(ignore_permissions=True)
    return doc.name
