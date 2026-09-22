"""Picking "Finished Goods" sets the item up the way the server will accept.

The rule was already enforced -- item.validate_fg_configuration refuses an FG item
that is not Kg / Nos, batched, with no batch abbreviation -- but only on save, and
the form offered no help getting there. Choosing the group left the UOMs on
whatever they were, showed a Custom Batch Abbreviation field that had to be left
empty, and the only way to find any of this out was to fill the form in and be
refused.

Now the group selection fills in Kg and Nos, the same pair the formula groups get,
and the abbreviation is hidden for finished goods -- their batches are named by
fg_stock.get_or_create_fg_batch (FG-<Sales Order>-<DUNO>), so there is nothing to
abbreviate.

Hidden is not enough on its own: an item moved to Finished Goods from a group that
had an abbreviation would still submit the old value from behind the hidden field,
and the server refuses exactly that -- a refusal with nothing on screen to explain
it. So it is cleared as well as hidden.

public/js/item.js is BUNDLED. The source file is not what the browser runs, so
these checks read the built asset in public/dist as well; without the build, the
form behaves exactly as it did before and nothing here would say so.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_item_form_defaults.run
"""

import glob
import os

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-60s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _refused(doc):
    """(refused?, message) from running THIS APP's Item validate hook on an unsaved doc.

    validate_item directly, not doc.run_method("validate"): the latter runs
    ERPNext's whole Item controller, which reads _doc_before_save and blows up on a
    document that was never saved -- an error from the harness that looks exactly
    like a refusal from the rule under test.
    """
    from manufyxinvenzaerp.item_management.item import validate_item

    frappe.clear_messages()
    try:
        validate_item(doc, "validate")
    except frappe.ValidationError as e:
        return True, frappe.utils.strip_html(str(e))
    return False, ""


def _fg_item(**overrides):
    base = dict(
        doctype="Item", item_code="ZZFG-FORMDEFAULTS", item_name="ZZFG-FORMDEFAULTS",
        item_group="All Item Groups", is_stock_item=1,
        custom_parent_item_group="Finished Goods", stock_uom="Kg",
        custom_secondary_uom="Nos", has_batch_no=1, create_new_batch=0,
    )
    base.update(overrides)
    return frappe.get_doc(base)


def run():
    src = open(frappe.get_app_path("manufyxinvenzaerp", "public", "js", "item.js")).read()

    print("=== 1. the form fills in Kg / Nos when Finished Goods is chosen ===")
    check("the group is named as a constant", 'const FG_GROUP = "Finished Goods"' in src, True)
    uom_fn = src.split("function set_default_uoms")[1].split("\nfunction ")[0]
    check("finished goods take the Kg / Nos branch",
          "FORMULA_GROUPS.includes(group) || group === FG_GROUP" in uom_fn, True)
    check("  which sets Kg", 'frm.set_value("stock_uom", "Kg")' in uom_fn, True)
    check("  and Nos", 'frm.set_value("custom_secondary_uom", "Nos")' in uom_fn, True)
    # Nuts and Bolts is the opposite way round and must not have been caught up in it.
    nb = uom_fn.split('group === "Nuts and Bolts"')[1]
    check("Nuts and Bolts is still Nos / Kg",
          'frm.set_value("stock_uom", "Nos")' in nb and 'frm.set_value("custom_secondary_uom", "Kg")' in nb,
          True)

    print("\n=== 2. it runs when the group is picked, not only on reload ===")
    handler = src.split("custom_parent_item_group(frm)")[1].split("\n\t},")[0]
    check("set_default_uoms is called", "set_default_uoms(frm)" in handler, True)
    check("apply_batch_ui is called", "apply_batch_ui(frm)" in handler, True)

    print("\n=== 3. Custom Batch Abbreviation is hidden for finished goods ===")
    batch_fn = src.split("function apply_batch_ui")[1].split("\nfunction ")[0]
    check("the form knows what an FG item is",
          "frm.doc.custom_parent_item_group === FG_GROUP" in batch_fn, True)
    check("the abbreviation is hidden for them",
          'frm.toggle_display("custom_batch_prefix", has_batch && !is_fg)' in batch_fn, True)
    check("and cleared, not just hidden",
          'frm.set_value("custom_batch_prefix", "")' in batch_fn, True)
    # Still shown for a batched raw material -- that is where it is required.
    check("still shown for other groups when batched",
          "has_batch && !is_fg" in batch_fn and "has_batch_no" not in batch_fn.split("toggle_display")[0].split("const has_batch")[0],
          True)

    print("\n=== 4. the built bundle is what the browser actually runs ===")
    dist = glob.glob(frappe.get_app_path(
        "manufyxinvenzaerp", "public", "dist", "js", "manufyxinvenzaerp.bundle.*.js"))
    dist = [p for p in dist if not p.endswith(".map")]
    check("a bundle is built", bool(dist), True)
    if dist:
        newest = max(dist, key=os.path.getmtime)
        built = open(newest).read()
        src_mtime = os.path.getmtime(
            frappe.get_app_path("manufyxinvenzaerp", "public", "js", "item.js"))
        check("the bundle carries the FG group", '"Finished Goods"' in built, True)
        check("  and the hide-and-clear", 'custom_batch_prefix' in built, True)
        # The trap this app documents: editing public/js changes nothing until
        # `bench build --app manufyxinvenzaerp` runs.
        check("the bundle is not older than the source",
              os.path.getmtime(newest) >= src_mtime, True)

    print("\n=== 5. the server still refuses anything else (unchanged) ===")
    refused, msg = _refused(_fg_item(stock_uom="Nos"))
    check("stock UOM Nos is refused", refused, True)
    check("  and says it must be Kg", "must be Kg" in msg, True)
    refused, msg = _refused(_fg_item(custom_secondary_uom="Kg"))
    check("Secondary UOM Kg is refused", refused, True)
    check("  and says it must be Nos", "must be Nos" in msg, True)
    refused, msg = _refused(_fg_item(custom_batch_prefix="FAB"))
    check("an abbreviation is refused", refused, True)
    check("  and says it must be blank", "must be blank" in msg, True)
    good = _fg_item()
    check("Kg / Nos / batched / no abbreviation passes", _refused(good)[0], False)
    check("  and Create New Batch is forced off", good.create_new_batch, 0)

    frappe.clear_messages()
    total, passed = len(checks), sum(checks)
    print("\n%s %d/%d CHECKS PASSED" % ("ALL" if passed == total else "ONLY", passed, total))
    return passed == total
