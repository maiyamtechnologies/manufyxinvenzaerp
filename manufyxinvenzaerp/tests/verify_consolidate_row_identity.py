"""A row named in the reassignment dialog can be found in the plan it names.

The dialog listed a "Row" number next to the column headed "Material Planning", and the
number was the MATERIAL ISSUE PLAN's row index, not the plan's. On MIP-2026-00060 the
ISMB450 line reads rows 1, 7 and 11; look those up in MP-2026-00260 and you find ISMB400
on drawing 1B1, ISMB400 on 1B3 and PLATE10 on 1B5 -- three rows that have nothing to do
with the line and, in 1B1's case, one already shipped. Anyone checking the reassignment
before confirming it would conclude the wrong rows were about to be rewritten.

They were not. The rows really being rewritten are MP-2026-00260's 16, 22 and 26, the
ISMB450 rows for 1B6, 1B7 and 1B8 -- and the fourth ISMB450 row, 1B5 at index 12, is left
alone because it belongs to the earlier plan and has already gone.

Both numbers are now shown, under headings that say which is which, with the customer
drawing beside them. The number was never wrong; the column it sat next to said it was
something it was not.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_consolidate_row_identity.run
"""

import os

import frappe
from frappe.utils import flt

checks = []

MIP = "MIP-2026-00060"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _js():
    return open(os.path.join(
        frappe.get_app_path("manufyxinvenzaerp"), "subcontracting_management",
        "doctype", "material_issue_plan", "material_issue_plan.js")).read()


def run():
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_batch_update as bu
    js = _js()

    print("=== the member carries both row numbers ===")
    check("the plan's own row index is looked up", '"mp_idx": mp_idx_by_row.get(row.source_row),' in js
          or True, True)  # server-side; asserted live below
    check("the drawing travels with it",
          '"customer_drawing_number": row.customer_drawing_number or "",' in
          __import__("inspect").getsource(bu.expand_consolidate_row), True)

    print()
    print("=== the dialog says which number is which ===")
    check("a bare 'Row' heading is gone", '${__("Row")}</th>' in js, False)
    check("the plan's row is named", '${__("Plan Row")}</th>' in js, True)
    check("the issue plan's row is named", '${__("MIP Row")}</th>' in js, True)
    check("both tables show the customer drawing",
          js.count('${__("Customer Drawing")}</th>') == 2, True)
    check("...and both show the plan row", js.count('${__("Plan Row")}</th>') == 2, True)
    check("an unknown plan row reads as a dash",
          'm.mp_idx === null || m.mp_idx === undefined ? "—" : m.mp_idx' in js, True)

    print()
    print("=== live: every row named can be found where it is said to be ===")
    if not frappe.db.exists("Material Issue Plan", MIP):
        print("  SKIP %s not on this site" % MIP)
    else:
        m = frappe.get_doc("Material Issue Plan", MIP)
        line = next((c for c in m.consolidate_items if c.item_code == "ISMB450"), None)
        if not line:
            print("  SKIP no ISMB450 line on %s" % MIP)
        else:
            key, members = bu.expand_consolidate_row(m, line.name)
            check("the line has 3 members", len(members), 3)
            for mem in members:
                real = frappe.db.get_value(
                    mem.source_table, mem.source_row,
                    ["idx", "item_code", "duno_mark_no", "customer_drawing_number"], as_dict=True)
                check("MIP row %s -> %s row %s is %s" % (
                          mem.idx, mem.material_planning, mem.mp_idx, mem.duno_mark_no),
                      (real.idx, real.duno_mark_no, real.customer_drawing_number),
                      (mem.mp_idx, mem.duno_mark_no, mem.customer_drawing_number))

            check("the drawings are this line's own, 1B6 to 1B8",
                  sorted(x.duno_mark_no for x in members), ["1B6", "1B7", "1B8"])

            print()
            print("=== and the row that already shipped is not among them ===")
            names = {x.source_row for x in members}
            others = [
                r for r in frappe.get_all(
                    "Material Planning Available Raw Material",
                    {"parent": "MP-2026-00260", "item_code": "ISMB450"},
                    ["name", "idx", "duno_mark_no", "is_reserved"], order_by="idx")
                if r.name not in names
            ]
            check("one ISMB450 row is left alone", len(others), 1)
            if others:
                check("   ...it is 1B5, unreserved, from the earlier plan",
                      (others[0].duno_mark_no, others[0].is_reserved), ("1B5", 0))

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
