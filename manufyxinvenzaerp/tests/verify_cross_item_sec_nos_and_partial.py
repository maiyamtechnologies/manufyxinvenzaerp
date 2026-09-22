"""A substituted batch is weighed as itself, and only its own rows are reported on.

Two faults surfaced the first time a line was actually moved across items — an ISMB450
requirement onto a PLATE40 sheet on MIP-2026-00060.

**Sec Nos came out as a bar.** _sec_nos_for_weight_arm took the unit weight and the item
group from the row's own item, which before cross-item reassignment was always the batch's
item too. It weighed one piece as 12 m x 72.4 kg/m = 868.8 Kg — an ISMB450 bar that is not
there — instead of 12 x 2.5 x 0.04 x 7850 = 9,420 Kg, which is what a PLATE40 sheet weighs.
530.804 Kg read as 0.611 pieces rather than 0.056.

That is not cosmetic. _qty_for_sec treats a Sec Nos BELOW the planned figure as a partial
transfer and caps the Kg at the plan's own. With 1.833 on the line, typing 1 to send one
whole sheet would have been read as sending less, capped back to 1,592.412 Kg, and the
7,827.588 Kg of off-cut would never have appeared as excess.

**The shortfall warning belonged to someone else.** reserve_exact_match_batches reserves
the WHOLE plan and reports every row it cannot fill. MP-2026-00260 has three ISMB400 rows
8,870.400 Kg short because that steel has already shipped — nothing to do with the
reassignment, and every one of the three rows actually moved was reserved in full. The
dialog said "3 row(s) could only be partly reserved (8870.4 Kg short)" about rows that
were complete.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_cross_item_sec_nos_and_partial.run
"""

import inspect

import frappe
from frappe.utils import flt

checks = []

SHEET = 12 * 2.5 * 0.04 * 7850      # one 12000x2500x40 PLATE40 sheet = 9,420 Kg
BAR = 12 * 72.4                     # one 12 m ISMB450 bar = 868.8 Kg


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _row(**kw):
    r = frappe._dict(kw)
    r.get = lambda f, d=None: dict.get(r, f, d)
    return r


def run():
    from manufyxinvenzaerp.production_management.doctype.material_planning import (
        material_planning as mp_mod,
    )
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_batch_update as bu

    print("=== a piece is weighed as the batch's item, not the requirement's ===")
    src = inspect.getsource(mp_mod._sec_nos_for_weight_arm)
    check("the batch's item is resolved",
          'batch_item = row.get("planned_item") or row.item_code' in src, True)
    check("the unit weight comes from it", 'get_value("Item", batch_item, "custom_unit_weight")' in src, True)
    check("so does the item group", 'custom_parent_item_group' in src, True)
    check("the caller passes both", "groups.get(batch_item) or row.parent_item_group" in
          inspect.getsource(mp_mod.MaterialPlanning._apply_rwd_fractional_nos), True)

    print()
    print("=== the arithmetic ===")
    plate = _row(item_code="ISMB450", planned_item="PLATE40", parent_item_group="Structurals",
                 length=12000.0, width=2500.0, thickness=40.0)
    check("530.804 Kg on a 9,420 Kg sheet", flt(mp_mod._sec_nos_for_weight_arm(plate, 530.804), 3),
          flt(530.804 / SHEET, 3))
    check("   ...which is 0.056, not 0.611", flt(mp_mod._sec_nos_for_weight_arm(plate, 530.804), 3), 0.056)
    bar = _row(item_code="ISMB450", planned_item=None, parent_item_group="Structurals",
               length=12000.0, width=0.0, thickness=0.0)
    check("an unsubstituted bar is unchanged", flt(mp_mod._sec_nos_for_weight_arm(bar, 530.804), 3),
          flt(530.804 / BAR, 3))

    print()
    print("=== why it mattered: a Sec Nos below the plan is read as a PARTIAL transfer ===")
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as mipt
    qsrc = inspect.getsource(mipt._qty_for_sec)
    check("typing less than planned caps the Kg", "qty = min(qty, flt(planned_qty, 3))" in qsrc, True)
    # The line as it was: the sheet's dimensions, but the bar's group, unit weight and
    # Sec Nos. That is the nasty part -- the three the formula reads (group, length,
    # unit weight) agreed with each other and with the stored Sec Nos, so
    # _line_kg_per_piece trusted them and priced a piece at 12 m x 72.4 = 868.8 Kg. A
    # bar, confidently, from a sheet's row. Typing 1 then reads as LESS than the plan
    # and is capped: the line would have shipped 868.8 Kg against a 1,592.412 Kg
    # requirement -- not a whole sheet, not even the requirement.
    line_wrong = {"qty": 1592.412, "custom_sec_qty": 1.833, "source_rows": 3,
                  "custom_length": 12000, "custom_width": 2500, "custom_thickness": 40,
                  "custom_unit_weight": 72.4, "custom_parent_item_group": "Structurals"}
    piece_wrong, from_dims_wrong = mipt._line_kg_per_piece(line_wrong)
    check("the old line looked self-consistent", from_dims_wrong, True)
    check("   ...and priced one 'piece' as a bar", flt(piece_wrong, 1), flt(BAR, 1))
    check("   ...and typing 1 sent less than the requirement",
          flt(mipt._qty_for_sec(line_wrong, 1)[0], 3) < 1592.412, True)

    # The line as it is now: the sheet's dimensions, group and unit weight together.
    line_right = {"qty": 1592.412, "custom_sec_qty": 0.168, "source_rows": 3,
                  "custom_length": 12000, "custom_width": 2500, "custom_thickness": 40,
                  "custom_unit_weight": 7.85, "custom_parent_item_group": "Plates"}
    piece_right, from_dims_right = mipt._line_kg_per_piece(line_right)
    check("the line is now priced from its dimensions", from_dims_right, True)
    check("   ...one piece is one sheet", flt(piece_right, 3), flt(SHEET, 3))
    check("   ...typing 1 sends the whole sheet",
          flt(mipt._qty_for_sec(line_right, 1)[0], 3), flt(SHEET, 3))
    check("   ...leaving the off-cut as excess",
          flt(mipt._qty_for_sec(line_right, 1)[0] - 1592.412, 3), flt(SHEET - 1592.412, 3))

    print()
    print("=== the shortfall warning names only the rows that moved ===")
    apply_src = inspect.getsource(bu._apply_to_one_plan)
    check("the rows touched are collected",
          "touched = {w.member.source_row for w in plan_writes}" in apply_src, True)
    check("both reserve calls are filtered", apply_src.count('if p.get("name") in touched') == 2, True)
    res = inspect.getsource(mp_mod.reserve_exact_match_batches)
    check("a partial row carries its name", '"name": row.name,' in res, True)

    print()
    print("=== live: MIP-2026-00060's reassigned line ===")
    if not frappe.db.exists("Material Issue Plan", "MIP-2026-00060"):
        print("  SKIP not on this site")
    else:
        m = frappe.get_doc("Material Issue Plan", "MIP-2026-00060")
        line = next((c for c in m.consolidate_items if c.item_code == "PLATE40"), None)
        if not line:
            print("  SKIP the line has not been reassigned to PLATE40")
        else:
            check("the line is on the PLATE40 sheet", line.batch_no, "PLT40-P40-L12000-W2500-SR001")
            check("its weight is unchanged", flt(line.qty, 3), 1592.412)
            check("its Sec Nos is a share of a sheet", flt(line.sec_qty, 3), 0.168)
            rows = frappe.get_all(
                "Material Planning Available Raw Material",
                {"parent": "MP-2026-00260", "planned_item": "PLATE40"},
                ["idx", "item_code", "sec_qty", "required_qty", "is_reserved",
                 "reserved_qty", "shortfall_qty"], order_by="idx")
            check("3 plan rows carry the substitution", len(rows), 3)
            check("every one is fully reserved",
                  all(r.is_reserved and flt(r.shortfall_qty, 3) == 0
                      and flt(r.reserved_qty, 3) == flt(r.required_qty, 3) for r in rows), True)
            check("every one is weighed as a sheet",
                  sorted({flt(r.sec_qty, 3) for r in rows}), [0.056])
            check("the requirement is still ISMB450",
                  sorted({r.item_code for r in rows}), ["ISMB450"])

            print()
            print("=== live: the plan row describes a sheet, all three ways ===")
            mip_rows = [r for r in m.raw_materials if (r.planned_item or r.item_code) == "PLATE40"]
            check("3 rows on the plan", len(mip_rows), 3)
            check("the group is the sheet's",
                  sorted({r.parent_item_group for r in mip_rows}), ["Plates"])
            check("so is the unit weight", sorted({flt(r.unit_weight) for r in mip_rows}), [7.85])
            check("and the dimensions",
                  sorted({(flt(r.length), flt(r.width), flt(r.thickness)) for r in mip_rows}),
                  [(12000.0, 2500.0, 40.0)])
            live = {"qty": flt(line.qty, 3), "custom_sec_qty": flt(line.sec_qty, 3),
                    "source_rows": line.source_rows,
                    "custom_length": flt(mip_rows[0].length),
                    "custom_width": flt(mip_rows[0].width),
                    "custom_thickness": flt(mip_rows[0].thickness),
                    "custom_unit_weight": flt(mip_rows[0].unit_weight),
                    "custom_parent_item_group": mip_rows[0].parent_item_group}
            piece, from_dims = mipt._line_kg_per_piece(live)
            check("the live line prices a piece from its dimensions", from_dims, True)
            check("   ...at one whole sheet", flt(piece, 3), flt(SHEET, 3))
            check("   ...so rounding to 1 sends 9,420.000 Kg",
                  flt(mipt._qty_for_sec(live, 1)[0], 3), flt(SHEET, 3))
            check("   ...and books 7,827.588 Kg of excess",
                  flt(mipt._qty_for_sec(live, 1)[0] - flt(line.qty), 3), 7827.588)

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
