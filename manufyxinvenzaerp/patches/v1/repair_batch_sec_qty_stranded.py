"""
Patch: repair_batch_sec_qty_stranded

A batch that still holds steel must not report zero pieces.

`ISMB450-L7331-R004` held 530.804 Kg -- one whole 7331.55 mm bar at 72.4 kg/m --
with `custom_sec_qty = 0`. Validate Stock therefore showed "0" against a real bar,
and the Material Issue Plan would have offered that weight at no pieces at all.

How it got there: the batch arrived on PR-26-00004 as 1061.608 Kg / 2 bars. The
requirement it was reserved against (MP-2026-00011, item 1w2, DUNO 1B5) is ONE
piece of 7331.55 mm = 530.804 Kg, and _alloc_sec_qty(530.804, 1061.608, 2) returns
1.0 -- the correct answer. But the Available Raw Material row carried sec_qty = 2,
the transfer (MAT-STE-00005) copied that 2 onto its Stock Entry row beside one
bar's weight, and _reduce_batch_sec_qty subtracted 2 pieces for 530.804 Kg. Two
bars' pieces came off for one bar's weight, leaving 0 against the bar still there.

What wrote 2 onto that Available Raw Material row has NOT been established, so this
repairs the consequence rather than the cause. The zero floor added to
_reduce_batch_sec_qty stops the count going negative from here, and check 7b in
_collect_batch_mapping_issues no longer treats a zero as "nothing to check", so a
recurrence is reported instead of hidden.

Recomputes the piece count from the batch's own dimensions through the app's shared
formula -- never from the Kg/Nos ratio, which is the figure in doubt. Only touches
batches that hold stock AND report zero or less; a batch legitimately down to dust
(ISMB400-L6936-R003 holds 0.006 Kg) yields zero whole pieces and is left alone.
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.utils.dimension_formula import calculate_qty

# Below this, a batch is dust rather than a piece -- see ISMB400-L6936-R003.
_MIN_KG = 0.01


def execute():
    rows = frappe.db.sql(
        """
        SELECT b.name, b.item, b.batch_qty, b.custom_sec_qty,
               b.custom_length, b.custom_width, b.custom_thickness,
               i.custom_unit_weight, i.custom_parent_item_group AS grp
        FROM `tabBatch` b
        JOIN `tabItem` i ON i.name = b.item
        WHERE b.batch_qty > %s
          AND IFNULL(b.custom_sec_qty, 0) <= 0
          AND i.custom_parent_item_group IN ('Structurals', 'Plates')
        """,
        (_MIN_KG,),
        as_dict=True,
    )

    fixed = 0
    for r in rows:
        per_piece = calculate_qty(
            r.grp, flt(r.custom_length), flt(r.custom_width),
            flt(r.custom_thickness), flt(r.custom_unit_weight), 1,
        )
        if not per_piece or flt(per_piece) <= 0:
            # No usable dimensions -- guessing a piece count here would be worse
            # than leaving the figure alone for someone to look at.
            print(f"repair_batch_sec_qty_stranded: {r.name} has no piece weight, left alone")
            continue

        pieces = int(flt(r.batch_qty) / flt(per_piece) + 0.001)
        if pieces <= 0:
            continue

        frappe.db.set_value(
            "Batch", r.name, "custom_sec_qty", flt(pieces, 3), update_modified=False
        )
        fixed += 1
        print(
            f"repair_batch_sec_qty_stranded: {r.name} {flt(r.batch_qty, 3)} Kg "
            f"@ {flt(per_piece, 3)} Kg/piece -> custom_sec_qty {flt(r.custom_sec_qty, 3)} => {pieces}"
        )

    # A negative count is never right and was reachable before the floor below.
    negatives = frappe.db.sql(
        """SELECT name, custom_sec_qty FROM `tabBatch` WHERE custom_sec_qty < 0""", as_dict=True
    )
    for n in negatives:
        frappe.db.set_value("Batch", n.name, "custom_sec_qty", 0, update_modified=False)
        print(f"repair_batch_sec_qty_stranded: {n.name} had {n.custom_sec_qty} pieces, clamped to 0")

    frappe.db.commit()
    print(f"repair_batch_sec_qty_stranded: repaired {fixed} batch(es), clamped {len(negatives)}")
