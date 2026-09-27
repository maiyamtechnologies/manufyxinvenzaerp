import frappe
from frappe.utils import flt
from erpnext.stock.doctype.batch.batch import get_batch_qty
SE, MIP, MP = "MAT-STE-00357", "MIP-2026-00059", "MP-2026-00260"

def run():
    s = frappe.get_doc("Stock Entry", SE)
    print(f"=== {SE} ===  type={s.stock_entry_type} docstatus={s.docstatus} posting={s.posting_date}")
    print(f"   mip_ref={s.get('custom_mip_ref')}  sco_ref={s.get('custom_sco_ref')}  "
          f"sco={s.get('subcontracting_order')}")
    print(f"\n   {'item':<9} {'Kg':>10} {'sec':>7} {'batch':<30} {'from':<16} {'to':<14} {'duno':<6} {'drawing':<16} cdn")
    tot = 0
    for r in s.items:
        tot += flt(r.qty)
        print(f"   {r.item_code:<9} {flt(r.qty):>10.3f} {flt(r.get('custom_sec_qty')):>7.3f} "
              f"{str(r.batch_no)[:30]:<30} {str(r.s_warehouse)[:16]:<16} {str(r.t_warehouse)[:14]:<14} "
              f"{str(r.get('custom_duno_mark_no') or ''):<6} {str(r.get('custom_drawing') or '-'):<16} "
              f"{str(r.get('custom_customer_drawing_number') or '')[:24]}")
    print(f"   TOTAL {tot:.3f} Kg")

    print("\n=== STOCK NOW ===")
    for b in ("ISA100-L12000-SR001","ISMB400-L12000-SR001","PLT10-P10-L10000-W2000-SR001"):
        rows = get_batch_qty(batch_no=b, warehouse=None) or []
        parts = [f"{r['warehouse']}={flt(r['qty']):.3f}" for r in rows if flt(r.get("qty"))]
        print(f"   {b:<32} {' | '.join(parts)}")

    m = frappe.get_doc("Material Issue Plan", MIP)
    print("\n=== MIP CNC rows ===")
    for r in (m.raw_materials or []):
        if r.cnc_process:
            print(f"   idx={r.idx} {r.item_code:<9} duno={r.duno_mark_no} qty={flt(r.qty):>9.3f} "
                  f"issued={flt(r.transferred_qty):>9.3f}")

    d = frappe.get_doc("Material Planning", MP)
    print("\n=== MP 1B1 rows (reservation released?) ===")
    for r in (d.available_raw_materials or []):
        if r.duno_mark_no == "1B1":
            print(f"   idx={r.idx} {r.item_code:<9} reqd={flt(r.required_qty):>9.3f} "
                  f"reserved={flt(r.reserved_qty):>9.3f} is_reserved={r.is_reserved}")
