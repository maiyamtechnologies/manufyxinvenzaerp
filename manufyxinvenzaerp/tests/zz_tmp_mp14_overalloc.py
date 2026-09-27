import frappe
from frappe.utils import flt
from erpnext.stock.doctype.batch.batch import get_batch_qty
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    _get_batch_reserved_by_others, _get_batch_total_stock, get_batch_cross_table_usage,
)

MP = "MP-2026-00014"

def run():
    mp = frappe.get_doc("Material Planning", MP)
    wh = mp.for_warehouse
    batches = {}
    for r in mp.available_raw_materials:
        if r.batch_no and r.is_reserved:
            batches.setdefault(r.batch_no, {"item": r.item_code, "res": 0.0})
            batches[r.batch_no]["res"] += flt(r.reserved_qty)
    for r in mp.material_mapping:
        if r.batch and r.is_reserved:
            batches.setdefault(r.batch, {"item": r.item_code, "res": 0.0})
            batches[r.batch]["res"] += flt(r.reserved_qty)

    print("%-32s %12s %12s %12s %12s %12s" % ("BATCH","THIS_PLAN","OTHERS","SBB_STOCK","get_batch_qty","FREE(SBB)"))
    for b, v in sorted(batches.items()):
        others = flt(_get_batch_reserved_by_others(b, MP))
        sbb = flt(_get_batch_total_stock(b, wh))
        gbq = flt(get_batch_qty(batch_no=b, warehouse=wh, item_code=v["item"]))
        free = sbb - others
        flag = ""
        if v["res"] > gbq - others + 0.001:
            flag = "  <<< OVER-ALLOC (vs get_batch_qty)"
        if sbb != gbq:
            flag += "  [SBB!=get_batch_qty]"
        print("%-32s %12.3f %12.3f %12.3f %12.3f %12.3f%s" % (b, v["res"], others, sbb, gbq, free, flag))

    # who else reserves these batches
    print("\n--- other plans' reservations on these batches ---")
    for b in sorted(batches):
        rows = frappe.db.sql("""
            SELECT parent, 'ARM' src, idx, item_code, reserved_qty FROM `tabMaterial Planning Available Raw Material`
             WHERE batch_no=%s AND is_reserved=1 AND parent!=%s
            UNION ALL
            SELECT parent, 'MM', idx, item_code, reserved_qty FROM `tabMaterial Planning Material Mapping`
             WHERE batch=%s AND is_reserved=1 AND parent!=%s
        """, (b, MP, b, MP), as_dict=True)
        if rows:
            agg = {}
            for r in rows:
                agg[(r.parent, r.src)] = agg.get((r.parent, r.src), 0) + flt(r.reserved_qty)
            for k, q in sorted(agg.items()):
                print("  %-32s %s/%s  %.3f" % (b, k[0], k[1], q))
        else:
            print("  %-32s none" % b)
