import frappe


def run():
    used = set(frappe.get_all("Cut Sheet", pluck="batch_no"))
    free = frappe.db.sql("""SELECT b.name, b.item FROM tabBatch b WHERE b.name NOT IN %s LIMIT 1""",
                         (tuple(used) or ("",),), as_dict=True)
    if not free:
        print("    no free batch to try"); return
    b = free[0]
    new = frappe.new_doc("Cut Sheet")
    new.update({
        "company": frappe.db.get_value("Company", {}, "name"),
        "batch_no": b.name, "item_code": b.item,
        "warehouse": frappe.db.get_value("Warehouse", {"is_group": 0}, "name"),
        "w1_length": 1000, "w1_sec_qty": 1,
    })
    try:
        new.insert(ignore_permissions=True)
        print("    a NEW sheet chooses batch/item/warehouse freely: OK (%s on %s)" % (new.name, b.name))
    except Exception as e:
        print("    new sheet blocked <-- bad: %s" % frappe.utils.strip_html(str(e))[:140])
    frappe.db.rollback()
