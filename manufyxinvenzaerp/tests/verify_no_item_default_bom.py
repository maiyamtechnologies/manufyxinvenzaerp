"""No Item carries a default BOM, and a Sales Order line never arrives with one.

An item here is a shape of steel, not a product. One finished-goods item has hundreds
of BOMs -- one per drawing -- and which one applies is decided by the drawing, never by
the item.

Stock ERPNext assumes the opposite. It nominates one BOM as the item's default and
stamps it on the Item master, and `get_item_details` then hands that BOM to every Sales
Order line for the item. Two things go wrong with that here:

  * a Sales Order line starts out carrying an arbitrary drawing's BOM, which nobody
    asked for and nobody notices; and
  * the moment that BOM is gone, the Sales Order will not open at all --
    "Could not find Row #1: BOM No: BOM-FINGOODS001-245" -- because the Item still
    points at it.

BOM.manage_default_bom is overridden to keep the flag clear and the field empty, and
after_migrate sweeps up anything set by a route outside it: an import, a manual edit on
the Item form, or a site restored from a database that predates the override.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_no_item_default_bom.run
"""

import frappe
from frappe.utils import add_days, nowdate

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-54s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    print("=== nothing on the site carries one ===")
    check("no Item has a default BOM",
          frappe.get_all("Item", filters={"default_bom": ["!=", ""]}, pluck="name"), [])
    # Submitted only. ERPNext defaults is_default to 1 on a new BOM and
    # manage_default_bom -- the override that clears it -- runs on submit, cancel and
    # update-after-submit, never on the insert of a draft. A draft carrying the flag has
    # not reached the Item and never will; after_migrate's sweep clears it regardless.
    # Asserting over every BOM failed the moment a test created a draft one.
    check("no submitted BOM is flagged as the default",
          frappe.db.count("BOM", {"is_default": 1, "docstatus": 1}), 0)

    print()
    print("=== and a Sales Order line does not pick one up ===")
    company = frappe.get_all("Company", pluck="name")[0]
    customer = frappe.db.get_value("Customer", {}, "name")
    item = _item_with_a_bom() or frappe.db.get_value("Item", {"is_stock_item": 1}, "name")
    if not (customer and item):
        print("   No Customer or Item on this site to build a line from.")
    else:
        from erpnext.stock.get_item_details import get_item_details

        details = get_item_details(frappe._dict({
            "item_code": item, "company": company, "customer": customer,
            "doctype": "Sales Order", "qty": 1, "conversion_rate": 1,
            "currency": frappe.get_cached_value("Company", company, "default_currency"),
            "price_list": "Standard Selling", "plc_conversion_rate": 1,
            "transaction_type": "selling", "transaction_date": nowdate(),
        }))
        check("%s fetches no BOM" % item, details.get("bom_no"), None)

        # The real failure was on insert, not on the fetch, so the document is built.
        so = frappe.new_doc("Sales Order")
        so.customer = customer
        so.company = company
        so.transaction_date = nowdate()
        so.delivery_date = add_days(nowdate(), 7)
        so.append("items", {"item_code": item, "qty": 1, "rate": 2,
                            "delivery_date": add_days(nowdate(), 7)})
        try:
            so.insert(ignore_permissions=True)
            check("a draft Sales Order saves", True, True)
            check("and its row carries no BOM", so.items[0].get("bom_no"), None)
        except Exception as e:
            check("a draft Sales Order saves", "%s: %s" % (type(e).__name__, str(e)[:80]), True)
        finally:
            frappe.db.rollback()

    print()
    print("=== the override is what keeps it that way ===")
    src = open(frappe.get_app_path("manufyxinvenzaerp", "drawing_management",
                                   "bom_class_override.py")).read()
    body = src[src.index("def manage_default_bom(self):"):]
    body = body[:body.index("\n\tdef ")]
    check("it never writes a BOM name onto the Item",
          'set_value("Item", self.item, "default_bom", self.name)' in body, False)
    check("it clears the field instead",
          'frappe.db.set_value("Item", self.item, "default_bom", None)' in body, True)
    check("and clears the flag on the BOM",
          'self.db_set("is_default", 0)' in body, True)
    # The override is a thin subclass, so on_submit / on_cancel / on_update_after_submit
    # are ERPNext's own -- and they must still be the ones calling it.
    import inspect

    from erpnext.manufacturing.doctype.bom.bom import BOM as ERPNextBOM

    for event in ("on_submit", "on_cancel", "on_update_after_submit"):
        check("still called on %s" % event.replace("on_", ""),
              "self.manage_default_bom()" in inspect.getsource(getattr(ERPNextBOM, event)), True)

    setup = open(frappe.get_app_path("manufyxinvenzaerp", "setup.py")).read()
    check("and a migrate sweeps up anything set elsewhere",
          "clear_item_default_boms()" in setup, True)

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))


def _item_with_a_bom():
    """Prefer an item that actually has BOMs -- that is the item stock ERPNext would
    have nominated a default for, so it is the one worth checking."""
    return frappe.db.get_value("BOM", {"docstatus": ["<", 2]}, "item")
