"""
Patch: backfill_production_plan_status

Production Plan status now follows the job rather than Work Orders -- In Process
once material has been transferred against the Material Issue Plan or any
operation has quantity logged, Completed once the final Stock Entry is submitted
(see production_plan.refresh_production_plan_status).

ERPNext derives it from total_produced_qty and all_items_completed(), both of
which read Work Orders. This app's plans never create one, so every plan
submitted before now sat on "Not Started"/"Submitted" no matter how far the job
had actually got, and nothing would move them: the status is re-derived when
material moves or an operation is saved, and a finished plan has no such event
left to fire.

Re-derives every submitted plan that has a Job Work Order behind it. Plans
without one are left entirely alone -- they are standard plans and ERPNext's own
Work-Order-driven status is still the right answer for them.
"""

import frappe


def execute():
    names = frappe.get_all(
        "Subcontracting Order",
        filters={"docstatus": 1, "custom_production_plan": ["is", "set"]},
        pluck="custom_production_plan",
        distinct=True,
    )
    if not names:
        return

    from manufyxinvenzaerp.production_plan_management.production_plan import (
        refresh_production_plan_status,
    )

    changed = 0
    for name in names:
        before = frappe.db.get_value("Production Plan", name, "status")
        try:
            refresh_production_plan_status(name)
        except Exception:
            # One unreadable plan must not stop the migrate; it corrects itself
            # the next time material moves against it.
            frappe.log_error(
                title=f"backfill_production_plan_status: could not re-derive {name}",
                message=frappe.get_traceback(),
            )
            continue
        if frappe.db.get_value("Production Plan", name, "status") != before:
            changed += 1

    frappe.db.commit()
    print(f"backfill_production_plan_status: re-derived {len(names)} plan(s), {changed} changed")
