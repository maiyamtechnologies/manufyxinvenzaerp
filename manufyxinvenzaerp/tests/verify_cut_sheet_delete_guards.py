"""Deleting a Cut Sheet must not strand the batch it rewrote.

W2 replaces the batch's Length and Sec Qty with the remnant's, and the batch keeps
its original name. Delete the sheet afterwards and nothing on the site explains
why a batch called ...L12000... says 6000, and nothing knows what to restore: the
ledger still holds every kilo, so the Manufyx Stock Balance report and Material
Planning -- which works from the dimensions -- disagree with no visible cause.
That is exactly how ISA130-L12000-SR001 ended up reading 6000 mm / 9.84 Nos while
holding the full 7332 Kg it was received with.

on_trash now refuses while anything stands on the sheet -- a Material Planning row
pointing at it, reserved or not, or a submitted transfer taken from it -- and when
it does go through, hands the batch back its own dimensions first.

Claims are read from the database rather than from the stored Allocations table,
which is only rebuilt during validate: a sheet loaded and deleted without saving
carried a stale table, and a claim made since then would not have appeared in it.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_cut_sheet_delete_guards.run
"""

import frappe
from frappe.utils import flt

checks = []

SUFFIX = frappe.generate_hash(length=6).upper()
ITEM = "ZZTEST-CSDEL-%s" % SUFFIX
BATCH = "ZZTEST-CSDEL-BATCH-%s" % SUFFIX

SHEET_LENGTH, SHEET_SEC = 12000.0, 26.0
UNIT_WEIGHT = 23.5
W2_LENGTH, W2_SEC = 6000.0, 9.84


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _batch_dims():
    return frappe.db.get_value("Batch", BATCH, ["custom_length", "custom_sec_qty"], as_dict=True)


def _make_item():
    if frappe.db.exists("Item", ITEM):
        return
    frappe.get_doc({
        "doctype": "Item", "item_code": ITEM, "item_name": ITEM,
        "item_group": "Structural child node", "stock_uom": "Kg",
        "has_batch_no": 1, "create_new_batch": 0, "is_stock_item": 1,
        "gst_hsn_code": frappe.db.get_value("GST HSN Code", {}, "name"),
        "custom_parent_item_group": "Structurals",
        "custom_unit_weight": UNIT_WEIGHT,
        "custom_batch_prefix": "ZZCSDEL%s" % SUFFIX,
    }).insert(ignore_permissions=True)


def _make_batch():
    frappe.get_doc({
        "doctype": "Batch", "batch_id": BATCH, "item": ITEM,
        "custom_length": SHEET_LENGTH, "custom_sec_qty": SHEET_SEC,
    }).insert(ignore_permissions=True)


def _warehouse():
    return frappe.db.get_value("Warehouse", {"is_group": 0}, "name")


def _make_sheet():
    cs = frappe.get_doc({
        "doctype": "Cut Sheet", "batch_no": BATCH, "item_code": ITEM,
        # Mandatory: the split is against the batch in this warehouse.
        "warehouse": _warehouse(),
        "parent_item_group": "Structurals", "unit_weight": UNIT_WEIGHT,
        "w1_length": SHEET_LENGTH - W2_LENGTH, "w1_sec_qty": 1,
        "w2_length": W2_LENGTH, "w2_sec_qty": W2_SEC,
    }).insert(ignore_permissions=True)
    return cs


def run():
    from manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet import (
        apply_w2_to_batch,
    )

    created = []
    try:
        _make_item()
        _make_batch()
        created.append(("Batch", BATCH))
        cs = _make_sheet()
        created.append(("Cut Sheet", cs.name))
        print("item %s | batch %s | sheet %s" % (ITEM, BATCH, cs.name))

        print()
        print("=== the sheet reads its size off the batch ===")
        check("sheet length", flt(cs.sheet_length), SHEET_LENGTH)
        check("sheet sec qty", flt(cs.sheet_sec_qty), SHEET_SEC)

        print()
        print("=== W2 rewrites the batch, as it is meant to ===")
        applied = apply_w2_to_batch(cs.name, None)
        check("write-back happened", applied, True)
        dims = _batch_dims()
        check("batch now describes the remnant",
              (flt(dims.custom_length), flt(dims.custom_sec_qty)), (W2_LENGTH, W2_SEC))

        print()
        print("=== deleting it now restores the batch ===")
        frappe.delete_doc("Cut Sheet", cs.name, ignore_permissions=True)
        created.remove(("Cut Sheet", cs.name))
        dims = _batch_dims()
        check("length is back", flt(dims.custom_length), SHEET_LENGTH)
        check("sec qty is back", flt(dims.custom_sec_qty), SHEET_SEC)
        check("the sheet is gone", frappe.db.exists("Cut Sheet", cs.name), None)
        print("       (before the fix the batch stayed at %s mm with the sheet deleted)" % W2_LENGTH)

        print()
        print("=== a sheet that never wrote back leaves the batch alone ===")
        cs2 = _make_sheet()
        created.append(("Cut Sheet", cs2.name))
        frappe.delete_doc("Cut Sheet", cs2.name, ignore_permissions=True)
        created.remove(("Cut Sheet", cs2.name))
        dims = _batch_dims()
        check("untouched", (flt(dims.custom_length), flt(dims.custom_sec_qty)),
              (SHEET_LENGTH, SHEET_SEC))

        print()
        print("=== a submitted transfer blocks deletion ===")
        cs3 = _make_sheet()
        created.append(("Cut Sheet", cs3.name))
        live_se = frappe.db.get_value("Stock Entry", {"docstatus": 1}, "name")
        if not live_se:
            print("   (no submitted Stock Entry on this site -- skipped)")
        else:
            frappe.db.set_value("Cut Sheet", cs3.name,
                                {"w2_applied": 1, "w2_applied_stock_entry": live_se},
                                update_modified=False)
            try:
                frappe.delete_doc("Cut Sheet", cs3.name, ignore_permissions=True)
                blocked = False
            except frappe.ValidationError as e:
                blocked = frappe.utils.strip_html(str(e))
            check("refused", bool(blocked), True)
            check("the entry is named", live_se in (blocked or ""), True)
            check("the sheet survives", bool(frappe.db.exists("Cut Sheet", cs3.name)), True)
            print("       ->", (blocked or "")[:150])
            frappe.db.set_value("Cut Sheet", cs3.name,
                                {"w2_applied": 0, "w2_applied_stock_entry": ""},
                                update_modified=False)

        print()
        print("=== a cancelled transfer does not block ===")
        cancelled = frappe.db.get_value("Stock Entry", {"docstatus": 2}, "name")
        if not cancelled:
            print("   (no cancelled Stock Entry on this site -- skipped)")
        else:
            frappe.db.set_value("Cut Sheet", cs3.name,
                                {"w2_applied_stock_entry": cancelled}, update_modified=False)
            frappe.delete_doc("Cut Sheet", cs3.name, ignore_permissions=True)
            created.remove(("Cut Sheet", cs3.name))
            check("deleted", frappe.db.exists("Cut Sheet", cs3.name), None)

        print()
        print("=== claims are read live, not from the stored table ===")
        # A Cut Sheet is unique per batch, so the previous section's sheet has to
        # be gone before this one can make its own. It usually is -- the cancelled
        # transfer deletes it -- but that section skips itself when the site has no
        # cancelled Stock Entry, and this test must not depend on that.
        for leftover in frappe.get_all("Cut Sheet", filters={"batch_no": BATCH}, pluck="name"):
            frappe.delete_doc("Cut Sheet", leftover, force=1, ignore_permissions=True)
            if ("Cut Sheet", leftover) in created:
                created.remove(("Cut Sheet", leftover))
        cs4 = _make_sheet()
        created.append(("Cut Sheet", cs4.name))
        mm = frappe.db.get_value("Material Planning Material Mapping", {}, ["name", "parent"],
                                 as_dict=True)
        if not mm or not frappe.db.exists("Material Planning", mm.parent):
            print("   (no Material Planning mapping row on this site -- skipped)")
        else:
            before = frappe.db.get_value("Material Planning Material Mapping", mm.name,
                                         "cut_sheet_ref")
            # Point a live row at the sheet WITHOUT saving the sheet, so its own
            # Allocations table still says nothing is claiming it.
            frappe.db.set_value("Material Planning Material Mapping", mm.name,
                                "cut_sheet_ref", cs4.name, update_modified=False)
            stored = frappe.get_doc("Cut Sheet", cs4.name)
            check("its own table still shows no claim", len(stored.allocations or []), 0)
            try:
                frappe.delete_doc("Cut Sheet", cs4.name, ignore_permissions=True)
                blocked = False
            except frappe.ValidationError as e:
                blocked = frappe.utils.strip_html(str(e))
            check("still refused", bool(blocked), True)
            check("the plan is named", mm.parent in (blocked or ""), True)
            print("       ->", (blocked or "")[:150])
            frappe.db.set_value("Material Planning Material Mapping", mm.name,
                                "cut_sheet_ref", before or "", update_modified=False)

    finally:
        for doctype, name in reversed(created):
            if frappe.db.exists(doctype, name):
                frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
        if frappe.db.exists("Item", ITEM):
            frappe.delete_doc("Item", ITEM, force=1, ignore_permissions=True)
        frappe.db.commit()
        print()
        print("test fixtures removed")

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
