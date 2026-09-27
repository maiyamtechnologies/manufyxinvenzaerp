import frappe
from frappe.utils import flt
from erpnext.stock.doctype.batch.batch import get_batch_qty
MP="MP-2026-00014"
def run():
    mp=frappe.get_doc("Material Planning",MP)
    seq={}
    bad=[]
    for r in sorted(mp.available_raw_materials,key=lambda x:x.idx):
        k=(r.item_code,r.batch_no)
        if k not in seq:
            start=flt(get_batch_qty(batch_no=r.batch_no,warehouse=mp.for_warehouse,item_code=r.item_code))
            if abs(flt(r.available_qty)-start)>0.01:
                bad.append("idx %s first row on %s: available_qty %.3f != batch stock %.3f"%(r.idx,r.batch_no,flt(r.available_qty),start))
            seq[k]=flt(r.available_qty)
        else:
            if abs(flt(r.available_qty)-seq[k])>0.01:
                bad.append("idx %s %s: available_qty %.3f != expected running %.3f"%(r.idx,r.batch_no,flt(r.available_qty),seq[k]))
        seq[k]=flt(seq[k])-flt(r.required_qty)
    print("cascade problems: %d"%len(bad))
    for b in bad[:20]: print("  "+b)
    print("\nresiduals after plan:")
    for k,v in sorted(seq.items()): print("  %-32s %s  left %.3f"%(k[1],k[0],v))

    # zero/negative and suspicious rows
    print("\nsuspicious rows:")
    for r in mp.available_raw_materials:
        msgs=[]
        if flt(r.sec_qty)==0: msgs.append("sec_qty=0")
        if flt(r.required_qty)<0.01: msgs.append("required<0.01Kg")
        if flt(r.required_qty)>flt(r.available_qty)+0.001: msgs.append("required>available")
        if r.warehouse!=mp.for_warehouse: msgs.append("wh!=for_warehouse(%s)"%r.warehouse)
        if msgs: print("  idx %-3s %-8s %-30s reqd=%.3f sec=%.3f  %s"%(r.idx,r.item_code,r.batch_no,flt(r.required_qty),flt(r.sec_qty),", ".join(msgs)))
