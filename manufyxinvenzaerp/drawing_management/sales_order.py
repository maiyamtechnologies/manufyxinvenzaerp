import frappe
from frappe import _
from frappe.utils import flt
from manufyxinvenzaerp.utils.dimension_formula import calculate_qty


def drawing_calculated_weight(rows, drawing_number):
    """What the raw materials listed under one drawing weigh in total.

    The counterpart to the drawing's Customer Provided Weight, which is typed in
    from the sheet and describes the FINISHED piece. This one is never typed:
    it is the sum of the rows' own calculated weights, and it is normally the
    larger of the two because stock is cut down to the part. A drawing where it
    comes out SMALLER is the case worth looking at -- the material listed cannot
    produce the piece.
    """
    return flt(sum(
        flt(r.get("qty")) for r in (rows or [])
        if r.get("customer_drawing_number") == drawing_number
    ), 3)


def recalculate_raw_material_qty(doc, method):
    """Recalculate qty, total_sec_qty and total_weight on unlocked raw material rows."""
    # Build lookup: drawing_number → total_quantity from the Drawing List table
    total_qty_map = {}
    for dr in (doc.custom_duno_items or []):
        if dr.drawing_number:
            total_qty_map[dr.drawing_number] = flt(dr.total_quantity) or 1.0

    for row in (doc.custom_so_raw_materials or []):
        # row.get("is_locked"), never row.is_locked: frappe's Document class
        # defines is_locked as a property (it reports whether a FILE LOCK is
        # held on the document), and a class property shadows the field of the
        # same name on every instance. The attribute therefore always reads
        # False no matter what the column holds, so this loop was recalculating
        # locked rows too -- rewriting rows a Drawing had already been built
        # from whenever the Sales Order was saved. .get() reads the row's own
        # data and returns the stored value.
        if row.get("is_locked"):
            continue
        pig = row.parent_item_group or ""
        unit_wt = flt(row.unit_weight)
        length = flt(row.length)
        width = flt(row.width)
        thickness = flt(row.thickness)
        sec_qty = flt(row.sec_qty)
        tq = total_qty_map.get(row.customer_drawing_number, 1.0)

        if pig in ("Structurals", "Plates"):
            qty = calculate_qty(pig, length, width, thickness, unit_wt, sec_qty)
            qty = qty if qty is not None else 0.0
        else:
            qty = sec_qty

        row.qty = flt(qty, 3)
        row.total_sec_qty = flt(sec_qty * tq, 3)
        row.total_weight = flt(qty * tq, 3)

    # Roll the row weights up onto each drawing. Done after the loop so it picks
    # up the values just recalculated, and for locked drawings too -- their rows
    # are frozen, so the total simply restates what is already there.
    for dr in (doc.custom_duno_items or []):
        if dr.drawing_number:
            dr.calculated_weight = drawing_calculated_weight(
                doc.custom_so_raw_materials, dr.drawing_number
            )

    # hooks.py registers only this function for Sales Order validate, and hooks.py
    # belongs to the schema wave, so the finished-goods checks ride in from here.
    validate_fg_lines(doc)


# ---------------------------------------------------------------------------
# Finished goods: the order line in Kg, the drawings in Nos (sep14 plan D1-D3,
# D24, D25). An FG line's Quantity is its total weight in Kg and its Qty (Nos) the
# number of pieces; the Drawing List rows of that item have to add up to both.
# ---------------------------------------------------------------------------

# Drawing List fields that describe what the customer ordered for one drawing. Once
# the Drawing exists they are copied into it and everything downstream, so from then
# on the Drawing is the source and the row only follows it (D24).
DRAWN_ROW_LOCKED_FIELDS = {
    # Sales Order DUNO Item field -> the Drawing field it was copied into
    "weight_per_pcs": "weight_per_pcs",
    "total_weight": "customer_provided_wt",
    "total_quantity": "no_of_qty_to_manufacture",
}

# What Verify Raw Materials reads on a Drawing List row that is still waiting for its
# Drawing. Changing any of them after a pass means the pass no longer describes the rows.
PENDING_ROW_VERIFIED_FIELDS = ("item", "total_quantity", "weight_per_pcs", "total_weight")


def fmt_qty(value):
    """A Kg or Nos figure at 3 decimals without trailing zeros: 250, 245.5, 30.214."""
    text = "%.3f" % flt(value, 3)
    text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def fg_line_totals(doc):
    """Per FG item on the order: what the lines order vs what the drawings add up to.

    Grouped by item rather than by line because a Drawing List row names its FG item,
    not a line -- if the same item sits on two lines, their drawings cannot be told
    apart, so the lines are compared together. Every Drawing List row of the item
    counts, created or not: the order is for all of them.

    Returns a list of dicts in line order, one per FG item on the items table:
    item_code, idx (its first line), ordered_kg, ordered_nos, drawing_kg, drawing_nos,
    and matches (both figures equal at 3 decimals, D14).
    """
    from manufyxinvenzaerp.production_management.fg_stock import is_fg_item

    totals = {}
    for line in (doc.get("items") or []):
        if not line.get("item_code") or not is_fg_item(line.item_code):
            continue
        t = totals.setdefault(line.item_code, frappe._dict(
            item_code=line.item_code, idx=line.idx,
            ordered_kg=0.0, ordered_nos=0.0, drawing_kg=0.0, drawing_nos=0.0,
        ))
        t.ordered_kg += flt(line.qty)
        t.ordered_nos += flt(line.get("custom_sec_qty"))

    for row in (doc.get("custom_duno_items") or []):
        t = totals.get(row.get("item"))
        if t:
            t.drawing_kg += flt(row.get("total_weight"))
            t.drawing_nos += flt(row.get("total_quantity"))

    for t in totals.values():
        for key in ("ordered_kg", "ordered_nos", "drawing_kg", "drawing_nos"):
            t[key] = flt(t[key], 3)
        t.matches = t.ordered_kg == t.drawing_kg and t.ordered_nos == t.drawing_nos
    return list(totals.values())


def fg_line_mismatch_text(t):
    """One sentence for an FG item whose drawings do not add up to its order lines:
    ordered vs drawings, in Kg and in Nos, and the difference of each."""
    return _(
        "FG Item <b>{0}</b>: the order is for <b>{1} Kg / {2} Nos</b> but the Drawing List "
        "adds up to <b>{3} Kg / {4} Nos</b> — difference {5} Kg / {6} Nos. "
        "The Cust Weight (Total) of its drawings must add up to the line Quantity, and their "
        "Total Quantity to the line Qty (Nos)."
    ).format(
        t.item_code, fmt_qty(t.ordered_kg), fmt_qty(t.ordered_nos),
        fmt_qty(t.drawing_kg), fmt_qty(t.drawing_nos),
        _signed(t.drawing_kg - t.ordered_kg), _signed(t.drawing_nos - t.ordered_nos),
    )


def _signed(value):
    value = flt(value, 3)
    return ("+" if value > 0 else "") + fmt_qty(value)


def validate_fg_lines(doc):
    """Sales Order validate, finished-goods part. Order matters: the lock throws
    before anything is changed or said."""
    lock_drawn_rows(doc)
    clear_verified_on_fg_change(doc)
    warn_fg_line_totals(doc)


def lock_drawn_rows(doc, method=None):
    """Refuse a change to the weights or Nos of a Drawing List row that has a Drawing.

    The form makes those cells read-only (read_only_depends_on), but that is only the
    browser; an import, an API call or a stale form could still send new figures, and
    they would then disagree with the Drawing, its BOM and every plan built from it.

    The one change let through is the row following its own Drawing: Update Customer
    Weight saves the Drawing first and then writes the same figures here, so a new
    value that equals the Drawing's is that update, not an edit. Compared with the
    row as saved, so an untouched row is never looked up.

    Takes (doc, method) so it can also be registered on before_update_after_submit:
    a submitted order skips validate, so this guard covers drafts only until it is.
    """
    before = doc.get_doc_before_save()
    if not before:
        return
    saved = {r.name: r for r in (before.get("custom_duno_items") or [])}

    for row in (doc.get("custom_duno_items") or []):
        old = saved.get(row.name)
        if not row.get("drawing") or not old:
            continue
        changed = [f for f in DRAWN_ROW_LOCKED_FIELDS
                   if flt(row.get(f), 3) != flt(old.get(f), 3)]
        if not changed:
            continue
        drawing = frappe.db.get_value(
            "Drawing", row.drawing, list(DRAWN_ROW_LOCKED_FIELDS.values()), as_dict=True
        ) or {}
        if drawing and all(
            flt(row.get(f), 3) == flt(drawing.get(DRAWN_ROW_LOCKED_FIELDS[f]), 3) for f in changed
        ):
            continue
        labels = [_(row.meta.get_label(f)) for f in changed]
        frappe.throw(
            _("Drawing List row {0} (DUNO {1}): Drawing {2} has already been created from it, "
              "so {3} can no longer be changed here. Open the Drawing and use "
              "<b>Update Customer Weight</b>.").format(
                row.idx, row.get("duno_mark_no") or "?", row.drawing, ", ".join(labels)),
            title=_("Drawing List Row Locked"),
        )


def clear_verified_on_fg_change(doc):
    """Keep Raw Materials Verified honest: it may only be raised by Verify Raw
    Materials, and it drops as soon as anything that pass looked at changes.

    Create Drawing trusts the flag (D25), and Verify now checks the FG lines against
    the Drawing List (D3). A line whose Kg, Nos or item changes after the pass -- or a
    pending Drawing List row whose weights, Nos or item change -- could otherwise be
    turned into drawings on the strength of a check made against other figures.

    The flag is read-only on the form, but a save sends whatever the browser holds,
    so a raise that did not come from Verify is put back too.
    """
    if not doc.get("custom_raw_materials_verified"):
        return
    before = doc.get_doc_before_save()
    if not before or not before.get("custom_raw_materials_verified"):
        doc.custom_raw_materials_verified = 0
        return

    reasons = _fg_line_changes(doc, before) + _pending_row_changes(doc, before)
    if reasons:
        doc.custom_raw_materials_verified = 0
        frappe.msgprint(
            _("Raw materials need verifying again before drawings are created, because:")
            + "<br>" + "<br>".join("• " + r for r in reasons),
            title=_("Verification Cleared"), indicator="orange",
        )


def _fg_line_changes(doc, before):
    from manufyxinvenzaerp.production_management.fg_stock import is_fg_item

    def snap(d):
        return (d.get("item_code"), flt(d.get("qty"), 3), flt(d.get("custom_sec_qty"), 3))

    old = {d.name: d for d in (before.get("items") or [])}
    new = {d.name: d for d in (doc.get("items") or [])}
    reasons = []
    for name in list(new) + [n for n in old if n not in new]:
        a, b = old.get(name), new.get(name)
        if not any(d and is_fg_item(d.get("item_code")) for d in (a, b)):
            continue
        if a and b and snap(a) == snap(b):
            continue
        d = b or a
        reasons.append(_("Items row {0} ({1}): Item, Quantity or Qty (Nos) changed").format(
            d.idx, d.get("item_code") or "?"))
    return reasons


def _pending_row_changes(doc, before):
    def snap(d):
        return tuple(flt(d.get(f), 3) if f != "item" else d.get(f)
                     for f in PENDING_ROW_VERIFIED_FIELDS)

    old = {d.name: d for d in (before.get("custom_duno_items") or []) if not d.get("drawing")}
    new = {d.name: d for d in (doc.get("custom_duno_items") or []) if not d.get("drawing")}
    reasons = []
    for name in list(new) + [n for n in old if n not in new]:
        a, b = old.get(name), new.get(name)
        if a and b and snap(a) == snap(b):
            continue
        d = b or a
        reasons.append(_("Drawing List row {0} ({1}): FG Item, Total Quantity or Cust Weight changed")
                       .format(d.idx, d.get("duno_mark_no") or d.get("drawing_number") or "?"))
    return reasons


def warn_fg_line_totals(doc):
    """Orange note on save when an FG item's drawings do not add up to its lines.

    Only a note: while the sheet is being worked on, the lines and the drawings are
    expected to disagree for a while. The block is Verify Raw Materials, which refuses
    to pass until they agree. Said only when the order has a Drawing List at all --
    an order that is not built from drawings has nothing to compare.
    """
    if not doc.get("custom_duno_items"):
        return
    bad = [t for t in fg_line_totals(doc) if not t.matches]
    if bad:
        frappe.msgprint(
            "<br><br>".join(_("Items row {0}").format(t.idx) + " · " + fg_line_mismatch_text(t)
                            for t in bad),
            title=_("Drawing List does not match the order"), indicator="orange",
        )
