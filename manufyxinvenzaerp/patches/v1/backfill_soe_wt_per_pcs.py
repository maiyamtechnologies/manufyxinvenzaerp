"""Fill Wt per Pcs (Kg) on Consumption Log rows written before the field existed.

The per-piece weight was always computed when a row was entered and then thrown
away, leaving the log showing a row total with nothing to read it against: 1,790.089
Kg for 4 Nos, beside a Transferred (Kg) of 6,846.680 on the Drawing Details row,
looks like a mismatch until you know one is this consumption and the other is the
whole drawing. The field now keeps it, but rows already logged would read 0 next to
a populated Total Weight, which is worse than the gap it was added to close.

Derived from the row's own two numbers -- Total Weight / Qty (Nos) -- rather than
re-read from the Drawing. The Drawing's weight can have been revised since the
consumption was logged (drawing_utils._cascade_customer_weight), and this field
must describe the row as it was entered, not re-price it against today's figure.
Rows with no quantity are left at zero; there is nothing to divide by and nothing
they could honestly claim.

Read-only and descriptive: it feeds no total. Total Consumed (Kg) sums weight_kg,
which this patch does not touch, so submitted entries are filled too without moving
any weight the ledger depends on.
"""

import frappe


def execute():
    if not frappe.db.has_column("SOE Consumption Log", "wt_per_pcs_kg"):
        return

    frappe.db.sql(
        """
        UPDATE `tabSOE Consumption Log`
        SET wt_per_pcs_kg = ROUND(weight_kg / qty_nos, 3)
        WHERE COALESCE(qty_nos, 0) > 0
          AND COALESCE(weight_kg, 0) != 0
          AND COALESCE(wt_per_pcs_kg, 0) = 0
        """
    )
