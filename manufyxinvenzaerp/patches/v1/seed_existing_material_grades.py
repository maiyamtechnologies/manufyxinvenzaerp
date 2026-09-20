"""Preserve every existing drawing grade when its field becomes a Link.

The live site may contain grades beyond the values seen on the development
site. The new Material Grade DocType exists by post_model_sync, so create one
master record for each distinct value already stored on drawing rows.
"""

import frappe


def execute():
    if not frappe.db.has_column("Sales Order Drawing Raw Material", "grade"):
        return

    grades = frappe.db.sql(
        """SELECT DISTINCT grade FROM `tabSales Order Drawing Raw Material`
           WHERE grade IS NOT NULL AND grade != ''""",
        as_list=True,
    )
    for (grade,) in grades:
        if not frappe.db.exists("Material Grade", grade):
            frappe.get_doc({"doctype": "Material Grade", "grade_name": grade}).insert(
                ignore_permissions=True
            )
