"""Feedback and Rework Remarks moved from the Inspection Entry header onto its rows.

Existing entries only have them on the header. Each row takes the header Feedback --
except that a Not Ok entry's rows with nothing rejected are Ok, since Not Ok on a row
now means that row had a rejection. A drawing row with a rejection takes the header
Rework Remarks. Only blank rows are filled, so running this again (or after someone
filled a row) changes nothing. Job Card entries have no rows and keep their header
values as they are.
"""

import frappe


def execute():
    for child, cond in (
        ("SOE Inspection Item", "p.source_doctype = 'Supplier Operation Entry'"),
        ("Inspection Entry Item", "p.source_doctype = 'Purchase Receipt'"),
    ):
        if not frappe.db.has_column(child, "feedback"):
            continue
        frappe.db.sql(
            f"""UPDATE `tab{child}` c JOIN `tabInspection Entry` p
                  ON p.name = c.parent AND c.parenttype = 'Inspection Entry'
                SET c.feedback = IF(p.feedback = 'Not Ok' AND IFNULL(c.reject_qty, 0) <= 0, 'Ok', p.feedback)
                WHERE {cond} AND IFNULL(c.feedback, '') = '' AND IFNULL(p.feedback, '') != ''"""
        )

    if frappe.db.has_column("SOE Inspection Item", "rework_remarks"):
        frappe.db.sql(
            """UPDATE `tabSOE Inspection Item` c JOIN `tabInspection Entry` p
                  ON p.name = c.parent AND c.parenttype = 'Inspection Entry'
                SET c.rework_remarks = p.rework_remarks
                WHERE p.source_doctype = 'Supplier Operation Entry' AND c.reject_qty > 0
                  AND IFNULL(c.rework_remarks, '') = '' AND IFNULL(p.rework_remarks, '') != ''"""
        )
