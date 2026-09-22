"""The Subcontracting Order's finished-goods line is measured in the item's own UOM.

SC-ORD-2026-00025 read "4,740.12 Nos" of a Kg-stocked item. The quantity was right --
4,740.12 Kg, with the real piece count of 11 sitting correctly in Sec Qty -- but the unit
beside it was not, so the order announced roughly four thousand seven hundred pieces of a
structure made of eleven.

Two things had to line up for that. Subcontracting Order Item has no "uom" field at all,
only "stock_uom", so the builder's `"uom": uom` was a key Frappe dropped without a word.
And the insert runs with ignore_validate and ignore_mandatory, which skips the
set_missing_values that would otherwise have fetched stock_uom from the Item. stock_uom is
read_only, so no one could have corrected it on the form either.

Nothing was numerically wrong -- the conversion factor is 1 -- but it reads as pieces to
anyone opening the order, and any conversion applied to it later would be wrong by the
weight of a whole structure.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_sco_fg_uom.run
"""

import inspect

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-60s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.subcontracting_management import subcontracting as sub_mod

    print("=== the builder names the field the doctype actually has ===")
    meta = frappe.get_meta("Subcontracting Order Item")
    check("there is no 'uom' field to set", bool(meta.get_field("uom")), False)
    df = meta.get_field("stock_uom")
    check("stock_uom is the one that exists", bool(df), True)
    if df:
        check("...and is read-only, so the form cannot fix it", df.read_only, 1)

    src = inspect.getsource(sub_mod)
    check("the FG row sets stock_uom", '"stock_uom": uom,' in src, True)
    check("the dropped key is gone", '"uom": uom,' in src, False)
    check("it still comes from the Item master",
          'uom = frappe.db.get_value("Item", fg_item, "stock_uom") or "Nos"' in src, True)

    print()
    print("=== live: no order line disagrees with its item ===")
    wrong = frappe.db.sql("""
        SELECT i.parent, i.item_code, i.stock_uom AS row_uom, it.stock_uom AS item_uom
        FROM `tabSubcontracting Order Item` i
        JOIN `tabItem` it ON it.name = i.item_code
        WHERE IFNULL(i.stock_uom, '') != it.stock_uom""", as_dict=True)
    for w in wrong:
        print("       %s %s: row=%s item=%s" % (w.parent, w.item_code, w.row_uom, w.item_uom))
    check("every line uses its item's stock UOM", len(wrong), 0)

    print()
    print("=== live: weight and pieces are told apart ===")
    sco_name = "SC-ORD-2026-00025"
    if not frappe.db.exists("Subcontracting Order", sco_name):
        print("  SKIP %s not on this site" % sco_name)
    else:
        sco = frappe.get_doc("Subcontracting Order", sco_name)
        d = sco.items[0]
        check("the quantity is in Kg", d.stock_uom, "Kg")
        check("the piece count is in Sec Qty", (flt(d.custom_sec_qty), d.custom_sec_uom), (11.0, "Nos"))
        check("no conversion is applied", flt(d.conversion_factor), 1.0)
        check("the BOM agrees", frappe.db.get_value("BOM", d.bom, "uom"), "Kg")

        print()
        print("=== live: the Kg chain still reconciles ===")
        moved = flt(frappe.db.sql("""
            SELECT SUM(CASE WHEN sed.t_warehouse = %(wh)s THEN sed.qty ELSE 0 END)
                 - SUM(CASE WHEN sed.s_warehouse = %(wh)s THEN sed.qty ELSE 0 END)
            FROM `tabStock Entry Detail` sed JOIN `tabStock Entry` se ON se.name = sed.parent
            WHERE (se.custom_sco_ref = %(sco)s OR se.subcontracting_order = %(sco)s)
              AND se.docstatus = 1""",
            {"wh": "INTERNATIONAL STEEL PRO - MIPL", "sco": sco_name})[0][0], 3)
        check("Transferred Weight is what the ledger holds",
              flt(sco.custom_transferred_weight_kg, 3), moved)
        check("Excess is transferred less planned",
              flt(sco.custom_excess_weight_kg, 3),
              flt(flt(sco.custom_transferred_weight_kg) - flt(sco.custom_total_weight_kg), 3))
        soe = frappe.db.get_value(
            "Supplier Operation Entry",
            {"subcontracting_order": sco_name, "sequence_id": 1}, "available_to_consume_kg")
        check("the first operation can consume all of it",
              flt(soe, 3), flt(sco.custom_transferred_weight_kg, 3))

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
