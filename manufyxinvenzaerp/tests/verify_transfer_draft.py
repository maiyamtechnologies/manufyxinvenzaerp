"""T6b — "Save and Close": park the transfer popup's state without transferring.

The point is to step away mid-decision: a Sec Nos half adjusted, an off-cut not yet
measured, a warehouse not yet chosen. So saving is deliberately unvalidated -- checking
stock or dimensions would refuse to save exactly the unfinished state being kept. It is
all re-checked server-side when Transfer is finally pressed.

The draft lives on the Consolidate Items rows, which are otherwise fully derived and
rebuilt wholesale on every save of the plan. Surviving that rebuild is the whole
contract: without it, "Save and Close" would quietly discard the work the moment
anything re-saved the plan.

This test writes real rows and commits, so it must leave the row it borrows exactly
as it found it. It used to take the first consolidate row on the site and finish by
clearing its draft -- which, on live data, destroyed a genuine "Save and Close" a user
had parked (MIP-2026-00005 / PLATE10 lost one on 11 Sep 2026 and again on 14 Sep). It
now prefers a row with no draft, snapshots the draft fields of EVERY consolidated row on
that plan, and puts them all back at the end whatever happens -- the whole-popup clear
exercised below reaches the borrowed row's siblings too.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_transfer_draft.run
"""

import inspect
import json

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        save_transfer_draft, get_transfer_draft, _clear_transfer_draft,
    )

    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        _CONSOLIDATE_DRAFT_FIELDS,
    )

    # Prefer a row nobody has parked anything on, so a failure part-way through cannot
    # cost a user their work even before the restore below runs.
    pick = frappe.db.get_value(
        "Material Issue Plan Consolidate Item",
        {"batch_no": ["!=", ""], "draft_saved_on": ["is", "not set"]},
        ["parent", "name"], as_dict=True,
    ) or frappe.db.get_value(
        "Material Issue Plan Consolidate Item", {"batch_no": ["!=", ""]},
        ["parent", "name"], as_dict=True,
    )
    if not pick:
        print("no Material Issue Plan with consolidated rows on this site -- skipped")
        return

    mip_name = pick.parent
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    row = next(r for r in mip.consolidate_items if r.name == pick.name)
    key = "%s|%s|%s" % (row.item_code, row.batch_no or "", 1 if row.cnc_process else 0)
    print("plan %s, row %s / %s" % (mip_name, row.item_code, row.batch_no))

    snapshot = _snapshot_drafts(mip_name, _CONSOLIDATE_DRAFT_FIELDS)
    try:
        _exercise(mip_name, mip, row, key, save_transfer_draft, get_transfer_draft, _clear_transfer_draft)
    finally:
        _restore_drafts(mip_name, snapshot)

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))


def _snapshot_drafts(mip_name, draft_fields):
    """Every consolidated row's draft on this plan, keyed by item+batch+leg.

    The whole plan, not just the row being borrowed: clearing a popup's draft now
    reaches every row of that popup, so a genuine "Save and Close" parked on a
    neighbouring row is within this test's reach and has to be put back too.
    """
    rows = frappe.get_all(
        "Material Issue Plan Consolidate Item", filters={"parent": mip_name},
        fields=["item_code", "batch_no", "cnc_process"] + list(draft_fields),
    )
    return {
        (r.item_code, r.batch_no or "", 1 if r.cnc_process else 0):
            {f: r.get(f) for f in draft_fields}
        for r in rows
    }


def _restore_drafts(mip_name, snapshot):
    """Put every draft back exactly -- including its original save time.

    The plan's saves above rebuild the consolidate table and rename every row, so rows
    are found again by their key rather than by name.
    """
    held = 0
    for (item_code, batch_no, cnc), original in snapshot.items():
        for name in frappe.get_all(
            "Material Issue Plan Consolidate Item",
            filters={"parent": mip_name, "item_code": item_code,
                     "batch_no": batch_no, "cnc_process": cnc},
            pluck="name",
        ):
            frappe.db.set_value("Material Issue Plan Consolidate Item", name, original,
                                update_modified=False)
        if original.get("draft_saved_on"):
            held += 1
    frappe.db.commit()
    print()
    print("  (restored %d row(s) on %s, %d of which held a real draft)"
          % (len(snapshot), mip_name, held))


def _exercise(mip_name, mip, row, key, save_transfer_draft, get_transfer_draft, _clear_transfer_draft):

    print()
    print("=== saving parks the state, unvalidated ===")
    # Deliberately more Sec Nos than could possibly be in stock: an unfinished draft
    # must save regardless, since validating here would refuse the very state being kept.
    draft = [{
        "item_code": row.item_code, "batch_no": row.batch_no,
        "cnc_process": 1 if row.cnc_process else 0,
        "custom_sec_qty": 9999,
    }]
    # The off-cut is stated once per ITEM now, on the popup's consolidated tab,
    # rather than once per batch row -- the same off-cut comes back whichever
    # batches it was drawn from. It is parked against every batch row of that item
    # so reopening finds it whichever row it reads first.
    excess_plan = {row.item_code: {"length": 640, "width": 12, "sec_qty": 1.25,
                                   "return_warehouse": mip.source_warehouse or ""}}
    res = save_transfer_draft(mip_name, json.dumps(draft), json.dumps(excess_plan))
    check("one row saved", res.get("saved"), 1)

    got = get_transfer_draft(mip_name).get(key) or {}
    check("Sec Nos parked as typed, however implausible", flt(got.get("draft_sec_qty")), 9999.0)
    check("excess length parked", flt(got.get("draft_excess_length")), 640.0)
    check("excess width parked", flt(got.get("draft_excess_width")), 12.0)
    check("excess Sec Nos parked", flt(got.get("draft_excess_sec_qty")), 1.25)
    check("return warehouse parked", got.get("draft_return_warehouse"), mip.source_warehouse or "")
    check("stamped with a save time", bool(got.get("draft_saved_on")), True)

    print()
    print("=== it survives a re-save of the plan, which rebuilds the whole table ===")
    mip.reload()
    mip.save(ignore_permissions=True)
    frappe.db.commit()
    after = get_transfer_draft(mip_name).get(key) or {}
    check("still present after rebuild", bool(after), True)
    check("Sec Nos intact", flt(after.get("draft_sec_qty")), 9999.0)
    check("excess intact", flt(after.get("draft_excess_length")), 640.0)
    check("warehouse intact", after.get("draft_return_warehouse"), mip.source_warehouse or "")

    print()
    print("=== a row that no longer exists is skipped, not invented ===")
    ghost = [{"item_code": "ZZ-NOT-A-REAL-ITEM", "batch_no": "ZZ-NOT-A-REAL-BATCH",
              "cnc_process": 0, "custom_sec_qty": 5}]
    check("nothing saved for it", save_transfer_draft(mip_name, json.dumps(ghost)).get("saved"), 0)

    print()
    print("=== transferring clears it ===")
    _clear_transfer_draft(mip_name, [{
        "item_code": row.item_code, "batch_no": row.batch_no,
        "cnc_process": 1 if row.cnc_process else 0,
    }])
    frappe.db.commit()
    check("draft gone for that row", key in get_transfer_draft(mip_name), False)

    print()
    print("=== and clearing survives the next rebuild too ===")
    mip.reload()
    mip.save(ignore_permissions=True)
    frappe.db.commit()
    check("still gone", key in get_transfer_draft(mip_name), False)

    print()
    print("=== a draft belongs to the popup it was typed in ===")
    # All three popups park against these same rows, and the CNC-to-supplier popup
    # keys its lines exactly as the RM-to-supplier one does (cnc_process is 0 in
    # both). So a "1 whole plate" parked against the stock sitting in stores was
    # restored into the CNC popup, which is looking at the far smaller amount that
    # has actually reached the CNC warehouse -- and it opened refusing to transfer,
    # "Not Enough Stock", on a plan nobody had touched.
    one_row = [{"item_code": row.item_code, "batch_no": row.batch_no,
                "cnc_process": 1 if row.cnc_process else 0, "custom_sec_qty": 7}]
    save_transfer_draft(mip_name, json.dumps(one_row), None, "cnc_forward")
    frappe.db.commit()
    check("the popup that saved it gets it back",
          flt((get_transfer_draft(mip_name, "cnc_forward").get(key) or {}).get("draft_sec_qty")), 7.0)
    check("the RM-to-supplier popup does not see it",
          key in get_transfer_draft(mip_name, "primary"), False)
    check("nor does the to-CNC popup", key in get_transfer_draft(mip_name, "cnc"), False)
    check("and asking without a type means the RM-to-supplier popup",
          key in get_transfer_draft(mip_name), False)

    print()
    print("=== and one popup's transfer does not clear another's draft ===")
    cleared = [{"item_code": row.item_code, "batch_no": row.batch_no,
                "cnc_process": 1 if row.cnc_process else 0}]
    _clear_transfer_draft(mip_name, cleared, "primary")
    frappe.db.commit()
    check("the cnc_forward draft survives a primary transfer",
          flt((get_transfer_draft(mip_name, "cnc_forward").get(key) or {}).get("draft_sec_qty")), 7.0)
    _clear_transfer_draft(mip_name, cleared, "cnc_forward")
    frappe.db.commit()
    check("its own transfer does clear it",
          key in get_transfer_draft(mip_name, "cnc_forward"), False)

    print()
    print("=== a transfer clears the WHOLE popup, not only the rows it sent ===")
    # Every transfer route passes items=None. Clearing only the rows actually sent left
    # two wrong things behind. The off-cut is stated once per ITEM and parked on every
    # batch row of that item, so sending one batch of a two-batch item left the other
    # row still holding an off-cut already booked into excess_return_items -- pressing
    # Transfer again would book it a second time. And a Sec Nos parked against a row
    # that was deselected describes a transfer nobody made, yet came back on the next
    # open looking current. After a transfer the popup opens empty.
    siblings = [
        r for r in frappe.get_all(
            "Material Issue Plan Consolidate Item",
            filters={"parent": mip_name, "batch_no": ["!=", ""]},
            fields=["item_code", "batch_no", "cnc_process"])
        if "%s|%s|%s" % (r.item_code, r.batch_no or "", 1 if r.cnc_process else 0) != key
    ]
    if not siblings:
        print("  SKIP this plan has only one consolidated row with a batch")
    else:
        sib = siblings[0]
        skey = "%s|%s|%s" % (sib.item_code, sib.batch_no or "", 1 if sib.cnc_process else 0)
        both = [{"item_code": row.item_code, "batch_no": row.batch_no,
                 "cnc_process": 1 if row.cnc_process else 0, "custom_sec_qty": 3},
                {"item_code": sib.item_code, "batch_no": sib.batch_no,
                 "cnc_process": 1 if sib.cnc_process else 0, "custom_sec_qty": 4}]
        check("both rows parked", save_transfer_draft(mip_name, json.dumps(both), None, "cnc").get("saved"), 2)
        frappe.db.commit()
        # A transfer that sent ONLY the borrowed row.
        _clear_transfer_draft(mip_name, None, "cnc")
        frappe.db.commit()
        after = get_transfer_draft(mip_name, "cnc")
        check("the row that was sent is clear", key in after, False)
        check("and so is the row that was not", skey in after, False)

        print()
        print("=== ...but still only its own popup ===")
        save_transfer_draft(mip_name, json.dumps(both[:1]), None, "cnc")
        save_transfer_draft(mip_name, json.dumps(both[1:]), None, "cnc_forward")
        frappe.db.commit()
        _clear_transfer_draft(mip_name, None, "cnc")
        frappe.db.commit()
        check("the to-CNC draft went", key in get_transfer_draft(mip_name, "cnc"), False)
        check("the CNC-to-supplier draft stayed",
              flt((get_transfer_draft(mip_name, "cnc_forward").get(skey) or {}).get("draft_sec_qty")), 4.0)
        _clear_transfer_draft(mip_name, None, "cnc_forward")
        frappe.db.commit()

    print()
    print("=== every transfer route actually calls it ===")
    # The popup's "Verify and Transfer" runs create_mip_partial_transfer, NOT
    # create_mip_transfer_entry -- which is why the parked state outlived every
    # transfer ever made from the dialog until this call was added.
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as mipt
    for fn, ttype in ((mipt.create_mip_partial_transfer, 'transfer_type or "primary"'),
                      (mipt.create_mip_transfer_entry, '"primary"'),
                      (mipt.create_mip_cnc_partial_forward, '"cnc_forward"')):
        src = inspect.getsource(fn)
        check("%s clears its popup" % fn.__name__,
              "_clear_transfer_draft(mip.name, None, %s)" % ttype in src, True)
