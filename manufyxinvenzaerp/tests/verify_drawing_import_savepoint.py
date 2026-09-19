"""One bad row in an import must not destroy the good drawings beside it.

create_drawings_from_import works in batches of 30. Each drawing was inserted
inside a try/except whose handler called a plain frappe.db.rollback() -- which
ends the whole transaction, not just the failed insert. A failure on drawing 15
therefore took drawings 1-14 with it. The user saw one error message and simply
had fewer drawings than the sheet described, with nothing saying which had gone.
On a 500-drawing import that is up to 29 good drawings destroyed by one bad row.

Each insert now runs inside its own savepoint, so only the drawing that failed is
undone.

The test builds a real Sales Order with staged rows, deliberately breaks the
middle one, runs the import, and counts what survived. It cleans up after itself.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_drawing_import_savepoint.run
"""

import frappe
from frappe.utils import flt

checks = []
SUFFIX = frappe.generate_hash(length=6).upper()


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.drawing_management.so_drawing_import import (
        create_drawings_from_import,
    )
    import inspect

    print("=== the rollback is scoped to one drawing ===")
    src = inspect.getsource(create_drawings_from_import)
    check("a savepoint is taken per drawing", "frappe.db.savepoint(savepoint)" in src, True)
    check("the handler rolls back to it",
          "frappe.db.rollback(save_point=savepoint)" in src, True)
    check("no unscoped rollback is left in the loop",
          "frappe.db.rollback()\n" in src, False)
    check("the savepoint is named per row", 'savepoint = "mfx_drawing_%d" % row_no' in src, True)

    print()
    print("=== savepoints behave as expected on this database ===")
    # Proves the mechanism itself, independently of the import: two inserts, the
    # second rolled back to its own savepoint, the first still standing.
    made = []
    try:
        for i, tag in enumerate(("KEEP", "DROP")):
            name = "ZZTEST-SP-%s-%s" % (SUFFIX, tag)
            sp = "mfx_test_%d" % i
            frappe.db.savepoint(sp)
            frappe.get_doc({"doctype": "Nature of Work", "nature_of_work": name}).insert(
                ignore_permissions=True)
            made.append(name)
            if tag == "DROP":
                frappe.db.rollback(save_point=sp)
        kept = [n for n in made if frappe.db.exists("Nature of Work", n)]
        check("the first insert survived", len(kept), 1)
        check("...and it is the one not rolled back", kept[0].endswith("KEEP"), True)
        check("the rolled-back one is gone",
              frappe.db.exists("Nature of Work", "ZZTEST-SP-%s-DROP" % SUFFIX), None)
    finally:
        for n in made:
            if frappe.db.exists("Nature of Work", n):
                frappe.delete_doc("Nature of Work", n, force=1, ignore_permissions=True)
        frappe.db.commit()

    print()
    print("=== against the real import: a broken row in the middle ===")
    so_name = None
    try:
        so_name = _build_sales_order()
        if not so_name:
            print("   (could not build a fixture Sales Order -- skipped)")
        else:
            res = create_drawings_from_import(so_name, 0, 30)
            ok = [r for r in res["results"] if r["status"] == "success"]
            bad = [r for r in res["results"] if r["status"] != "success"]
            print("   %d row(s): %d created, %d failed" % (len(res["results"]), len(ok), len(bad)))
            for r in bad:
                print("      failed: %s — %s" % (r["drawing_number"],
                                                 frappe.utils.strip_html(r["error"])[:90]))
            check("the broken row failed", len(bad), 1)
            check("every other row was created", len(ok), 3)
            created = frappe.get_all("Drawing", filters={"sales_order": so_name}, pluck="name")
            check("and they are really in the database", len(created), 3)
            print("       (before the fix all three would have been rolled back)")
    finally:
        if so_name:
            _cleanup(so_name)

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))


def _build_sales_order():
    """Four staged drawings, the third pointing at an item that does not exist so
    its insert fails while the other three are sound."""
    customer = frappe.db.get_value("Customer", {}, "name")
    company = frappe.db.get_value("Company", {}, "name")
    fg = frappe.db.get_value("Item", {"is_stock_item": 1, "has_batch_no": 0}, "name") \
        or frappe.db.get_value("Item", {}, "name")
    material = frappe.db.get_value("Item", {"custom_parent_item_group": "Structurals"}, "name")
    if not (customer and company and fg and material):
        return None

    so = frappe.get_doc({
        "doctype": "Sales Order",
        "customer": customer,
        "company": company,
        "delivery_date": frappe.utils.nowdate(),
        "items": [{"item_code": fg, "qty": 1, "rate": 1,
                   "delivery_date": frappe.utils.nowdate()}],
    })
    so.flags.ignore_permissions = True
    so.insert()

    uw = flt(frappe.db.get_value("Item", material, "custom_unit_weight")) or 1
    for i in range(1, 5):
        cdn = "ZZTEST-CDN-%s-%d" % (SUFFIX, i)
        so.append("custom_duno_items", {
            "assembly_group": "ZZTEST",
            # Row 3 names an FG item that does not exist, so its Drawing insert
            # throws on the link while the rest are fine.
            "item": "ZZ-NOT-A-REAL-ITEM" if i == 3 else fg,
            "duno_mark_no": "ZZ%d" % i,
            "drawing_number": cdn,
            "total_quantity": 1,
            "total_weight": 10,
            "create_drawing": 1,
        })
        so.append("custom_so_raw_materials", {
            "customer_drawing_number": cdn,
            "item_no": "1",
            "material_code": material,
            "material_name": material,
            "parent_item_group": "Structurals",
            "length": 1000, "sec_qty": 1, "unit_weight": uw,
            "qty": flt(uw, 3), "uom": "Kg",
        })
    so.save(ignore_permissions=True)
    # Create Drawing now refuses an unverified order on the server (sep14 plan D25).
    # This fixture carries a broken row on purpose, which Verify would reject, so the
    # pass is stood in for directly -- the savepoint is what is under test here.
    frappe.db.set_value("Sales Order", so.name, "custom_raw_materials_verified", 1,
                        update_modified=False)
    frappe.db.commit()
    return so.name


def _cleanup(so_name):
    for name in frappe.get_all("Drawing", filters={"sales_order": so_name}, pluck="name"):
        frappe.delete_doc("Drawing", name, force=1, ignore_permissions=True)
    if frappe.db.exists("Sales Order", so_name):
        frappe.delete_doc("Sales Order", so_name, force=1, ignore_permissions=True)
    frappe.db.commit()
    print("test fixtures removed")
