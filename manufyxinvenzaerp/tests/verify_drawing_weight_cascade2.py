"""A customer-weight change after the plans and Job Work Orders exist (sep14 FG plan, R5).

One drawing, 10 Nos at 30 Kg per Nos (Total 300), Rate 20 / Kg, split over two plans:

  plan 1   4 Nos, submitted -> Job Work Order 1, submitted   120 Kg, amount 2,400
  plan 2   6 Nos, draft     -> Job Work Order 2, draft       180 Kg, amount 3,600

Update Customer Weight to 31 per Nos (Total 310):
  - every Production Plan Item and Job Work Order / MIP drawing row carries the new
    Total (310) with per Nos (31) alongside -- Total always means all pieces (D2);
  - the draft plan's Planned Qty follows: 6 x 31 = 186 Kg; the submitted one keeps 120;
  - the draft Job Work Order recalculates: 186 Kg, amount 3,720, rate 20;
  - the submitted one keeps 120 Kg / 2,400 and is listed in the result, so the user
    can decide whether to amend it.

Built on a fresh ZZFG-A3 chain inside one transaction that is rolled back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_drawing_weight_cascade2.run
"""

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
    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))


def _jwo(pp_name):
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        create_sco_and_mip_from_production_plan,
    )
    return create_sco_and_mip_from_production_plan(pp_name)


def _run():
    from manufyxinvenzaerp.drawing_management.drawing_utils import update_customer_provided_weight

    c = build_fg_chain()
    pp1 = make_pp(c.bom, nos=4, submit=True)
    pp2 = make_pp(c.bom, nos=6)
    j1, j2 = _jwo(pp1.name), _jwo(pp2.name)
    sco1 = frappe.get_doc("Subcontracting Order", j1["sco"])
    sco1.submit()
    print("=== fixture: %s | %s (4 Nos, submitted) -> %s submitted | %s (6 Nos, draft) -> %s draft ==="
          % (c.drawing, pp1.name, j1["sco"], pp2.name, j2["sco"]))

    before = frappe.db.get_value("Subcontracting Order Item", {"parent": j2["sco"]},
                                 ["qty", "rate", "amount"], as_dict=True)
    check("draft JWO before: 180 Kg / rate 20 / 3,600",
          (flt(before.qty, 3), flt(before.rate, 2), flt(before.amount, 2)), (180.0, 20.0, 3600.0))

    res = update_customer_provided_weight(c.drawing, 31)

    print()
    print("=== Production Plan Items: Total and per Nos ===")
    for pp in (pp1, pp2):
        r = frappe.db.get_value("Production Plan Item", {"parent": pp.name},
                                ["custom_customer_weight_kg", "custom_cust_weight_per_nos", "planned_qty"],
                                as_dict=True)
        check("%s Cust Weight (Total)" % pp.name, flt(r.custom_customer_weight_kg, 3), 310.0)
        check("%s Cust Weight (per Nos)" % pp.name, flt(r.custom_cust_weight_per_nos, 3), 31.0)
    check("submitted plan keeps 120 Kg",
          flt(frappe.db.get_value("Production Plan Item", {"parent": pp1.name}, "planned_qty"), 3), 120.0)
    check("draft plan follows: 6 x 31 = 186 Kg",
          flt(frappe.db.get_value("Production Plan Item", {"parent": pp2.name}, "planned_qty"), 3), 186.0)
    check("draft plan header total",
          flt(frappe.db.get_value("Production Plan", pp2.name, "total_planned_qty"), 3), 186.0)
    check("result: draft plans recalculated", res["draft_production_plans_recalculated"], 1)

    print()
    print("=== Job Work Order / MIP drawing rows ===")
    rows = frappe.get_all("SCO Drawing Item", filters={"drawing": c.drawing},
                          fields=["parent", "parenttype", "customer_weight_kg", "cust_weight_per_nos"])
    check("4 drawing rows (2 JWO + 2 MIP)", len(rows), 4)
    check("every one carries Total 310 / per Nos 31",
          sorted({(flt(r.customer_weight_kg, 3), flt(r.cust_weight_per_nos, 3)) for r in rows}), [(310.0, 31.0)])
    for j in (j1, j2):
        check("%s header Cust Weight (Total)" % j["sco"],
              flt(frappe.db.get_value("Subcontracting Order", j["sco"], "custom_customer_weight_kg"), 3), 310.0)

    print()
    print("=== R5: the draft Job Work Order recalculates ===")
    after = frappe.db.get_value("Subcontracting Order Item", {"parent": j2["sco"]},
                                ["qty", "rate", "amount", "custom_sec_qty"], as_dict=True)
    check("qty 186 Kg", flt(after.qty, 3), 186.0)
    check("Nos unchanged", flt(after.custom_sec_qty), 6.0)
    check("rate stays 20", flt(after.rate, 2), 20.0)
    check("amount 3,720", flt(after.amount, 2), 3720.0)
    dr = frappe.db.get_value("SCO Drawing Item", {"parent": j2["sco"], "parenttype": "Subcontracting Order"},
                             ["job_work_amount", "rate_per_kg"], as_dict=True)
    check("drawing row Job Work Amount 3,720", flt(dr.job_work_amount, 2), 3720.0)
    hdr = frappe.db.get_value("Subcontracting Order", j2["sco"], ["total_qty", "total"], as_dict=True)
    check("header totals", (flt(hdr.total_qty, 3), flt(hdr.total, 2)), (186.0, 3720.0))
    check("listed as recalculated", res["draft_job_work_orders_recalculated"], [j2["sco"]])

    print()
    print("=== R5: the submitted one keeps its qty and amount, and is listed ===")
    sub = frappe.db.get_value("Subcontracting Order Item", {"parent": j1["sco"]}, ["qty", "amount"], as_dict=True)
    check("120 Kg / 2,400 kept", (flt(sub.qty, 3), flt(sub.amount, 2)), (120.0, 2400.0))
    check("listed as submitted", res["submitted_job_work_orders"], [j1["sco"]])

    print()
    print("=== MIP summary refreshed ===")
    check("both MIPs refreshed", res["material_issue_plans_updated"], 2)
