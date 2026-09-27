"""READ-ONLY: provable lower bound on how many purchased plates MP-2026-00014's
PLATE10 cut list needs, plus cross-table usage and the decision log.
Temporary helper; rolls back at the end."""
import frappe
from frappe.utils import flt
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    get_batch_cross_table_usage,
)

MP = "MP-2026-00014"
WH = "Stores - MIPL"


def run():
    mp = frappe.get_doc("Material Planning", MP)
    bat = frappe.get_doc("Batch", "PLT10-T10-L740-W311-R006")
    BL, BW, BT = flt(bat.custom_length), flt(bat.custom_width), flt(bat.custom_thickness)
    bought = flt(bat.custom_sec_qty)
    print("plate bought: %.2f x %.2f x %.2f, %.0f plates" % (BL, BW, BT, bought))

    pieces = []
    for r in mp.material_mapping:
        if r.item_code != "PLATE10" or not r.batch:
            continue
        for _ in range(int(round(flt(r.sec_qty)))):
            pieces.append((flt(r.length), flt(r.width), flt(r.thickness)))
    print("cut pieces: %d" % len(pieces))
    over_t = [p for p in pieces if p[2] > BT + 1e-9]
    print("pieces thicker than the plate bought: %d" % len(over_t))
    over_size = [p for p in pieces if p[0] > BL + 1e-9 or p[1] > BW + 1e-9]
    print("pieces longer/wider than the plate bought: %d" % len(over_size))

    # Provable bound 1: a piece whose SHORT side exceeds half the plate's short side
    # occupies the full plate width for its whole length, so those pieces can only be
    # laid end to end along the plate length -- at most one row per plate.
    half_w = BW / 2.0
    full_width = [p for p in pieces if min(p[0], p[1]) > half_w]
    tot_len = sum(min(p[0], p[1]) if max(p[0], p[1]) > BW else max(p[0], p[1]) for p in full_width)
    print("\nBOUND A -- pieces needing the full plate width (short side > %.1f mm): %d, total run %.1f mm"
          % (half_w, len(full_width), tot_len))
    import math
    print("          plates needed for those alone >= ceil(%.1f / %.2f) = %d"
          % (tot_len, BL, math.ceil(tot_len / BL)))

    # Provable bound 2: pieces longer than half the plate length AND wider than half the
    # plate width cannot share a plate with each other at all.
    solo = [p for p in pieces if p[0] > BL / 2.0 and p[1] > BW / 2.0]
    print("\nBOUND B -- pieces > half length AND > half width (no two can share a plate): %d" % len(solo))
    for p in sorted(set(solo), reverse=True):
        print("          %.2f x %.2f  x%d" % (p[0], p[1], solo.count(p)))
    print("          plates needed >= %d ; bought %.0f  %s"
          % (len(solo), bought, "<<< SHORT" if len(solo) > bought else "OK"))

    # Area bound
    area_req = sum(p[0] * p[1] for p in pieces)
    area_bought = BL * BW * bought
    print("\nAREA -- required %.0f mm2, bought %.0f mm2, utilisation needed %.1f%%"
          % (area_req, area_bought, 100.0 * area_req / area_bought))

    print("\n== get_batch_cross_table_usage (batch, MP, warehouse) ==")
    seen = set()
    for r in list(mp.material_mapping) + list(mp.available_raw_materials):
        b = r.get("batch") or r.get("batch_no")
        if b and b not in seen:
            seen.add(b)
            print("   %-30s %s" % (b, get_batch_cross_table_usage(b, MP, WH)))

    print("\n== Manufyx Decision Log for this plan ==")
    for d in frappe.get_all("Manufyx Decision Log",
                            filters={"material_planning": MP},
                            fields=["name", "action", "item_code", "batch_no", "qty", "creation", "remarks"],
                            order_by="creation") or []:
        print("   ", d)

    print("\n== RFQ / Supplier Quotation touching this chain ==")
    print("   SQ:", frappe.db.sql("""
        SELECT DISTINCT sq.name, sq.docstatus, sq.supplier FROM `tabSupplier Quotation` sq
        JOIN `tabSupplier Quotation Item` sqi ON sqi.parent=sq.name
        WHERE sqi.material_request='MAT-MR-2026-00004'""", as_dict=True))
    print("   RFQ:", frappe.db.sql("""
        SELECT DISTINCT r.name, r.docstatus FROM `tabRequest for Quotation` r
        JOIN `tabRequest for Quotation Item` ri ON ri.parent=r.name
        WHERE ri.material_request='MAT-MR-2026-00004'""", as_dict=True))
    print("   PO items with supplier_quotation:", frappe.db.sql("""
        SELECT name, supplier_quotation FROM `tabPurchase Order Item`
        WHERE parent='PUR-ORD-2026-00011' AND IFNULL(supplier_quotation,'')!=''""", as_dict=True))

    print("\n== other plans / MIPs referencing PR-26-00006 batches ==")
    print(frappe.db.sql("""
        SELECT 'MM' src, parent, item_code, batch, qty, reserved_qty
          FROM `tabMaterial Planning Material Mapping`
         WHERE batch LIKE '%%-R006' AND parent!=%s
        UNION ALL
        SELECT 'ARM', parent, item_code, batch_no, required_qty, reserved_qty
          FROM `tabMaterial Planning Available Raw Material`
         WHERE batch_no LIKE '%%-R006' AND parent!=%s
        UNION ALL
        SELECT 'MIP', parent, item_code, batch_no, qty, 0
          FROM `tabMaterial Issue Plan Raw Material`
         WHERE batch_no LIKE '%%-R006'
    """, (MP, MP), as_dict=True))

    print("\n== stock ledger for PR-26-00006 (trap 1: batch_no is blank here) ==")
    print(frappe.db.sql("""
        SELECT item_code, warehouse, actual_qty, batch_no, serial_and_batch_bundle
          FROM `tabStock Ledger Entry` WHERE voucher_no='PR-26-00006' AND is_cancelled=0
    """, as_dict=True))

    frappe.db.rollback()
