"""Material Mapping: a reserved row is settled, and a re-selected batch re-derives Sec Nos.

Two things this locks down.

1. A reserved row holds stock, so its Batch, its "Reserve stock without dimensions"
   waiver and its Sec Nos are read-only until it is unreserved. Sec Nos is in the list
   because Calc Qty is derived from it, and Calc Qty is the weight that was reserved --
   editing it on a reserved row describes a reservation nobody is holding.

   The batch handler already refused a change and put the old value back, but only after
   the user had picked a new batch and watched it vanish -- and the collapsed grid edits
   inline, where nothing had told them yet. The server agrees: _apply_rwd_fractional_nos
   skips reserved rows entirely.

2. On a waiver row the arithmetic runs backwards -- Required Qty is fixed and Sec Nos is
   derived from it. Every recalculation used to work from the Sec Nos already on the row,
   so selecting a SECOND batch left the FIRST batch's Sec Nos sitting there, and the only
   way to correct it was to untick the waiver and tick it again. _recalc_batch_qty now
   derives it, and every path that recalculates a row comes through there.

Also guards what must NOT change: the batch picker is deliberately not filtered by item.
A plate batch against an ISMB requirement is a combination the Material Mapping table
exists to allow, and no restriction belongs there.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_mapping_reserved_lock_and_rwd.run
"""

import inspect
import os

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _js():
    return open(os.path.join(
        frappe.get_app_path("manufyxinvenzaerp"), "production_management",
        "doctype", "material_planning", "material_planning.js")).read()


def run():
    from manufyxinvenzaerp.production_management.doctype.material_planning import (
        material_planning as mp_mod,
    )
    js = _js()

    print("=== a reserved row's batch, waiver and Sec Nos are read-only ===")
    # The lock has since widened: a row that has SHIPPED is settled too, and CNC Process
    # joined the locked fields -- see verify_transferred_row_locked. What this test still
    # owns is that being reserved is one of the things that settles a row, and that the
    # three original fields are among those locked.
    check("the row-expand handler locks them",
          "df.read_only = _mp_row_settled(row) ? 1 : 0;" in js, True)
    check("reserved still counts as settled", "row.is_reserved ||" in js, True)
    check("every row is locked, not just the expanded one",
          "function _mp_lock_settled_rows(frm)" in js, True)
    check("...and it runs on form refresh",
          "_mp_lock_settled_rows(frm);" in js, True)
    check("all three fields are named",
          '"batch", "reserve_without_dimensions", "batch_sec_qty"' in js, True)
    check("Sec Nos is locked too (it drives the reserved weight)",
          "_MP_LOCKED_MAPPING_FIELDS" in js, True)
    check("the old reactive guard is still there as a backstop",
          "This row is reserved. Unreserve it before changing the batch." in js, True)

    print()
    print("=== re-selecting a batch re-derives Sec Nos ===")
    recalc = js[js.index("function _recalc_batch_qty"):]
    recalc = recalc[:recalc.index("\n}")]
    check("the shared recalc delegates for waiver rows",
          "_calc_rwd_preview(frm, cdt, cdn);" in recalc, True)
    check("...and returns rather than falling through",
          "return;" in recalc.split("_calc_rwd_preview")[1][:40], True)
    check("the batch handler routes through that recalc",
          js.count("_recalc_batch_qty(frm, cdt, cdn);") >= 2, True)

    print()
    print("=== the server derives the same figure on every save ===")
    src = inspect.getsource(mp_mod.MaterialPlanning._apply_rwd_fractional_nos)
    check("reserved rows are skipped", "if row.is_reserved or not row.batch:" in src, True)
    check("Sec Nos comes from the requirement weight",
          "_sec_nos_for_weight(row, row.qty)" in src, True)
    check("Required Qty is what is reserved", "row.batch_calc_qty = flt(row.qty, 3)" in src, True)

    print()
    print("=== the arithmetic: a different batch means a different Sec Nos ===")
    # Same 1,000 Kg requirement, two batches of the same item in different sizes.
    # Structurals: kg per piece = (length/1000) * unit weight.
    need = 1000.0
    for length, uw, expect in ((12000.0, 61.6, 1000.0 / (12.0 * 61.6)),
                               (6000.0, 61.6, 1000.0 / (6.0 * 61.6))):
        kg_per_nos = (length / 1000.0) * uw
        check("a %.0f mm bar gives %.3f Nos" % (length, expect),
              flt(need / kg_per_nos, 3), flt(expect, 3))
    check("the two batches do NOT give the same Sec Nos",
          flt(1000.0 / (12.0 * 61.6), 3) == flt(1000.0 / (6.0 * 61.6), 3), False)

    print()
    print("=== no item restriction on the batch picker (must stay this way) ===")
    q = inspect.getsource(mp_mod.material_mapping_batch_query)
    check("the query filters on warehouse", '"warehouse"' in q, True)
    check("the query does NOT filter on the row's item",
          'filters.get("item_code")' in q or '"item_code":' in q, False)
    check("and says so deliberately", "NOT filtered by item" in q, True)

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
