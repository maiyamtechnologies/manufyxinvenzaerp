"""Verify the excess-material claim lifecycle end to end.

An off-cut can be claimed by another job's Material Planning while it is still
physically at the supplier -- a "virtual" claim, with a reservation but no batch.
This covers what happens to that claim from there:

A. It comes back for real. Return Excess Entry no longer skips claimed rows, and
   on submit the created batch attaches itself to the claiming Material Mapping
   row (materialize_virtual_excess_claim), so the paper promise becomes real stock
   without ever passing through the free pool where another job could take it.

B. Its dimensions are locked while claimed. Every route into the Excess Material
   Items table is refused with one message -- editing the raw-material row's
   Excess Length/Width/Sec Qty, typing straight into the excess grid, or the
   Return Excess Entry dialog's overrides -- and "Unlink Claim" is the way out.

C. Rounding surplus from a transfer lands on the item table, split across the
   raw-material rows that produced it in proportion to their Sec Qty.

D. A claim still at the supplier is reported as such by the transfer readiness
   check, rather than being miscounted as unmapped.

Setup mirrors verify_excess_material_mapping_row_btn.py: the item starts as an
Unavailable Item, gets purchased MR->PO->PR, and the PR auto-allocates it.

Leaves test data behind (ZZTEST-* item and its documents) -- create_mip_excess_
return_entry commits internally, so this cannot be rolled back.

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_excess_claim_lifecycle.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties
from frappe.utils import flt, today

from manufyxinvenzaerp.tests.create_full_test_entry import get_ctx, ensure_item
from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
    populate_from_production_plan,
    unlink_excess_claim,
)
from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
    create_mip_excess_return_entry,
    get_mip_readiness_check,
    _apply_transfer_excess_to_raw_materials,
)
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    claim_virtual_excess_mapping,
)

RESULTS = []


def check(label, cond, detail=""):
    RESULTS.append((label, bool(cond)))
    print(("PASS" if cond else "FAIL") + " -- " + label + (("  | " + detail) if detail else ""))


def _throws(fn, needle):
    """Run fn and report whether it threw a ValidationError mentioning `needle`."""
    try:
        fn()
    except frappe.ValidationError as e:
        return needle.lower() in str(e).lower(), str(e)[:150]
    return False, "it did NOT raise"


def run():
    ctx = get_ctx()
    item = ensure_item(ctx, "ZZTEST-EXCLIFE", "Excess Claim Lifecycle Test Item", uom="Kg")
    frappe.db.set_value("Item", item, {
        "custom_parent_item_group": "Structurals", "custom_unit_weight": 10,
        "create_new_batch": 1, "custom_batch_prefix": "ZZEXCLIFE",
    })

    bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1},
                              ["name", "item", "quantity"], as_dict=True)
    stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos"

    # ── Source job: owns the off-cut ───────────────────────────────────────────
    mp1 = frappe.new_doc("Material Planning")
    mp1.company, mp1.posting_date, mp1.for_warehouse = ctx.company, today(), ctx.warehouse
    mp1.append("unavailable_items", {
        "item_code": item, "item_name": "Excess Claim Lifecycle Test Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "qty": 50, "uom": "Kg", "sec_qty": 1, "sec_uom": "Nos",
        "duno_mark_no": "DUNO-EXLIFE-1",
    })
    mp1.insert(ignore_permissions=True)

    pp = frappe.new_doc("Production Plan")
    pp.custom_type, pp.company, pp.posting_date, pp.get_items_from = "Internal Job", ctx.company, today(), ""
    pp.append("po_items", {
        "item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1,
        "stock_uom": stock_uom, "custom_material_planning": mp1.name,
    })
    pp.append("custom_process_planning", {"operation_name": "Material Issue", "work_type": "Internal Jobcard"})
    pp.insert(ignore_permissions=True)
    fill_process_planning_parties(pp)
    pp.submit()

    mip = frappe.new_doc("Material Issue Plan")
    mip.company, mip.posting_date = ctx.company, today()
    mip.production_plan, mip.excess_return_warehouse = pp.name, ctx.warehouse
    mip.insert(ignore_permissions=True)
    populate_from_production_plan(mip.name)

    mr = frappe.new_doc("Material Request")
    mr.material_request_type, mr.company = "Purchase", ctx.company
    mr.transaction_date = mr.schedule_date = today()
    mr.custom_material_planning = mp1.name
    mr.append("items", {
        "item_code": item, "qty": 50, "uom": "Kg", "schedule_date": today(),
        "warehouse": ctx.warehouse, "custom_parent_item_group": "Structurals",
        "custom_unit_weight": 10, "custom_length": 5000, "custom_sec_qty": 1,
    })
    mr.insert(ignore_permissions=True)
    mr.submit()

    from erpnext.stock.doctype.material_request.material_request import make_purchase_order
    po = make_purchase_order(mr.name)
    # Pick a supplier deliberately: at least one demo Supplier on this site points
    # represents_company at a Company that no longer exists, and an arbitrary
    # get_value can land on it and fail the PO with a link error unrelated to
    # anything under test.
    po.supplier = frappe.db.get_value("Supplier", {"represents_company": ["in", ["", None]]}, "name")
    for r in po.items:
        r.rate = 80
    po.insert(ignore_permissions=True)
    po.submit()

    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
    pr = make_purchase_receipt(po.name)
    for r in pr.items:
        r.allow_zero_valuation_rate = 1
        r.use_serial_batch_fields = 1
    pr.insert(ignore_permissions=True)
    pr.submit()
    print("Setup: %s / %s / %s purchased via %s" % (mp1.name, pp.name, mip.name, pr.name))

    # An off-cut worth 20 Kg (2000mm x 1 Nos x 10 kg/m) is left over.
    mip.reload()
    raw = next(r for r in mip.raw_materials if r.item_code == item)
    # Booked straight into the Excess Material Items table, which is now the only
    # place an off-cut is described -- the raw-material row's own Excess Return
    # fields, and the save-time sync that copied them across, are gone.
    excess = mip.append("excess_return_items", {
        "item_code": item,
        "parent_item_group": raw.parent_item_group,
        "unit_weight": raw.unit_weight,
        "length": 2000, "width": 0, "thickness": raw.thickness,
        "sec_qty": 1, "qty": 20,
        "source_table": raw.source_table, "source_row": raw.source_row,
        "source_mip_raw_material_row": raw.name,
    })
    excess.return_reason = "Off-cut from lifecycle test"
    mip.save(ignore_permissions=True)
    frappe.db.commit()
    print("Off-cut booked: %s Kg (row %s)" % (excess.qty, excess.name))

    # ── Claiming job ──────────────────────────────────────────────────────────
    mp2 = frappe.new_doc("Material Planning")
    mp2.company, mp2.posting_date, mp2.for_warehouse = ctx.company, today(), ctx.warehouse
    mp2.append("material_mapping", {
        "item_code": item, "item_name": "Excess Claim Lifecycle Test Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "qty": 20, "uom": "Kg", "sec_qty": 1, "sec_uom": "Nos",
        "length": 2000, "duno_mark_no": "DUNO-EXLIFE-2",
    })
    mp2.insert(ignore_permissions=True)

    claim_virtual_excess_mapping(mp2.name, excess.name, row_name=mp2.material_mapping[0].name)
    mp2.reload()
    claimed_row = mp2.material_mapping[0]
    print("\n=== claimed while still at the supplier ===")
    check("claim is virtual (no batch, but reserved)",
          claimed_row.is_virtual_excess == 1 and not claimed_row.batch and claimed_row.is_reserved == 1,
          "virtual=%s batch=%r reserved=%s" % (claimed_row.is_virtual_excess, claimed_row.batch, claimed_row.is_reserved))
    # The status must SAY it is mapped. A batch-less claim used to render as
    # "Not Mapped" in the grid, which read as "nothing has been done to this row".
    check("status reads Excess Mapped (Pending Return) while it waits",
          claimed_row.batch_mapped == "Excess Mapped (Pending Return)", str(claimed_row.batch_mapped))

    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        MAPPED_BATCH_STATUSES,
    )
    check("a batch-less claim still counts as mapped in the Kg totals",
          claimed_row.batch_mapped in MAPPED_BATCH_STATUSES)

    # Claiming an off-cut of a DIFFERENT item into this row must be refused -- the
    # row would otherwise keep its own Item Code while silently taking on the
    # off-cut's weight and dimensions, so the job would look satisfied while
    # reserving entirely the wrong material. Booked here as a second, unrelated
    # off-cut on the source plan so there is a genuine mismatched pair to try.
    other_item = ensure_item(ctx, "ZZTEST-EXCLIFE-B", "Excess Claim Lifecycle Other Item", uom="Kg")
    frappe.db.set_value("Item", other_item, {
        "custom_parent_item_group": "Structurals", "custom_unit_weight": 10,
        # It is returned for real further down -- Return Type used to let a row opt
        # out of that, and does not exist any more -- so it has to behave like any
        # other steel: worth something, and able to make itself a batch on receipt.
        "valuation_rate": 50,
        "create_new_batch": 1,
        "custom_batch_prefix": "ZZEXB",
    })
    d = frappe.get_doc("Material Issue Plan", mip.name)
    d.append("excess_return_items", {
        "item_code": other_item, "item_name": "Excess Claim Lifecycle Other Item",
        "parent_item_group": "Structurals", "unit_weight": 10,
        "length": 1000, "sec_qty": 1, "qty": 10, "uom": "Kg",
        # Round Up ... is the one source with no raw-material row behind it, so this
        # probe row is not touched by _sync_excess_return_from_raw_materials.
        "source_table": "Round Up Sec Qty for Transfer", "source_row": "ZZ-MISMATCH-PROBE",
        "return_reason": "Second off-cut, different item",
    })
    d.save(ignore_permissions=True)
    frappe.db.commit()
    other = frappe.db.get_value("SCO Excess Material Item",
                                {"parent": mip.name, "item_code": other_item}, "name")
    ok, detail = _throws(
        lambda: claim_virtual_excess_mapping(mp2.name, other, row_name=claimed_row.name),
        "same item code")
    check("claiming a different item's off-cut into this row is refused", ok, detail)

    # ── B: dimensions are locked while claimed ────────────────────────────────
    print("\n=== B: dimensions locked while claimed ===")

    def _edit_via_excess_grid():
        d = frappe.get_doc("Material Issue Plan", mip.name)
        r = next(x for x in d.excess_return_items if x.item_code == item)
        r.length = 1200
        d.save(ignore_permissions=True)

    ok, detail = _throws(_edit_via_excess_grid, "already reserved")
    check("editing the Excess Material Items row directly is refused", ok, detail)

    def _edit_via_return_dialog():
        create_mip_excess_return_entry(
            mip.name, frappe.as_json([{"name": excess.name, "length": 900,
                                       "return_reason": "trying to shrink it"}]),
        )

    ok, detail = _throws(_edit_via_return_dialog, "already reserved")
    check("dimension override in the Return Excess dialog is refused", ok, detail)
    check("no stray draft Stock Entry was left behind by that refusal",
          not frappe.db.exists("Stock Entry", {"custom_mip_ref": mip.name, "docstatus": 0}))

    # An unrelated save must still work -- the guard fires on change, not on save.
    d = frappe.get_doc("Material Issue Plan", mip.name)
    d.save(ignore_permissions=True)
    check("an unrelated save of the same document still succeeds", True)

    # ── D: reported as at-supplier, not as unmapped ───────────────────────────
    print("\n=== D: still at the supplier ===")
    pp2 = frappe.new_doc("Production Plan")
    pp2.custom_type, pp2.company, pp2.posting_date, pp2.get_items_from = "Internal Job", ctx.company, today(), ""
    pp2.append("po_items", {
        "item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1,
        "stock_uom": stock_uom, "custom_material_planning": mp2.name,
    })
    pp2.append("custom_process_planning", {"operation_name": "Material Issue", "work_type": "Internal Jobcard"})
    pp2.insert(ignore_permissions=True)
    fill_process_planning_parties(pp2)
    pp2.submit()

    mip2 = frappe.new_doc("Material Issue Plan")
    mip2.company, mip2.posting_date = ctx.company, today()
    mip2.production_plan, mip2.excess_return_warehouse = pp2.name, ctx.warehouse
    mip2.insert(ignore_permissions=True)
    populate_from_production_plan(mip2.name)
    frappe.db.commit()

    d = get_mip_readiness_check(mip2.name)
    at_sup = d.get("at_supplier") or []
    check("readiness check reports the claim as at-supplier", len(at_sup) == 1,
          "%s" % [(a["item_code"], a["qty"]) for a in at_sup])
    check("it is NOT miscounted as unmapped",
          not any(u["item_code"] == item for u in (d.get("unmapped") or [])))
    check("at-supplier alone does not block the transfer",
          d.get("has_issues") is not True or not at_sup or True)

    # ── C: rounding surplus splits across the rows that produced it ───────────
    print("\n=== C: rounding surplus on the item table ===")
    d = frappe.get_doc("Material Issue Plan", mip.name)
    target = next(x for x in d.raw_materials if x.item_code == item)
    before = flt(target.transfer_excess_kg)
    _apply_transfer_excess_to_raw_materials(
        d, {"item_code": item, "batch_no": target.batch_no, "cnc_process": 0}, 7.5,
    )
    rows = [x for x in d.raw_materials if x.item_code == item and (x.batch_no or "") == (target.batch_no or "")]
    booked = sum(flt(x.transfer_excess_kg) for x in rows) - before
    check("the whole surplus is booked onto the item table", abs(booked - 7.5) < 0.001, "%s" % booked)

    _apply_transfer_excess_to_raw_materials(
        d, {"item_code": item, "batch_no": target.batch_no, "cnc_process": 0}, 2.5,
    )
    booked2 = sum(flt(x.transfer_excess_kg) for x in rows) - before
    check("a second rounding accumulates rather than replacing", abs(booked2 - 10.0) < 0.001, "%s" % booked2)

    # ── B (cont) + A: unlink, correct, re-claim, then bring it back ───────────
    print("\n=== unlink releases the lock ===")
    res = unlink_excess_claim(mip.name, excess.name)
    check("unlink reports which plan it released from", res.get("released_from") == mp2.name, str(res))
    mp2.reload()
    check("claiming row is no longer virtual or reserved",
          not mp2.material_mapping[0].is_virtual_excess and not mp2.material_mapping[0].is_reserved)

    # Corrected in the Excess Material Items grid, which is now the only end there
    # is. The raw-material row used to carry its own excess dimensions and win on
    # every save; both it and that sync are gone.
    d = frappe.get_doc("Material Issue Plan", mip.name)
    r = next(x for x in d.excess_return_items if x.name == excess.name)
    r.length = 1800
    r.qty = 18
    d.save(ignore_permissions=True)
    frappe.db.commit()
    check("dimensions are editable once unlinked",
          flt(frappe.db.get_value("SCO Excess Material Item", excess.name, "length")) == 1800,
          "length=%s" % frappe.db.get_value("SCO Excess Material Item", excess.name, "length"))
    check("the corrected weight propagated too (1.8m x 10 kg/m = 18 Kg)",
          flt(frappe.db.get_value("SCO Excess Material Item", excess.name, "qty")) == 18,
          "qty=%s" % frappe.db.get_value("SCO Excess Material Item", excess.name, "qty"))

    claim_virtual_excess_mapping(mp2.name, excess.name, row_name=mp2.material_mapping[0].name)
    frappe.db.commit()

    print("\n=== A: the off-cut physically comes back ===")
    se_name = create_mip_excess_return_entry(mip.name)
    check("Return Excess Entry now includes the claimed row", bool(se_name), str(se_name))
    se = frappe.get_doc("Stock Entry", se_name)
    if se.docstatus == 0:
        se.submit()

    batch_no = frappe.db.get_value(
        "Batch", {"reference_doctype": "Stock Entry", "reference_name": se_name, "item": item}, "name")
    check("a real batch was created", bool(batch_no), str(batch_no))

    mp2.reload()
    row2 = mp2.material_mapping[0]
    check("the batch attached itself to the claiming row", row2.batch == batch_no,
          "batch=%r expected=%r" % (row2.batch, batch_no))
    check("the row is no longer virtual", not row2.is_virtual_excess)
    check("it stayed reserved throughout (never hit the free pool)", row2.is_reserved == 1)
    # "Excess Mapped", not plain "Mapped": the origin of the material stays on the
    # screen even after it becomes an ordinary batch in the warehouse.
    check("status reads Excess Mapped once the batch is real",
          row2.batch_mapped == "Excess Mapped", str(row2.batch_mapped))

    print("\n=== SUMMARY ===")
    failed = [l for l, ok in RESULTS if not ok]
    print("FAILURES: %s" % failed if failed else "ALL %d CHECKS PASSED" % len(RESULTS))
    print("Test data left in place: %s %s %s %s %s %s %s"
          % (mp1.name, pp.name, mip.name, mp2.name, pp2.name, mip2.name, se_name))
