import frappe
import json
from frappe import _
from frappe.utils import flt
from collections import defaultdict
from frappe.query_builder.functions import IfNull, Sum
from erpnext.stock.get_item_details import get_conversion_factor
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from frappe.model.naming import make_autoname
from frappe.utils import (
	add_days,
	ceil,
	cint,
	comma_and,
	flt,
	get_link_to_form,
	getdate,
	now_datetime,
	nowdate,
)

def get_sbb_available_qty(item_code, warehouse, dimensions, location=None):
	"""
	Fetch available qty per batch for an item in a warehouse, optionally filtered
	by location.

	NOTE (Phase 1 HP-05 / Report 7 SS4): this filters Stock Ledger Entry's
	`storage_location` field -- confirmed live via `DESCRIBE tabStock Ledger
	Entry` to be the only location-shaped column that actually exists on SLE,
	linked to the "Storage Location" doctype (the real, widely-wired ERPNext
	Inventory Dimension -- 32 Link fields across the app). Material Planning's
	own `store_location` field (the argument's usual caller) links to a
	*different* doctype, "Store Location", which has zero records and zero
	Material Planning documents that have ever set it in this site's real
	data -- i.e. this location-filtering feature has never actually been
	exercised in practice. Before this fix, passing a location value here
	produced a hard `OperationalError: Unknown column
	'tabStock Ledger Entry.store_location'` (confirmed live), since that
	column has never existed -- this was silently masked only because the
	feature has never been used. This fix stops the crash by querying the
	column that actually exists; it does NOT resolve the deeper product
	question of whether Material Planning's `store_location` field should
	instead link to "Storage Location" so this filter is ever meaningfully
	populated -- that needs a business decision, not a code fix.

	Flow when location is given:
	  SLE (item + warehouse + storage_location) → SBB → SBE → aggregate by batch_no
	Flow without location:
	  SBB (item + warehouse) → SBE → aggregate by batch_no

	Returns (total_qty, matched_batches) where each matched_batch includes
	batch_no, qty (Kg), custom_sec_qty (NOS), custom_sec_uom.
	Only batches whose dimensions exactly match the required dimensions are returned.

	Client change request Phase 6.2: a batch whose item requires inspection
	(Item.custom_inspection_required) and whose source Purchase Receipt hasn't
	completed inspection yet is excluded from matched_batches entirely -- not
	offered as an Exact Match candidate at all, rather than only failing later
	at actual reservation time (reserve_exact_match_batches carries the same
	gate, via material_planning._get_batch_inspection_block_reason, imported
	locally here to avoid a circular import -- material_planning.py already
	imports from this module the same way, function-local, for this reason).
	"""
	from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
		_get_batch_inspection_block_reason,
	)

	total_qty = 0
	matched_batches = []

	if location:
		# Filter SLEs by location → collect their SBB names
		sle_filters = {
			"item_code": item_code,
			"warehouse": warehouse,
			"is_cancelled": 0,
			"storage_location": location,
			"serial_and_batch_bundle": ("is", "set"),
		}
		sle_list = frappe.get_all(
			"Stock Ledger Entry",
			filters=sle_filters,
			fields=["serial_and_batch_bundle"],
		)
		if not sle_list:
			return 0, []
		sbb_names = list({s.serial_and_batch_bundle for s in sle_list if s.serial_and_batch_bundle})
	else:
		sbb_list = frappe.get_all(
			"Serial and Batch Bundle",
			filters={"item_code": item_code, "warehouse": warehouse, "docstatus": 1},
			fields=["name"],
		)
		if not sbb_list:
			return 0, []
		sbb_names = [d.name for d in sbb_list]

	entries = frappe.get_all(
		"Serial and Batch Entry",
		filters={"parent": ["in", sbb_names]},
		fields=["parent", "batch_no", "qty"],
	)
	if not entries:
		return 0, []

	batch_nos = list({e.batch_no for e in entries if e.batch_no})

	batch_map = {}
	if batch_nos:
		batch_data = frappe.get_all(
			"Batch",
			filters={"name": ["in", batch_nos]},
			fields=["name", "custom_length", "custom_thickness", "custom_width",
			        "custom_sec_qty", "custom_sec_uom"],
		)
		batch_map = {b.name: b for b in batch_data}

	# Net qty per batch across all SBB entries (outgoing SBEs have negative qty)
	batch_qty_map = defaultdict(float)
	for row in entries:
		if row.batch_no:
			batch_qty_map[row.batch_no] += flt(row.qty)

	for batch_no, qty in batch_qty_map.items():
		if qty <= 0:
			continue
		batch = batch_map.get(batch_no)
		if not batch:
			continue
		if _get_batch_inspection_block_reason(batch_no):
			continue

		if (
			flt(batch.custom_length) == flt(dimensions.get("custom_length"))
			and flt(batch.custom_thickness) == flt(dimensions.get("custom_thickness"))
			and flt(batch.custom_width) == flt(dimensions.get("custom_width"))
		):
			total_qty += qty
			matched_batches.append({
				"batch_no": batch_no,
				"qty": qty,
				"custom_sec_qty": flt(batch.custom_sec_qty),
				"custom_sec_uom": batch.custom_sec_uom,
			})

	return total_qty, matched_batches


def get_sbb_batches_bulk(item_codes, warehouse, location=None):
	"""Batched variant of get_sbb_available_qty -- fetches every batch-level
	stock entry for a *set* of items in one warehouse (optionally filtered by
	Store Location) via 3 queries total, instead of 3 queries per item_code
	(Report 4 Finding D-02). Unlike get_sbb_available_qty, this does NOT
	filter by dimensions -- callers apply the same per-row dimension match
	get_sbb_available_qty performs itself, via match_batches_by_dimension()
	below, against the returned per-item batch list.

	Returns {item_code: [{batch_no, qty, custom_length, custom_thickness,
	custom_width, custom_sec_qty, custom_sec_uom}, ...]}. Only batches with
	positive net qty and an existing Batch record are included, mirroring
	get_sbb_available_qty's own `if qty <= 0: continue` / `if not batch:
	continue` guards.
	"""
	item_codes = list({c for c in item_codes if c})
	if not item_codes:
		return {}

	ph = ", ".join(["%s"] * len(item_codes))
	sbb_to_item = {}

	if location:
		# See get_sbb_available_qty's docstring above for why this queries
		# `storage_location` and not `store_location` (Phase 1 HP-05).
		sle_list = frappe.db.sql(
			f"""
			SELECT item_code, serial_and_batch_bundle
			FROM `tabStock Ledger Entry`
			WHERE item_code IN ({ph}) AND warehouse = %s AND is_cancelled = 0
			  AND storage_location = %s AND serial_and_batch_bundle IS NOT NULL
			  AND serial_and_batch_bundle != ''
			""",
			[*item_codes, warehouse, location],
			as_dict=True,
		)
		for s in sle_list:
			if s.serial_and_batch_bundle:
				sbb_to_item[s.serial_and_batch_bundle] = s.item_code
	else:
		sbb_list = frappe.db.sql(
			f"""
			SELECT name, item_code
			FROM `tabSerial and Batch Bundle`
			WHERE item_code IN ({ph}) AND warehouse = %s AND docstatus = 1
			""",
			[*item_codes, warehouse],
			as_dict=True,
		)
		for s in sbb_list:
			sbb_to_item[s.name] = s.item_code

	if not sbb_to_item:
		return {}

	sbb_names = list(sbb_to_item.keys())
	ph_sbb = ", ".join(["%s"] * len(sbb_names))
	entries = frappe.db.sql(
		f"""
		SELECT parent, batch_no, qty
		FROM `tabSerial and Batch Entry`
		WHERE parent IN ({ph_sbb})
		""",
		sbb_names,
		as_dict=True,
	)
	if not entries:
		return {}

	batch_nos = list({e.batch_no for e in entries if e.batch_no})
	batch_map = {}
	if batch_nos:
		ph_batch = ", ".join(["%s"] * len(batch_nos))
		batch_data = frappe.db.sql(
			f"""
			SELECT name, custom_length, custom_thickness, custom_width,
			       custom_sec_qty, custom_sec_uom
			FROM `tabBatch`
			WHERE name IN ({ph_batch})
			""",
			batch_nos,
			as_dict=True,
		)
		batch_map = {b.name: b for b in batch_data}

	# Net qty per (item_code, batch_no) across all SBB entries for that item
	# (outgoing SBEs have negative qty) -- same aggregation get_sbb_available_qty
	# performs per-item, just grouped across every requested item at once.
	batch_qty_map = defaultdict(float)
	for row in entries:
		if not row.batch_no:
			continue
		item_code = sbb_to_item.get(row.parent)
		if not item_code:
			continue
		batch_qty_map[(item_code, row.batch_no)] += flt(row.qty)

	result = defaultdict(list)
	for (item_code, batch_no), qty in batch_qty_map.items():
		if qty <= 0:
			continue
		batch = batch_map.get(batch_no)
		if not batch:
			continue
		result[item_code].append({
			"batch_no": batch_no,
			"qty": qty,
			"custom_length": flt(batch.custom_length),
			"custom_thickness": flt(batch.custom_thickness),
			"custom_width": flt(batch.custom_width),
			"custom_sec_qty": flt(batch.custom_sec_qty),
			"custom_sec_uom": batch.custom_sec_uom,
		})

	return dict(result)


def match_batches_by_dimension(batches, dimensions):
	"""Filter a get_sbb_batches_bulk()-style batch list down to only the ones
	whose recorded dimensions exactly match `dimensions` -- the same
	dimension-equality check get_sbb_available_qty performs itself. Returns
	(total_qty, matched_batches) in the same shape get_sbb_available_qty
	returns, so this is a drop-in per-row replacement once the bulk fetch has
	already happened."""
	matched = [
		b for b in batches
		if flt(b["custom_length"]) == flt(dimensions.get("custom_length"))
		and flt(b["custom_thickness"]) == flt(dimensions.get("custom_thickness"))
		and flt(b["custom_width"]) == flt(dimensions.get("custom_width"))
	]
	total_qty = sum(flt(b["qty"]) for b in matched)
	return total_qty, matched


@frappe.whitelist()
def get_items_for_material_requests(doc, warehouses=None, get_parent_warehouse_data=None):
	if isinstance(doc, str):
		doc = frappe._dict(json.loads(doc))

	if warehouses:
		warehouses = list(set(get_warehouse_list(warehouses)))

		if (
			doc.get("for_warehouse")
			and not get_parent_warehouse_data
			and doc.get("for_warehouse") in warehouses
		):
			warehouses.remove(doc.get("for_warehouse"))

	doc["mr_items"] = []

	po_items = doc.get("po_items") if doc.get("po_items") else doc.get("items")

	if not po_items or not [row.get("item_code") for row in po_items if row.get("item_code")]:
		frappe.throw(_("Items to Manufacture are required"))

	company = doc.get("company")
	ignore_existing_ordered_qty = doc.get("ignore_existing_ordered_qty")
	include_safety_stock = doc.get("include_safety_stock")

	# so_item_details keyed by (item_code, length, thickness, width) to handle same item at different dims
	so_item_details = frappe._dict()

	# =========================
	# STEP 1: BUILD ITEMS
	# =========================
	for data in po_items:
		planned_qty = data.get("required_qty") or data.get("planned_qty")

		item_details = {}

		if data.get("bom") or data.get("bom_no"):
			bom_no = data.get("bom") or data.get("bom_no")

			item_details = get_exploded_items(
				{},
				company,
				bom_no,
				1,
				planned_qty=planned_qty,
				doc=doc,
			)
			# Raw material dimensions come from the BOM explosion items themselves.
			# The po_item dimension is for the finished good and must NOT override
			# individual raw material dimensions — doing so collapses all structural
			# entries with different lengths into a single merged row.

		elif data.get("item_code"):
			item_master = frappe.get_doc("Item", data["item_code"]).as_dict()

			dim_key = (
				item_master.name,
				flt(data.get("custom_length")),
				flt(data.get("custom_thickness")),
				flt(data.get("custom_width")),
			)
			item_details[dim_key] = frappe._dict({
				"item_name": item_master.item_name,
				"qty": planned_qty or 1,
				"item_code": item_master.name,
				"description": item_master.description,
				"stock_uom": item_master.stock_uom,
				"safety_stock": item_master.safety_stock,
				"custom_thickness": data.get("custom_thickness"),
				"custom_length": data.get("custom_length"),
				"custom_width": data.get("custom_width"),
				"custom_parent_item_group": frappe.db.get_value(
					"Item", item_master.name, "custom_parent_item_group"
				),
				"custom_unit_weight": frappe.db.get_value(
					"Item", item_master.name, "custom_unit_weight"
				),
			})

		# Merge by the item's actual dimensions — two BOM items with the same
		# item_code and identical dimensions from different po_items are combined;
		# same item at different dimensions keeps a separate entry.
		for _sql_key, details in item_details.items():
			final_key = (
				details.item_code,
				flt(details.custom_length),
				flt(details.custom_thickness),
				flt(details.custom_width),
			)
			so_item_details.setdefault(None, frappe._dict())

			if final_key in so_item_details[None]:
				so_item_details[None][final_key]["qty"] += flt(details.qty)
			else:
				so_item_details[None][final_key] = details

	mr_items = []
	available_rows = []

	# =========================
	# STEP 2: SBB CHECK
	# =========================
	for item_dict in so_item_details.values():
		for details in item_dict.values():

			warehouse = doc.get("for_warehouse") or details.get("default_warehouse")
			required_qty = flt(details.qty)

			dimensions = {
				"custom_length": details.get("custom_length"),
				"custom_thickness": details.get("custom_thickness"),
				"custom_width": details.get("custom_width"),
			}

			available_qty, matched_batches = get_sbb_available_qty(
				details.item_code,
				warehouse,
				dimensions
			)

			# Build available-rows list (one row per matching batch)
			for batch in matched_batches:
				available_rows.append({
					"item_code": details.item_code,
					"item_name": details.item_name,
					"batch_no": batch["batch_no"],
					"required_qty": required_qty,
					"available_qty": batch["qty"],
					"custom_sec_qty": batch["custom_sec_qty"],
					"custom_sec_uom": batch["custom_sec_uom"],
					"uom": details.get("stock_uom"),
					"custom_length": dimensions["custom_length"],
					"custom_thickness": dimensions["custom_thickness"],
					"custom_width": dimensions["custom_width"],
					"warehouse": warehouse,
					"custom_parent_item_group": details.get("custom_parent_item_group"),
				})

			shortage_qty = required_qty - available_qty

			# =========================
			# STEP 3: CREATE MR ONLY IF SHORTAGE
			# =========================
			if shortage_qty > 0:
				item_row = get_material_request_items(
					doc,
					details,
					None,
					company,
					ignore_existing_ordered_qty,
					include_safety_stock,
					warehouse,
					{},
					defaultdict(float),
				)

				if item_row:
					item_row["quantity"] = shortage_qty
					item_row["custom_thickness"] = dimensions["custom_thickness"]
					item_row["custom_length"] = dimensions["custom_length"]
					item_row["custom_width"] = dimensions["custom_width"]
					item_row["required_bom_qty"] = shortage_qty
					item_row["custom_parent_item_group"] = details.get("custom_parent_item_group")
					item_row["custom_unit_weight"] = details.get("custom_unit_weight")

					# Calculate NOS (sec_qty) for the shortage
					group = details.get("custom_parent_item_group")
					length = flt(dimensions.get("custom_length"))
					thickness = flt(dimensions.get("custom_thickness"))
					width = flt(dimensions.get("custom_width"))
					unit_weight = flt(details.get("custom_unit_weight"))

					if group == "Structurals" and length and unit_weight:
						denominator = (length / 1000) * unit_weight
						if denominator:
							item_row["custom_sec_qty"] = ceil(shortage_qty / denominator)
					elif group == "Plates" and length and width and thickness and unit_weight:
						denominator = (length / 1000) * (width / 1000) * thickness * unit_weight
						if denominator:
							item_row["custom_sec_qty"] = ceil(shortage_qty / denominator)
					elif group in ("Nuts and Bolts", "Fasteners") and unit_weight:
						# shortage is in Nos; sec_qty = Kg reference
						item_row["custom_sec_qty"] = shortage_qty * unit_weight

					item_row["custom_sec_uom"] = frappe.db.get_value(
						"Item", details.item_code, "custom_secondary_uom"
					)

					mr_items.append(item_row)

	return {"mr_items": mr_items, "available_raw_materials": available_rows}


def get_exploded_items(item_details, company, bom_no, include_non_stock_items, planned_qty=1, doc=None,
                       planned_nos=None):
	# Delegate to the dimension-aware direct query so all rows with different
	# custom dimensions are kept separate (ERPNext's BOM Explosion merges rows
	# by item_code+UOM without considering custom_length/thickness/width).
	return get_bom_items_direct(item_details, company, bom_no, include_non_stock_items, planned_qty,
	                            planned_nos=planned_nos)


def get_bom_items_direct(item_details, company, bom_no, include_non_stock_items, planned_qty=1,
                         planned_nos=None):
	"""
	Query BOM Item rows directly instead of BOM Explosion Item.

	Each BOM Item row is preserved as a separate entry keyed by its unique row
	name — even when two rows share the same item_code and dimensions (e.g., the
	same structural profile used in multiple positions). qty is scaled by
	planned_qty / bom.quantity.

	A drawing BOM's quantity is Kg (its Cust Weight (Total), sep14 FG plan D12), and
	the Production Plan passes its planned_qty in Kg, so that ratio is unchanged.
	Material Planning plans in pieces, so it passes planned_nos instead and the
	ratio becomes planned_nos / BOM Qty (Nos). A BOM with no Qty (Nos) -- one made
	before the change, whose quantity WAS the piece count -- falls back to
	quantity, which is what it always did.
	"""
	scale = None
	if planned_nos is not None:
		bom_qty, bom_nos = frappe.db.get_value("BOM", bom_no, ["quantity", "custom_sec_qty"]) or (0, 0)
		scale = flt(planned_nos) / (flt(bom_nos) or flt(bom_qty) or 1)

	bi = frappe.qb.DocType("BOM Item")
	bom = frappe.qb.DocType("BOM")
	item = frappe.qb.DocType("Item")
	item_default = frappe.qb.DocType("Item Default")
	item_uom = frappe.qb.DocType("UOM Conversion Detail")

	data = (
		frappe.qb.from_(bi)
		.join(bom)
		.on(bom.name == bi.parent)
		.join(item)
		.on(item.name == bi.item_code)
		.left_join(item_default)
		.on((item_default.parent == item.name) & (item_default.company == company))
		.left_join(item_uom)
		.on((item.name == item_uom.parent) & (item_uom.uom == item.purchase_uom))
		.select(
			bi.name.as_("bom_item_name"),
			bi.idx,
			(
				(bi.stock_qty * scale) if scale is not None
				else (bi.stock_qty / IfNull(bom.quantity, 1) * planned_qty)
			).as_("qty"),
			item.item_name,
			item.name.as_("item_code"),
			bi.description,
			bi.stock_uom,
			item.min_order_qty,
			bi.source_warehouse,
			item.default_material_request_type,
			item_default.default_warehouse,
			item.purchase_uom,
			item_uom.conversion_factor,
			item.safety_stock,
			bom.item.as_("main_bom_item"),
			bi.custom_length,
			bi.custom_thickness,
			bi.custom_width,
			item.custom_parent_item_group,
			bi.custom_unit_weight,
			bi.custom_item_number,
			bi.custom_sec_qty,
		)
		.where(
			(bi.docstatus < 2)
			& (bom.name == bom_no)
			& (item.is_stock_item.isin([0, 1]) if include_non_stock_items else item.is_stock_item == 1)
		)
		.orderby(bi.idx)
	).run(as_dict=True)

	for d in data:
		if not d.conversion_factor and d.purchase_uom:
			d.conversion_factor = get_uom_conversion_factor(d.item_code, d.purchase_uom)
		# Key by the BOM Item row's unique name so every row is preserved individually
		item_details[d["bom_item_name"]] = d

	return item_details


def get_uom_conversion_factor(item_code, uom):
	return frappe.db.get_value(
		"UOM Conversion Detail", {"parent": item_code, "uom": uom}, "conversion_factor"
	)


def get_warehouse_list(warehouses):
	warehouse_list = []

	if isinstance(warehouses, str):
		warehouses = json.loads(warehouses)

	for row in warehouses:
		child_warehouses = frappe.db.get_descendants("Warehouse", row.get("warehouse"))
		if child_warehouses:
			warehouse_list.extend(child_warehouses)
		else:
			warehouse_list.append(row.get("warehouse"))

	return warehouse_list


def get_material_request_items(
	doc,
	row,
	sales_order,
	company,
	ignore_existing_ordered_qty,
	include_safety_stock,
	warehouse,
	bin_dict,
	consumed_qty,
):
	required_qty = 0
	item_code = row.get("item_code")

	if ignore_existing_ordered_qty or bin_dict.get("projected_qty", 0) < 0:
		required_qty = flt(row.get("qty"))
	else:
		key = (item_code, warehouse)
		available_qty = flt(bin_dict.get("projected_qty", 0)) - consumed_qty[key]
		if available_qty > 0:
			required_qty = max(0, flt(row.get("qty")) - available_qty)
			consumed_qty[key] += min(flt(row.get("qty")), available_qty)
		else:
			required_qty = flt(row.get("qty"))

	if doc.get("consider_minimum_order_qty") and required_qty > 0 and required_qty < row["min_order_qty"]:
		required_qty = row["min_order_qty"]

	item_group_defaults = get_item_group_defaults(row.item_code, company)

	if not row["purchase_uom"]:
		row["purchase_uom"] = row["stock_uom"]

	if row["purchase_uom"] != row["stock_uom"]:
		if not (row["conversion_factor"] or frappe.flags.show_qty_in_stock_uom):
			frappe.throw(
				_("UOM Conversion factor ({0} -> {1}) not found for item: {2}").format(
					row["purchase_uom"], row["stock_uom"], row.item_code
				)
			)

			required_qty = required_qty / row["conversion_factor"]

	if frappe.db.get_value("UOM", row["purchase_uom"], "must_be_whole_number"):
		required_qty = ceil(required_qty)

	if include_safety_stock:
		required_qty += flt(row["safety_stock"])

	item_details = frappe.get_cached_value("Item", row.item_code, ["purchase_uom", "stock_uom"], as_dict=1)

	conversion_factor = 1.0
	if (
		row.get("default_material_request_type") == "Purchase"
		and item_details.purchase_uom
		and item_details.purchase_uom != item_details.stock_uom
	):
		conversion_factor = (
			get_conversion_factor(row.item_code, item_details.purchase_uom).get("conversion_factor") or 1.0
		)

	if required_qty > 0:
		return {
			"item_code": row.item_code,
			"item_name": row.item_name,
			"quantity": required_qty / conversion_factor,
			"conversion_factor": conversion_factor,
			"required_bom_qty": row.get("qty"),
			"stock_uom": row.get("stock_uom"),
			"warehouse": warehouse
			or row.get("source_warehouse")
			or row.get("default_warehouse")
			or item_group_defaults.get("default_warehouse"),
			"safety_stock": row.safety_stock,
			"actual_qty": bin_dict.get("actual_qty", 0),
			"projected_qty": bin_dict.get("projected_qty", 0),
			"ordered_qty": bin_dict.get("ordered_qty", 0),
			"reserved_qty_for_production": bin_dict.get("reserved_qty_for_production", 0),
			"min_order_qty": row["min_order_qty"],
			"material_request_type": row.get("default_material_request_type"),
			"sales_order": sales_order,
			"description": row.get("description"),
			"uom": row.get("purchase_uom") or row.get("stock_uom"),
			"main_bom_item": row.get("main_bom_item"),
		}



@frappe.whitelist()
def get_mp_planned_weights(mp_duno_pairs):
	"""Return {"mp|duno": planned_rm_weight_kg} for each (mp, duno_mark_no) pair.
	Keying by duno ensures each drawing in a PP gets its own per-drawing weight,
	not the whole-MP total."""
	if isinstance(mp_duno_pairs, str):
		mp_duno_pairs = json.loads(mp_duno_pairs)
	result = {}
	for pair in mp_duno_pairs:
		mp   = pair.get("mp") or ""
		duno = pair.get("duno") or ""
		key  = f"{mp}|{duno}"
		result[key] = _calc_mp_drawing_weight(mp, duno)
	return result


def _calc_mp_drawing_weight(mp_name, duno_mark_no):
	"""Planned RM weight for one drawing — sum of qty from the raw_materials sub-table.
	Using raw_materials (always has duno_mark_no) rather than reservations tables
	(available_raw_material has no duno_mark_no so can't be split per drawing)."""
	if not mp_name:
		return 0.0
	if duno_mark_no:
		wt = frappe.db.sql(
			"""SELECT COALESCE(SUM(qty), 0)
			   FROM `tabMaterial Planning Raw Material`
			   WHERE parent = %s AND duno_mark_no = %s""",
			(mp_name, duno_mark_no),
		)[0][0] or 0
		return flt(wt)
	return _calc_mp_weight(mp_name)


def _calc_mp_weight(mp_name):
	"""Full-MP planned RM weight (all drawings combined)."""
	if not mp_name:
		return 0.0
	mapping_wt = frappe.db.sql(
		"""SELECT COALESCE(SUM(batch_calc_qty), 0)
		   FROM `tabMaterial Planning Material Mapping`
		   WHERE parent = %s AND is_reserved = 1 AND batch IS NOT NULL AND batch != ''""",
		mp_name,
	)[0][0] or 0
	available_wt = frappe.db.sql(
		"""SELECT COALESCE(SUM(reserved_qty), 0)
		   FROM `tabMaterial Planning Available Raw Material`
		   WHERE parent = %s AND is_reserved = 1""",
		mp_name,
	)[0][0] or 0
	return flt(mapping_wt) + flt(available_wt)


@frappe.whitelist()
def get_pp_drawings_for_picker(search_type, search_value, pp_name=""):
	"""
	Returns drawing rows for the Production Plan picker popup.
	search_type: "material_planning" or "sales_order"
	search_value: MP name or SO name
	pp_name: current PP (used to flag rows already in this plan)
	"""
	if search_type == "material_planning":
		return _picker_rows_from_mp(search_value, pp_name)
	elif search_type == "sales_order":
		return _picker_rows_from_so(search_value, pp_name)
	return []


def _item_stock_uoms(item_codes):
	"""stock_uom for a set of items, in one query."""
	codes = sorted({c for c in (item_codes or []) if c})
	if not codes:
		return {}
	return {
		r.name: r.stock_uom
		for r in frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "stock_uom"])
	}


def _picker_rows_from_mp(mp_name, pp_name):
	mp = frappe.get_doc("Material Planning", mp_name)
	if mp.docstatus == 2:
		frappe.throw(_("Material Planning {0} is cancelled.").format(mp_name))
	if not mp.bom_items:
		frappe.throw(_("No BOM items found on Material Planning {0}.").format(mp_name))

	# Batch-fetch customer weights from Sales Order DUNO Items
	so_duno_pairs = [(r.sales_order, r.duno_mark_no) for r in mp.bom_items if r.sales_order and r.duno_mark_no]
	customer_weights = {}
	if so_duno_pairs:
		where_clauses = " OR ".join(["(parent = %s AND duno_mark_no = %s)"] * len(so_duno_pairs))
		params = [x for pair in so_duno_pairs for x in pair]
		wt_rows = frappe.db.sql(
			f"SELECT parent, duno_mark_no, total_weight FROM `tabSales Order DUNO Item` WHERE {where_clauses}",
			params, as_dict=True,
		)
		customer_weights = {(r.parent, r.duno_mark_no): flt(r.total_weight) for r in wt_rows}

	# The Production Plan row's UOM is the finished-goods item's stock UOM (Kg), which is
	# what Planned Qty is in. The Material Planning row's own UOM is Nos, the unit of its
	# Qty to Manufacture -- passing that through labelled Planned Qty (Kg) "Nos" and
	# ERPNext then refused it as a fraction of a whole-number UOM.
	stock_uoms = _item_stock_uoms(r.item_code for r in mp.bom_items)

	rows = []
	for row in mp.bom_items:
		cust_name = ""
		if row.customer:
			cust_name = frappe.db.get_value("Customer", row.customer, "customer_name") or row.customer
		rows.append({
			"bom_no": row.bom_no or "",
			"item_code": row.item_code or "",
			"item_name": row.item_name or "",
			"drawing": row.drawing or "",
			"duno_mark_no": row.duno_mark_no or "",
			"customer_drawing_number": row.customer_drawing_number or "",
			"sales_order": row.sales_order or "",
			"customer": row.customer or "",
			"customer_name": cust_name,
			"qty_to_manufacture": flt(row.qty_to_manufacture) or 1,
			"uom": stock_uoms.get(row.item_code) or row.uom or "",
			"material_planning": mp_name,
			"for_warehouse": mp.for_warehouse or "",
			"mp_complete": True,
			"mp_docstatus": mp.docstatus,
			"customer_weight": customer_weights.get((row.sales_order or "", row.duno_mark_no or ""), 0.0),
		})

	_mark_already_in_pp(rows, pp_name)
	return rows


def _picker_rows_from_so(so_name, pp_name):
	mp_bom_items = frappe.db.sql("""
		SELECT
			mpbi.bom_no, mpbi.item_code, mpbi.item_name, mpbi.drawing,
			mpbi.duno_mark_no, mpbi.customer_drawing_number, mpbi.sales_order,
			mpbi.customer, mpbi.qty_to_manufacture, mpbi.uom,
			mpbi.parent AS material_planning,
			COALESCE(sodi.total_weight, 0) AS customer_weight
		FROM `tabMaterial Planning BOM Item` mpbi
		INNER JOIN `tabMaterial Planning` mp ON mp.name = mpbi.parent
		LEFT JOIN `tabSales Order DUNO Item` sodi
			ON sodi.parent = mpbi.sales_order AND sodi.duno_mark_no = mpbi.duno_mark_no
		WHERE mpbi.sales_order = %s
		  AND mp.docstatus != 2
		ORDER BY mpbi.parent, mpbi.idx
	""", (so_name,), as_dict=True)

	if not mp_bom_items:
		return []

	# Determine completion per MP: has stock analysis tables populated
	mp_names = list({r.material_planning for r in mp_bom_items})
	mp_completion = {}
	for mp_n in mp_names:
		has_analysis = (
			frappe.db.count("Material Planning Available Raw Material", {"parent": mp_n}) > 0
			or frappe.db.count("Material Planning Material Mapping", {"parent": mp_n}) > 0
			or frappe.db.count("Material Planning Unavailable Item", {"parent": mp_n}) > 0
		)
		mp_vals = frappe.db.get_value("Material Planning", mp_n, ["docstatus", "for_warehouse"], as_dict=True) or {}
		mp_completion[mp_n] = {
			"complete": has_analysis,
			"docstatus": mp_vals.get("docstatus") or 0,
			"for_warehouse": mp_vals.get("for_warehouse") or "",
		}

	stock_uoms = _item_stock_uoms(r.item_code for r in mp_bom_items)  # see _picker_rows_from_mp

	rows = []
	for r in mp_bom_items:
		cust_name = ""
		if r.customer:
			cust_name = frappe.db.get_value("Customer", r.customer, "customer_name") or r.customer
		mp_info = mp_completion.get(r.material_planning, {"complete": False, "docstatus": 0, "for_warehouse": ""})
		row = dict(r)
		row["uom"] = stock_uoms.get(r.item_code) or r.uom or ""
		row["customer_name"] = cust_name
		row["mp_complete"] = mp_info["complete"]
		row["mp_docstatus"] = mp_info["docstatus"]
		row["for_warehouse"] = mp_info["for_warehouse"]
		row["duno_mark_no"] = r.duno_mark_no or ""
		row["customer_drawing_number"] = r.customer_drawing_number or ""
		rows.append(row)

	_mark_already_in_pp(rows, pp_name)
	return rows


def _mark_already_in_pp(rows, current_pp_name):
	"""Flag each picker row as in this plan, fully planned elsewhere, or free.

	A drawing may be split across plans (D16), so being on another plan no longer
	locks it: what locks it is having no pieces left. Each drawing row carries its
	remaining Nos -- the default the picker inserts -- and is only put with the
	"already in another Production Plan" rows once that reaches 0. Rows with no
	drawing keep the old one-plan-per-BOM rule."""
	_mark_fg_nos_left(rows, current_pp_name)

	bom_nos = [r.get("bom_no") for r in rows if r.get("bom_no")]
	if not bom_nos:
		return

	placeholders = ", ".join(["%s"] * len(bom_nos))
	used_rows = frappe.db.sql(
		"""
		SELECT ppi.bom_no, ppi.parent
		FROM `tabProduction Plan Item` ppi
		INNER JOIN `tabProduction Plan` pp ON pp.name = ppi.parent
		WHERE ppi.bom_no IN ({placeholders})
		  AND pp.docstatus != 2
		ORDER BY ppi.parent
		""".format(placeholders=placeholders),
		tuple(bom_nos),
		as_dict=True,
	)

	bom_pp_map = {}
	for u in used_rows:
		bom_pp_map.setdefault(u.bom_no, []).append(u.parent)

	for r in rows:
		pp_list = bom_pp_map.get(r.get("bom_no"), [])
		r["already_in_this_pp"] = bool(current_pp_name and current_pp_name in pp_list)
		other_pps = [p for p in pp_list if p != current_pp_name]
		if r.get("fg_nos_tracked"):
			# Split plans are allowed; only a drawing with nothing left is taken.
			r["already_in_pp"] = (", ".join(other_pps) or _("fully planned")) if flt(r.get("nos_left")) <= 0 else ""
			r["other_pps"] = ", ".join(other_pps)
		else:
			r["already_in_pp"] = other_pps[0] if other_pps else ""


def _mark_fg_nos_left(rows, current_pp_name):
	"""Add drawing Nos, Nos left and both customer weights to each picker row."""
	drawings = list({r.get("drawing") for r in rows if r.get("drawing")})
	if not drawings:
		return
	elsewhere = fg_nos_planned_elsewhere(drawings, exclude_pp=current_pp_name)
	cache = {}
	for r in rows:
		drawing = r.get("drawing")
		if not drawing:
			continue
		if drawing not in cache:
			cache[drawing] = drawing_fg_weights(drawing)
		info = cache[drawing]
		if not info:
			continue
		used = sum(n for _pp, n in elsewhere.get(drawing, []))
		r["fg_nos_tracked"] = 1
		r["drawing_nos"] = info.nos
		r["nos_left"] = max(flt(info.nos - used, 3), 0.0)
		r["cust_weight_total"] = info.total
		r["cust_weight_per_nos"] = info.per_nos


@frappe.whitelist()
def get_operations_from_routing(bom_no):
    """Return ordered list of operations for a BOM (from its operations table)."""
    if not bom_no:
        return []
    ops = frappe.db.sql("""
        SELECT operation FROM `tabBOM Operation`
        WHERE parent = %s AND operation IS NOT NULL AND operation != ''
        ORDER BY idx
    """, bom_no, as_dict=True)
    return [r.operation for r in ops]


@frappe.whitelist()
def get_standard_routing_operations():
    """Return ordered operations from Standard Manufacturing Routing."""
    ops = frappe.db.sql("""
        SELECT operation FROM `tabBOM Operation`
        WHERE parent = 'Standard Manufacturing Routing'
          AND parenttype = 'Routing'
          AND operation IS NOT NULL AND operation != ''
        ORDER BY idx
    """, as_dict=True)
    return [r.operation for r in ops]


@frappe.whitelist()
def make_material_request(doc, submit):
	self = frappe.get_doc("Production Plan", doc)
	material_request_list = []
	material_request_map = {}

	for item in self.mr_items:
		item_doc = frappe.get_cached_doc("Item", item.item_code)

		material_request_type = item.material_request_type or item_doc.default_material_request_type

		key = "{}:{}:{}".format(item.sales_order, material_request_type, item_doc.customer or "")
		schedule_date = item.schedule_date or add_days(nowdate(), cint(item_doc.lead_time_days))

		if key not in material_request_map:
			material_request_map[key] = frappe.new_doc("Material Request")
			material_request = material_request_map[key]
			material_request.update(
				{
					"transaction_date": nowdate(),
					"status": "Draft",
					"company": self.company,
					"material_request_type": material_request_type,
					"customer": item_doc.customer or "",
				}
			)
			material_request_list.append(material_request)
		else:
			material_request = material_request_map[key]

		material_request.append(
			"items",
			{
				"item_code": item.item_code,
				"from_warehouse": item.from_warehouse
				if material_request_type == "Material Transfer"
				else None,
				"qty": item.quantity,
				"custom_length": item.custom_length,
				"custom_thickness": item.custom_thickness,
				"custom_width": item.custom_width,
				"custom_sec_qty": item.custom_sec_qty,
				"custom_sec_uom": item.custom_sec_uom,
				"schedule_date": schedule_date,
				"warehouse": item.warehouse,
				"sales_order": item.sales_order,
				"production_plan": self.name,
				"material_request_plan_item": item.name,
				"project": frappe.db.get_value("Sales Order", item.sales_order, "project")
				if item.sales_order
				else None,
			},
		)

	for material_request in material_request_list:
		material_request.flags.ignore_permissions = 1
		material_request.run_method("set_missing_values")
		material_request.save()
		if self.get("submit_material_request"):
			material_request.submit()

	frappe.flags.mute_messages = False

	if material_request_list:
		material_request_list = [
			get_link_to_form("Material Request", m.name) for m in material_request_list
		]
		frappe.msgprint(_("{0} created").format(comma_and(material_request_list)))
	else:
		frappe.msgprint(_("No material request created"))


PP_TYPE_ABBR = {
	"Internal Job": "INT",
	"Supplier Job": "SUP",
	"Supplier with Material": "SUPWM",
}


def autoname_production_plan(doc, method):
	"""Name as PP-<abbr>-<year>-<running>, e.g. PP-INT-2026-00001, based on the
	Type field — resets the running number every year since the year is baked
	into the series prefix. Overrides the core naming_series-based naming."""
	abbr = PP_TYPE_ABBR.get(doc.custom_type)
	if not abbr:
		frappe.throw(_("Set Type before saving (Internal Job / Supplier Job / Supplier with Material)."))
	doc.name = make_autoname(f"PP-{abbr}-.YYYY.-.#####", doc.doctype, doc)


def after_save_production_plan(doc, method):
	for row in doc.mr_items:
		_recalculate_sec_qty(row)


def refresh_production_plan_status(pp_name):
	"""Move a plan's Status along with the work its Job Work Order is doing.

	ERPNext derives a Production Plan's status from total_produced_qty and
	all_items_completed(), both of which read Work Orders. This app's plans are
	executed through a Job Work Order and a Material Issue Plan instead -- no Work
	Order is ever created -- so total_produced_qty stays 0 forever and the plan sat
	on "Not Started" from submit to the end of the job, however much had been
	transferred, made and booked.

	  In Process   material has been transferred against the plan's Material Issue
	               Plan, or any operation on the Job Work Order has quantity logged
	  Completed    the Material Issue Plan's final Stock Entry is submitted, i.e.
	               the finished goods are actually in stock

	Completed waits for that entry to be SUBMITTED, not merely created: the button
	hands back a draft, and a draft can still be edited or deleted. Like the Job
	Work Order's own status this is derived on each event rather than latched, so
	cancelling the final entry drops the plan back to In Process.

	Written with db_set so it does not fight ERPNext's set_status during a save, and
	only for plans that actually have a Job Work Order -- a standard plan keeps
	ERPNext's own Work-Order-driven status untouched.
	"""
	if not pp_name:
		return

	pp = frappe.db.get_value(
		"Production Plan", pp_name, ["name", "docstatus", "status"], as_dict=True
	)
	if not pp or pp.docstatus != 1:
		return
	# Closed and Cancelled are deliberate stops; never talk over them.
	if pp.status in ("Closed", "Cancelled"):
		return

	sco_names = frappe.get_all(
		"Subcontracting Order",
		filters={"custom_production_plan": pp_name, "docstatus": 1},
		pluck="name",
	)
	if not sco_names:
		return

	from manufyxinvenzaerp.subcontracting_management.overrides import (
		_any_operation_started,
		_final_stock_entry_submitted,
	)

	if any(_final_stock_entry_submitted(sco) for sco in sco_names):
		status = "Completed"
	elif _plan_material_transferred(pp_name, sco_names) or any(
		_any_operation_started(sco) for sco in sco_names
	):
		status = "In Process"
	else:
		return  # nothing has happened yet -- leave ERPNext's own value alone

	if pp.status != status:
		frappe.db.set_value("Production Plan", pp_name, "status", status, update_modified=False)


def _plan_material_transferred(pp_name, sco_names):
	"""True once any submitted Stock Entry has moved material for this plan.

	Matches on the Material Issue Plan reference the transfer carries
	(custom_mip_ref, set by _tag_stock_entry) as well as the Job Work Order one,
	because a transfer can be raised against either side of the same job."""
	mip_names = frappe.get_all(
		"Material Issue Plan", filters={"production_plan": pp_name}, pluck="name"
	)
	conditions, values = [], {}
	if mip_names:
		conditions.append("custom_mip_ref IN %(mips)s")
		values["mips"] = tuple(mip_names)
	if sco_names:
		conditions.append("custom_sco_ref IN %(scos)s")
		values["scos"] = tuple(sco_names)
	if not conditions:
		return False

	return bool(frappe.db.sql(
		"SELECT 1 FROM `tabStock Entry` WHERE docstatus = 1 AND ({0}) LIMIT 1".format(
			" OR ".join(conditions)
		),
		values,
	))


def validate_duno_uniqueness(doc, method):
	"""No two Production Plan Items may share a DUNO/Mark No.

	The twin of Material Planning's own check, and needed separately because a plan
	does not have to come from one: the "Add Drawings" picker builds po_items
	directly, and can pull from several Material Plannings and several Sales Orders
	in one go.

	This is the gate that matters most for the transfer chain. The Material Issue
	Plan's transfer scope (_linked_mp_names_and_duno_scope) is built from THIS
	table's DUNOs and then applied to the linked Material Planning's reserved rows --
	so a repeated mark here would offer another Sales Order's reserved batches for
	shipment to this job's supplier.
	"""
	from manufyxinvenzaerp.drawing_management.duno_uniqueness import assert_unique, normalise

	rows = [
		normalise(r, duno_field="custom_duno_mark_no",
		          cdn_field="custom_customer_drawing_number",
		          drawing_field="custom_drawing")
		for r in (doc.po_items or [])
	]
	assert_unique(rows, _("Items to Manufacture"))


def validate_process_planning(doc, method):
	"""Every custom_process_planning row needs a work_type, and a plan with any
	Subcontractor row needs a Vendor/Contractor.

	Work Type ORDER is deliberately not checked. This used to insist that every
	Subcontractor row came before every Internal Jobcard row, on the reasoning that
	a subcontractor cannot hand off to internal ops and then get material back
	mid-stream. That is not how the shop actually works -- a job routinely goes out
	for cutting, comes back for fit-up, and goes out again for painting -- and the
	rule was removed at the client's request so Work Type can be set freely per row.

	Nothing downstream ever depended on the ordering: create_sco_from_production_plan
	says so in its own docstring, and _create_soes_for_sco builds one Supplier
	Operation Entry per row in sequence_id order, reading work_type only to decide
	whether that entry carries a supplier and supplier warehouse. A mixed plan is
	covered by tests/verify_mixed_sco_regression.py.
	"""
	has_subcontractor = False
	for row in (doc.custom_process_planning or []):
		if not row.work_type:
			frappe.throw(
				_("Row {0} ({1}): set Work Type (Subcontractor / Internal Jobcard).")
				.format(row.idx, row.operation_name),
				title=_("Work Type Required"),
			)
		if row.work_type == "Subcontractor":
			has_subcontractor = True

	# Backstop for the field's client-side mandatory_depends_on — covers API/
	# import-created documents that bypass the form's own validation.
	if has_subcontractor and not doc.custom_vendor_contractor:
		frappe.throw(
			_("Set Vendor/Contractor — it's required when any Process Planning row has "
			  "Work Type set to Subcontractor."),
			title=_("Vendor/Contractor Required"),
		)


# ─────────────────────────────────────────────────────────────────────────────
# Finished goods planned in Nos, carried in Kg (sep14 FG plan, D5 / D16 / D26)
# ─────────────────────────────────────────────────────────────────────────────

def fg_kg_for_nos(total, nos, drawing_nos):
	"""Kg for `nos` pieces of a drawing: Cust Weight (Total) x Nos / drawing Nos.

	Worked from the Total rather than per Nos x Nos so that planning every piece
	gives back the Total exactly -- per Nos is rounded to 3 dp, and 3 x 33.333 is
	not 100. Shared by the Production Plan, the Job Work Order builder and the
	customer-weight cascade so all three land on the same figure."""
	if not flt(drawing_nos):
		return 0.0
	return flt(flt(total) * flt(nos) / flt(drawing_nos), 3)


def drawing_kg_for_nos(drawing, nos, cache=None):
	"""Kg of finished goods for `nos` pieces of `drawing`, or 0.0 when it can't be told.

	For the Qty to Manufacture (Kg) shown beside the Nos on planning rows (Material
	Planning, Job Work Order, Material Issue Plan). 0.0 for a drawing made before the
	Kg / Nos change: its Cust Weight (Total) then holds one piece's weight, so any Kg
	worked from it would be wrong. `cache` (a dict) spares repeat lookups per drawing."""
	if not drawing or not flt(nos):
		return 0.0
	if cache is not None and drawing in cache:
		info = cache[drawing]
	else:
		info = drawing_fg_weights(drawing)
		if cache is not None:
			cache[drawing] = info
	if not info or not info.has_per_nos:
		return 0.0
	return fg_kg_for_nos(info.total, nos, info.nos)


def drawing_fg_weights(drawing):
	"""The drawing's piece count and both customer weights, as one dict.

	per_nos falls back to Total / Nos for a drawing that never had the per Nos
	figure stored (made by hand, or before the Kg / Nos change)."""
	d = frappe.db.get_value(
		"Drawing", drawing,
		["name", "no_of_qty_to_manufacture", "customer_provided_wt", "weight_per_pcs",
		 "rs_rate_per_kg", "duno_mark_no", "docstatus"],
		as_dict=True,
	)
	if not d:
		return None
	nos = flt(d.no_of_qty_to_manufacture)
	total = flt(d.customer_provided_wt, 3)
	return frappe._dict(
		name=d.name,
		nos=nos,
		total=total,
		per_nos=flt(d.weight_per_pcs, 3) or (flt(total / nos, 3) if nos else 0.0),
		has_per_nos=bool(flt(d.weight_per_pcs)),
		rate_per_kg=flt(d.rs_rate_per_kg),
		duno_mark_no=d.duno_mark_no or "",
		docstatus=d.docstatus,
	)


def fg_nos_planned_elsewhere(drawings, exclude_pp=None):
	"""{drawing: [(plan, nos), ...]} over every non-cancelled Production Plan.

	Reads Qty (Nos) only. A row saved before the Kg / Nos change has none and so
	counts nothing (D13): those plans are being removed, and guessing their Nos
	from a planned_qty that may be pieces or Kg would be worse than ignoring them."""
	drawings = [d for d in (drawings or []) if d]
	if not drawings:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT ppi.custom_drawing AS drawing, ppi.parent AS pp,
		       SUM(IFNULL(ppi.custom_sec_qty, 0)) AS nos
		FROM `tabProduction Plan Item` ppi
		INNER JOIN `tabProduction Plan` pp ON pp.name = ppi.parent
		WHERE ppi.custom_drawing IN %(drawings)s
		  AND pp.docstatus < 2
		  AND pp.name != %(exclude)s
		GROUP BY ppi.custom_drawing, ppi.parent
		HAVING SUM(IFNULL(ppi.custom_sec_qty, 0)) > 0
		ORDER BY ppi.parent
		""",
		{"drawings": tuple(drawings), "exclude": exclude_pp or ""},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.drawing, []).append((r.pp, flt(r.nos)))
	return out


def fg_nos_remaining(drawing, exclude_pp=None):
	"""Pieces of a drawing no non-cancelled Production Plan has claimed yet."""
	info = drawing_fg_weights(drawing)
	if not info:
		return 0.0
	used = sum(n for _pp, n in fg_nos_planned_elsewhere([drawing], exclude_pp).get(drawing, []))
	return max(flt(info.nos - used, 3), 0.0)


def apply_fg_nos(doc, method=None):
	"""Production Plan validate hook: Planned Qty (Kg) from Qty (Nos) on drawing rows.

	The planner thinks in pieces; stock, the BOM and the Job Work Order move Kg. This
	is the ONE place the Kg of a drawing row is worked out (D26), so the picker, the
	BOM's Create Production Plan and Material Planning's Make Production Plan -- which
	each set only Qty (Nos) -- cannot drift apart:

		planned_qty = Cust Weight (Total) x Qty (Nos) / drawing Nos, 3 dp   (D5)

	Cust Weight (per Nos) and (Total) are refreshed from the drawing on every save,
	so a plan always shows the drawing's current weight.

	A drawing can be split over several plans, but never beyond its own piece count
	(D16): the Nos on every non-cancelled plan, this one included, may not exceed the
	drawing's Nos. The refusal names the other plans, because the fix is on them.

	Rows are left alone when they have no drawing, and when they have no Qty (Nos)
	on a drawing that has no per Nos weight -- a plan built before the change (D13).

	Hooks run after ERPNext's own validate, which has already totalled planned_qty
	and copied it into pending_qty; both are redone here once the Kg is known.
	"""
	rows = [r for r in (doc.get("po_items") or []) if r.get("custom_drawing")]
	if not rows:
		return

	nos_by_drawing = defaultdict(float)
	info_by_drawing = {}
	for row in rows:
		info = info_by_drawing.get(row.custom_drawing)
		if info is None:
			info = drawing_fg_weights(row.custom_drawing)
			info_by_drawing[row.custom_drawing] = info
		if not info:
			continue

		nos = flt(row.get("custom_sec_qty"))
		if nos <= 0:
			if not info.has_per_nos:
				continue  # legacy row (D13): planned_qty stays as it was entered
			frappe.throw(
				_("Row {0}: enter NOS for drawing {1} (DUNO {2}). Planned Qty (Kg) is "
				  "calculated from it.").format(row.idx, row.custom_drawing, info.duno_mark_no),
				title=_("NOS Required"),
			)
		if nos != int(nos):
			frappe.throw(
				_("Row {0}: NOS must be a whole number of pieces, not {1}.").format(row.idx, nos),
				title=_("Whole Pieces Only"),
			)
		if not info.nos or not info.total:
			frappe.throw(
				_("Row {0}: drawing {1} has no {2}. Set it with Update Customer Weight on the "
				  "drawing first.").format(
					row.idx, row.custom_drawing,
					_("No of Qty to Manufacture") if not info.nos else _("Cust Weight (Total)")),
				title=_("Customer Weight Missing"),
			)

		row.custom_sec_uom = "Nos"
		row.custom_customer_weight_kg = info.total
		row.custom_cust_weight_per_nos = info.per_nos
		row.planned_qty = fg_kg_for_nos(info.total, nos, info.nos)
		nos_by_drawing[row.custom_drawing] += nos

	if nos_by_drawing:
		elsewhere = fg_nos_planned_elsewhere(list(nos_by_drawing), exclude_pp=doc.name)
		problems = []
		for drawing, nos_here in nos_by_drawing.items():
			info = info_by_drawing[drawing]
			others = elsewhere.get(drawing, [])
			used = sum(n for _pp, n in others)
			if flt(nos_here + used, 3) > flt(info.nos, 3):
				left = max(flt(info.nos - used, 3), 0)
				problems.append(
					_("Drawing {0} (DUNO {1}) has {2} Nos. {3} Nos are already planned in {4}, "
					  "so {5} Nos are left -- this plan asks for {6}.").format(
						drawing, info.duno_mark_no, _fmt_nos(info.nos), _fmt_nos(used),
						", ".join("{0} ({1} Nos)".format(get_link_to_form("Production Plan", p), _fmt_nos(n))
						          for p, n in others) or _("no other plan"),
						_fmt_nos(left), _fmt_nos(nos_here))
				)
		if problems:
			frappe.throw("<br>".join(problems), title=_("More Pieces Than the Drawing Has"))

	# ERPNext's validate ran first and read the old planned_qty.
	doc.set_pending_qty_in_row_without_reference()
	doc.calculate_total_planned_qty()


def _fmt_nos(n):
	"""Pieces print without a trailing .0 -- '4 Nos', not '4.0 Nos'."""
	n = flt(n, 3)
	return str(int(n)) if n == int(n) else str(n)


def unlink_production_plan_on_trash(doc, method):
	linked = frappe.get_all(
		"Material Planning",
		filters={"production_plan": doc.name},
		fields=["name"],
	)
	for mp in linked:
		frappe.db.set_value("Material Planning", mp.name, "production_plan", "")


PLATES_REQUIRED = ["custom_length", "custom_width", "custom_thickness", "custom_unit_weight", "quantity"]


def _recalculate_sec_qty(row):
	group = row.custom_parent_item_group

	if group == "Structurals":
		if row.custom_length and row.custom_unit_weight:
			denominator = (row.custom_length / 1000) * row.custom_unit_weight
			if denominator:
				row.custom_sec_qty = row.quantity / denominator

	elif group == "Plates":
		if all(getattr(row, f, None) for f in PLATES_REQUIRED):
			denominator = (
				(row.custom_length / 1000)
				* (row.custom_width / 1000)
				* row.custom_thickness
				* row.custom_unit_weight
			)
			if denominator:
				row.custom_sec_qty = row.quantity / denominator
