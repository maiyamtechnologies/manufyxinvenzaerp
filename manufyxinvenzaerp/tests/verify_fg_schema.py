"""Wave 0 of the finished-goods Kg / Nos plan: the schema, hooks and stubs are all there.

sep14 FG plan (.claude/tasks/sep14_fg_uom_plan.md), package A0. Every later agent
codes against what A0 laid down -- the fields in section 4.1, the two settings, the
hook registrations and the fg_stock contract -- and is told not to add fields or
touch hooks.py itself. So if a field is missing or mislabelled, or a hook points at
nothing, the failure would surface much later as somebody else's bug. This pins it.

It also pins three things that went wrong, or nearly did, while building it:

  - Frappe's grid stops drawing columns once their widths pass 11 (see
    setup.layout_purchase_receipt_item_grid). Qty (Nos) is only "in the list view"
    if it is inside that budget, so the checks work the budget out the same way the
    grid does and look for the column among the ones actually drawn.
  - A new Single field has no row in tabSingles, and get_single_value then reads 0,
    not the field's default. The settings are checked as STORED, not just in meta.
  - Custom fields live twice: setup.py (wins on migrate) and custom/<doctype>.json
    (synced on migrate). Each new field is checked in the JSON too, against the
    database, so the two cannot drift apart unnoticed.

Read-only: it creates, changes and deletes nothing.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_schema.run
"""

import inspect
import json
import os

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-72s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


# (doctype, fieldname, label, fieldtype, {other docfield properties expected})
FIELDS = [
    ("Manufyxinvenza Settings", "edit_fg_stock_kg", "Edit FG Stock Kg", "Check", {"default": "1"}),
    ("Manufyxinvenza Settings", "fg_weight_difference_warning_percent", "FG Weight Difference Warning (%)",
     "Percent", {"default": "5"}),
    ("Sales Order DUNO Item", "weight_per_pcs", "Cust Weight (per Nos)", "Float",
     {"read_only_depends_on": "eval:doc.drawing || doc.docstatus===1"}),
    ("Sales Order DUNO Item", "total_weight", "Cust Weight (Total)", "Float",
     {"read_only_depends_on": "eval:doc.drawing || doc.docstatus===1"}),
    ("Sales Order DUNO Item", "total_quantity", "Total Quantity", "Float",
     {"read_only_depends_on": "eval:doc.drawing || doc.docstatus===1"}),
    ("Sales Order Item", "custom_sec_qty", "NOS", "Float", {"in_list_view": 1, "read_only": 0}),
    ("Sales Order Item", "custom_sec_uom", "Sec UOM", "Link", {"options": "UOM", "default": "Nos", "read_only": 1}),
    ("Sales Order Item", "custom_delivered_sec_qty", "Delivered NOS", "Float", {"read_only": 1, "no_copy": 1}),
    ("Sales Order Item", "custom_billed_sec_qty", "Billed NOS", "Float", {"read_only": 1, "no_copy": 1}),
    ("Drawing", "weight_per_pcs", "Cust Weight (per Nos)", "Float",
     {"read_only": 1, "description": "Change with Update Customer Weight."}),
    ("Drawing", "customer_provided_wt", "Cust Weight (Total)", "Float",
     {"description": "Cust Weight (per Nos) × No of Qty to Manufacture. Calculated."}),
    ("BOM", "custom_sec_qty", "NOS", "Float", {"read_only": 1}),
    ("BOM", "custom_sec_uom", "Sec UOM", "Link", {"options": "UOM", "default": "Nos", "read_only": 1}),
    ("BOM", "custom_cust_weight_per_nos", "Cust Weight (per Nos)", "Float", {"read_only": 1}),
    ("BOM", "custom_cust_weight_total", "Cust Weight (Total)", "Float", {"read_only": 1}),
    ("Production Plan Item", "custom_sec_qty", "NOS", "Float", {"in_list_view": 1, "read_only": 0}),
    ("Production Plan Item", "custom_sec_uom", "Sec UOM", "Link", {"options": "UOM", "default": "Nos", "read_only": 1}),
    ("Production Plan Item", "custom_cust_weight_per_nos", "Cust Weight (per Nos)", "Float", {"read_only": 1}),
    ("Production Plan Item", "custom_customer_weight_kg", "Cust Weight (Total)", "Float", {}),
    ("Production Plan Item", "planned_qty", "Planned Qty (Kg)", "Float",
     {"read_only_depends_on": "eval:doc.custom_drawing"}),
    ("Subcontracting Order Item", "custom_sec_qty", "NOS", "Float", {"read_only": 1}),
    ("Subcontracting Order Item", "custom_sec_uom", "Sec UOM", "Link", {"options": "UOM", "default": "Nos", "read_only": 1}),
    ("Subcontracting Order", "custom_customer_weight_kg", "Cust Weight (Total)", "Float", {"read_only": 1}),
    ("SCO Drawing Item", "cust_weight_per_nos", "Cust Weight (per Nos)", "Float", {"read_only": 1}),
    ("SCO Drawing Item", "customer_weight_kg", "Cust Weight (Total)", "Float", {"read_only": 1}),
    ("SCO Drawing Item", "rate_per_kg", "Rate / Kg", "Currency", {"read_only": 1}),
    ("SCO Drawing Item", "job_work_amount", "Job Work Amount", "Currency", {"read_only": 1}),
    ("SOE Drawing Detail", "customer_provided_weight_kg", "Cust Weight (Total)", "Float", {"read_only": 1}),
    ("Material Planning BOM Item", "customer_provided_weight_kg", "Cust Weight (Total)", "Float", {"read_only": 1}),
    ("Batch", "custom_fg_details_section", "FG Details", "Section Break",
     {"collapsible": 1, "depends_on": "eval:doc.custom_sales_order"}),
    ("Batch", "custom_sales_order", "Sales Order", "Link", {"options": "Sales Order", "read_only": 1}),
    ("Batch", "custom_customer", "Customer", "Link", {"options": "Customer", "read_only": 1}),
    ("Batch", "custom_drawing", "Drawing", "Link", {"options": "Drawing", "read_only": 1}),
    ("Batch", "custom_duno_mark_no", "DUNO/Mark No", "Data", {"read_only": 1}),
    ("Batch", "custom_customer_drawing_number", "Cust Drawing Number", "Data", {"read_only": 1}),
    ("Batch", "custom_job_work_order", "Job Work Order", "Link", {"options": "Subcontracting Order", "read_only": 1}),
    ("Batch", "custom_cust_weight_per_nos", "Planned Kg per Nos", "Float", {"read_only": 1}),
    ("Batch", "custom_weight_per_piece", "Actual Kg per Nos", "Float", {"read_only": 1}),
    ("Stock Entry Detail", "custom_sec_qty", "NOS", "Float", {"in_list_view": 1}),
    ("Stock Entry Detail", "custom_drawing", "Drawing", "Link", {}),
    ("Stock Entry Detail", "custom_duno_mark_no", "DUNO/Mark No", "Data", {}),
    ("Delivery Note Item", "custom_drawing", "Drawing", "Link", {"options": "Drawing", "read_only": 1}),
    ("Delivery Note Item", "custom_duno_mark_no", "DUNO/Mark No", "Data", {"read_only": 1}),
    ("Delivery Note Item", "custom_sec_uom", "Sec UOM", "Link", {"options": "UOM", "read_only": 1, "default": None}),
    ("Delivery Note Item", "custom_sec_qty", "NOS", "Float", {"in_list_view": 1, "read_only": 0}),
    ("Delivery Note Item", "custom_billed_sec_qty", "Billed NOS", "Float", {"read_only": 1, "no_copy": 1}),
    ("Delivery Note Item", "qty", "Quantity", "Float", {"read_only_depends_on": "eval:doc.custom_sec_uom"}),
    ("Sales Invoice Item", "custom_drawing", "Drawing", "Link", {"options": "Drawing", "read_only": 1}),
    ("Sales Invoice Item", "custom_duno_mark_no", "DUNO/Mark No", "Data", {"read_only": 1}),
    ("Sales Invoice Item", "custom_sec_qty", "NOS", "Float", {"in_list_view": 1, "read_only": 0}),
    ("Sales Invoice Item", "custom_sec_uom", "Sec UOM", "Link", {"options": "UOM", "read_only": 1, "default": None}),
    ("Sales Invoice Item", "qty", "Quantity", "Float", {"read_only_depends_on": "eval:doc.custom_sec_uom"}),
    ("Item", "opening_stock", "Opening Stock", "Float", {"hidden": 1}),
]

# Grids that must show Qty (Nos), and what left the row view to pay for it.
GRIDS = {
    "Sales Order Item": {"hidden_from_grid": ["delivery_date"]},
    "Delivery Note Item": {"hidden_from_grid": ["uom"]},
    "Sales Invoice Item": {"hidden_from_grid": []},
    "Production Plan Item": {"hidden_from_grid": ["custom_item_name"]},
    "Stock Entry Detail": {"hidden_from_grid": []},
}

# Each custom field A0 added or relabelled, and the file that must carry it.
JSON_FILES = {
    "Sales Order Item": "drawing_management/custom/sales_order_item.json",
    "BOM": "drawing_management/custom/bom.json",
    "Production Plan Item": "production_management/custom/production_plan_item.json",
    "Subcontracting Order Item": "subcontracting_management/custom/subcontracting_order_item.json",
    "Subcontracting Order": "subcontracting_management/custom/subcontracting_order.json",
    "Batch": "manufyxinvenzaerp/custom/batch.json",
    "Delivery Note Item": "manufyxinvenzaerp/custom/delivery_note_item.json",
    "Sales Invoice Item": "manufyxinvenzaerp/custom/sales_invoice_item.json",
    "Item": "manufyxinvenzaerp/custom/item.json",
}

# (doctype, field_name, property, value) that must be Property Setters in DB and JSON.
PROPERTY_SETTERS = [
    ("Production Plan Item", "planned_qty", "label", "Planned Qty (Kg)"),
    ("Production Plan Item", "planned_qty", "read_only_depends_on", "eval:doc.custom_drawing"),
    ("Delivery Note Item", "qty", "read_only_depends_on", "eval:doc.custom_sec_uom"),
    ("Sales Invoice Item", "qty", "read_only_depends_on", "eval:doc.custom_sec_uom"),
    ("Item", "opening_stock", "hidden", "1"),
    ("Sales Order Item", "delivery_date", "in_list_view", "0"),
    ("Delivery Note Item", "uom", "in_list_view", "0"),
    ("Sales Invoice Item", "item_code", "columns", "3"),
]

PREFIX = "manufyxinvenzaerp."
DOC_EVENTS = [
    ("Stock Reconciliation", "validate", "stock_management.stock_reconciliation.block_stock_reconciliation"),
    ("Production Plan", "validate", "production_plan_management.production_plan.apply_fg_nos"),
    ("Stock Entry", "validate", "production_management.fg_stock.validate_fg_stock_entry_rows"),
    ("Stock Entry", "on_submit", "production_management.fg_stock.on_fg_stock_entry_change"),
    ("Stock Entry", "on_cancel", "production_management.fg_stock.on_fg_stock_entry_change"),
    ("Delivery Note", "validate", "selling_management.delivery_note.validate_delivery_note"),
    ("Delivery Note", "on_submit", "selling_management.delivery_note.on_submit_delivery_note"),
    ("Delivery Note", "on_cancel", "selling_management.delivery_note.on_cancel_delivery_note"),
    ("Sales Invoice", "validate", "selling_management.sales_invoice.validate_sales_invoice"),
    ("Sales Invoice", "on_submit", "selling_management.sales_invoice.on_submit_sales_invoice"),
    ("Sales Invoice", "on_cancel", "selling_management.sales_invoice.on_cancel_sales_invoice"),
]
# The existing handlers must still run, and before the new ones.
MUST_STAY_FIRST = [
    ("Stock Entry", "validate", "production_management.stock_entry.validate_stock_entry"),
    ("Stock Entry", "on_submit", "production_management.stock_entry.on_submit_stock_entry"),
    ("Stock Entry", "on_cancel", "production_management.stock_entry.on_cancel_stock_entry"),
    ("Production Plan", "validate", "production_plan_management.production_plan.after_save_production_plan"),
]

OVERRIDES = {
    "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note":
        "manufyxinvenzaerp.selling_management.mapping.make_delivery_note",
    "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice":
        "manufyxinvenzaerp.selling_management.mapping.make_sales_invoice_from_so",
    "erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice":
        "manufyxinvenzaerp.selling_management.mapping.make_sales_invoice_from_dn",
}

DOCTYPE_JS = {
    "Delivery Note": "public/js/delivery_note.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Stock Reconciliation": "public/js/stock_reconciliation.js",
    "Stock Entry": "public/js/stock_entry_fg.js",
}


def _norm(value):
    """Docfield values come back as 0/None/'' interchangeably; compare them as one."""
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, int):
        return str(value)
    return value


# frappe.model.layout_fields on the JS side (frappe/model/model.js).
LAYOUT_FIELDS = ("Section Break", "Column Break", "Tab Break", "Fold")


def _visible_grid_columns(doctype):
    """The columns Frappe's grid actually draws (grid.js setup_visible_columns)."""
    total, visible = 1, []
    for df in frappe.get_meta(doctype).fields:
        if not df.in_list_view or df.hidden or df.fieldtype in LAYOUT_FIELDS:
            continue
        size = df.columns or (3 if df.fieldtype == "Small Text" else 1 if df.fieldtype == "Check" else 2)
        if total + size > 11:
            break  # the grid stops here, and draws nothing after it
        total += size
        visible.append(df.fieldname)
    return visible, total


def _check_fields():
    print("\n1. Fields, labels and properties (frappe.get_meta)")
    for doctype, fieldname, label, fieldtype, props in FIELDS:
        df = frappe.get_meta(doctype).get_field(fieldname)
        where = "%s.%s" % (doctype, fieldname)
        check(where + " exists", bool(df), True)
        if not df:
            continue
        check(where + " label", df.label, label)
        check(where + " fieldtype", df.fieldtype, fieldtype)
        for prop, want in props.items():
            check("%s %s" % (where, prop), _norm(df.get(prop)), _norm(want))


def _check_grids():
    print("\n2. Qty (Nos) inside each grid's column budget")
    for doctype, spec in GRIDS.items():
        visible, total = _visible_grid_columns(doctype)
        check("%s grid shows custom_sec_qty (%s)" % (doctype, ", ".join(visible)),
              "custom_sec_qty" in visible, True)
        check("%s grid within budget (total %d)" % (doctype, total), total <= 11, True)
        for fieldname in spec["hidden_from_grid"]:
            check("%s.%s out of the row view" % (doctype, fieldname),
                  frappe.get_meta(doctype).get_field(fieldname).in_list_view, 0)


def _check_settings():
    print("\n3. Settings stored with their defaults")
    from manufyxinvenzaerp.production_management import fg_stock

    for fieldname, want in (("edit_fg_stock_kg", "1"), ("fg_weight_difference_warning_percent", "5")):
        stored = frappe.db.sql(
            "SELECT value FROM `tabSingles` WHERE doctype='Manufyxinvenza Settings' AND field=%s",
            fieldname,
        )
        # Only "is there a row" is asserted strictly: the value is the client's to change.
        check("tabSingles has " + fieldname, bool(stored), True)
        print("       stored value: %r (default %s)" % (stored[0][0] if stored else None, want))
    check("fg_stock.edit_fg_stock_kg_enabled() is a bool",
          isinstance(fg_stock.edit_fg_stock_kg_enabled(), bool), True)
    check("fg_stock.fg_weight_difference_warning_percent() is a float",
          isinstance(fg_stock.fg_weight_difference_warning_percent(), float), True)


def _check_json_agrees():
    print("\n4. custom/<doctype>.json carries every A0 field and property setter as in the DB")
    app = frappe.get_app_path("manufyxinvenzaerp")
    compare = ("label", "fieldtype", "options", "insert_after", "in_list_view", "columns",
               "read_only", "no_copy", "default", "depends_on", "collapsible", "read_only_depends_on")
    by_doctype = {}
    for doctype, fieldname, *_ in FIELDS:
        if doctype in JSON_FILES and fieldname.startswith("custom_"):
            by_doctype.setdefault(doctype, []).append(fieldname)
    for doctype, rel in JSON_FILES.items():
        path = os.path.join(app, rel)
        data = json.load(open(path))
        check("%s sync_on_migrate" % rel, data.get("sync_on_migrate"), 1)
        in_file = {r["fieldname"]: r for r in data["custom_fields"]}
        for fieldname in by_doctype.get(doctype, []):
            db = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, compare, as_dict=True)
            rec = in_file.get(fieldname)
            if not db:
                # Relabelled standard/Stock Entry fields defined elsewhere are covered by section 1.
                continue
            check("%s: %s in JSON" % (rel.split("/")[-1], fieldname), bool(rec), True)
            if rec:
                diff = [k for k in compare if _norm(rec.get(k)) != _norm(db.get(k))]
                check("%s: %s JSON == DB" % (rel.split("/")[-1], fieldname), diff, [])
    for doctype, field_name, prop, value in PROPERTY_SETTERS:
        db_value = frappe.db.get_value(
            "Property Setter", {"doc_type": doctype, "field_name": field_name, "property": prop}, "value"
        )
        check("Property Setter %s.%s.%s" % (doctype, field_name, prop), db_value, value)
        data = json.load(open(os.path.join(app, JSON_FILES[doctype])))
        rec = [r for r in data["property_setters"]
               if r["field_name"] == field_name and r["property"] == prop]
        check("  ...and in %s" % JSON_FILES[doctype].split("/")[-1],
              str(rec[0]["value"]) if rec else None, value)


def _check_hooks():
    print("\n5. Hooks resolve")
    doc_events = frappe.get_hooks("doc_events")
    for doctype, event, path in DOC_EVENTS:
        handlers = doc_events.get(doctype, {}).get(event, [])
        check("doc_events %s.%s -> %s" % (doctype, event, path.split(".")[-1]), PREFIX + path in handlers, True)
        fn = frappe.get_attr(PREFIX + path)
        check("  ...importable and callable", callable(fn), True)
    for doctype, event, path in MUST_STAY_FIRST:
        handlers = [h for h in doc_events.get(doctype, {}).get(event, []) if h.startswith(PREFIX)]
        check("%s.%s still runs %s first" % (doctype, event, path.split(".")[-1]),
              handlers[:1], [PREFIX + path])

    overrides = frappe.get_hooks("override_whitelisted_methods")
    for original, ours in OVERRIDES.items():
        check("override %s" % original.split(".")[-1] + " (" + original.split(".")[-2] + ")",
              frappe.override_whitelisted_method(original), ours)
        check("  ...registered once", overrides.get(original), [ours])
        fn = frappe.get_attr(ours)
        check("  ...whitelisted", fn in frappe.whitelisted, True)
        orig_params = list(inspect.signature(frappe.get_attr(original)).parameters)
        check("  ...same parameters as ERPNext", list(inspect.signature(fn).parameters), orig_params)

    doctype_js = frappe.get_hooks("doctype_js", app_name="manufyxinvenzaerp")
    app = frappe.get_app_path("manufyxinvenzaerp")
    for doctype, rel in DOCTYPE_JS.items():
        check("doctype_js %s" % doctype, rel in (doctype_js.get(doctype) or []), True)
        check("  ...%s exists" % rel, os.path.exists(os.path.join(app, rel)), True)


def _check_fg_stock():
    print("\n6. fg_stock contract")
    from manufyxinvenzaerp.production_management import fg_stock

    check('is_fg_item("Fabricated Structurs")', fg_stock.is_fg_item("Fabricated Structurs"), True)
    rm = frappe.db.get_value("Item", {"custom_parent_item_group": ["in", ["Plates", "Structurals"]]}, "name")
    check("a raw-material item exists to test with", bool(rm), True)
    check("is_fg_item(%r) (raw material)" % rm, fg_stock.is_fg_item(rm), False)
    check("is_fg_item(None)", fg_stock.is_fg_item(None), False)
    check("is_fg_item(unknown code)", fg_stock.is_fg_item("ZZFG-NO-SUCH-ITEM"), False)
    for name in ("get_or_create_fg_batch", "refresh_fg_batch", "fg_batch_nos_by_warehouse",
                 "fg_batch_available", "kg_for_nos"):
        fn = getattr(fg_stock, name, None)
        check("fg_stock.%s defined and documented" % name, bool(fn and fn.__doc__), True)
    # Wave 0 checked these two were harmless no-ops; A4 has since implemented them (its
    # own test, verify_fg_final_stock_entry, covers their behaviour), so only their
    # presence is a schema-level fact now.
    for name in ("validate_fg_stock_entry_rows", "on_fg_stock_entry_change"):
        check("fg_stock.%s is callable" % name, callable(getattr(fg_stock, name, None)), True)


def run():
    print("=== verify_fg_schema: sep14 FG plan, wave 0 (A0) ===")
    _check_fields()
    _check_grids()
    _check_settings()
    _check_json_agrees()
    _check_hooks()
    _check_fg_stock()

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        failed = len([c for c in checks if not c])
        print("%d OF %d CHECKS FAILED" % (failed, len(checks)))
        raise AssertionError("verify_fg_schema: %d check(s) failed" % failed)
