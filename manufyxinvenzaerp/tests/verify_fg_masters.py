"""Finished-goods item rule, the FG batch prefix guard, and Stock Reconciliation blocked.

sep14 FG plan (.claude/tasks/sep14_fg_uom_plan.md), package A1 items 1-3:

  1. A finished-goods item with no transactions must be Kg with Nos as Secondary
     UOM, Has Batch No on, Create New Batch off, no batch prefix. One that already
     has transactions (FINGOODS001) gets an orange note and still saves.
  2. A raw-material batch prefix may not be FG: FG- names belong to finished goods.
  3. Stock Reconciliation cannot be saved, for any purpose, with one fixed message;
     the form shows the same message and disables Save.

Items 1 and 2 run the Item validate hook on documents that are never saved.
Item 3 tries a real insert, which the hook refuses, so nothing is written. The
one real record read, FINGOODS001, is validated in memory only, not saved.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_masters.run
"""

import os

import frappe

from manufyxinvenzaerp.item_management.item import validate_item
from manufyxinvenzaerp.stock_management.stock_reconciliation import BLOCKED_MESSAGE

checks = []

EXPECTED_MESSAGE = (
    "As the inventory module is completely customized, Stock Reconciliation cannot be "
    "used. Instead, use a Stock Entry of type Material Issue to remove the product from "
    "inventory, then a Material Receipt to add the updated stock."
)


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _refused(doc):
    """(refused?, message) from running the Item validate hook on an unsaved doc."""
    frappe.clear_messages()
    try:
        validate_item(doc, "validate")
    except frappe.ValidationError as e:
        return True, str(e)
    return False, ""


def _new_item(**fields):
    return frappe.get_doc(dict({
        "doctype": "Item", "item_code": "ZZFG-UNSAVED", "item_name": "ZZFG-UNSAVED",
        "item_group": "All Item Groups", "is_stock_item": 1,
    }, **fields))


def _fg(**overrides):
    base = dict(custom_parent_item_group="Finished Goods", stock_uom="Kg",
                custom_secondary_uom="Nos", has_batch_no=1, create_new_batch=0)
    base.update(overrides)
    return _new_item(**base)


def _fg_item_rule():
    print("=== 1. finished-goods item rule (new items) ===")
    good = _fg(create_new_batch=1)
    check("Kg / Nos / batch saves", _refused(good)[0], False)
    check("Create New Batch is switched off", good.create_new_batch, 0)

    refused, msg = _refused(_fg(stock_uom="Nos"))
    check("stock UOM Nos is refused", refused, True)
    check("  and says why", "must be Kg" in msg, True)
    check("Secondary UOM other than Nos is refused", _refused(_fg(custom_secondary_uom="Kg"))[0], True)
    check("no Secondary UOM is refused", _refused(_fg(custom_secondary_uom=None))[0], True)
    refused, msg = _refused(_fg(has_batch_no=0))
    check("no batch is refused", refused, True)
    check("  and says why", "Has Batch No" in msg, True)
    check("a batch prefix is refused", _refused(_fg(custom_batch_prefix="FAB"))[0], True)

    print()
    print("=== 1b. an FG item with transactions keeps its old set-up ===")
    fingoods = frappe.get_doc("Item", "FINGOODS001")
    refused, _ = _refused(fingoods)
    check("FINGOODS001 (Nos, no batch) still validates", refused, False)
    notes = " ".join(str(m) for m in (frappe.local.message_log or []))
    check("  with an orange note", "does not follow the Kg / Nos set-up" in notes, True)
    frappe.clear_messages()
    # In memory only: nothing on FINGOODS001 was changed or saved.
    check("  and nothing on it changed", fingoods.stock_uom, frappe.db.get_value("Item", "FINGOODS001", "stock_uom"))


def _prefix_guard():
    print()
    print("=== 2. FG is not a raw-material batch prefix ===")
    plate = dict(custom_parent_item_group="Plates", stock_uom="Kg", custom_secondary_uom="Nos",
                 has_batch_no=1)
    for prefix in ("FG", "fg", " Fg ", "FG-X"):
        refused, msg = _refused(_new_item(custom_batch_prefix=prefix, **plate))
        check("prefix %r is refused" % prefix, refused, True)
    check("  and says it is reserved", "reserved for finished-goods" in msg, True)
    check("prefix 'FGX' is allowed", _refused(_new_item(custom_batch_prefix="FGX", **plate))[0], False)
    check("prefix 'PLT8' is allowed", _refused(_new_item(custom_batch_prefix="PLT8", **plate))[0], False)


def _stock_reconciliation():
    print()
    print("=== 3. Stock Reconciliation is blocked ===")
    check("server message is the agreed wording", BLOCKED_MESSAGE, EXPECTED_MESSAGE)

    company = frappe.db.get_value("Warehouse", "Stores - MIPL", "company")
    item = "ZZFG-RM-NUT" if frappe.db.exists("Item", "ZZFG-RM-NUT") else "Nut-M20"
    for purpose in ("Stock Reconciliation", "Opening Stock"):
        before = frappe.db.count("Stock Reconciliation")
        sr = frappe.get_doc({
            "doctype": "Stock Reconciliation", "company": company, "purpose": purpose,
            "items": [{"item_code": item, "warehouse": "Stores - MIPL", "qty": 5,
                       "valuation_rate": 10}],
        })
        if purpose == "Opening Stock":
            sr.expense_account = frappe.db.get_value(
                "Account", {"company": company, "account_type": "Temporary", "is_group": 0}, "name")
        try:
            sr.insert(ignore_permissions=True)
            refused, msg = False, ""
        except frappe.ValidationError as e:
            refused, msg = True, str(e)
        frappe.db.rollback()
        check("%s: save refused" % purpose, refused, True)
        check("%s: with the agreed message" % purpose, EXPECTED_MESSAGE in msg, True)
        check("%s: nothing written" % purpose, frappe.db.count("Stock Reconciliation"), before)

    js_path = os.path.join(frappe.get_app_path("manufyxinvenzaerp"), "public", "js", "stock_reconciliation.js")
    js = open(js_path).read()
    check("form shows the same message", EXPECTED_MESSAGE in js, True)
    check("form disables Save", "frm.disable_save()" in js, True)
    hooks = frappe.get_hooks("doctype_js").get("Stock Reconciliation") or []
    check("form script is registered", "public/js/stock_reconciliation.js" in hooks, True)


def run():
    for part in (_fg_item_rule, _prefix_guard, _stock_reconciliation):
        try:
            part()
        except Exception as e:
            checks.append(False)
            print("  FAIL %s raised %s: %s" % (part.__name__, type(e).__name__, e))
    frappe.db.rollback()

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
