"""Planning rows carry the drawing's Nos with its UOM, and the Kg beside it.

Material Planning's Selected BOMs rows showed Qty to Manufacture (the drawing's piece
count) next to the finished-goods item's stock UOM, so 2 pieces read "2 Kg". The rows
now say Nos, and every planning row -- Material Planning, and the drawing rows of the
Job Work Order and Material Issue Plan -- also carries Qty to Manufacture (Kg).

This fills both on rows written before the change:

  Material Planning BOM Item  UOM = Nos on every drawing row; Kg from the drawing.
  SCO Drawing Item            Kg = the plan's Planned Qty (Kg) for the drawing when the
                              plan was made in pieces, else worked from the drawing.

Kg is left at 0 for a drawing made before Kg and Nos were tracked separately: its Cust
Weight (Total) holds one piece's weight, so a Kg worked from it would be wrong. Figures
only -- no stock, reservation or amount is touched. Safe to run again.

Every column is checked before it is read. Patches run BEFORE after_migrate, which is
where this app creates its custom fields, so on a site taking this release for the first
time Production Plan Item.custom_sec_qty does not exist yet and reading it aborted the
whole migrate ("Unknown column 'tabProduction Plan Item.custom_sec_qty' in 'WHERE'").
A column that is not there yet holds no data either, so skipping it loses nothing: the
rows it would have filled are written by the form's own validate on the next save.
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.production_plan_management.production_plan import drawing_kg_for_nos


def execute():
    cache = {}

    if not (frappe.db.has_column("Material Planning BOM Item", "qty_to_manufacture_kg")
            and frappe.db.has_column("Material Planning BOM Item", "uom")):
        return

    for r in frappe.get_all(
        "Material Planning BOM Item",
        filters={"drawing": ["is", "set"]},
        fields=["name", "drawing", "qty_to_manufacture", "uom", "qty_to_manufacture_kg"],
    ):
        kg = drawing_kg_for_nos(r.drawing, r.qty_to_manufacture, cache)
        if r.uom != "Nos" or flt(r.qty_to_manufacture_kg, 3) != kg:
            frappe.db.set_value(
                "Material Planning BOM Item", r.name,
                {"uom": "Nos", "qty_to_manufacture_kg": kg}, update_modified=False,
            )

    plan_of = {}  # (parenttype, parent) -> Production Plan
    for doctype, field in (("Subcontracting Order", "custom_production_plan"),
                           ("Material Issue Plan", "production_plan")):
        for d in frappe.get_all(doctype, fields=["name", field]):
            plan_of[(doctype, d.name)] = d.get(field)

    planned_kg = {}  # (Production Plan, drawing) -> Planned Qty (Kg), plans made in Nos
    # No Qty (Nos) column yet means no plan was made in pieces, so there is no Kg to take
    # from one; the drawing's own weight below answers for every row.
    if frappe.db.has_column("Production Plan Item", "custom_sec_qty"):
        for p in frappe.get_all(
            "Production Plan Item",
            filters={"custom_drawing": ["is", "set"], "custom_sec_qty": [">", 0]},
            fields=["parent", "custom_drawing", "planned_qty"],
        ):
            key = (p.parent, p.custom_drawing)
            planned_kg[key] = flt(planned_kg.get(key, 0) + flt(p.planned_qty), 3)

    if not frappe.db.has_column("SCO Drawing Item", "qty_to_manufacture_kg"):
        return

    for r in frappe.get_all(
        "SCO Drawing Item",
        filters={"drawing": ["is", "set"]},
        fields=["name", "parent", "parenttype", "drawing", "qty_to_manufacture",
                "qty_to_manufacture_kg"],
    ):
        plan = plan_of.get((r.parenttype, r.parent))
        kg = planned_kg.get((plan, r.drawing))
        if kg is None:
            kg = drawing_kg_for_nos(r.drawing, r.qty_to_manufacture, cache)
        if flt(r.qty_to_manufacture_kg, 3) != flt(kg, 3):
            frappe.db.set_value(
                "SCO Drawing Item", r.name, "qty_to_manufacture_kg", flt(kg, 3),
                update_modified=False,
            )
