import frappe
from frappe.utils import flt


def run():
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _job_stock_at_supplier, get_mip_process_loss_state,
    )
    for mip_name in ("MIP-2026-00002", "MIP-2026-00003"):
        mip = frappe.get_doc("Material Issue Plan", mip_name)
        mip.flags.mfx_saved_by_another_document = True
        mip.save(ignore_permissions=True)
        mip.reload()
        s = get_mip_process_loss_state(mip_name)
        at = _job_stock_at_supplier(mip)
        print("== %s (%s) sco=%s" % (mip_name, mip.status, mip.subcontracting_order))
        print("   transferred      %10.3f" % flt(mip.transferred_weight_kg))
        print("   used in FG       %10.3f" % flt(mip.used_in_fg_weight_kg))
        print("   excess planned   %10.3f" % flt(mip.excess_return_total_kg))
        print("   actually returned%10.3f" % flt(mip.returned_weight_kg))
        print("   process loss     %10.3f" % flt(mip.process_loss_weight_kg))
        bal = flt(mip.transferred_weight_kg) - flt(mip.used_in_fg_weight_kg) \
              - flt(mip.returned_weight_kg) - flt(mip.process_loss_weight_kg)
        print("   -> unaccounted   %10.3f   (still at supplier per ledger: %.3f)"
              % (bal, flt(sum(at.values()), 3)))
        print("   final entry made: %s | over %s%% threshold: %s"
              % (s["final_entry_exists"], s["threshold_pct"], s["over_threshold"]))
    frappe.db.rollback()
