"""Fill the Delivery Plan tab on Sales Orders that already have finished goods.

The tab's rows are a derived view, rebuilt when FG is booked or a Delivery Note is
submitted or cancelled. An order whose pieces were booked before the tab existed has
had none of those events since, so without this every existing order would open the
new tab to an empty table -- which reads as broken, not as "nothing happened yet".

Only submitted orders that have an FG batch are touched; the rest have nothing to
show. Derived data only: no Delivery Plan (Nos) exists yet to preserve, and nothing
on the order itself changes.
"""

import frappe


def execute():
    if not frappe.db.table_exists("Sales Order Delivery Plan"):
        return

    from manufyxinvenzaerp.selling_management.delivery_plan import _refresh

    orders = frappe.db.sql_list(
        """
        SELECT DISTINCT b.custom_sales_order
        FROM `tabBatch` b
        JOIN `tabSales Order` so ON so.name = b.custom_sales_order
        WHERE so.docstatus = 1 AND IFNULL(b.custom_drawing, '') != ''
        """
    )
    for so in orders:
        _refresh(so, keep_plan=False)
