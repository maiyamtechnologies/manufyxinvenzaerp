import frappe
def run():
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import validate_planned_stock
    for row in (validate_planned_stock("MP-2026-00014") or {}).get("rows", []):
        if "ISMB450" in (row.get("batch_no") or "") or "L6936" in (row.get("batch_no") or ""):
            print("  %-22s planned_kg=%-10s planned_sec=%-8s whole=%-4s stock=%s" % (
                row.get("batch_no"), row.get("planned_qty"), row.get("planned_sec_qty"),
                row.get("whole_sec_qty"), row.get("batch_stock_qty")))
    frappe.db.rollback()
