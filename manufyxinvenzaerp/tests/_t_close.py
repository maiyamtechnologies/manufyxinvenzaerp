import frappe
from frappe.utils import flt


def run():
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import _job_stock_at_supplier
    mip = frappe.get_doc("Material Issue Plan", "MIP-2026-00018")
    print("BEFORE status=%s  left=%.3f" % (mip.status, flt(sum(_job_stock_at_supplier(mip).values()), 3)))
    mip.flags.mfx_saved_by_another_document = True
    mip.save(ignore_permissions=True)
    mip.reload()
    print("AFTER  status=%s used=%s returned=%s loss=%s reason=%r"
          % (mip.status, mip.used_in_fg_weight_kg, mip.returned_weight_kg,
             mip.process_loss_weight_kg, mip.process_loss_reason))
    frappe.db.commit()
