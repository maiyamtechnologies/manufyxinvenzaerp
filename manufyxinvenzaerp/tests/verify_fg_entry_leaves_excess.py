"""The Final Stock Entry leaves behind what the plan booked to return.

MIP-2026-00007: the transfer sent more than the drawings called for and the popup's
consolidated excess tab booked the off-cut to come back (PLATE8 666.308 Kg, PLATE25
130.467 Kg, FLAT 30.222 Kg). The Manufacture entry (MAT-STE-00014) then consumed every
kilo at the supplier, off-cut included, so Return Excess Entry had nothing left to move:

    "There is not enough of this material left at Work in Progress ... to return:
     PLATE8: 666.308 Kg short ... It has already been consumed by the final Stock Entry"

An Excess Material Items row that has not yet become a Stock Entry, and is not claimed by
another plan, now holds its Kg back from consumption
(_excess_booked_to_return / _consumption_for_completed).

Runs the real _consumption_for_completed with the plan's rows stood in as data; nothing
is read or written on the site beyond the Material Issue Plan that lends its name.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_entry_leaves_excess.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-70s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _run_consumption(rows, available, booked, finished=1.0):
    """_consumption_for_completed with the plan's rows, the supplier's stock and the
    booked excess supplied as data."""
    from manufyxinvenzaerp.subcontracting_management import subcontracting as sc

    sco = frappe._dict(name="ZZ-NO-SUCH-SCO")
    preview = {"drawings": [{"duno_mark_no": "TYPE 1", "qty_to_manufacture": 1,
                             "completed_qty_nos": finished}]}
    saved = (frappe.db.get_value, frappe.get_all, sc._rm_already_consumed, sc._excess_booked_to_return)

    def fake_get_value(doctype, filters=None, fieldname=None, *a, **k):
        if doctype == "Material Issue Plan":
            return "ZZ-NO-SUCH-MIP"
        return saved[0](doctype, filters, fieldname, *a, **k)

    def fake_get_all(doctype, **k):
        if doctype == "Material Issue Plan Raw Material":
            return [frappe._dict(r) for r in rows]
        return saved[1](doctype, **k)

    frappe.db.get_value = fake_get_value
    frappe.get_all = fake_get_all
    sc._rm_already_consumed = lambda *a, **k: {}
    sc._excess_booked_to_return = lambda mip: dict(booked)
    try:
        out = sc._consumption_for_completed(sco, "WIP", preview, available)
    finally:
        frappe.db.get_value, frappe.get_all, sc._rm_already_consumed, sc._excess_booked_to_return = saved
    return {(r["item_code"], r.get("batch_no") or ""): flt(r["qty"], 3) for r in out}


def _mip_00007_shape():
    """PLATE8 as MIP-2026-00007 had it: 3,931.705 Kg sent and planned on the rows, with
    666.201 Kg of it booked to come back."""
    rows = [{"item_code": "PLATE8", "planned_item": "PLATE8", "batch_no": "B1",
             "duno_mark_no": "TYPE 1", "transferred_qty": 3931.705,
             "drawing_planned_weight": 3931.705, "reqd_kg": 3931.705}]
    available = [{"item_code": "PLATE8", "batch_no": "B1", "qty": 3931.705, "s_warehouse": "WIP"}]
    return rows, available


def run():
    print("=== verify_fg_entry_leaves_excess ===")

    rows, available = _mip_00007_shape()

    print("\n=== MIP-2026-00007: 3,931.705 Kg at the supplier, 666.201 booked to return ===")
    got = _run_consumption(rows, available, {"PLATE8": 666.201})
    check("the entry consumes the rest and leaves the off-cut",
          got, {("PLATE8", "B1"): flt(3931.705 - 666.201, 3)})
    check("what is left equals the booked return",
          flt(3931.705 - got[("PLATE8", "B1")], 3), 666.201)

    print("\n=== nothing booked: unchanged behaviour ===")
    got = _run_consumption(rows, available, {})
    check("everything the drawings planned is consumed", got, {("PLATE8", "B1"): 3931.705})

    print("\n=== a booked row already turned into a Stock Entry holds nothing back ===")
    # _excess_booked_to_return filters those out; an empty dict is what it returns.
    got = _run_consumption(rows, available, {})
    check("consumption is untouched", got, {("PLATE8", "B1"): 3931.705})

    print("\n=== the plan already leaves a gap: the booked Kg comes out of that first ===")
    # 3,000 Kg planned on the drawings of 3,931.705 sent: 931.705 is already staying.
    rows2 = [dict(rows[0], drawing_planned_weight=3000.0, reqd_kg=3000.0)]
    got = _run_consumption(rows2, available, {"PLATE8": 666.201})
    check("consumption is not cut twice", got, {("PLATE8", "B1"): 3000.0})

    print("\n=== booked more than one batch holds: the rest comes off the next batch ===")
    rows3 = [dict(rows[0], batch_no="B1", transferred_qty=100.0, drawing_planned_weight=100.0, reqd_kg=100.0),
             dict(rows[0], batch_no="B2", transferred_qty=100.0, drawing_planned_weight=100.0, reqd_kg=100.0)]
    available3 = [{"item_code": "PLATE8", "batch_no": "B1", "qty": 100.0, "s_warehouse": "WIP"},
                  {"item_code": "PLATE8", "batch_no": "B2", "qty": 100.0, "s_warehouse": "WIP"}]
    got = _run_consumption(rows3, available3, {"PLATE8": 150.0})
    check("150 Kg held back across two batches of 100",
          flt(200.0 - sum(got.values()), 3), 150.0)

    print("\n=== half the drawing finished: its share, less the booked return ===")
    got = _run_consumption(rows, available, {"PLATE8": 666.201}, finished=0.5)
    check("half of 3,931.705 is 1,965.853, and the off-cut still stays",
          got, {("PLATE8", "B1"): flt(3931.705 * 0.5, 3)})

    print()
    failed = checks.count(False)
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, len(checks)))
    else:
        print("ALL %d CHECKS PASSED" % len(checks))
