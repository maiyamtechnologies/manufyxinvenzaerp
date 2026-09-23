"""The Sales Order's Delivery Plan tab lists finished drawings and makes a note from them.

A Sales Order usually carries ONE finished-goods line ("Fabricated Structurs", 31 Nos)
while its pieces are made drawing by drawing, each into its own FG batch. So a delivery
is "one of 1B1 and three of 1B3", and the Delivery Note needs one row per drawing: the
same FG item and Sales Order line, each with its own batch and DUNO.

What is checked here, and why each one matters:

  * The rows come from the ledger -- completed from Final Stock Entries, delivered from
    submitted notes net of returns, available from the batch's stock less drafts.
  * Create Delivery builds rows and lets the note's OWN validate price and police them
    (compute_fg_rows). If this ever grows its own Kg arithmetic the two will drift.
  * Draft notes count against Available. Validate only counts submitted stock, so
    without this two drafts could each take the same four pieces.
  * The stored rows follow submit and cancel through the hooks, with no Refresh.
  * Delivery Plan (Nos) stays visible. The grid is at exactly 11 of its 11-column
    budget and it is the LAST column, so any column added later silently drops the
    one field people type in (grid.js setup_visible_columns gives no error).

Needs a Sales Order with FG booked into a batch; says so and stops if there is none.
Everything runs in a transaction and is rolled back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_delivery_plan.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, fragment):
    try:
        fn()
    except Exception as e:
        return fragment.lower() in frappe.utils.strip_html(str(e)).lower()
    return False


def _sales_order_with_fg():
    """A submitted Sales Order with at least one FG batch holding two pieces or more."""
    from manufyxinvenzaerp.selling_management.delivery_plan import build_plan_rows

    for so in frappe.get_all("Sales Order", filters={"docstatus": 1}, pluck="name",
                             order_by="creation desc"):
        rows = build_plan_rows(so)
        if any(flt(r["available_qty"]) >= 2 for r in rows):
            return so, rows
    return None, []


def _stored(so):
    return frappe.get_all("Sales Order Delivery Plan",
                          filters={"parent": so, "parentfield": "custom_delivery_plan"},
                          fields=["*"], order_by="idx")


def run():
    try:
        _run()
    finally:
        frappe.db.rollback()
        print()
        print("  (rolled back -- this check leaves no trace)")
    _summary()


def _run():
    from manufyxinvenzaerp.selling_management.delivery_note import _update_after_change
    from manufyxinvenzaerp.selling_management.delivery_plan import (
        _refresh, build_plan_rows, create_delivery_from_plan,
    )

    print("=== 1. The tab and its grid ===")
    meta = frappe.get_meta("Sales Order")
    table = meta.get_field("custom_delivery_plan")
    check("Sales Order has the Delivery Plan table", bool(table), True)
    check("  typed on a submitted order (allow_on_submit)", bool(table and table.allow_on_submit), True)
    check("  never copied onto a duplicate or amendment", bool(table and table.no_copy), True)
    check("  Create Delivery is a button usable after submit",
          bool(meta.get_field("custom_create_delivery")
               and meta.get_field("custom_create_delivery").allow_on_submit), True)
    # Above the table, not below it: on a forty-drawing order the buttons would
    # otherwise be a long scroll away from the top of the tab.
    order = [f.fieldname for f in meta.fields]
    check("  both buttons sit above the table",
          order.index("custom_create_delivery") < order.index("custom_delivery_plan")
          and order.index("custom_refresh_delivery_plan") < order.index("custom_delivery_plan"),
          True)
    script = frappe.db.get_value("Client Script", "Sales Order-delivery-plan", "script") or ""
    check("  Create Delivery painted orange (alt), Refresh light (info)",
          ('mfx_paint_field(frm, "custom_create_delivery", "alt"' in script,
           'mfx_paint_field(frm, "custom_refresh_delivery_plan", "info"' in script),
          (True, True))

    child = frappe.get_meta("Sales Order Delivery Plan")
    total, shown = 1, []
    for f in child.fields:
        if f.hidden or not f.in_list_view or f.fieldtype in ("Section Break", "Column Break"):
            continue
        total += f.columns or (1 if f.fieldtype in ("Float", "Int", "Date", "Check") else 2)
        if total <= 11:
            shown.append(f.fieldname)
    check("  the grid fits its 11-column budget", total <= 11, True)
    check("  and Delivery Plan (Nos) is not the column it drops",
          "delivery_plan_qty" in shown, True)
    # Drawing left the grid to make room: DUNO and FG Batch already name the drawing,
    # and it is still in the row. Delivery Weight is the column that needed the room.
    check("  nor Delivery Weight (Kg)", "delivery_weight" in shown, True)
    check("  Delivery Weight is set in the browser, so it may change after submit",
          bool(child.get_field("delivery_weight").allow_on_submit), True)
    for fn in ("cust_weight_per_pcs", "total_cust_weight", "stock_weight_per_pcs",
               "total_stock_weight"):
        f = child.get_field(fn)
        check("  %s is in the row, read-only, not the grid" % fn,
              (bool(f), bool(f and f.read_only), bool(f and f.in_list_view)),
              (True, True, False))
    for fn in ("completed_qty", "delivered_qty", "draft_qty", "available_qty", "fg_batch"):
        check("  %s is read-only" % fn, bool(child.get_field(fn).read_only), True)
    check("  delivery_plan_qty is editable after submit",
          (bool(child.get_field("delivery_plan_qty").read_only),
           bool(child.get_field("delivery_plan_qty").allow_on_submit)), (False, True))

    so, rows = _sales_order_with_fg()
    if not so:
        print()
        print("    (no submitted Sales Order has two finished pieces in stock -- nothing "
              "further to exercise)")
        return

    print()
    print("=== 2. Rows come from the ledger (%s) ===" % so)
    for r in rows:
        check("  %s: available never exceeds completed less delivered" % r["duno_mark_no"],
              flt(r["available_qty"]) <= flt(r["completed_qty"]) - flt(r["delivered_qty"]) + 0.001,
              True)
    duno = [r["duno_mark_no"] for r in rows]
    from manufyxinvenzaerp.selling_management.delivery_plan import _natural_key
    check("  rows are in DUNO order as people read it (1B2 before 1B10)",
          duno, sorted(duno, key=_natural_key))

    _refresh(so)
    check("  Refresh stores one row per (batch, warehouse)", len(_stored(so)), len(rows))

    print()
    print("=== 2b. Weights ===")
    from manufyxinvenzaerp.production_management.fg_stock import (
        _price_nos, kg_for_nos, planned_kg_per_nos,
    )
    for r in rows:
        tag = r["duno_mark_no"]
        check("  %s: Cust Wt per Pcs is the drawing's own figure" % tag,
              flt(r["cust_weight_per_pcs"], 3),
              flt(planned_kg_per_nos(r["drawing"], r["fg_batch"]), 3))
        # Both totals over the Completed pieces, so they compare like with like.
        check("  %s: Total Cust Wt = per pcs x Completed" % tag,
              flt(r["total_cust_weight"], 3),
              flt(r["cust_weight_per_pcs"] * r["completed_qty"], 3))
        check("  %s: Stock Wt per Pcs = Total Stock Wt / Completed" % tag,
              flt(r["stock_weight_per_pcs"], 3),
              flt(r["total_stock_weight"] / r["completed_qty"], 3) if r["completed_qty"] else 0.0)

    # Delivery Weight must be the note's own pricing, or the grid shows one weight and
    # the note carries another. Checked through a saved plan, which _refresh re-prices.
    w = next(r for r in rows if flt(r["available_qty"]) >= 2)
    frappe.db.set_value("Sales Order Delivery Plan",
                        {"parent": so, "fg_batch": w["fg_batch"], "warehouse": w["warehouse"]},
                        "delivery_plan_qty", 1)
    _refresh(so)
    kept = {(x.fg_batch, x.warehouse): x for x in _stored(so)}[(w["fg_batch"], w["warehouse"])]
    check("  Delivery Weight of a saved plan = kg_for_nos, the note's own pricing",
          flt(kept.delivery_weight, 3), flt(kg_for_nos(w["fg_batch"], w["warehouse"], 1), 3))
    # The last-piece rule: every piece in the warehouse takes its exact Kg, whatever
    # the per-piece ratio would round to.
    check("  planning every piece in stock gives exactly the stock Kg",
          _price_nos(w["stock_nos"], w["stock_kg"], w["stock_nos"]), flt(w["stock_kg"], 3))
    _refresh(so, keep_plan=False)

    print()
    print("=== 3. Create Delivery ===")
    target = next(r for r in rows if flt(r["available_qty"]) >= 2)
    plan = [{"fg_batch": target["fg_batch"], "warehouse": target["warehouse"],
             "delivery_plan_qty": 2}]
    name = create_delivery_from_plan(so, plan)
    note = frappe.get_doc("Delivery Note", name)
    check("  a draft Delivery Note is made", note.docstatus, 0)
    check("  with one row for the one drawing planned", len(note.items), 1)
    row = note.items[0]
    check("  the FG item", row.item_code, target["fg_item"])
    check("  that drawing's own batch", row.batch_no, target["fg_batch"])
    check("  its DUNO", row.custom_duno_mark_no, target["duno_mark_no"])
    check("  its drawing", row.custom_drawing, target["drawing"])
    check("  the pieces planned", flt(row.custom_sec_qty), 2.0)
    check("  from the warehouse holding them", row.warehouse, target["warehouse"])
    check("  against the Sales Order line", bool(row.so_detail and row.against_sales_order), True)
    # Priced by the note's own validate, not by anything here: the batch's Kg for
    # two pieces, whatever placeholder the row was built with.
    from manufyxinvenzaerp.production_management.fg_stock import kg_for_nos
    check("  Kg priced by the batch, as a hand-made note would be",
          flt(row.qty, 3), flt(kg_for_nos(target["fg_batch"], target["warehouse"], 2), 3))
    from manufyxinvenzaerp.selling_management.delivery_plan import delivery_weight
    check("  and it is the Delivery Weight the plan showed for those pieces",
          flt(row.qty, 3), flt(delivery_weight(target, 2), 3))

    after = {(r.fg_batch, r.warehouse): r for r in _stored(so)}[(target["fg_batch"], target["warehouse"])]
    check("  the pieces move to In Draft DN", flt(after.draft_qty), 2.0)
    check("  and out of Available",
          flt(after.available_qty), flt(target["available_qty"]) - 2)
    check("  and the plan that made them is cleared", flt(after.delivery_plan_qty), 0.0)

    print()
    print("=== 4. It refuses what it cannot deliver ===")
    check("  the same pieces cannot be planned onto a second draft",
          _throws(lambda: create_delivery_from_plan(so, plan), "already on draft Delivery Note"),
          True)
    check("  and the refusal names the draft holding them",
          _throws(lambda: create_delivery_from_plan(so, plan), name), True)
    check("  half a piece is refused",
          _throws(lambda: create_delivery_from_plan(so, [dict(plan[0], delivery_plan_qty=0.5)]),
                  "whole number"), True)
    check("  an empty plan is refused",
          _throws(lambda: create_delivery_from_plan(so, []), "at least one drawing"), True)

    print()
    print("=== 5. Submit and cancel keep the tab current by themselves ===")
    # docstatus set in this transaction and the real hook body run on it, rather than
    # note.submit(): the GL posting needs a Fiscal Year linked to the company, which
    # a restored copy of the live database may not have. What is under test is this
    # feature's wiring, not ERPNext's ledger.
    frappe.db.set_value("Delivery Note", name, "docstatus", 1, update_modified=False)
    frappe.db.sql("UPDATE `tabDelivery Note Item` SET docstatus = 1 WHERE parent = %s", name)
    _update_after_change(frappe.get_doc("Delivery Note", name))
    sub = {(r.fg_batch, r.warehouse or ""): r for r in _stored(so)}
    delivered = sum(flt(r.delivered_qty) for r in sub.values() if r.fg_batch == target["fg_batch"])
    check("  on submit, Delivered rises with no Refresh",
          flt(delivered) >= flt(target["delivered_qty"]) + 2
          or any(flt(r.delivered_qty) == flt(target["delivered_qty"]) + 2
                 for r in sub.values() if r.fg_batch == target["fg_batch"]), True)

    frappe.db.set_value("Delivery Note", name, "docstatus", 2, update_modified=False)
    frappe.db.sql("UPDATE `tabDelivery Note Item` SET docstatus = 2 WHERE parent = %s", name)
    _update_after_change(frappe.get_doc("Delivery Note", name))
    back = {(r.fg_batch, r.warehouse): r for r in _stored(so)}.get(
        (target["fg_batch"], target["warehouse"]))
    check("  on cancel, the pieces are Available again",
          flt(back.available_qty) if back else None, flt(target["available_qty"]))


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
