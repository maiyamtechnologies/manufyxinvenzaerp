import frappe


def on_submit_payment_entry(doc, method):
    """A Payment Entry built from a Payment Approval ("Create Payment Entry") marks it Paid."""
    approval = doc.get("custom_payment_approval")
    if approval:
        frappe.db.set_value(
            "Payment Approval", approval, {"status": "Paid", "payment_entry": doc.name}, update_modified=False
        )


def on_cancel_payment_entry(doc, method):
    approval = doc.get("custom_payment_approval")
    if approval and frappe.db.get_value("Payment Approval", approval, "payment_entry") == doc.name:
        frappe.db.set_value(
            "Payment Approval", approval, {"status": "Submitted", "payment_entry": None}, update_modified=False
        )
