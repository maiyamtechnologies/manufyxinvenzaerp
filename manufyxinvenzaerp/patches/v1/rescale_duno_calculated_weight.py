"""
Patch: rescale_duno_calculated_weight

Sales Order DUNO Item.calculated_weight was stored per PIECE while the customer
weight it exists to be compared against (the same row's total_weight) is for ALL
pieces. drawing_calculated_weight summed the raw material rows' `qty` -- one
piece's steel -- when those same rows already carry `total_weight`, which is qty
times the drawing's piece count.

So the Loaded Sheet summary compared one piece's steel against every piece's
finished weight, and a drawing for 4 pieces read 75% short. The "below customer
weight" warning -- the whole point of the panel, the check that says the material
listed cannot produce the part -- fired on exactly the drawings that had more than
one piece. On this site all 30 drawings it had ever flagged, across 9 orders, were
false alarms, and not one genuinely short drawing existed to be found.

Single-piece drawings were never affected: per piece and all pieces are the same
number there. 44 of 104 drawing rows across 12 orders held the wrong figure.

Recomputed by direct write rather than by re-saving: most of these orders are
submitted (validate never runs again), and two thirds of the raw material rows are
locked, which recalculate_raw_material_qty deliberately skips. The rows' own
total_weight is already correct in both cases -- it always was -- so this only
re-does the roll-up that read the wrong column.
"""

import frappe


def execute():
    if not frappe.db.has_column("Sales Order DUNO Item", "calculated_weight"):
        return

    rows = frappe.db.sql(
        """
        SELECT d.name, d.calculated_weight AS was, ROUND(IFNULL(rm.tw, 0), 3) AS now_
        FROM `tabSales Order DUNO Item` d
        LEFT JOIN (
            SELECT parent, customer_drawing_number AS cdn, SUM(total_weight) AS tw
            FROM `tabSales Order Drawing Raw Material`
            WHERE parenttype = 'Sales Order'
            GROUP BY parent, customer_drawing_number
        ) rm ON rm.parent = d.parent AND rm.cdn = d.drawing_number
        WHERE d.parenttype = 'Sales Order'
          AND IFNULL(d.drawing_number, '') != ''
          AND ABS(IFNULL(d.calculated_weight, 0) - ROUND(IFNULL(rm.tw, 0), 3)) > 0.01
        """,
        as_dict=True,
    )
    if not rows:
        print("rescale_duno_calculated_weight: nothing to correct")
        return

    for r in rows:
        # update_modified=False: correcting a derived figure is not an edit anyone
        # made, and these rows sit on submitted orders.
        frappe.db.set_value(
            "Sales Order DUNO Item", r.name, "calculated_weight", r.now_, update_modified=False
        )

    frappe.db.commit()
    print(f"rescale_duno_calculated_weight: corrected {len(rows)} drawing row(s)")
