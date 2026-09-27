import frappe
from erpnext.stock.doctype.batch.batch import get_batch_qty
def run():
    for b,i in (("ISMB450-L7331-R004","ISMB450"),("ISMB400-L6936-R003","ISMB400")):
        kg = get_batch_qty(batch_no=b, warehouse="Stores - MIPL", item_code=i)
        nos = frappe.db.get_value("Batch", b, "custom_sec_qty")
        print(f"  {b:24} stock={kg:>10.3f} Kg   custom_sec_qty={nos}")
