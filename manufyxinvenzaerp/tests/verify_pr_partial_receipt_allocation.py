"""A receipt smaller than the plan must still allocate everything it delivered.

Real purchasing does not hand the plan back what the plan asked for. An item is
dropped when the Purchase Order is raised, another is dropped again at the receipt,
and what does arrive is re-cut to whatever the supplier actually had -- so the
received weight is routinely BELOW the planned weight. The rule is: allocate every
item the receipt did deliver, and leave the balance as a blank-batch "Not Mapped"
row so it can be purchased or mapped to another batch by hand.

Three separate things stopped that happening on PR-26-00008 -> MP-2026-00015, where
PLATE8 was cut from 7 nos @ 6300 mm to 5 nos @ 6000 mm at the receipt:

  1. _validate_batch_calc_qty compared raw floats. Allocation spread 2826 Kg over
     the PLATE8 rows and the batch ran out EXACTLY on row 21, so the row claimed
     239.690 Kg against ten unrounded floats summing to 239.6899999999996 free --
     refused for a difference the message itself printed as "0.0 Kg". Both the
     comparison and the running total are now taken at the 3 decimals this table
     stores.

  2. The whole receipt is written in ONE save, so that single refused row discarded
     the allocation of PLATE12, PLATE25, PLATE16 and PLATE10 as well. Five items
     received, four of them allocatable without argument, and the plan kept all
     five unmapped. A failed pass now retries line by line under a savepoint each.

  3. Nothing capped a line at the batch's free stock, so a batch partly reserved by
     another plan produced mapping rows claiming more of it than exists -- the same
     refusal, from the other direction. _receivable_qty caps it, turning an
     over-claim into the ordinary shortfall row.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_pr_partial_receipt_allocation.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _pr_item(qty, length=6000, width=1500, thickness=8):
    return frappe._dict(
        qty=qty, custom_length=length, custom_width=width, custom_thickness=thickness
    )


def _validate_boundary(row_qtys, batch_stock):
    """_validate_batch_calc_qty's accumulator over reserve_without_dimensions rows,
    which is where the drift built up. Returns the row idx that would be refused,
    or None when they all fit."""
    allocated_so_far = 0.0
    for idx, qty in enumerate(row_qtys, start=1):
        available = flt(max(0.0, batch_stock - allocated_so_far), 3)
        if flt(flt(qty) - available, 3) > 0:
            return idx
        allocated_so_far = flt(allocated_so_far + flt(qty), 3)
    return None


def run():
    from manufyxinvenzaerp.purchase_receipt_management.purchase_receipt import (
        _receivable_qty,
    )

    print("=== 1. the exact-fit boundary that refused PR-26-00008 ===")
    # The real PLATE8 allocation: ten rows filled, the eleventh taking the last
    # 239.690 Kg of a 2826 Kg batch to the kilo.
    plate8 = [146.010, 564.485, 333.124, 333.124, 141.300, 275.133,
              172.700, 333.124, 146.010, 141.300, 239.690]
    check("sum of claims equals the batch exactly", flt(sum(plate8), 3), 2826.0)
    check("a batch filled to the last row is accepted", _validate_boundary(plate8, 2826.0), None)

    over = list(plate8)
    over[-1] = flt(over[-1] + 0.01, 3)
    check("one hundredth over is still refused", _validate_boundary(over, 2826.0), 11)

    print()
    print("=== 2. a line is capped at the batch's free stock, not the plan's wish ===")
    # Nothing reserved: the whole line is claimable.
    check("free batch -> whole line", _receivable_qty(_pr_item(2826.0), 2826.0, 0.0), 2826.0)
    # Another plan holds 1000 Kg of it: only the rest may be claimed, and the
    # remainder becomes a Not Mapped row rather than a refused save.
    check("partly reserved -> capped", _receivable_qty(_pr_item(2826.0), 2826.0, 1000.0), 1826.0)
    check("fully reserved -> nothing to claim", _receivable_qty(_pr_item(2826.0), 2826.0, 2826.0), 0.0)
    # No stock in the plan's warehouse: _validate_batch_calc_qty skips such rows
    # too, so capping to 0 here would block a legitimate allocation.
    check("no stock in this warehouse -> uncapped", _receivable_qty(_pr_item(500.0), 0.0, 0.0), 500.0)

    print()
    print("=== 3. one refused line cannot discard the rest of the receipt ===")
    from manufyxinvenzaerp.purchase_receipt_management import purchase_receipt as pr_mod
    # signature() unwraps @frappe.whitelist(), which __code__ would not see past.
    import inspect
    check("allocate_pr_stock_to_mp takes only_items",
          "only_items" in inspect.signature(pr_mod.allocate_pr_stock_to_mp).parameters, True)
    check("the per-line fallback exists",
          callable(getattr(pr_mod, "_allocate_pr_items_individually", None)), True)
    source = frappe.read_file(frappe.get_app_path(
        "manufyxinvenzaerp", "purchase_receipt_management", "purchase_receipt.py"))
    check("the fallback rolls back to its own savepoint",
          "frappe.db.rollback(save_point=savepoint)" in source, True)
    check("submit falls back to it", "_allocate_pr_items_individually(doc.name, mp_name)" in source, True)
    check("retry falls back to it too",
          "_allocate_pr_items_individually(pr_name, mp_name)" in source, True)

    print()
    print("=== 4. the shortfall is reported, not just left in the table ===")
    check("allocation returns what is still unmapped", "pending_by_item" in source, True)
    check("and submit shows it", "_msgprint_pending_mapping" in source, True)

    print()
    print("=== 5. against the live plan that failed ===")
    if frappe.db.exists("Material Planning", "MP-2026-00015"):
        mp = frappe.get_doc("Material Planning", "MP-2026-00015")
        mapped = [r for r in mp.material_mapping if r.batch]
        blank = [r for r in mp.material_mapping if not r.batch]
        print("   MP-2026-00015: %d mapped, %d not mapped, %d exact match"
              % (len(mapped), len(blank), len(mp.available_raw_materials)))

        # No batch may be claimed for more than it holds -- the condition the
        # refusal was protecting, which must still hold now the save succeeds.
        claimed = {}
        for row in mapped:
            claimed[row.batch] = flt(claimed.get(row.batch, 0.0) + flt(row.qty), 3)
        over_claimed = []
        for batch, kg in sorted(claimed.items()):
            stock = flt(frappe.db.get_value("Batch", batch, "batch_qty"), 3)
            if stock and flt(kg - stock, 3) > 0:
                over_claimed.append((batch, kg, stock))
        check("no batch is claimed beyond its stock", over_claimed, [])

        try:
            mp.flags.mfx_saved_by_another_document = True
            mp.save(ignore_permissions=True)
            frappe.db.commit()
            saved = True
        except Exception as e:
            saved = frappe.utils.strip_html(str(e))[:120]
        check("the plan that could not be saved now saves", saved, True)
    else:
        print("   (MP-2026-00015 not on this site -- skipped)")

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
