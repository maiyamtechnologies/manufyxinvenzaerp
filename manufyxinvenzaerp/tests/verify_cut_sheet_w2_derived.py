"""T4 — W2 is derived from W1, so the batch's available qty always matches its own
Balance details.

Both halves of a cut used to be calculated from their own dimensions, independently.
The Stock Entry consumes W1, so the batch was left holding (sheet - W1) while the
Balance fields claimed whatever their dimensions said -- which is why Total available
qty did not agree with the W2 details after a final stock entry.

W2 is now whatever is left: sheet - W1. The W2 DIMENSIONS are still entered by hand
(they describe the off-cut's shape, which cannot be inferred -- a plate can be cut
along either edge) and are what gets written onto the batch, so they are checked
against that derived weight and a mismatch is warned about on save.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_cut_sheet_w2_derived.run
"""

import frappe
from frappe.utils import flt
from manufyxinvenzaerp.tests.create_full_test_entry import get_ctx, ensure_item, ensure_batch

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    ctx = get_ctx()
    item = ensure_item(ctx, "ZZTEST-W2DERIVE", "W2 Derived", uom="Kg")
    frappe.db.set_value("Item", item, {"custom_unit_weight": 10, "custom_parent_item_group": "Structurals"})
    # 10 m bar at 10 Kg/m = 100 Kg. The batch is named per run: the last section
    # weighs what the LEDGER holds against it, so a batch reused from a previous
    # run carried that run's leftovers and the balance came out doubled. A Cut
    # Sheet is also unique per batch, so a fixed name made the second run fail to
    # insert at all.
    batch = ensure_batch(item, "ZZTEST-W2DERIVE-BATCH-%s" % frappe.generate_hash(length=6).upper(),
                         L=10000)
    frappe.db.set_value("Batch", batch, {"custom_length": 10000, "custom_sec_qty": 1})
    frappe.db.commit()

    print("=== Cut Sheet doctype: W2 derives from the sheet ===")
    cs = frappe.new_doc("Cut Sheet")
    cs.update({
        "batch_no": batch, "item_code": item, "parent_item_group": "Structurals",
        # Warehouse is mandatory: the split happens against the batch in one
        # particular warehouse, so a sheet that does not name one cannot say
        # which stock it is cutting.
        "warehouse": ctx.warehouse,
        "unit_weight": 10, "sheet_length": 10000, "sheet_sec_qty": 1,
        "w1_length": 3000, "w1_sec_qty": 2,      # 2 pieces x 3 m x 10 Kg/m = 60 Kg
        # Deliberately mis-measured: 7 m x 10 Kg/m would be 70 Kg, but only 40 Kg is
        # actually left. If W2 were still read from its own dimensions this would say
        # 70, so the assertion below is what proves the derivation.
        "w2_length": 7000, "w2_sec_qty": 1,
    })
    cs.insert(ignore_permissions=True)
    print("   sheet=%s Kg  w1=%s Kg  w2=%s Kg  (W2 dimensions would say 70)"
          % (cs.sheet_qty, cs.w1_total_qty, cs.w2_calc_qty))
    check("sheet weight", flt(cs.sheet_qty), 100.0)
    check("W1 from its own dimensions", flt(cs.w1_total_qty), 60.0)
    check("W2 is sheet - W1, ignoring its own dimensions (70)", flt(cs.w2_calc_qty), 40.0)

    # Make W1 bigger and confirm W2 follows without touching the W2 dimensions.
    cs.w1_sec_qty = 3                              # 90 Kg
    cs.save(ignore_permissions=True)
    check("W2 follows W1 automatically", flt(cs.w2_calc_qty), 10.0)

    # The whole sheet consumed leaves nothing, never a negative.
    cs.w1_length = 10000
    cs.w1_sec_qty = 1                              # 100 Kg == the whole sheet
    cs.save(ignore_permissions=True)
    check("nothing left -> W2 is 0", flt(cs.w2_calc_qty), 0.0)

    cs.w1_length = 12000                           # more than the sheet holds
    cs.save(ignore_permissions=True)
    check("over-cut never goes negative", flt(cs.w2_calc_qty), 0.0)

    print()
    print("=== the reported symptom: batch balance vs W2 ===")
    # Restore a sane plan: 60 Kg used, 40 Kg left.
    cs.w1_length = 3000
    cs.w1_sec_qty = 2
    cs.save(ignore_permissions=True)

    se = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": "Material Receipt",
        "company": ctx.company,
        "items": [{
            "item_code": item, "qty": 100, "uom": "Kg", "t_warehouse": ctx.warehouse,
            "batch_no": batch, "use_serial_batch_fields": 1,
            "basic_rate": 50, "allow_zero_valuation_rate": 1,
        }],
    })
    se.insert(ignore_permissions=True)
    se.submit()

    issue = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": "Material Issue",
        "company": ctx.company,
        "items": [{
            "item_code": item, "qty": flt(cs.w1_total_qty), "uom": "Kg",
            "s_warehouse": ctx.warehouse, "batch_no": batch,
            "use_serial_batch_fields": 1, "allow_zero_valuation_rate": 1,
        }],
    })
    issue.insert(ignore_permissions=True)
    issue.submit()

    balance = flt(frappe.db.sql("""
        SELECT SUM(sle.actual_qty) FROM `tabStock Ledger Entry` sle
        JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
        WHERE sle.is_cancelled = 0 AND sbe.batch_no = %s""", batch)[0][0] or 0)
    print("   received 100, consumed W1 (%s) -> batch balance %s" % (flt(cs.w1_total_qty), balance))
    check("batch balance equals W2 exactly", balance, flt(cs.w2_calc_qty))

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
    print("Test data left in place:", cs.name, batch, se.name, issue.name)
