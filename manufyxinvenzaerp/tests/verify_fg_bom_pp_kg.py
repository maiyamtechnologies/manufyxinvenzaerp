"""Finished goods planned in Nos, carried in Kg: Drawing -> BOM -> Production Plan ->
Job Work Order / Material Issue Plan, and the raw material that follows from it.

sep14 FG plan (.claude/tasks/sep14_fg_uom_plan.md), package A3. The worked example
(section 6): one drawing of 10 Nos at Cust Weight (per Nos) 30, Cust Weight (Total)
300, Rate 20 / Kg.

  - BOM          quantity 300 Kg, Qty (Nos) 10, both Cust Weights            (D12)
  - PP 4 Nos     Planned Qty 120 Kg; a second PP of 7 is refused (6 left)    (D5, D16)
  - Job Work     120 Kg / 4 Nos, drawing row 4 Nos, Rate 20, amount 2,400    (D31, R3)
  - MIP          drawing row 4 Nos, both Cust Weights                        (D27)
  - RM           Material Planning and the plan's own explosion draw exactly 4/10
                 of the drawing's raw material -- the BOM-quantity audit
  - Update Customer Weight to 31 per Nos -> Total 310 everywhere, Operation Entry
    included; a draft Job Work Order recalculates, a submitted one is listed    (D15, R5)

The BOM-quantity audit, as found (the plan's section 5 A3 item 4):
  - production_plan.get_bom_items_direct: the plan passes Kg against a BOM in Kg, so
    the ratio is unchanged. Material Planning passes PIECES, which against a BOM in
    Kg drew 4/300 of the material -- it now passes planned_nos, scaled against the
    BOM's Qty (Nos). Checked below.
  - material_planning.get_bom_info falls back to the BOM's Qty (Nos).
  - bom_class_override ratios (stock_qty / quantity) are unit-free and unchanged.
    Its `cost_per_unit x quantity` operating cost applies only to operations flagged
    set_cost_based_on_bom_qty (none on this site), and every workstation hour rate is
    0 -- so operating cost is untouched by the BOM moving to Kg. Checked below.
  - Update Customer Weight moves the BOM's quantity with the Total, so the ratio
    stays pieces-true after a weight change. Checked below.

Everything runs inside one transaction that is rolled back at the end: frappe.db.commit
is held off for the duration, and every document made is named ZZFG-A3-*.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_bom_pp_kg.run
"""

import frappe
from frappe.utils import add_days, flt, today

checks = []

FG_ITEM = "Fabricated Structurs"
RM_ITEM = "FLAT"            # Structurals, 7.85 Kg/m
PREFIX = "ZZFG-A3"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def refused(fn, *args, **kwargs):
    """The message of the exception fn raises, or None when it does not raise."""
    try:
        fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 -- any refusal counts, the text is checked
        return frappe.utils.strip_html(str(e))
    return None


class hold_commits:
    """Keep everything in one transaction so the finally-rollback removes it all.

    Several functions under test commit (update_customer_provided_weight does, on
    purpose). A commit mid-test would make the fixture permanent, so it is held off."""

    def __enter__(self):
        self._commit = frappe.db.commit
        frappe.db.commit = lambda *a, **k: None
        return self

    def __exit__(self, *exc):
        frappe.db.commit = self._commit
        frappe.db.rollback()
        frappe.message_log = []
        return False


def company():
    return (frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company"))


def build_fg_chain(duno="D1", nos=10, per_nos=30, rate=20, rm_length=1000, rm_sec=2):
    """A fresh Sales Order row -> Drawing (Final Revision) -> submitted BOM, made with
    the app's own functions. Call inside hold_commits: nothing here is kept.

    Returns a dict with sales_order, duno_row, drawing, bom and the drawing's RM Kg."""
    from manufyxinvenzaerp.drawing_management.drawing_utils import (
        create_bom_from_drawing, mark_as_final_revision,
    )

    comp = company()
    customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")
    mark = "%s-%s" % (PREFIX, duno)
    cdn = "%s-CDN-%s" % (PREFIX, duno)

    # Inserted without validate: the Sales Order is only the parent of the Drawing
    # List row here, and its own checks (Verify Raw Materials etc.) are not under test.
    so = frappe.get_doc({
        "doctype": "Sales Order",
        "company": comp,
        "customer": customer,
        "transaction_date": today(),
        "delivery_date": add_days(today(), 30),
        "po_no": PREFIX,
        "items": [{
            "item_code": FG_ITEM, "qty": flt(nos * per_nos, 3), "rate": 1, "uom": "Kg",
            "delivery_date": add_days(today(), 30), "custom_sec_qty": nos, "custom_sec_uom": "Nos",
        }],
        "custom_duno_items": [{
            "item": FG_ITEM, "duno_mark_no": mark, "drawing_number": cdn,
            "total_quantity": nos, "weight_per_pcs": per_nos, "total_weight": flt(nos * per_nos, 3),
        }],
    })
    so.flags.ignore_validate = True
    so.flags.ignore_mandatory = True
    so.insert(ignore_permissions=True)

    drawing = frappe.get_doc({
        "doctype": "Drawing",
        "sales_order": so.name,
        "customer": customer,
        "duno_mark_no": mark,
        "customer_drawing_number": cdn,
        "fg_item_code": FG_ITEM,
        "fg_item_name": FG_ITEM,
        "no_of_qty_to_manufacture": nos,
        "weight_per_pcs": per_nos,
        "rs_rate_per_kg": rate,
        "items": [{
            "item_number": "1", "material_code": RM_ITEM, "material_name": RM_ITEM,
            "parent_item_group": "Structurals", "unit_weight": 7.85, "length": rm_length,
            "sec_qty": rm_sec, "sec_uom": "Nos", "uom": "Kg",
        }],
    })
    drawing.insert(ignore_permissions=True)
    drawing.submit()
    mark_as_final_revision(drawing.name)

    bom_name = create_bom_from_drawing(drawing.name)
    bom = frappe.get_doc("BOM", bom_name)
    bom.submit()

    return frappe._dict(
        sales_order=so.name,
        duno_row=so.custom_duno_items[0].name,
        drawing=drawing.name,
        duno=mark,
        bom=bom_name,
        rm_kg=flt(drawing.items[0].total_qty, 3),
        rm_piece_kg=flt(drawing.items[0].qty, 3),
    )


def make_pp(bom, nos=None, submit=False):
    """A Production Plan from the BOM's own button, optionally re-set to `nos` pieces."""
    from manufyxinvenzaerp.drawing_management.drawing_utils import create_production_plan_from_bom

    pp = frappe.get_doc("Production Plan", create_production_plan_from_bom(bom))
    if nos is not None:
        pp.po_items[0].custom_sec_qty = nos
        pp.save(ignore_permissions=True)
    if submit:
        pp.submit()
    return pp


def rm_kg_from_pp(pp):
    """Raw material Kg the plan's own explosion asks for (Get Raw Materials)."""
    from manufyxinvenzaerp.production_plan_management.production_plan import get_exploded_items

    total = 0.0
    for row in pp.po_items:
        for d in get_exploded_items({}, pp.company, row.bom_no, 1, planned_qty=row.planned_qty).values():
            total += flt(d.qty)
    return flt(total, 3)


def rm_kg_from_mp(bom, nos):
    """Raw material Kg Material Planning asks for, for `nos` pieces of the drawing."""
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        get_bom_info, get_raw_materials,
    )

    info = get_bom_info(bom)
    rows = get_raw_materials(frappe.as_json({
        "company": company(),
        "for_warehouse": "",
        "bom_items": [{**info, "bom_no": bom, "qty_to_manufacture": nos}],
    }))
    return flt(sum(flt(r["qty"]) for r in rows), 3), info


def run():
    with hold_commits():
        _run()
    _summary()


def _run():
    from manufyxinvenzaerp.drawing_management.drawing_utils import (
        create_production_plan_from_bom, update_customer_provided_weight,
    )
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        _job_work_figures, create_sco_and_mip_from_production_plan,
    )

    c = build_fg_chain()
    print("=== fixture: %s / %s / %s, drawing RM %s Kg ===" % (c.sales_order, c.drawing, c.bom, c.rm_kg))

    print()
    print("=== Drawing: Total = per Nos x Nos ===")
    d = frappe.db.get_value("Drawing", c.drawing,
                            ["weight_per_pcs", "customer_provided_wt", "total_weight"], as_dict=True)
    check("Cust Weight (per Nos)", flt(d.weight_per_pcs, 3), 30.0)
    check("Cust Weight (Total) worked out on validate", flt(d.customer_provided_wt, 3), 300.0)
    check("total_weight is still the raw-material roll-up (one piece)", flt(d.total_weight, 3), c.rm_piece_kg)

    print()
    print("=== BOM in Kg (D12) ===")
    bom = frappe.db.get_value("BOM", c.bom, ["quantity", "custom_sec_qty", "custom_sec_uom",
                                             "custom_cust_weight_per_nos", "custom_cust_weight_total",
                                             "operating_cost"], as_dict=True)
    check("quantity = Cust Weight (Total)", flt(bom.quantity, 3), 300.0)
    check("Qty (Nos) = drawing Nos", flt(bom.custom_sec_qty, 3), 10.0)
    check("Sec UOM Nos", bom.custom_sec_uom, "Nos")
    check("Cust Weight (per Nos)", flt(bom.custom_cust_weight_per_nos, 3), 30.0)
    check("Cust Weight (Total)", flt(bom.custom_cust_weight_total, 3), 300.0)

    print()
    print("=== audit: BOM operating cost does not scale with quantity on this site ===")
    check("no operation costed per BOM quantity",
          frappe.db.count("BOM Operation", {"set_cost_based_on_bom_qty": 1}), 0)
    check("no BOM on FG-based operating cost", frappe.db.count("BOM", {"fg_based_operating_cost": 1}), 0)
    check("this BOM's operating cost", flt(bom.operating_cost, 2), 0.0)

    print()
    print("=== Material Planning in pieces: get_bom_info + RM explosion ===")
    mp_rm_10, info = rm_kg_from_mp(c.bom, 10)
    check("get_bom_info qty_to_manufacture = drawing Nos", flt(info.get("qty_to_manufacture")), 10.0)
    check("MP RM for all 10 Nos = the drawing's RM", mp_rm_10, c.rm_kg)
    mp_rm_4, _i = rm_kg_from_mp(c.bom, 4)
    check("MP RM for 4 Nos = 4/10 of it", mp_rm_4, flt(c.rm_kg * 4 / 10, 3))

    print()
    print("=== Material Planning -> Make Production Plan sets only Qty (Nos) ===")
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        make_production_plan,
    )
    from manufyxinvenzaerp.production_plan_management.production_plan import get_pp_drawings_for_picker
    mp = frappe.get_doc({
        "doctype": "Material Planning", "company": company(), "posting_date": today(),
        "bom_items": [{**info, "bom_no": c.bom, "qty_to_manufacture": 4}],
    })
    mp.flags.ignore_validate = True
    mp.insert(ignore_permissions=True)
    rows = get_pp_drawings_for_picker("material_planning", mp.name)
    check("picker offers the drawing with all 10 Nos left",
          [(r.get("nos_left"), r.get("drawing_nos"), bool(r.get("already_in_pp"))) for r in rows],
          [(10.0, 10.0, False)])
    check("picker carries the Total for the Kg mirror", flt(rows[0].get("cust_weight_total"), 3), 300.0)
    mpp = frappe.get_doc("Production Plan", make_production_plan(mp.name))
    check("MP plan: Qty (Nos) = MP qty_to_manufacture", flt(mpp.po_items[0].custom_sec_qty), 4.0)
    check("MP plan: Planned Qty (Kg) worked out by apply_fg_nos", flt(mpp.po_items[0].planned_qty, 3), 120.0)
    frappe.db.set_value("Material Planning", mp.name, "production_plan", "")
    frappe.delete_doc("Production Plan", mpp.name, ignore_permissions=True, force=True)

    print()
    print("=== Production Plan from the BOM: defaults to every piece left ===")
    pp1 = make_pp(c.bom)
    r = pp1.po_items[0]
    check("Qty (Nos) defaults to 10", flt(r.custom_sec_qty), 10.0)
    check("Planned Qty (Kg) = 300", flt(r.planned_qty, 3), 300.0)

    print()
    print("=== PP 4 Nos -> 120 Kg (D5) ===")
    r.custom_sec_qty = 4
    pp1.save(ignore_permissions=True)
    pp1.reload()
    r = pp1.po_items[0]
    check("Planned Qty (Kg)", flt(r.planned_qty, 3), 120.0)
    check("Cust Weight (Total) on the row is the drawing's", flt(r.custom_customer_weight_kg, 3), 300.0)
    check("Cust Weight (per Nos)", flt(r.custom_cust_weight_per_nos, 3), 30.0)
    check("Sec UOM", r.custom_sec_uom, "Nos")
    check("header total_planned_qty follows", flt(pp1.total_planned_qty, 3), 120.0)
    check("pending_qty follows", flt(r.pending_qty, 3), 120.0)
    check("plan's RM explosion = 4/10 of the drawing", rm_kg_from_pp(pp1), flt(c.rm_kg * 4 / 10, 3))

    r.custom_sec_qty = 2.5
    check("half a piece is refused", "whole number" in (refused(pp1.save) or ""), True)
    pp1.reload()
    pp1.submit()

    print()
    print("=== D16: a second plan may take what is left, never more ===")
    pp2 = make_pp(c.bom)
    check("second plan defaults to the 6 left", flt(pp2.po_items[0].custom_sec_qty), 6.0)
    pp2.po_items[0].custom_sec_qty = 7
    msg = refused(pp2.save) or ""
    check("7 Nos is refused", bool(msg), True)
    check("the refusal names the other plan", pp1.name in msg, True)
    check("and says how many are left", "6 Nos are left" in msg, True)
    pp2.reload()
    pp2.po_items[0].custom_sec_qty = 6
    pp2.save(ignore_permissions=True)
    check("6 Nos is accepted: 180 Kg", flt(pp2.po_items[0].planned_qty, 3), 180.0)
    check("a third plan has nothing left",
          "already on a Production Plan" in (refused(create_production_plan_from_bom, c.bom) or ""), True)

    print()
    print("=== picker: Nos left per drawing ===")
    from manufyxinvenzaerp.production_plan_management.production_plan import _mark_already_in_pp
    rows = [{"drawing": c.drawing, "bom_no": c.bom}]
    _mark_already_in_pp(rows, "")
    check("fully planned drawing has 0 left", flt(rows[0]["nos_left"]), 0.0)
    check("and is not offered", bool(rows[0]["already_in_pp"]), True)
    rows = [{"drawing": c.drawing, "bom_no": c.bom}]
    _mark_already_in_pp(rows, pp2.name)
    check("seen from plan 2 itself: 6 left", flt(rows[0]["nos_left"]), 6.0)
    check("and it is this plan's row", rows[0]["already_in_this_pp"], True)

    print()
    print("=== Job Work Order + MIP from plan 1 (4 Nos) ===")
    res = create_sco_and_mip_from_production_plan(pp1.name)
    sco = frappe.get_doc("Subcontracting Order", res["sco"])
    item = sco.items[0]
    check("item qty = PP Kg", flt(item.qty, 3), 120.0)
    check("item Qty (Nos)", flt(item.custom_sec_qty), 4.0)
    check("item Sec UOM", item.custom_sec_uom, "Nos")
    check("item rate = 20", flt(item.rate, 2), 20.0)
    check("item amount = 2,400", flt(item.amount, 2), 2400.0)
    check("header total", flt(sco.total, 2), 2400.0)
    dr = sco.custom_drawing_items[0]
    check("drawing row qty_to_manufacture = 4 Nos", flt(dr.qty_to_manufacture), 4.0)
    check("drawing row Cust Weight (Total)", flt(dr.customer_weight_kg, 3), 300.0)
    check("drawing row Cust Weight (per Nos)", flt(dr.cust_weight_per_nos, 3), 30.0)
    check("drawing row Rate / Kg", flt(dr.rate_per_kg, 2), 20.0)
    check("drawing row Job Work Amount", flt(dr.job_work_amount, 2), 2400.0)
    mip = frappe.get_doc("Material Issue Plan", res["mip"])
    m = mip.drawing_items[0]
    check("MIP drawing row 4 Nos", flt(m.qty_to_manufacture), 4.0)
    check("MIP Cust Weight (Total)", flt(m.customer_weight_kg, 3), 300.0)
    check("MIP Cust Weight (per Nos)", flt(m.cust_weight_per_nos, 3), 30.0)
    # A later save runs the override's own totalling; it must land on the same amount.
    sco.save(ignore_permissions=True)
    check("re-saved Job Work Order keeps amount 2,400", flt(sco.items[0].amount, 2), 2400.0)

    print()
    print("=== R3: several drawings on one order -> Kg-weighted item rate ===")
    fig = _job_work_figures([
        frappe._dict(drawing=None, kg=120, rate_per_kg=20, name="a"),
        frappe._dict(drawing=None, kg=90, rate_per_kg=15, name="b"),
    ])
    check("amount = sum of the drawings'", fig.amount, 3750.0)
    check("Kg", fig.kg, 210.0)
    check("Kg x weighted rate gives the amount back", flt(fig.kg * fig.rate, 2), 3750.0)

    print()
    print("=== Material Planning: _update_bom_item_weights copies the Total ===")
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        _update_bom_item_weights,
    )
    fake_mp = frappe._dict(name="%s-NO-MP" % PREFIX, bom_items=[
        frappe._dict(duno_mark_no=c.duno, sales_order=c.sales_order)])
    _update_bom_item_weights(fake_mp)
    check("customer_provided_weight_kg = Cust Weight (Total)",
          flt(fake_mp.bom_items[0].customer_provided_weight_kg, 3), 300.0)

    print()
    print("=== Update Customer Weight to 31 per Nos: the RM ratio holds ===")
    update_customer_provided_weight(c.drawing, 31)
    check("BOM quantity follows the Total", flt(frappe.db.get_value("BOM", c.bom, "quantity"), 3), 310.0)
    pp2.reload()
    check("draft plan 2 (6 Nos) is now 186 Kg", flt(pp2.po_items[0].planned_qty, 3), 186.0)
    check("its RM is still 6/10 of the drawing", rm_kg_from_pp(pp2), flt(c.rm_kg * 6 / 10, 3))
    mp_rm_4_after, _i = rm_kg_from_mp(c.bom, 4)
    check("MP RM for 4 Nos still 4/10", mp_rm_4_after, flt(c.rm_kg * 4 / 10, 3))


def _summary():
    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
