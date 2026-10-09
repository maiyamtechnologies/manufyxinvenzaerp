"""Verify that Excess Material and Cut Sheet now behave the same way.

Both are pools of dimensioned pieces with no stock ledger of their own, shared out
across jobs until they run out. This covers the half that was still all-or-nothing:

  * an off-cut can be claimed in PIECES, not only whole
  * the remainder stays free for another Material Planning
  * over-claiming is refused
  * the Availability figures shown on the Excess Material Items row are live
  * the picker stops offering an off-cut once nothing is left
  * when it physically returns, the batch attaches to EVERY row holding a piece

Plus the batch-driven Cut Sheet rules:
  * picking a batch that has a Cut Sheet ticks Cut Sheet by itself
  * a row cannot ask for more pieces than that sheet has free

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_excess_partial_and_flags.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties
from frappe.utils import flt, today

from manufyxinvenzaerp.tests.create_full_test_entry import get_ctx, ensure_item
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    claim_virtual_excess_mapping, get_available_virtual_excess_items,
    excess_row_availability, materialize_virtual_excess_claim,
)
from manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet import allocate_cut_sheet

RESULTS = []
UW, THICK = 7.85, 5.0


def check(label, cond, detail=""):
    RESULTS.append((label, bool(cond)))
    print(("PASS" if cond else "FAIL") + " -- " + label + (("  | " + detail) if detail else ""))


def _throws(fn, needle):
    try:
        fn()
    except frappe.ValidationError as e:
        return needle.lower() in str(e).lower(), str(e)[:140]
    return False, "it did NOT raise"


def run():
    ctx = get_ctx()
    item = ensure_item(ctx, "ZZTEST-EXPART", "Excess Partial Test Plate", uom="Kg")
    frappe.db.set_value("Item", item, {
        "custom_parent_item_group": "Plates", "custom_unit_weight": UW,
        "create_new_batch": 1, "custom_batch_prefix": "ZZEXPART",
    })

    # A Material Issue Plan carrying one off-cut worth 6 pieces. It needs a Production
    # Plan behind it (mandatory field) even though nothing here is produced.
    bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1},
                              ["name", "item", "quantity"], as_dict=True)
    pp = frappe.new_doc("Production Plan")
    pp.custom_type, pp.company, pp.posting_date, pp.get_items_from = "Internal Job", ctx.company, today(), ""
    pp.append("po_items", {
        "item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1,
        "stock_uom": frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos",
    })
    pp.append("custom_process_planning", {"operation_name": "Material Issue", "work_type": "Internal Jobcard"})
    pp.insert(ignore_permissions=True)
    fill_process_planning_parties(pp)
    pp.submit()

    mip = frappe.new_doc("Material Issue Plan")
    mip.company, mip.posting_date = ctx.company, today()
    mip.production_plan = pp.name
    mip.excess_return_warehouse = ctx.warehouse
    mip.append("excess_return_items", {
        "item_code": item, "item_name": "Excess Partial Test Plate",
        "parent_item_group": "Plates", "unit_weight": UW,
        "length": 1000.0, "width": 500.0, "thickness": THICK,
        "sec_qty": 6, "qty": flt((1000/1000.0) * (500/1000.0) * THICK * UW * 6, 3),
        "uom": "Kg", "source_table": "Round Up Sec Qty for Transfer",
        "source_row": "ZZ-EXPART", "return_reason": "Partial-claim test off-cut",
    })
    mip.insert(ignore_permissions=True)
    frappe.db.commit()
    excess_row = mip.excess_return_items[0].name
    per_piece = flt(mip.excess_return_items[0].qty / 6, 3)
    print("off-cut: 6 pieces, %s Kg total, %s Kg each" % (mip.excess_return_items[0].qty, per_piece))

    def _mp():
        mp = frappe.new_doc("Material Planning")
        mp.company, mp.posting_date, mp.for_warehouse = ctx.company, today(), ctx.warehouse
        mp.append("material_mapping", {
            "item_code": item, "item_name": "Excess Partial Test Plate",
            "parent_item_group": "Plates", "unit_weight": UW,
            "length": 1000.0, "width": 500.0, "thickness": THICK,
            "qty": per_piece * 2, "uom": "Kg", "sec_qty": 2, "sec_uom": "Nos",
            "duno_mark_no": "DUNO-EXPART",
        })
        mp.insert(ignore_permissions=True)
        return mp

    print("\n=== claiming an off-cut in pieces ===")
    mp1, mp2 = _mp(), _mp()
    claim_virtual_excess_mapping(mp1.name, excess_row, row_name=mp1.material_mapping[0].name, sec_qty=2)
    a = excess_row_availability(excess_row)
    check("2 of 6 pieces claimed", flt(a["allocated_sec_qty"]) == 2, str(a["allocated_sec_qty"]))
    check("4 pieces still free", flt(a["available_sec_qty"]) == 4, str(a["available_sec_qty"]))

    mp1.reload()
    row1 = mp1.material_mapping[0]
    check("the row took only its share of the weight",
          abs(flt(row1.batch_calc_qty) - per_piece * 2) < 0.01, str(row1.batch_calc_qty))

    claim_virtual_excess_mapping(mp2.name, excess_row, row_name=mp2.material_mapping[0].name, sec_qty=3)
    a = excess_row_availability(excess_row)
    check("a second Material Planning takes 3 more", flt(a["allocated_sec_qty"]) == 5,
          str(a["allocated_sec_qty"]))
    check("1 piece remains", flt(a["available_sec_qty"]) == 1, str(a["available_sec_qty"]))

    print("\n=== limits ===")
    mp3 = _mp()
    ok, detail = _throws(
        lambda: claim_virtual_excess_mapping(mp3.name, excess_row,
                                             row_name=mp3.material_mapping[0].name, sec_qty=5),
        "still free")
    check("claiming more pieces than remain is refused", ok, detail)

    print("\n=== availability shows on the Excess Material Items row ===")
    d = frappe.get_doc("Material Issue Plan", mip.name)
    d.save(ignore_permissions=True)
    d.reload()
    er = d.excess_return_items[0]
    check("Allocated Sec Nos is displayed", flt(er.allocated_sec_qty) == 5, str(er.allocated_sec_qty))
    check("Available Sec Nos is displayed", flt(er.available_sec_qty) == 1, str(er.available_sec_qty))
    check("Available Kg is displayed", abs(flt(er.available_qty) - per_piece) < 0.01,
          str(er.available_qty))

    print("\n=== the picker offers only what is left ===")
    offered = [o for o in get_available_virtual_excess_items(mp3.name, item_code=item)
               if o["excess_row"] == excess_row]
    check("off-cut still offered while 1 piece remains", len(offered) == 1)
    check("it advertises 6 planned and 1 free",
          offered and flt(offered[0]["planned_sec_qty"]) == 6 and flt(offered[0]["available_sec_qty"]) == 1,
          "planned=%s free=%s" % (offered[0]["planned_sec_qty"], offered[0]["available_sec_qty"]) if offered else "")

    claim_virtual_excess_mapping(mp3.name, excess_row, row_name=mp3.material_mapping[0].name, sec_qty=1)
    offered = [o for o in get_available_virtual_excess_items(mp3.name, item_code=item)
               if o["excess_row"] == excess_row]
    check("once fully claimed it drops out of the picker", not offered)

    print("\n=== it comes back: every holder gets the batch ===")
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type, se.company, se.posting_date = "Material Receipt", ctx.company, today()
    se.append("items", {
        "item_code": item, "qty": flt(per_piece * 6, 3), "uom": "Kg",
        "t_warehouse": ctx.warehouse, "basic_rate": 50, "allow_zero_valuation_rate": 1,
        "custom_parent_item_group": "Plates", "custom_unit_weight": UW,
        "custom_length": 1000.0, "custom_width": 500.0, "custom_thickness": THICK,
        "custom_sec_qty": 6, "custom_source_mip_excess_row": excess_row,
    })
    se.insert(ignore_permissions=True)
    se.submit()
    batch_no = frappe.db.get_value("Batch", {"reference_doctype": "Stock Entry",
                                             "reference_name": se.name, "item": item}, "name")
    holders = frappe.get_all("Material Planning Material Mapping",
                             {"virtual_excess_source_row": excess_row},
                             ["name", "parent", "batch", "is_virtual_excess", "batch_mapped"])
    check("all three holders now point at the real batch",
          len(holders) == 3 and all(h.batch == batch_no for h in holders),
          str([(h.parent, h.batch) for h in holders]))
    check("none is virtual any more", all(not h.is_virtual_excess for h in holders))

    print("\n=== a batch with a Cut Sheet ticks Cut Sheet by itself ===")
    # A FRESH sheet. The batch above is now fully reserved by the three excess
    # holders, and _validate_batch_calc_qty rightly refuses to hand the same steel
    # to a Cut Sheet as well -- correct, but not what this section is testing.
    se2 = frappe.new_doc("Stock Entry")
    se2.stock_entry_type, se2.company, se2.posting_date = "Material Receipt", ctx.company, today()
    se2.append("items", {
        "item_code": item, "qty": flt((2000/1000.0) * (1000/1000.0) * THICK * UW, 3), "uom": "Kg",
        "t_warehouse": ctx.warehouse, "basic_rate": 50, "allow_zero_valuation_rate": 1,
        "custom_parent_item_group": "Plates", "custom_unit_weight": UW,
        "custom_length": 2000.0, "custom_width": 1000.0, "custom_thickness": THICK,
        "custom_sec_qty": 1,
    })
    se2.insert(ignore_permissions=True)
    se2.submit()
    cut_batch = frappe.db.get_value("Batch", {"reference_doctype": "Stock Entry",
                                              "reference_name": se2.name, "item": item}, "name")

    cs = frappe.new_doc("Cut Sheet")
    cs.company, cs.item_code, cs.batch_no, cs.warehouse = ctx.company, item, cut_batch, ctx.warehouse
    cs.w1_length, cs.w1_width, cs.w1_sec_qty = 500.0, 250.0, 4
    cs.w2_length, cs.w2_width, cs.w2_sec_qty = 1000.0, 100.0, 1
    cs.insert(ignore_permissions=True)

    mp4 = _mp()
    allocate_cut_sheet(mp4.name, cs.name, 2, row_name=mp4.material_mapping[0].name)
    mp4.reload()
    r = mp4.material_mapping[0]
    check("Cut Sheet is ticked automatically from the batch", r.cut_sheet == 1, str(r.cut_sheet))
    check("it names the sheet", r.cut_sheet_ref == cs.name, str(r.cut_sheet_ref))
    # 4 on the sheet, none held by anyone else, so this row could take all 4.
    check("free pieces are shown on the row", flt(r.cut_sheet_avail_sec_qty) == 4,
          str(r.cut_sheet_avail_sec_qty))

    # Over-asking is refused either way: a RESERVED row cannot have its quantity
    # changed at all (_validate_batch_calc_qty gets there first), and an unreserved
    # one is caught by the Cut Sheet check. Accept whichever fires -- both are the
    # protection this is testing.
    def _overask():
        d = frappe.get_doc("Material Planning", mp4.name)
        d.material_mapping[0].batch_sec_qty = 9
        d.save(ignore_permissions=True)
    ok_cs, detail = _throws(_overask, "piece(s) free")
    ok_reserved, detail2 = _throws(_overask, "already reserved")
    check("asking for more pieces than the sheet has free is refused",
          ok_cs or ok_reserved, detail if ok_cs else detail2)

    frappe.db.commit()
    print("\n=== SUMMARY ===")
    failed = [l for l, ok in RESULTS if not ok]
    print("FAILURES: %s" % failed if failed else "ALL %d CHECKS PASSED" % len(RESULTS))
    print("Test data left: %s %s %s %s %s %s" % (mip.name, mp1.name, mp2.name, mp3.name, mp4.name, cs.name))
