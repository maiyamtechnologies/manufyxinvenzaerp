import frappe
from collections import defaultdict
from frappe.utils import flt
def run():
    pp = frappe.get_doc("Production Plan", "PP-INT-2026-00004")
    mip = frappe.get_doc("Material Issue Plan", "MIP-2026-00007")
    # independent fractions: this plan's Nos / the drawing's Total Quantity on the Drawing itself
    frac = {}
    for r in pp.po_items:
        d = frappe.db.get_value("Drawing", r.custom_drawing, ["duno_mark_no", "no_of_qty_to_manufacture", "docstatus"], as_dict=True)
        others = frappe.db.sql("""select ppi.parent, sum(ppi.custom_sec_qty) from `tabProduction Plan Item` ppi join `tabProduction Plan` p on p.name=ppi.parent
            where ppi.custom_drawing=%s and p.docstatus<2 and p.name!=%s group by ppi.parent""", (r.custom_drawing, pp.name))
        frac[r.custom_duno_mark_no] = flt(r.custom_sec_qty) / flt(d.no_of_qty_to_manufacture)
        print("DRAW", r.custom_duno_mark_no, r.custom_drawing, "total", d.no_of_qty_to_manufacture, "here", r.custom_sec_qty, "other plans", others, "frac", round(frac[r.custom_duno_mark_no], 4))
    exp = defaultdict(lambda: [0.0, 0.0])
    for r in frappe.get_all("Material Planning Material Mapping", filters={"parent": "MP-2026-00016", "duno_mark_no": ["in", list(frac)], "is_reserved": 1},
                            fields=["duno_mark_no", "item_code", "planned_item", "batch", "reserved_qty", "batch_calc_qty", "batch_sec_qty"]):
        f = frac[r.duno_mark_no]; kg = flt(r.reserved_qty)
        nos = flt(r.batch_sec_qty) * min(kg / flt(r.batch_calc_qty), 1) if flt(r.batch_calc_qty) else 0
        k = (r.duno_mark_no, r.planned_item or r.item_code, r.batch); exp[k][0] += kg * f; exp[k][1] += nos * f
    for r in frappe.get_all("Material Planning Available Raw Material", filters={"parent": "MP-2026-00016", "duno_mark_no": ["in", list(frac)], "is_reserved": 1},
                            fields=["duno_mark_no", "item_code", "batch_no", "reserved_qty", "sec_qty"]):
        f = frac[r.duno_mark_no]
        k = (r.duno_mark_no, r.item_code, r.batch_no); exp[k][0] += flt(r.reserved_qty) * f; exp[k][1] += flt(r.sec_qty) * f
    got = defaultdict(lambda: [0.0, 0.0])
    for r in mip.raw_materials:
        k = (r.duno_mark_no, r.planned_item or r.item_code, r.batch_no); got[k][0] += flt(r.qty); got[k][1] += flt(r.sec_qty)
    bad = 0
    for k in sorted(set(exp) | set(got)):
        e, g = exp.get(k, [0, 0]), got.get(k, [0, 0])
        ok = abs(e[0] - g[0]) <= 0.01 and abs(e[1] - g[1]) <= 0.002
        bad += not ok
        print("%-4s %-4s %-8s %-26s expected %10.3f kg %7.3f nos | MIP %10.3f kg %7.3f nos" % ("OK" if ok else "DIFF", *k, e[0], e[1], g[0], g[1]))
    print("TOTAL expected %.3f kg / %.3f nos, MIP %.3f kg / %.3f nos, mismatches %d" % (
        sum(v[0] for v in exp.values()), sum(v[1] for v in exp.values()), sum(v[0] for v in got.values()), sum(v[1] for v in got.values()), bad))
    # the drawing rows' planned weight vs the Production Plan's planned qty
    for r in pp.po_items:
        dp = {flt(x.drawing_planned_weight, 3) for x in mip.raw_materials if x.duno_mark_no == r.custom_duno_mark_no}
        print("PLANNED", r.custom_duno_mark_no, "PP planned_qty", r.planned_qty, "MIP drawing_planned_weight", sorted(dp))
