"""The Final Stock Entry books finished goods in Kg, counted in Nos per drawing batch.

sep14 FG plan (.claude/tasks/sep14_fg_uom_plan.md), package A4, on the worked example
of section 6: one drawing of 10 Nos at 30 Kg per Nos.

  1. The first Final Stock Entry books 4 of 10 Nos, weighed at 122 Kg: the drawing's
     batch FG-<Sales Order>-<DUNO> is created with every FG detail filled in, and holds
     4 Nos / 122 Kg = 30.5 Kg per Nos.
  2. With Edit FG Stock Kg off, a typed Kg is replaced by Nos x Cust Weight (per Nos);
     with it on, the weighed Kg stands, with a warning above the % setting.
  3. The second books the other 6 at 181 Kg into the same batch: 10 Nos / 303 Kg.
  4. A third run finds nothing to book.
  5. FG movements take their Kg from the Nos: transferring 3 Nos moves 90.9 Kg
     (3 x 30.3) and leaves 7 + 3 Nos in the two warehouses; issuing all 10 takes the
     exact 303 Kg; a receipt of 10 Nos at 300 Kg into the same batch re-weighs it to
     30.0 Kg per Nos. Too many pieces, part pieces or no batch are refused.
  6. Every cancel puts the batch figures back.

The Job Work Order is a real one on this site (its finished-goods item, drawing weight
and completed pieces are pointed at a ZZFG- test item for the run). EVERYTHING runs
inside one transaction that is rolled back at the end: nothing is kept, nothing of the
user's is changed. frappe.db.commit is disabled for the run, so a stray commit fails
the test instead of saving anything.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_final_stock_entry.run
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.production_management import fg_stock
from manufyxinvenzaerp.subcontracting_management.subcontracting import (
    _fg_already_booked,
    create_finished_goods_entry,
    get_final_stock_entry_preview,
)

checks = []

FG_ITEM = "ZZFG-A4-FG"
STORES = "Stores - MIPL"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def raises(label, fn, text):
    """The call must throw, and its message must mention `text`."""
    try:
        fn()
    except Exception as e:
        frappe.clear_last_message()
        check(label, text.lower() in str(e).lower(), True)
        if text.lower() not in str(e).lower():
            print("       message was: %s" % e)
        return
    check(label, "no error", "refused")


# ── set-up (all inside the transaction) ───────────────────────────────────────

def _pick_sco():
    """A submitted Job Work Order with a final operation and an open Material Issue Plan."""
    for name in frappe.get_all("Subcontracting Order", filters={"docstatus": 1},
                               order_by="creation desc", pluck="name"):
        mip = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": name},
                                  ["name", "status"], as_dict=True)
        p = get_final_stock_entry_preview(name)
        if mip and mip.status != "Completed" and p["final_operation"] and p["drawings"] \
                and flt(frappe.db.get_value("Subcontracting Order", name,
                                            "custom_transferred_weight_kg")):
            return name, p
    return None, None


def _make_item():
    group, hsn = frappe.db.get_value("Item", "Fabricated Structurs", ["item_group", "gst_hsn_code"])
    frappe.get_doc({
        "doctype": "Item", "item_code": FG_ITEM, "item_name": FG_ITEM,
        "item_group": group, "gst_hsn_code": hsn, "custom_parent_item_group": "Finished Goods",
        "stock_uom": "Kg", "custom_secondary_uom": "Nos", "is_stock_item": 1,
        "has_batch_no": 1, "create_new_batch": 0, "valuation_rate": 50,
        "include_item_in_manufacturing": 1,
    }).insert(ignore_permissions=True)


def _settings(edit, pct=5):
    frappe.db.set_single_value("Manufyxinvenza Settings", "edit_fg_stock_kg", 1 if edit else 0)
    frappe.db.set_single_value("Manufyxinvenza Settings", "fg_weight_difference_warning_percent", pct)


def _fg_row(se):
    return [r for r in se.items if r.item_code == FG_ITEM][0]


def _entry(se_type, row):
    se = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": se_type,
        "company": frappe.db.get_value("Warehouse", STORES, "company"),
        "items": [dict({"item_code": FG_ITEM, "custom_sec_uom": "Nos",
                        "use_serial_batch_fields": 1}, **row)],
    })
    se.insert(ignore_permissions=True)
    return se


def _state(batch):
    """(batch Nos, Actual Kg per Nos, Nos per warehouse, Kg per warehouse)."""
    b = frappe.db.get_value("Batch", batch, ["custom_sec_qty", "custom_weight_per_piece"], as_dict=True)
    kg = {wh: v for wh, v in fg_stock._kg_by_warehouse(batch).items() if v}
    return (flt(b.custom_sec_qty, 3), flt(b.custom_weight_per_piece, 3),
            fg_stock.fg_batch_nos_by_warehouse(batch), kg)


# ── run ───────────────────────────────────────────────────────────────────────

def run():
    real_commit = frappe.db.commit

    def _no_commit(*a, **k):
        raise RuntimeError("verify_fg_final_stock_entry must not commit")

    frappe.db.commit = _no_commit
    try:
        _run()
    except Exception as e:
        checks.append(False)
        import traceback
        traceback.print_exc()
        print("  FAIL the run raised %s: %s" % (type(e).__name__, e))
    finally:
        frappe.db.rollback()
        frappe.db.commit = real_commit
        frappe.clear_cache(doctype="Item")

    print()
    print("=== after rollback ===")
    check("the test item is gone", bool(frappe.db.exists("Item", FG_ITEM)), False)
    check("no FG batch of it is left", frappe.db.count("Batch", {"item": FG_ITEM}), 0)
    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))


def _run():
    sco, p = _pick_sco()
    if not sco:
        print("=== no usable submitted Job Work Order on this site ===")
        checks.append(False)
        return
    print("=== %s (final operation %s) ===" % (sco, p["final_operation"]["name"]))

    # Entries booked before this change counted pieces in qty; they still count.
    booked_before = _fg_already_booked(sco)
    want_before = {}
    for r in frappe.db.sql(
            """SELECT sed.custom_drawing d, sed.qty q, sed.custom_sec_qty s FROM `tabStock Entry Detail` sed
               JOIN `tabStock Entry` se ON se.name = sed.parent
               WHERE se.subcontracting_order = %s AND se.stock_entry_type = 'Manufacture'
                 AND se.docstatus = 1 AND sed.is_finished_item = 1
                 AND IFNULL(sed.custom_drawing, '') != ''""", sco, as_dict=True):
        want_before[r.d] = flt(want_before.get(r.d, 0) + (flt(r.s) or flt(r.q)))
    check("already booked: Sec Qty, or qty on an old entry", booked_before, want_before)

    # Clear the way: earlier entries hold the job's material and its pieces.
    for name in frappe.get_all("Stock Entry", filters={"subcontracting_order": sco, "docstatus": 1,
                                                       "stock_entry_type": "Manufacture"},
                               pluck="name", order_by="creation desc"):
        doc = frappe.get_doc("Stock Entry", name)
        doc.flags.ignore_links = True
        doc.cancel()

    _make_item()
    _settings(edit=True, pct=5)

    final = p["final_operation"]["name"]
    soe_rows = frappe.get_all("SOE Drawing Detail", filters={"parent": final},
                              fields=["name", "drawing", "duno_mark_no"], order_by="idx")
    d1 = soe_rows[0]
    for r in soe_rows:
        frappe.db.set_value("SOE Drawing Detail", r.name,
                            {"completed_qty_nos": 0, "qty_to_manufacture": 10}, update_modified=False)
    for r in frappe.get_all("SCO Drawing Item", filters={"parent": sco}, pluck="name"):
        frappe.db.set_value("SCO Drawing Item", r, "item_code", FG_ITEM, update_modified=False)
    frappe.db.set_value("Drawing", d1.drawing, {"weight_per_pcs": 30, "no_of_qty_to_manufacture": 10},
                        update_modified=False)
    drg = frappe.db.get_value("Drawing", d1.drawing,
                              ["sales_order", "customer", "duno_mark_no", "customer_drawing_number"],
                              as_dict=True)
    fg_wh = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": sco},
                                "excess_return_warehouse")
    want_batch = "FG-%s-%s" % (drg.sales_order, d1.duno_mark_no or d1.drawing)

    # ── 1. first Final Stock Entry: 4 of 10 at 122 Kg ──
    print()
    print("=== 1. Final Stock Entry 1: 4 of 10 Nos, weighed 122 Kg ===")
    frappe.db.set_value("SOE Drawing Detail", d1.name, "completed_qty_nos", 4, update_modified=False)
    pv = get_final_stock_entry_preview(sco)
    dv = [d for d in pv["drawings"] if d["drawing"] == d1.drawing][0]
    check("preview: 4 ready, planned 120 Kg at 30 per Nos",
          (dv["ready_to_book"], dv["planned_kg"], dv["cust_weight_per_nos"]), (4.0, 120.0, 30.0))

    se1 = frappe.get_doc("Stock Entry", create_finished_goods_entry(sco)["name"])
    row = _fg_row(se1)
    check("FG row: Kg = Nos x per Nos, in Kg", (flt(row.qty, 3), row.uom), (120.0, "Kg"))
    check("FG row: Sec Qty 4 Nos", (flt(row.custom_sec_qty), row.custom_sec_uom), (4.0, "Nos"))
    check("FG row: drawing batch, batch field used",
          (row.batch_no, row.use_serial_batch_fields), (want_batch, 1))
    check("FG row: drawing, DUNO, Sales Order",
          (row.custom_drawing, row.custom_duno_mark_no, row.custom_sales_order),
          (d1.drawing, d1.duno_mark_no, drg.sales_order))
    b = frappe.get_doc("Batch", want_batch)
    check("batch carries every FG detail",
          (b.custom_sales_order, b.custom_customer, b.custom_drawing, b.custom_duno_mark_no,
           b.custom_customer_drawing_number, b.custom_job_work_order,
           flt(b.custom_cust_weight_per_nos), b.custom_sec_uom),
          (drg.sales_order, drg.customer, d1.drawing, d1.duno_mark_no,
           drg.customer_drawing_number or "", sco, 30.0, "Nos"))
    check("no reference while the entry is a draft", b.reference_name, None)

    # Weighed figure: 122 vs 120 is 1.67% -- a warning at 1%, none at 5%.
    row.qty = 122
    _settings(edit=True, pct=1)
    frappe.local.message_log = []
    se1.save()
    warned = any("FG Weight Difference" in str(m) for m in frappe.local.message_log)
    check("setting on: the weighed 122 Kg stands", flt(_fg_row(se1).qty, 3), 122.0)
    check("and warns above 1%", warned, True)
    _settings(edit=True, pct=5)
    frappe.local.message_log = []
    se1.save()
    check("no warning at 5%", any("FG Weight Difference" in str(m) for m in frappe.local.message_log), False)
    check("header total follows the Kg",
          flt(se1.custom_total_qty, 3), flt(sum(flt(i.qty) for i in se1.items), 3))
    se1.submit()
    check("batch: 4 Nos, 30.5 Kg per Nos, all in the FG warehouse",
          _state(want_batch), (4.0, 30.5, {fg_wh: 4.0}, {fg_wh: 122.0}))
    check("batch now references this first entry",
          frappe.db.get_value("Batch", want_batch, "reference_name"), se1.name)
    check("booked: 4 Nos (Sec Qty, not the 122 Kg)", _fg_already_booked(sco).get(d1.drawing), 4.0)

    # ── 2 + 3. setting off, then the second entry at 181 Kg ──
    print()
    print("=== 2. Edit FG Stock Kg off: a typed Kg is replaced ===")
    frappe.db.set_value("SOE Drawing Detail", d1.name, "completed_qty_nos", 10, update_modified=False)
    se2 = frappe.get_doc("Stock Entry", create_finished_goods_entry(sco)["name"])
    check("entry 2 proposes the other 6 Nos at 180 Kg",
          (flt(_fg_row(se2).custom_sec_qty), flt(_fg_row(se2).qty, 3), _fg_row(se2).batch_no),
          (6.0, 180.0, want_batch))
    _settings(edit=False)
    _fg_row(se2).qty = 181
    se2.save()
    check("setting off: 181 typed -> reset to 180", flt(_fg_row(se2).qty, 3), 180.0)
    _fg_row(se2).custom_sec_qty = 5.5
    raises("part pieces refused", se2.save, "whole number")
    se2.reload()

    print()
    print("=== 3. Final Stock Entry 2: 6 more Nos, weighed 181 Kg ===")
    _settings(edit=True)
    _fg_row(se2).qty = 181
    se2.save()
    check("setting on: 181 kept", flt(_fg_row(se2).qty, 3), 181.0)
    se2.submit()
    check("same batch: 10 Nos / 303 Kg -> 30.3", _state(want_batch),
          (10.0, 30.3, {fg_wh: 10.0}, {fg_wh: 303.0}))

    print()
    print("=== 4. a third run finds nothing to book ===")
    check("preview has nothing ready", get_final_stock_entry_preview(sco)["can_create"], False)
    raises("create refuses", lambda: create_finished_goods_entry(sco), "Nothing is waiting")
    check("get_or_create reuses the drawing's batch",
          fg_stock.get_or_create_fg_batch(FG_ITEM, drg.sales_order, d1.drawing, d1.duno_mark_no,
                                          drg.customer, "", sco, 30, None), want_batch)
    if len(soe_rows) > 1:
        other = soe_rows[1].drawing
        check("a DUNO taken by another drawing falls back to the drawing name",
              fg_stock.get_or_create_fg_batch(FG_ITEM, drg.sales_order, other, d1.duno_mark_no,
                                              drg.customer, "", sco, 30, None),
              "FG-%s-%s" % (drg.sales_order, other))

    # ── 5. movements ──
    print()
    print("=== 5. FG transfer, issue and receipt ===")
    check("kg_for_nos: 3 Nos = 90.9", fg_stock.kg_for_nos(want_batch, fg_wh, 3), 90.9)
    check("kg_for_nos: all 10 = the exact 303", fg_stock.kg_for_nos(want_batch, fg_wh, 10), 303.0)
    check("fg_batch_available", fg_stock.fg_batch_available(want_batch, fg_wh),
          {"nos": 10.0, "kg": 303.0, "kg_per_nos": 30.3})

    raises("transfer of 11 of 10 refused",
           lambda: _entry("Material Transfer", {"batch_no": want_batch, "custom_sec_qty": 11, "qty": 1,
                                                "s_warehouse": fg_wh, "t_warehouse": STORES}),
           "cannot be taken")
    raises("transfer of 2.5 Nos refused",
           lambda: _entry("Material Transfer", {"batch_no": want_batch, "custom_sec_qty": 2.5, "qty": 1,
                                                "s_warehouse": fg_wh, "t_warehouse": STORES}),
           "whole number")
    raises("transfer without Nos refused",
           lambda: _entry("Material Transfer", {"batch_no": want_batch, "qty": 1,
                                                "s_warehouse": fg_wh, "t_warehouse": STORES}),
           "number of pieces")
    raises("FG row without a batch refused",
           lambda: _entry("Material Transfer", {"custom_sec_qty": 3, "qty": 1, "use_serial_batch_fields": 0,
                                                "s_warehouse": fg_wh, "t_warehouse": STORES}),
           "per drawing batch")

    tr = _entry("Material Transfer", {"batch_no": want_batch, "custom_sec_qty": 3, "qty": 1,
                                      "s_warehouse": fg_wh, "t_warehouse": STORES})
    check("transfer 3 Nos: the typed 1 Kg becomes 90.9", flt(_fg_row(tr).qty, 3), 90.9)
    tr.submit()
    check("after transfer: 10 Nos, 7 + 3 per warehouse", _state(want_batch),
          (10.0, 30.3, {fg_wh: 7.0, STORES: 3.0}, {fg_wh: 212.1, STORES: 90.9}))
    tr.cancel()
    check("transfer cancelled: all back", _state(want_batch),
          (10.0, 30.3, {fg_wh: 10.0}, {fg_wh: 303.0}))

    iss = _entry("Material Issue", {"batch_no": want_batch, "custom_sec_qty": 10, "qty": 1,
                                    "s_warehouse": fg_wh})
    check("issue all 10: the exact 303 Kg", flt(_fg_row(iss).qty, 3), 303.0)
    iss.submit()
    check("after issue: 0 Nos, Kg per Nos left as it was", _state(want_batch), (0.0, 30.3, {}, {}))

    raises("receipt without Nos refused",
           lambda: _entry("Material Receipt", {"batch_no": want_batch, "qty": 300, "basic_rate": 50,
                                               "t_warehouse": fg_wh}),
           "number of pieces")
    rc = _entry("Material Receipt", {"batch_no": want_batch, "custom_sec_qty": 10, "qty": 300,
                                     "basic_rate": 50, "t_warehouse": fg_wh})
    check("receipt: the typed 300 Kg stands", flt(_fg_row(rc).qty, 3), 300.0)
    rc.submit()
    check("re-weighed: 10 Nos / 300 Kg -> 30.0", _state(want_batch),
          (10.0, 30.0, {fg_wh: 10.0}, {fg_wh: 300.0}))

    # ── 6. every cancel restores ──
    print()
    print("=== 6. cancelling in reverse ===")
    rc.cancel()
    check("receipt cancelled", _state(want_batch)[0::2], (0.0, {}))
    iss.cancel()
    check("issue cancelled: 10 / 303", _state(want_batch), (10.0, 30.3, {fg_wh: 10.0}, {fg_wh: 303.0}))
    se2.reload()
    se2.cancel()
    check("entry 2 cancelled: 4 / 122", _state(want_batch), (4.0, 30.5, {fg_wh: 4.0}, {fg_wh: 122.0}))
    check("and its 6 Nos are bookable again", _fg_already_booked(sco).get(d1.drawing), 4.0)
    se1.reload()
    se1.cancel()
    check("entry 1 cancelled: empty", _state(want_batch)[0::2], (0.0, {}))
    check("nothing booked", _fg_already_booked(sco).get(d1.drawing), None)
