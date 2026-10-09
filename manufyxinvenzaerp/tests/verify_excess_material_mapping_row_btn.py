"""Verify three things together:

1. Bug fix: Material Planning Available Raw Material carries no unit_weight
   field of its own, so refresh_mip_raw_materials previously left every
   ARM-sourced raw_materials row (and anything derived from it, e.g. Excess
   Calc Qty) stuck at unit_weight=0/qty=0. Now it's looked up from the Item
   master directly.

2. Bug fix: _sync_excess_return_from_raw_materials used to key its
   find-or-create against excess_return_items by the MIP's own raw_materials
   row name -- but that name is regenerated (fresh row) on every
   refresh_mip_raw_materials call, so calling refresh twice while a row was
   still pending (not yet returned to stock) silently duplicated its
   excess_return_items entry. Fixed to key on (source_table, source_row) --
   the stable reference back to the underlying Material Planning row.

3. New feature: a per-row "Excess Material Mapping" button on Material
   Planning Material Mapping reserves a recovered excess-return batch
   straight into an EXISTING row (via reassign_batch), and marks the source
   SCO Excess Material Item row with where it ended up
   (mapped_material_planning / mapped_row_name).

Scenario for (1)+(2): identical setup to verify_mip_post_purchase_refresh.py
(item starts as an Unavailable Item, gets purchased via MR->PO->PR, PR submit
auto-allocates it into Available Raw Materials with a real batch) -- proven
to correctly produce an ARM-sourced raw_materials row. Flag that row's Excess
Return Applicable, refresh twice before returning it, then create + submit
the real excess-return Stock Entry.

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_excess_material_mapping_row_btn.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties
from frappe.utils import flt, today

from manufyxinvenzaerp.tests.create_full_test_entry import get_ctx, ensure_item
from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
    refresh_mip_raw_materials,
)
from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
    create_mip_excess_return_entry,
)
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    reassign_batch,
)


def run():
    ctx = get_ctx()
    item = ensure_item(ctx, "ZZTEST-EXCESSBTN", "Excess Mapping Row Button Test Item", uom="Kg")
    frappe.db.set_value("Item", item, "custom_parent_item_group", "Structurals")
    frappe.db.set_value("Item", item, "custom_unit_weight", 10)
    frappe.db.set_value("Item", item, "create_new_batch", 1)
    frappe.db.set_value("Item", item, "custom_batch_prefix", "ZZEXCESSBTN")

    bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1}, ["name", "item", "quantity"], as_dict=True)
    stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos"

    # --- MP #1: needs this item, currently unavailable (not yet purchased) ---
    mp1 = frappe.new_doc("Material Planning")
    mp1.company = ctx.company
    mp1.posting_date = today()
    mp1.for_warehouse = ctx.warehouse
    mp1.append("unavailable_items", {
        "item_code": item, "item_name": "Excess Mapping Row Button Test Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "qty": 50, "uom": "Kg", "sec_qty": 1, "sec_uom": "Nos",
        "duno_mark_no": "DUNO-EXBTN-1",
        # Must match the purchased length below. Allocation routes a receipt to
        # Available Raw Materials only on an exact dimension match, and sends
        # anything else to Material Mapping -- a requirement with no length at all
        # can never be an exact match, which is what this test needs it to be.
        "length": 5000,
    })
    mp1.insert(ignore_permissions=True)
    print("Created MP1:", mp1.name)

    pp = frappe.new_doc("Production Plan")
    pp.custom_type = "Internal Job"
    pp.company = ctx.company
    pp.posting_date = today()
    pp.get_items_from = ""
    pp.append("po_items", {
        "item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1,
        "stock_uom": stock_uom, "custom_material_planning": mp1.name,
    })
    pp.append("custom_process_planning", {"operation_name": "Material Issue", "work_type": "Internal Jobcard"})
    pp.insert(ignore_permissions=True)
    fill_process_planning_parties(pp)
    pp.submit()
    print("Created Production Plan:", pp.name)

    mip = frappe.new_doc("Material Issue Plan")
    mip.company = ctx.company
    mip.posting_date = today()
    mip.production_plan = pp.name
    mip.excess_return_warehouse = ctx.warehouse
    mip.insert(ignore_permissions=True)

    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        populate_from_production_plan,
    )
    populate_from_production_plan(mip.name)
    print("Populated MIP:", mip.name)

    # Purchase it: MR (tagged to MP1) -> PO -> PR, submit PR -- auto-allocates
    # into Available Raw Materials with a real batch, and refreshes this MIP.
    mr = frappe.new_doc("Material Request")
    mr.material_request_type = "Purchase"
    mr.company = ctx.company
    mr.transaction_date = today()
    mr.schedule_date = today()
    mr.custom_material_planning = mp1.name
    mr.append("items", {
        "item_code": item, "qty": 50, "uom": "Kg", "schedule_date": today(),
        "warehouse": ctx.warehouse, "custom_parent_item_group": "Structurals",
        "custom_unit_weight": 10, "custom_length": 5000, "custom_sec_qty": 1,
    })
    mr.insert(ignore_permissions=True)
    mr.submit()

    # Skip any demo Supplier whose represents_company points at a Company that no
    # longer exists -- an arbitrary get_value can land on one and fail the PO with a
    # link error that has nothing to do with what this test covers.
    supplier = frappe.db.get_value("Supplier", {"represents_company": ["in", ["", None]]}, "name")
    from erpnext.stock.doctype.material_request.material_request import make_purchase_order
    po = make_purchase_order(mr.name)
    po.supplier = supplier
    for row in po.items:
        row.rate = 80
    po.insert(ignore_permissions=True)
    po.submit()

    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
    pr = make_purchase_receipt(po.name)
    for row in pr.items:
        row.allow_zero_valuation_rate = 1
        row.use_serial_batch_fields = 1
    pr.insert(ignore_permissions=True)
    pr.submit()
    print("Purchased via MR/PO/PR:", mr.name, po.name, pr.name)

    mip.reload()
    row = next(r for r in mip.raw_materials if r.item_code == item)
    print("raw_materials source_table:", row.source_table, "| unit_weight (expect 10, was the ARM-source bug):", row.unit_weight)
    assert row.source_table == "Material Planning Available Raw Material"
    assert flt(row.unit_weight) == 10, f"unit_weight bug not fixed, got {row.unit_weight}"

    # Booked straight into the Excess Material Items table -- the raw-material row's
    # own Excess Return fields are gone, along with the sync that copied them over.
    mip.append("excess_return_items", {
        "item_code": item,
        "parent_item_group": row.parent_item_group,
        "unit_weight": row.unit_weight,
        "length": 2000, "width": 0, "thickness": row.thickness,
        "sec_qty": 1, "qty": 20,
        "source_table": row.source_table, "source_row": row.source_row,
        "source_mip_raw_material_row": row.name,
    })
    mip.save(ignore_permissions=True)
    mip.reload()
    excess_row = next(r for r in mip.excess_return_items if r.item_code == item)
    print("excess_calc_qty (expect 20 = 2*10*1):", excess_row.qty, "| source_table:", excess_row.source_table)
    assert flt(excess_row.qty) == 20
    assert excess_row.source_table == "Material Planning Available Raw Material"

    # Return Reason lives on the excess_return_items row itself (SCO Excess
    # Material Item), not on the raw_materials row.
    excess_row.return_reason = "Test off-cut"
    mip.save(ignore_permissions=True)
    mip.reload()
    frappe.db.commit()

    # --- Duplication regression: refresh raw materials twice while the excess
    # row is still pending (not yet returned to stock) -- must NOT duplicate.
    refresh_mip_raw_materials(mip.name)
    refresh_mip_raw_materials(mip.name)
    mip.reload()
    matching = [r for r in mip.excess_return_items if r.item_code == item]
    print(f"excess_return_items rows for {item} after 2 extra refreshes (expect 1):", len(matching))
    assert len(matching) == 1, f"Duplication bug not fixed -- found {len(matching)} rows"
    frappe.db.commit()

    # --- Create + submit the real excess-return Stock Entry ---
    se_name = create_mip_excess_return_entry(mip.name)
    se = frappe.get_doc("Stock Entry", se_name)
    if se.docstatus == 0:
        se.submit()
    print("Created + submitted excess-return Stock Entry:", se_name)

    batch_no = frappe.db.get_value(
        "Batch", {"reference_doctype": "Stock Entry", "reference_name": se_name, "item": item}, "name"
    )
    print("Recovered batch:", batch_no)
    assert batch_no, "No batch created from the excess-return Stock Entry"
    src_excess_row = frappe.db.get_value("Batch", batch_no, "custom_source_mip_excess_row")
    print("Batch's custom_source_mip_excess_row:", src_excess_row)
    assert src_excess_row, "custom_source_mip_excess_row not copied onto the new batch"

    # Refresh again post-return -- must still not duplicate (now completed).
    refresh_mip_raw_materials(mip.name)
    mip.reload()
    matching = [r for r in mip.excess_return_items if r.item_code == item]
    print(f"excess_return_items rows for {item} after a post-return refresh (expect 1):", len(matching))
    assert len(matching) == 1
    frappe.db.commit()

    # --- MP #2: a genuinely separate Material Planning needing the SAME item,
    # with an existing (unreserved) Material Mapping row -- the new per-row
    # Excess Material Mapping button's target.
    mp2 = frappe.new_doc("Material Planning")
    mp2.company = ctx.company
    mp2.posting_date = today()
    mp2.for_warehouse = ctx.warehouse
    mp2.append("material_mapping", {
        "item_code": item, "item_name": "Excess Mapping Row Button Test Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "qty": 20, "uom": "Kg", "sec_qty": 1, "sec_uom": "Nos",
        "length": 2000, "duno_mark_no": "DUNO-EXBTN-2",
    })
    mp2.insert(ignore_permissions=True)
    print("Created MP2 (has the target Material Mapping row):", mp2.name)

    target_row = mp2.material_mapping[0]
    result = reassign_batch(
        material_planning_name=mp2.name,
        source_table="Material Planning Material Mapping",
        row_name=target_row.name,
        new_batch_no=batch_no,
        sec_qty=1,
    )
    print("reassign_batch result:", result)

    mp2.reload()
    row2 = mp2.material_mapping[0]
    print("MP2 row after reassign -- batch:", row2.batch, "| is_reserved:", row2.is_reserved,
          "| batch_calc_qty:", row2.batch_calc_qty)
    assert row2.batch == batch_no
    assert row2.is_reserved == 1

    excess_doc = frappe.get_doc("SCO Excess Material Item", src_excess_row)
    print("Source excess row after mapping -- mapped_material_planning:", excess_doc.mapped_material_planning,
          "| mapped_row_name:", excess_doc.mapped_row_name)
    assert excess_doc.mapped_material_planning == mp2.name
    assert excess_doc.mapped_row_name == row2.name

    frappe.db.commit()
    print("\nALL CHECKS DONE — unit_weight bug fixed, excess_return_items no longer duplicates across "
          "refreshes, and the per-row Excess Material Mapping button correctly reserves an existing "
          "row while marking the source excess item with where it ended up.")
    print("Test data left in place:", mp1.name, pp.name, mip.name, se_name, mp2.name)
