"""An operation closes only when it is finished, cannot be cancelled alone, and the
Job Work Order's status follows the work.

Four faults reported together off the live server, all on the same chain:

  * SCO-SOE-0005 was cancelled and then could not be amended at all -- "amended_from
    field must be present to do an amendment". The doctype is submittable but never
    had that field, so Frappe refused every amendment. Worse, the cancel should not
    have been possible in the first place: the Job Work Order's Operations tab, the
    next operation's available quantity and the SCO Drawing Items all report from
    SUBMITTED operation entries, so a cancelled one leaves the order quoting a
    quantity nothing accounts for.

  * Nothing stopped Status being set to Completed on an unfinished operation. Since
    before_submit requires Completed, and submitting hands this operation's quantity
    to the next one, that passed forward work nobody had done.

  * The Job Work Order sat on "Open" for its whole life. ERPNext derives an SCO's
    status from per_received and Raw Materials Supplied; a Production-Plan-flow order
    has neither, so no status transition was ever reachable.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_operation_close_and_sco_status.run
"""

import re

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.subcontracting_management.overrides import (
    _any_operation_started,
    _final_stock_entry_submitted,
    refresh_sco_status,
)

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, fragment):
    """True when fn() raises a message containing fragment."""
    try:
        fn()
    except Exception as e:
        return fragment.lower() in str(e).lower()
    return False


def run():
    print("=== an operation entry can be amended at all ===")
    meta = frappe.get_meta("Supplier Operation Entry")
    check("the doctype has an amended_from field", bool(meta.get_field("amended_from")), True)
    check("and it is submittable", bool(meta.is_submittable), True)

    cancelled = frappe.db.get_value("Supplier Operation Entry", {"docstatus": 2}, "name")
    if not cancelled:
        print("    (no cancelled operation entry on this site to amend -- skipped)")
    else:
        src = frappe.get_doc("Supplier Operation Entry", cancelled)
        amended = frappe.copy_doc(src)
        amended.amended_from = src.name
        amended.docstatus = 0
        amended.insert(ignore_permissions=True)
        check("a cancelled one can be amended", bool(amended.name), True)
        # The cancelled document's Completed status copies across but its finished
        # quantities do not -- carried over unchanged, the amendment could not be
        # saved at all.
        check("and the amendment does not start out Completed",
              amended.status != "Completed", True)

    print()
    print("=== a submitted operation refuses to be cancelled on its own ===")
    submitted = frappe.db.get_value(
        "Supplier Operation Entry", {"docstatus": 1}, ["name", "subcontracting_order"], as_dict=True
    )
    if not submitted:
        print("    (no submitted operation entry on this site -- skipped)")
    else:
        doc = frappe.get_doc("Supplier Operation Entry", submitted.name)
        check("cancelling it directly is refused",
              _throws(doc.cancel, "cannot be cancelled on its own"), True)
        check("and it is still submitted afterwards",
              frappe.db.get_value("Supplier Operation Entry", submitted.name, "docstatus"), 1)

        # The Job Work Order's own cancel still has to work -- it takes the whole
        # chain with it, which is the supported way to undo one.
        doc2 = frappe.get_doc("Supplier Operation Entry", submitted.name)
        doc2.flags.mfx_cancelled_by_sco = True
        from manufyxinvenzaerp.subcontracting_management.subcontracting import (
            before_cancel_supplier_operation_entry,
        )
        check("but the Job Work Order's cascade is allowed through",
              before_cancel_supplier_operation_entry(doc2, "before_cancel"), None)

    print()
    print("=== Status cannot reach Completed on an unfinished operation ===")
    draft = frappe.db.get_value(
        "Supplier Operation Entry", {"docstatus": 0}, "name", order_by="sequence_id desc"
    )
    if not draft:
        print("    (no draft operation entry on this site -- skipped)")
    else:
        d = frappe.get_doc("Supplier Operation Entry", draft)
        rows = [r for r in (d.drawing_details or []) if flt(r.qty_to_manufacture) > 0]
        outstanding = []
        for r in rows:
            target = (
                flt(r.available_to_consume_nos) if (d.sequence_id or 1) > 1
                else flt(r.qty_to_manufacture)
            )
            # target 0 counts too: the previous operation passed nothing across,
            # so there is nothing here that could have been finished.
            if target <= 0 or flt(r.completed_qty_nos) + 0.001 < target:
                outstanding.append(r)
        print("    %s: %d drawing(s), %d still outstanding" % (draft, len(rows), len(outstanding)))
        if not outstanding:
            print("    (this one is already finished -- cannot exercise the block)")
        else:
            d.status = "Completed"
            check("setting Completed is refused",
                  _throws(d.save, "cannot be set to <b>completed</b>"), True)

    print()
    print("=== the Job Work Order's status follows its operations ===")
    check("Working is a valid Status option",
          "Working" in (frappe.get_meta("Subcontracting Order").get_field("status").options or "").split("\n"),
          True)

    for sco in frappe.get_all(
        "Subcontracting Order",
        filters={"docstatus": 1, "custom_production_plan": ["!=", ""]},
        fields=["name", "status", "custom_all_ops_complete"],
        order_by="creation",
    ):
        started = _any_operation_started(sco.name)
        final_se = _final_stock_entry_submitted(sco.name)
        expected = (
            "Completed" if (sco.custom_all_ops_complete and final_se)
            else ("Working" if started else "Open")
        )
        refresh_sco_status(sco.name)
        got = frappe.db.get_value("Subcontracting Order", sco.name, "status")
        print("    %s: ops_started=%s all_ops=%s final_se=%s" % (
            sco.name, started, bool(sco.custom_all_ops_complete), final_se))
        check("  %s reaches %s" % (sco.name, expected), got, expected)

    print()
    print("=== the buttons ===")
    sco_js = frappe.db.get_value("Client Script", "Subcontracting Order-soe-buttons", "script") or ""
    check("Subcontracting Receipt is removed from Create",
          bool(re.search(r'remove_custom_button\(__\("Subcontracting Receipt"\)', sco_js)), True)
    check("the Job Work Order offers Open MIP",
          bool(re.search(r'add_custom_button\(__\("Open MIP"\)', sco_js)), True)

    mip_js_path = frappe.get_app_path(
        "manufyxinvenzaerp", "subcontracting_management", "doctype",
        "material_issue_plan", "material_issue_plan.js",
    )
    mip_js = open(mip_js_path).read()
    check("the Material Issue Plan offers Open Job Work Order",
          bool(re.search(r'add_custom_button\(__\("Open Job Work Order"\)', mip_js)), True)

    soe_js = frappe.db.get_value(
        "Client Script", "Supplier Operation Entry-consumption-logic", "script"
    ) or ""
    # Matched on the call, not on one exact spelling of it. This read
    # 'save("Submit")' with the closing bracket, which stopped being true the moment
    # c0582e3 gave the call its callbacks -- save("Submit", function() {...}, ...) --
    # and the check then passed only on sites whose installed Client Script predated
    # that commit. It went green on stale data and red on current code, which is
    # exactly backwards.
    check("setting Completed asks before submitting",
          bool(re.search(r"frappe\.confirm", soe_js))
          and bool(re.search(r'save\(\s*"Submit"', soe_js)), True)
    # What c0582e3 actually added: the operation is validated server-side BEFORE the
    # question is put, so a confirmation is never offered for a submit that would fail.
    check("  and validates the operation before asking",
          "check_soe_completion_before_confirm" in soe_js
          and soe_js.index("check_soe_completion_before_confirm")
              < soe_js.index("frappe.confirm"), True)

    print()
    print("=== The order's status is not set by hand ===")
    sco_js = frappe.db.get_value(
        "Client Script", "Subcontracting Order-soe-buttons", "script") or ""
    # ERPNext's Status group offers Close / Re-open. On a PP-flow order the status is
    # derived (update_status in overrides.py, re-run from the SOE hooks and from Stock
    # Entry submit/cancel), so a hand-set value is overwritten by the next recompute
    # without telling anybody. The standard controller adds whichever label fits the
    # current status, so both have to go; an empty group is then dropped by Frappe.
    for label in ("Close", "Re-open"):
        check('  the "%s" button is removed from the Status group' % label,
              'remove_custom_button(__("%s"), __("Status"))' % label in sco_js, True)

    # Create -> Material Issue Plan is gone; Open MIP covers it, and the plan is made
    # with the order. Checked on the CODE, not the source text -- the button is kept
    # commented out so it can be restored, so a plain search still finds its name.
    sco_code = "\n".join(line.split("//")[0] for line in sco_js.splitlines())
    check("  Create no longer offers Material Issue Plan",
          'add_custom_button(__("Material Issue Plan")' not in sco_code, True)
    check("  but Open MIP still navigates to it",
          '__("Open MIP")' in sco_code, True)
    check("  and Supplier Operation Entries is untouched",
          '__("Supplier Operation Entries")' in sco_code, True)

    frappe.db.rollback()
    print()
    print("  (rolled back -- this check leaves no trace)")
    _summary()


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
