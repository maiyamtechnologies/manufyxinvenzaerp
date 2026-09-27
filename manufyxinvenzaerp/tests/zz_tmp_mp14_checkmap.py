import frappe
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    complete_batch_mapping, validate_planned_stock,
)
def run():
    r = complete_batch_mapping("MP-2026-00014")
    print("=== Check Mapping ===  status=%s planning_status=%s  issues=%d" % (r["status"], r["planning_status"], len(r["issues"])))
    for i, m in enumerate(r["issues"], 1):
        print("  %d. %s" % (i, str(m)))
    print("\n=== Validate Stock ===")
    rows = validate_planned_stock("MP-2026-00014")
    if rows and isinstance(rows, dict):
        rows = rows.get("rows") or rows
    for row in (rows or []):
        print("  " + str(dict(row)))
    frappe.db.rollback()
