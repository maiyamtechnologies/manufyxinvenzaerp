"""A drawing split over two Production Plans: each plan gets its share of the raw
material, and neither can transfer the other's.

Scenario, built inside ONE transaction that is rolled back (frappe.db.commit is a
no-op for the run; tabSeries compared before and after):

  1B3 (DRW-2026-00248) is 4 NOS on one Material Planning row: 16 x ISMB400 of
  6936 mm, 6,836.131 Kg, batch ISMB400-L6936-R003. Its real plan is set aside and
  two fresh plans take it instead -- plan A 1 NOS, plan B 3 NOS -- each with its own
  Material Issue Plan. The row is put back to "reserved, nothing moved yet".

  A is owed 1/4: 4 bars, 1,709.033 Kg.  B is owed 3/4: 12 bars, 5,127.098 Kg.

Also checked: the picker's Total / Already Planned / To Use Now figures, the
Material Issue Plan's own rows and weights, the double-counted partial transfer,
and that a job's Final Stock Entry no longer releases another plan's reservation.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_drawing_split_plans.run
"""

import frappe
from frappe.utils import flt

checks = []

DRAWING = "DRW-2026-00248"
DUNO = "1B3"
SO = "SAL-ORD-2026-00027"
REAL_PP = "PP-INT-2026-00001"
MP = "MP-2026-00010"
BATCH = "ISMB400-L6936-R003"
ITEM = "ISMB400"
TOTAL_KG = 6836.131
SCO = "SC-ORD-2026-00002"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-70s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, fragment):
    try:
        fn()
    except Exception as e:
        return fragment.lower() in frappe.utils.strip_html(str(e)).lower()
    return False


def _mm_row():
    return frappe.db.get_value(
        "Material Planning Material Mapping",
        {"parent": MP, "duno_mark_no": DUNO, "batch": BATCH}, "name")


def _new_plan(nos):
    """A draft plan holding `nos` of 1B3, copied from the real plan's 1B3 row."""
    real = frappe.get_doc("Production Plan", REAL_PP)
    pp = frappe.copy_doc(real)
    pp.docstatus = 0
    pp.custom_material_issue_plan = None
    pp.set("po_items", [r for r in pp.po_items if r.custom_drawing == DRAWING])
    pp.po_items[0].custom_sec_qty = nos
    pp.flags.ignore_permissions = True
    pp.insert(ignore_mandatory=True)
    return pp.name


def _new_mip(pp_name):
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        populate_from_production_plan,
    )
    real = frappe.db.get_value("Material Issue Plan", "MIP-2026-00002",
                               ["company", "source_warehouse", "supplier_warehouse"], as_dict=True)
    # A job of its own for each plan (one Material Issue Plan per job): only its company
    # and supplier warehouse are read, to know where the transfer goes.
    sco = "ZZ-SPLIT-" + pp_name
    frappe.db.sql(
        """INSERT INTO `tabSubcontracting Order` (name, docstatus, company, supplier_warehouse,
               creation, modified) VALUES (%s, 0, %s, %s, NOW(), NOW())""",
        (sco, real.company, real.supplier_warehouse))
    mip = frappe.new_doc("Material Issue Plan")
    mip.company = real.company
    mip.production_plan = pp_name
    mip.subcontracting_order = sco
    mip.source_warehouse = real.source_warehouse
    mip.supplier_warehouse = real.supplier_warehouse
    mip.flags.ignore_permissions = True
    mip.insert(ignore_mandatory=True)
    populate_from_production_plan(mip.name)
    return frappe.get_doc("Material Issue Plan", mip.name)


def _record_transfer(mip, qty, docstatus=1):
    """A transfer of R003 out of the stores for this plan, as the ledger would show it."""
    se = frappe.generate_hash(length=10)
    frappe.db.sql(
        """INSERT INTO `tabStock Entry` (name, docstatus, stock_entry_type, company, custom_mip_ref,
               creation, modified)
           VALUES (%s, %s, 'Send to Subcontractor', %s, %s, NOW(), NOW())""",
        (se, docstatus, mip.company, mip.name))
    frappe.db.sql(
        """INSERT INTO `tabStock Entry Detail` (name, parent, parenttype, parentfield, idx, docstatus,
               item_code, batch_no, qty, s_warehouse, t_warehouse, creation, modified)
           VALUES (%s, %s, 'Stock Entry', 'items', 1, %s, %s, %s, %s, %s, %s, NOW(), NOW())""",
        (frappe.generate_hash(length=10), se, docstatus, ITEM, BATCH, qty,
         mip.source_warehouse, mip.supplier_warehouse))
    return se


def _pending(mip):
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import get_mip_pending_items
    line = next((p for p in get_mip_pending_items(mip.name) if p["batch_no"] == BATCH), None)
    return (flt(line["qty"], 3), flt(line["custom_sec_qty"], 3)) if line else (0.0, 0.0)


def _available(mip):
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _batch_availability_for_plan,
    )
    return _batch_availability_for_plan(mip, ITEM, BATCH)


def _scenario():
    from manufyxinvenzaerp.production_plan_management import drawing_split as ds
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as mt
    from manufyxinvenzaerp.subcontracting_management.subcontracting import _get_mp_reserved_batches

    print("\n=== setting up: 1B3 split 1 + 3 over two new plans ===")
    frappe.db.set_value("Production Plan", REAL_PP, "docstatus", 2, update_modified=False)
    row = _mm_row()
    frappe.db.set_value("Material Planning Material Mapping", row,
                        {"is_reserved": 1, "reserved_qty": TOTAL_KG, "transferred_qty": 0,
                         "fully_transferred": 0}, update_modified=False)
    pp_a = _new_plan(1)
    pp_b = _new_plan(3)
    mip_a, mip_b = _new_mip(pp_a), _new_mip(pp_b)

    print("\n=== 1. each plan's slice of the drawing ===")
    sa = ds.plan_drawing_slices(pp_a).get((MP, DUNO))
    sb = ds.plan_drawing_slices(pp_b).get((MP, DUNO))
    check("plan A (made first) holds the first quarter", (sa["start"], sa["end"]), (0.0, 0.25))
    check("plan B holds the other three quarters", (sb["start"], sb["end"]), (0.25, 1.0))
    check("share named as it is in messages", ds.share_label(sb), "3 of 4 NOS")
    exact = all(flt(ds.portion(x, sa) + ds.portion(x, sb), 3) == flt(x, 3)
                for x in (TOTAL_KG, 1, 0.001, 2260.8, 16, 0.227, 7.078, 12345.678))
    check("the two shares always add back to the whole, to the gram", exact, True)

    print("\n=== 2. the picker: Total / Already Planned / left for this plan ===")
    from manufyxinvenzaerp.production_plan_management.production_plan import get_pp_drawings_for_picker
    r = next(x for x in get_pp_drawings_for_picker("sales_order", SO, pp_b) if x.get("drawing") == DRAWING)
    check("from plan B: total 4, 1 planned elsewhere, 3 left", (r["drawing_nos"], r["nos_left"]), (4.0, 3.0))
    r = next(x for x in get_pp_drawings_for_picker("sales_order", SO, "") if x.get("drawing") == DRAWING)
    check("from a new plan: nothing left, so it is not offered", (r["nos_left"], bool(r["already_in_pp"])), (0.0, True))

    print("\n=== 3. each Material Issue Plan lists only its share ===")
    for mip, kg, nos, label in ((mip_a, 1709.033, 4.0, "A"), (mip_b, 5127.098, 12.0, "B")):
        rows = [x for x in mip.raw_materials if x.duno_mark_no == DUNO and x.batch_no == BATCH]
        check("plan %s ISMB400 row: %s Kg, %s bars" % (label, kg, nos),
              (flt(sum(flt(x.qty) for x in rows), 3), flt(sum(flt(x.sec_qty) for x in rows), 3)), (kg, nos))
    # Every other raw-material row of the drawing is divided the same way, and the two
    # plans' rows add back to the whole drawing's.
    whole_kg = whole_nos = 0.0
    for tbl, qf in (("Material Planning Material Mapping", "batch_calc_qty"),
                    ("Material Planning Available Raw Material", "required_qty"),
                    ("Material Planning Unavailable Item", "qty")):
        for r in frappe.get_all(tbl, filters={"parent": MP, "duno_mark_no": DUNO},
                                fields=[qf + " as q", "sec_qty"] if tbl != "Material Planning Material Mapping"
                                else ["batch_calc_qty as q", "batch_sec_qty as sec_qty", "batch", "qty as rq", "sec_qty as rs"]):
            if tbl == "Material Planning Material Mapping" and not r.get("batch"):
                r.q, r.sec_qty = r.rq, r.rs
            whole_kg += flt(r.q)
            whole_nos += flt(r.sec_qty)
    both = [x for m in (mip_a, mip_b) for x in m.raw_materials if x.duno_mark_no == DUNO]
    check("A's and B's raw-material rows add back to the whole drawing's",
          (flt(sum(flt(x.qty) for x in both), 3), flt(sum(flt(x.sec_qty) for x in both), 3)),
          (flt(whole_kg, 3), flt(whole_nos, 3)))
    for mip, nos, label in ((mip_a, 1.0, "A"), (mip_b, 3.0, "B")):
        d = next(x for x in mip.drawing_items if x.duno_mark_no == DUNO)
        check("plan %s drawing row: %s NOS" % (label, int(nos)), flt(d.qty_to_manufacture), nos)
    from manufyxinvenzaerp.subcontracting_management.subcontracting import _get_mp_drawing_weights_by_duno
    whole = flt(_get_mp_drawing_weights_by_duno(MP).get(DUNO))
    da = next(x for x in frappe.get_doc("Material Issue Plan", mip_a.name).drawing_items if x.duno_mark_no == DUNO)
    db_ = next(x for x in frappe.get_doc("Material Issue Plan", mip_b.name).drawing_items if x.duno_mark_no == DUNO)
    check("planned weight on the two plans adds back to the drawing's",
          flt(flt(da.total_weight_kg) + flt(db_.total_weight_kg), 3), flt(whole, 3))
    check("plan A carries a quarter of it", flt(da.total_weight_kg, 3), ds.portion(whole, sa))

    print("\n=== 4. transfer lists: A 4 bars, B 12 bars ===")
    check("plan A pending", _pending(mip_a), (1709.033, 4.0))
    check("plan B pending", _pending(mip_b), (5127.098, 12.0))

    print("\n=== 5. neither plan can take the other's share ===")
    real_free = mt._batch_free_qty
    mt._batch_free_qty = lambda *a, **k: TOTAL_KG
    try:
        a = _available(mip_a)
        b = _available(mip_b)
        check("A may take its quarter, not the whole batch", flt(a.available, 3), 1709.033)
        check("B may take its three quarters", flt(b.available, 3), 5127.098)
        check("A is told why: the other plan's share, named",
              any(pp_b in c["material_planning"] for c in a.reserved_for_others), True)

        sel = lambda qty, sec: [{"item_code": ITEM, "batch_no": BATCH, "qty": qty, "custom_sec_qty": sec,
                                 "cnc_process": 0}]
        check("A sending its 4 bars passes", _throws(lambda: mt._validate_selected_against_stock(
            mip_a, sel(1709.033, 4)), "cannot"), False)
        check("A rounding up to 5 bars (B's material) is refused",
              _throws(lambda: mt._validate_selected_against_stock(mip_a, sel(2136.291, 5)), "Not enough stock"), True)

        print("\n=== 6. A transfers its 4 bars ===")
        _record_transfer(mip_a, 1709.033)
        frappe.db.set_value("Material Planning Material Mapping", row,
                            {"reserved_qty": 5127.098, "transferred_qty": 1709.033}, update_modified=False)
        mt._batch_free_qty = lambda *a, **k: 5127.098
        check("A has nothing left to send", _pending(mip_a), (0.0, 0.0))
        check("B's pending is untouched: still 12 bars", _pending(mip_b), (5127.098, 12.0))
        check("A can take nothing more of the batch", flt(_available(mip_a).available, 3), 0.0)
        check("B can take all that is left", flt(_available(mip_b).available, 3), 5127.098)

        print("\n=== 7. B sends 6 bars now, 6 later ===")
        _record_transfer(mip_b, 2563.549)
        frappe.db.set_value("Material Planning Material Mapping", row,
                            {"reserved_qty": 2563.549, "transferred_qty": 4272.582}, update_modified=False)
        mt._batch_free_qty = lambda *a, **k: 2563.549
        check("B's pending is the other 6 bars -- not counted twice", _pending(mip_b), (2563.549, 6.0))
        check("and a draft for them blocks a second copy of the same bars",
              (_record_transfer(mip_b, 2563.549, docstatus=0) and _pending(mip_b)), (0.0, 0.0))
    finally:
        mt._batch_free_qty = real_free

    print("\n=== 8. the reserved basis is unchanged for other callers ===")
    reserved = _get_mp_reserved_batches(MP, "Stores - MIPL", None, duno_filter={DUNO})
    held = _get_mp_reserved_batches(MP, "Stores - MIPL", None, duno_filter={DUNO}, basis="held")
    check("default basis: what is still reserved", flt(sum(x["qty"] for x in reserved if x["batch_no"] == BATCH), 3), 2563.549)
    check("held basis: what the row was given", flt(sum(x["qty"] for x in held if x["batch_no"] == BATCH), 3), TOTAL_KG)
    return mip_a, mip_b


def _release_scope(mip):
    from manufyxinvenzaerp.production_management.stock_entry import _downstream_sourced_rows, _job_mip_name

    print("\n=== 9. a job's own supplier-side entries release nothing in the stores ===")
    se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Manufacture",
                         "custom_mip_ref": mip.name, "items": [
                             {"item_code": ITEM, "s_warehouse": mip.supplier_warehouse, "qty": 1},
                             {"item_code": ITEM, "s_warehouse": mip.source_warehouse, "qty": 1}]})
    se.items[0].name, se.items[1].name = "row-supplier", "row-stores"
    check("consumption at the supplier is skipped; the stores row is not",
          _downstream_sourced_rows(se), {"row-supplier"})
    fg = frappe._dict(custom_mip_ref=None, custom_sco_ref=None, subcontracting_order="SC-ORD-2026-00002",
                      work_order=None)
    check("a Final Stock Entry is traced to its plan through the job",
          _job_mip_name(fg), frappe.db.get_value("Material Issue Plan", {"subcontracting_order": "SC-ORD-2026-00002"}))


def _whole_plan_unchanged():
    from manufyxinvenzaerp.production_plan_management.drawing_split import plan_drawing_slices

    print("\n=== 10. a plan holding whole drawings has no slices (nothing changes) ===")
    whole = [p for p in frappe.get_all("Production Plan", filters={"docstatus": 1}, pluck="name")]
    check("no submitted plan on this site has a split drawing",
          [p for p in whole if plan_drawing_slices(p)], [])


def run():
    print("=== verify_drawing_split_plans ===")
    series_before = frappe.db.sql("select name, current from tabSeries order by name")
    real_commit = frappe.db.commit
    frappe.db.commit = lambda *a, **k: None
    try:
        _whole_plan_unchanged()
        mip_a, _mip_b = _scenario()
        _release_scope(mip_a)
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
