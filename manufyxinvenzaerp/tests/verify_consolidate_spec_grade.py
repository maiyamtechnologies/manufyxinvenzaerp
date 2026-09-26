"""Material Spec and Grade must show on the Consolidate Item rows of Material
Planning and Material Issue Plan.

WHY: MP-2026-00016 on the live site showed both columns blank on every
Consolidate Item line while the Unavailable Items beside them read MS / IS2062.
Both columns are `fetch_from item_code`, but Frappe runs that fetch in
_validate_links, BEFORE validate() -- and validate() is where both tables are
built (_consolidate_unavailable_items, _sync_consolidate_items). A row appended
there never got the fetch. Spec and grade are one per Item (a second grade of
PLATE10 is a second Item), so each grade must land on its own line.

Writes two Items' spec/grade, then rolls everything back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_consolidate_spec_grade.run
"""

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    print("=== verify_consolidate_spec_grade ===")
    try:
        _run()
    finally:
        frappe.db.rollback()
    print()
    failed = checks.count(False)
    print(("%d of %d CHECKS FAILED" % (failed, len(checks))) if failed else "ALL %d CHECKS PASSED" % len(checks))


def _run():
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        _sync_consolidate_items,
    )

    specs = frappe.get_all("Material Spec", pluck="name", limit=2)
    grades = frappe.get_all("Material Grade", pluck="name", limit=2)
    if len(specs) < 2 or len(grades) < 2:
        print("  SKIP need two Material Spec and two Material Grade records")
        return
    # Two Items standing in for "PLATE10 grade 1" and "PLATE10 grade 2".
    a, b = "PLATE10", "PLATE12"
    frappe.db.set_value("Item", a, {"custom_material_spec": specs[0], "custom_material_grade": grades[0]})
    frappe.db.set_value("Item", b, {"custom_material_spec": specs[1], "custom_material_grade": grades[1]})

    mp = frappe.new_doc("Material Planning")
    for item, qty in ((a, 100), (b, 50), (a, 25)):
        mp.append("unavailable_items", {"item_code": item, "qty": qty, "parent_item_group": "Plates"})
    mp._consolidate_unavailable_items()
    rows = {r.item_code: r for r in mp.consolidate_items}

    check("MP: one Consolidate line per Item (grade)", len(mp.consolidate_items), 2)
    check("MP: grade-1 Item carries its spec", rows[a].material_spec, specs[0])
    check("MP: grade-1 Item carries its grade", rows[a].material_grade, grades[0])
    check("MP: grade-2 Item carries its spec", rows[b].material_spec, specs[1])
    check("MP: grade-2 Item carries its grade", rows[b].material_grade, grades[1])
    check("MP: required Kg still sums per Item", rows[a].required_kg, 125.0)

    # A line saved blank before the fix is repaired on the next save.
    rows[a].material_spec = rows[a].material_grade = None
    mp._consolidate_unavailable_items()
    check("MP: a line saved blank is back-filled", (rows[a].material_spec, rows[a].material_grade),
          (specs[0], grades[0]))

    mip = frappe.new_doc("Material Issue Plan")
    for item, batch in ((a, "B-1"), (b, "B-2")):
        mip.append("raw_materials", {"item_code": item, "batch_no": batch, "qty": 10, "sec_qty": 1})
    _sync_consolidate_items(mip)
    mrows = {r.item_code: r for r in mip.consolidate_items}
    check("MIP: one Consolidate line per Item (grade)", len(mip.consolidate_items), 2)
    check("MIP: grade-1 Item carries spec and grade", (mrows[a].material_spec, mrows[a].material_grade),
          (specs[0], grades[0]))
    check("MIP: grade-2 Item carries spec and grade", (mrows[b].material_spec, mrows[b].material_grade),
          (specs[1], grades[1]))
