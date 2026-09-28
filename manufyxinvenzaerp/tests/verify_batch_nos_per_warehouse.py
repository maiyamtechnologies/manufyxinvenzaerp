"""A batch's Nos are counted in the warehouse being planned from, not across all.

WHY: MP-2026-00016 reserved 12 Nos of ISMB400-L6936-R008 in Stores against 0.035 Kg.
MAT-STE-00013 had moved the batch to Work In Progress for MP-2026-00015, leaving a
0.035 Kg crumb behind in Stores -- and Batch.custom_sec_qty (12) counts the pieces
across EVERY warehouse. The stock readers paired the Stores Kg with that batch-wide
count, so the dust guard (_batch_has_free_stock) saw 0.035 Kg = 12 Nos and handed the
crumb to DUNO 1B3 as an Exact Match row of 12 pieces, leaving only 4 Nos on the batch
that really holds them. production_plan._warehouse_sec_qty now scales the pieces to
the warehouse's share of the Kg.

Built on figures only. It used to re-run Check Stock Availability against
MP-2026-00016 on the site, which stopped meaning anything the first time a newer
snapshot was restored over it.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_batch_nos_per_warehouse.run
"""

import frappe
from frappe.utils import flt

checks = []



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
        _batch_has_free_stock,
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

    # A batch with no pieces left anywhere (2026-09-28): PLT10-T10-L186-W180-R009 held
    # 0.002 Kg and 0 Nos and was offered as a 0 Nos row.
    check("a zero-Nos crumb under 0.01 Kg is refused", _batch_has_free_stock(0.002, 0.002, 0), False)
    check("...but real weight on a batch with no Nos recorded is still offered",
          _batch_has_free_stock(12.5, 12.5, 0), True)
    check("...and so are the last grams of a batch that does not count pieces",
          _batch_has_free_stock(0.002, 100, 0), True)
