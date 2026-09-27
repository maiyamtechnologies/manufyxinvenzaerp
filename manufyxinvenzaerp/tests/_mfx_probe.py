import json
import frappe

def run():
    for dt in ("Material Planning Material Mapping", "Material Planning Available Raw Material"):
        order = frappe.db.get_value("Property Setter",
                                    {"doc_type": dt, "property": "field_order"}, "value")
        if order:
            names = json.loads(order)
            print("%-42s pinned field_order: cnc_process present=%s (%d fields)" % (
                dt, "cnc_process" in names, len(names)))
        else:
            print("%-42s no pinned field_order" % dt)
        df = frappe.get_meta(dt).get_field("cnc_process")
        print("     in_list_view=%r hidden=%r read_only=%r" % (
            df.in_list_view, df.hidden, df.read_only))
