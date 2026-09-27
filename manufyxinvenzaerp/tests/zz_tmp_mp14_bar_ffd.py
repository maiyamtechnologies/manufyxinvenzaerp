"""READ-ONLY: proper 1-D bin packing (first-fit-decreasing) of MP-2026-00014's
structural cut lists into the bars actually received, and into the bars as ORDERED.
Temporary helper; rolls back."""
import math
import frappe
from frappe.utils import flt

MP = "MP-2026-00014"


def ffd(pieces, bar):
    bins = []
    for p in sorted(pieces, reverse=True):
        if p > bar + 1e-9:
            return None, p  # impossible
        for b in range(len(bins)):
            if bins[b] + p <= bar + 1e-9:
                bins[b] += p
                break
        else:
            bins.append(p)
    return len(bins), None


def run():
    mp = frappe.get_doc("Material Planning", MP)
    # cut list per item, and the bar received / ordered
    received = {}   # item_code -> (bar_len, bars_bought)
    for it in frappe.get_doc("Purchase Receipt", "PR-26-00006").items:
        if it.custom_parent_item_group != "Structurals":
            continue
        received[it.item_code] = (flt(it.custom_length), flt(it.custom_sec_qty))
    ordered = {}
    for it in frappe.get_doc("Purchase Order", "PUR-ORD-2026-00011").items:
        if it.custom_parent_item_group != "Structurals":
            continue
        ordered[it.item_code] = (flt(it.custom_length), flt(it.custom_sec_qty))

    cuts = {}
    for r in mp.material_mapping:
        if (r.parent_item_group or "") != "Structurals" or not r.batch:
            continue
        key = r.planned_item or r.item_code   # the item actually bought
        cuts.setdefault(key, []).extend([flt(r.length)] * int(round(flt(r.sec_qty))))

    for item, cl in sorted(cuts.items()):
        uw = flt(frappe.db.get_value("Item", item, "custom_unit_weight"))
        for label, src in (("AS RECEIVED", received), ("AS ORDERED", ordered)):
            bar, bought = src.get(item, (0, 0))
            if not bar:
                continue
            n, bad = ffd(cl, bar)
            per = bar / 1000.0 * uw
            if n is None:
                print("%-9s %-11s bar %8.2f mm x %3.0f bought -> IMPOSSIBLE: a %.2f mm piece does not fit"
                      % (item, label, bar, bought, bad))
                big = [p for p in cl if p > bar + 1e-9]
                print("          %d of %d pieces are longer than the bar (%.3f Kg of requirement)"
                      % (len(big), len(cl), sum(p / 1000.0 * uw for p in big)))
                rest = [p for p in cl if p <= bar + 1e-9]
                n2, _ = ffd(rest, bar)
                print("          the remaining %d pieces would need %d bars" % (len(rest), n2))
            else:
                short = n - bought
                print("%-9s %-11s bar %8.2f mm x %3.0f bought -> %3d bars needed (FFD optimum) %s"
                      % (item, label, bar, bought, n,
                         ("SHORT by %d bars = %.3f Kg" % (short, short * per)) if short > 0 else "OK"))
        print()
    frappe.db.rollback()
