"""A batch's Nos are counted in the warehouse being planned from, not across all.

WHY: MP-2026-00016 reserved 12 Nos of ISMB400-L6936-R008 in Stores against 0.035 Kg.
MAT-STE-00013 had moved the batch to Work In Progress for MP-2026-00015, leaving a
0.035 Kg crumb behind in Stores -- and Batch.custom_sec_qty (12) counts the pieces
across EVERY warehouse. The stock readers paired the Stores Kg with that batch-wide
count, so the dust guard (_batch_has_free_stock) saw 0.035 Kg = 12 Nos and handed the
crumb to DUNO 1B3 as an Exact Match row of 12 pieces, leaving only 4 Nos on the batch
that really holds them. production_plan._warehouse_sec_qty now scales the pieces to
the warehouse's share of the Kg.

The live part re-runs Check Stock Availability for MP-2026-00016 with its own
reservations released inside a transaction, and rolls back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_batch_nos_per_warehouse.run
"""

import json

import frappe
from frappe.utils import flt

checks = []

MP = "MP-2026-00016"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    print("=== verify_batch_nos_per_warehouse ===")
    try:
        _run()
    finally:
        frappe.db.rollback()
    print()
    failed = checks.count(False)
    print(("%d of %d CHECKS FAILED" % (failed, len(checks))) if failed else "ALL %d CHECKS PASSED" % len(checks))


def _run():
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        _batch_has_free_stock, check_stock_availability,
    )
    from manufyxinvenzaerp.production_plan_management.production_plan import _warehouse_sec_qty

    print("=== the share of the pieces follows the share of the Kg ===")
    check("batch all in one warehouse: unchanged", _warehouse_sec_qty(27, 11535.972, 11535.972), 27)
    check("half the Kg here: half the pieces", flt(_warehouse_sec_qty(12, 2500, 5000), 3), 6.0)
    check("no batch total known: unchanged", _warehouse_sec_qty(12, 0.035, 0), 12)
    crumb = _warehouse_sec_qty(12, 0.035, 5127.13)
    check("a 0.035 Kg crumb of a 12-piece batch stays a crumb, not 0", 0 < crumb < 0.001, True)
    check("...and the dust guard refuses it", _batch_has_free_stock(0.035, 0.035, crumb), False)
    check("...where the batch-wide 12 used to pass it", _batch_has_free_stock(0.035, 0.035, 12), True)

    if not frappe.db.exists("Material Planning", MP):
        print("  SKIP %s is not on this site -- live re-check not run" % MP)
        return

    print()
    print("=== %s re-checked with its own reservations released ===" % MP)
    mp = frappe.get_doc("Material Planning", MP).as_dict()
    for table in ("Material Planning Material Mapping", "Material Planning Available Raw Material"):
        frappe.db.delete(table, {"parent": MP})  # rolled back in run()
    for field in ("material_mapping", "available_raw_materials", "unavailable_items"):
        mp[field] = []
    res = check_stock_availability(json.dumps(mp, default=str))

    rows = []
    for bucket in ("available_raw_materials", "material_mapping"):
        for r in res.get(bucket) or []:
            rows.append(frappe._dict(
                bucket=bucket, duno=r.get("duno_mark_no"), item=r.get("item_code"),
                batch=r.get("batch_no") or r.get("batch") or "",
                kg=flt(r.get("required_qty") or r.get("qty"), 3), nos=flt(r.get("sec_qty"), 3)))

    check("no row on the 0.035 Kg crumb of R008",
          [r for r in rows if r.batch == "ISMB400-L6936-R008"], [])
    b3 = [(r.batch, r.kg, r.nos) for r in rows if r.duno == "1B3" and r.item == "ISMB400"]
    print("       1B3 ISMB400 ->", b3)
    check("1B3 ISMB400: all 16 Nos on the batch that holds them",
          sum(n for b, k, n in b3 if b == "ISMB400-L6936-R009"), 16.0)
    check("no row anywhere reserves Kg for 0 Nos on a piece-counted batch",
          [(r.duno, r.batch, r.kg) for r in rows if r.batch and r.kg > 0 and r.nos <= 0], [])
    required = frappe.db.sql(
        "SELECT SUM(qty), SUM(sec_qty) FROM `tabMaterial Planning Raw Material` WHERE parent=%s", MP)[0]
    check("every Kg of the requirement is placed",
          flt(sum(r.kg for r in rows), 3), flt(required[0], 3))
    check("every Nos of the requirement is placed",
          flt(sum(r.nos for r in rows), 3), flt(required[1], 3))
