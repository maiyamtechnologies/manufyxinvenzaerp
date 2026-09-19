"""Planning rows carry the drawing's Nos (UOM Nos) and the Kg for those Nos.

Material Planning showed Qty to Manufacture -- the drawing's piece count -- beside the
finished-goods item's stock UOM, so 2 pieces read "2 Kg". Now:

  Material Planning row   Qty to Manufacture (Nos) + UOM Nos + Qty to Manufacture (Kg)
  Production Plan row     Qty (Nos) + Planned Qty (Kg)                     (unchanged)
  Job Work Order row      Qty to Manufacture (Nos) + Qty to Manufacture (Kg)
  Material Issue Plan row Qty to Manufacture (Nos) + Qty to Manufacture (Kg)

Borrows a drawing made after the Kg / Nos change (it has a Cust Weight (per Nos)) and
its BOM, read-only. Everything the test creates happens inside ONE transaction that is
rolled back (frappe.db.commit is a no-op for the run), and tabSeries is compared before
and after, so no document and no series number is left behind.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_planning_nos_kg.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _drawing_with_room():
    """A drawing that has a per-Nos weight, a submitted BOM and Nos left to plan."""
    from manufyxinvenzaerp.production_plan_management.production_plan import fg_nos_remaining

    for d in frappe.get_all(
        "Drawing",
        filters={"docstatus": 1, "weight_per_pcs": [">", 0], "no_of_qty_to_manufacture": [">", 0]},
        fields=["name", "no_of_qty_to_manufacture", "customer_provided_wt", "weight_per_pcs"],
        order_by="creation desc",
        limit=200,
    ):
        bom = frappe.db.get_value("BOM", {"custom_drawing": d.name, "docstatus": 1, "is_active": 1}, "name")
        if bom and flt(fg_nos_remaining(d.name)) >= 1:
            return d, bom
    return None, None


def _material_planning(d, bom):
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        _update_bom_item_weights, get_bom_info,
    )

    print("\n=== Material Planning row ===")
    info = get_bom_info(bom)
    nos = flt(d.no_of_qty_to_manufacture)
    check("get_bom_info: Qty to Manufacture is the drawing's Nos", flt(info["qty_to_manufacture"]), nos)
    check("get_bom_info: its UOM is Nos (not the item's Kg)", info["uom"], "Nos")
    check("get_bom_info: Kg = Cust Weight (Total)", flt(info["qty_to_manufacture_kg"], 3),
          flt(d.customer_provided_wt, 3))

    # A row saved the old way (UOM Kg, no Kg figure) is put right on the next save.
    mp = frappe.new_doc("Material Planning")
    mp.append("bom_items", {"bom_no": bom, "drawing": d.name, "qty_to_manufacture": nos,
                            "uom": "Kg", "qty_to_manufacture_kg": 0})
    _update_bom_item_weights(mp)
    row = mp.bom_items[0]
    check("old row on save: UOM becomes Nos", row.uom, "Nos")
    check("old row on save: Kg filled", flt(row.qty_to_manufacture_kg, 3), flt(d.customer_provided_wt, 3))


def _picker_uom(d):
    """The drawing picker hands the Production Plan the ITEM's stock UOM (Kg).

    The Material Planning row's own UOM is Nos -- the unit of its Qty to Manufacture --
    and passing that through labelled Planned Qty (Kg) "Nos", which ERPNext then refused
    as a fraction of a whole-number UOM ("Quantity (890.08) cannot be a fraction")."""
    from manufyxinvenzaerp.production_plan_management.production_plan import (
        _picker_rows_from_mp, _picker_rows_from_so,
    )

    print("\n=== the drawing picker's UOM ===")
    # Any plan row will do, as long as its drawing carries a per-Nos weight (the borrowed
    # drawing above is not necessarily on a plan).
    mpbi = None
    for cand in frappe.get_all(
        "Material Planning BOM Item", filters={"drawing": ["is", "set"]},
        fields=["parent", "sales_order", "uom", "drawing", "item_code"],
        order_by="modified desc", limit=50,
    ):
        if flt(frappe.db.get_value("Drawing", cand.drawing, "weight_per_pcs")):
            mpbi = cand
            break
    if not mpbi:
        print("  SKIP no Material Planning row on a drawing with a per-Nos weight")
        return
    d = frappe._dict(name=mpbi.drawing, fg_item_code=mpbi.item_code)
    stock_uom = frappe.db.get_value("Item", mpbi.item_code, "stock_uom")
    check("the Material Planning row itself says Nos", mpbi.uom, "Nos")
    for label, rows in (("from Material Planning", _picker_rows_from_mp(mpbi.parent, None)),
                        ("from the Sales Order", _picker_rows_from_so(mpbi.sales_order, None) if mpbi.sales_order else [])):
        row = next((r for r in rows if r.get("drawing") == d.name), None)
        if row:
            check("%s: the plan row's UOM is the item's stock UOM" % label, row["uom"], stock_uom)


def _plan_to_job(d, bom):
    from manufyxinvenzaerp.drawing_management.drawing_utils import create_production_plan_from_bom
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        create_sco_and_mip_from_production_plan,
    )

    print("\n=== Production Plan -> Job Work Order and Material Issue Plan ===")
    pp = frappe.get_doc("Production Plan", create_production_plan_from_bom(bom))
    pp.po_items[0].custom_sec_qty = 1
    pp.save(ignore_permissions=True)
    pp.submit()
    kg = flt(pp.po_items[0].planned_qty, 3)
    per = flt(flt(d.customer_provided_wt) / flt(d.no_of_qty_to_manufacture), 3)
    check("Production Plan: 1 Nos -> Planned Qty (Kg) = the drawing's Kg for 1 piece", kg, per)

    res = create_sco_and_mip_from_production_plan(pp.name)
    for doctype, name in (("Subcontracting Order", res.get("sco")), ("Material Issue Plan", res.get("mip"))):
        rows = frappe.get_all(
            "SCO Drawing Item", filters={"parent": name, "parenttype": doctype, "drawing": d.name},
            fields=["qty_to_manufacture", "qty_to_manufacture_kg"],
        )
        check("%s drawing row: 1 Nos" % doctype, [flt(r.qty_to_manufacture) for r in rows], [1.0])
        check("%s drawing row: Kg = the plan's Planned Qty (Kg)" % doctype,
              [flt(r.qty_to_manufacture_kg, 3) for r in rows], [kg])


def _patch_is_idempotent():
    from manufyxinvenzaerp.patches.v1.fg_nos_kg_on_drawing_rows import execute

    print("\n=== patch ===")
    before = frappe.db.sql("select name, uom, qty_to_manufacture_kg from `tabMaterial Planning BOM Item` order by name")
    execute()
    after = frappe.db.sql("select name, uom, qty_to_manufacture_kg from `tabMaterial Planning BOM Item` order by name")
    check("running the patch again changes nothing", before == after, True)
    old = frappe.db.sql(
        """select count(*) from `tabMaterial Planning BOM Item` b join `tabDrawing` d on d.name = b.drawing
           where ifnull(d.weight_per_pcs, 0) = 0 and ifnull(b.qty_to_manufacture_kg, 0) != 0"""
    )[0][0]
    check("a drawing from before Kg / Nos keeps its Kg blank", old, 0)

    # A site taking this release for the first time runs patches BEFORE after_migrate,
    # where the app creates its custom fields -- so the columns can be missing. Reading
    # one that is not there aborted the whole migrate on the live server ("Unknown column
    # 'tabProduction Plan Item.custom_sec_qty' in 'WHERE'").
    real_has_column = frappe.db.has_column
    for missing in ("custom_sec_qty", "qty_to_manufacture_kg"):
        frappe.db.has_column = (
            lambda dt, col, _m=missing, _real=real_has_column: False if col == _m else _real(dt, col)
        )
        try:
            execute()
            ran = True
        except Exception as e:
            ran = "%s: %s" % (type(e).__name__, e)
        finally:
            frappe.db.has_column = real_has_column
        check("runs without the %s column (fields not created yet)" % missing, ran, True)


def run():
    print("=== verify_fg_planning_nos_kg ===")
    series_before = frappe.db.sql("select name, current from tabSeries order by name")
    real_commit = frappe.db.commit
    frappe.db.commit = lambda *a, **k: None
    try:
        d, bom = _drawing_with_room()
        if not d:
            print("  SKIP no drawing with a per-Nos weight, a BOM and Nos left to plan")
        else:
            print("  borrowing %s (%s Nos, %s Kg) and %s, read-only" % (
                d.name, flt(d.no_of_qty_to_manufacture), flt(d.customer_provided_wt, 3), bom))
            _material_planning(d, bom)
            _picker_uom(d)
            _plan_to_job(d, bom)
        _patch_is_idempotent()
    finally:
        frappe.db.rollback()
        frappe.db.commit = real_commit
    series_after = frappe.db.sql("select name, current from tabSeries order by name")
    check("no naming-series number used", series_before == series_after, True)

    print()
    failed = checks.count(False)
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, len(checks)))
    else:
        print("ALL %d CHECKS PASSED" % len(checks))
