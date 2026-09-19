"""Rounding dust left in a batch is not offered to the next requirement.

MP-2026-00129: batch ISMB450-L7331-R005 holds 3 pieces (1,592.413 Kg). Three drawings
(1B5, 1B6, 1B7) each need one piece; the requirement rows carry more decimals than they
show (~530.80395 Kg), so 0.00115 Kg was left over -- just above the 0.001 Kg line -- and
Check Stock Availability handed it to the fourth drawing, 1B8: a 0.001 Kg / 0 Nos Exact
Match row on R005, and the rest of 1B8 (530.803 Kg) on the newly bought batch R037.

A batch that counts its pieces now only has free stock while what is left is worth at
least 0.001 Nos (material_planning._batch_has_free_stock).

The allocation is run through the real check_stock_availability with the batch stock
stood in (the same two batches, as data), so nothing on the site is read or written
beyond the item master of ISMB450, which is only read.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_mp_batch_dust.run
"""

import frappe
from frappe.utils import flt

checks = []

ITEM = "ISMB450"
WH = "Stores - MIPL"
LENGTH = 7331.55
REQUIRED = 530.80395  # one piece, as the requirement rows actually carry it


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-70s %s got=%r want=%r" % (label, "OK  " if ok else "FAIL", got, want))


def _batch(name, kg, nos):
    return {"batch_no": name, "qty": kg, "custom_sec_qty": nos, "custom_sec_uom": "Nos",
            "custom_length": LENGTH, "custom_thickness": 0, "custom_width": 0}


def _unit():
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        _batch_has_free_stock,
    )

    print("\n=== _batch_has_free_stock ===")
    check("0.00115 Kg left of a 3-piece 1,592.413 Kg bar: dust", _batch_has_free_stock(0.00115, 1592.413, 3), False)
    check("0.01 Kg left of the same bar: still dust (0.00002 Nos)", _batch_has_free_stock(0.01, 1592.413, 3), False)
    check("half a piece left (265.4 Kg): real stock", _batch_has_free_stock(265.4, 1592.413, 3), True)
    check("a whole piece left: real stock", _batch_has_free_stock(530.804, 1592.413, 3), True)
    check("batch without a piece count, 0.002 Kg: real stock", _batch_has_free_stock(0.002, 100, 0), True)
    check("0.001 Kg or less is never free", _batch_has_free_stock(0.001, 100, 0), False)


def _check(batches):
    """Run the real check_stock_availability for the four drawings against `batches`."""
    from manufyxinvenzaerp.production_management.doctype.material_planning import material_planning as mp
    from manufyxinvenzaerp.production_plan_management import production_plan as pp

    doc = frappe._dict({
        "name": "", "company": frappe.defaults.get_global_default("company"),
        "for_warehouse": WH, "raw_materials": [
            {"item_code": ITEM, "item_name": ITEM, "duno_mark_no": duno, "qty": REQUIRED,
             "sec_qty": 1, "sec_uom": "Nos", "uom": "Kg", "length": LENGTH, "width": 0,
             "thickness": 0, "unit_weight": 72.4, "parent_item_group": "Structurals",
             "bom_no": "", "drawing": ""}
            for duno in ("1B5", "1B6", "1B7", "1B8")
        ],
    })
    saved = (pp.get_sbb_batches_bulk, mp._get_batch_reserved_by_others_bulk)
    pp.get_sbb_batches_bulk = lambda item_codes, warehouse, location=None: {ITEM: [dict(b) for b in batches]}
    mp._get_batch_reserved_by_others_bulk = lambda batch_nos, mp_name, exclude_table=None: {}
    try:
        res = mp.check_stock_availability(doc)
    finally:
        pp.get_sbb_batches_bulk, mp._get_batch_reserved_by_others_bulk = saved
    by_duno = {}
    for r in res["available_raw_materials"]:
        by_duno.setdefault(r["duno_mark_no"], []).append(
            (r["batch_no"], flt(r["required_qty"], 3), flt(r["sec_qty"], 3)))
    short = {r["duno_mark_no"]: (flt(r["qty"], 3), flt(r["sec_qty"], 3)) for r in res.get("material_mapping") or []}
    return res["available_raw_materials"], by_duno, short


def _allocation():
    r005, r037 = _batch("ZZDUST-R005", 1592.413, 3), _batch("ZZDUST-R037", 530.804, 1)

    # What MP-2026-00129 saw at Check Stock Availability: only the 3-piece bar in stock.
    print("\n=== only the 3-piece bar in stock (as on MP-2026-00129 before the purchase) ===")
    rows, by_duno, short = _check([r005])
    check("three Exact Match rows, none for 1B8", sorted(by_duno), ["1B5", "1B6", "1B7"])
    check("no 0 Nos row", [r for r in rows if not flt(r["sec_qty"])], [])
    check("1B8 short by one whole piece: 530.804 Kg, 1 Nos", short.get("1B8"), (530.804, 1.0))

    # After the purchase the new bar is in stock too.
    print("\n=== the 3-piece bar and the newly bought 1-piece bar ===")
    rows, by_duno, short = _check([r005, r037])
    check("four Exact Match rows, one per drawing", len(rows), 4)
    for duno in ("1B5", "1B6", "1B7"):
        check("%s: one piece of the 3-piece bar" % duno, by_duno.get(duno), [("ZZDUST-R005", 530.804, 1.0)])
    check("1B8: one whole piece of the new bar, not split", by_duno.get("1B8"), [("ZZDUST-R037", 530.804, 1.0)])
    check("nothing short", short, {})


def _old_rule_reproduces():
    """The same scenario under the old Kg-only rule gives the 0 Nos dust row seen live,
    so the checks above would catch the bug coming back."""
    from manufyxinvenzaerp.production_management.doctype.material_planning import material_planning as mp

    print("\n=== the old Kg-only rule, for contrast ===")
    new_rule = mp._batch_has_free_stock
    mp._batch_has_free_stock = lambda remaining, total_kg, total_sec: flt(remaining) > mp.BATCH_FREE_EPSILON
    try:
        rows, by_duno, short = _check([_batch("ZZDUST-R005", 1592.413, 3)])
    finally:
        mp._batch_has_free_stock = new_rule
    check("old rule: 1B8 gets a 0.001 Kg / 0 Nos row on the 3-piece bar",
          by_duno.get("1B8"), [("ZZDUST-R005", 0.001, 0.0)])
    check("old rule: and is short by only 530.803 Kg", short.get("1B8", (None,))[0], 530.803)


def run():
    print("=== verify_mp_batch_dust ===")
    _unit()
    _allocation()
    _old_rule_reproduces()
    print()
    failed = checks.count(False)
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, len(checks)))
    else:
        print("ALL %d CHECKS PASSED" % len(checks))
