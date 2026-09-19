"""A batch with nothing left in it is not a match.

Splitting one batch across several requirements leaves an arithmetic residue.
1061.609 Kg shared between two 530.804 Kg rows leaves 0.001; the next split leaves a
millionth of that. The stock check treated *any* positive remainder as free stock, so
those crumbs became Exact Match rows of 0.000 Kg -- nothing to reserve, nothing to
transfer, and a "2 matched to Available Raw Materials" message claiming stock had been
found when the batch was consumed to the last kilo.

It is a convincing kind of wrong: the batch really is named on a real requirement, the
dimensions really do match, and the only thing saying otherwise is a quantity that
rounds to zero.

A batch now counts as free only above BATCH_FREE_EPSILON, and no row is written for a
quantity that rounds away to nothing.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_no_zero_qty_exact_match.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-54s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.production_management.doctype.material_planning import (
        material_planning as mp,
    )
    src = open(frappe.get_app_path(
        "manufyxinvenzaerp", "production_management", "doctype",
        "material_planning", "material_planning.py")).read()

    print("=== free stock has a floor ===")
    check("the floor exists", hasattr(mp, "BATCH_FREE_EPSILON"), True)
    check("and it is the same 0.001 used everywhere else",
          getattr(mp, "BATCH_FREE_EPSILON", None), 0.001)

    print()
    print("=== every stock check uses it ===")
    check("no bare 'greater than zero' test is left",
          'batch_remaining.get(b["batch_no"], 0) > 0' in src, False)
    # The floor now lives in _batch_has_free_stock, which also refuses a crumb worth
    # less than 0.001 Nos (verify_mp_batch_dust covers that).
    check("all three sites go through _batch_has_free_stock",
          src.count("if _batch_has_free_stock(\n"), 3)
    check("which still refuses anything at or under the floor",
          mp._batch_has_free_stock(mp.BATCH_FREE_EPSILON, 0, 0), False)

    print()
    print("=== and nothing writes a row for a quantity that rounds to nothing ===")
    check("the row write is guarded",
          "if flt(consumed_qty, 3) <= 0:\n                        continue" in src, True)

    print()
    print("=== the symptom, across every plan on this site ===")
    empty = frappe.db.sql(
        """
        SELECT parent, idx, item_code, batch_no, required_qty, is_reserved
        FROM `tabMaterial Planning Available Raw Material`
        WHERE batch_no IS NOT NULL AND batch_no != '' AND ROUND(required_qty, 3) <= 0
        ORDER BY parent, idx
        """,
        as_dict=True,
    )
    if not empty:
        print("   No Exact Match row names a batch while asking for nothing.")
    else:
        print("   %d row(s) name a batch but ask for 0 Kg — left by the old rule:" % len(empty))
        for r in empty:
            print("     %s row %-3s %-10s %-28s reserved=%s"
                  % (r.parent, r.idx, r.item_code, r.batch_no, r.is_reserved))
        print("   Harmless in themselves: nothing to reserve, nothing to transfer.")
        print("   They cannot be created any more; clearing the existing ones is a")
        print("   data decision, not a code one.")

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
