"""A customer weight correction reaches Operation Entry -- as the Total, like everywhere else.

_cascade_customer_weight once stopped before SOE Drawing Detail, so the sheet the shop
floor works from kept the old figure. When it was added, it was given the PER-PIECE
weight while every other copy got the whole row's -- so the same drawing read 31 Kg on
the Operation Entry and 310 Kg on its Job Work Order.

Under the Kg / Nos plan (sep14 FG plan, D2 / D30) the Total -- all pieces of the
drawing -- is sent everywhere, Operation Entry included. Operation Entry also counts
the drawing in pieces: its Qty to Mfg (Nos) comes from the Job Work Order's drawing
row, which is now the plan's Qty (Nos), not its Kg.

Submitted and cancelled entries are updated too. The weight there is descriptive -- it
drives no stock movement or costing -- and leaving a correction out would freeze the
wrong number into the document people read.

Built on a fresh ZZFG-A3 chain (plan of 4 of 10 Nos -> submitted Job Work Order ->
its Operation Entries) inside one transaction that is rolled back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_weight_cascade_reaches_soe.run
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


def _soe_rows(drawing):
    return frappe.get_all("SOE Drawing Detail",
                          filters={"drawing": drawing, "parenttype": "Supplier Operation Entry"},
                          fields=["name", "parent", "qty_to_manufacture", "customer_provided_weight_kg"])


def _run():
    from manufyxinvenzaerp.drawing_management.drawing_utils import update_customer_provided_weight
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        create_sco_and_mip_from_production_plan, create_supplier_operation_entries,
    )

    c = build_fg_chain()
    pp = make_pp(c.bom, nos=4, submit=True)
    sco = frappe.get_doc("Subcontracting Order", create_sco_and_mip_from_production_plan(pp.name)["sco"])
    sco.submit()
    if not _soe_rows(c.drawing):
        create_supplier_operation_entries(sco.name)
    rows = _soe_rows(c.drawing)
    print("=== fixture: %s -> %s, %d Operation Entry drawing row(s) ===" % (pp.name, sco.name, len(rows)))

    print()
    print("=== Operation Entry starts with the Total and counts pieces ===")
    check("there are Operation Entry rows", bool(rows), True)
    check("Qty to Mfg (Nos) = the plan's 4 Nos", sorted({flt(r.qty_to_manufacture) for r in rows}), [4.0])
    check("Cust Weight (Total) = 300", sorted({flt(r.customer_provided_weight_kg, 3) for r in rows}), [300.0])

    print()
    print("=== after 31 per Nos: Total 310, not the per-piece 31 ===")
    res = update_customer_provided_weight(c.drawing, 31)
    rows = _soe_rows(c.drawing)
    check("every Operation Entry row reads 310", sorted({flt(r.customer_provided_weight_kg, 3) for r in rows}),
          [310.0])
    check("the count is reported back", res["operation_entry_rows_updated"], len(rows))
    jwo_total = flt(frappe.db.get_value("SCO Drawing Item",
                                        {"parent": sco.name, "parenttype": "Subcontracting Order"},
                                        "customer_weight_kg"), 3)
    check("and agrees with the Job Work Order's drawing row", jwo_total, 310.0)

    print()
    print("=== the form tells the user about it ===")
    js = open(frappe.get_app_path("manufyxinvenzaerp", "drawing_management", "doctype", "drawing",
                                  "drawing.js")).read()
    check("the message names the count", "Operation Entry drawing rows updated" in js, True)
    check("and passes it through", "m.operation_entry_rows_updated" in js, True)
