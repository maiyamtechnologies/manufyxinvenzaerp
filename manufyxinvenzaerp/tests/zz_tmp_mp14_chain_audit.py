"""READ-ONLY audit of the MP-2026-00014 purchase chain (MR-00004 / PO-00011 / PR-26-00006).
Temporary helper written for a verification pass; rolls back at the end. Safe to re-run."""
import frappe
from frappe.utils import flt
from erpnext.stock.doctype.batch.batch import get_batch_qty
from manufyxinvenzaerp.purchase_receipt_management.purchase_receipt import (
    get_mp_for_pr, diagnose_mp_allocation, get_pr_mp_allocations, _pr_dimensions_match,
)
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    _get_batch_reserved_by_others, _get_batch_total_stock, get_batch_cross_table_usage,
)

MP = "MP-2026-00014"
PR = "PR-26-00006"
WH = "Stores - MIPL"


def run():
    frappe.set_user("Administrator")
    print("== get_mp_for_pr(%s) ==" % PR)
    print(get_mp_for_pr(PR))
    print("\n== diagnose_mp_allocation(%s) ==" % PR)
    print(diagnose_mp_allocation(PR))
    print("\n== get_pr_mp_allocations(%s) ==" % PR)
    for r in get_pr_mp_allocations(PR):
        print("   ", r)

    print("\n== batch quantities (get_batch_qty vs SBB helper) ==")
    mp = frappe.get_doc("Material Planning", MP)
    batches = {}
    for r in mp.available_raw_materials:
        if r.batch_no:
            batches.setdefault(r.batch_no, {"item": r.item_code, "res": 0.0, "claim": 0.0})
            batches[r.batch_no]["res"] += flt(r.reserved_qty)
            batches[r.batch_no]["claim"] += flt(r.required_qty)
    for r in mp.material_mapping:
        if r.batch:
            batches.setdefault(r.batch, {"item": r.item_code, "res": 0.0, "claim": 0.0})
            batches[r.batch]["res"] += flt(r.reserved_qty)
            batches[r.batch]["claim"] += flt(r.batch_calc_qty)
    print("%-30s %-9s %11s %11s %11s %11s %11s" % (
        "BATCH", "ITEM", "get_bqty", "SBB_stock", "this_res", "claimed", "others"))
    for b, v in sorted(batches.items()):
        item = frappe.db.get_value("Batch", b, "item")
        gbq = flt(get_batch_qty(batch_no=b, warehouse=WH, item_code=item))
        sbb = flt(_get_batch_total_stock(b, WH))
        others = flt(_get_batch_reserved_by_others(b, MP))
        flag = ""
        if v["res"] > gbq - others + 0.001:
            flag = "  <<< OVER-RESERVED"
        print("%-30s %-9s %11.3f %11.3f %11.3f %11.3f %11.3f%s" % (
            b, item, gbq, sbb, v["res"], v["claim"], others, flag))

    print("\n== cross-table usage ==")
    for b in sorted(batches):
        try:
            print("   %-30s %s" % (b, get_batch_cross_table_usage(b)))
        except Exception as e:
            print("   %-30s ERR %s" % (b, e))

    print("\n== _pr_dimensions_match for every PR line x every plan row it landed on ==")
    pr = frappe.get_doc("Purchase Receipt", PR)
    by_batch = {}
    for it in pr.items:
        bno = frappe.db.get_value("Serial and Batch Entry", {"parent": it.serial_and_batch_bundle}, "batch_no")
        by_batch[bno] = it
    for r in mp.material_mapping:
        it = by_batch.get(r.batch)
        if not it:
            continue
        m = _pr_dimensions_match(it, r)
        if m != (not r.reserve_without_dimensions):
            print("   MISMATCH idx %s %s: dims_match=%s rwd=%s" % (r.idx, r.item_code, m, r.reserve_without_dimensions))
    print("   (no output above = every row's reserve_without_dimensions agrees with _pr_dimensions_match)")

    print("\n== undersized received stock: required cut size vs batch size ==")
    print("%-5s %-9s %-9s %10s %10s %10s %10s %10s %10s %s" % (
        "idx", "item", "planned", "req_L", "bat_L", "req_W", "bat_W", "req_T", "bat_T", "verdict"))
    bad = 0
    for r in mp.material_mapping:
        if not r.batch:
            continue
        probs = []
        if flt(r.batch_length) and flt(r.length) and flt(r.batch_length) < flt(r.length) - 0.0005:
            probs.append("L short %.2f" % (flt(r.length) - flt(r.batch_length)))
        if flt(r.batch_width) and flt(r.width) and flt(r.batch_width) < flt(r.width) - 0.0005:
            probs.append("W short %.2f" % (flt(r.width) - flt(r.batch_width)))
        if flt(r.batch_thickness) and flt(r.thickness) and flt(r.batch_thickness) < flt(r.thickness) - 0.0005:
            probs.append("T short %.2f" % (flt(r.thickness) - flt(r.batch_thickness)))
        if probs:
            bad += 1
            print("%-5s %-9s %-9s %10.2f %10.2f %10.2f %10.2f %10.2f %10.2f %s  qty=%.3f sec=%.0f" % (
                r.idx, r.item_code, r.planned_item, flt(r.length), flt(r.batch_length),
                flt(r.width), flt(r.batch_width), flt(r.thickness), flt(r.batch_thickness),
                ", ".join(probs), flt(r.qty), flt(r.sec_qty)))
    print("   rows with stock smaller than the cut piece: %d" % bad)

    print("\n== piece feasibility: can the bought pieces yield the cut pieces? ==")
    # group requirements by purchased batch, then count how many bars each cut length needs
    agg = {}
    for r in mp.material_mapping:
        if not r.batch:
            continue
        agg.setdefault(r.batch, {}).setdefault(round(flt(r.length), 2), 0)
        agg[r.batch][round(flt(r.length), 2)] += flt(r.sec_qty)
    for b, lens in sorted(agg.items()):
        bat = frappe.get_doc("Batch", b)
        bl = flt(bat.custom_length)
        bsec = flt(bat.custom_sec_qty)
        group = frappe.db.get_value("Item", bat.item, "custom_parent_item_group")
        if group != "Structurals" or not bl:
            print("   %-30s (%s -- skipped, nesting not a 1-D problem)" % (b, group))
            continue
        need = 0.0
        detail = []
        for L, n in sorted(lens.items(), reverse=True):
            if L <= 0:
                continue
            per_bar = int(bl // L)
            if per_bar < 1:
                detail.append("%d x %.0fmm IMPOSSIBLE (bar %.0f)" % (n, L, bl))
                need = float("inf")
                continue
            bars = -(-int(round(n)) // per_bar)
            need += bars
            detail.append("%d x %.0fmm -> %d/bar -> %d bars" % (n, L, per_bar, bars))
        print("   %-30s bar %.2fmm x %.0f pcs bought" % (b, bl, bsec))
        for d in detail:
            print("        %s" % d)
        print("        bars needed (best case, no offcut re-use): %s ; bought %.0f %s" % (
            need, bsec, "<<< SHORT" if need > bsec else "OK"))

    print("\n== weight summary reconciliation ==")
    rm = sum(flt(r.qty) for r in mp.raw_materials)
    arm = sum(flt(r.required_qty) for r in mp.available_raw_materials)
    mm = sum(flt(r.qty) for r in mp.material_mapping)
    un = sum(flt(r.qty) for r in mp.unavailable_items)
    print("   raw_materials qty sum           %12.3f  (field total_weight_plates_structurals %.3f)" % (
        rm, flt(mp.total_weight_plates_structurals)))
    print("   available_raw_materials req sum %12.3f  (field weight_exact_raw_material %.3f)" % (
        arm, flt(mp.weight_exact_raw_material)))
    print("   material_mapping qty sum        %12.3f  (field expected_weight_material_mapping %.3f)" % (
        mm, flt(mp.expected_weight_material_mapping)))
    print("   weight_cross_item_mapped        %12.3f" % flt(mp.weight_cross_item_mapped))
    print("   unavailable_items qty sum       %12.3f" % un)
    print("   arm + mm + unavail              %12.3f  vs raw_materials %.3f  diff %.3f" % (
        arm + mm + un, rm, arm + mm + un - rm))
    print("   planning_status                 %s" % mp.planning_status)

    print("\n== sec_qty sanity on every batch this plan reserves ==")
    for b in sorted(batches):
        bat = frappe.get_doc("Batch", b)
        gbq = flt(get_batch_qty(batch_no=b, warehouse=WH, item_code=bat.item))
        uw = flt(frappe.db.get_value("Item", bat.item, "custom_unit_weight"))
        group = frappe.db.get_value("Item", bat.item, "custom_parent_item_group")
        if group == "Plates":
            per = flt(bat.custom_length) * flt(bat.custom_width) * flt(bat.custom_thickness) * uw / 1e6
        else:
            per = flt(bat.custom_length) / 1000.0 * uw
        expect = (gbq / per) if per else 0.0
        ok = abs(expect - flt(bat.custom_sec_qty)) < 0.01
        print("   %-30s qty %11.3f  per_piece %9.3f  implied_sec %8.3f  custom_sec_qty %8.3f  %s" % (
            b, gbq, per, expect, flt(bat.custom_sec_qty), "OK" if ok else "<<< MISMATCH"))

    frappe.db.rollback()
