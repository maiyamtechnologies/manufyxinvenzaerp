"""Material Spec and Grade are mandatory on Structurals and Plates rows of the
Sales Order drawing import (the client's "BOM" sheet), and optional elsewhere.

Read-only: builds rows in memory and calls the Verify check directly.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_spec_grade_mandatory.run
"""

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _so(*rows):
    return frappe._dict(custom_so_raw_materials=[
        frappe._dict(idx=i, customer_drawing_number="CDN-1", material_code="M-%d" % i, **r)
        for i, r in enumerate(rows, start=1)])


def run():
    from manufyxinvenzaerp.drawing_management import so_drawing_import as imp

    print("=== verify_spec_grade_mandatory ===")
    so = _so(
        {"parent_item_group": "Structurals", "material_spec": "", "grade": "E250"},
        {"parent_item_group": "Plates", "material_spec": "IS2062", "grade": ""},
        {"parent_item_group": "Plates", "material_spec": "", "grade": ""},
        {"parent_item_group": "Structurals", "material_spec": "IS2062", "grade": "E250"},
        {"parent_item_group": "Nuts and Bolts", "material_spec": "", "grade": ""},
        {"parent_item_group": "Plates", "material_spec": "", "grade": "", "is_locked": 1},
    )
    issues = [frappe.utils.strip_html(str(i)) for i in imp._check_spec_grade_required(so)]
    check("three rows refused", len(issues), 3)
    check("Structurals row without a spec names Material Spec",
          any("M-1" in i and "Material Spec is mandatory for Structurals" in i for i in issues), True)
    check("Plates row without a grade names Grade",
          any("M-2" in i and "Grade is mandatory for Plates" in i for i in issues), True)
    check("a row missing both names both", any("M-3" in i and "Material Spec and Grade" in i for i in issues), True)
    check("a complete row passes", any("M-4" in i for i in issues), False)
    check("Nuts and Bolts stays optional", any("M-5" in i for i in issues), False)
    check("a row already made into a Drawing is not re-checked", any("M-6" in i for i in issues), False)

    src = open(frappe.get_app_path("manufyxinvenzaerp", "drawing_management", "so_drawing_import.py")).read()
    check("the check runs inside Verify Raw Materials", "_check_spec_grade_required(so)" in src, True)
    check("template sample rows carry a spec",
          src.count("sample_spec, sample_grade") == 2, True)

    print()
    failed = checks.count(False)
    print(("%d of %d CHECKS FAILED" % (failed, len(checks))) if failed else "ALL %d CHECKS PASSED" % len(checks))
