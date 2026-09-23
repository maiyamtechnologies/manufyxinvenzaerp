"""Shared dimension -> quantity formula and missing-field check for
Structurals / Plates / Nuts and Bolts items.

Consolidates logic that was previously copy-pasted, byte-for-byte identical,
across material_request.py, purchase_order.py, purchase_receipt.py, and
supplier_quotation.py (the `custom_`-prefixed procurement-chain row shape),
plus re-derived with a different row shape in sales_order.py,
so_drawing_import.py, drawing_utils.py, and the Drawing doctype controller
(Report 3 Finding H-08 / Report 6 Findings DC-01/DC-02).

No formula or threshold below has been changed from any of the pre-existing
copies -- this module only centralizes logic that was already identical (or,
for calculate_qty/calculate_sec_qty_from_qty, factors out the part of the
formula that WAS identical across every call site, leaving each call site's
own group-handling/fallback behavior for anything beyond Structurals/Plates
untouched at the call site, since that part genuinely differs by doctype).
"""

import frappe
from frappe import _

# ── Procurement-chain constants (Material Request / Purchase Order /
# Purchase Receipt / Supplier Quotation row shape -- all `custom_`-prefixed) ──

STRUCTURALS_REQUIRED = ["custom_length", "custom_unit_weight", "custom_sec_qty"]
PLATES_REQUIRED = ["custom_length", "custom_width", "custom_thickness", "custom_unit_weight", "custom_sec_qty"]
FIELD_LABELS = {
    "custom_length": "Length",
    "custom_width": "Width",
    "custom_thickness": "Thickness",
    "custom_unit_weight": "Unit Weight",
    "custom_sec_qty": "NOS",
}


def calculate_qty(parent_item_group, length, width, thickness, unit_weight, sec_qty):
    """Core Structurals/Plates dimension formula, shared by every call site.

    Returns the calculated qty, or None if the group isn't Structurals/Plates,
    or if the required inputs for that group aren't all present yet (mirrors
    every pre-existing copy's "leave qty untouched until inputs are ready"
    guard) -- callers decide what None means for their own row shape (leave
    the field untouched, or fall back to 0.0/another value), since that part
    of the behavior genuinely differs between call sites and is preserved
    at the call site rather than folded in here.
    """
    if parent_item_group == "Structurals":
        if length and unit_weight and sec_qty:
            return (length / 1000) * unit_weight * sec_qty
        return None
    if parent_item_group == "Plates":
        if length and width and thickness and unit_weight and sec_qty:
            return (length / 1000) * (width / 1000) * thickness * unit_weight * sec_qty
        return None
    return None


def calculate_sec_qty_from_qty(unit_weight, qty):
    """Nuts and Bolts inverse direction: Sec Qty (Kg) = Qty (Nos) x Unit Weight.

    Returns None if either input is falsy (mirrors every pre-existing copy's
    guard), leaving the caller's field untouched, matching current behavior.
    """
    if qty and unit_weight:
        return unit_weight * qty
    return None


def check_missing_fields(row, throw):
    """Shared missing-field check for the procurement-chain row shape
    (Material Request / Purchase Order / Purchase Receipt / Supplier
    Quotation Item rows) -- identical to what was previously duplicated
    verbatim across all four (Report 3 Finding H-08 / L-01)."""
    group = row.custom_parent_item_group
    if group == "Structurals":
        required = STRUCTURALS_REQUIRED
    elif group == "Plates":
        required = PLATES_REQUIRED
    else:
        return
    missing = [FIELD_LABELS[f] for f in required if not getattr(row, f, None)]
    if missing:
        msg = _("Row {0}: {1} required for {2} formula").format(
            row.idx, ", ".join(missing), group
        )
        if throw:
            frappe.throw(msg)
        else:
            frappe.msgprint(msg, indicator="orange", title=_("Missing Fields"))
