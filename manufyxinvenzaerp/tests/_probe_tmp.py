import frappe
def run():
    for s in frappe.get_all("Supplier Operation Entry",
                            filters={"subcontracting_order": "SC-ORD-2026-00003"},
                            fields=["name","sequence_id","operation"], order_by="sequence_id"):
        n = frappe.db.count("SOE Drawing Detail", {"parent": s.name})
        print("  %s seq=%s %-10s drawing rows=%d" % (s.name, s.sequence_id, s.operation, n))
    print("SCO drawing items:", frappe.db.count("SCO Drawing Item",
          {"parent": "SC-ORD-2026-00003", "parenttype": "Subcontracting Order"}))
    print("Manufacture SEs:", frappe.get_all("Stock Entry",
          filters={"subcontracting_order": "SC-ORD-2026-00003", "stock_entry_type": "Manufacture"},
          fields=["name","docstatus"]))
