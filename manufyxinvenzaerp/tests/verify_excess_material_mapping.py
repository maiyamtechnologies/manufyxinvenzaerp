"""Verify Phase 2.3: Excess Material Return report + Excess Material Mapping.

1. Build a Material Issue Plan with one not-yet-returned excess row, confirm
   it shows under the report's default "Pending" filter.
2. Submit the excess-return Stock Entry (create_mip_excess_return_entry),
   confirm the row now shows under "Returned" and disappears from "Pending".
3. Build a SEPARATE Material Planning with an Unavailable Item row for the
   same item, confirm get_available_excess_batches() finds the recovered
   batch, then call add_excess_material_mapping() and confirm: a new
   Material Mapping row is added + reserved, and the Unavailable Item row is
   correctly shrunk by the amount consumed.

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_excess_material_mapping.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties
from frappe.utils import flt, today
from manufyxinvenzaerp.tests.create_full_test_entry import get_ctx, ensure_item


def run():
    ctx = get_ctx()
    item = ensure_item(ctx, "ZZTEST-EXCESS-MAP", "Excess Mapping Test Item", uom="Kg")
    frappe.db.set_value("Item", item, "custom_parent_item_group", "Structurals")
    frappe.db.set_value("Item", item, "custom_unit_weight", 10)
    frappe.db.set_value("Item", item, "create_new_batch", 1)
    frappe.db.set_value("Item", item, "custom_batch_prefix", "ZZEXCESS")

    bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1}, ["name", "item", "quantity"], as_dict=True)
    stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos"

    pp = frappe.new_doc("Production Plan")
    pp.custom_type = "Internal Job"
    pp.company = ctx.company
    pp.posting_date = today()
    pp.get_items_from = ""
    pp.append("po_items", {"item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1, "stock_uom": stock_uom})
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
    mip.append("excess_return_items", {
        "item_code": item, "parent_item_group": "Structurals",
        "length": 3000, "sec_qty": 1, "qty": 30, "uom": "Kg",
        "return_reason": "Off-cut recovered after operation (test)",
    })
    mip.insert(ignore_permissions=True)
    print("Created MIP:", mip.name)

    # 1. Pending filter should show this row.
    from manufyxinvenzaerp.subcontracting_management.report.excess_material_return_report.excess_material_return_report import execute as run_report

    _, pending_rows = run_report({"status": "Pending", "material_issue_plan": mip.name})
    print("Pending rows for this MIP (expect 1):", len(pending_rows))
    assert len(pending_rows) == 1
    assert pending_rows[0]["status"] == "Pending"

    _, returned_rows = run_report({"status": "Returned", "material_issue_plan": mip.name})
    print("Returned rows for this MIP before return (expect 0):", len(returned_rows))
    assert len(returned_rows) == 0

    # 2. Submit the excess-return Stock Entry.
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import create_mip_excess_return_entry

    se_name = create_mip_excess_return_entry(mip.name)
    se = frappe.get_doc("Stock Entry", se_name)
    for row in se.items:
        row.allow_zero_valuation_rate = 1
    se.save(ignore_permissions=True)
    se.submit()
    print("Created + submitted excess-return Stock Entry:", se_name)

    _, pending_rows = run_report({"status": "Pending", "material_issue_plan": mip.name})
    _, returned_rows = run_report({"status": "Returned", "material_issue_plan": mip.name})
    print("Pending rows after return (expect 0):", len(pending_rows))
    print("Returned rows after return (expect 1):", len(returned_rows))
    assert len(pending_rows) == 0
    assert len(returned_rows) == 1
    assert returned_rows[0]["status"] == "Returned"

    # Find the batch the excess-return SE created for this item.
    se.reload()
    print("SE custom_mip_ref:", se.custom_mip_ref, "| stock_entry_type:", se.stock_entry_type, "| docstatus:", se.docstatus)
    for r in se.items:
        print("  SE item:", r.item_code, "batch_no:", r.batch_no, "t_warehouse:", r.t_warehouse, "qty:", r.qty)
    batch_no = frappe.db.get_value("Batch", {"reference_doctype": "Stock Entry", "reference_name": se_name, "item": item}, "name")
    print("Recovered batch:", batch_no)
    assert batch_no, "Expected a batch to have been auto-created for the excess-return receipt"

    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import _get_batch_total_stock
    print("Batch total stock in", ctx.warehouse, ":", _get_batch_total_stock(batch_no, ctx.warehouse))

    # 3. Build a separate Material Planning needing this same item, with a
    # bigger requirement (40 Kg) than the recovered excess batch has (30 Kg),
    # so the shortfall behavior after mapping is also exercised.
    mp = frappe.new_doc("Material Planning")
    mp.company = ctx.company
    mp.posting_date = today()
    mp.for_warehouse = ctx.warehouse
    mp.append("unavailable_items", {
        "item_code": item, "item_name": "Excess Mapping Test Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "qty": 40, "uom": "Kg", "sec_qty": 4, "sec_uom": "Nos",
        "duno_mark_no": "DUNO-EXCESS-TEST",
    })
    mp.insert(ignore_permissions=True)
    print("Created MP:", mp.name)
    unavail_row_name = mp.unavailable_items[0].name

    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        get_available_excess_batches, add_excess_material_mapping,
    )

    available = get_available_excess_batches(mp.name, item_code=item)
    print("Available excess batches found:", available)
    match = next((b for b in available if b["batch_no"] == batch_no), None)
    assert match, "Expected the recovered batch to appear in get_available_excess_batches"
    assert flt(match["free_qty"]) == 30, f"Expected 30 Kg free, got {match['free_qty']}"

    result = add_excess_material_mapping(mp.name, batch_no, sec_qty=1, unavailable_item_row=unavail_row_name)
    print("add_excess_material_mapping result:", result)

    mp.reload()
    mm_rows = [r for r in mp.material_mapping if r.batch == batch_no]
    print("Material Mapping rows for this batch (expect 1):", len(mm_rows))
    assert len(mm_rows) == 1
    mm = mm_rows[0]
    print("New row: qty=", mm.qty, "is_reserved=", mm.is_reserved, "reserved_qty=", mm.reserved_qty,
          "duno_mark_no=", mm.duno_mark_no)
    assert flt(mm.qty) == 30, f"Expected the mapped row's Kg to be 30 (L=3000,UW=10,secqty=1), got {mm.qty}"
    assert mm.is_reserved, "New row should be reserved"
    assert flt(mm.reserved_qty) == 30
    assert mm.duno_mark_no == "DUNO-EXCESS-TEST", "Traceability should be copied from the linked Unavailable Item row"

    remaining_unavail = [r for r in mp.unavailable_items if r.name == unavail_row_name]
    print("Unavailable Item row remaining (expect 1, qty=10):", remaining_unavail[0].qty if remaining_unavail else "REMOVED")
    assert len(remaining_unavail) == 1, "Unavailable Item row should still exist (only partially covered: 40-30=10 remains)"
    assert flt(remaining_unavail[0].qty) == 10, f"Expected remaining shortfall of 10 Kg, got {remaining_unavail[0].qty}"

    frappe.db.commit()
    print("\nALL CHECKS DONE — report correctly tracks Pending/Returned, and Excess Material "
          "Mapping correctly finds + reserves the recovered batch and shrinks the Unavailable Item row.")
    print("Test data left in place:", pp.name, mip.name, se_name, mp.name, batch_no)
