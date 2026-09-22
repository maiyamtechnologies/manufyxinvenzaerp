"""
Patch: backfill_fg_entry_mip_ref

Two repairs for the same gap, both fixed in code as of this patch.

1. The final Manufacture entry carried no custom_mip_ref.
   create_finished_goods_entry built it with subcontracting_order only, and the
   plan's Connections panel keys on custom_mip_ref alone
   (material_issue_plan_dashboard) -- so the one entry that finishes the job was
   the only one missing from the panel. Tag every existing one from its plan.

2. Material Issue Plans left on Open with nothing outstanding.
   The completion gate reads the stock ledger, which counts submitted entries
   only. create_mip_process_loss_entry inserts its write-off as a DRAFT and then
   saves the plan in the same call, so _maybe_mark_completed ran against a ledger
   the draft was invisible to and saw exactly the weight that was about to be
   written off. The submit that cleared it fired no re-check: on_submit_stock_entry
   covered Send to Subcontractor, Material Transfer and Manufacture, but not
   Material Issue (process loss) or Repack (excess return) -- the last two steps
   of the chain. A plan finishing on either one stayed Open for good, because a
   finished plan has no further event to fire.

   MIP-2026-00003 on the live server is exactly that: 3975.154 Kg transferred,
   1592.976 used in finished goods, 2074.642 returned, 307.536 written off --
   every kilo accounted for, still reading Open.

Re-checks every non-Completed plan once. recheck_mip_completion re-applies the
real gate rather than assuming anything, so a plan with genuine work outstanding
is left alone; it only ever moves Open/In Progress -> Completed.
"""

import frappe


def execute():
    _backfill_fg_entry_refs()
    _recheck_stuck_plans()
    frappe.db.commit()


def _backfill_fg_entry_refs():
    """Tag submitted/draft Manufacture entries with the plan behind their SCO."""
    rows = frappe.db.sql(
        """
        SELECT se.name, mip.name AS mip
        FROM `tabStock Entry` se
        JOIN `tabMaterial Issue Plan` mip
          ON mip.subcontracting_order = se.subcontracting_order
        WHERE se.stock_entry_type = 'Manufacture'
          AND se.docstatus < 2
          AND IFNULL(se.custom_mip_ref, '') = ''
          AND IFNULL(se.subcontracting_order, '') != ''
        """,
        as_dict=True,
    )
    for r in rows:
        # update_modified=False: this is a missing back-reference, not an edit
        # anyone made, and these entries are submitted -- a normal save is not
        # available to them anyway.
        frappe.db.set_value("Stock Entry", r.name, "custom_mip_ref", r.mip, update_modified=False)

    print(f"backfill_fg_entry_mip_ref: tagged {len(rows)} final Stock Entry(ies) with their plan")


def _recheck_stuck_plans():
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        recheck_mip_completion,
    )

    names = frappe.get_all(
        "Material Issue Plan", filters={"status": ["!=", "Completed"]}, pluck="name"
    )
    if not names:
        return

    changed = 0
    for name in names:
        try:
            recheck_mip_completion(name)
        except Exception:
            # One unreadable plan must not stop the migrate; it will correct
            # itself on the next Stock Entry submitted against it.
            frappe.log_error(
                title=f"backfill_fg_entry_mip_ref: could not re-check {name}",
                message=frappe.get_traceback(),
            )
            continue
        if frappe.db.get_value("Material Issue Plan", name, "status") == "Completed":
            changed += 1

    print(f"backfill_fg_entry_mip_ref: re-checked {len(names)} plan(s), {changed} now Completed")
