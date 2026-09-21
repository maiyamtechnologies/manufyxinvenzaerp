import frappe
from frappe.utils import today, add_days

# The specs the sample items below quote. Stated once here so the master records
# and the items that link to them cannot drift apart.
_SAMPLE_MATERIAL_SPECS = ("IS 2062 E250", "Grade 8.8")


def run():
    frappe.set_user("Administrator")

    # ── 0. WAREHOUSE TYPES (needed before company creation) ──────
    print("Ensuring warehouse types...")
    for wt in ["Stores", "Work In Progress", "Finished Goods", "Transit"]:
        if not frappe.db.exists("Warehouse Type", wt):
            frappe.get_doc({"doctype": "Warehouse Type", "name": wt}).insert(ignore_permissions=True)
    frappe.db.commit()

    # ── 0b. MATERIAL SPECS USED BELOW ────────────────────────────
    # Material Spec became a Link in Sep 2026, so the specs these sample items
    # quote have to exist as master records first -- without this every Item
    # insert below dies on "Could not find Material Spec".
    print("Ensuring material specs...")
    for spec in _SAMPLE_MATERIAL_SPECS:
        if not frappe.db.exists("Material Spec", spec):
            frappe.get_doc({"doctype": "Material Spec", "spec_name": spec}).insert(
                ignore_permissions=True)
    frappe.db.commit()

    # ── 1. COMPANY ───────────────────────────────────────────────
    print("Creating company...")
    if not frappe.db.exists("Company", "Manufyx Steel Works Pvt Ltd"):
        company = frappe.get_doc({
            "doctype": "Company",
            "company_name": "Manufyx Steel Works Pvt Ltd",
            "abbr": "MSW",
            "default_currency": "INR",
            "country": "India",
            "create_chart_of_accounts_based_on": "Standard Template",
            "chart_of_accounts": "Standard with Numbers",
        })
        company.insert(ignore_permissions=True)
        frappe.db.commit()
        print("  Company created.")
    else:
        print("  Company already exists.")

    COMPANY = "Manufyx Steel Works Pvt Ltd"

    # ── 2. UOM ───────────────────────────────────────────────────
    print("Ensuring UOMs...")
    for uom in ["Kg", "Nos"]:
        if not frappe.db.exists("UOM", uom):
            frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(ignore_permissions=True)
    frappe.db.commit()

    # ── 3. ITEM GROUPS ───────────────────────────────────────────
    print("Creating item groups...")
    if not frappe.db.exists("Item Group", "All Item Groups"):
        frappe.get_doc({
            "doctype": "Item Group",
            "item_group_name": "All Item Groups",
            "is_group": 1,
            "parent_item_group": "",
        }).insert(ignore_permissions=True)
        frappe.db.commit()

    for ig_name, parent in [
        ("Structurals", "All Item Groups"),
        ("Plates", "All Item Groups"),
        ("Nuts and Bolts", "All Item Groups"),
        ("Finished Goods", "All Item Groups"),
    ]:
        if not frappe.db.exists("Item Group", ig_name):
            frappe.get_doc({
                "doctype": "Item Group",
                "item_group_name": ig_name,
                "parent_item_group": parent,
                "is_group": 0,
            }).insert(ignore_permissions=True)
    frappe.db.commit()
    print("  Item Groups done.")

    # ── 4. WAREHOUSES ─────────────────────────────────────────────
    print("Creating warehouses...")
    ABBR = frappe.db.get_value("Company", COMPANY, "abbr") or "MSW"
    for wh_name in ["Raw Material Store", "WIP Warehouse", "Subcontractor Warehouse"]:
        full_name = f"{wh_name} - {ABBR}"
        if not frappe.db.exists("Warehouse", full_name):
            frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": wh_name,
                "company": COMPANY,
            }).insert(ignore_permissions=True)
    frappe.db.commit()
    print("  Warehouses done.")

    RM_WH = f"Raw Material Store - {ABBR}"
    WIP_WH = f"WIP Warehouse - {ABBR}"
    FG_WH = frappe.db.get_value("Warehouse", {"warehouse_name": "Finished Goods", "company": COMPANY}, "name") or f"Finished Goods - {ABBR}"
    SUB_WH = f"Subcontractor Warehouse - {ABBR}"

    # ── 4b. ROOT GROUPS (Supplier, Customer, Territory) ──────────
    print("Ensuring root groups...")
    if not frappe.db.exists("Supplier Group", "All Supplier Groups"):
        frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": "All Supplier Groups", "is_group": 1}).insert(ignore_permissions=True)
    if not frappe.db.exists("Customer Group", "All Customer Groups"):
        frappe.get_doc({"doctype": "Customer Group", "customer_group_name": "All Customer Groups", "is_group": 1}).insert(ignore_permissions=True)
    if not frappe.db.exists("Customer Group", "Commercial"):
        frappe.get_doc({"doctype": "Customer Group", "customer_group_name": "Commercial", "parent_customer_group": "All Customer Groups", "is_group": 0}).insert(ignore_permissions=True)
    if not frappe.db.exists("Territory", "All Territories"):
        frappe.get_doc({"doctype": "Territory", "territory_name": "All Territories", "is_group": 1}).insert(ignore_permissions=True)
    frappe.db.commit()

    # ── 5. SUPPLIER ───────────────────────────────────────────────
    print("Creating suppliers...")
    for sup_name, sup_group in [
        ("Steel Traders India", "All Supplier Groups"),
        ("Ace Fabricators Pvt Ltd", "All Supplier Groups"),
    ]:
        if not frappe.db.exists("Supplier", sup_name):
            frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": sup_name,
                "supplier_group": sup_group,
                "supplier_type": "Company",
                "country": "India",
            }).insert(ignore_permissions=True)
    frappe.db.commit()
    print("  Suppliers done.")

    # ── 6. CUSTOMER ───────────────────────────────────────────────
    print("Creating customer...")
    if not frappe.db.exists("Customer", "Horizon Infrastructure Ltd"):
        frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Horizon Infrastructure Ltd",
            "customer_group": "Commercial",
            "territory": "All Territories",
            "customer_type": "Company",
        }).insert(ignore_permissions=True)
    frappe.db.commit()
    print("  Customer done.")

    # ── 7. ITEMS ──────────────────────────────────────────────────
    print("Creating items...")

    # Ensure HSN codes exist (required by India Compliance)
    for hsn_code, desc in [("721610", "Angles, shapes and sections of iron or non-alloy steel"),
                            ("720810", "Flat-rolled products of iron or non-alloy steel, hot-rolled"),
                            ("731810", "Screws, bolts and nuts, of iron or steel"),
                            ("730890", "Structures and parts of structures of iron or steel")]:
        if not frappe.db.exists("GST HSN Code", hsn_code):
            frappe.get_doc({"doctype": "GST HSN Code", "hsn_code": hsn_code, "description": desc}).insert(ignore_permissions=True)
    frappe.db.commit()

    # Structural item — ISMB 150
    if not frappe.db.exists("Item", "ISMB-150"):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": "ISMB-150",
            "item_name": "ISMB 150 Beam",
            "item_group": "Structurals",
            "stock_uom": "Kg",
            "gst_hsn_code": "721610",
            "custom_parent_item_group": "Structurals",
            "custom_unit_weight": 14.9,
            "custom_secondary_uom": "Nos",
            "custom_material_spec": "IS 2062 E250",
            "has_batch_no": 1,
            "create_new_batch": 1,
            "custom_batch_prefix": "ISMB150",
            "is_stock_item": 1,
        }).insert(ignore_permissions=True)

    # Plate item — MS Plate 10mm
    if not frappe.db.exists("Item", "MS-PLATE-10"):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": "MS-PLATE-10",
            "item_name": "MS Plate 10mm",
            "item_group": "Plates",
            "stock_uom": "Kg",
            "gst_hsn_code": "720810",
            "custom_parent_item_group": "Plates",
            "custom_unit_weight": 7.85,
            "custom_secondary_uom": "Nos",
            "custom_material_spec": "IS 2062 E250",
            "has_batch_no": 1,
            "create_new_batch": 1,
            "custom_batch_prefix": "PL10",
            "is_stock_item": 1,
        }).insert(ignore_permissions=True)

    # Nuts & Bolts item — M16 Bolt
    if not frappe.db.exists("Item", "BOLT-M16"):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": "BOLT-M16",
            "item_name": "M16 Hex Bolt 50mm",
            "item_group": "Nuts and Bolts",
            "stock_uom": "Nos",
            "gst_hsn_code": "731810",
            "custom_parent_item_group": "Nuts and Bolts",
            "custom_unit_weight": 0.08,
            "custom_secondary_uom": "Kg",
            "custom_material_spec": "Grade 8.8",
            "is_stock_item": 1,
        }).insert(ignore_permissions=True)

    # Finished Good — Steel Frame Assembly
    if not frappe.db.exists("Item", "FG-FRAME-001"):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": "FG-FRAME-001",
            "item_name": "Steel Frame Assembly",
            "item_group": "Finished Goods",
            "stock_uom": "Nos",
            "gst_hsn_code": "730890",
            "custom_parent_item_group": "Finished Goods",
            "is_stock_item": 1,
            "is_purchase_item": 0,
            "is_sales_item": 1,
        }).insert(ignore_permissions=True)

    frappe.db.commit()
    print("  Items done.")

    # ── 6b. PRICE LIST ────────────────────────────────────────────
    print("Ensuring price lists...")
    if not frappe.db.exists("Price List", "Standard Selling"):
        frappe.get_doc({"doctype": "Price List", "price_list_name": "Standard Selling", "selling": 1, "buying": 0, "currency": "INR", "enabled": 1}).insert(ignore_permissions=True)
    if not frappe.db.exists("Price List", "Standard Buying"):
        frappe.get_doc({"doctype": "Price List", "price_list_name": "Standard Buying", "selling": 0, "buying": 1, "currency": "INR", "enabled": 1}).insert(ignore_permissions=True)
    frappe.db.commit()

    # ── 7b. FISCAL YEAR ───────────────────────────────────────────
    print("Ensuring fiscal year...")
    if not frappe.db.exists("Fiscal Year", "2026-2027"):
        fy = frappe.get_doc({
            "doctype": "Fiscal Year",
            "year": "2026-2027",
            "year_start_date": "2026-04-01",
            "year_end_date": "2027-03-31",
            "companies": [{"company": COMPANY}],
        })
        fy.insert(ignore_permissions=True)
        frappe.db.commit()
    # Also create 2025-2026 in case today's date is within it
    if not frappe.db.exists("Fiscal Year", "2025-2026"):
        fy = frappe.get_doc({
            "doctype": "Fiscal Year",
            "year": "2025-2026",
            "year_start_date": "2025-04-01",
            "year_end_date": "2026-03-31",
            "companies": [{"company": COMPANY}],
        })
        fy.insert(ignore_permissions=True)
        frappe.db.commit()
    print("  Fiscal year done.")

    # ── 8. STOCK OPENING ENTRIES (put raw material in store) ──────
    print("Creating stock opening entries...")
    if not frappe.db.exists("Stock Entry", {"purpose": "Material Receipt", "remarks": "Sample opening stock"}):
        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "purpose": "Material Receipt",
            "company": COMPANY,
            "remarks": "Sample opening stock",
            "items": [
                {
                    "item_code": "ISMB-150",
                    "qty": 500,
                    "custom_sec_qty": 10,
                    "custom_length": 6000,
                    "custom_unit_weight": 14.9,
                    "uom": "Kg",
                    "t_warehouse": RM_WH,
                    "basic_rate": 60,
                },
                {
                    "item_code": "MS-PLATE-10",
                    "qty": 785,
                    "custom_sec_qty": 5,
                    "custom_length": 2500,
                    "custom_width": 1250,
                    "custom_thickness": 10,
                    "custom_unit_weight": 7.85,
                    "uom": "Kg",
                    "t_warehouse": RM_WH,
                    "basic_rate": 65,
                },
                {
                    "item_code": "BOLT-M16",
                    "qty": 200,
                    "uom": "Nos",
                    "t_warehouse": RM_WH,
                    "basic_rate": 15,
                },
            ],
        })
        se.insert(ignore_permissions=True)
        se.submit()
        frappe.db.commit()
        print("  Opening stock entry created and submitted.")
    else:
        print("  Opening stock already exists.")

    # ── 9. SALES ORDER ───────────────────────────────────────────
    print("Creating Sales Order...")
    CUSTOMER_NAME = frappe.db.get_value("Customer", {"customer_name": "Horizon Infrastructure Ltd"}, "name") or "Horizon Infrastructure Ltd"
    so_name = None
    existing_so = frappe.db.get_value("Sales Order", {"customer": CUSTOMER_NAME, "docstatus": 1}, "name")
    if not existing_so:
        so = frappe.get_doc({
            "doctype": "Sales Order",
            "customer": CUSTOMER_NAME,
            "company": COMPANY,
            "delivery_date": add_days(today(), 30),
            "order_type": "Sales",
            "items": [
                {
                    "item_code": "FG-FRAME-001",
                    "qty": 5,
                    "rate": 50000,
                    "delivery_date": add_days(today(), 30),
                    "warehouse": FG_WH,
                },
            ],
        })
        so.insert(ignore_permissions=True)
        so.submit()
        frappe.db.commit()
        so_name = so.name
        print(f"  Sales Order created: {so_name}")
    else:
        so_name = existing_so
        print(f"  Sales Order already exists: {so_name}")

    # get SO item name for Drawing linkage
    so_item_name = frappe.db.get_value("Sales Order Item", {"parent": so_name}, "name")

    # ── 10. DRAWING ──────────────────────────────────────────────
    print("Creating Drawing...")
    drawing_name = None
    existing_drawing = frappe.db.get_value("Drawing", {"sales_order": so_name}, "name")
    if not existing_drawing:
        drawing = frappe.get_doc({
            "doctype": "Drawing",
            "naming_series": "DRW-.YYYY.-",
            "sales_order": so_name,
            "so_item_reference": so_item_name,
            "customer": CUSTOMER_NAME,
            "customer_name": "Horizon Infrastructure Ltd",
            "customer_no": "HIL-2024-001",
            "cust_po_no": "PO-HIL-5001",
            "customer_drawing_number": "HIL-DRW-001",
            "rev_no": 1,
            "duno_mark_no": 1,
            "fg_item_code": "FG-FRAME-001",
            "fg_item_name": "Steel Frame Assembly",
            "fg_description": "Structural steel frame assembly for industrial building",
            "no_of_qty_to_manufacture": 5,
            "status": "Working",
            "items": [
                {
                    "item_number": 1,
                    "material_code": "ISMB-150",
                    "material_name": "ISMB 150 Beam",
                    "item_group": "Structurals",
                    "parent_item_group": "Structurals",
                    "unit_weight": 14.9,
                    "length": 6000,
                    "sec_qty": 4,
                    "sec_uom": "Nos",
                    "qty": 357.6,
                    "uom": "Kg",
                    "rate": 60,
                    "amount": 21456,
                },
                {
                    "item_number": 2,
                    "material_code": "MS-PLATE-10",
                    "material_name": "MS Plate 10mm",
                    "item_group": "Plates",
                    "parent_item_group": "Plates",
                    "unit_weight": 7.85,
                    "length": 500,
                    "width": 400,
                    "thickness": 10,
                    "sec_qty": 8,
                    "sec_uom": "Nos",
                    "qty": 125.6,
                    "uom": "Kg",
                    "rate": 65,
                    "amount": 8164,
                },
                {
                    "item_number": 3,
                    "material_code": "BOLT-M16",
                    "material_name": "M16 Hex Bolt 50mm",
                    "item_group": "Nuts and Bolts",
                    "parent_item_group": "Nuts and Bolts",
                    "unit_weight": 0.08,
                    "sec_qty": 0,
                    "sec_uom": "Nos",
                    "qty": 40,
                    "uom": "Nos",
                    "rate": 15,
                    "amount": 600,
                },
            ],
        })
        drawing.insert(ignore_permissions=True)
        frappe.db.commit()
        drawing_name = drawing.name
        print(f"  Drawing created: {drawing_name}")
    else:
        drawing_name = existing_drawing
        print(f"  Drawing already exists: {drawing_name}")

    # ── 11. BOM ──────────────────────────────────────────────────
    print("Creating BOM...")
    existing_bom = frappe.db.get_value("BOM", {"item": "FG-FRAME-001", "is_active": 1}, "name")
    bom_name = None
    if not existing_bom:
        bom = frappe.get_doc({
            "doctype": "BOM",
            "item": "FG-FRAME-001",
            "item_name": "Steel Frame Assembly",
            "quantity": 1,
            "company": COMPANY,
            "routing": "Standard Manufacturing Routing",
            "custom_drawing": drawing_name,
            "with_operations": 1,
            "items": [
                {
                    "item_code": "ISMB-150",
                    "item_name": "ISMB 150 Beam",
                    "qty": 357.6,
                    "uom": "Kg",
                    "rate": 60,
                    "custom_item_number": 1,
                    "custom_length": 6000,
                    "custom_unit_weight": 14.9,
                    "custom_sec_qty": 4,
                    "custom_sec_uom": "Nos",
                    "source_warehouse": RM_WH,
                },
                {
                    "item_code": "MS-PLATE-10",
                    "item_name": "MS Plate 10mm",
                    "qty": 125.6,
                    "uom": "Kg",
                    "rate": 65,
                    "custom_item_number": 2,
                    "custom_length": 500,
                    "custom_width": 400,
                    "custom_thickness": 10,
                    "custom_unit_weight": 7.85,
                    "custom_sec_qty": 8,
                    "custom_sec_uom": "Nos",
                    "source_warehouse": RM_WH,
                },
                {
                    "item_code": "BOLT-M16",
                    "item_name": "M16 Hex Bolt 50mm",
                    "qty": 40,
                    "uom": "Nos",
                    "rate": 15,
                    "custom_item_number": 3,
                    "source_warehouse": RM_WH,
                },
            ],
        })
        bom.insert(ignore_permissions=True)
        bom.submit()
        frappe.db.commit()
        bom_name = bom.name
        print(f"  BOM created and submitted: {bom_name}")
    else:
        bom_name = existing_bom
        print(f"  BOM already exists: {bom_name}")

    # ── 12. PURCHASE ORDER (Raw Material Procurement) ─────────────
    print("Creating Purchase Order for raw materials...")
    existing_po = frappe.db.get_value("Purchase Order", {"supplier": "Steel Traders India", "docstatus": 1}, "name")
    if not existing_po:
        po = frappe.get_doc({
            "doctype": "Purchase Order",
            "supplier": "Steel Traders India",
            "company": COMPANY,
            "schedule_date": add_days(today(), 7),
            "items": [
                {
                    "item_code": "ISMB-150",
                    "item_name": "ISMB 150 Beam",
                    "qty": 500,
                    "uom": "Kg",
                    "custom_sec_qty": 10,
                    "custom_sec_uom": "Nos",
                    "custom_length": 6000,
                    "custom_unit_weight": 14.9,
                    "rate": 58,
                    "schedule_date": add_days(today(), 7),
                    "warehouse": RM_WH,
                },
                {
                    "item_code": "MS-PLATE-10",
                    "item_name": "MS Plate 10mm",
                    "qty": 785,
                    "uom": "Kg",
                    "custom_sec_qty": 5,
                    "custom_sec_uom": "Nos",
                    "custom_length": 2500,
                    "custom_width": 1250,
                    "custom_thickness": 10,
                    "custom_unit_weight": 7.85,
                    "rate": 63,
                    "schedule_date": add_days(today(), 7),
                    "warehouse": RM_WH,
                },
                {
                    "item_code": "BOLT-M16",
                    "item_name": "M16 Hex Bolt 50mm",
                    "qty": 200,
                    "uom": "Nos",
                    "rate": 13,
                    "schedule_date": add_days(today(), 7),
                    "warehouse": RM_WH,
                },
            ],
        })
        po.insert(ignore_permissions=True)
        po.submit()
        frappe.db.commit()
        print(f"  Purchase Order created: {po.name}")
    else:
        print(f"  Purchase Order already exists: {existing_po}")

    print("\n✅ All sample data created successfully!")
    print(f"   Company  : {COMPANY}")
    print(f"   Customer : Horizon Infrastructure Ltd")
    print(f"   Suppliers: Steel Traders India, Ace Fabricators Pvt Ltd")
    print(f"   Items    : ISMB-150, MS-PLATE-10, BOLT-M16, FG-FRAME-001")
    print(f"   SO       : {so_name}")
    print(f"   Drawing  : {drawing_name}")
    print(f"   BOM      : {bom_name}")

