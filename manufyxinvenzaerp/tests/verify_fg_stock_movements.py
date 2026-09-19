"""Material Transfer, Material Issue and Material Receipt keep Kg, Nos and batches right.

sep14 FG plan (.claude/tasks/sep14_fg_uom_plan.md), package A1 item 4 (D21).
Stock Reconciliation is blocked on this site, so a correction is now always a
Material Issue (take it out) followed by a Material Receipt (put the right figure
back). That only works if those two, and Material Transfer, move the piece count
along with the Kg. This walks each movement for three kinds of stock and checks,
after submit and again after cancel:

  - the Stock Entry row: Kg and Nos;
  - the batch: custom_sec_qty (total Nos, all warehouses);
  - the batch's Kg per warehouse, from the ledger.

  1. an RM plate batch    -- stock UOM Kg, Nos as Sec Qty, one batch per receipt;
  2. an RM nuts and bolts -- stock UOM Nos, Kg as Sec Qty, no batch, so Nos per
                             warehouse comes from the ledger instead;
  3. an FG batch          -- stock UOM Kg, Nos per warehouse (A4's fg_stock).
                             Skipped, with a note, until A4 has filled fg_stock in;
                             re-run in wave 3.

Everything it creates is named ZZFG-: two raw-material items, one FG item, one
FG batch, and Stock Entries on them. Each entry is cancelled again (in reverse
order) whatever happens; nothing is deleted and no user record is touched.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_stock_movements.run
"""

import frappe
from frappe.utils import flt

checks = []

STORES = "Stores - MIPL"
WIP = "Work In Progress - MIPL"

PLATE = "ZZFG-RM-PLATE"
PLATE_PREFIX = "ZZFGPL"
NUT = "ZZFG-RM-NUT"
NUT_UNIT_WEIGHT = 0.061
FG_ITEM = "ZZFG-FG-ITEM"
FG_BATCH = "ZZFG-FG-D1"

# 1000 x 1000 x 10 mm at 7.85 -> 78.5 Kg a plate.
PLATE_DIMS = {"custom_length": 1000, "custom_width": 1000, "custom_thickness": 10,
              "custom_unit_weight": 7.85}
KG_PER_PLATE = 78.5


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


# ── set-up ────────────────────────────────────────────────────────────────────

def _company():
    return frappe.db.get_value("Warehouse", STORES, "company")


def _ensure_item(code, like, **fields):
    """Create a ZZFG- test item once; later runs reuse it as it is.

    Item group and HSN code are copied from a real item of the same kind (`like`),
    read only: the site requires an HSN code on every item."""
    if frappe.db.exists("Item", code):
        return
    group, hsn = frappe.db.get_value("Item", like, ["item_group", "gst_hsn_code"])
    frappe.get_doc(dict({
        "item_group": group, "gst_hsn_code": hsn,
        "doctype": "Item", "item_code": code, "item_name": code,
        "is_stock_item": 1, "include_item_in_manufacturing": 1,
        "valuation_rate": 50,
    }, **fields)).insert(ignore_permissions=True)


def _setup_items():
    _ensure_item(PLATE, "PLATE10",
                 custom_parent_item_group="Plates", stock_uom="Kg",
                 custom_secondary_uom="Nos", custom_unit_weight=7.85,
                 has_batch_no=1, create_new_batch=1, custom_batch_prefix=PLATE_PREFIX)
    _ensure_item(NUT, "Nut-M20",
                 custom_parent_item_group="Nuts and Bolts", stock_uom="Nos",
                 custom_secondary_uom="Kg", custom_unit_weight=NUT_UNIT_WEIGHT,
                 has_batch_no=0)
    _ensure_item(FG_ITEM, "Fabricated Structurs",
                 custom_parent_item_group="Finished Goods", stock_uom="Kg",
                 custom_secondary_uom="Nos", has_batch_no=1, create_new_batch=0)
    frappe.db.commit()


# ── reading the figures ───────────────────────────────────────────────────────

def _batch_nos(batch_no):
    return flt(frappe.db.get_value("Batch", batch_no, "custom_sec_qty"), 3)


def _batch_kg(batch_no):
    """{warehouse: Kg} of one batch, from submitted, uncancelled bundles."""
    rows = frappe.db.sql(
        """
        SELECT sbe.warehouse, SUM(sbe.qty)
        FROM `tabSerial and Batch Entry` sbe
        JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
        WHERE sbe.batch_no = %s AND sbb.docstatus = 1 AND sbb.is_cancelled = 0
        GROUP BY sbe.warehouse
        """,
        batch_no,
    )
    return {wh: flt(q, 3) for wh, q in rows if flt(q, 3)}


def _item_qty(item_code):
    """{warehouse: stock qty} of an item without batches, from the ledger."""
    rows = frappe.db.sql(
        """
        SELECT warehouse, SUM(actual_qty) FROM `tabStock Ledger Entry`
        WHERE item_code = %s AND is_cancelled = 0 GROUP BY warehouse
        """,
        item_code,
    )
    return {wh: flt(q, 3) for wh, q in rows if flt(q, 3)}


def _row(se):
    """The entry's single row, as saved (after the server's own recalculation)."""
    return frappe.db.get_value(
        "Stock Entry Detail", {"parent": se.name}, ["qty", "custom_sec_qty"], as_dict=True
    )


# ── making and undoing entries ────────────────────────────────────────────────

_made = []


def _entry(se_type, row):
    se = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": se_type, "company": _company(),
        "remarks": "ZZFG- sep14 A1 stock movement audit",
        "items": [dict({"use_serial_batch_fields": 1, "basic_rate": 50}, **row)],
    })
    se.insert(ignore_permissions=True)
    se.submit()
    _made.append(se.name)
    frappe.db.commit()
    return se


def _cancel(se):
    frappe.get_doc("Stock Entry", se.name).cancel()
    frappe.db.commit()


def _cancel_leftovers():
    for name in reversed(_made):
        try:
            if frappe.db.get_value("Stock Entry", name, "docstatus") == 1:
                frappe.get_doc("Stock Entry", name).cancel()
        except Exception as e:
            print("   (could not cancel %s: %s)" % (name, e))
    frappe.db.commit()


# ── 1. RM plate batch ─────────────────────────────────────────────────────────

def _plate_move(label, se_type, batch, qty, nos, want_row, want_nos, want_kg,
                after_cancel_nos, after_cancel_kg, **wh):
    print()
    print("--- plate: %s ---" % label)
    row = dict(item_code=PLATE, batch_no=batch, qty=qty, custom_sec_qty=nos, **wh)
    if se_type in ("Material Issue", "Material Receipt"):
        row.update(PLATE_DIMS)   # Issue / Receipt re-derive the Kg from the size
    se = _entry(se_type, row)
    got = _row(se)
    check("row Kg / Nos", (flt(got.qty, 3), flt(got.custom_sec_qty, 3)), want_row)
    check("batch Nos after submit", _batch_nos(batch), want_nos)
    check("batch Kg per warehouse after submit", _batch_kg(batch), want_kg)
    _cancel(se)
    check("batch Nos after cancel", _batch_nos(batch), after_cancel_nos)
    check("batch Kg per warehouse after cancel", _batch_kg(batch), after_cancel_kg)


def _plate_cases():
    print()
    print("=== 1. RM plate batch (Kg stock, Nos as Sec Qty) ===")
    print("--- plate: receipt of 4 plates makes a new batch ---")
    receipt = _entry("Material Receipt", dict(
        item_code=PLATE, t_warehouse=STORES, qty=4 * KG_PER_PLATE, custom_sec_qty=4,
        custom_sec_uom="Nos", **PLATE_DIMS))
    batch = frappe.db.get_value(
        "Batch", {"reference_doctype": "Stock Entry", "reference_name": receipt.name}, "name")
    check("a batch was made", bool(batch), True)
    check("named with the item's prefix", (batch or "").startswith(PLATE_PREFIX + "-"), True)
    got = _row(receipt)
    check("row Kg / Nos", (flt(got.qty, 3), flt(got.custom_sec_qty, 3)), (314.0, 4.0))
    check("batch Nos", _batch_nos(batch), 4.0)
    check("batch Kg per warehouse", _batch_kg(batch), {STORES: 314.0})

    full = {STORES: 314.0}
    _plate_move("full transfer Stores -> WIP", "Material Transfer", batch, 314.0, 4,
                (314.0, 4.0), 4.0, {WIP: 314.0}, 4.0, full,
                s_warehouse=STORES, t_warehouse=WIP)
    _plate_move("partial transfer, 2 of 4", "Material Transfer", batch, 157.0, 2,
                (157.0, 2.0), 4.0, {STORES: 157.0, WIP: 157.0}, 4.0, full,
                s_warehouse=STORES, t_warehouse=WIP)
    _plate_move("issue 1 plate", "Material Issue", batch, KG_PER_PLATE, 1,
                (78.5, 1.0), 3.0, {STORES: 235.5}, 4.0, full,
                s_warehouse=STORES)
    # The correction path that replaces Stock Reconciliation puts stock back into
    # the batch it came from, so a receipt into an existing batch must add its Nos.
    _plate_move("receipt of 1 plate back into the same batch", "Material Receipt", batch,
                KG_PER_PLATE, 1, (78.5, 1.0), 5.0, {STORES: 392.5}, 4.0, full,
                t_warehouse=STORES)

    print()
    print("--- plate: cancelling the first receipt empties the batch ---")
    _cancel(receipt)
    check("batch Nos after cancel", _batch_nos(batch), 0.0)
    check("batch Kg per warehouse after cancel", _batch_kg(batch), {})


# ── 2. RM nuts and bolts (no batch) ───────────────────────────────────────────

def _nut_kg(nos):
    return flt(nos * NUT_UNIT_WEIGHT, 3)


def _nut_move(label, se_type, nos, want_wh, **wh):
    print()
    print("--- nuts: %s ---" % label)
    before = _item_qty(NUT)
    # Kg is not typed: it follows from the Nos, as on a Purchase Receipt.
    se = _entry(se_type, dict(item_code=NUT, qty=nos, **wh))
    got = _row(se)
    check("row Nos / Kg", (flt(got.qty, 3), flt(got.custom_sec_qty, 3)), (flt(nos, 3), _nut_kg(nos)))
    check("Nos per warehouse after submit", _item_qty(NUT), want_wh)
    _cancel(se)
    check("Nos per warehouse after cancel", _item_qty(NUT), before)


def _nut_cases():
    print()
    print("=== 2. RM nuts and bolts (Nos stock, Kg as Sec Qty, no batch) ===")
    print("--- nuts: receipt of 100 ---")
    receipt = _entry("Material Receipt", dict(item_code=NUT, qty=100, t_warehouse=STORES))
    got = _row(receipt)
    check("row Nos / Kg", (flt(got.qty, 3), flt(got.custom_sec_qty, 3)), (100.0, 6.1))
    check("Nos per warehouse", _item_qty(NUT), {STORES: 100.0})

    _nut_move("full transfer Stores -> WIP", "Material Transfer", 100, {WIP: 100.0},
              s_warehouse=STORES, t_warehouse=WIP)
    _nut_move("partial transfer, 40 of 100", "Material Transfer", 40,
              {STORES: 60.0, WIP: 40.0}, s_warehouse=STORES, t_warehouse=WIP)
    _nut_move("issue 30", "Material Issue", 30, {STORES: 70.0}, s_warehouse=STORES)
    _nut_move("receipt of 25 more", "Material Receipt", 25, {STORES: 125.0}, t_warehouse=STORES)

    print()
    print("--- nuts: cancelling the first receipt ---")
    _cancel(receipt)
    check("Nos per warehouse after cancel", _item_qty(NUT), {})


# ── 3. FG batch (needs A4) ────────────────────────────────────────────────────

def _fg_ready():
    """False while fg_stock still carries A0's stubs."""
    from manufyxinvenzaerp.production_management import fg_stock

    try:
        fg_stock.fg_batch_nos_by_warehouse("ZZFG-NO-SUCH-BATCH")
    except NotImplementedError:
        return False
    return True


def _ensure_fg_batch():
    """An FG batch for the test item, made the way fg_stock does it: explicitly.

    It carries no Sales Order on purpose -- a batch pointing at a real order would
    be offered on that order's Delivery Note by Get FG Batches."""
    if frappe.db.exists("Batch", FG_BATCH):
        return
    frappe.get_doc({
        "doctype": "Batch", "batch_id": FG_BATCH, "item": FG_ITEM,
        "custom_sec_uom": "Nos", "custom_cust_weight_per_nos": 30,
    }).insert(ignore_permissions=True)
    frappe.db.commit()


def _fg_state():
    from manufyxinvenzaerp.production_management.fg_stock import fg_batch_nos_by_warehouse

    nos_wh = {wh: flt(n, 3) for wh, n in (fg_batch_nos_by_warehouse(FG_BATCH) or {}).items() if flt(n, 3)}
    return _batch_nos(FG_BATCH), nos_wh, _batch_kg(FG_BATCH)


def _fg_move(label, se_type, nos, kg_typed, want_row, want_state, **wh):
    print()
    print("--- FG: %s ---" % label)
    before = _fg_state()
    se = _entry(se_type, dict(item_code=FG_ITEM, batch_no=FG_BATCH, qty=kg_typed,
                              custom_sec_qty=nos, custom_sec_uom="Nos", **wh))
    got = _row(se)
    check("row Kg / Nos", (flt(got.qty, 3), flt(got.custom_sec_qty, 3)), want_row)
    check("batch Nos, Nos per warehouse, Kg per warehouse", _fg_state(), want_state)
    return se, before


def _fg_cases():
    print()
    print("=== 3. FG batch (Kg stock, Nos per warehouse) ===")
    if not _fg_ready():
        print("  SKIP fg_stock is not implemented yet (A4, wave 1). This part is")
        print("       re-run in wave 3, once the FG batch functions exist.")
        return

    _ensure_fg_batch()
    # Receipt: 10 Nos weighed at 300 Kg -> 30 Kg a piece.
    receipt, _ = _fg_move("receipt of 10 Nos at 300 Kg", "Material Receipt", 10, 300.0,
                          (300.0, 10.0), (10.0, {STORES: 10.0}, {STORES: 300.0}),
                          t_warehouse=STORES)
    # Transfer: the Kg typed is ignored; it is Nos x Kg per Nos from the batch.
    part, before_part = _fg_move("partial transfer, 3 of 10", "Material Transfer", 3, 1.0,
                                 (90.0, 3.0),
                                 (10.0, {STORES: 7.0, WIP: 3.0}, {STORES: 210.0, WIP: 90.0}),
                                 s_warehouse=STORES, t_warehouse=WIP)
    # The last 7 in Stores take exactly what is left there.
    rest, before_rest = _fg_move("full transfer of the remaining 7", "Material Transfer", 7, 1.0,
                                 (210.0, 7.0), (10.0, {WIP: 10.0}, {WIP: 300.0}),
                                 s_warehouse=STORES, t_warehouse=WIP)
    issue, before_issue = _fg_move("issue 4 from WIP", "Material Issue", 4, 1.0,
                                   (120.0, 4.0), (6.0, {WIP: 6.0}, {WIP: 180.0}),
                                   s_warehouse=WIP)

    print()
    print("--- FG: every cancel restores the figures ---")
    for se, before, label in ((issue, before_issue, "issue"), (rest, before_rest, "full transfer"),
                              (part, before_part, "partial transfer")):
        _cancel(se)
        check("after cancelling the %s" % label, _fg_state(), before)
    _cancel(receipt)
    check("after cancelling the receipt", _fg_state(), (0.0, {}, {}))


# ── run ───────────────────────────────────────────────────────────────────────

def run():
    _setup_items()
    try:
        for part in (_plate_cases, _nut_cases, _fg_cases):
            try:
                part()
            except Exception as e:
                # One kind of stock failing must not hide what the others show.
                frappe.db.rollback()
                checks.append(False)
                print("  FAIL %s raised %s: %s" % (part.__name__, type(e).__name__, e))
    finally:
        _cancel_leftovers()
        print()
        print("   test entries cancelled, nothing deleted")

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
