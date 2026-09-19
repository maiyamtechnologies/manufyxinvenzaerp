"""Sales Invoice hooks for finished goods invoiced by the piece.

sep14 FG plan, package A6. Invoices are in Kg (same UOM as the Sales Order and
the Delivery Note) but the user works in Nos: the Kg follows from the source line's
Kg per Nos, and the Sales Order line / Delivery Note row keep a Billed (Nos) total.

Where a row's Nos and Kg come from (reading R2):
	- invoice from a Sales Order: Kg per Nos = SO line Kg / SO line Nos (the ordered
	  weight);
	- invoice from a Delivery Note: Kg per Nos = that DN row's own Kg / Nos (the
	  actual weight that left the yard);
	- last-piece rule: when the Nos is everything still unbilled on the source, the
	  Kg is the exact unbilled Kg, so no 0.001 Kg crumb is left behind.

Billed figures are always re-summed from submitted Sales Invoice rows rather than
incremented, so a credit note (negative Nos) and a cancel both come out right
without any bookkeeping of their own.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from manufyxinvenzaerp.production_management.fg_stock import is_fg_item

SEC_UOM = "Nos"

SO_ITEM = "Sales Order Item"
DN_ITEM = "Delivery Note Item"

# Sales Invoice Item field that points at each source row.
_SOURCE_LINK = {SO_ITEM: "so_detail", DN_ITEM: "dn_detail"}


# ── Source figures ────────────────────────────────────────────────────────────


def _source_row(doctype, name):
	"""Kg (qty) and Nos of a Sales Order line / Delivery Note row, signed.

	For a Delivery Note row, returns booked against it (return DNs whose dn_detail
	points at it) are netted off, because pieces that came back cannot be billed.
	own_kg / own_nos stay the row's own figures: that is the Kg per Nos the invoice
	uses. A return DN row keeps its negative figures (a credit note is made from it).
	"""
	row = frappe.db.get_value(doctype, name, ["qty", "custom_sec_qty"], as_dict=True)
	if not row:
		return None
	out = frappe._dict(
		own_kg=flt(row.qty), own_nos=flt(row.custom_sec_qty),
		total_kg=flt(row.qty), total_nos=flt(row.custom_sec_qty),
	)
	if doctype == DN_ITEM and out.own_nos > 0:
		returned = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(dni.qty), 0), COALESCE(SUM(dni.custom_sec_qty), 0)
			FROM `tabDelivery Note Item` dni
			JOIN `tabDelivery Note` dn ON dn.name = dni.parent
			WHERE dni.dn_detail = %s AND dn.docstatus = 1 AND dn.is_return = 1
			""",
			name,
		)[0]
		# Return rows are stored negative, so adding them nets the row down.
		out.total_kg += flt(returned[0])
		out.total_nos += flt(returned[1])
	return out


def _billed(doctype, name, exclude_invoice=None):
	"""(Nos, Kg) already billed against a source row by submitted invoices.

	Credit notes carry negative Nos and Kg, so the sum is net of them. Rate
	adjustment (debit note) invoices bill no pieces and are left out.
	"""
	link = _SOURCE_LINK[doctype]
	nos, kg = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(sii.custom_sec_qty), 0), COALESCE(SUM(sii.qty), 0)
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE sii.{link} = %(name)s AND si.docstatus = 1
			AND IFNULL(si.is_debit_note, 0) = 0 AND si.name != %(exclude)s
		""",
		{"name": name, "exclude": exclude_invoice or ""},
	)[0]
	return flt(nos), flt(kg)


def _limit(source, billed_nos, billed_kg, is_return):
	"""(Nos, Kg) this invoice may still take from a source row, as magnitudes.

	- invoice: what is left unbilled (source total - billed);
	- credit note against a normal source: what has been billed so far;
	- credit note made from a return Delivery Note row (source negative): what of
	  that return is not yet credited.
	"""
	if is_return and source.total_nos > 0:
		return flt(billed_nos, 3), flt(billed_kg, 3)
	sign = -1 if is_return else 1
	return (
		flt(sign * (source.total_nos - billed_nos), 3),
		flt(sign * (source.total_kg - billed_kg), 3),
	)


def _kg_for_nos(nos, source, limit_nos, limit_kg):
	"""Kg (magnitude) for |nos| pieces of a source row, applying the last-piece rule."""
	nos = abs(flt(nos))
	if nos and flt(nos) == flt(limit_nos) and limit_kg > 0:
		return flt(limit_kg, 3)
	if not source.own_nos:
		return 0.0
	return flt(nos * abs(source.own_kg / source.own_nos), 3)


class _Ledger:
	"""Source figures for one invoice, with its own earlier rows counted.

	One invoice can hold two rows against the same SO line (e.g. split by cost
	centre). The second row's pending must already include the first, so every
	row "takes" from the ledger as it is processed.
	"""

	def __init__(self, exclude_invoice=None):
		self.exclude = exclude_invoice
		self._sources = {}
		self._taken = {}

	def source(self, doctype, name):
		key = (doctype, name)
		if key not in self._sources:
			self._sources[key] = _source_row(doctype, name)
		return self._sources[key]

	def billed(self, doctype, name):
		key = (doctype, name)
		nos, kg = _billed(doctype, name, self.exclude)
		taken_nos, taken_kg = self._taken.get(key, (0.0, 0.0))
		return nos + taken_nos, kg + taken_kg

	def take(self, doctype, name, nos, kg):
		key = (doctype, name)
		taken_nos, taken_kg = self._taken.get(key, (0.0, 0.0))
		self._taken[key] = (taken_nos + flt(nos), taken_kg + flt(kg))


def _row_sources(row):
	"""[(doctype, name)] the row bills against, DN row first (it decides the Kg)."""
	out = []
	if row.get("dn_detail"):
		out.append((DN_ITEM, row.dn_detail))
	if row.get("so_detail"):
		out.append((SO_ITEM, row.so_detail))
	return out


def _tracked_sources(ledger, row):
	"""Sources that carry Nos. A legacy line with no Nos is not tracked by the piece."""
	return [
		(dt, name) for dt, name in _row_sources(row)
		if (ledger.source(dt, name) or frappe._dict()).get("own_nos")
	]


def _clear_sec(row):
	# Sales Order Item.custom_sec_uom defaults to "Nos" and the mapper copies it by
	# name onto every invoice line; the property setter then makes that line's Kg
	# read-only. Only FG rows tracked by the piece may keep it.
	row.custom_sec_uom = None
	row.custom_sec_qty = 0


def compute_fg_rows(doc, throw=True):
	"""Check and price every FG row of a Sales Invoice by its Nos.

	Input:  doc (Sales Invoice, saved or not); throw -- False collects messages
	        instead of raising (used by the form while the user types).
	Output: {row.name: {"kg", "nos", "error"}} for the FG rows tracked by the piece.
	        Sets row.qty / custom_sec_qty / custom_sec_uom on doc as it goes.

	The Kg side comes from the Delivery Note row when there is one, else from the
	Sales Order line. When the row comes from a DN, the SO line's unbilled Nos is
	checked as well, so billing the same pieces once from the SO and once from the
	DN is refused.
	"""
	is_return = cint(doc.get("is_return"))
	sign = -1 if is_return else 1
	ledger = _Ledger(exclude_invoice=None if doc.is_new() else doc.name)
	results = {}

	def fail(row, msg):
		if throw:
			frappe.throw(msg, title=_("Finished Goods Invoice"))
		results.setdefault(row.name, {})["error"] = msg

	for row in doc.get("items"):
		if not is_fg_item(row.item_code):
			_clear_sec(row)
			continue

		if not _row_sources(row):
			fail(row, _(
				"Row {0}: {1} is a finished-goods item. It can only be invoiced from a "
				"Sales Order or a Delivery Note, so that its Nos are tracked."
			).format(row.idx, frappe.bold(row.item_code)))
			continue

		sources = _tracked_sources(ledger, row)
		if not sources:
			# Order taken before FG lines carried Nos (D13): invoiced by Kg as before.
			_clear_sec(row)
			continue

		row.custom_sec_uom = SEC_UOM
		nos = abs(flt(row.custom_sec_qty))
		results[row.name] = {"nos": sign * nos, "kg": flt(row.qty, 3), "error": None}

		if nos <= 0 or nos != cint(nos):
			fail(row, _(
				"Row {0}: Qty (Nos) of {1} must be a whole number of pieces greater "
				"than 0 (got {2})."
			).format(row.idx, frappe.bold(row.item_code), flt(row.custom_sec_qty)))
			continue

		kg = None
		ok = True
		for dt, name in sources:
			source = ledger.source(dt, name)
			billed_nos, billed_kg = ledger.billed(dt, name)
			limit_nos, limit_kg = _limit(source, billed_nos, billed_kg, is_return)
			if nos > limit_nos:
				what = _("Delivery Note row") if dt == DN_ITEM else _("Sales Order line")
				verb = _("credited") if is_return else _("invoiced")
				fail(row, _(
					"Row {0}: {1} Nos of {2} is more than can still be {3} on its {4} "
					"({5} Nos left)."
				).format(row.idx, cint(nos), frappe.bold(row.item_code), verb, what,
					cint(max(limit_nos, 0))))
				ok = False
				break
			if kg is None:
				# The first source (the DN row when there is one) sets the Kg.
				kg = _kg_for_nos(nos, source, limit_nos, limit_kg)
		if not ok:
			continue

		row.custom_sec_qty = sign * nos
		row.qty = sign * kg
		row.stock_qty = flt(row.qty * flt(row.conversion_factor or 1), row.precision("stock_qty"))
		results[row.name].update({"nos": row.custom_sec_qty, "kg": row.qty})
		for dt, name in sources:
			ledger.take(dt, name, row.custom_sec_qty, row.qty)

	return results


def refresh_totals(doc):
	"""Recompute amounts after row Kg changed, including the GST item columns.

	Our validate runs after ERPNext's and India Compliance's, which already priced
	the rows; a Kg changed here must be priced again or the invoice would save a
	stale amount, taxable value and payment schedule.
	"""
	if not doc.get("items"):
		return
	doc.calculate_taxes_and_totals()
	try:
		from india_compliance.gst_india.overrides.transaction import (
			update_item_gst_details,
			update_taxable_values,
		)
	except ImportError:
		pass
	else:
		update_taxable_values(doc)
		update_item_gst_details(doc)
	if not cint(doc.get("is_return")) and doc.get("payment_schedule"):
		doc.set_payment_schedule()


# ── Hooks ─────────────────────────────────────────────────────────────────────


def _has_fg_line(doc):
	return any(is_fg_item(row.item_code) for row in doc.get("items"))


def validate_sales_invoice(doc, method=None):
	"""Sales Invoice validate hook (registered in hooks.py).

	- Update Stock is refused when any line is an FG item (D23): FG leaves stock
	  only through a Delivery Note, which is where its batch Nos are kept.
	- FG rows: whole Nos, Nos <= pending on the source (Sales Order line or
	  Delivery Note row), Kg recalculated from Nos (last pending Nos = exact pending
	  Kg), and an FG row must come from a Sales Order or a Delivery Note.
	- Non-FG rows lose the Nos UOM the mapper copied onto them.
	"""
	if cint(doc.get("update_stock")) and _has_fg_line(doc):
		frappe.throw(
			_(
				"Update Stock cannot be used on an invoice with finished-goods items. "
				"Deliver them with a Delivery Note (which moves their drawing batch "
				"by Nos) and invoice from the Delivery Note or the Sales Order."
			),
			title=_("Finished Goods Invoice"),
		)

	if cint(doc.get("is_debit_note")):
		# A rate adjustment bills no pieces: leave its rows as typed.
		return

	before = [flt(row.qty, 3) for row in doc.get("items")]
	compute_fg_rows(doc, throw=True)
	if [flt(row.qty, 3) for row in doc.get("items")] != before:
		refresh_totals(doc)


def _update_billed_sec_qty(doc):
	"""Re-sum Billed (Nos) on every SO line and DN row this invoice touches."""
	touched = set()
	for row in doc.get("items"):
		if not row.get("custom_sec_uom"):
			continue
		for dt, name in _row_sources(row):
			touched.add((dt, name))
	for dt, name in touched:
		nos, _kg = _billed(dt, name)
		frappe.db.set_value(dt, name, "custom_billed_sec_qty", flt(nos), update_modified=False)


def on_submit_sales_invoice(doc, method=None):
	"""Sales Invoice on_submit hook (registered in hooks.py).

	Updates custom_billed_sec_qty on the Sales Order line (every invoice) and on the
	Delivery Note row (DN-based invoices). Credit notes carry negative Nos, so they
	reduce it.
	"""
	_update_billed_sec_qty(doc)


def on_cancel_sales_invoice(doc, method=None):
	"""Sales Invoice on_cancel hook (registered in hooks.py).

	The reverse of on_submit_sales_invoice: the invoice is already cancelled in the
	database here, so the same re-sum simply leaves it out.
	"""
	_update_billed_sec_qty(doc)


@frappe.whitelist()
def get_fg_row_kg(doc, row_name):
	"""Kg for one FG row of an unsaved invoice, for the form while Nos is typed.

	Input:  doc (the Sales Invoice as JSON), row_name (the Sales Invoice Item name).
	Output: {"kg", "nos", "error"}; error is a message when the Nos is refused, and
	        kg is then the row's current Kg.

	Runs the same compute_fg_rows as validate, so the form and the server can never
	disagree on the last-piece Kg.
	"""
	if isinstance(doc, str):
		doc = frappe.parse_json(doc)
	doc = frappe.get_doc(doc)
	if not frappe.has_permission("Sales Invoice", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	results = compute_fg_rows(doc, throw=False)
	return results.get(row_name) or {}
