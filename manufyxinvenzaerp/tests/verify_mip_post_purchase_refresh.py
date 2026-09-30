"""Verify Phase 5.1: Material Issue Plan's raw-material snapshot correctly
picks up material that was still UNAVAILABLE (not yet purchased) at the time
the MIP was first populated, once it's later purchased and allocated.

Scenario:
  1. Material Planning has one Unavailable Item (not yet purchased).
  2. Material Issue Plan is populated from a Production Plan whose item links
     to that Material Planning -- its raw_materials snapshot should show the
     item as unavailable (is_unavailable=1), since nothing has been bought yet.
  3. The item is then purchased (MR -> PO -> PR, PR submitted) -- submitting
     the PR auto-allocates into the Material Planning AND (per
     on_submit_purchase_receipt) refreshes every MIP whose drawing_items
     reference that Material Planning.
  4. Reload the MIP: its raw_materials snapshot should now show the SAME item
     as available (is_unavailable=0) with a real batch and qty -- proving the
     refresh correctly covers material that was unpurchased at MIP creation
     time, not just material that was already available then.

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_mip_post_purchase_refresh.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties
from frappe.utils import flt, today
from manufyxinvenzaerp.tests.create_full_test_entry import get_ctx, ensure_item


def run():
    ctx = get_ctx()
    item = ensure_item(ctx, "ZZTEST-MIP-REFRESH", "MIP Post-Purchase Refresh Test Item", uom="Kg")
    frappe.db.set_value("Item", item, "custom_parent_item_group", "Structurals")
    frappe.db.set_value("Item", item, "custom_unit_weight", 10)
    frappe.db.set_value("Item", item, "create_new_batch", 1)
    frappe.db.set_value("Item", item, "custom_batch_prefix", "ZZMIPREFRESH")

    bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1}, ["name", "item", "quantity"], as_dict=True)
    stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos"

    # 1. Material Planning with one Unavailable Item -- not yet purchased.
    mp = frappe.new_doc("Material Planning")
    mp.company = ctx.company
    mp.posting_date = today()
    mp.for_warehouse = ctx.warehouse
    mp.append("unavailable_items", {
        "item_code": item, "item_name": "MIP Post-Purchase Refresh Test Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "qty": 50, "uom": "Kg", "sec_qty": 1, "sec_uom": "Nos",
        "duno_mark_no": "DUNO-MIP-REFRESH",
    })
    mp.insert(ignore_permissions=True)
    print("Created MP:", mp.name)

    # 2. Production Plan whose item links to this Material Planning.
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

    # 3. Populate the MIP -- should show the item as unavailable right away.
    mip = frappe.new_doc("Material Issue Plan")
    mip.company = ctx.company
    mip.posting_date = today()
    mip.production_plan = pp.name
    mip.insert(ignore_permissions=True)

    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        populate_from_production_plan,
    )
    populate_from_production_plan(mip.name)
    print("Populated MIP:", mip.name)

    mip.reload()
    rows = [r for r in mip.raw_materials if r.item_code == item]
    print("raw_materials rows for item before purchase:", len(rows))
    assert len(rows) == 1, f"Expected exactly 1 raw_materials row before purchase, got {len(rows)}"
    assert rows[0].is_unavailable == 1, "Item should show as unavailable before any purchase"
    assert not rows[0].batch_no, "No batch should be assigned yet"
    print("  is_unavailable:", rows[0].is_unavailable, "| qty:", rows[0].qty, "| batch_no:", rows[0].batch_no)

    # 4. Purchase it: MR (tagged to this MP) -> PO -> PR, submit PR.
    mr = frappe.new_doc("Material Request")
    mr.material_request_type = "Purchase"
    mr.company = ctx.company
    mr.transaction_date = today()
    mr.schedule_date = today()
    mr.custom_material_planning = mp.name
    mr.append("items", {
        "item_code": item, "qty": 50, "uom": "Kg", "schedule_date": today(),
        "warehouse": ctx.warehouse, "custom_parent_item_group": "Structurals",
        "custom_unit_weight": 10, "custom_length": 5000, "custom_sec_qty": 1,
    })
    mr.insert(ignore_permissions=True)
    mr.submit()
    print("Created + submitted MR:", mr.name)

    supplier = frappe.db.get_value("Supplier", {}, "name")
    from erpnext.stock.doctype.material_request.material_request import make_purchase_order
    po = make_purchase_order(mr.name)
    po.supplier = supplier
    for row in po.items:
        row.rate = 80
    po.insert(ignore_permissions=True)
    po.submit()
    print("Created + submitted PO:", po.name)

    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
    pr = make_purchase_receipt(po.name)
    for row in pr.items:
        row.allow_zero_valuation_rate = 1
        row.use_serial_batch_fields = 1
    pr.insert(ignore_permissions=True)
    pr.submit()
    print("Created + submitted PR:", pr.name)

    # 5. Reload the MIP -- refresh_mip_raw_materials should have already run
    # automatically via on_submit_purchase_receipt.
    mip.reload()
    rows = [r for r in mip.raw_materials if r.item_code == item]
    print("raw_materials rows for item after purchase:", len(rows))
    for r in rows:
        print("  source_table:", r.source_table, "| is_unavailable:", r.is_unavailable,
              "| qty:", r.qty, "| batch_no:", r.batch_no)

    assert len(rows) == 1, f"Expected exactly 1 raw_materials row after purchase (replaced, not duplicated), got {len(rows)}"
    assert rows[0].is_unavailable == 0, "Item should now show as available after purchase"
    assert rows[0].batch_no, "A real batch should now be assigned"
    assert flt(rows[0].qty) == 50, f"Expected qty=50 Kg, got {rows[0].qty}"
    assert rows[0].source_table == "Material Planning Available Raw Material"

    frappe.db.commit()
    print("\nALL CHECKS DONE — MIP raw_materials correctly refreshed from 'unavailable' to "
          "'available with real batch' after the underlying Material Planning was purchased, "
          "even though the item was NOT yet purchased at the time the MIP was first populated.")
    print("Test data left in place:", mp.name, pp.name, mip.name, mr.name, po.name, pr.name)
