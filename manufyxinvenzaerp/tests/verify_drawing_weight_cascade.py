"""Update Customer Weight on the Drawing: per Nos in, Total worked out, written back.

sep14 FG plan, D15 / D24 / D30. The popup takes the weight of ONE piece -- the figure
the customer states -- and Cust Weight (Total) = per Nos x No of Qty to Manufacture is
worked out on the server. Both are written to the Drawing and to its Sales Order
Drawing List row, which is otherwise locked once it has a drawing. The change log
keeps the old and new Total. The result reports the Sales Order line's new
difference (ordered vs drawings) without blocking.

Built on a fresh ZZFG-A3 chain (Sales Order -> Drawing -> BOM) inside one transaction
that is rolled back -- no real drawing is touched.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_drawing_weight_cascade.run
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.tests.verify_fg_bom_pp_kg import build_fg_chain, hold_commits, refused

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


def _run():
    from manufyxinvenzaerp.drawing_management.drawing_utils import update_customer_provided_weight

    c = build_fg_chain()
    print("=== fixture: %s on %s, 10 Nos at 30 Kg per Nos ===" % (c.drawing, c.sales_order))

    print()
    print("=== refusals ===")
    check("the same per Nos is refused",
          "same as the current value" in (refused(update_customer_provided_weight, c.drawing, 30) or ""), True)
    check("zero is refused",
          "weight of one piece" in (refused(update_customer_provided_weight, c.drawing, 0) or ""), True)

    print()
    print("=== 31 per Nos ===")
    res = update_customer_provided_weight(c.drawing, 31)
    check("result: old / new per Nos", (res["old_weight_per_nos"], res["new_weight_per_nos"]), (30.0, 31.0))
    check("result: old / new Total", (res["old_weight"], res["new_weight"]), (300.0, 310.0))
    check("result: Nos", res["nos"], 10.0)

    d = frappe.get_doc("Drawing", c.drawing)
    check("Drawing Cust Weight (per Nos)", flt(d.weight_per_pcs, 3), 31.0)
    check("Drawing Cust Weight (Total)", flt(d.customer_provided_wt, 3), 310.0)
    log = d.weight_change_log[-1]
    check("change log keeps the old and new Total", (flt(log.old_weight, 3), flt(log.new_weight, 3)),
          (300.0, 310.0))
    check("and who made it", log.changed_by, frappe.session.user)

    row = frappe.db.get_value("Sales Order DUNO Item", c.duno_row,
                              ["weight_per_pcs", "total_weight", "total_quantity"], as_dict=True)
    check("SO Drawing List row per Nos", flt(row.weight_per_pcs, 3), 31.0)
    check("SO Drawing List row Total", flt(row.total_weight, 3), 310.0)
    check("SO Drawing List row Nos untouched", flt(row.total_quantity), 10.0)
    check("sales_order_updated", res["sales_order_updated"], True)

    print()
    print("=== the Sales Order line difference is reported, not blocked ===")
    lines = res["sales_order_lines"]
    check("one line reported", len(lines), 1)
    line = lines[0] if lines else {}
    check("ordered Kg", line.get("ordered_kg"), 300.0)
    check("drawings Kg", line.get("drawings_kg"), 310.0)
    check("difference Kg", line.get("difference_kg"), 10.0)
    check("difference Nos", line.get("difference_nos"), 0.0)

    print()
    print("=== BOM follows (D12: its quantity IS the Total) ===")
    bom = frappe.db.get_value("BOM", c.bom, ["quantity", "custom_sec_qty", "custom_cust_weight_per_nos",
                                             "custom_cust_weight_total"], as_dict=True)
    check("BOM quantity", flt(bom.quantity, 3), 310.0)
    check("BOM Qty (Nos) unchanged", flt(bom.custom_sec_qty), 10.0)
    check("BOM Cust Weight (per Nos)", flt(bom.custom_cust_weight_per_nos, 3), 31.0)
    check("BOM Cust Weight (Total)", flt(bom.custom_cust_weight_total, 3), 310.0)
    per_unit = frappe.db.get_value("BOM Item", {"parent": c.bom}, ["stock_qty", "qty_consumed_per_unit"],
                                   as_dict=True)
    check("BOM Item qty_consumed_per_unit = stock_qty / new quantity",
          flt(per_unit.qty_consumed_per_unit, 6), flt(flt(per_unit.stock_qty) / 310, 6))
    check("result counts the BOM", res["boms_updated"], 1)

    print()
    print("=== the popup asks for per Nos and shows the new total ===")
    js = open(frappe.get_app_path("manufyxinvenzaerp", "drawing_management", "doctype", "drawing",
                                  "drawing.js")).read()
    check("field label", 'label: __("New Cust Weight (per Nos)")' in js, True)
    check("sends new_weight_per_nos", "new_weight_per_nos: values.new_weight_per_nos" in js, True)
    check("live New total line", '__("New total")' in js, True)
    check("SO difference shown in orange", "difference {6} Kg" in js and "orange" in js, True)
