"""Delivery Challan (Gate Pass): status, partial returns, and the no-stock guarantee.

This exists because the gate pass is the one document in this app that must NOT
touch stock. It replaces a paper pad and nothing else -- if submitting one ever
starts writing a Stock Ledger Entry it would double-count material that the
Material Issue Plan chain already moves, and nothing on the form would say so.
Check 11 below is that guarantee, asserted rather than assumed.

The other half is return chasing, which has two traps of its own:

  * A partial return must net against the ROW it came from, not the item code.
    Two rows carrying the same item on one challan cannot be told apart otherwise,
    so `against_challan_item` anchors every return row to its source row.

  * "Overdue" is normally a scheduler's job, and this bench runs with
    "pause_scheduler": 1 -- so a scheduler-only implementation would pass review
    and then never once fire. refresh_overdue_gate_passes is therefore called
    directly here, exactly as the list view calls it.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_delivery_challan.run
"""

import frappe
from frappe.utils import add_days, flt, nowdate

from manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan import (
    _render_delivery_challan_html,
    make_return_entry,
    refresh_overdue_gate_passes,
)

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(label, fn, expect_fragment):
    """A rule is only a rule if breaking it is refused."""
    try:
        fn()
    except Exception as e:
        got = expect_fragment.lower() in str(e).lower()
        checks.append(got)
        print("  %-4s %-58s refused: %s"
              % ("OK" if got else "FAIL", label, str(e)[:70].replace("\n", " ")))
        return
    checks.append(False)
    print("  %-4s %-58s NOT REFUSED" % ("FAIL", label))


def _company():
    return frappe.db.sql("SELECT name FROM tabCompany LIMIT 1")[0][0]


def _supplier():
    name = frappe.db.get_value("Supplier", {"disabled": 0}, "name")
    if name:
        return name
    doc = frappe.get_doc({
        "doctype": "Supplier", "supplier_name": "ZZTEST-GATEPASS-SUPPLIER",
        "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
    }).insert(ignore_permissions=True)
    return doc.name


def _challan(company, supplier, challan_type, rows, gp_date=None, return_date=None):
    doc = frappe.new_doc("Delivery Challan")
    doc.update({
        "challan_type": challan_type,
        "company": company,
        "gp_date": gp_date or nowdate(),
        "expected_return_date": return_date,
        "party_type": "Supplier",
        "party": supplier,
        "vehicle_no": "TN-49-ZZ-0001",
        "driver_name": "Test Driver",
        "total_value_of_goods": 25000,
    })
    for qty, weight, desc in rows:
        doc.append("items", {
            "material_description": desc, "uom": "Nos",
            "qty": qty, "weight_kg": weight,
        })
    return doc


def _status(name):
    return frappe.db.get_value("Delivery Challan", name, "status")


def _pending(name):
    return flt(frappe.db.get_value("Delivery Challan", name, "pending_qty"), 3)


def run():
    company = _company()
    supplier = _supplier()

    sle_before = frappe.db.count("Stock Ledger Entry")
    se_before = frappe.db.count("Stock Entry")

    print("=== 1. Naming and the type rules ===")

    gp_a = _challan(company, supplier, "Returnable", [(10, 100, "ZZTEST plate 10mm")],
                    return_date=add_days(nowdate(), 7))
    gp_a.insert(ignore_permissions=True)
    check("names on the GP- series", gp_a.name.startswith("GP-"), True)
    check("draft before submit", gp_a.status, "Draft")
    check("totals summed from the rows", (flt(gp_a.total_qty), flt(gp_a.total_weight_kg)),
          (10.0, 100.0))

    _throws(
        "Returnable without a return date is refused",
        lambda: _challan(company, supplier, "Returnable",
                         [(1, 1, "x")]).insert(ignore_permissions=True),
        "Expected Date of Return is required",
    )

    _throws(
        "Return Entry without a source gate pass is refused",
        lambda: _challan(company, supplier, "Return Entry",
                         [(1, 1, "x")]).insert(ignore_permissions=True),
        "must name the gate pass",
    )

    print()
    print("=== 2. Submit puts the material out ===")
    gp_a.submit()
    check("submitted Returnable is Material Out", _status(gp_a.name), "Material Out")
    check("nothing returned yet, all pending", _pending(gp_a.name), 10.0)

    non_ret = _challan(company, supplier, "Non Returnable", [(3, 30, "ZZTEST scrap")],
                       return_date=add_days(nowdate(), 5))
    non_ret.insert(ignore_permissions=True)
    non_ret.submit()
    check("Non Returnable is Material Out", _status(non_ret.name), "Material Out")
    check("Non Returnable clears the return date", non_ret.expected_return_date, None)

    _throws(
        "Return Entry against a Non Returnable pass is refused",
        lambda: make_return_entry(non_ret.name),
        "only be made against a Returnable",
    )

    print()
    print("=== 3. Partial return nets against the source ROW ===")
    ret1 = make_return_entry(gp_a.name)
    check("return entry prefills the full pending qty", flt(ret1.items[0].qty), 10.0)
    check("return row is anchored to the source row",
          ret1.items[0].against_challan_item, gp_a.items[0].name)
    check("return entry points back at the source", ret1.against_gate_pass, gp_a.name)

    ret1.items[0].qty = 6
    ret1.items[0].weight_kg = 60
    ret1.insert(ignore_permissions=True)
    ret1.submit()

    check("return entry itself is Material In", _status(ret1.name), "Material In")
    check("source is Partially Returned", _status(gp_a.name), "Partially Returned")
    check("source pending is 4 of 10", _pending(gp_a.name), 4.0)
    check("source returned is 6",
          flt(frappe.db.get_value("Delivery Challan", gp_a.name, "returned_qty"), 3), 6.0)
    check("the source ROW carries its own returned qty",
          flt(frappe.db.get_value("Delivery Challan Item", gp_a.items[0].name,
                                  "returned_qty"), 3), 6.0)

    print()
    print("=== 4. Over-returning is refused ===")

    def over_return():
        doc = make_return_entry(gp_a.name)
        doc.items[0].qty = 5          # only 4 are still out
        doc.insert(ignore_permissions=True)

    _throws("returning more than is still out is refused", over_return,
            "only 4.0 is still out")

    print()
    print("=== 5. The remainder closes it, and cancelling reopens it ===")
    ret2 = make_return_entry(gp_a.name)
    check("second return prefills the remaining 4", flt(ret2.items[0].qty), 4.0)
    ret2.insert(ignore_permissions=True)
    ret2.submit()
    check("source is Returned", _status(gp_a.name), "Returned")
    check("nothing pending", _pending(gp_a.name), 0.0)

    ret2.cancel()
    check("cancelling the return reopens the source",
          _status(gp_a.name), "Partially Returned")
    check("the 4 are out again", _pending(gp_a.name), 4.0)

    print()
    print("=== 6. Overdue -- computed, not left to the paused scheduler ===")
    gp_b = _challan(company, supplier, "Returnable", [(5, 50, "ZZTEST bar 20mm")],
                    gp_date=add_days(nowdate(), -10),
                    return_date=add_days(nowdate(), -3))
    gp_b.insert(ignore_permissions=True)
    gp_b.submit()
    check("past its return date on submit -> Overdue", _status(gp_b.name), "Overdue")

    changed = refresh_overdue_gate_passes()
    check("the sweep is idempotent (nothing left to change)", changed, 0)
    check("still Overdue after the sweep", _status(gp_b.name), "Overdue")

    # The submit path can only judge the date it was submitted on. What actually
    # makes a gate pass go overdue is time passing afterwards, and the ONLY thing
    # that notices is this sweep -- so it is worth proving it flips a stale row,
    # not just that it leaves a correct one alone.
    gp_c = _challan(company, supplier, "Returnable", [(2, 20, "ZZTEST angle 50mm")],
                    return_date=add_days(nowdate(), 7))
    gp_c.insert(ignore_permissions=True)
    gp_c.submit()
    check("still in date, so Material Out", _status(gp_c.name), "Material Out")

    # Time passes. Nothing re-saves the document -- exactly the real situation.
    frappe.db.set_value("Delivery Challan", gp_c.name, "expected_return_date",
                        add_days(nowdate(), -1), update_modified=False)
    check("the sweep notices and flips it", refresh_overdue_gate_passes(), 1)
    check("stale gate pass is now Overdue", _status(gp_c.name), "Overdue")

    # A hook path is a string: a typo in it fails silently forever.
    hook = frappe.get_hooks("scheduler_events", app_name="manufyxinvenzaerp")
    daily = (hook or {}).get("daily") or []
    check("the daily scheduler hook is registered",
          any("refresh_overdue_gate_passes" in h for h in daily), True)
    for path in daily:
        check("the hook path resolves: %s" % path.rsplit(".", 1)[-1],
              callable(frappe.get_attr(path)), True)

    ret3 = make_return_entry(gp_b.name)
    ret3.insert(ignore_permissions=True)
    ret3.submit()
    check("a late but complete return clears Overdue", _status(gp_b.name), "Returned")

    print()
    print("=== 7. The guarantee: a gate pass moves no stock ===")
    check("no Stock Ledger Entry was written",
          frappe.db.count("Stock Ledger Entry"), sle_before)
    check("no Stock Entry was created", frappe.db.count("Stock Entry"), se_before)

    print()
    print("=== 8. It prints ===")
    html = _render_delivery_challan_html(frappe.get_doc("Delivery Challan", gp_a.name))
    check("print carries the GP number", gp_a.name in html, True)
    check("print carries the party", (gp_a.party_display_name or supplier) in html, True)
    check("print carries the material row", "ZZTEST plate 10mm" in html, True)
    check("print carries the DELIVERY CHALLAN title", "DELIVERY CHALLAN" in html, True)

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
    print("Test data left in place:", gp_a.name, gp_b.name, non_ret.name,
          ret1.name, ret3.name)
