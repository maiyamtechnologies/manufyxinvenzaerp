"""Build one complete job and walk it through the whole chain, for real.

transfer 1,000 -> FG uses 500 -> return 300 -> process loss 200.

Uses ZZTEST fixtures only. The return and process-loss endpoints commit
internally (deadlock avoidance), so this cannot be rolled back -- it deliberately
leaves a sample job behind.
"""

import frappe
from frappe.utils import flt, today

ITEM = "ZZTEST-LOSS"
TAG = frappe.generate_hash(length=5).upper()


def _wh(name, company, abbr):
    full = "%s - %s" % (name, abbr)
    if not frappe.db.exists("Warehouse", full):
        frappe.get_doc({"doctype": "Warehouse", "warehouse_name": name,
                        "company": company, "is_group": 0}).insert(ignore_permissions=True)
    return full


def run():
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _job_stock_at_supplier, get_mip_process_loss_state,
        create_mip_excess_return_entry, create_mip_process_loss_entry,
    )

    company = frappe.db.get_value("Company", {}, "name")
    abbr = frappe.db.get_value("Company", company, "abbr")
    src = _wh("ZZTEST Stores", company, abbr)
    supplier_wh = _wh("ZZTEST Supplier", company, abbr)
    return_wh = _wh("ZZTEST Returns", company, abbr)

    # ── item + batch with 1,000 Kg in stores ────────────────────────────────
    if not frappe.db.exists("Item", ITEM):
        frappe.get_doc({
            "doctype": "Item", "item_code": ITEM, "item_name": "Process Loss Test",
            "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
            "stock_uom": "Kg", "is_stock_item": 1, "has_batch_no": 1, "create_new_batch": 0,
            "gst_hsn_code": frappe.db.get_value("GST HSN Code", {}, "name"),
            "custom_parent_item_group": "Structurals", "custom_unit_weight": 10,
            "custom_batch_prefix": "ZZLOSS", "custom_batch_abbreviation": "ZZL",
        }).insert(ignore_permissions=True)

    fg_item = "ZZTEST-LOSS-FG"
    if not frappe.db.exists("Item", fg_item):
        frappe.get_doc({
            "doctype": "Item", "item_code": fg_item, "item_name": "Process Loss FG",
            "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
            "stock_uom": "Nos", "is_stock_item": 1, "has_batch_no": 0,
            "gst_hsn_code": frappe.db.get_value("GST HSN Code", {}, "name"),
        }).insert(ignore_permissions=True)

    batch = "ZZTEST-LOSS-%s" % TAG
    frappe.get_doc({"doctype": "Batch", "batch_id": batch, "item": ITEM,
                    "custom_length": 10000, "custom_sec_qty": 10}).insert(ignore_permissions=True)

    receipt = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": company,
        "items": [{"item_code": ITEM, "qty": 1000, "uom": "Kg", "t_warehouse": src,
                   "batch_no": batch, "use_serial_batch_fields": 1, "basic_rate": 50}],
    })
    receipt.insert(ignore_permissions=True); receipt.submit()
    print("1. received 1,000 Kg into %s as batch %s" % (src, batch))

    # ── an SCO to hang the job on ───────────────────────────────────────────
    # An order with no plan of its own yet -- one Material Issue Plan per order.
    sco = frappe.db.sql("""
        SELECT sco.name FROM `tabSubcontracting Order` sco
        LEFT JOIN `tabMaterial Issue Plan` m ON m.subcontracting_order = sco.name
        WHERE m.name IS NULL AND sco.custom_production_plan IS NOT NULL
        ORDER BY sco.creation DESC LIMIT 1""")
    sco = sco[0][0] if sco else None
    if not sco:
        print("   (no submitted job work order on this site -- cannot continue)")
        return

    # production_plan is mandatory; take the SCO's own. The plan is then forced back
    # onto ZZTEST warehouses, because after_insert repopulates from that plan.
    mip = frappe.new_doc("Material Issue Plan")
    mip.company = company
    mip.subcontracting_order = sco
    mip.production_plan = frappe.db.get_value("Subcontracting Order", sco, "custom_production_plan")
    mip.insert(ignore_permissions=True)
    mip.reload()
    mip.source_warehouse = src
    mip.supplier_warehouse = supplier_wh
    mip.excess_return_warehouse = return_wh
    mip.flags.mfx_saved_by_another_document = True
    mip.save(ignore_permissions=True)
    print("2. plan %s created (supplier=%s)" % (mip.name, supplier_wh))

    # ── transfer 1,000 Kg to the supplier ───────────────────────────────────
    xfer = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": "Material Transfer", "company": company,
        "custom_sco_ref": sco, "custom_mip_ref": mip.name,
        "items": [{"item_code": ITEM, "qty": 1000, "uom": "Kg", "s_warehouse": src,
                   "t_warehouse": supplier_wh, "batch_no": batch, "use_serial_batch_fields": 1}],
    })
    xfer.insert(ignore_permissions=True); xfer.submit()
    print("3. transferred 1,000 Kg to the supplier (%s)" % xfer.name)
    print("   at supplier now: %.3f" % flt(sum(_job_stock_at_supplier(mip).values()), 3))

    # ── the job uses 500 ────────────────────────────────────────────────────
    fg = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": "Manufacture", "company": company,
        "subcontracting_order": sco,
        "items": [
            {"item_code": ITEM, "qty": 500, "uom": "Kg", "s_warehouse": supplier_wh,
             "batch_no": batch, "use_serial_batch_fields": 1},
            {"item_code": fg_item, "qty": 1, "uom": "Nos", "t_warehouse": return_wh,
             "is_finished_item": 1, "basic_rate": 100},
        ],
    })
    fg.insert(ignore_permissions=True); fg.submit()
    print("4. final stock entry consumed 500 Kg (%s)" % fg.name)
    print("   at supplier now: %.3f" % flt(sum(_job_stock_at_supplier(mip).values()), 3))

    # ── declare 300 to return, and return it ────────────────────────────────
    mip.reload()
    mip.append("excess_return_items", {
        "item_code": ITEM, "item_name": ITEM, "parent_item_group": "Structurals",
        "unit_weight": 10, "length": 3000, "sec_qty": 10, "qty": 300, "uom": "Kg",
        "return_reason": "off-cut", "return_warehouse": return_wh,
        "source_table": "Round Up Sec Qty for Transfer", "source_row": "ZZ-%s" % TAG,
    })
    mip.flags.mfx_saved_by_another_document = True
    mip.save(ignore_permissions=True)

    ret = create_mip_excess_return_entry(mip.name)
    ret_doc = frappe.get_doc("Stock Entry", ret)
    print("5. return entry %s type=%s" % (ret, ret_doc.stock_entry_type))
    for r in ret_doc.items:
        print("     %-14s %8.3f  %s -> %s" % (r.item_code, flt(r.qty),
              r.s_warehouse or "(none)", r.t_warehouse or "(none)"))
    ret_doc.submit()
    print("   at supplier now: %.3f" % flt(sum(_job_stock_at_supplier(frappe.get_doc('Material Issue Plan', mip.name)).values()), 3))

    # ── what is left ────────────────────────────────────────────────────────
    s = get_mip_process_loss_state(mip.name)
    print("6. process loss state: transferred=%s used=%s returned=%s remaining=%s over_threshold=%s"
          % (s["transferred"], s["used_in_fg"], s["returned"], s["remaining"], s["over_threshold"]))

    out = create_mip_process_loss_entry(mip.name, "supplier confirms cutting loss")
    loss_doc = frappe.get_doc("Stock Entry", out["stock_entry"])
    print("7. process loss %s type=%s qty=%.3f" % (
        out["stock_entry"], loss_doc.stock_entry_type,
        flt(sum(flt(i.qty) for i in loss_doc.items))))
    loss_doc.submit()

    final = frappe.get_doc("Material Issue Plan", mip.name)
    print("8. final: transferred=%s used=%s returned=%s loss=%s  | left at supplier=%.3f | status=%s"
          % (final.transferred_weight_kg, final.used_in_fg_weight_kg,
             final.returned_weight_kg, final.process_loss_weight_kg,
             flt(sum(_job_stock_at_supplier(final).values()), 3), final.status))
    print("   SAMPLE MIP:", mip.name)
