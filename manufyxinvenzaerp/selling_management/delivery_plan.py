"""The Sales Order's Delivery Plan tab: finished drawings, and a Delivery Note from them.

One Sales Order usually carries ONE finished-goods line ("Fabricated Structurs",
31 Nos) while its pieces are made drawing by drawing, each into its own FG batch
(FG-<order>-<DUNO>, see fg_stock.get_or_create_fg_batch). So a delivery is not "this
line" -- it is "two of 1B1 and four of 1B3", and the Delivery Note needs one row per
drawing: the same FG item and Sales Order line, each with its own batch and DUNO.

The tab lists every drawing that has pieces booked into finished goods, with what was
completed, delivered, held on draft notes and still available, and a Delivery Plan
(Nos) the user types. Create Delivery turns those into a draft Delivery Note.

What this module does NOT do is price or police the note. The Delivery Note's own
validate (delivery_note.compute_fg_rows) already fills the drawing and DUNO from the
batch, checks the pieces are in the warehouse and within the line's pending Nos, and
prices the Kg by the last-piece rule. Create Delivery builds the rows and inserts the
note, so every one of those rules runs exactly as it does for a note made by hand.
The one check made here that validate cannot make is against DRAFT notes: validate
counts submitted stock only, so two drafts could each take the same four pieces.

The stored rows are a derived view. They are rebuilt from the ledger when their
inputs change -- FG booked or cancelled (fg_stock.on_fg_stock_entry_change), a note
submitted or cancelled (delivery_note._update_after_change) -- and on Refresh.
Written straight to the child table rather than by saving the Sales Order: saving a
submitted order runs its update-after-submit hooks and bumps `modified` under anyone
who has it open, for a table that holds no decision of its own except Delivery Plan.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from manufyxinvenzaerp.production_management import fg_stock
from manufyxinvenzaerp.selling_management import delivery_note as dn

CHILD = "Sales Order Delivery Plan"
FIELD = "custom_delivery_plan"


# ── Figures per batch ─────────────────────────────────────────────────────────


def _completed_nos(batch_no):
    """Pieces booked into the batch by submitted Final Stock Entries (Manufacture)."""
    return flt(frappe.db.sql(
        """
        SELECT COALESCE(SUM(sed.custom_sec_qty), 0)
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.docstatus = 1 AND se.purpose = 'Manufacture'
          AND sed.is_finished_item = 1 AND IFNULL(sed.t_warehouse, '') != ''
          AND {match}
        """.format(match=fg_stock._batch_row_match("sed")),
        {"batch": batch_no},
    )[0][0], 3)


def _booked_kg(batch_no):
    """Kg booked into the batch by submitted Final Stock Entries -- the weight the
    Completed pieces were taken into stock at. Same rows as _completed_nos, so the two
    always describe the same pieces."""
    return flt(frappe.db.sql(
        """
        SELECT COALESCE(SUM(sed.qty), 0)
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.docstatus = 1 AND se.purpose = 'Manufacture'
          AND sed.is_finished_item = 1 AND IFNULL(sed.t_warehouse, '') != ''
          AND {match}
        """.format(match=fg_stock._batch_row_match("sed")),
        {"batch": batch_no},
    )[0][0], 3)


def delivery_weight(row, qty):
    """Kg for `qty` pieces of a plan row, priced as the Delivery Note will price them.

    fg_stock._price_nos is the exact function compute_fg_rows prices a note row with
    (through kg_for_nos): pieces x Kg per piece on the unrounded ratio, and taking
    every piece in the warehouse takes the exact Kg there. Anything else here would be
    a second opinion on the weight that the note would then contradict.
    """
    return fg_stock._price_nos(row.get("stock_nos"), row.get("stock_kg"), qty)


def _dn_nos(batch_no, docstatus):
    """{warehouse: Nos} on Delivery Note rows of the batch at one docstatus.

    Returns carry negative Nos, so on submitted notes this is net of them."""
    rows = frappe.db.sql(
        """
        SELECT dni.warehouse AS wh, COALESCE(SUM(dni.custom_sec_qty), 0) AS nos
        FROM `tabDelivery Note Item` dni
        JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dn.docstatus = %(ds)s AND {match}
        GROUP BY dni.warehouse
        """.format(match=fg_stock._batch_row_match("dni")),
        {"batch": batch_no, "ds": docstatus},
        as_dict=True,
    )
    return {r.wh or "": flt(r.nos, 3) for r in rows}


def _draft_notes(batch_no):
    """Names of draft Delivery Notes holding pieces of the batch -- named in errors,
    because 'not enough available' is only fixable by knowing which draft took them."""
    return frappe.db.sql_list(
        """
        SELECT DISTINCT dn.name
        FROM `tabDelivery Note Item` dni
        JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dn.docstatus = 0 AND {match}
        """.format(match=fg_stock._batch_row_match("dni")),
        {"batch": batch_no},
    )


def _natural_key(value):
    """1B2 before 1B10: DUNOs are the customer's own marks and sort as people read them."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", value or "")]


def build_plan_rows(sales_order):
    """The live Delivery Plan rows for a Sales Order, from the ledger.

    One row per (FG batch, warehouse holding its pieces). A drawing whose pieces
    have all gone still gets one row, warehouse blank and nothing available, so a
    finished drawing does not disappear from the list the moment it is delivered.
    Only batches that have something completed are listed: a batch created but never
    booked into has nothing to deliver and nothing to report.
    """
    batches = frappe.get_all(
        "Batch",
        filters={"custom_sales_order": sales_order, "custom_drawing": ["is", "set"]},
        fields=["name", "item", "custom_drawing", "custom_duno_mark_no",
                "custom_customer_drawing_number"],
    )
    rows = []
    for b in batches:
        if not dn.is_tracked_fg_item(b.item):
            continue
        completed = _completed_nos(b.name)
        if completed <= 0:
            continue
        delivered = flt(sum(_dn_nos(b.name, 1).values()), 3)
        draft_by_wh = _dn_nos(b.name, 0)
        stock_by_wh = fg_stock.fg_batch_nos_by_warehouse(b.name)

        # Both totals are over the Completed pieces, so the customer's weight and the
        # weight actually booked can be compared like with like -- and neither moves
        # as pieces are delivered, which would make the comparison mean nothing.
        cust_per_pcs = flt(fg_stock.planned_kg_per_nos(b.custom_drawing, b.name), 3)
        booked_kg = _booked_kg(b.name)
        base = {
            "drawing": b.custom_drawing,
            "duno_mark_no": b.custom_duno_mark_no or "",
            "customer_drawing_number": b.custom_customer_drawing_number or "",
            "fg_item": b.item,
            "fg_batch": b.name,
            "completed_qty": completed,
            "delivered_qty": delivered,
            "cust_weight_per_pcs": cust_per_pcs,
            "total_cust_weight": flt(cust_per_pcs * completed, 3),
            "total_stock_weight": booked_kg,
            "stock_weight_per_pcs": flt(booked_kg / completed, 3) if completed else 0.0,
        }
        if not stock_by_wh:
            rows.append(dict(base, warehouse="", draft_qty=flt(sum(draft_by_wh.values()), 3),
                             available_qty=0.0, stock_nos=0.0, stock_kg=0.0))
            continue
        for wh, nos in sorted(stock_by_wh.items()):
            draft = flt(draft_by_wh.get(wh), 3)
            # This warehouse's own Nos and Kg: what Delivery Weight is priced against,
            # in the browser as the plan is typed and here for a kept plan.
            stock = fg_stock.fg_batch_available(b.name, wh)
            rows.append(dict(base, warehouse=wh, draft_qty=draft,
                             available_qty=flt(max(nos - draft, 0), 3),
                             stock_nos=flt(stock["nos"], 3), stock_kg=flt(stock["kg"], 3)))

    rows.sort(key=lambda r: (_natural_key(r["duno_mark_no"]), r["fg_batch"], r["warehouse"]))
    return rows


# ── Keeping the stored table current ──────────────────────────────────────────


def _key(row):
    return (row.get("fg_batch") or "", row.get("warehouse") or "")


def _write_rows(sales_order, rows):
    """Replace the stored rows, straight into the child table (see module docstring)."""
    frappe.db.delete(CHILD, {"parent": sales_order, "parenttype": "Sales Order",
                             "parentfield": FIELD})
    now, user = now_datetime(), frappe.session.user
    for idx, r in enumerate(rows, start=1):
        child = frappe.get_doc(dict(
            r, doctype=CHILD, parent=sales_order, parenttype="Sales Order",
            parentfield=FIELD, idx=idx, docstatus=1,
            owner=user, modified_by=user, creation=now, modified=now,
        ))
        child.db_insert()


@frappe.whitelist()
def refresh_delivery_plan(sales_order):
    """The Refresh button. Rebuilds the tab and keeps any saved Delivery Plan (Nos).

    Always keeps them: clearing a plan is Create Delivery's job, once it has turned
    the plan into a note, and a Refresh click should never be able to throw away
    what somebody else typed and saved.
    """
    if not frappe.has_permission("Sales Order", "read", doc=sales_order):
        frappe.throw(_("Not permitted to read this Sales Order"), frappe.PermissionError)
    return _refresh(sales_order, keep_plan=True)


def _refresh(sales_order, keep_plan=True):
    """Rebuild the Delivery Plan rows from the ledger. Returns the rows written.

    No permission check, deliberately: this is also what the Stock Entry and
    Delivery Note hooks call, as whoever submitted that document -- a store user who
    may have no access to the Sales Order at all. The table is derived data; keeping
    it true is not an action that user is taking.

    keep_plan -- carry over a Delivery Plan (Nos) already saved on a row, matched on
    (batch, warehouse) and cut down to what is still available.
    """
    if frappe.db.get_value("Sales Order", sales_order, "docstatus") != 1:
        return []

    kept = {}
    if keep_plan:
        for r in frappe.get_all(CHILD, filters={"parent": sales_order, "parentfield": FIELD},
                                fields=["fg_batch", "warehouse", "delivery_plan_qty"]):
            if flt(r.delivery_plan_qty) > 0:
                kept[_key(r)] = flt(r.delivery_plan_qty)

    rows = build_plan_rows(sales_order)
    for r in rows:
        r["delivery_plan_qty"] = min(kept.get(_key(r), 0.0), r["available_qty"])
        r["delivery_weight"] = delivery_weight(r, r["delivery_plan_qty"])
    _write_rows(sales_order, rows)
    return rows


def refresh_plans_for_batches(batch_nos):
    """Rebuild the plan of every Sales Order these FG batches belong to.

    Called from the Stock Entry and Delivery Note submit/cancel hooks. Must never be
    able to fail them: a note that cannot submit because a display table could not be
    refreshed is the wrong way round, so everything here is caught and logged.
    """
    try:
        orders = set()
        for b in batch_nos or []:
            so = frappe.db.get_value("Batch", b, "custom_sales_order")
            if so:
                orders.add(so)
        for so in orders:
            _refresh(so)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Delivery Plan: could not refresh")


# ── Create Delivery ───────────────────────────────────────────────────────────


@frappe.whitelist()
def create_delivery_from_plan(sales_order, plan):
    """Make a draft Delivery Note from the Delivery Plan (Nos) typed on the tab.

    plan -- [{fg_batch, warehouse, delivery_plan_qty}] as the form holds them. Taken
    from the form rather than the stored rows because they are typed on a submitted
    order and need not have been saved; everything in it is checked again here
    against the ledger, so nothing the browser sends is trusted.

    Returns the Delivery Note name. The note is inserted as a draft -- priced and
    checked by its own validate -- for the user to review and submit, the same as a
    note made from Create > Delivery Note.
    """
    if not frappe.has_permission("Delivery Note", "create"):
        frappe.throw(_("Not permitted to create a Delivery Note"), frappe.PermissionError)
    if not frappe.has_permission("Sales Order", "read", doc=sales_order):
        frappe.throw(_("Not permitted to read this Sales Order"), frappe.PermissionError)
    so = frappe.get_doc("Sales Order", sales_order)
    if so.docstatus != 1:
        frappe.throw(_("Submit the Sales Order before creating a delivery from it."))

    wanted = []
    for p in (frappe.parse_json(plan) if isinstance(plan, str) else plan) or []:
        qty = flt(p.get("delivery_plan_qty"), 3)
        if qty:
            wanted.append((p.get("fg_batch") or "", p.get("warehouse") or "", qty))
    if not wanted:
        frappe.throw(_("Enter a Delivery Plan NOS on at least one drawing first."),
                     title=_("Nothing Planned"))

    live = {_key(r): r for r in build_plan_rows(sales_order)}
    problems = []
    for batch, wh, qty in wanted:
        row = live.get((batch, wh))
        label = _("{0} ({1})").format(frappe.bold((row or {}).get("duno_mark_no") or batch),
                                      (row or {}).get("drawing") or "-")
        if not row:
            problems.append(_("{0}: this batch has no pieces in {1} any more. Refresh the "
                              "Delivery Plan.").format(label, wh or _("any warehouse")))
        elif qty < 0 or flt(qty, 3) != cint(qty):
            problems.append(_("{0}: Delivery Plan must be a whole number of pieces "
                              "(got {1}).").format(label, qty))
        elif qty > row["available_qty"]:
            msg = _("{0}: {1} Nos planned but only {2} available.").format(
                label, cint(qty), cint(row["available_qty"]))
            drafts = _draft_notes(batch)
            if drafts:
                msg += " " + _("{0} Nos are already on draft Delivery Note(s) {1} -- submit "
                               "or delete those first.").format(
                    cint(row["draft_qty"]), ", ".join(drafts))
            problems.append(msg)
    if problems:
        frappe.throw("<br>".join(problems), title=_("Delivery Plan Cannot Be Created"))

    note = _build_note(so, [(live[(b, w)], q) for b, w, q in wanted])
    note.insert()

    # The pieces are on a draft note now, so they come off Available, and the plan
    # that produced them is spent.
    _refresh(sales_order, keep_plan=False)
    return note.name


def _build_note(so, planned):
    """A draft Delivery Note holding exactly the planned drawings.

    Mapped by the app's own make_delivery_note (customer, addresses, taxes, rates,
    accounts, the Sales Order line) and then reduced to one row per planned drawing,
    each copied from that line's mapped row with its own batch, warehouse and Nos.
    Rows the plan did not ask for are left off: this note is the plan.
    """
    from manufyxinvenzaerp.selling_management.mapping import make_delivery_note

    note = make_delivery_note(so.name)

    # The mapped FG row for each Sales Order line is the template: it carries the
    # rate, UOM, accounts and so_detail a hand-made row would get.
    templates = {}
    for row in note.get("items"):
        if row.get("so_detail") and dn.is_tracked_fg_item(row.item_code):
            templates.setdefault(row.so_detail, row)

    # Lines of each FG item in Sales Order order, with their pending Nos, so a plan
    # spread over two lines of one item fills the first before the second.
    lines = {}
    for line in so.items:
        if line.name in templates:
            lines.setdefault(line.item_code, []).append(
                [line.name, flt(dn.pending_nos(line.name), 3)])

    skip = {"name", "idx", "batch_no", "serial_and_batch_bundle", "docstatus",
            "parent", "parenttype", "parentfield", "creation", "modified",
            "owner", "modified_by"}
    new_rows = []
    for row, qty in planned:
        remaining = qty
        for entry in lines.get(row["fg_item"], []):
            if remaining <= 0:
                break
            take = min(remaining, entry[1])
            if take <= 0:
                continue
            base = {k: v for k, v in templates[entry[0]].as_dict().items() if k not in skip}
            per_nos = fg_stock.planned_kg_per_nos(row["drawing"]) or 0
            base.update({
                "batch_no": row["fg_batch"],
                "use_serial_batch_fields": 1,
                "warehouse": row["warehouse"],
                "custom_sec_qty": take,
                "custom_sec_uom": dn.SEC_UOM,
                "custom_drawing": row["drawing"],
                "custom_duno_mark_no": row["duno_mark_no"],
                # A placeholder only: validate prices the batch's real Kg for these
                # pieces (last-piece rule) and re-totals the note.
                "qty": flt(per_nos * take, 3) or take,
            })
            new_rows.append(base)
            entry[1] -= take
            remaining -= take
        if remaining > 0:
            frappe.throw(
                _("{0} ({1}): {2} Nos planned, but the Sales Order has only {3} Nos of {4} "
                  "still to deliver.").format(
                    frappe.bold(row["duno_mark_no"] or row["fg_batch"]), row["drawing"],
                    cint(qty), cint(qty - remaining), row["fg_item"]),
                title=_("More Planned Than Ordered"),
            )

    note.set("items", [])
    for r in new_rows:
        note.append("items", r)
    note.run_method("set_missing_values")
    note.run_method("calculate_taxes_and_totals")
    return note
