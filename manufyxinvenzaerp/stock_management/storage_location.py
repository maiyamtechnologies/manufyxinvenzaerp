"""Storage Location: where inside a warehouse the stock sits.

Storage Location is the ERPNext Inventory Dimension of that name, so the location every
stock movement names is already written to its Stock Ledger Entry, and a Material
Transfer inside one warehouse that changes only the location is how stock moves between
locations. What this module adds on top:

  * Mandatory where it applies. A warehouse needs a location when its Warehouse Type has
    "Storage Location Applicable" ticked. It is enforced here and not on the Inventory
    Dimension, because it is not wanted in every warehouse (supplier, transit), and the
    dimension's own `reqd` can no longer be changed once stock exists against it.
  * Which locations an item may be put in: the item's own Storage Locations table for
    that warehouse, or, when it lists none, every location of the warehouse.
  * That stock is taken out of a location that holds it -- per batch. The native check
    on the dimension compares item + warehouse + location only, so a batch could leave
    location A-2 while it actually sits in A-1.
  * Filling the location in on entries the app creates itself (Material Issue Plan
    transfers, the final Manufacture, excess returns, the cut-sheet repack), from where
    the batch is now -- not from a stored value, so a reserved batch that was moved to
    another location after it was reserved still transfers from the right one.

Locations are filled in `before_validate` and enforced in `before_submit`: the app
inserts its entries as drafts, so a location it cannot work out leaves a draft the user
completes, rather than an error halfway through a transfer.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.caching import request_cache

# A location needs this much of a batch to be counted as holding it -- below it is a
# rounding residue of earlier movements, not stock.
QTY_EPSILON = 0.001

# The Material Issue Plan field naming the location for each of its receiving warehouses.
MIP_LOCATION_FIELDS = (
	("supplier_warehouse", "supplier_storage_location"),
	("cnc_warehouse", "cnc_storage_location"),
	("excess_return_warehouse", "fg_storage_location"),
	("excess_material_warehouse", "excess_material_storage_location"),
)

# Location fields a plan may be saved without. The Excess Return location is only needed
# on the day something comes back, and the return popup asks for it then -- requiring it
# on every save would block plans that may never return anything.
OPTIONAL_UNTIL_USED = ("excess_material_storage_location",)


# ── Masters ──────────────────────────────────────────────────────────────────────


@request_cache
def location_applicable(warehouse):
	"""Whether stock in `warehouse` must name a Storage Location: the Warehouse's own
	Mandatory Storage Location box is on and the warehouse has at least one location to
	choose from (client, 23 Oct 2026). It used to be the Warehouse Type's flag; patch
	v16.warehouse_mandatory_storage_location copied that onto each warehouse."""
	if not warehouse:
		return False
	return bool(
		frappe.get_cached_value("Warehouse", warehouse, "custom_mandatory_storage_location")
		and warehouse_locations(warehouse)
	)


@request_cache
def warehouse_locations(warehouse):
	return frappe.get_all(
		"Storage Location", filters={"warehouse": warehouse}, pluck="name", order_by="name asc"
	)


def _item_rows(item_code, warehouse):
	return frappe.get_all(
		"Item Storage Location",
		filters={"parenttype": "Item", "parent": item_code, "warehouse": warehouse},
		fields=["storage_location", "is_default"],
		order_by="idx asc",
	)


def validates_item_locations(item_code):
	"""Whether the Item's own Storage Locations table limits where it may go (the Item's
	Validate Storage Location box). Off by default (client, 22 Oct 2026): the per-item
	lists are not in use yet, so every location of the warehouse is offered."""
	return bool(item_code and frappe.get_cached_value("Item", item_code, "custom_validate_storage_location"))


def allowed_locations(item_code, warehouse):
	"""Locations `item_code` may be put in inside `warehouse`. With Validate Storage
	Location on: the ones its Item lists, and nothing else (client, Oct 2026) -- an item
	listing none for a warehouse has no allowed location there. With it off: every
	location of the warehouse."""
	if not validates_item_locations(item_code):
		return warehouse_locations(warehouse)
	return [r.storage_location for r in _item_rows(item_code, warehouse)]


def default_location(item_code, warehouse):
	"""The location an inward row is filled with: the item's default, else the only choice."""
	for row in _item_rows(item_code, warehouse):
		if row.is_default:
			return row.storage_location
	allowed = allowed_locations(item_code, warehouse)
	return allowed[0] if len(allowed) == 1 else None


# ── Stock per location ───────────────────────────────────────────────────────────


def location_stock(item_code, warehouse, batch_no=None):
	"""{location: qty in stock UOM} for an item -- or one batch of it -- in a warehouse.

	Stock with no location is keyed "". A batch received through a Purchase Receipt is
	recorded in a Serial and Batch Bundle and the ledger's own batch_no column is empty
	(see SKILL.md, "Batch quantities do not live in the ledger's batch_no"), so a batch is
	read through the bundle, plus the ledger rows that carry it directly."""
	if not item_code or not warehouse:
		return {}

	if batch_no:
		rows = frappe.db.sql(
			"""
			SELECT IFNULL(sle.storage_location, '') AS location, SUM(sbe.qty) AS qty
			FROM `tabStock Ledger Entry` sle
			JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
			WHERE sle.item_code = %(item)s AND sle.warehouse = %(wh)s AND sle.is_cancelled = 0
				AND sbe.batch_no = %(batch)s
			GROUP BY location
			UNION ALL
			SELECT IFNULL(storage_location, '') AS location, SUM(actual_qty) AS qty
			FROM `tabStock Ledger Entry`
			WHERE item_code = %(item)s AND warehouse = %(wh)s AND is_cancelled = 0
				AND batch_no = %(batch)s
				AND IFNULL(serial_and_batch_bundle, '') = ''
			GROUP BY location
			""",
			{"item": item_code, "wh": warehouse, "batch": batch_no},
			as_dict=True,
		)
	else:
		rows = frappe.db.sql(
			"""
			SELECT IFNULL(storage_location, '') AS location, SUM(actual_qty) AS qty
			FROM `tabStock Ledger Entry`
			WHERE item_code = %s AND warehouse = %s AND is_cancelled = 0
			GROUP BY location
			""",
			(item_code, warehouse),
			as_dict=True,
		)

	stock = defaultdict(float)
	for row in rows:
		stock[row.location] += flt(row.qty)
	return {loc: flt(qty, 6) for loc, qty in stock.items() if flt(qty) > QTY_EPSILON}


def batch_locations(warehouse, batch_nos):
	"""{batch: {location: qty}} for many batches in one warehouse, in one query."""
	batch_nos = sorted({b for b in batch_nos or [] if b})
	if not warehouse or not batch_nos:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT sbe.batch_no, IFNULL(sle.storage_location, '') AS location, SUM(sbe.qty) AS qty
		FROM `tabStock Ledger Entry` sle
		JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
		WHERE sle.warehouse = %(wh)s AND sle.is_cancelled = 0 AND sbe.batch_no IN %(batches)s
		GROUP BY sbe.batch_no, location
		UNION ALL
		SELECT batch_no, IFNULL(storage_location, '') AS location, SUM(actual_qty) AS qty
		FROM `tabStock Ledger Entry`
		WHERE warehouse = %(wh)s AND is_cancelled = 0 AND batch_no IN %(batches)s
			AND IFNULL(serial_and_batch_bundle, '') = ''
		GROUP BY batch_no, location
		""",
		{"wh": warehouse, "batches": tuple(batch_nos)},
		as_dict=True,
	)
	out = defaultdict(lambda: defaultdict(float))
	for row in rows:
		out[row.batch_no][row.location] += flt(row.qty)
	return {
		batch: {loc: flt(qty, 6) for loc, qty in locs.items() if flt(qty) > QTY_EPSILON}
		for batch, locs in out.items()
	}


def main_location(stock):
	"""The named location holding most, from a {location: qty}."""
	named = {loc: qty for loc, qty in (stock or {}).items() if loc}
	return max(named, key=named.get) if named else None


def batch_location(item_code, warehouse, batch_no):
	"""The location holding most of a batch in a warehouse, or None."""
	stock = {loc: qty for loc, qty in location_stock(item_code, warehouse, batch_no).items() if loc}
	return max(stock, key=stock.get) if stock else None


def describe_stock(stock):
	"""'A-1: 120.5, A-2: 30' -- for messages and the picker."""
	if not stock:
		return _("none")
	return ", ".join(f"{loc or _('No location')}: {flt(qty, 3)}" for loc, qty in sorted(stock.items()))


# ── Which rows move stock where ──────────────────────────────────────────────────


class Move:
	"""One side of one row: stock going into or out of a warehouse, and the field naming its location."""

	__slots__ = ("row", "warehouse", "field", "inward", "qty")

	def __init__(self, row, warehouse, field, inward, qty):
		self.row, self.warehouse, self.field, self.inward, self.qty = row, warehouse, field, inward, qty


def _stock_qty(row):
	if row.doctype == "Stock Entry Detail":
		return flt(row.transfer_qty) or flt(row.qty) * (flt(row.conversion_factor) or 1)
	return flt(row.stock_qty) or flt(row.qty) * (flt(row.conversion_factor) or 1)


def moves(doc):
	"""Every location-bearing side of every row of a Stock Entry, Purchase Receipt or Delivery Note."""
	out = []
	is_return = bool(doc.get("is_return"))
	for row in doc.get("items") or []:
		if not row.item_code or not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			continue
		qty = abs(_stock_qty(row))
		if doc.doctype == "Stock Entry":
			if row.s_warehouse:
				out.append(Move(row, row.s_warehouse, "storage_location", False, qty))
			if row.t_warehouse:
				out.append(Move(row, row.t_warehouse, "to_storage_location", True, qty))
		elif doc.doctype == "Purchase Receipt":
			if row.warehouse and flt(row.qty):
				out.append(Move(row, row.warehouse, "storage_location", not is_return, qty))
			if row.get("rejected_warehouse") and flt(row.get("rejected_qty")):
				rejected = abs(flt(row.rejected_qty) * (flt(row.conversion_factor) or 1))
				out.append(Move(row, row.rejected_warehouse, "rejected_storage_location", not is_return, rejected))
		elif doc.doctype == "Delivery Note":
			if row.warehouse:
				out.append(Move(row, row.warehouse, "storage_location", is_return, qty))
	return out


def row_batches(row, qty):
	"""{batch: qty} a row moves: its batch_no, or the entries of its Serial and Batch Bundle."""
	if row.get("batch_no"):
		return {row.batch_no: qty}
	if row.get("serial_and_batch_bundle"):
		batches = defaultdict(float)
		for entry in frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": row.serial_and_batch_bundle},
			fields=["batch_no", "qty"],
		):
			if entry.batch_no:
				batches[entry.batch_no] += abs(flt(entry.qty))
		return dict(batches)
	return {}


# ── Filling locations in (before_validate) ───────────────────────────────────────


def fill_locations(doc, method=None):
	"""Fill in every location that can be worked out; split a row whose batch is spread
	over several locations. Never throws: what is left blank is reported on submit."""
	if doc.docstatus != 0:
		return

	mip = _mip_locations(doc)
	split_rows = []
	for move in moves(doc):
		row = move.row
		if row.get(move.field) or not location_applicable(move.warehouse):
			continue
		if move.inward:
			location = (
				_repack_source_location(doc, move)
				or mip.get(move.warehouse)
				or default_location(row.item_code, move.warehouse)
			)
			if location:
				row.set(move.field, location)
			continue

		batches = row_batches(row, move.qty)
		if len(batches) > 1:
			# A bundle naming several batches: only fill when one location holds them all.
			holders = None
			for batch, need in batches.items():
				stock = location_stock(row.item_code, move.warehouse, batch)
				covering = {loc for loc, qty in stock.items() if loc and qty + QTY_EPSILON >= need}
				holders = covering if holders is None else holders & covering
			if holders and len(holders) == 1:
				row.set(move.field, holders.pop())
			continue

		batch = next(iter(batches), None)
		stock = {loc: qty for loc, qty in location_stock(row.item_code, move.warehouse, batch).items() if loc}
		if not stock:
			continue
		if len(stock) == 1:
			row.set(move.field, next(iter(stock)))
			continue
		covering = [loc for loc, qty in stock.items() if qty + QTY_EPSILON >= move.qty]
		if len(covering) == 1:
			row.set(move.field, covering[0])
		elif not covering and doc.doctype == "Stock Entry" and batch and sum(stock.values()) + QTY_EPSILON >= move.qty:
			split_rows.append((row, move, stock))
		# Several locations each holding enough: a choice for the user, not for us.

	for row, move, stock in split_rows:
		_split_row_by_location(doc, row, move, stock)


def _repack_source_location(doc, move):
	"""A Repack back into the warehouse it took from (the cut-sheet remnant) keeps the
	location the consumed batch came from."""
	if doc.doctype != "Stock Entry":
		return None
	# ERPNext sets `purpose` from the entry type during validate, after this runs.
	purpose = doc.get("purpose") or frappe.get_cached_value("Stock Entry Type", doc.stock_entry_type, "purpose")
	if purpose != "Repack":
		return None
	for row in doc.items:
		if row.s_warehouse == move.warehouse and row.get("storage_location"):
			return row.storage_location
	return None


def _system_placed(doc, move, location):
	"""Inward rows whose location the system chose, exempt from the item's own list.

	A Material Issue Plan entry goes where the plan (or its return popup) says -- its WIP,
	CNC, finished-goods or excess-return location, picked deliberately for the job -- and a
	same-warehouse Repack (cut-sheet remnant) goes back where its batch came from. Holding
	those to each item's list would stop a running job's transfers until every raw
	material listed the WIP location; the item list governs what people key in."""
	if doc.doctype != "Stock Entry":
		return False
	if doc.get("custom_mip_ref"):
		return frappe.get_cached_value("Storage Location", location, "warehouse") == move.warehouse
	return location == _repack_source_location(doc, move)


def _mip_locations(doc):
	"""{warehouse: location} the Material Issue Plan behind this entry names for its warehouses."""
	mip_name = doc.get("custom_mip_ref") if doc.doctype == "Stock Entry" else None
	if not mip_name or not frappe.db.exists("Material Issue Plan", mip_name):
		return {}
	values = frappe.db.get_value(
		"Material Issue Plan",
		mip_name,
		[f for pair in MIP_LOCATION_FIELDS for f in pair],
		as_dict=True,
	) or {}
	return {
		values[wh_field]: values[loc_field]
		for wh_field, loc_field in MIP_LOCATION_FIELDS
		if values.get(wh_field) and values.get(loc_field)
	}


# Row fields measured in the row's quantity, scaled with it when a row is split.
_SCALED_FIELDS = ("qty", "transfer_qty", "custom_sec_qty", "drawing_planned_weight")


def _split_row_by_location(doc, row, move, stock):
	"""Split one Stock Entry row into one row per location holding its batch, largest
	first. Each row keeps everything else the original carried (references, drawing,
	DUNO), so a reservation released per batch releases exactly what one row would."""
	remaining = move.qty
	chunks = []
	for location, held in sorted(stock.items(), key=lambda kv: -kv[1]):
		if remaining <= QTY_EPSILON:
			break
		take = min(held, remaining)
		chunks.append((location, take))
		remaining -= take

	if len(chunks) < 2:
		if chunks:
			row.set(move.field, chunks[0][0])
		return

	values = row.as_dict(no_default_fields=True)
	position = doc.items.index(row)
	new_rows = []
	for i, (location, take) in enumerate(chunks):
		ratio = take / move.qty
		changes = {
			field: flt(flt(values.get(field)) * ratio, 6)
			for field in _SCALED_FIELDS
			if values.get(field) is not None
		}
		changes[move.field] = location
		if i == 0:
			row.update(changes)
		else:
			copy = {k: v for k, v in values.items() if k not in ("name", "idx")}
			copy.update(changes)
			new_rows.append(doc.append("items", copy))

	# Put the new rows right after the one they came from.
	items = [r for r in doc.items if r not in new_rows]
	items[position + 1 : position + 1] = new_rows
	doc.items = items
	for idx, item in enumerate(doc.items, 1):
		item.idx = idx


# ── Enforcing (before_submit) ────────────────────────────────────────────────────


def check_locations(doc, method=None):
	"""On save: every location that IS filled in must fit -- allowed for the item going
	in, holding the stock going out (client, Oct 2026: "on save need to validate stock").

	A blank one is let through here and refused on submit (validate_locations): the app
	saves its own drafts (Material Issue Plan transfers, Final entries) before anyone
	has picked a location, and those must stay saveable."""
	if doc.docstatus == 0:
		validate_locations(doc, require=False)


def validate_locations(doc, method=None, require=True):
	"""Refuse to submit unless every movement in a location-managed warehouse names a
	location it may use -- and, going out, one that holds the stock."""
	demand = defaultdict(float)
	for move in moves(doc):
		if not location_applicable(move.warehouse):
			continue
		row, location = move.row, move.row.get(move.field)
		label = frappe.get_meta(row.doctype).get_label(move.field)
		if not location:
			if not require:
				continue
			frappe.throw(
				_("Row #{0}: {1} is mandatory for {2}, because its Warehouse Type needs a Storage Location.").format(
					row.idx, frappe.bold(label), frappe.bold(move.warehouse)
				),
				title=_("Storage Location Missing"),
			)
		if move.inward:
			if _system_placed(doc, move, location):
				continue
			allowed = allowed_locations(row.item_code, move.warehouse)
			if location not in allowed:
				frappe.throw(
					_("Row #{0}: Storage Location {1} cannot hold {2} in {3}. Allowed: {4}.").format(
						row.idx,
						frappe.bold(location),
						frappe.bold(row.item_code),
						frappe.bold(move.warehouse),
						", ".join(allowed)
						or _("none -- add {0}'s locations to the Item's Storage Locations table").format(
							move.warehouse
						),
					),
					title=_("Storage Location Not Allowed"),
				)
			continue

		if frappe.get_cached_value("Storage Location", location, "warehouse") != move.warehouse:
			frappe.throw(
				_("Row #{0}: Storage Location {1} is not in {2}.").format(
					row.idx, frappe.bold(location), frappe.bold(move.warehouse)
				),
				title=_("Wrong Storage Location"),
			)
		batches = row_batches(row, move.qty) or {None: move.qty}
		for batch, qty in batches.items():
			demand[(row.item_code, move.warehouse, location, batch)] += qty

	for (item_code, warehouse, location, batch), need in demand.items():
		stock = location_stock(item_code, warehouse, batch)
		if flt(stock.get(location)) + QTY_EPSILON < need:
			what = _("Batch {0} of {1}").format(frappe.bold(batch), item_code) if batch else frappe.bold(item_code)
			frappe.throw(
				_("{0}: {1} needed from Storage Location {2} in {3}, but it holds {4}. Where it is: {5}.").format(
					what,
					flt(need, 3),
					frappe.bold(location),
					frappe.bold(warehouse),
					flt(stock.get(location), 3),
					describe_stock(stock),
				),
				title=_("Not in this Storage Location"),
			)


# ── Material Planning: show where a reserved batch is ────────────────────────────

_MP_TABLES = (("material_mapping", "batch"), ("available_raw_materials", "batch_no"))


def stamp_reserved_locations(mp):
	"""Material Planning validate: each batch row -- reserved or offered -- shows the
	location the batch is in now, so the store knows where to pick it. A row whose batch
	has left the planning warehouse keeps what it showed."""
	warehouse = mp.get("for_warehouse")
	if not warehouse or not location_applicable(warehouse):
		return
	rows = [
		(row, row.get(batch_field))
		for table, batch_field in _MP_TABLES
		for row in mp.get(table) or []
		if row.get(batch_field) and row.meta.has_field("storage_location")
	]
	stock = batch_locations(warehouse, [batch for _row, batch in rows])
	for row, batch in rows:
		location = main_location(stock.get(batch))
		if location:
			row.storage_location = location


def refresh_reserved_locations(doc, method=None):
	"""Stock Entry on_submit / on_cancel: a batch moved between locations shows its new
	location on every Material Planning row naming it."""
	batches = {
		(row.item_code, row.s_warehouse, row.batch_no)
		for row in doc.items
		if row.batch_no and row.s_warehouse and row.s_warehouse == row.t_warehouse
		and location_applicable(row.s_warehouse)
	}
	for item_code, warehouse, batch in batches:
		location = batch_location(item_code, warehouse, batch)
		if not location:
			continue
		for child_dt, batch_field in (
			("Material Planning Material Mapping", "batch"),
			("Material Planning Available Raw Material", "batch_no"),
		):
			frappe.db.sql(
				f"""
				UPDATE `tab{child_dt}` row JOIN `tabMaterial Planning` mp ON mp.name = row.parent
				SET row.storage_location = %s
				WHERE row.{batch_field} = %s AND mp.for_warehouse = %s
				""",
				(location, batch, warehouse),
			)


# ── Pickers ──────────────────────────────────────────────────────────────────────


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def inward_location_query(doctype, txt, searchfield, start, page_len, filters):
	"""Locations an item may be put in inside a warehouse."""
	item_code, warehouse = filters.get("item_code"), filters.get("warehouse")
	if not warehouse:
		return []
	allowed = allowed_locations(item_code, warehouse) if item_code else warehouse_locations(warehouse)
	default = default_location(item_code, warehouse) if item_code else None
	txt = (txt or "").lower()
	rows = [
		(loc, _("Default") if loc == default else "")
		for loc in allowed
		if txt in loc.lower()
	]
	return rows[cint_start(start) : cint_start(start) + cint_start(page_len, 20)]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def outward_location_query(doctype, txt, searchfield, start, page_len, filters):
	"""Locations holding the item -- or the row's batch -- in a warehouse, with the qty there."""
	item_code, warehouse = filters.get("item_code"), filters.get("warehouse")
	if not (item_code and warehouse):
		return []
	stock = location_stock(item_code, warehouse, filters.get("batch_no") or None)
	txt = (txt or "").lower()
	rows = [
		(loc, _("In stock: {0}").format(flt(qty, 3)))
		for loc, qty in sorted(stock.items(), key=lambda kv: -kv[1])
		if loc and txt in loc.lower()
	]
	return rows[cint_start(start) : cint_start(start) + cint_start(page_len, 20)]


def cint_start(value, default=0):
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


@frappe.whitelist()
def get_default_location(item_code, warehouse):
	"""What an inward row is filled with, for the form; None when the warehouse needs none."""
	if not location_applicable(warehouse):
		return None
	return default_location(item_code, warehouse)


@frappe.whitelist()
def get_location_settings(warehouses):
	"""{warehouse: applicable?} for the form, so it marks the location fields mandatory."""
	warehouses = frappe.parse_json(warehouses) if isinstance(warehouses, str) else warehouses
	return {wh: location_applicable(wh) for wh in set(warehouses or []) if wh}


# ── Material Issue Plan: the location for each warehouse it sends stock into ─────


def validate_mip_locations(mip):
	"""Material Issue Plan validate: a warehouse that needs a Storage Location has one.

	A new plan is created by the system from the Production Plan, before anyone has
	looked at it, so it is only filled in -- when the warehouse has exactly one location
	-- and never refused. From the next save on, a missing one is an error, and every
	transfer into the warehouse checks it again (require_mip_location)."""
	for wh_field, loc_field in MIP_LOCATION_FIELDS:
		warehouse, location = mip.get(wh_field), mip.get(loc_field)
		if not warehouse or not location_applicable(warehouse):
			if location:
				mip.set(loc_field, None)
			continue
		if location:
			if frappe.get_cached_value("Storage Location", location, "warehouse") != warehouse:
				frappe.throw(
					_("{0}: Storage Location {1} is not in {2}.").format(
						mip.meta.get_label(loc_field), frappe.bold(location), frappe.bold(warehouse)
					)
				)
			continue
		choices = warehouse_locations(warehouse)
		if len(choices) == 1:
			mip.set(loc_field, choices[0])
		elif loc_field in OPTIONAL_UNTIL_USED:
			# Asked for when it is used: the return popup refuses to receive without one.
			continue
		elif not mip.is_new():
			frappe.throw(
				_("{0} is mandatory: {1} needs a Storage Location for everything put into it.").format(
					frappe.bold(mip.meta.get_label(loc_field)), frappe.bold(warehouse)
				),
				title=_("Storage Location Missing"),
			)


def require_mip_location(mip, warehouse):
	"""Before a Material Issue Plan creates an entry into `warehouse`: refuse when the
	warehouse needs a Storage Location and the plan names none for it."""
	if not warehouse or not location_applicable(warehouse):
		return
	for wh_field, loc_field in MIP_LOCATION_FIELDS:
		if mip.get(wh_field) == warehouse:
			if mip.get(loc_field):
				return
			frappe.throw(
				_("Set {0} on {1} first: {2} needs a Storage Location for everything put into it.").format(
					frappe.bold(mip.meta.get_label(loc_field)), mip.name, frappe.bold(warehouse)
				),
				title=_("Storage Location Missing"),
			)


def validate_item_locations(doc, method=None):
	"""Item validate: each Storage Locations row names a location of its own warehouse,
	and a warehouse has at most one default."""
	defaults = defaultdict(list)
	for row in doc.get("custom_storage_locations") or []:
		if row.storage_location and row.warehouse:
			if frappe.get_cached_value("Storage Location", row.storage_location, "warehouse") != row.warehouse:
				frappe.throw(
					_("Storage Locations row #{0}: {1} is not in {2}.").format(
						row.idx, frappe.bold(row.storage_location), frappe.bold(row.warehouse)
					)
				)
		if row.is_default:
			defaults[row.warehouse].append(row.idx)
	for warehouse, rows in defaults.items():
		if len(rows) > 1:
			frappe.throw(
				_("Storage Locations: only one default per warehouse -- rows {0} are all default for {1}.").format(
					", ".join(map(str, rows)), frappe.bold(warehouse)
				)
			)
