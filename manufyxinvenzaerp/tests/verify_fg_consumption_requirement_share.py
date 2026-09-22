"""One requirement filled from two batches is still one requirement.

drawing_planned_weight on a raw-material row is the weight of the WHOLE requirement, not
that row's part of it. Fill one requirement from two batches -- drawing 1B3 needs
6,836.131 Kg of ISMB400 and gets 5,452.340 Kg from an ISMB400 bar plus 1,884.000 Kg cut
from a PLATE8 sheet -- and BOTH rows carry 6,836.131.

The finished-goods entry decides how much to consume by asking each line "did you send
more than the drawing needs?". Measured against the whole 6,836.131, neither line looks
oversized, so neither holds anything back -- and the off-cut gets consumed into the job as
though it had been used.

On MIP-2026-00059 that was 128.456 Kg of PLATE8: material standing at the supplier,
booked as steel used in the beams. Stock was never wrong, but the weight sat in the wrong
bucket, and the excess left to return was understated by the same amount.

The requirement is now divided between its rows in proportion to what each carries --
5,080.586 and 1,755.544 -- by requirement_weight_shares, the same rule the transfer popup
and the per-row Excess Qty already use. With it, consumption lands exactly on the plan's
own planned weight and the whole excess stays where it is.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_consumption_requirement_share.run
"""

import inspect

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.subcontracting_management import subcontracting as sub
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        requirement_weight_shares,
    )

    print("=== the consumption cap uses the row's share, not the whole requirement ===")
    src = inspect.getsource(sub._consumption_for_completed)
    check("it asks for the shares", "row_share = requirement_weight_shares(rows)" in src, True)
    check("...and caps each row on its own", "wanted = flt(wanted_share) or flt(r.reqd_kg)" in src, True)
    check("the unshared read is gone",
          "wanted = flt(r.drawing_planned_weight) or flt(r.reqd_kg)" in src, False)
    check("the fields the key needs are fetched",
          all(f in src for f in ('"sales_order"', '"customer_drawing_number"',
                                 '"item_number"', '"qty"')), True)

    print()
    print("=== the split itself ===")
    # 1B3's ISMB400 requirement, filled from a bar and a plate.
    rows = [
        frappe._dict(sales_order="SO", customer_drawing_number="1B3", item_number="1w27",
                     item_code="ISMB400", qty=5452.340, drawing_planned_weight=6836.131),
        frappe._dict(sales_order="SO", customer_drawing_number="1B3", item_number="1w27",
                     item_code="ISMB400", qty=1884.000, drawing_planned_weight=6836.131),
    ]
    shares = requirement_weight_shares(rows)
    check("the bar's share", flt(shares[0], 3), 5080.587)
    check("the plate's share", flt(shares[1], 3), 1755.544)
    check("they add back to the requirement", flt(sum(shares), 3), 6836.131)
    check("and not to twice it", flt(sum(shares), 3) == flt(2 * 6836.131, 3), False)

    print()
    print("=== live: consumption lands on the plan's own planned weight ===")
    sco_name = "SC-ORD-2026-00025"
    mip_name = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": sco_name}, "name")
    if not (frappe.db.exists("Subcontracting Order", sco_name) and mip_name):
        print("  SKIP %s not on this site" % sco_name)
    else:
        sco = frappe.get_doc("Subcontracting Order", sco_name)
        mip = frappe.get_doc("Material Issue Plan", mip_name)
        wh = sub._get_sco_supplier_warehouse(sco)
        available = sub._get_supplier_wh_consumption_items(sco, wh)
        preview = sub.get_final_stock_entry_preview(sco_name)
        consumed = sub._consumption_for_completed(sco, wh, preview, available)

        at_supplier = flt(sum(flt(r["qty"]) for r in available), 3)
        total = flt(sum(flt(r["qty"]) for r in consumed), 3)
        left = flt(at_supplier - total, 3)

        check("every drawing is finished, so the whole plan is consumed",
              total, flt(mip.total_planned_weight_kg, 3))
        check("what stays behind is exactly the excess",
              left, flt(mip.excess_weight_kg, 3))
        check("the booked return still fits inside it",
              left >= flt(mip.excess_return_total_kg, 3), True)

        by_item = {r["item_code"]: flt(r["qty"], 3) for r in consumed}
        check("PLATE8 consumes its drawing share, not its whole transfer",
              by_item.get("PLATE8"), 3021.054)
        check("...which is 128.456 Kg less than before the fix",
              flt(3149.510 - by_item.get("PLATE8", 0), 3), 128.456)

    print()
    total_c, passed = len(checks), sum(1 for c in checks if c)
    if passed == total_c:
        print("ALL %d CHECKS PASSED" % total_c)
    else:
        print("%d of %d CHECKS FAILED" % (total_c - passed, total_c))
