"""Customer weight downstream is the drawing's Total -- all pieces -- never one piece.

The original fault: the Sales Order DUNO row held customer weight PER PIECE and it was
copied straight through, so a drawing making two pieces read 890 Kg of customer weight
against 1,814 Kg of planned material -- "104% waste" that was really 1.9%. The fix of
the day multiplied by the plan's quantity on the way down.

Under the Kg / Nos plan (sep14 FG plan, D2 / D30) the drawing itself holds both figures:
Cust Weight (per Nos) and Cust Weight (Total) = per Nos x Nos. The Total is what goes
downstream -- to the Production Plan, the Job Work Order and Material Issue Plan
drawing rows, Operation Entry and the BOM -- with per Nos beside it, and nothing
multiplies it again. A plan for part of a drawing (4 of 10 Nos) still shows the
drawing's Total; the part is in its Planned Qty (Kg).

Checked on a fresh ZZFG-A3 chain inside one transaction that is rolled back, plus the
wiring: neither the picker nor the cascade scales by a quantity any more.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_customer_weight_scaled.run
"""

import inspect

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.tests.verify_fg_bom_pp_kg import build_fg_chain, hold_commits, make_pp

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    with hold_commits():
        _run()
    _wiring()
    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))


def _run():
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        create_sco_and_mip_from_production_plan,
    )

    c = build_fg_chain()           # 10 Nos x 30 = 300
    pp = make_pp(c.bom, nos=4)     # part of the drawing
    res = create_sco_and_mip_from_production_plan(pp.name)
    print("=== fixture: %s, plan %s (4 of 10 Nos), %s / %s ===" % (c.drawing, pp.name, res["sco"], res["mip"]))

    print()
    print("=== every downstream copy is the drawing's Total, per Nos beside it ===")
    for doctype, total_f, per_f, link, extra in (
        ("Production Plan Item", "custom_customer_weight_kg", "custom_cust_weight_per_nos", "custom_drawing", {}),
        ("SCO Drawing Item", "customer_weight_kg", "cust_weight_per_nos", "drawing",
         {"parenttype": "Subcontracting Order"}),
        ("SCO Drawing Item", "customer_weight_kg", "cust_weight_per_nos", "drawing",
         {"parenttype": "Material Issue Plan"}),
        ("BOM", "custom_cust_weight_total", "custom_cust_weight_per_nos", "custom_drawing", {}),
    ):
        rows = frappe.get_all(doctype, filters={link: c.drawing, **extra}, fields=[total_f, per_f])
        label = doctype + (" (%s)" % extra["parenttype"] if extra else "")
        check("%s: Total 300 / per Nos 30" % label,
              sorted({(flt(r[total_f], 3), flt(r[per_f], 3)) for r in rows}), [(300.0, 30.0)])

    print()
    print("=== the part of the drawing is in the Kg, not in the customer weight ===")
    check("plan Planned Qty = 4/10 of the Total",
          flt(frappe.db.get_value("Production Plan Item", {"parent": pp.name}, "planned_qty"), 3), 120.0)
    check("Job Work Order header Cust Weight (Total)",
          flt(frappe.db.get_value("Subcontracting Order", res["sco"], "custom_customer_weight_kg"), 3), 300.0)
    check("Job Work Order qty = the plan's Kg",
          flt(frappe.db.get_value("Subcontracting Order Item", {"parent": res["sco"]}, "qty"), 3), 120.0)


def _wiring():
    print()
    print("=== nothing multiplies the Total again ===")
    js = open(frappe.get_app_path("manufyxinvenzaerp", "public", "js", "production_plan.js")).read()
    check("the picker no longer scales customer weight by planned qty",
          "flt(s.customer_weight || 0) * flt(child.planned_qty)" in js, False)
    check("the picker takes the drawing's Total as it is",
          "child.custom_customer_weight_kg  = flt(s.cust_weight_total, 3)" in js, True)

    from manufyxinvenzaerp.drawing_management import drawing_utils
    src = inspect.getsource(drawing_utils._cascade_customer_weight)
    check("the cascade no longer multiplies by the drawing's Nos",
          "flt(new_weight) * (flt(frappe.db.get_value(" in src, False)
    check("it writes the Total to Production Plan Items",
          '"custom_customer_weight_kg": new_total' in src, True)
    check("and to Operation Entry",
          '"SOE Drawing Detail", row.name, "customer_provided_weight_kg", new_total' in src, True)
