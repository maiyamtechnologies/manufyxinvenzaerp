"""Material Planning: Check stock without dimensions, the re-check after a purchase,
and Allocate from Purchase Receipt (.claude/tasks/sep20_mp_stock_matching.md).

Why: on MP-2026-00129 a receipt's stock was reserved, unreserved, and a re-check sent 76
requirements back to purchase -- the Material Request still looked "in progress" after
delivery, and the purchase came in consolidated sizes Exact Match never matches.

Part A runs the real check_stock_availability with the batch stock stood in (as data):
  1. box off: today's behaviour -- only the drawing's own size matches
  2. box on: same item, any size, own size first; Reserve stock without dimensions,
     batch's dimensions, Nos = Kg / the batch's piece weight (fractional)
  3. short stock: Exact Match for what there is, Material Mapping for the rest
  4. re-check after a purchase: stock matched first; a requirement still being bought
     keeps its Unavailable row only for what stock can't cover, and only while the
     Material Request has quantity to receive
  5. box on keeps reserved rows: their Kg covers the requirement, their batch is not
     offered again, a batch held in Material Mapping is not offered to Exact Match
Part B runs allocate_receipt_to_plan on a real (draft) Material Planning and real
batches, inside ONE transaction that is rolled back (commit is a no-op), comparing
tabSeries before and after so no document or series number is left behind. Its rows go
to Material Mapping (Alternate Stock) -- a batch of another size belongs there -- filling
a row already waiting for a batch where there is one.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_mp_stock_without_dimensions.run
"""

import frappe
from frappe.utils import flt

checks = []

ITEM = "ISMB250"   # Structurals, 37.3 Kg/m -- read only
UW = 37.3
WH = "Stores - MIPL"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-72s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def piece(length):
    return flt(length / 1000 * UW, 3)


def batch(name, length, nos):
    return {"batch_no": name, "qty": flt(piece(length) * nos, 3), "custom_sec_qty": nos,
            "custom_sec_uom": "Nos", "custom_length": length, "custom_width": 0, "custom_thickness": 0}


def req(duno, length, nos, item_no="1w11"):
    return {"item_code": ITEM, "item_name": ITEM, "duno_mark_no": duno, "item_number": item_no,
            "qty": flt(piece(length) * nos, 3), "sec_qty": nos, "sec_uom": "Nos", "uom": "Kg",
            "length": length, "width": 0, "thickness": 0, "unit_weight": UW,
            "parent_item_group": "Structurals", "bom_no": "", "drawing": ""}


# ── Part A ──────────────────────────────────────────────────────────────────────

def _check(batches, requirements, without_dims, held=None, pending=None, **extra):
    from manufyxinvenzaerp.production_management.doctype.material_planning import material_planning as mp
    from manufyxinvenzaerp.production_plan_management import production_plan as pp

    doc = frappe._dict(dict({
        "name": "ZZ-NO-SUCH-MP", "company": frappe.defaults.get_global_default("company"),
        "for_warehouse": WH, "check_stock_without_dimensions": 1 if without_dims else 0,
        "raw_materials": requirements,
    }, **extra))
    saved = (pp.get_sbb_batches_bulk, mp._get_batch_reserved_by_others_bulk, mp._pending_purchase_items)
    pp.get_sbb_batches_bulk = lambda item_codes, warehouse, location=None: {ITEM: [dict(b) for b in batches]}
    mp._get_batch_reserved_by_others_bulk = lambda nos, mp_name, exclude_table=None: dict(held or {})
    mp._pending_purchase_items = lambda mp_name: set(pending or [])
    try:
        return mp.check_stock_availability(doc)
    finally:
        pp.get_sbb_batches_bulk, mp._get_batch_reserved_by_others_bulk, mp._pending_purchase_items = saved


def arm_view(res):
    return [(r["duno_mark_no"], r["batch_no"], flt(r["required_qty"], 3), flt(r["sec_qty"], 3),
             int(r.get("reserve_without_dimensions") or 0), flt(r["length"])) for r in res["available_raw_materials"]]


def part_a():
    long_bar = batch("ZZ-LONG-7479", 7479.1, 2)       # consolidated purchase size
    exact_bar = batch("ZZ-EXACT-879", 879.1, 1)        # the drawing's own size
    reqs = [req("1B1", 879.1, 1), req("1B2", 3186.0, 1, "1w12")]

    print("\n=== 1. box off: only the drawing's own size matches ===")
    res = _check([long_bar, exact_bar], reqs, False)
    check("1B1 on its own-size bar", [(d, b) for d, b, *_ in arm_view(res)], [("1B1", "ZZ-EXACT-879")])
    check("1B2 (3,186 mm) not matched -> Material Mapping",
          [(r["duno_mark_no"], r["batch_mapped"]) for r in res["material_mapping"]], [("1B2", "Not Mapped")])
    check("no reserved rows kept flag", res["kept_reserved"], False)

    print("\n=== 2. box on: same item, any size, own size first, fractional Nos ===")
    res = _check([long_bar, exact_bar], reqs, True)
    kg2 = piece(3186.0)
    check("1B1 still takes its own-size bar first", arm_view(res)[0][:2], ("1B1", "ZZ-EXACT-879"))
    check("1B2 takes the 7,479 mm bar: exact Kg, Nos = Kg / bar piece, RWD, bar's length",
          arm_view(res)[1], ("1B2", "ZZ-LONG-7479", kg2, flt(kg2 / piece(7479.1), 3), 1, 7479.1))
    check("nothing left to buy", res["material_mapping"] + res["unavailable_items"], [])

    print("\n=== 3. box on, not enough: what there is, and the rest to Material Mapping ===")
    small = batch("ZZ-SHORT-500", 500.0, 1)            # 18.65 Kg, requirement 118.838 Kg
    res = _check([small], [req("1B2", 3186.0, 1, "1w12")], True)
    have = piece(500.0)
    check("Exact Match takes the whole 500 mm bar", [(r[1], r[2]) for r in arm_view(res)], [("ZZ-SHORT-500", have)])
    short = res["material_mapping"]
    check("Material Mapping keeps the shortfall in Kg", [flt(r["qty"], 3) for r in short], [flt(piece(3186.0) - have, 3)])
    check("... and in the drawing's own pieces",
          [flt(r["sec_qty"], 3) for r in short], [flt((piece(3186.0) - have) / piece(3186.0), 3)])

    print("\n=== 4. re-check after a purchase ===")
    ua = [dict(req("1B2", 3186.0, 1, "1w12"), consolidated_into="ISMB250")]
    res = _check([long_bar], [req("1B2", 3186.0, 1, "1w12")], True, pending=[ITEM], unavailable_items=ua)
    check("received stock covers it -> matched, Unavailable row dropped",
          ([r[0] for r in arm_view(res)], res["unavailable_items"]), (["1B2"], []))
    res = _check([], [req("1B2", 3186.0, 1, "1w12")], True, pending=[ITEM], unavailable_items=ua)
    check("nothing received yet -> the Unavailable row stays (still being bought)",
          [(r["duno_mark_no"], flt(r["qty"], 3)) for r in res["unavailable_items"]], [("1B2", piece(3186.0))])
    check("... and is not asked for twice in Material Mapping", res["material_mapping"], [])
    res = _check([small], [req("1B2", 3186.0, 1, "1w12")], True, pending=[ITEM], unavailable_items=ua)
    check("part received -> Unavailable row kept for the remainder only",
          [flt(r["qty"], 3) for r in res["unavailable_items"]], [flt(piece(3186.0) - piece(500.0), 3)])
    res = _check([], [req("1B2", 3186.0, 1, "1w12")], True, pending=[], unavailable_items=ua)
    check("Material Request fully received -> no longer protected, goes to Material Mapping",
          ([r["duno_mark_no"] for r in res["material_mapping"]], res["unavailable_items"]), (["1B2"], []))

    print("\n=== 5. box on keeps reserved rows ===")
    reserved_arm = {"item_code": ITEM, "duno_mark_no": "1B1", "item_number": "1w11", "batch_no": "ZZ-EXACT-879",
                    "required_qty": piece(879.1), "reserved_qty": piece(879.1), "is_reserved": 1}
    res = _check([long_bar, exact_bar], reqs, True, available_raw_materials=[reserved_arm])
    check("1B1 already reserved: no new row for it", [r[0] for r in arm_view(res)], ["1B2"])
    check("result says reserved rows were kept", res["kept_reserved"], True)
    other = [req("1B9", 879.1, 1, "1w99")]
    res = _check([exact_bar], other, True, available_raw_materials=[reserved_arm])
    check("the reserved bar is not offered to another drawing", arm_view(res), [])
    held_mm = {"item_code": ITEM, "duno_mark_no": "1B7", "item_number": "1w70", "batch": "ZZ-LONG-7479",
               "qty": 10.0, "is_reserved": 1}
    res = _check([long_bar], [req("1B2", 3186.0, 1, "1w12")], True, material_mapping=[held_mm])
    check("a bar held in Material Mapping is not offered to Exact Match", arm_view(res), [])


# ── Part B ──────────────────────────────────────────────────────────────────────

def part_b():
    from manufyxinvenzaerp.production_management.doctype.material_planning import material_planning as mp
    from manufyxinvenzaerp.production_plan_management import production_plan as pp

    print("\n=== B. Allocate from Purchase Receipt (into Material Mapping) ===")
    pr_name = frappe.db.get_value("Purchase Receipt", {"docstatus": 1}, "name")
    stamp = frappe.generate_hash(length=6).upper()
    names = {k: "ZZALLOC-%s-%s" % (stamp, k) for k in ("LONG", "EXACT", "OWNSIZE", "HELD")}
    for bn in names.values():
        frappe.get_doc({"doctype": "Batch", "batch_id": bn, "item": ITEM}).insert(ignore_permissions=True)
    stock = [dict(batch(names["LONG"], 7479.1, 2)), dict(batch(names["EXACT"], 879.1, 1)),
             dict(batch(names["OWNSIZE"], 879.1, 1)), dict(batch(names["HELD"], 7479.1, 1))]

    plan = frappe.new_doc("Material Planning")
    plan.company = frappe.defaults.get_global_default("company")
    plan.for_warehouse = WH
    for r in (req("1B1", 879.1, 1), req("1B2", 3186.0, 1, "1w12"), req("1B3", 979.1, 1, "1w13")):
        plan.append("raw_materials", r)
    # 1B2 is already waiting in Material Mapping for a batch; 1B3 is out for purchase.
    plan.append("material_mapping", dict(req("1B2", 3186.0, 1, "1w12"), batch_mapped="Not Mapped"))
    plan.append("unavailable_items", dict(req("1B3", 979.1, 1, "1w13")))
    # A batch already in Exact Match (for another drawing) must be left alone.
    plan.append("available_raw_materials", {
        "item_code": ITEM, "duno_mark_no": "1B9", "item_number": "1w99", "batch_no": names["EXACT"],
        "required_qty": piece(879.1), "sec_qty": 1, "length": 879.1, "warehouse": WH,
        "parent_item_group": "Structurals",
    })
    plan.flags.ignore_mandatory = True
    plan.insert(ignore_permissions=True)

    def _allocate():
        saved = (mp._receipt_batch_names, pp.get_sbb_batches_bulk, mp._get_batch_reserved_by_others_bulk)
        mp._receipt_batch_names = lambda pr: set(names.values())
        pp.get_sbb_batches_bulk = lambda item_codes, warehouse, location=None: {ITEM: [dict(b) for b in stock]}
        # Someone else holds the whole of HELD.
        mp._get_batch_reserved_by_others_bulk = lambda nos, mp_name, exclude_table=None: {names["HELD"]: stock[3]["qty"]}
        try:
            return mp.allocate_receipt_to_plan(plan.name, pr_name)
        finally:
            mp._receipt_batch_names, pp.get_sbb_batches_bulk, mp._get_batch_reserved_by_others_bulk = saved

    res = _allocate()
    plan.reload()
    rows = [(r.duno_mark_no, r.batch or "", flt(r.qty, 3), flt(r.batch_calc_qty, 3),
             int(r.reserve_without_dimensions or 0), flt(r.batch_length), flt(r.length))
            for r in plan.material_mapping]
    by_duno = {r[0]: r for r in rows}
    check("nothing was added to Exact Match", len(plan.available_raw_materials), 1)
    check("1B2's waiting row is filled in place, not duplicated",
          [r[0] for r in rows].count("1B2"), 1)
    check("1B2: the long bar, exact Kg, reserve by weight, batch's size on the row",
          by_duno["1B2"][1:], (names["LONG"], piece(3186.0), piece(3186.0), 1, 7479.1, 3186.0))
    check("1B1: its own size taken first", by_duno["1B1"][1], names["OWNSIZE"])
    check("1B3: a row of its own, from the long bar",
          (by_duno["1B3"][1], by_duno["1B3"][2]), (names["LONG"], piece(979.1)))
    check("1B3's Unavailable row is gone", [r.duno_mark_no for r in plan.unavailable_items], [])
    used = {r[1] for r in rows}
    check("the batch reserved elsewhere is never used", names["HELD"] in used, False)
    check("the batch already in Exact Match is never used", names["EXACT"] in used, False)
    check("... and is reported as skipped", res.get("skipped_in_exact_match"), [names["EXACT"]])
    check("nothing was reserved", [r.is_reserved for r in plan.material_mapping], [0, 0, 0])
    check("Sec Nos is the weight in pieces of the batch, fractional",
          flt(by_duno["1B2"][0] and [r.batch_sec_qty for r in plan.material_mapping if r.duno_mark_no == "1B2"][0], 3),
          flt(piece(3186.0) / piece(7479.1), 3))
    check("running it again allocates nothing twice", _allocate().get("rows_added"), 0)

    print("\n=== B2. a batch that covers only part of a waiting row ===")
    small = "ZZALLOC-%s-SMALL" % stamp
    frappe.get_doc({"doctype": "Batch", "batch_id": small, "item": ITEM}).insert(ignore_permissions=True)
    stock2 = [dict(batch(small, 500.0, 1))]                      # 18.65 Kg
    plan2 = frappe.new_doc("Material Planning")
    plan2.company = plan.company
    plan2.for_warehouse = WH
    plan2.append("raw_materials", req("1B2", 3186.0, 1, "1w12"))
    plan2.append("material_mapping", dict(req("1B2", 3186.0, 1, "1w12"), batch_mapped="Not Mapped"))
    plan2.flags.ignore_mandatory = True
    plan2.insert(ignore_permissions=True)
    saved = (mp._receipt_batch_names, pp.get_sbb_batches_bulk, mp._get_batch_reserved_by_others_bulk)
    mp._receipt_batch_names = lambda pr: {small}
    pp.get_sbb_batches_bulk = lambda item_codes, warehouse, location=None: {ITEM: [dict(b) for b in stock2]}
    mp._get_batch_reserved_by_others_bulk = lambda nos, mp_name, exclude_table=None: {}
    try:
        mp.allocate_receipt_to_plan(plan2.name, pr_name)
    finally:
        mp._receipt_batch_names, pp.get_sbb_batches_bulk, mp._get_batch_reserved_by_others_bulk = saved
    plan2.reload()
    got = sorted((r.batch or "", flt(r.qty, 3), flt(r.sec_qty, 3)) for r in plan2.material_mapping)
    rest = flt(piece(3186.0) - piece(500.0), 3)
    check("the covered part gets the batch, the rest stays waiting",
          got, sorted([(small, piece(500.0), flt(piece(500.0) / piece(3186.0), 3)), ("", rest, flt(rest / piece(3186.0), 3))]))


def run():
    print("=== verify_mp_stock_without_dimensions ===")
    part_a()
    series_before = frappe.db.sql("select name, current from tabSeries order by name")
    real_commit = frappe.db.commit
    frappe.db.commit = lambda *a, **k: None
    try:
        part_b()
    finally:
        frappe.db.rollback()
        frappe.db.commit = real_commit
    check("no document or series number left behind",
          frappe.db.sql("select name, current from tabSeries order by name") == series_before, True)
    print()
    failed = checks.count(False)
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, len(checks)))
    else:
        print("ALL %d CHECKS PASSED" % len(checks))
