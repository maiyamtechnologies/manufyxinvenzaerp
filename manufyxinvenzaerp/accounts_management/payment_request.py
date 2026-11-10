import frappe
from frappe import _


def validate_payment_request(doc, method):
    """Warn (non-blocking) if this supplier Payment Request would overdraw its
    selected customer Payment Entry's remaining balance."""
    if doc.party_type != "Supplier" or not doc.custom_source_of_funds:
        return

    usage = get_fund_usage(doc.custom_source_of_funds, doc.name)
    if doc.grand_total and doc.grand_total > usage["balance_amount"]:
        frappe.msgprint(
            _(
                "This Payment Request's amount ({0}) exceeds the remaining balance "
                "({1}) of the selected Source of Funds ({2})."
            ).format(
                frappe.format(doc.grand_total, {"fieldtype": "Currency"}),
                frappe.format(usage["balance_amount"], {"fieldtype": "Currency"}),
                doc.custom_source_of_funds,
            ),
            title=_("Fund Balance Exceeded"),
            indicator="orange",
        )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def payment_entry_query(doctype, txt, searchfield, start, page_len, filters):
    """Link search for Source of Funds: matches Payment Entry name, customer
    (party/party_name), or reference no. Restricted to submitted customer receipts."""
    like_txt = f"%{txt}%"
    values = {"txt": like_txt, "page_len": int(page_len), "start": int(start)}

    return frappe.db.sql(
        """
        SELECT pe.name, pe.party_name, pe.reference_no, pe.paid_amount
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Receive'
          AND pe.party_type = 'Customer'
          AND (
              pe.name LIKE %(txt)s
              OR pe.party_name LIKE %(txt)s
              OR pe.party LIKE %(txt)s
              OR pe.reference_no LIKE %(txt)s
          )
        ORDER BY pe.posting_date DESC
        LIMIT %(page_len)s OFFSET %(start)s
        """,
        values,
    )


@frappe.whitelist()
def get_fund_usage(payment_entry, payment_request=None):
    """Given a customer Payment Entry used as a Source of Funds, return how much of
    it has already been drawn by other *Paid* supplier Payment Requests, and what
    remains. `payment_request` (the current doc, if any) is excluded from the sum."""
    pe = frappe.db.get_value(
        "Payment Entry", payment_entry, ["paid_amount", "posting_date"], as_dict=True
    )
    if not pe:
        frappe.throw(_("Payment Entry {0} not found").format(payment_entry))

    filters = {
        "custom_source_of_funds": payment_entry,
        "party_type": "Supplier",
        "status": "Paid",
        "docstatus": 1,
    }
    if payment_request:
        filters["name"] = ["!=", payment_request]

    already_used_amount = (
        frappe.db.get_list(
            "Payment Request",
            filters=filters,
            fields=[{"SUM": "grand_total", "as": "total"}],
        )[0]["total"]
        or 0
    )

    total_customer_payment = pe.paid_amount or 0
    return {
        "total_customer_payment": total_customer_payment,
        "customer_payment_date": pe.posting_date,
        "already_used_amount": already_used_amount,
        "balance_amount": total_customer_payment - already_used_amount,
    }
