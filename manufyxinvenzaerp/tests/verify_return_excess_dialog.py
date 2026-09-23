"""The Return Excess Entry dialog is laid out and validated like the transfer popup.

It used to stack Length, Width and Sec Qty as three boxes inside one cell, which
made a five-row return hard to read and gave no clue which of them an item
actually uses. It now has a column per dimension, matching the transfer popup's
excess tab, and applies the same rules:

  * Width belongs to the Plates formula alone -- a Structurals row cannot type one.
  * Thickness is the batch's own and is shown read-only, because a cut changes
    Length and Width and never Thickness.
  * A row is refused until every figure its group's formula reads is present, so
    nothing is received back as 0 Kg.

The dialog is client-side, so this checks the markup and mirrors its rules against
the shared weight formula.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_return_excess_dialog.run
"""

import os
import re

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _dialog_source():
    path = os.path.join(
        frappe.get_app_path("manufyxinvenzaerp"),
        "subcontracting_management", "doctype", "material_issue_plan", "material_issue_plan.js",
    )
    with open(path) as f:
        js = f.read()
    start = js.index("function _show_return_excess_dialog")
    end = js.index("frappe.ui.form.on(\"SCO Excess Material Item\"")
    return js[start:end]


def run():
    from manufyxinvenzaerp.utils.dimension_formula import calculate_qty

    js = _dialog_source()

    print("=== one column per dimension, as on the transfer popup ===")
    for column in ("Item Code", "Length (mm)", "Width (mm)", "Thickness (mm)",
                   "NOS", "Qty (Kg)", "Return Reason"):
        check("column: %s" % column, '__("%s")' % column in js, True)
    check("the old stacked cell is gone", "Length / Width / Sec Qty" in js, False)

    print()
    print("=== the same rules about which dimensions an item uses ===")
    check("width is for Plates only", 'let uses_width = g === "Plates";' in js, True)
    check("...and its box is disabled otherwise",
          'box("_rex_width", r.width, dim_driven && uses_width)' in js, True)
    check("thickness is shown, not typed", "_rex_thickness" in js, False)
    check("a non-dimensioned group types its weight directly", "_rex_qty" in js, True)

    print()
    print("=== nothing may be returned as a weight of zero ===")
    check("incomplete rows are collected", "let incomplete = []" in js, True)
    check("Length is required", 'if (!entry.length) need.push(__("Length"))' in js, True)
    check("Width only where the formula reads it",
          'if (g === "Plates" && !entry.width)' in js, True)
    check("NOS is required", 'if (!entry.sec_qty) need.push(__("NOS"))' in js, True)
    check("a typed weight must be above zero", "if (entry.qty <= 0)" in js, True)
    check("the message names the rows", "Measurements Incomplete" in js, True)
    check("a reason is still mandatory", "Reason Required" in js, True)
    check("...and names which rows are missing one", "missing_reason.map" in js, True)

    print()
    print("=== the dialog's rules agree with the shared formula ===")
    # Structurals: Length x Unit Weight x Sec Qty -- width plays no part, which is
    # why the box is disabled rather than merely ignored.
    with_width = calculate_qty("Structurals", 1200, 500, 0, 23.5, 2)
    without = calculate_qty("Structurals", 1200, 0, 0, 23.5, 2)
    check("a Structural weighs the same with or without a width",
          flt(with_width, 3), flt(without, 3))
    check("...and that weight is", flt(without, 3), 56.4)

    # Plates need every one of the three, so any missing figure yields nothing.
    check("a plate with no width has no weight",
          calculate_qty("Plates", 500, 0, 10, 7.85, 1), None)
    check("a plate with no thickness has no weight",
          calculate_qty("Plates", 500, 300, 0, 7.85, 1), None)
    check("a complete plate does", flt(calculate_qty("Plates", 500, 300, 10, 7.85, 1), 3), 11.775)
    check("a structural with no Sec Qty has no weight",
          calculate_qty("Structurals", 1200, 0, 0, 23.5, 0), None)

    print()
    print("=== the live preview still recalculates as figures are typed ===")
    # Delegated, so the extra size lines added by the duplicate icon recalculate too.
    check("bound to all three boxes",
          'dialog.$wrapper.on("input", "._rex_length, ._rex_width, ._rex_sec_qty"' in js, True)

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
