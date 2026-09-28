"""A row sent in part is not settled until the rest is reserved; the Op-1 tolerance is
real on a site that never saved it.

WHY (both from the 2026-09-27 fixes for MP-2026-00017 / SCO-SOE-0027):

1. The status rule counted ANY transferred amount as done. A row that sent 40 of 100 Kg
   with the other 60 unreserved read "Batch Mapping Completed", and Check Mapping --
   which skipped every row that had shipped at all -- said nothing. That is exactly the
   state MP-2026-00017 was in before its balance could be sent. _row_still_to_send now
   decides both.

2. "Weight Difference Tolerance (Kg)" was added with a default of 0.05, but a Single field
   nobody has saved reads 0.0, not blank -- so on live the tolerance was zero and the 2 g
   rounding difference on SCO-SOE-0027 stayed blocked. set_fg_settings_defaults now
   writes it on migrate.

In memory and inside a rolled-back transaction, with commits stubbed.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_partial_transfer_settling.run
"""

import inspect

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    print("=== verify_partial_transfer_settling ===")
    real_commit = frappe.db.commit
    frappe.db.commit = lambda *a, **k: None
    try:
        _status()
        _check_mapping()
        _tolerance()
    finally:
        frappe.db.commit = real_commit
        frappe.db.rollback()
    print()
    failed = checks.count(False)
    print(("%d of %d CHECKS FAILED" % (failed, len(checks))) if failed else "ALL %d CHECKS PASSED" % len(checks))


def _mp(**row):
    mp = frappe.new_doc("Material Planning")
    mp.for_warehouse = "Stores - MIPL"
    base = {"item_code": "ISA100", "qty": 100, "batch": "ZZ-NO-SUCH-BATCH", "is_reserved": 0,
            "reserved_qty": 0, "transferred_qty": 0, "fully_transferred": 0}
    base.update(row)
    mp.append("material_mapping", base)
    return mp


def _status_of(**row):
    mp = _mp(**row)
    mp._auto_update_planning_status()
    return mp.planning_status


def _status():
    print("=== the plan's status ===")
    check("nothing sent, reserved: complete", _status_of(is_reserved=1, reserved_qty=100),
          "Batch Mapping Completed")
    check("nothing sent, not reserved: Working", _status_of(), "Working")
    check("40 of 100 sent, rest NOT reserved: Working", _status_of(transferred_qty=40), "Working")
    check("40 of 100 sent, rest reserved: complete",
          _status_of(transferred_qty=40, is_reserved=1, reserved_qty=60), "Batch Mapping Completed")
    check("all 100 sent (released): complete", _status_of(transferred_qty=100, fully_transferred=1),
          "Batch Mapping Completed")
    check("99.9995 of 100 sent: within a gram, complete", _status_of(transferred_qty=99.9995),
          "Batch Mapping Completed")

    mp = frappe.new_doc("Material Planning")
    mp.append("available_raw_materials", {"item_code": "ISA100", "required_qty": 50, "batch_no": "X",
                                          "is_reserved": 0, "transferred_qty": 20})
    mp._auto_update_planning_status()
    check("Exact Match measured on Required Qty: 20 of 50 sent, not reserved", mp.planning_status, "Working")


def _check_mapping():
    print()
    print("=== Check Mapping ===")
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        _collect_batch_mapping_issues,
    )
    part = [i for i in _collect_batch_mapping_issues(_mp(transferred_qty=40))
            if "not reserved" in i]
    check("a part-sent row with the rest unreserved is reported", len(part), 1)
    check("...saying how much is sent and how much to reserve",
          bool(part) and "40.0 of 100.0 Kg already sent; 60.0 Kg still to reserve" in part[0], True)
    full = [i for i in _collect_batch_mapping_issues(_mp(transferred_qty=100, fully_transferred=1))
            if "not reserved" in i]
    check("a row sent in full is not (MP-2026-00260's 32 false issues)", full, [])


def _tolerance():
    print()
    print("=== Weight Difference Tolerance ===")
    from manufyxinvenzaerp import setup
    from manufyxinvenzaerp.subcontracting_management import subcontracting

    frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype='Manufyxinvenza Settings' "
                  "AND field='weight_difference_tolerance'")  # rolled back
    frappe.clear_cache(doctype="Manufyxinvenza Settings")
    check("a site that never saved it reads 0.0 (strict)",
          frappe.db.get_single_value("Manufyxinvenza Settings", "weight_difference_tolerance"), 0.0)
    setup.set_fg_settings_defaults()
    frappe.clear_cache(doctype="Manufyxinvenza Settings")
    check("migrate writes the 0.05 Kg default",
          frappe.db.get_single_value("Manufyxinvenza Settings", "weight_difference_tolerance"), 0.05)

    frappe.db.set_single_value("Manufyxinvenza Settings", "weight_difference_tolerance", 0.2)
    setup.set_fg_settings_defaults()
    frappe.clear_cache(doctype="Manufyxinvenza Settings")
    check("a value somebody set is left alone",
          frappe.db.get_single_value("Manufyxinvenza Settings", "weight_difference_tolerance"), 0.2)

    src = inspect.getsource(subcontracting.validate_supplier_operation_entry)
    check("Op-1 blocks only beyond the tolerance", "if diff > tolerance:" in src, True)
    check("within it, a warning instead", '"Weight Difference Within Tolerance"' in src, True)

    # The popup only on the save that changed the log; every other save, status change
    # and submit gets the bottom-of-screen notification (2026-09-28).
    check("otherwise the bottom notification, not a popup",
          "frappe.msgprint(message, indicator=\"orange\", alert=True)" in src
          and "if _consumption_log_changed(doc):" in src, True)
    doc = frappe.new_doc("Supplier Operation Entry")
    doc.append("consumption_log", {"drawing": "D1", "qty_nos": 1, "weight_kg": 555.891})
    check("a new entry with a log counts as changed", subcontracting._consumption_log_changed(doc), True)
    doc.name, doc.flags.__islocal = "ZZ-SOE", False
    doc.set("__islocal", 0)
    doc._doc_before_save = frappe.copy_doc(doc)
    check("saved again unchanged: not changed", subcontracting._consumption_log_changed(doc), False)
    doc.append("consumption_log", {"drawing": "D2", "qty_nos": 1, "weight_kg": 556.606})
    check("a row added: changed", subcontracting._consumption_log_changed(doc), True)
