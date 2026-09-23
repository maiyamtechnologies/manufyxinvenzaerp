"""The secondary quantity is headed NOS everywhere, and nothing but the heading moved.

Raw material and finished goods are kept in Kg (primary UOM) with pieces as the
secondary UOM. The pieces field was headed ten different ways -- Sec Qty, Sec Nos,
Sec Qty (NOS), Qty (Nos), Reqd Sec Qty, Required Sec Qty, Total Sec Qty... -- across
~110 fields and ~40 doctypes. The rule now:

  * the row's own pieces quantity (the one that pairs with its Kg) -> NOS
  * every other pieces figure -> "<Qualifier> NOS" (Completed NOS, Delivered NOS...),
    so no two columns on one table read the same
  * Sec UOM keeps its label but leaves every grid -- the unit is in the heading now
  * the Stock Entry grid shows Stock UOM; Basic Rate moved into the row to pay for it

Labels only. Field names, the core Qty (Kg) field and all logic are unchanged, which
is why several checks here assert what did NOT move:

  * weight fields ("Cust Weight (per Nos)", "Kg per Piece") hold Kg, not a count;
  * Job Card / Work Order leftovers -- those two doctypes carry no customizations;
  * the BOM Excel import matches column headers BY NAME against customers' sheets,
    so its headers are a data contract and must never follow a relabel.

Standard-doctype fields are defined twice (setup.py and custom/*.json) and setup.py
wins on migrate, so this reads the EFFECTIVE meta rather than either source file.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_nos_labels.run
"""

import frappe

checks = []

# (doctype, fieldname) -> label. The approved map.
LABELS = {}
for _dt in ("Material Request Item", "Material Request Plan Item", "Request for Quotation Item",
            "Supplier Quotation Item", "Purchase Order Item", "Purchase Receipt Item",
            "Subcontracting Order Item", "Sales Order Item", "Delivery Note Item",
            "Sales Invoice Item", "Stock Entry Detail", "BOM", "BOM Item", "Batch",
            "Production Plan Item"):
    LABELS[(_dt, "custom_sec_qty")] = "NOS"
LABELS.update({
    ("Sales Order Item", "custom_delivered_sec_qty"): "Delivered NOS",
    ("Sales Order Item", "custom_billed_sec_qty"): "Billed NOS",
    ("Delivery Note Item", "custom_billed_sec_qty"): "Billed NOS",
    ("Stock Entry", "custom_total_sec_qty"): "Total NOS",
})
_OWN = {
    "Drawing Item": {"sec_qty": "NOS", "total_sec_qty": "Total NOS"},
    "Sales Order Drawing Raw Material": {"sec_qty": "NOS", "total_sec_qty": "Total NOS"},
    "Sales Order Delivery Plan": {
        "completed_qty": "Completed NOS", "delivered_qty": "Delivered NOS",
        "draft_qty": "In Draft DN NOS", "available_qty": "Available NOS",
        "delivery_plan_qty": "Delivery Plan NOS", "stock_nos": "Stock NOS"},
    "Material Planning Raw Material": {"sec_qty": "NOS"},
    "Material Planning Consolidate Item": {"sec_qty": "NOS"},
    "Production Plan Available Raw Material": {"custom_sec_qty": "NOS"},
    "Production Plan BOM Raw Material": {"sec_qty": "NOS"},
    "Material Planning Available Raw Material": {
        "sec_qty": "NOS", "balance_sec_qty": "Balance NOS", "use_sec_qty": "To Use NOS"},
    "Material Planning Material Mapping": {
        "batch_sec_qty": "NOS", "sec_qty": "Required NOS",
        "cut_sheet_avail_sec_qty": "Free on Sheet NOS",
        "balance_sec_qty": "Balance NOS", "use_sec_qty": "To Use NOS"},
    "Material Planning Unavailable Item": {"sec_qty": "NOS", "alternate_sec_qty": "Alternate NOS"},
    "Material Planning Batch Change Log": {"old_sec_qty": "Old NOS", "new_sec_qty": "New NOS"},
    "Material Planning BOM Item": {"qty_to_manufacture": "To Manufacture NOS"},
    "Material Issue Plan": {"excess_return_total_nos": "Total Return NOS"},
    "Material Issue Plan Raw Material": {
        "sec_qty": "NOS", "balance_sec_qty": "Balance NOS", "use_sec_qty": "To Use NOS"},
    "Material Issue Plan Consolidate Item": {
        "sec_qty": "NOS", "draft_sec_qty": "Draft NOS", "draft_excess_sec_qty": "Draft Excess NOS"},
    "SCO Excess Material Item": {
        "sec_qty": "NOS", "available_sec_qty": "Available NOS", "allocated_sec_qty": "Allocated NOS"},
    "SCO Drawing Item": {"completed_qty_nos": "Completed NOS", "qty_to_manufacture": "To Manufacture NOS"},
    "Supplier Operation Entry": {
        "total_available_nos": "Available to Consume NOS", "total_completed_nos": "Total Consumed NOS"},
    "SOE Drawing Detail": {
        "available_to_consume_nos": "Available NOS", "completed_qty_nos": "Completed NOS",
        "qty_to_manufacture": "To Manufacture NOS"},
    "SOE Consumption Log": {"qty_nos": "NOS"},
    "SOE Inspection Item": {"qty_nos": "Completed NOS"},
    "Supplier Operation Item": {
        "current_sec_qty": "NOS", "prev_operation_sec_qty": "Prev Op NOS",
        "transferred_sec_qty": "Transferred NOS"},
    "Cut Sheet": {
        "sheet_sec_qty": "NOS", "available_sec_qty": "Available NOS",
        "allocated_sec_qty": "Allocated NOS", "w1_sec_qty": "W1 NOS", "w2_sec_qty": "W2 NOS"},
    "Cut Sheet Allocation": {"sec_qty": "NOS"},
    "Manufyx Decision Log": {"sec_qty": "NOS", "previous_sec_qty": "Previous NOS"},
}
for _dt, _m in _OWN.items():
    for _fn, _lab in _m.items():
        LABELS[(_dt, _fn)] = _lab

OLD_WORDING = ("Sec Qty", "Sec Nos", "Sec NOS", "(Nos)", "(NOS)")
_LAYOUT = ("Section Break", "Column Break", "Tab Break", "Table Break")

# The list-view flags this change touched, as they were before it. Section 6 puts
# them back to measure each grid as it was, so "did this change push a column off?"
# is answered by comparison rather than assumed.
_BEFORE = {
    ("Material Request Item", "custom_sec_uom"): 1, ("Purchase Order Item", "custom_sec_uom"): 1,
    ("Purchase Receipt Item", "custom_sec_uom"): 1, ("Request for Quotation Item", "custom_sec_uom"): 1,
    ("Supplier Quotation Item", "custom_sec_uom"): 1, ("Material Planning Unavailable Item", "sec_uom"): 1,
    ("Stock Entry Detail", "stock_uom"): 0, ("Stock Entry Detail", "basic_rate"): 1,
}


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _colsize(f):
    """grid.js update_default_colsize, exactly: 2, or 3 for Text / Small Text, 1 for
    Check -- unless the field sets its own `columns`. (An earlier draft of this check
    guessed 1 for Float and reported columns lost that were simply mis-measured.)"""
    if f.columns:
        return f.columns
    return 3 if f.fieldtype in ("Text", "Small Text") else (1 if f.fieldtype == "Check" else 2)


def _grid(doctype, before=False):
    """(shown, dropped) as grid.js setup_visible_columns renders the doctype: the total
    starts at 1 and the first column that takes it past 11 is dropped with every one
    after it. before=True measures it with this change's list-view flags undone."""
    shown, dropped, total = [], [], 1
    for f in frappe.get_meta(doctype).fields:
        lv = _BEFORE.get((doctype, f.fieldname), f.in_list_view) if before else f.in_list_view
        if f.hidden or not lv or f.fieldtype in _LAYOUT:
            continue
        total += _colsize(f)
        (dropped if total > 11 else shown).append(f.fieldname)
    return shown, dropped


def run():
    for dt in {k[0] for k in LABELS} | {"Stock Entry Detail"}:
        frappe.clear_cache(doctype=dt)

    print("=== 1. Every pieces field carries its approved heading ===")
    wrong = []
    for (dt, fn), want in sorted(LABELS.items()):
        f = frappe.get_meta(dt).get_field(fn)
        got = f.label if f else None
        if got != want:
            wrong.append("%s.%s=%r" % (dt, fn, got))
    check("all %d fields labelled as approved" % len(LABELS), wrong, [])

    print()
    print("=== 2. No two pieces fields on one doctype read the same ===")
    clashes = []
    for dt in sorted({k[0] for k in LABELS}):
        labels = [LABELS[k] for k in LABELS if k[0] == dt]
        dup = sorted({l for l in labels if labels.count(l) > 1})
        if dup:
            clashes.append("%s: %s" % (dt, dup))
    check("no duplicate NOS headings", clashes, [])

    print()
    print("=== 3. No pieces field still wears the old wording ===")
    # Over every field on the touched doctypes, not just the mapped ones, so a pieces
    # field this map missed cannot hide behind it. Weight fields are allowed their
    # "(per Nos)" -- they hold Kg per piece, and the check skips them by that phrase.
    stale = []
    for dt in sorted({k[0] for k in LABELS}):
        for f in frappe.get_meta(dt).fields:
            lab = f.label or ""
            if "per Nos" in lab or "Kg" in lab:
                continue
            if any(w in lab for w in OLD_WORDING):
                stale.append("%s.%s=%r" % (dt, f.fieldname, lab))
    check("none left", stale, [])

    print()
    print("=== 4. Sec UOM keeps its label and leaves every grid ===")
    in_grid, relabelled = [], []
    for (dt, fn) in [(k[0], k[1]) for k in LABELS]:
        for uom_fn in ("custom_sec_uom", "sec_uom"):
            f = frappe.get_meta(dt).get_field(uom_fn)
            if f and f.in_list_view:
                in_grid.append("%s.%s" % (dt, uom_fn))
            if f and f.label != "Sec UOM":
                relabelled.append("%s.%s=%r" % (dt, uom_fn, f.label))
    check("no Sec UOM in any grid", sorted(set(in_grid)), [])
    check("and its label is still Sec UOM", sorted(set(relabelled)), [])

    print()
    print("=== 5. Stock Entry grid: Stock UOM in, Basic Rate in the row ===")
    shown, dropped = _grid("Stock Entry Detail")
    check("Stock UOM is shown", "stock_uom" in shown, True)
    check("Basic Rate left the grid", "basic_rate" in shown or "basic_rate" in dropped, False)
    check("  but is still on the row (not hidden)",
          bool(frappe.get_meta("Stock Entry Detail").get_field("basic_rate").hidden), False)
    check("NOS and Qty (Kg) are both shown",
          ("custom_sec_qty" in shown, "qty" in shown), (True, True))
    check("nothing runs off the end of the grid", dropped, [])

    print()
    print("=== 6. This change pushed no column off any grid ===")
    # A relabel changes no width. Sec UOM leaving freed a column in five grids and
    # Stock UOM took one in Stock Entry -- so each grid is measured before and after,
    # and nothing may be dropped now that was shown before.
    tables = sorted({k[0] for k in LABELS if frappe.get_meta(k[0]).istable} | {"Stock Entry Detail"})
    newly_lost, hidden_before = [], []
    for dt in tables:
        _, before = _grid(dt, before=True)
        _, after = _grid(dt)
        newly_lost += ["%s.%s" % (dt, fn) for fn in after if fn not in before]
        hidden_before += ["%s.%s" % (dt, fn) for (d, fn) in LABELS if d == dt and fn in before]
    check("no column newly dropped by this change", newly_lost, [])
    # Not asserted -- it predates this change and fixing it means choosing what leaves
    # each grid. Printed so it stays visible: these NOS columns are past their grid's
    # 11-column budget, so Frappe does not render them in the table at all (they are
    # still on the row). Relabelling cannot make a column Frappe never draws visible.
    if hidden_before:
        print("    (pre-existing, not from this change) NOS past the grid budget:")
        for h in hidden_before:
            print("      " + h)

    print()
    print("=== 7. What must NOT have moved ===")
    for dt, fn, want in (
        ("Drawing", "weight_per_pcs", "Cust Weight (per Nos)"),
        ("Sales Order DUNO Item", "weight_per_pcs", "Cust Weight (per Nos)"),
        ("SCO Drawing Item", "cust_weight_per_nos", "Cust Weight (per Nos)"),
        ("Cut Sheet", "w1_qty_per_nos", "Kg per Piece"),
        ("Stock Entry Detail", "qty", "Qty"),
    ):
        f = frappe.get_meta(dt).get_field(fn)
        check("%s.%s unchanged" % (dt, fn), f.label if f else None, want)
    # The BOM Excel import matches headers by name against customers' own sheets.
    import inspect
    from manufyxinvenzaerp.drawing_management import so_drawing_import
    src = inspect.getsource(so_drawing_import.download_bom_template)
    check("the BOM Excel template headers are untouched",
          '"Cust Weight (per Nos)"' in src and '"Reqd Raw Material Qty"' in src, True)

    _summary()


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
