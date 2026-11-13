"""Move the old Payment Request customizations into Payment Approval, then remove them.

Core Payment Request is now stock ERPNext. Before this, supplier Payment Requests carried
a Payment Type and a Source of Funds. Each such request (Supplier, with a Source of Funds
or a Payment Type) is copied into a Payment Approval -- keeping its status, so a Paid one
still counts against its Source of Funds -- and then the Custom Fields and the hidden
Accounting Dimensions Property Setter are deleted. The original Payment Requests are
left untouched. Safe to re-run: copies are keyed on Payment Approval.migrated_from."""

import frappe

OLD_FIELDS = (
    "custom_payment_type",
    "custom_source_of_funds_section",
    "custom_source_of_funds",
    "custom_total_customer_payment",
    "custom_customer_payment_date",
    "custom_source_of_funds_column_break",
    "custom_already_used_amount",
    "custom_balance_amount",
    "custom_payment_entry_created",
)


def execute():
    if frappe.db.has_column("Payment Request", "custom_source_of_funds") and frappe.db.has_column(
        "Payment Request", "custom_payment_type"
    ):
        _copy_requests()

    for fieldname in OLD_FIELDS:
        name = frappe.db.get_value("Custom Field", {"dt": "Payment Request", "fieldname": fieldname})
        if name:
            frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
    for ps in frappe.get_all(
        "Property Setter", filters={"doc_type": "Payment Request", "field_name": "accounting_dimensions_section"}, pluck="name"
    ):
        frappe.delete_doc("Property Setter", ps, force=True, ignore_permissions=True)
    frappe.clear_cache(doctype="Payment Request")


def _copy_requests():
    rows = frappe.db.sql(
        """
        SELECT * FROM `tabPayment Request`
        WHERE party_type = 'Supplier'
          AND (IFNULL(custom_source_of_funds, '') != '' OR IFNULL(custom_payment_type, '') != '')
        """,
        as_dict=True,
    )
    for pr in rows:
        if frappe.db.exists("Payment Approval", {"migrated_from": pr.name}):
            continue
        ref = {"Sales Order": "sales_order", "Purchase Order": "purchase_order", "Purchase Invoice": "purchase_invoice"}
        doc = frappe.get_doc(
            {
                "doctype": "Payment Approval",
                "company": pr.company,
                "requested_by": pr.owner,
                "transaction_date": pr.transaction_date,
                "payment_type": pr.custom_payment_type or "Bill Payment",
                "party_type": "Supplier",
                "party": pr.party,
                "requested_amount": pr.grand_total,
                "approved_amount": pr.grand_total if pr.docstatus == 1 else 0,
                "department": None,
                "material_type": None,
                "project": pr.project,
                "purpose": pr.subject or pr.message or "Migrated from Payment Request",
                "source_of_funds": pr.custom_source_of_funds or None,
                "mode_of_payment": pr.mode_of_payment,
                "remarks": f"Migrated from Payment Request {pr.name}",
                "migrated_from": pr.name,
                ref.get(pr.reference_doctype, "remarks"): pr.reference_name if pr.reference_doctype in ref else f"Migrated from Payment Request {pr.name}",
            }
        )
        doc.flags.ignore_validate = True
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        doc.flags.ignore_permissions = True
        doc.insert()

        status = {0: "Draft", 2: "Cancelled"}.get(pr.docstatus)
        if pr.docstatus == 1:
            status = "Paid" if pr.status == "Paid" else "Submitted"
        values = {"docstatus": pr.docstatus, "status": status, "owner": pr.owner, "creation": pr.creation}
        if status == "Paid":
            values["payment_entry"] = frappe.db.get_value(
                "Payment Entry Reference", {"payment_request": pr.name, "docstatus": 1}, "parent"
            )
        frappe.db.set_value("Payment Approval", doc.name, values, update_modified=False)
