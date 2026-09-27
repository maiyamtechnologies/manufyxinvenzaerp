import frappe
from frappe.utils import flt
from erpnext.stock.doctype.batch.batch import get_batch_qty

MP = "MP-2026-00014"

def run():
    mp = frappe.get_doc("Material Planning", MP)
    wh = mp.for_warehouse
    print("plan=%s wh=%s company=%s" % (MP, wh, mp.company))

    # collect batches referenced on this plan
    refs = {}
    for r in mp.available_raw_materials:
        if r.batch_no:
            k = (r.item_code, r.batch_no)
            refs.setdefault(k, {"reqd": 0.0, "res": 0.0, "rows": 0})
            refs[k]["reqd"] += flt(r.required_qty)
            refs[k]["res"] += flt(r.reserved_qty) if r.is_reserved else 0.0
            refs[k]["rows"] += 1
    for r in mp.material_mapping:
        if r.batch:
            k = (r.item_code, r.batch)
            refs.setdefault(k, {"reqd": 0.0, "res": 0.0, "rows": 0})
            refs[k]["reqd"] += flt(r.qty)
            refs[k]["res"] += flt(r.reserved_qty) if r.is_reserved else 0.0
            refs[k]["rows"] += 1

    print("\n%-32s %-10s %14s %14s %14s %6s" % ("BATCH", "ITEM", "REQD_ON_PLAN", "QTY_IN_FORWH", "QTY_ALL_WH", "ROWS"))
    for (item, b), v in sorted(refs.items(), key=lambda x: x[0][1]):
        q_wh = flt(get_batch_qty(batch_no=b, warehouse=wh, item_code=item))
        allwh = get_batch_qty(batch_no=b, warehouse=None, item_code=item)
        tot = sum(flt(d.get("qty")) for d in (allwh or [])) if isinstance(allwh, list) else flt(allwh)
        print("%-32s %-10s %14.3f %14.3f %14.3f %6d%s" % (b, item, v["reqd"], q_wh, tot, v["rows"],
              "   <<< SHORT" if q_wh < v["reqd"] - 0.001 else ""))
        if isinstance(allwh, list):
            for d in allwh:
                if d.get("warehouse") != wh and flt(d.get("qty")):
                    print("        also in %s: %.3f" % (d.get("warehouse"), flt(d.get("qty"))))

    # batch master details + exists check
    print("\n--- batch master ---")
    for (item, b), v in sorted(refs.items(), key=lambda x: x[0][1]):
        if not frappe.db.exists("Batch", b):
            print("MISSING BATCH MASTER: %s" % b)
            continue
        d = frappe.db.get_value("Batch", b, ["item", "batch_qty", "disabled", "sec_qty", "custom_length", "custom_width", "custom_thickness"], as_dict=True)
        print("%-32s %s" % (b, d))
