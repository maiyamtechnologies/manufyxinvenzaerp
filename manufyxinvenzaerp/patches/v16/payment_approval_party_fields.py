"""Payment Approval started life with a Supplier field; it now has Party Type + Party
(Supplier or Customer). Copy the old column into the new fields on any site that already
had Payment Approvals. Sites that get the doctype fresh have no `supplier` column, so
this does nothing there."""

import frappe


def execute():
    if not frappe.db.has_column("Payment Approval", "supplier"):
        return
    frappe.db.sql(
        """
        UPDATE `tabPayment Approval`
        SET party_type = 'Supplier', party = supplier
        WHERE IFNULL(party, '') = '' AND IFNULL(supplier, '') != ''
        """
    )
    if frappe.db.has_column("Payment Approval", "supplier_name"):
        frappe.db.sql(
            """
            UPDATE `tabPayment Approval`
            SET party_name = supplier_name
            WHERE IFNULL(party_name, '') = '' AND IFNULL(supplier_name, '') != ''
            """
        )
