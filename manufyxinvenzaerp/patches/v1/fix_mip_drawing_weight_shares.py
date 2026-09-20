"""Re-stamp Item Number, Drawing Planned Weight and Excess Qty on Material Issue Plan
raw-material rows written before the requirement could be identified exactly.

Those rows were matched to their Sales Order requirement by DIMENSIONS, and a plan row
carries the batch's size (a 12000 mm bar), never the cut size (340 mm). The match
therefore missed and fell through to a loose drawing+item lookup where "first row wins",
so a drawing needing one item in two sizes had both requirements measured against one of
them. Separately, a requirement filled from two differently-sized batches looked like two
requirements and claimed its weight twice. Together they put six-figure phantom shortfalls
on the transfer popup's consolidated excess tab -- MIP-2026-00050 reported 6,836.131 Kg of
ISMB400 missing and 44.077 Kg of PLATE10 missing on a plan whose mapping covered the
requirement exactly.

Item Number is copied down from the Material Planning row (both source tables carry it),
the weight is re-looked-up with it, and Excess Qty is recomputed from each row's SHARE of
its requirement.

Draft and Open plans only. A plan that has issued stock is a record of what was sent, and
these three fields are descriptive -- nothing in the transfer, consumption or excess-return
ledger reads them back -- so rewriting settled history buys nothing and loses the figures
the operator actually saw. Completed plans reread correctly the moment someone refreshes
their raw materials.
"""

import frappe
from frappe.utils import flt


def execute():
    table = "Material Issue Plan Raw Material"
    if not frappe.db.has_column(table, "item_number"):
        return

    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        _lookup_drawing_planned_weight,
        requirement_weight_shares,
    )

    plans = frappe.get_all(
        "Material Issue Plan", filters={"status": ["in", ["Draft", "Open"]]}, pluck="name"
    )
    if not plans:
        return

    # The Material Planning row the MIP row was copied from, so Item Number can be
    # carried down without rebuilding the plan (a rebuild is blocked once anything has
    # been transferred, and would overwrite operator edits besides).
    item_number_by_source = {}
    for source_table in ("Material Planning Material Mapping",
                         "Material Planning Available Raw Material",
                         "Material Planning Unavailable Item"):
        for r in frappe.get_all(source_table, fields=["name", "item_number"]):
            if r.item_number:
                item_number_by_source[(source_table, r.name)] = r.item_number

    touched = 0
    for plan in plans:
        rows = frappe.get_all(
            table, filters={"parent": plan},
            fields=["name", "source_table", "source_row", "sales_order",
                    "customer_drawing_number", "item_code", "planned_item", "qty",
                    "length", "width", "thickness", "is_unavailable"],
            order_by="idx",
        )
        if not rows:
            continue

        for row in rows:
            row.item_number = item_number_by_source.get((row.source_table, row.source_row)) or ""
            row.drawing_planned_weight = _lookup_drawing_planned_weight(
                row.sales_order, row.customer_drawing_number, row.item_code,
                row.length, row.width, row.thickness, row.item_number)

        for row, share in zip(rows, requirement_weight_shares(rows)):
            excess = 0 if row.is_unavailable or share is None else flt(flt(row.qty) - share, 3)
            frappe.db.set_value(table, row.name, {
                "item_number": row.item_number,
                # None means "no requirement to compare against" in memory; the column
                # is not nullable, and an ordinary save stores that case as 0 too.
                "drawing_planned_weight": flt(row.drawing_planned_weight),
                "excess_qty": excess,
            }, update_modified=False)
            touched += 1

    frappe.db.commit()
    print("fix_mip_drawing_weight_shares: re-stamped {0} row(s) across {1} plan(s)".format(
        touched, len(plans)))
