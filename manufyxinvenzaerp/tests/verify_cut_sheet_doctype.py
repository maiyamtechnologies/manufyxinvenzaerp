"""Verify the Cut Sheet doctype: one nesting plan, shared across Material Plannings.

The nesting is stated ONCE against the batch -- this piece (W1), this many of them,
this remnant (W2) -- and jobs take pieces from it like they reserve batch stock.
Covers what the client asked for:

  * partial allocation: 10 pieces, 2 to one plan, 2 to another, 6 still free
  * the same sheet serving two Material Plannings at once
  * over-allocation refused
  * releasing an allocation puts the pieces back
  * W1's dimensions ride on the reservation, not the batch's
  * W2 written to the batch on the FIRST transfer, and taken back off if cancelled

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_cut_sheet_doctype.run
"""

import frappe
from frappe.utils import flt, today

from manufyxinvenzaerp.tests.create_full_test_entry import get_ctx, ensure_item
from manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet import (
    allocate_cut_sheet, get_available_cut_sheets, suggest_w1_sec_qty,
    apply_w2_to_batch, revert_w2_from_batch,
)
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    unreserve_batches,
)

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


def plate_kg(l, w, n=1):
    return flt((l / 1000.0) * (w / 1000.0) * THICK * UW * n, 3)


def run():
    ctx = get_ctx()
    item = ensure_item(ctx, "ZZTEST-CSDOC", "Cut Sheet Doctype Test Plate", uom="Kg")
    frappe.db.set_value("Item", item, {
        "custom_parent_item_group": "Plates", "custom_unit_weight": UW,
        "create_new_batch": 1, "custom_batch_prefix": "ZZCSDOC",
    })

    SHEET_L, SHEET_W = 1800.0, 6300.0
    W1_L, W1_W = 900.0, 1200.0
    sheet_kg, w1_kg = plate_kg(SHEET_L, SHEET_W), plate_kg(W1_L, W1_W)

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type, se.company, se.posting_date = "Material Receipt", ctx.company, today()
    se.append("items", {
        "item_code": item, "qty": sheet_kg, "uom": "Kg", "t_warehouse": ctx.warehouse,
        "basic_rate": 50, "allow_zero_valuation_rate": 1,
        "custom_parent_item_group": "Plates", "custom_unit_weight": UW,
        "custom_length": SHEET_L, "custom_width": SHEET_W, "custom_thickness": THICK,
        "custom_sec_qty": 1,
    })
    se.insert(ignore_permissions=True)
    se.submit()
    batch_no = frappe.db.get_value("Batch", {"reference_doctype": "Stock Entry",
                                             "reference_name": se.name, "item": item}, "name")
    print("sheet %s Kg as batch %s | W1 %sx%s = %s Kg" % (sheet_kg, batch_no, W1_L, W1_W, w1_kg))

    print("\n=== the nesting plan ===")
    suggested = suggest_w1_sec_qty(sheet_length=SHEET_L, sheet_width=SHEET_W,
                                   w1_length=W1_L, w1_width=W1_W)
    # 1800/900 x 6300/1200 = 2 x 5 = 10
    check("piece count is suggested from geometry, not weight", suggested == 10, "suggested %s" % suggested)

    cs = frappe.new_doc("Cut Sheet")
    cs.company, cs.item_code, cs.batch_no, cs.warehouse = ctx.company, item, batch_no, ctx.warehouse
    cs.w1_length, cs.w1_width, cs.w1_sec_qty = W1_L, W1_W, 10
    cs.w2_length, cs.w2_width, cs.w2_sec_qty = 1800.0, 300.0, 1
    cs.insert(ignore_permissions=True)
    cs.reload()
    check("sheet dimensions read from the batch",
          flt(cs.sheet_width) == SHEET_W and flt(cs.sheet_thickness) == THICK,
          "%sx%s t%s" % (cs.sheet_length, cs.sheet_width, cs.sheet_thickness))
    check("Kg per piece computed", abs(flt(cs.w1_qty_per_nos) - w1_kg) < 0.01,
          "%s vs %s" % (cs.w1_qty_per_nos, w1_kg))
    check("all 10 pieces start free", flt(cs.available_sec_qty) == 10, str(cs.available_sec_qty))
    check("status is Active", cs.status == "Active", cs.status)

    def _mp():
        mp = frappe.new_doc("Material Planning")
        mp.company, mp.posting_date, mp.for_warehouse = ctx.company, today(), ctx.warehouse
        mp.append("material_mapping", {
            "item_code": item, "item_name": "Cut Sheet Doctype Test Plate",
            "parent_item_group": "Plates", "unit_weight": UW,
            "length": W1_L, "width": W1_W, "thickness": THICK,
            "qty": plate_kg(W1_L, W1_W, 2), "uom": "Kg", "sec_qty": 2, "sec_uom": "Nos",
            "duno_mark_no": "DUNO-CS",
        })
        mp.insert(ignore_permissions=True)
        return mp

    print("\n=== two plans drawing from one sheet ===")
    mp1, mp2 = _mp(), _mp()
    r1 = allocate_cut_sheet(mp1.name, cs.name, 2, row_name=mp1.material_mapping[0].name)
    check("plan 1 takes 2 pieces", abs(flt(r1["qty"]) - plate_kg(W1_L, W1_W, 2)) < 0.01, str(r1))

    cs.reload()
    check("6 free after the first claim... (expect 8)", flt(cs.available_sec_qty) == 8,
          str(cs.available_sec_qty))

    r2 = allocate_cut_sheet(mp2.name, cs.name, 2, row_name=mp2.material_mapping[0].name)
    cs.reload()
    check("the SAME sheet serves a second Material Planning", len(cs.allocations) == 2,
          "%s allocations" % len(cs.allocations))
    check("6 pieces still free for anyone else", flt(cs.available_sec_qty) == 6,
          str(cs.available_sec_qty))
    check("both plans are named on the sheet",
          {a.material_planning for a in cs.allocations} == {mp1.name, mp2.name})

    print("\n=== the reservation carries W1's size, not the sheet's ===")
    mp1.reload()
    row = mp1.material_mapping[0]
    check("batch is the real batch (so the ledger still works)", row.batch == batch_no, str(row.batch))
    check("dimensions on the row are W1's",
          flt(row.batch_width) == W1_W and flt(row.batch_length) == W1_L,
          "%sx%s" % (row.batch_length, row.batch_width))
    check("thickness is the batch's", flt(row.batch_thickness) == THICK, str(row.batch_thickness))
    check("status reads Cut Sheet Mapped", row.batch_mapped == "Cut Sheet Mapped", str(row.batch_mapped))
    check("row is reserved", row.is_reserved == 1)
    check("row points back at the sheet", row.cut_sheet_ref == cs.name, str(row.cut_sheet_ref))

    print("\n=== limits ===")
    ok, detail = _throws(lambda: allocate_cut_sheet(mp1.name, cs.name, 99), "still free")
    check("taking more pieces than remain is refused", ok, detail)
    ok, detail = _throws(lambda: allocate_cut_sheet(mp1.name, cs.name, 0), "greater than 0")
    check("zero pieces is refused", ok, detail)

    def _shrink_below_allocated():
        d = frappe.get_doc("Cut Sheet", cs.name)
        d.w1_sec_qty = 1
        d.save(ignore_permissions=True)
    # Refused, and now by the broader guard: any change to W1/W2 is blocked while a
    # job is planning from the sheet, not only a reduction past what it holds
    # (CutSheet._block_cut_changes_while_claimed). Matched on "cannot be changed"
    # rather than the older "already allocated" wording, which only ever covered the
    # one case.
    ok, detail = _throws(_shrink_below_allocated, "cannot be changed")
    check("cutting the sheet's yield below what jobs hold is refused", ok, detail)

    print("\n=== releasing gives the pieces back ===")
    mp2.reload()
    unreserve_batches(mp2.name, frappe.as_json([mp2.material_mapping[0].name]))
    cs.reload()
    check("plan 2's pieces are back on the sheet", flt(cs.available_sec_qty) == 8,
          str(cs.available_sec_qty))
    check("its allocation row is gone", len(cs.allocations) == 1, "%s left" % len(cs.allocations))

    print("\n=== W2 lands on the batch at the first transfer ===")
    before = frappe.db.get_value("Batch", batch_no, ["custom_width"], as_dict=True)
    applied = apply_w2_to_batch(cs.name, se.name)
    after = frappe.db.get_value("Batch", batch_no, ["custom_length", "custom_width"], as_dict=True)
    check("W2 written to the batch", applied and flt(after.custom_width) == 300.0,
          "%s -> %s" % (before.custom_width, after.custom_width))
    cs.reload()
    check("sheet is marked Consumed", cs.status == "Consumed" and cs.w2_applied == 1, cs.status)
    check("a second transfer does not re-apply it", apply_w2_to_batch(cs.name, se.name) is False)

    revert_w2_from_batch(cs.name)
    back = frappe.db.get_value("Batch", batch_no, ["custom_width"], as_dict=True)
    check("cancelling the transfer restores the uncut sheet",
          flt(back.custom_width) == SHEET_W, str(back.custom_width))

    print("\n=== picker ===")
    offered = [c for c in get_available_cut_sheets(mp1.name, item_code=item) if c["name"] == cs.name]
    check("sheet is offered while pieces remain", len(offered) == 1)
    check("it advertises what is left", offered and flt(offered[0]["available_sec_qty"]) == 8,
          str(offered[0]["available_sec_qty"]) if offered else "")

    frappe.db.commit()
    print("\n=== SUMMARY ===")
    failed = [l for l, ok in RESULTS if not ok]
    print("FAILURES: %s" % failed if failed else "ALL %d CHECKS PASSED" % len(RESULTS))
    print("Test data left in place: %s %s %s %s" % (cs.name, mp1.name, mp2.name, batch_no))
