"""Verify Phase 5.4: a consolidated purchase's sequential allocation (Phase
2.5, already covered on the Material Planning side by
verify_pr_sequential_allocation.py) surfaces correctly in a linked Material
Issue Plan's raw_materials tab -- no new code, just confirming the existing
refresh_mip_raw_materials mechanism (Phase 5.1) already reads every row of
every linked Material Planning's own child tables regardless of DUNO/Mark No,
so a split that lands across two originally-separate Unavailable Item rows
(DUNO-A fully covered, DUNO-B partially covered) both show up on the MIP.

Scenario: identical to verify_pr_sequential_allocation.py (item needed by
DUNO-A: 50 Kg + DUNO-B: 30 Kg, consolidated into one Consolidate Item row,
purchased as one PO/PR line, only 60 Kg actually received -- DUNO-A fully
covered, DUNO-B partially covered with a 20 Kg shortfall remaining) but this
Material Planning is also linked to a Production Plan -> SCO -> Material
Issue Plan, and the MIP is refreshed after the PR submits.

Verifies:
  1. MIP raw_materials contains a DUNO-A row sourced from Available Raw
     Material with qty 50 (fully covered).
  2. MIP raw_materials contains a DUNO-B row sourced from Available Raw
     Material with qty 10 (partial) AND a separate DUNO-B row still sourced
     from Unavailable Item with qty 20 (remaining shortfall) -- both present,
     neither dropped nor double-counted.

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_mip_consolidated_allocation.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties
from frappe.utils import flt, today
from manufyxinvenzaerp.tests.create_full_test_entry import get_ctx, ensure_item, ensure_batch


def run():
    ctx = get_ctx()
    item = ensure_item(ctx, "ZZTEST-MIP-CONSOL", "MIP Consolidated Allocation Test Item", uom="Kg")
    frappe.db.set_value("Item", item, "custom_parent_item_group", "Structurals")
    frappe.db.set_value("Item", item, "custom_unit_weight", 10)

    mp = frappe.new_doc("Material Planning")
    mp.company = ctx.company
    mp.posting_date = today()
    mp.for_warehouse = ctx.warehouse
    mp.append("unavailable_items", {
        "item_code": item, "item_name": "MIP Consolidated Allocation Test Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "qty": 50, "uom": "Kg", "sec_qty": 1, "sec_uom": "Nos",
        "duno_mark_no": "DUNO-A",
    })
    mp.append("unavailable_items", {
        "item_code": item, "item_name": "MIP Consolidated Allocation Test Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "qty": 30, "uom": "Kg", "sec_qty": 1, "sec_uom": "Nos",
        "duno_mark_no": "DUNO-B",
    })
    mp.insert(ignore_permissions=True)
    print("Created test MP:", mp.name)

    mp.reload()
    consol_row = next(r for r in mp.consolidate_items if r.item_code == item)
    consol_row.length = 8000
    consol_row.sec_qty = 1
    mp.save(ignore_permissions=True)
    mp.reload()

    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        make_material_request_from_consolidate,
    )
    import json as _json

    mr_name = make_material_request_from_consolidate(mp.name, _json.dumps([item]))
    mr = frappe.get_doc("Material Request", mr_name)
    mr.submit()
    print("Created + submitted MR:", mr_name)

    from erpnext.stock.doctype.material_request.material_request import make_purchase_order

    supplier = frappe.db.get_value("Supplier", {}, "name")
    if not supplier:
        frappe.throw("No supplier found in DB — create one first")

    po = make_purchase_order(mr_name)
    po.supplier = supplier
    for row in po.items:
        row.rate = 80
    po.insert(ignore_permissions=True)
    po.submit()
    print("Created + submitted PO:", po.name)

    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

    pr = make_purchase_receipt(po.name)
    pr.items[0].custom_sec_qty = 0.75  # (8000/1000)*10*0.75 = 60 Kg
    pr.items[0].qty = 60
    pr.items[0].received_qty = 60
    pr.items[0].accepted_qty = 60
    pr.items[0].rejected_qty = 0
    batch_no = ensure_batch(item, "ZZTEST-MIP-CONSOL-BATCH-1", L=8000, sec_qty=0.75)
    pr.items[0].use_serial_batch_fields = 1
    pr.items[0].batch_no = batch_no
    pr.insert(ignore_permissions=True)

    # Link this Material Planning to a real Production Plan -> SCO -> Material
    # Issue Plan BEFORE the PR submits, so the MIP already exists when
    # allocate_pr_stock_to_mp (triggered by PR submit) calls refresh_mip_raw_materials.
    bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1}, ["name", "item", "quantity"], as_dict=True)
    stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos"

    pp = frappe.new_doc("Production Plan")
    pp.custom_type = "Internal Job"
    pp.company = ctx.company
    pp.posting_date = today()
    pp.get_items_from = ""
    pp.append("po_items", {
        "item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1,
        "stock_uom": stock_uom, "custom_material_planning": mp.name,
    })
    pp.append("custom_process_planning", {"operation_name": "Material Issue", "work_type": "Internal Jobcard"})
    pp.insert(ignore_permissions=True)
    fill_process_planning_parties(pp)
    pp.submit()
    print("Created Production Plan:", pp.name)

    from manufyxinvenzaerp.subcontracting_management.subcontracting import create_sco_from_production_plan
    sco_name = create_sco_from_production_plan(pp.name)
    print("Created SCO:", sco_name)

    mip = frappe.new_doc("Material Issue Plan")
    mip.company = ctx.company
    mip.posting_date = today()
    mip.production_plan = pp.name
    mip.subcontracting_order = sco_name
    mip.source_warehouse = ctx.warehouse
    mip.insert(ignore_permissions=True)
    mip.reload()  # after_insert's populate_from_production_plan modifies the DB copy, not this in-memory one
    print("Populated MIP (pre-PR-submit):", mip.name)

    pre_rows = {(r.duno_mark_no, r.source_table): r for r in mip.raw_materials}
    print("MIP raw_materials before PR submit:", [(k, v.qty) for k, v in pre_rows.items()])
    assert ("DUNO-A", "Material Planning Unavailable Item") in pre_rows
    assert ("DUNO-B", "Material Planning Unavailable Item") in pre_rows

    pr.submit()
    print("Submitted PR:", pr.name, "-- this triggers allocate_pr_stock_to_mp -> refresh_mip_raw_materials")

    mip.reload()
    post_rows = {(r.duno_mark_no, r.source_table): r for r in mip.raw_materials}
    print("MIP raw_materials after PR submit:", [(k, flt(v.qty)) for k, v in post_rows.items()])

    key_a_arm = ("DUNO-A", "Material Planning Available Raw Material")
    key_b_arm = ("DUNO-B", "Material Planning Available Raw Material")
    key_b_unavail = ("DUNO-B", "Material Planning Unavailable Item")

    assert key_a_arm in post_rows, "DUNO-A should now show as an Available Raw Material row on the MIP"
    assert flt(post_rows[key_a_arm].qty) == 50, f"DUNO-A should be fully covered at 50 Kg, got {post_rows[key_a_arm].qty}"
    assert ("DUNO-A", "Material Planning Unavailable Item") not in post_rows, "DUNO-A should no longer appear as Unavailable on the MIP"

    assert key_b_arm in post_rows, "DUNO-B should show a partial Available Raw Material row on the MIP"
    assert flt(post_rows[key_b_arm].qty) == 10, f"DUNO-B's partial coverage should be 10 Kg, got {post_rows[key_b_arm].qty}"
    assert key_b_unavail in post_rows, "DUNO-B should still show its remaining shortfall as Unavailable on the MIP"
    assert flt(post_rows[key_b_unavail].qty) == 20, f"DUNO-B's remaining shortfall should be 20 Kg, got {post_rows[key_b_unavail].qty}"

    frappe.db.commit()
    print("\nALL CHECKS DONE — the consolidated purchase's sequential split (DUNO-A fully covered, "
          "DUNO-B partially covered with a 20 Kg shortfall) correctly surfaced on the linked Material "
          "Issue Plan's raw_materials tab via the existing refresh mechanism -- no new code needed.")
    print("Test data left in place:", mp.name, mr_name, po.name, pr.name, pp.name, sco_name, mip.name)
