"""A requirement's planned weight is counted ONCE, split across the rows that fill it,
and never shared between the CNC leg and the direct leg.

Three defects put phantom shortfalls on the transfer popup's consolidated excess tab of
MIP-2026-00050, a plan whose mapping covered its requirement exactly (true excess 0.000
on every item):

  ISMB400  -6,836.131 Kg  one requirement (drawing 1B3, 6,836.131 Kg) filled from a
                          12000 mm bar and a 5136 mm off-cut. The requirement key
                          included the row's dimensions -- which on a plan row are the
                          BATCH's, not the cut's -- so one requirement looked like two
                          and claimed its weight twice.
  PLATE10    -44.077 Kg   one batch feeding both a CNC drawing and a direct one makes
                          TWO pending lines. The weight map was keyed (item, batch) with
                          no leg, so the whole 51.935 Kg requirement was handed to both;
                          the direct line compared it against the 7.858 Kg it carries.
  ISA100    +19.072 Kg    drawing 1B5 needs ISA100 at 320 mm (9.536 Kg) and 390 mm
                          (11.622 Kg). The dimensional match missed for the reason
                          above and fell through to a loose drawing+item lookup where
                          "first row wins", so both requirements were measured against
                          11.622 Kg.

The fix carries the requirement's own Item No onto the plan row and keys off that.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_mip_drawing_weight_share.run
"""

import inspect

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _row(**kw):
    """A stand-in for a raw-material row: the helpers read it with .get()."""
    return frappe._dict(kw)


def run():
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        requirement_key,
        requirement_weight_shares,
        _lookup_drawing_planned_weight,
    )
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as mipt

    print("=== a requirement split across two batch SIZES is one requirement ===")
    # Drawing 1B3 needs 6,836.131 Kg of ISMB400, filled from a 12000 mm bar and a
    # 5136 mm off-cut. Both rows carry the whole requirement's weight.
    split = [
        _row(sales_order="SO", customer_drawing_number="1B3", item_number="1w27",
             item_code="ISMB400", qty=5452.340, length=12000, drawing_planned_weight=6836.131),
        _row(sales_order="SO", customer_drawing_number="1B3", item_number="1w27",
             item_code="ISMB400", qty=1383.791, length=5136, drawing_planned_weight=6836.131),
    ]
    check("both rows share one requirement key",
          requirement_key(split[0]) == requirement_key(split[1]), True)
    shares = requirement_weight_shares(split)
    check("shares add back to the requirement", flt(sum(shares), 3), 6836.131)
    check("first row's share matches what it carries", shares[0], 5452.340)
    check("second row's share matches what it carries", shares[1], 1383.791)

    print()
    print("=== one drawing needing an item in two sizes keeps two requirements ===")
    two_sizes = [
        _row(sales_order="SO", customer_drawing_number="1B5", item_number="1a3",
             item_code="ISA100", qty=9.536, length=12000, drawing_planned_weight=9.536),
        _row(sales_order="SO", customer_drawing_number="1B5", item_number="1a5",
             item_code="ISA100", qty=11.622, length=12000, drawing_planned_weight=11.622),
    ]
    check("different Item No means different requirement",
          requirement_key(two_sizes[0]) != requirement_key(two_sizes[1]), True)
    check("both requirements counted", flt(sum(requirement_weight_shares(two_sizes)), 3), 21.158)

    print()
    print("=== an alternate item issued against a requirement is still that requirement ===")
    # MIP-2026-00007: a 56.167 Kg PLATE25 requirement filled by one PLATE25 batch and
    # one FLAT batch. Keying on the batch's item splits it in two, each claiming the
    # whole 56.167 Kg -- the same double count, arriving by the other door.
    alternate = [
        _row(sales_order="SO", customer_drawing_number="Type-2", item_number="15",
             item_code="PLATE25", qty=56.139, drawing_planned_weight=56.167),
        _row(sales_order="SO", customer_drawing_number="Type-2", item_number="15",
             item_code="PLATE25", planned_item="FLAT", qty=86.350,
             drawing_planned_weight=56.167),
    ]
    check("the alternate row shares the requirement key",
          requirement_key(alternate[0]) == requirement_key(alternate[1]), True)
    check("the requirement is still counted once",
          flt(sum(requirement_weight_shares(alternate)), 3), 56.167)

    print()
    print("=== rows with no Item No do not all collapse into one requirement ===")
    # MIP-2026-00004 carries rows predating the field: 1B7 needs ISA100 in two lengths.
    # Merging them made the group take whichever weight came first and lose the other.
    legacy = [
        _row(sales_order="SO", customer_drawing_number="1B7", item_code="ISA100",
             qty=9.536, drawing_planned_weight=9.536),
        _row(sales_order="SO", customer_drawing_number="1B7", item_code="ISA100",
             qty=11.622, drawing_planned_weight=11.622),
    ]
    check("two different weights stay two requirements",
          requirement_key(legacy[0]) != requirement_key(legacy[1]), True)
    check("neither requirement is lost",
          flt(sum(requirement_weight_shares(legacy)), 3), 21.158)

    split_no_item_no = [
        _row(sales_order="SO", customer_drawing_number="1B3", item_code="ISMB400",
             qty=5452.340, drawing_planned_weight=6836.131),
        _row(sales_order="SO", customer_drawing_number="1B3", item_code="ISMB400",
             qty=1383.791, drawing_planned_weight=6836.131),
    ]
    check("but one requirement split across batches still merges",
          requirement_key(split_no_item_no[0]) == requirement_key(split_no_item_no[1]), True)
    check("and is still counted once",
          flt(sum(requirement_weight_shares(split_no_item_no)), 3), 6836.131)

    print()
    print("=== the identity is the Item No, not the dimensions ===")
    # Behaviour, not a grep of the source: two rows of one requirement drawn from
    # batches of different sizes must key the same. The batch's dimensions are on the
    # row and must play no part.
    dims_differ = (
        _row(sales_order="SO", customer_drawing_number="1B3", item_number="1w27",
             item_code="ISMB400", qty=1.0, length=12000, width=0, thickness=0,
             drawing_planned_weight=10.0),
        _row(sales_order="SO", customer_drawing_number="1B3", item_number="1w27",
             item_code="ISMB400", qty=1.0, length=5136, width=250, thickness=8,
             drawing_planned_weight=10.0),
    )
    check("dimensions play no part in the identity",
          requirement_key(dims_differ[0]) == requirement_key(dims_differ[1]), True)
    check("the Item No does", "1w27" in requirement_key(dims_differ[0]), True)
    check("lookup tries Item No first",
          inspect.getsource(_lookup_drawing_planned_weight).index("by_item_no")
          < inspect.getsource(_lookup_drawing_planned_weight).index('cached["exact"]'), True)

    print()
    print("=== the CNC leg and the direct leg never share a weight ===")
    src = inspect.getsource(mipt.get_mip_pending_items)
    check("weight map is keyed by the CNC leg",
          "1 if (r.cnc_process and cnc_warehouse) else 0" in src, True)
    check("weight map is read with the leg",
          "drawing_wt_by_key.get((item_code, batch_no, 1 if is_cnc else 0)" in src, True)
    check("the old leg-blind read is gone",
          "drawing_wt_by_key.get((item_code, batch_no), 0)" in src, False)
    check("the local copy of the share rule is gone", "req_totals" in src, False)

    print()
    print("=== live: MIP-2026-00050 covers its requirement exactly ===")
    # The plan this was found on. Both legs together must move exactly what the five
    # drawings call for -- any non-zero total here is the bug coming back.
    #
    # A plan stops being useful here once everything on it has shipped -- pending goes
    # empty and the loops below would silently assert nothing, so say so out loud
    # rather than reporting a pass that exercised no data.
    if not frappe.db.exists("Material Issue Plan", "MIP-2026-00050"):
        print("  SKIP MIP-2026-00050 is not on this site")
    elif not mipt.get_mip_pending_items("MIP-2026-00050"):
        print("  SKIP MIP-2026-00050 has nothing left pending (fully transferred) --")
        print("       the live comparison needs a plan with material still to send.")
    else:
        pending = mipt.get_mip_pending_items("MIP-2026-00050")
        by_item = {}
        for p in pending:
            e = by_item.setdefault(p["item_code"], {"drawing": 0.0, "transfer": 0.0})
            e["drawing"] = flt(e["drawing"] + flt(p.get("drawing_planned_weight")), 3)
            e["transfer"] = flt(e["transfer"] + flt(p.get("qty")), 3)
        for item_code in sorted(by_item):
            e = by_item[item_code]
            check("%s: excess is 0.000 Kg" % item_code,
                  flt(e["transfer"] - e["drawing"], 3), 0.0)

        print()
        print("  -- each leg is measured against its own share --")
        legs = {}
        for p in pending:
            if p["item_code"] != "PLATE10":
                continue
            legs["CNC" if p.get("cnc_process") else "direct"] = (
                flt(p.get("qty"), 3), flt(p.get("drawing_planned_weight"), 3))
        for leg in sorted(legs):
            qty, drawing = legs[leg]
            check("PLATE10 %s leg: planned weight is not the whole item's" % leg,
                  drawing <= qty + 0.001, True)

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
