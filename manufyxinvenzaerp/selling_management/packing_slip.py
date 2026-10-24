"""Packing Slip from a Delivery Note in pieces and weight (client, Oct 2026).

A finished-goods Delivery Note row is Kg (its qty) and Nos (custom_sec_qty). The
packing slip is counted in pieces: each row's Qty is the Nos, its Net Weight the Kg
of one piece, so ERPNext's own header Net Weight (Qty x Net Weight, summed) comes
out at the Delivery Note's Kg.

ERPNext ties a packing slip to its Delivery Note through `packed_qty`: the slip adds
its Qty onto the note's row and the note refuses to submit unless packed_qty equals
the row's qty -- in Kg. Pieces would never equal kilos, so each slip row also
carries `custom_dn_qty`, the same quantity in the note's own unit, and that is what
is added up instead. Rows without a piece count (no Nos on the note) pack as
before: Qty is the note's qty and custom_dn_qty equals it.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt

from erpnext.stock.doctype.delivery_note.delivery_note import make_packing_slip as _erpnext_make_packing_slip
from erpnext.stock.doctype.packing_slip.packing_slip import PackingSlip as ERPNextPackingSlip

from manufyxinvenzaerp.selling_management.weighment import set_total_weighment_weight

_EPSILON = 0.001


def _dn_rows(names):
	if not names:
		return {}
	return {
		r.name: r
		for r in frappe.get_all(
			"Delivery Note Item",
			filters={"name": ["in", list(names)]},
			fields=["name", "qty", "packed_qty", "custom_sec_qty", "custom_sec_uom"],
		)
	}


def _per_piece(dn_row):
	"""Kg of one piece on this note row, or None when the row has no piece count."""
	if dn_row and flt(dn_row.custom_sec_qty) > 0 and flt(dn_row.qty) > 0:
		return flt(dn_row.qty) / flt(dn_row.custom_sec_qty)
	return None


def apply_delivery_note_quantities(doc):
	"""Fill each row from its Delivery Note row: Qty in Nos, Net Weight per piece, and
	custom_dn_qty -- the Kg this row packs, which is what the note counts.

	A row packing everything still open on its note row takes exactly the Kg left, so
	the last slip lands the note's packed_qty on its qty to the gram despite rounding."""
	dn_rows = _dn_rows({r.dn_detail for r in doc.items if r.get("dn_detail")})
	for row in doc.items:
		dn_row = dn_rows.get(row.get("dn_detail"))
		per = _per_piece(dn_row)
		if per is None:
			row.custom_dn_qty = flt(row.qty, 3)
			continue
		remaining_kg = flt(flt(dn_row.qty) - flt(dn_row.packed_qty), 3)
		row.stock_uom = dn_row.custom_sec_uom or "Nos"
		row.net_weight = flt(per, 3)
		row.weight_uom = "Kg"
		if abs(flt(row.qty) * per - remaining_kg) < _EPSILON * max(per, 1):
			row.custom_dn_qty = remaining_kg
		else:
			row.custom_dn_qty = flt(flt(row.qty) * per, 3)


@frappe.whitelist()
def make_packing_slip(source_name, target_doc=None):
	"""Override of erpnext.stock.doctype.delivery_note.delivery_note.make_packing_slip:
	the same rows, counted in pieces."""
	doc = _erpnext_make_packing_slip(source_name, target_doc)
	dn_rows = _dn_rows({r.dn_detail for r in doc.items if r.get("dn_detail")})
	for row in doc.items:
		per = _per_piece(dn_rows.get(row.get("dn_detail")))
		if per is not None:
			# ERPNext mapped the Kg still to pack; the pieces are that Kg over one piece.
			row.qty = flt(flt(row.qty) / per, 3)
	apply_delivery_note_quantities(doc)
	doc.run_method("calculate_net_total_pkg")
	return doc


class PackingSlip(ERPNextPackingSlip):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# packed_qty on the note is counted in the note's own unit (Kg), not in pieces.
		for updater in self.status_updater:
			updater["source_field"] = "custom_dn_qty"

	def validate(self):
		apply_delivery_note_quantities(self)
		set_total_weighment_weight(self)
		super().validate()

	def validate_items(self):
		"""ERPNext's check, made on custom_dn_qty: what this slip packs, in the note's
		unit, must fit in what the note row still has unpacked."""
		for item in self.items:
			if flt(item.qty) <= 0:
				frappe.throw(_("Row {0}: Qty must be greater than 0.").format(item.idx))
			if not item.dn_detail and not item.pi_detail:
				frappe.throw(
					_("Row {0}: Either Delivery Note Item or Packed Item reference is mandatory.").format(item.idx)
				)
			doctype = "Delivery Note Item" if item.dn_detail else "Packed Item"
			table = frappe.qb.DocType(doctype)
			remaining = frappe.db.get_value(
				doctype,
				{"name": item.dn_detail or item.pi_detail, "docstatus": 0},
				Sum(table.qty - table.packed_qty),
			)
			if remaining is None:
				frappe.throw(
					_("Row {0}: Please provide a valid Delivery Note Item or Packed Item reference.").format(item.idx)
				)
			if flt(remaining, 3) <= 0:
				frappe.throw(
					_("Row {0}: Packing Slip is already created for Item {1}.").format(
						item.idx, frappe.bold(item.item_code)
					)
				)
			if flt(item.custom_dn_qty, 3) > flt(remaining, 3) + _EPSILON:
				frappe.throw(
					_("Row {0}: {1} Kg cannot be packed for Item {2}; only {3} Kg is left on the Delivery Note.").format(
						item.idx, flt(item.custom_dn_qty, 3), frappe.bold(item.item_code), flt(remaining, 3)
					)
				)
