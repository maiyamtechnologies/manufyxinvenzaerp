"""Payment Approval no longer names Approver 1 in advance: every Director can approve, and
any two approvals allow submit. Drop approver slots that were only "named" (no decision
yet) on draft requests, then recompute status, approval count and who is still pending.
Safe to re-run."""

import frappe


def execute():
    for name in frappe.get_all("Payment Approval", filters={"docstatus": 0}, pluck="name"):
        doc = frappe.get_doc("Payment Approval", name)
        for n in (1, 2, 3, 4):
            if doc.get(f"approver_{n}") and (doc.get(f"approver_{n}_status") or "Pending") == "Pending":
                doc.clear_slot(n)
        doc.set_status()
        doc.set_approval_summary()
        values = {"status": doc.status, "approvals_received": doc.approvals_received, "pending_with": doc.pending_with}
        for n in (1, 2, 3, 4):
            for suffix in ("", "_status", "_on", "_remarks"):
                values[f"approver_{n}{suffix}"] = doc.get(f"approver_{n}{suffix}")
        frappe.db.set_value("Payment Approval", name, values, update_modified=False)
        doc.sync_assignments()
