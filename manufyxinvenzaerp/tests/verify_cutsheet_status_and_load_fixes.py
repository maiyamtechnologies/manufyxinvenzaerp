"""Six faults reported together from a testing session, checked in one place.

  1. Cut Sheet showed Width and Thickness on a Structurals sheet, where the formula
     (Length / 1000 x Unit Weight x Nos) reads neither -- inviting values that are
     silently ignored. It also left every weight blank until Save, so a cut had to be
     planned blind, and left Warehouse optional even though the split happens against
     the batch in one particular warehouse.

  2. Loading drawings warned "BEAM-1B16 -SHT-16 OF 291 / ISMB250: Structurals do not
     use Thickness" and left it there -- no row. Verify Raw Materials reports the same
     problem led by the row it is on, so the two messages described one fault in two
     ways and only one of them could be acted on.

  3. Ticking "Reserve stock without dimensions" and then pressing Move to Unavailable
     Items un-ticked it again: finalize_mapping rebuilds each row it keeps, and the
     flag was not among the fields it carried across. Sec Qty (Nos) then drifted
     (_apply_rwd_fractional_nos only maintains it while the flag is set) and the next
     save failed with "Calculated Qty is less than Required Qty", because
     reserve_batches routes a dimension-waived row down its own branch. Re-ticking the
     box fixed all three at once -- the signature of a dropped field.

  4. The post-submit popup naming the Material Planning a receipt's batches landed in
     never appeared. It hung off an "after_submit" form event, which Frappe does not
     have; the events around a save are after_save / before_submit / before_cancel /
     after_cancel.

  5. "Job work order & MIP" died with "AttributeError: __dict__" the moment a plan had
     a cut-sheet row: frappe.local is a Werkzeug Local proxy and raises for __dict__ on
     this version.

  6. Production Plan status never moved off Not Started. ERPNext derives it from Work
     Orders, and this app's plans are executed through a Job Work Order and a Material
     Issue Plan instead, so total_produced_qty stays 0 forever.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_cutsheet_status_and_load_fixes.run
"""

import re

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    print("=== 1. Cut Sheet ===")
    meta = frappe.get_meta("Cut Sheet")
    check("Warehouse is mandatory", bool(meta.get_field("warehouse").reqd), True)

    cs_js = open(frappe.get_app_path(
        "manufyxinvenzaerp", "production_management", "doctype", "cut_sheet", "cut_sheet.js"
    )).read()
    check("Width/Thickness are hidden for Structurals",
          bool(re.search(r'parent_item_group === "Structurals"', cs_js))
          and "sheet_thickness" in cs_js and "toggle_display" in cs_js, True)
    check("the weights are calculated in the form",
          all(f in cs_js for f in ("sheet_qty", "w1_qty_per_nos", "w1_total_qty", "w2_calc_qty")),
          True)
    # The client formula must be the server's, or the preview lies until Save.
    check("using the same formula as the server",
          bool(re.search(r"length / 1000\) \* unit_weight \* sec_qty", cs_js))
          and bool(re.search(r"length / 1000\) \* \(width / 1000\) \* thickness \* unit_weight \* sec_qty", cs_js)),
          True)

    print()
    print("=== 2. Load warnings name the row ===")
    from manufyxinvenzaerp.drawing_management import so_drawing_import as sdi

    src = open(sdi.__file__.replace(".pyc", ".py")).read()
    check("the dimension warnings are raised with _at(RAW_MATERIALS, ...)",
          len(re.findall(r"dim_warn\.append\(_at\(RAW_MATERIALS, t2_idx", src)), 3)
    check("and no longer without a row",
          bool(re.search(r'dim_warn\.append\(\s*_\("\{0\} / \{1\}', src)), False)

    print()
    print("=== 3. Move to Unavailable Items keeps the row's own decisions ===")
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        finalize_mapping,
    )
    import json

    doc = {
        "material_mapping": [{
            "item_code": "ZZTEST-RWD", "item_name": "RWD", "bom_no": "BOM-X",
            "drawing": "DRW-X", "duno_mark_no": "D1", "parent_item_group": "Structurals",
            "qty": 100.0, "uom": "Kg", "sec_qty": 2.0, "sec_uom": "Nos",
            "length": 1000.0, "width": 0.0, "thickness": 0.0, "unit_weight": 10.0,
            "batch": "ZZTEST-BATCH", "batch_parent_item_group": "Structurals",
            "batch_calc_qty": 100.0, "batch_sec_qty": 1.5,
            "reserve_without_dimensions": 1,
            "cut_sheet": 1, "cut_sheet_ref": "CS-2026-00001",
            "use_length": 500.0, "use_sec_qty": 2.0, "balance_length": 400.0,
            "cnc_process": 1, "batch_remarks": "keep me",
        }],
        "unavailable_items": [],
    }
    res = finalize_mapping(json.dumps(doc))
    kept = (res.get("material_mapping") or [{}])[0]
    check("the row stays in Material Mapping", len(res.get("material_mapping") or []), 1)
    check("Reserve stock without dimensions survives",
          kept.get("reserve_without_dimensions"), 1)
    check("and so does the cut sheet it is cutting from",
          (kept.get("cut_sheet"), kept.get("cut_sheet_ref"), flt(kept.get("use_length"))),
          (1, "CS-2026-00001", 500.0))
    check("and the rest of the row's own flags",
          (kept.get("cnc_process"), kept.get("batch_remarks")), (1, "keep me"))

    print()
    print("=== 4. The receipt's allocation popup is on an event that exists ===")
    pr_js = open(frappe.get_app_path(
        "manufyxinvenzaerp", "public", "js", "purchase_receipt.js"
    )).read()
    check("it no longer hangs off after_submit", "after_submit(frm)" in pr_js, False)
    check("it runs on after_save, guarded on docstatus",
          bool(re.search(r"after_save\(frm\)\s*\{\s*\n\s*if \(frm\.doc\.docstatus !== 1\) return;", pr_js)),
          True)

    print()
    print("=== 5. Job work order & MIP no longer dies on frappe.local ===")
    mip_src = open(frappe.get_app_path(
        "manufyxinvenzaerp", "subcontracting_management", "doctype",
        "material_issue_plan", "material_issue_plan.py",
    )).read()
    # The call, not the word: the comment above the fix names the old expression
    # to explain what it broke, so a bare substring search matches the prose.
    check("nothing calls into frappe.local.__dict__ any more",
          bool(re.search(r"frappe\.local\.__dict__\s*\.", mip_src)), False)
    # The real proof: the call that died now returns a plan.
    pp = frappe.db.get_value(
        "Production Plan",
        {"docstatus": 1, "name": ["not in", _plans_with_sco()]},
        "name", order_by="creation desc",
    )
    if not pp:
        print("    (no submitted plan without a Job Work Order to try -- skipped)")
    else:
        from manufyxinvenzaerp.subcontracting_management.subcontracting import (
            create_sco_and_mip_from_production_plan,
        )
        out = create_sco_and_mip_from_production_plan(pp)
        check("it creates the order and the issue plan",
              bool(out.get("sco")) and bool(out.get("mip")), True)

        print()
        print("=== 6. Production Plan status follows the job ===")
        from manufyxinvenzaerp.production_plan_management.production_plan import (
            refresh_production_plan_status,
        )
        # Nothing transferred yet, so it must NOT claim to have started.
        before = frappe.db.get_value("Production Plan", pp, "status")
        refresh_production_plan_status(pp)
        check("an untouched plan is left alone",
              frappe.db.get_value("Production Plan", pp, "status"), before)

    for name, expected in _existing_plan_expectations():
        check("  %s reads %s" % (name, expected),
              frappe.db.get_value("Production Plan", name, "status"), expected)

    frappe.db.rollback()
    print()
    print("  (rolled back -- this check leaves no trace)")
    _summary()


def _plans_with_sco():
    names = frappe.get_all(
        "Subcontracting Order", filters={"docstatus": ["!=", 2]},
        pluck="custom_production_plan", distinct=True,
    )
    return [n for n in names if n] or [""]


def _existing_plan_expectations():
    """What every plan already carrying a Job Work Order should read, worked out
    the same way refresh_production_plan_status does."""
    from manufyxinvenzaerp.production_plan_management.production_plan import (
        _plan_material_transferred,
    )
    from manufyxinvenzaerp.subcontracting_management.overrides import (
        _any_operation_started, _final_stock_entry_submitted,
    )

    out = []
    for row in frappe.get_all(
        "Subcontracting Order",
        filters={"docstatus": 1, "custom_production_plan": ["is", "set"]},
        fields=["name", "custom_production_plan"],
    ):
        pp = row.custom_production_plan
        if frappe.db.get_value("Production Plan", pp, "status") in ("Closed", "Cancelled"):
            continue
        if _final_stock_entry_submitted(row.name):
            out.append((pp, "Completed"))
        elif _plan_material_transferred(pp, [row.name]) or _any_operation_started(row.name):
            out.append((pp, "In Process"))
    return out


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
