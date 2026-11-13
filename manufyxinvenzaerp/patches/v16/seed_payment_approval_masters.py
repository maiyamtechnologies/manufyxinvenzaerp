"""One-time seed of the Payment Approval dropdown masters (Material Type, Department).

A patch, not a fixture, so it runs once per site: values the client later renames or
deletes are not brought back by the next migrate. The wording follows the client's
Payment Request sheet, with its spelling slips corrected."""

import frappe

MATERIAL_TYPES = (
    "Raw Materials",
    "Paints",
    "Welding Consumables",
    "Grinding Consumables",
    "Cylinders",
    "Bolt & Nuts",
    "Painting Consumables",
    "Assets",
    "Machineries",
    "Maintenance Spares",
    "Painting Tools",
    "Production Tools",
    "Stationery",
    "Others (to fill manually)",
)

DEPARTMENTS = ("Production", "Plan", "Assets", "Etc")


def execute():
    for doctype, field, values in (
        ("Payment Material Type", "material_type", MATERIAL_TYPES),
        ("Payment Department", "department_name", DEPARTMENTS),
    ):
        for value in values:
            if not frappe.db.exists(doctype, value):
                frappe.get_doc({"doctype": doctype, field: value}).insert(ignore_permissions=True)
