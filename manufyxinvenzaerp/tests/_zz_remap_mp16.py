"""One-off: re-map MP-2026-00016 the way the form's buttons do (Unreserve -> Check
Stock Availability -> Reserve), after the per-warehouse Nos fix."""
import json
import frappe
from frappe.utils import flt

MP = "MP-2026-00016"


def run():
    from manufyxinvenzaerp.production_management.doctype.material_planning import material_planning as m

    mp = frappe.get_doc("Material Planning", MP)
    arm = [r.name for r in mp.available_raw_materials if r.is_reserved]
    mm = [r.name for r in mp.material_mapping if r.is_reserved]
    print("1. unreserve: %d exact-match rows, %d mapping rows" % (len(arm), len(mm)))
    if arm:
        m.unreserve_exact_match_batches(MP, json.dumps(arm))
    if mm:
        m.unreserve_batches(MP, json.dumps(mm))

    mp = frappe.get_doc("Material Planning", MP)
    res = m.check_stock_availability(json.dumps(mp.as_dict(), default=str))
    # Same as the form's check_stock_btn callback: replace the four tables with the result.
    for table in ("raw_materials", "available_raw_materials", "material_mapping", "unavailable_items"):
        mp.set(table, [])
        for row in res.get(table) or []:
            row = {k: v for k, v in dict(row).items() if k not in ("name", "idx", "parent", "parentfield", "parenttype", "doctype")}
            child = mp.append(table, row)
            if table == "material_mapping" and not child.get("batch_mapped"):
                child.batch_mapped = "Mapped" if child.get("batch") else "Not Mapped"
    mp.save()
    print("2. re-checked: %d exact match, %d mapping, %d unavailable" % (
        len(mp.available_raw_materials), len(mp.material_mapping), len(mp.unavailable_items)))

    if mp.available_raw_materials:
        m.reserve_exact_match_batches(MP)
    if mp.material_mapping:
        m.reserve_batches(MP)
    mp = frappe.get_doc("Material Planning", MP)
    rows = list(mp.available_raw_materials) + list(mp.material_mapping)
    print("3. reserved: %d of %d rows, status %s" % (sum(1 for r in rows if r.is_reserved), len(rows), mp.planning_status))
    frappe.db.commit()
