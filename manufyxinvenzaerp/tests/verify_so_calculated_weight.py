"""Calculated weight is shown beside the customer's own figure, at both levels.

Two different numbers that were being conflated. The sheet's Total Weight (KG) is
typed in and describes the FINISHED piece; it becomes Customer Provided Weight.
What the raw materials listed under that drawing weigh is never typed -- it comes
out of the group's formula -- and it is normally the larger of the two, because
stock is cut down to the part. A drawing where it comes out SMALLER is the case
worth attention: the material listed cannot produce the piece.

The row already carried its own calculated weight, unlabelled as such. This adds
the per-drawing total (Sales Order DUNO Item.calculated_weight), names both for
what they are, and checks the totals actually add up on real data.

Both numbers must also be on the same SCALE, which is what this missed for as long
as it existed. A raw material row carries qty (one piece's steel) and total_weight
(that times the drawing's piece count); the customer figure is for all pieces. The
roll-up summed qty, so a drawing for 4 pieces read 75% short and the "below customer
weight" warning fired on it -- every one of the 30 drawings it had ever flagged on
this site was a multi-piece drawing, and not one was genuinely short. This checked
the roll-up with fixtures whose piece count was 1, where both columns agree and the
bug is invisible, and validated live orders with the same summed column it was
testing. It now uses a piece count of 3 and reads total_weight.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_so_calculated_weight.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.drawing_management.sales_order import drawing_calculated_weight

    print("=== the fields exist and are read-only ===")
    rm = frappe.get_meta("Sales Order Drawing Raw Material")
    duno = frappe.get_meta("Sales Order DUNO Item")
    qty_f = rm.get_field("qty")
    calc_f = duno.get_field("calculated_weight")
    check("row weight is labelled as calculated", qty_f.label, "Calculated Weight (Kg)")
    check("row weight is read-only", bool(qty_f.read_only), True)
    check("row weight says it is auto calculated",
          "Auto calculated" in (qty_f.description or ""), True)
    check("drawing total exists", bool(calc_f), True)
    # "(Total)", pairing it with "Cust Weight (Total)" beside it. It used to read
    # "Calculated Weight (Kg)" -- the same label the per-piece column on the raw
    # material row carries -- so the grid showed two different scales under one name.
    check("drawing total is labelled", calc_f.label, "Calculated Weight (Total)")
    check("and not by the per-piece column's name", calc_f.label == qty_f.label, False)
    check("drawing total is read-only", bool(calc_f.read_only), True)
    check("drawing total is in the grid", bool(calc_f.in_list_view), True)
    check("drawing total says it is auto calculated",
          "Auto calculated" in (calc_f.description or ""), True)
    check("the customer's own figure is still editable",
          bool(duno.get_field("total_weight").read_only), False)

    print()
    print("=== the roll-up sums only its own drawing's rows ===")
    # qty is ONE piece's steel; total_weight is that times the drawing's piece
    # count. These rows are deliberately given a piece count of 3 (total_weight =
    # qty * 3) because summing the wrong column is the bug this whole section
    # exists for, and rows where the two agree cannot tell the difference.
    rows = [
        frappe._dict(customer_drawing_number="CDN-A", qty=10.5, total_weight=31.5),
        frappe._dict(customer_drawing_number="CDN-A", qty=4.25, total_weight=12.75),
        frappe._dict(customer_drawing_number="CDN-B", qty=99.0, total_weight=297.0),
        frappe._dict(customer_drawing_number="", qty=7.0, total_weight=21.0),
    ]
    check("CDN-A adds up", drawing_calculated_weight(rows, "CDN-A"), 44.25)
    check("CDN-B is separate", drawing_calculated_weight(rows, "CDN-B"), 297.0)
    check("an unknown drawing is zero, not an error",
          drawing_calculated_weight(rows, "CDN-NONE"), 0.0)
    check("no rows at all is zero", drawing_calculated_weight([], "CDN-A"), 0.0)
    # The one that would have caught it: summing qty gives 14.75 here.
    check("it is not summing the per-piece column",
          drawing_calculated_weight(rows, "CDN-A") == 14.75, False)

    print()
    print("=== against live orders ===")
    parents = frappe.db.sql(
        """SELECT DISTINCT parent FROM `tabSales Order DUNO Item`
           WHERE parenttype='Sales Order' AND calculated_weight > 0""", as_list=True)
    if not parents:
        print("   (no order carries a calculated weight on this site -- skipped)")
    else:
        bad, under, per_piece_scale, total_rows = [], [], [], 0
        for (so_name,) in parents:
            drawing_rows = frappe.db.sql(
                """SELECT duno_mark_no, drawing_number, total_weight, calculated_weight
                   FROM `tabSales Order DUNO Item` WHERE parent=%s""", so_name, as_dict=True)
            # total_weight, not qty: the all-pieces figure, matching the scale of
            # the customer weight it is compared against. See
            # drawing_calculated_weight and patch rescale_duno_calculated_weight.
            rm_rows = frappe.db.sql(
                """SELECT customer_drawing_number, qty, total_weight
                   FROM `tabSales Order Drawing Raw Material` WHERE parent=%s""",
                so_name, as_dict=True)
            for d in drawing_rows:
                total_rows += 1
                expected = flt(sum(flt(r.total_weight) for r in rm_rows
                                   if r.customer_drawing_number == d.drawing_number), 3)
                per_piece = flt(sum(flt(r.qty) for r in rm_rows
                                    if r.customer_drawing_number == d.drawing_number), 3)
                if abs(expected - flt(d.calculated_weight, 3)) > 0.01:
                    bad.append((so_name, d.duno_mark_no, d.calculated_weight, expected))
                # A multi-piece drawing still holding the per-piece sum is the
                # original bug, stored. Named separately from a plain mismatch so a
                # regression says which way it went.
                if abs(expected - per_piece) > 0.01 \
                        and abs(flt(d.calculated_weight, 3) - per_piece) <= 0.01:
                    per_piece_scale.append((so_name, d.duno_mark_no))
                if flt(d.total_weight) and flt(d.calculated_weight) \
                        and flt(d.calculated_weight) < flt(d.total_weight):
                    under.append((so_name, d.duno_mark_no))
        print("   orders:", len(parents), "| drawing rows:", total_rows)
        for b in bad[:5]:
            print("   MISMATCH %s / %s stored=%s expected=%s" % b)
        check("every stored total matches its own rows", len(bad), 0)
        check("none is still stored on the per-piece scale", per_piece_scale, [])
        # Now a real signal rather than noise: while this was summing qty, every
        # multi-piece drawing landed here and nothing else ever did.
        print("   drawings below customer weight:", under or "none")
        print("   (below is not a failure -- it is the case the summary calls out)")

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
