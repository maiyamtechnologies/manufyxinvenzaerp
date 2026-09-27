import frappe
def run():
    for f in frappe.get_all("Custom Field", filters={"dt": "Stock Entry", "fieldname": ["like", "custom_consumable%"]},
                            fields=["fieldname", "reqd", "mandatory_depends_on"], order_by="idx"):
        print(f)
