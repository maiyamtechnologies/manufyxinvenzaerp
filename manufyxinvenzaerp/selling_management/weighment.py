"""Weighment Weight on the Delivery Note and the Packing Slip (client, 22 Oct 2026).

Each row may carry what the weighbridge read for it. The header's Total Weighment
Weight is the sum of those rows whenever any row has one; when none does, the total
is whatever was typed into it, so a single weighment of the whole load can still be
recorded without splitting it across rows.
"""

from frappe.utils import flt


def set_total_weighment_weight(doc, method=None):
	rows = [flt(r.get("custom_weighment_weight")) for r in doc.get("items") or []]
	if any(rows):
		doc.custom_total_weighment_weight = flt(sum(rows), 3)
