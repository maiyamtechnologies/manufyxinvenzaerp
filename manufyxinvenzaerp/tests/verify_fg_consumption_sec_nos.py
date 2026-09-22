"""The final stock entry consumes pieces as well as kilos.

Every document in the chain carries two figures: the weight in Kg and the count in Sec
Nos. The transfers to the supplier carried both. The finished-goods entry built its
consumption rows from item, batch, qty, uom and warehouse only -- so the Nos were dropped
at the last step, and the one entry that closes the job said nothing about how many
pieces it had eaten.

Two things had to be added. The supplier-warehouse tally now nets custom_sec_qty exactly
as it nets the Kg, in and out. And where the Kg on a line get narrowed -- down to the
finished drawings' share, then again by whatever off-cut is booked to come back -- the
Nos travel in the same proportion, or the line would claim every piece while consuming
part of the weight.

Fractional Nos are correct here and not a rounding fault: a 12 m bar cut across two
drawings is genuinely 0.7 of a bar to one of them. On SC-ORD-2026-00025 the ISMB400 line
consumes 11.497 of the 12.000 bars standing at the supplier; the 0.503 left behind is the
371.753 Kg of off-cut, at 739.2 Kg per 12 m bar.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_consumption_sec_nos.run
"""

import inspect

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.subcontracting_management import subcontracting as sub

    print("=== the tally nets Nos the same way it nets Kg ===")
    src = inspect.getsource(sub._get_supplier_wh_consumption_items)
    check("Sec Nos are summed in and out",
          "THEN -IFNULL(sed.custom_sec_qty, 0)" in src, True)
    check("the row carries them", '"custom_sec_qty": flt(r.sec_qty, 3),' in src, True)
    check("...with their UOM", '"custom_sec_uom": r.sec_uom or "",' in src, True)

    print()
    print("=== narrowing the Kg narrows the Nos with them ===")
    narrowed = inspect.getsource(sub._consumption_for_completed)
    check("the scaling is applied where qty is set",
          "**_scaled_sec_qty(row, qty)" in narrowed, True)
    scale = inspect.getsource(sub._scaled_sec_qty)
    check("it is a proportion of what was there",
          "sec * (flt(qty, 3) / whole)" in scale, True)
    check("a line with no Nos is left alone", "if not sec or not whole:" in scale, True)

    print()
    print("=== the arithmetic ===")
    # 12 bars, 8,870.400 Kg; consume 8,500.800 and half a bar stays behind.
    check("12 bars scaled to 8500.800/8870.400",
          flt(sub._scaled_sec_qty({"qty": 8870.400, "custom_sec_qty": 12.0}, 8500.800)["custom_sec_qty"], 3),
          11.5)
    check("consuming all of it changes nothing",
          flt(sub._scaled_sec_qty({"qty": 8870.400, "custom_sec_qty": 12.0}, 8870.400)["custom_sec_qty"], 3),
          12.0)
    check("a line with no Nos yields no key",
          sub._scaled_sec_qty({"qty": 100.0, "custom_sec_qty": 0.0}, 50.0), {})

    print()
    print("=== live: every consumption line keeps its own Kg-per-piece ===")
    sco_name = "SC-ORD-2026-00025"
    if not frappe.db.exists("Subcontracting Order", sco_name):
        print("  SKIP %s not on this site" % sco_name)
    else:
        sco = frappe.get_doc("Subcontracting Order", sco_name)
        wh = sub._get_sco_supplier_warehouse(sco)
        available = sub._get_supplier_wh_consumption_items(sco, wh)
        preview = sub.get_final_stock_entry_preview(sco_name)
        consumed = sub._consumption_for_completed(sco, wh, preview, available)

        at_supplier = {(r["item_code"], r.get("batch_no") or ""): r for r in available}
        check("every line at the supplier carries Nos",
              all(flt(r.get("custom_sec_qty")) > 0 for r in available), True)
        check("so does every line being consumed",
              all(flt(r.get("custom_sec_qty")) > 0 for r in consumed), True)

        # Compared as Nos rather than as Kg-per-piece: the Nos are stored at three
        # decimals, so on a 1,884 Kg sheet the last digit is worth 0.3 Kg and a
        # Kg-per-piece comparison fails on the rounding alone, not on the split.
        for r in consumed:
            src_row = at_supplier[(r["item_code"], r.get("batch_no") or "")]
            exact = flt(src_row["custom_sec_qty"]) * (flt(r["qty"]) / flt(src_row["qty"]))
            check("%-9s %.3f of %.3f piece(s)" % (
                      r["item_code"], flt(r["custom_sec_qty"], 3), flt(src_row["custom_sec_qty"], 3)),
                  flt(r["custom_sec_qty"], 3), flt(exact, 3))

        print()
        print("=== live: the Nos left behind weigh what the Kg left behind weigh ===")
        ismb = next((r for r in consumed if r["item_code"] == "ISMB400"), None)
        if not ismb:
            print("  SKIP no ISMB400 line")
        else:
            src_row = at_supplier[("ISMB400", ismb.get("batch_no") or "")]
            check("12.000 bars at the supplier", flt(src_row["custom_sec_qty"], 3), 12.0)
            kg_per_bar = flt(src_row["qty"]) / flt(src_row["custom_sec_qty"])
            kg_left = flt(flt(src_row["qty"]) - flt(ismb["qty"]), 3)
            nos_left = flt(flt(src_row["custom_sec_qty"]) - flt(ismb["custom_sec_qty"]), 3)
            check("%.3f Kg of bar stays behind" % kg_left,
                  flt(nos_left * kg_per_bar, 1), flt(kg_left, 1))
            check("which is more than the booked return needs",
                  kg_left >= 369.600, True)

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
