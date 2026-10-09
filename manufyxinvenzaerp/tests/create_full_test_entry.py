"""
Creates a single end-to-end Material Planning entry that covers ALL table logic.

Scenario: "Steel Frame Assembly — Shop Floor Test"

BOM has 4 raw material lines:
┌─────────────────────────────────────────────────────────────────────┐
│ Item             │ BOM Dims       │ Warehouse Stock   │ → Table     │
├─────────────────────────────────────────────────────────────────────┤
│ TEST-MB-250X125  │ L=5000         │ Batch-1: L=5000   │ Table 2 ✅  │
│                  │                │ Batch-2: L=5000   │ Table 2 ✅  │
│ TEST-PLATE-10MM  │ L=2500,W=1250  │ Batch-3: L=6000   │ Table 3 ✂️  │
│                  │                │ (wrong length)    │             │
│ TEST-ANGLE-65X6  │ L=3000         │ No stock          │ Table 4 🛒  │
│ TEST-NUT-M16     │ (no dims)      │ No stock          │ Table 4 🛒  │
└─────────────────────────────────────────────────────────────────────┘

Table 2 shows 2 rows (one per matching batch) for TEST-MB-250X125.
Table 3 shows 1 row — store person must select a batch & it gets cut.
Table 4 shows 2 rows — both need purchase.

Run:
  bench --site fl.local execute manufyxinvenzaerp.tests.create_full_test_entry.run
"""

import frappe
from frappe.utils import today, flt


# ── Context ───────────────────────────────────────────────────────────────────

def get_ctx():
    company_row = frappe.db.sql("SELECT name, abbr, default_currency FROM tabCompany LIMIT 1", as_dict=True)
    company  = company_row[0]["name"]
    abbr     = company_row[0]["abbr"]
    currency = company_row[0]["default_currency"] or "INR"

    wh = frappe.db.sql(
        "SELECT name FROM tabWarehouse WHERE is_group=0 LIMIT 1", as_dict=True
    )
    warehouse = wh[0]["name"]

    ig = frappe.db.sql(
        "SELECT name FROM `tabItem Group` WHERE is_group=0 LIMIT 1", as_dict=True
    )
    item_group = ig[0]["name"]

    hsn = frappe.db.sql(
        "SELECT name FROM `tabGST HSN Code` WHERE LENGTH(name)>=6 LIMIT 1", as_dict=True
    )
    hsn_code = hsn[0]["name"] if hsn else ""

    return frappe._dict(
        company=company, abbr=abbr, currency=currency,
        warehouse=warehouse, item_group=item_group, hsn_code=hsn_code
    )


# ── Item factory ──────────────────────────────────────────────────────────────

def fill_process_planning_parties(pp):
    """Give every Process Planning row the Supplier/Contractor it needs to submit.

    A Production Plan refuses to submit while any Process Planning row has no party
    (production_plan.before_submit_process_planning). The fixtures in these checks
    predate that rule and built their rows without one, so every check that submits
    a plan stopped at the plan instead of reaching what it was written to test.

    Subcontractor rows take the plan's own Vendor/Contractor where it has one -- that
    is who the Job Work Order goes to -- and any enabled Supplier otherwise. Internal
    Jobcard rows take a Contractor, and one is created if the site has none. Rows that
    already carry a party are left alone."""
    supplier = pp.get("custom_vendor_contractor") or frappe.db.get_value(
        "Supplier", {"disabled": 0}, "name")
    contractor = frappe.db.get_value("Contractor", {}, "name")
    if not contractor:
        contractor = frappe.get_doc({"doctype": "Contractor",
                                     "contractor_name": "ZZTEST Contractor"}).insert(
            ignore_permissions=True).name
    for row in pp.get("custom_process_planning") or []:
        if row.get("party"):
            continue
        if row.work_type == "Subcontractor":
            row.party_type, row.party = "Supplier", supplier
        elif row.work_type == "Internal Jobcard":
            row.party_type, row.party = "Contractor", contractor


def ensure_item(ctx, code, name, uom="Kg", batch_tracked=True):
    if frappe.db.exists("Item", code):
        return code
    frappe.get_doc({
        "doctype": "Item",
        "item_code": code,
        "item_name": name,
        "item_group": ctx.item_group,
        "stock_uom": uom,
        "is_stock_item": 1,
        "has_batch_no": 1 if batch_tracked else 0,
        "create_new_batch": 0,
        "gst_hsn_code": ctx.hsn_code,
        "custom_parent_item_group": ctx.item_group,
    }).insert(ignore_permissions=True)
    print(f"  ✔ Item     : {code}")
    return code


def ensure_fg_item(ctx, code, name):
    if frappe.db.exists("Item", code):
        return code
    frappe.get_doc({
        "doctype": "Item",
        "item_code": code,
        "item_name": name,
        "item_group": ctx.item_group,
        "stock_uom": "Nos",
        "is_stock_item": 1,
        "has_batch_no": 0,
        "gst_hsn_code": ctx.hsn_code,
        "custom_parent_item_group": ctx.item_group,
    }).insert(ignore_permissions=True)
    print(f"  ✔ FG Item  : {code}")
    return code


# ── Batch factory ─────────────────────────────────────────────────────────────

def ensure_batch(item, batch_id, L=0.0, W=0.0, T=0.0, sec_qty=0, sec_uom="Nos"):
    if frappe.db.exists("Batch", batch_id):
        return batch_id
    frappe.get_doc({
        "doctype": "Batch",
        "batch_id": batch_id,
        "item": item,
        "custom_length":    L,
        "custom_width":     W,
        "custom_thickness": T,
        "custom_sec_qty":   sec_qty,
        "custom_sec_uom":   sec_uom,
    }).insert(ignore_permissions=True)
    print(f"  ✔ Batch    : {batch_id}  (L={L}, W={W}, T={T}, sec_qty={sec_qty})")
    return batch_id


# ── Stock Entry factory ───────────────────────────────────────────────────────

def make_receipt(ctx, item, batch, qty, uom="Kg", rate=80):
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"
    se.company          = ctx.company
    se.posting_date     = today()
    se.append("items", {
        "item_code":          item,
        "qty":                qty,
        "uom":                uom,
        "stock_uom":          uom,
        "conversion_factor":  1,
        "t_warehouse":        ctx.warehouse,
        "batch_no":           batch,
        "basic_rate":         rate,
    })
    se.insert(ignore_permissions=True)
    se.submit()
    print(f"  ✔ Stock    : {se.name}  — {qty} {uom} of {item} [{batch}] → {ctx.warehouse}")
    return se.name


# ── BOM factory ───────────────────────────────────────────────────────────────

def make_bom(ctx, fg, rows):
    """
    rows = list of dicts:
      item_code, qty, uom, L, W, T, item_number
    """
    existing = frappe.db.sql(
        "SELECT name FROM tabBOM WHERE item=%s AND docstatus=1 LIMIT 1", fg, as_dict=True
    )
    if existing:
        print(f"  ✔ BOM      : {existing[0]['name']} (already exists)")
        return existing[0]["name"]

    bom = frappe.new_doc("BOM")
    bom.item      = fg
    bom.quantity  = 1
    bom.company   = ctx.company
    bom.currency  = ctx.currency

    for r in rows:
        bom.append("items", {
            "item_code":          r["item_code"],
            "qty":                r["qty"],
            "uom":                r.get("uom", "Kg"),
            "stock_uom":          r.get("uom", "Kg"),
            "conversion_factor":  1,
            "custom_length":      r.get("L", 0),
            "custom_width":       r.get("W", 0),
            "custom_thickness":   r.get("T", 0),
            "custom_item_number": r["item_number"],
        })

    bom.insert(ignore_permissions=True)
    bom.submit()
    print(f"  ✔ BOM      : {bom.name}  (FG: {fg})")
    return bom.name


# ── Material Planning factory ──────────────────────────────────────────────────

def make_material_planning(ctx, bom_name, fg_item):
    mp = frappe.new_doc("Material Planning")
    mp.company       = ctx.company
    mp.posting_date  = today()
    mp.for_warehouse = ctx.warehouse
    mp.append("bom_items", {
        "bom_no":            bom_name,
        "item_code":         fg_item,
        "item_name":         frappe.db.get_value("Item", fg_item, "item_name"),
        "qty_to_manufacture": 1,
        "uom":               "Nos",
    })
    mp.insert(ignore_permissions=True)
    print(f"  ✔ Material Planning : {mp.name}")
    return mp


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    frappe.set_user("Administrator")
    ctx = get_ctx()

    print(f"""
{'═'*60}
  Full Test Entry — Steel Frame Assembly
{'═'*60}
  Company   : {ctx.company}
  Warehouse : {ctx.warehouse}
{'═'*60}
""")

    # ── Items ─────────────────────────────────────────────────────────────────
    print("[ 1 ] Items")
    BEAM   = ensure_item(ctx, "TEST-MB-250X125",  "IS MB 250×125 Structural Beam", uom="Kg")
    PLATE  = ensure_item(ctx, "TEST-PLATE-10MM",  "MS Plate 10mm Thick",           uom="Kg")
    ANGLE  = ensure_item(ctx, "TEST-ANGLE-65X6",  "IS Angle 65×65×6mm",            uom="Kg")
    NUT    = ensure_item(ctx, "TEST-NUT-M16",     "M16 Hex Nut Grade 8",           uom="Nos", batch_tracked=True)
    FG     = ensure_fg_item(ctx, "TEST-STEEL-FRAME", "Steel Frame Assembly — Test")
    frappe.db.commit()

    # ── Batches ───────────────────────────────────────────────────────────────
    print("\n[ 2 ] Batches")
    # BEAM: 2 batches both with L=5000 — both will EXACTLY match the BOM → 2 rows in Table 2
    B_BEAM_1 = ensure_batch(BEAM, "BATCH-MB250-L5000-R01", L=5000.0, W=0.0, T=0.0, sec_qty=4,  sec_uom="Nos")
    B_BEAM_2 = ensure_batch(BEAM, "BATCH-MB250-L5000-R02", L=5000.0, W=0.0, T=0.0, sec_qty=3,  sec_uom="Nos")
    # PLATE: batch with L=6000 (BOM needs L=2500) → WRONG LENGTH → Table 3
    B_PLATE  = ensure_batch(PLATE, "BATCH-PLATE10-L6000",  L=6000.0, W=1500.0, T=10.0, sec_qty=2, sec_uom="Nos")
    # ANGLE & NUT: no batches created → Table 4
    frappe.db.commit()

    # ── Stock Entries ─────────────────────────────────────────────────────────
    print("\n[ 3 ] Stock Receipts")
    make_receipt(ctx, BEAM,  B_BEAM_1, qty=235.5)  # 4 pcs × 5m × 11.775 kg/m
    make_receipt(ctx, BEAM,  B_BEAM_2, qty=176.6)  # 3 pcs × 5m × 11.775 kg/m
    make_receipt(ctx, PLATE, B_PLATE,  qty=141.3)  # 2 pcs × 6m × 1.5m × 0.01m × 7850 kg/m³
    # ANGLE and NUT intentionally have NO stock
    frappe.db.commit()

    # ── BOM ───────────────────────────────────────────────────────────────────
    print("\n[ 4 ] BOM")
    bom_rows = [
        # item_code,  qty,    uom,   L,      W,      T,    item_number
        # BEAM: BOM says L=5000 → both batches match → 2 rows in Table 2
        {"item_code": BEAM,  "qty": 94.2,  "uom": "Kg",  "L": 5000.0, "W": 0.0,    "T": 0.0,  "item_number": 1},
        # PLATE: BOM says L=2500,W=1250 — batch has L=6000,W=1500 → wrong → Table 3
        {"item_code": PLATE, "qty": 29.4,  "uom": "Kg",  "L": 2500.0, "W": 1250.0, "T": 10.0, "item_number": 2},
        # ANGLE: no stock at all → Table 4
        {"item_code": ANGLE, "qty": 21.9,  "uom": "Kg",  "L": 3000.0, "W": 0.0,    "T": 0.0,  "item_number": 3},
        # NUT: no stock, no dimensions → Table 4
        {"item_code": NUT,   "qty": 32,    "uom": "Nos", "L": 0.0,    "W": 0.0,    "T": 0.0,  "item_number": 4},
    ]
    bom_name = make_bom(ctx, FG, bom_rows)
    frappe.db.commit()

    # ── Material Planning ─────────────────────────────────────────────────────
    print("\n[ 5 ] Material Planning")
    mp = make_material_planning(ctx, bom_name, FG)
    frappe.db.commit()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"""
{'═'*60}
  ENTRIES CREATED
{'═'*60}
  Material Planning : {mp.name}   ← Open this in the UI
  BOM               : {bom_name}
  Warehouse         : {ctx.warehouse}

{'═'*60}
  WHAT TO DO IN UI
{'═'*60}

  1. Manufacturing → Material Planning → {mp.name}

  2. Selected BOMs tab — BOM is already filled:
       {bom_name}  (FG: TEST-STEEL-FRAME)

  3. Click  [ Get Raw Materials ]
     → 4 rows appear in Raw Materials:
       • TEST-MB-250X125   94.2 Kg  (L=5000)
       • TEST-PLATE-10MM   29.4 Kg  (L=2500, W=1250, T=10)
       • TEST-ANGLE-65X6   21.9 Kg  (L=3000)
       • TEST-NUT-M16      32 Nos

  4. Go to Stock Analysis tab
     Click  [ Check Stock Availability ]

     ┌─────────────────────────────────────────────────────┐
     │ RAW MATERIALS (updated availability)                │
     │  MB-250X125  avail=412.1 Kg  shortage=0            │
     │  PLATE-10MM  avail=0         shortage=29.4  ← no   │
     │              exact dim match despite stock          │
     │  ANGLE-65X6  avail=0         shortage=21.9          │
     │  NUT-M16     avail=0         shortage=32            │
     ├─────────────────────────────────────────────────────┤
     │ AVAILABLE RAW MATERIALS (2 rows — one per batch)   │
     │  • TEST-MB-250X125  BATCH-MB250-L5000-R01  235.5Kg │
     │  • TEST-MB-250X125  BATCH-MB250-L5000-R02  176.6Kg │
     ├─────────────────────────────────────────────────────┤
     │ MATERIAL MAPPING (1 row — stock but wrong dims)    │
     │  • TEST-PLATE-10MM  [Assign Batch manually]        │
     │    BOM needs L=2500  |  Batch has L=6000 → cut it  │
     ├─────────────────────────────────────────────────────┤
     │ UNAVAILABLE ITEMS (2 rows — zero stock)            │
     │  • TEST-ANGLE-65X6  21.9 Kg  (needs purchase)      │
     │  • TEST-NUT-M16     32 Nos   (needs purchase)       │
     └─────────────────────────────────────────────────────┘

  5. In Material Mapping row → click edit (✏)
     → Assign Batch field → type "BATCH" → see dropdown
     → Each result shows:  BATCH-PLATE10-L6000  |  TEST-PLATE-10MM
     → Select BATCH-PLATE10-L6000
     → Planned Item auto-fills: TEST-PLATE-10MM

  6. Save → Submit

  7. Create → Production Plan
     → MFG-PP-XXXX created with 1 BOM item (Steel Frame)
{'═'*60}
""")
