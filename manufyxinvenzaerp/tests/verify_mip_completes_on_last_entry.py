"""A plan closes when its last entry is SUBMITTED, whichever entry that turns out to be.

MIP-2026-00003 finished its job and stayed Open. Every kilo was accounted for --
3975.154 transferred, 1592.976 used in finished goods, 2074.642 returned, 307.536
written off -- the FG dialog said "Nothing to Book", and the status still read Open
with no way to move it.

Three things, one shape: the plan is only judged at the moment it is saved, and the
saves were in the wrong places.

  * create_mip_process_loss_entry INSERTS its write-off as a draft and then saves the
    plan in the same call. The completion gate reads the stock ledger, and the ledger
    counts submitted entries only -- so the plan was judged against a ledger its own
    write-off was invisible to, and saw exactly the 307.536 Kg that was about to be
    written off. Stayed Open, correctly, on the information it had.

  * The submit fourteen seconds later cleared the supplier warehouse and told nobody.
    on_submit_stock_entry re-checked the plan for Send to Subcontractor, Material
    Transfer and Manufacture -- but the last two steps of the chain are Material Issue
    (process loss) and Repack (excess return), and both fell through every branch. A
    plan finishing on either one had no event left that could ever close it.

  * The final Manufacture entry carried no custom_mip_ref, which is what the plan's
    Connections panel keys on -- so the one entry that finishes the job was the only
    one missing from the panel. The dashboard's own docstring claimed it was there.

Tagging that entry then made a fourth thing visible: the Inventory Report counted
"Issued" as every custom_mip_ref entry EXCEPT Material Receipt. That blacklist was
written when the excess return WAS a Material Receipt; it became a Repack, and process
loss arrived as a Material Issue, so both were already being counted as issued and the
figure was overstated by the return plus the write-off.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_mip_completes_on_last_entry.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _src(*parts):
    return open(frappe.get_app_path("manufyxinvenzaerp", *parts)).read()


def run():
    print("\n1. The re-check fires for ANY entry the plan raised, not a chosen few")
    se_src = _src("production_management", "stock_entry.py")
    submit_body = se_src.split("def on_submit_stock_entry")[1].split("\ndef ")[0]
    check("on_submit re-checks completion", "recheck_mip_completion(" in submit_body, True)
    check("gated on custom_mip_ref, not entry type",
          'if doc.get("custom_mip_ref"):' in submit_body, True)
    # The bug was a type whitelist that the chain outgrew. If someone reintroduces
    # one here, the next step added to the chain goes missing the same way.
    recheck_tail = submit_body.split('if doc.get("custom_mip_ref"):')[1]
    check("re-check not re-narrowed by entry type",
          "stock_entry_type" in recheck_tail, False)
    check("a failed re-check cannot block the stock movement",
          "except Exception" in recheck_tail, True)

    print("\n2. The re-check only ever closes a plan, never reopens one")
    mip_src = _src("subcontracting_management", "doctype", "material_issue_plan",
                   "material_issue_plan.py")
    recheck_body = mip_src.split("def recheck_mip_completion")[1].split("\n@")[0]
    check("returns early when already Completed",
          'if mip.status == "Completed":' in recheck_body, True)
    check("only ever writes Completed",
          recheck_body.count('"Completed"'), 3)
    # on_cancel is deliberately left alone: _maybe_mark_completed never reverses,
    # so a cancel that puts material back at the supplier must not be answered here.
    cancel_body = se_src.split("def on_cancel_stock_entry")[1].split("\ndef ")[0]
    check("cancel does not re-check", "recheck_mip_completion(" in cancel_body, False)

    print("\n3. The final Manufacture entry is tagged with its plan")
    sub_src = _src("subcontracting_management", "subcontracting.py")
    fg_body = sub_src.split("def create_finished_goods_entry")[1].split("\ndef ")[0]
    check("new entry carries custom_mip_ref", '"custom_mip_ref": mip_ref' in fg_body, True)
    check("an existing draft is tagged too", "se.custom_mip_ref = mip_ref" in fg_body, True)
    # _update_sco_transferred_weight matches on custom_sco_ref ALONE. A Manufacture
    # entry has no business in that sum, and subcontracting_order already carries the
    # value for every query that pairs the two with OR.
    check("custom_sco_ref deliberately not set", '"custom_sco_ref"' in fg_body, False)

    print("\n4. Inventory Report names what it counts instead of excluding what it does not")
    inv_src = _src("production_management", "report", "inventory_report", "inventory_report.py")
    check("Issued restricted to the two transfer types",
          "IN ('Send to Subcontractor', 'Material Transfer')" in inv_src, True)
    check("the outgrown blacklist is gone",
          "stock_entry_type != 'Material Receipt'" in inv_src, False)

    print("\n5. The plan the bug was found on")
    mip_name = "MIP-2026-00003"
    if not frappe.db.exists("Material Issue Plan", mip_name):
        print("  SKIP %s not on this site" % mip_name)
    else:
        mip = frappe.get_doc("Material Issue Plan", mip_name)
        check("status", mip.status, "Completed")

        # Every kilo lands somewhere: used + returned + written off == transferred.
        accounted = flt(mip.used_in_fg_weight_kg) + flt(mip.returned_weight_kg) + \
            flt(mip.process_loss_weight_kg)
        check("transferred is fully accounted for",
              flt(accounted, 3), flt(mip.transferred_weight_kg, 3))

        # And the ledger agrees -- the gate reads this, not the summary fields above.
        from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
            _job_stock_at_supplier,
        )
        check("nothing left standing at the supplier",
              flt(sum(_job_stock_at_supplier(mip).values()), 3), 0.0)

        fg = frappe.db.get_value(
            "Stock Entry",
            {"subcontracting_order": mip.subcontracting_order,
             "stock_entry_type": "Manufacture", "docstatus": 1},
            ["name", "custom_mip_ref"], as_dict=True,
        )
        check("a final entry exists", bool(fg), True)
        if fg:
            check("it is reachable from the plan's Connections", fg.custom_mip_ref, mip_name)

    print("\n6. No submitted final entry anywhere is orphaned from its plan")
    orphans = frappe.db.sql(
        """
        SELECT se.name
        FROM `tabStock Entry` se
        JOIN `tabMaterial Issue Plan` mip
          ON mip.subcontracting_order = se.subcontracting_order
        WHERE se.stock_entry_type = 'Manufacture'
          AND se.docstatus = 1
          AND IFNULL(se.custom_mip_ref, '') = ''
        """,
        pluck=True,
    )
    check("untagged final entries", orphans, [])

    print("\n7. No plan is sitting Open with nothing left to do")
    stuck = []
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        _maybe_mark_completed,
    )
    for name in frappe.get_all("Material Issue Plan", filters={"status": ["!=", "Completed"]},
                               pluck="name"):
        doc = frappe.get_doc("Material Issue Plan", name)
        _maybe_mark_completed(doc)
        if doc.status == "Completed":
            stuck.append(name)
    check("plans eligible to close but still Open", stuck, [])

    total, passed = len(checks), sum(checks)
    print("\n%s %d/%d CHECKS PASSED" % ("ALL" if passed == total else "ONLY", passed, total))
    return passed == total
