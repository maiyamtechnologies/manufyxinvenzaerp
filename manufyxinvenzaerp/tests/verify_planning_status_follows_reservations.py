"""A Material Planning's status is what its reservations say it is -- both ways.

It used to be a one-way ratchet. _auto_update_planning_status opened with

    if self.planning_status == "Batch Mapping Completed":
        return

so a plan marked complete stayed complete after somebody unreserved a row.
MP-2026-00010 on the live site reads "Batch Mapping Completed" with not one of its six
rows reserved -- and a Material Issue Plan only ever offers reserved rows for transfer.
The plan says it is ready and would move nothing.

The status is now recomputed on every save and can fall as well as rise:

    Open                     nothing mapped and nothing outstanding
    Working                  something is mapped, but not all of it is reserved
    Batch Mapping Completed  every mapped row is reserved, and nothing is still
                             sitting in Unavailable Items

An Unavailable Item counts against completion because it cannot be reserved at all.

Setting it by hand is gone with it: two writers, one of them a button pressed once, is
how a stale "Completed" survives in the first place. complete_batch_mapping still runs
the deeper checks -- cross-table duplicates, over-allocation across plans, Nos against
batch stock -- but sets nothing, and sits behind a button that now says Check Mapping.

Everything here runs inside a transaction and is rolled back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_planning_status_follows_reservations.run
"""

import inspect

import frappe

from manufyxinvenzaerp.production_management.doctype.material_planning import (
    material_planning as mp_module,
)

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-54s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _status(name):
    return frappe.db.get_value("Material Planning", name, "planning_status")


def _save(doc):
    # The plan is being saved by a test, not edited by a person -- the same flag the
    # Purchase Receipt sets when it saves a plan as a side effect.
    doc.flags.mfx_saved_by_another_document = True
    doc.save(ignore_permissions=True)


def run():
    print("=== the ratchet is gone ===")
    src = inspect.getsource(mp_module.MaterialPlanning._auto_update_planning_status)
    check("it no longer returns early when already complete",
          'if self.planning_status == "Batch Mapping Completed":\n            return' in src, False)
    # Since 2026-09-28 a row sent IN FULL counts as settled too (it has nothing left to
    # hold); a row sent in part still needs the rest reserved (_row_still_to_send).
    check("an unreserved row keeps it Working",
          "not all(_is_row_done(r) for r in rows)" in src
          and "bool(r.is_reserved) or not _row_still_to_send(r)" in src, True)
    check("and an outstanding Unavailable Item does too", "outstanding or not all(" in src, True)

    print()
    print("=== nothing sets it by hand any more ===")
    complete_src = inspect.getsource(mp_module.complete_batch_mapping)
    check("the check writes no status",
          'set_value("Material Planning", mp_name, "planning_status"' in complete_src, False)
    check("it still reports the deeper issues",
          "_collect_batch_mapping_issues(mp)" in complete_src, True)
    js = open(frappe.get_app_path("manufyxinvenzaerp", "production_management", "doctype",
                                  "material_planning", "material_planning.js")).read()
    check("the button says what it does now",
          'add_custom_button(__("Check Mapping")' in js, True)
    check("Reopen Mapping is gone", 'add_custom_button(__("Reopen Mapping")' in js, False)
    check("and so is the button that set it",
          'add_custom_button(__("Batch Mapping Completed")' in js, False)
    check("the field itself is read-only",
          frappe.get_meta("Material Planning").get_field("planning_status").read_only, 1)

    name = frappe.db.get_value("Material Planning", {"docstatus": 0}, "name")
    if not name:
        print()
        print("   No draft Material Planning on this site to move.")
        _summary()
        return

    print()
    print("=== against %s ===" % name)
    doc = frappe.get_doc("Material Planning", name)
    rows = [r for r in (doc.material_mapping or []) if r.item_code]
    rows += [r for r in (doc.available_raw_materials or []) if r.item_code]
    if not rows:
        print("   It has no mapped rows to reserve.")
        _summary()
        return
    print("   %d mapped row(s), %d reserved, status %s"
          % (len(rows), sum(1 for r in rows if r.is_reserved), doc.planning_status))

    try:
        for r in rows:
            r.is_reserved = 1
        _save(doc)
        check("every row reserved reads complete", _status(name), "Batch Mapping Completed")

        # A row that still has material to send -- one sent in full is settled whether
        # or not it is reserved, so unreserving it proves nothing.
        doc = frappe.get_doc("Material Planning", name)
        pending = [r for r in list(doc.material_mapping) + list(doc.available_raw_materials)
                   if r.item_code and mp_module._row_still_to_send(r)]
        if pending:
            pending[0].is_reserved = 0
            _save(doc)
            check("unreserve one and it falls back", _status(name), "Working")
        else:
            print("   (every row of %s is sent in full -- unreserve check not exercised)" % name)

        doc = frappe.get_doc("Material Planning", name)
        for r in doc.material_mapping:
            r.is_reserved = 1
        for r in doc.available_raw_materials:
            r.is_reserved = 1
        _save(doc)
        check("reserve it again and it rises", _status(name), "Batch Mapping Completed")

        # An Unavailable Item is material with no batch behind it -- it cannot be
        # reserved at all, so a plan holding one is not complete however well the rest
        # is mapped.
        doc = frappe.get_doc("Material Planning", name)
        sample = doc.material_mapping[0]
        doc.append("unavailable_items", {
            "item_code": sample.item_code, "item_name": sample.item_name,
            "qty": 1, "uom": sample.uom or "Kg",
        })
        _save(doc)
        check("an outstanding Unavailable Item holds it at Working", _status(name), "Working")
    finally:
        frappe.db.rollback()

    _summary()


def _summary():
    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
