"""Approver 1 is chosen again by the requester (Request tab) and approves first. Open drafts that
were approved under the "any Director" flow have no Approver 1: make the first Director who
decided Approver 1 (move that slot to slot 1) so they stay valid. Drafts nobody has acted on
simply show the now-mandatory Approver 1 field for the requester to fill. Safe to re-run."""

import frappe


def execute():
    for name in frappe.get_all("Payment Approval", filters={"docstatus": 0}, pluck="name"):
        doc = frappe.get_doc("Payment Approval", name)
        if doc.approver_1:
            continue
        decided = [
            n for n in (2, 3, 4) if doc.get(f"approver_{n}") and doc.get(f"approver_{n}_status") in ("Approved", "Rejected")
        ]
        if not decided:
            continue
        first = min(decided, key=lambda n: str(doc.get(f"approver_{n}_on") or "9999"))
        values = {}
        for suffix in ("", "_status", "_on", "_remarks"):
            values[f"approver_1{suffix}"] = doc.get(f"approver_{first}{suffix}")
            values[f"approver_{first}{suffix}"] = None
        frappe.db.set_value("Payment Approval", name, values, update_modified=False)
        doc.reload()
        doc.set_status()
        doc.set_approval_summary()
        frappe.db.set_value(
            "Payment Approval",
            name,
            {"status": doc.status, "approvals_received": doc.approvals_received, "pending_with": doc.pending_with},
            update_modified=False,
        )
        doc.sync_assignments()
