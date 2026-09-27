import frappe
from manufyxinvenzaerp.item_management.item import validate_item

def run():
    """In-memory only: builds an unsaved doc and prints the refusal. No insert, no commit."""
    for label, over in (
        ("primary UOM wrong (Nos)", dict(stock_uom="Nos")),
        ("secondary UOM wrong (Kg)", dict(custom_secondary_uom="Kg")),
        ("both wrong", dict(stock_uom="Nos", custom_secondary_uom="Kg")),
        ("abbreviation filled in", dict(custom_batch_prefix="FAB")),
    ):
        d = dict(doctype="Item", item_code="(unsaved)", item_name="(unsaved)",
                 item_group="Fin Goods Item", is_stock_item=1,
                 custom_parent_item_group="Finished Goods", stock_uom="Kg",
                 custom_secondary_uom="Nos", has_batch_no=1, create_new_batch=0)
        d.update(over)
        doc = frappe.get_doc(d)
        print("\n--- %s ---" % label)
        try:
            validate_item(doc, "validate")
            print("  (accepted)")
        except frappe.ValidationError as e:
            print("  " + frappe.utils.strip_html(str(e)).strip().replace("\n", "\n  "))
    frappe.db.rollback()
