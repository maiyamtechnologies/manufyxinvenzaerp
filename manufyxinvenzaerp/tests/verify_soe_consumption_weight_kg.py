"""The Consumption Log states the per-piece weight and the row total, and they agree.

Originally a Phase 4.4 print-out that opened a hardcoded SCO-SOE-0056 and described
what the browser ought to show. That entry does not exist on every site, so the
script died with DoesNotExistError rather than checking anything -- it proved nothing
and failed loudly on any database but the one it was written against.

It now checks the thing it was always about. Wt per Pcs (Kg) used to be computed when
a row was entered and thrown away, leaving a row total with nothing to read it
against: 1,790.089 Kg for 4 Nos, beside a Transferred (Kg) of 6,846.680 on the
Drawing Details row, looks like a mismatch until you know one is this consumption and
the other is the whole drawing. Both figures are now on the row.

The direction that matters is that Total Weight stays the TOTAL. It is what adds up
into Total Consumed (Kg), which seeds the next operation's Available to Consume (Kg)
and backs the Op-1 over-consume guard -- so a well-meant "make Weight (Kg) the
per-piece figure" would move the Kg ledger on every operation in every routing.
Check 3 is that invariant.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_soe_consumption_weight_kg.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-60s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    meta = frappe.get_meta("SOE Consumption Log")

    print("=== 1. Both figures exist on the row, and are derived ===")
    for fn, label in (("wt_per_pcs_kg", "Wt per Pcs (Kg)"),
                      ("weight_kg", "Total Weight (Kg)")):
        f = meta.get_field(fn)
        check("%s is present, read-only and in the grid" % label,
              (bool(f), bool(f and f.read_only), bool(f and f.in_list_view)),
              (True, True, True))

    # The grid drops columns silently once the widths pass 11 (grid.js
    # setup_visible_columns), so adding one has to be measured, not assumed.
    total = 1
    for f in meta.fields:
        if f.hidden or not f.in_list_view or f.fieldtype in ("Section Break", "Column Break"):
            continue
        total += f.columns or (1 if f.fieldtype in ("Float", "Int", "Date", "Check") else 2)
    check("  and the grid still fits its column budget", total <= 11, True)

    print()
    print("=== 2. Per-piece x quantity is the row total ===")
    rows = frappe.get_all(
        "SOE Consumption Log",
        filters={"qty_nos": [">", 0], "weight_kg": ["!=", 0]},
        fields=["name", "parent", "drawing", "qty_nos", "wt_per_pcs_kg", "weight_kg"],
        limit=25, order_by="modified desc",
    )
    if not rows:
        print("    (no consumption logged on this site yet -- nothing to measure)")
    for r in rows[:5]:
        # One gram of tolerance per piece: Wt per Pcs is stored rounded to 3 decimals
        # for display while the total is computed off the unrounded figure, so
        # multiplying the displayed value back cannot always land on it exactly.
        gap = abs(flt(r.wt_per_pcs_kg) * flt(r.qty_nos) - flt(r.weight_kg))
        check("  %s row: %s x %s = %s" % (r.parent, r.wt_per_pcs_kg, r.qty_nos, r.weight_kg),
              gap <= 0.001 * flt(r.qty_nos), True)

    print()
    print("=== 3. Total Weight is what Total Consumed is made of ===")
    # The invariant the ledger rests on, measured on a real entry rather than asserted.
    parent = rows[0].parent if rows else None
    if not parent:
        print("    (nothing logged -- skipped)")
    else:
        soe = frappe.get_doc("Supplier Operation Entry", parent)
        logged = flt(sum(flt(c.weight_kg) for c in (soe.consumption_log or [])), 3)
        check("  %s: sum of Total Weight equals Total Consumed (Kg)" % parent,
              logged, flt(soe.total_consumed_kg, 3))
        per_pcs_sum = flt(sum(flt(c.wt_per_pcs_kg) for c in (soe.consumption_log or [])), 3)
        # Only meaningful where some row logged more than one piece; with every row at
        # 1 Nos the two sums coincide legitimately and the check proves nothing.
        if any(flt(c.qty_nos) > 1 for c in (soe.consumption_log or [])):
            check("  and NOT the sum of the per-piece weights",
                  per_pcs_sum != flt(soe.total_consumed_kg, 3), True)

    print()
    print("=== 4. The drawings behind it carry usable weights ===")
    if parent:
        soe = frappe.get_doc("Supplier Operation Entry", parent)
        for r in (soe.drawing_details or [])[:5]:
            d = frappe.db.get_value(
                "Drawing", r.drawing,
                ["total_weight", "no_of_qty_to_manufacture"], as_dict=True) or {}
            # A blank no_of_qty_to_manufacture silently yields a zero weight on every
            # row logged against that drawing, which is the original script's warning.
            check("  %s has a per-piece weight to offer" % r.drawing,
                  flt(d.get("no_of_qty_to_manufacture")) > 0
                  and flt(d.get("total_weight")) > 0, True)

    _summary()


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
