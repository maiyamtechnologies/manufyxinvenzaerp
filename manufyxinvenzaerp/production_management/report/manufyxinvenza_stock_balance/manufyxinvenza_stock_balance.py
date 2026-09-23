# Copyright (c) 2026, Manufyxinvenza and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt
from pypika import functions as fn

from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter


def execute(filters=None):
	if not filters:
		filters = {}

	float_precision = cint(frappe.db.get_default("float_precision")) or 3

	columns = get_columns()
	item_map = get_item_details()
	batch_map = get_batch_details()
	iwb_map = get_item_warehouse_batch_map(filters, float_precision)

	# Apply item_group filter to batch items by restricting the map
	if filters.get("item_group"):
		items_in_group = {
			r.name for r in frappe.get_all(
				"Item",
				filters={"item_group": filters["item_group"], "has_batch_no": 1},
				fields=["name"],
			)
		}
		iwb_map = {item: wh_map for item, wh_map in iwb_map.items() if item in items_in_group}

	data = []

	# ── Batch items ──────────────────────────────────────────────────────────
	for item in sorted(iwb_map):
		for wh in sorted(iwb_map[item]):
			for batch in sorted(iwb_map[item][wh]):
				qty_dict = iwb_map[item][wh][batch]
				if flt(qty_dict.bal_qty, float_precision) <= 0:
					continue

				item_details = item_map.get(item, frappe._dict())
				batch_details = batch_map.get(batch, frappe._dict())

				# Proportional available sec qty: scale batch's sec qty by remaining fraction
				batch_sec_qty = flt(batch_details.get("custom_sec_qty", 0))
				received_qty = flt(qty_dict.get("received_qty", 0))
				if received_qty > 0 and batch_sec_qty > 0:
					available_sec_qty = flt(
						batch_sec_qty * (qty_dict.bal_qty / received_qty), float_precision
					)
				else:
					available_sec_qty = batch_sec_qty

				data.append({
					"item_code": item,
					"item_name": item_details.get("item_name", ""),
					"description": item_details.get("description", ""),
					"warehouse": wh,
					"batch_no": batch,
					"available_qty": flt(qty_dict.bal_qty, float_precision),
					"uom": item_details.get("stock_uom", ""),
					"available_sec_qty": available_sec_qty,
					"sec_uom": batch_details.get("custom_sec_uom", ""),
					"thickness": flt(batch_details.get("custom_thickness", 0)),
					"width": flt(batch_details.get("custom_width", 0)),
					"length": flt(batch_details.get("custom_length", 0)),
					"reserved_qty": 0.0,
					"free_qty": 0.0,
					"reserved_mp": "",
					"reserved_sales_order": "",
					"reserved_project": "",
					"reserved_customer": "",
				})

	# ── Non-batch items ───────────────────────────────────────────────────────
	for nb in get_non_batch_stock(filters, float_precision):
		item_details = item_map.get(nb["item_code"], frappe._dict())
		data.append({
			"item_code": nb["item_code"],
			"item_name": item_details.get("item_name", ""),
			"description": item_details.get("description", ""),
			"warehouse": nb["warehouse"],
			"batch_no": "",
			"available_qty": flt(nb["bal_qty"], float_precision),
			"uom": item_details.get("stock_uom", ""),
			"available_sec_qty": 0.0,
			"sec_uom": "",
			"thickness": None,
			"width": None,
			"length": None,
			"reserved_qty": 0.0,
			"free_qty": 0.0,
			"reserved_mp": "",
			"reserved_sales_order": "",
			"reserved_project": "",
			"reserved_customer": "",
		})

	# ── Enrich with reservation data ─────────────────────────────────────────
	all_batch_nos = list({row["batch_no"] for row in data if row["batch_no"]})
	res_map = get_batch_reservations_map(all_batch_nos)

	non_batch_pairs = [(row["item_code"], row["warehouse"]) for row in data if not row["batch_no"]]
	nb_res_map = get_non_batch_reservations_map(non_batch_pairs)

	for row in data:
		if row["batch_no"]:
			res = res_map.get(row["batch_no"])
			if res:
				reserved_qty = flt(res["reserved_qty"], float_precision)
				row["reserved_qty"] = reserved_qty
				row["free_qty"] = flt(max(0.0, row["available_qty"] - reserved_qty), float_precision)
				row["reserved_mp"] = res["reserved_mp"]
				row["reserved_sales_order"] = res["reserved_sales_order"]
				row["reserved_project"] = res["reserved_project"]
				row["reserved_customer"] = res["reserved_customer"]
			else:
				row["free_qty"] = row["available_qty"]
		else:
			res = nb_res_map.get((row["item_code"], row["warehouse"]))
			if res:
				reserved_qty = flt(res["reserved_qty"], float_precision)
				row["reserved_qty"] = reserved_qty
				row["free_qty"] = flt(max(0.0, row["available_qty"] - reserved_qty), float_precision)
				row["reserved_mp"] = res["reserved_mp"]
			else:
				row["free_qty"] = row["available_qty"]

	return columns, data


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 130,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Description"),
			"fieldname": "description",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 130,
		},
		{
			"label": _("Batch"),
			"fieldname": "batch_no",
			"fieldtype": "Link",
			"options": "Batch",
			"width": 220,
		},
		{
			"label": _("Available Qty"),
			"fieldname": "available_qty",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 80,
		},
		{
			"label": _("Available NOS"),
			"fieldname": "available_sec_qty",
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"label": _("Sec UOM"),
			"fieldname": "sec_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 90,
		},
		{
			"label": _("Thickness"),
			"fieldname": "thickness",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Width"),
			"fieldname": "width",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Length"),
			"fieldname": "length",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Reserved Qty"),
			"fieldname": "reserved_qty",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Free Qty"),
			"fieldname": "free_qty",
			"fieldtype": "Float",
			"width": 100,
		},
		{
			"label": _("Reserved by MP"),
			"fieldname": "reserved_mp",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Sales Order"),
			"fieldname": "reserved_sales_order",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Project"),
			"fieldname": "reserved_project",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Customer"),
			"fieldname": "reserved_customer",
			"fieldtype": "Data",
			"width": 150,
		},
	]


def get_batch_reservations_map(batch_nos):
	"""Return reservation details per batch_no, aggregated across all Material Planning docs."""
	if not batch_nos:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT mm.batch AS batch_no, mm.parent AS mp_name, mm.sales_order, mm.reserved_qty
		FROM `tabMaterial Planning Material Mapping` mm
		WHERE mm.is_reserved = 1 AND mm.batch IN %(batches)s

		UNION ALL

		SELECT arm.batch_no, arm.parent AS mp_name, arm.sales_order, arm.reserved_qty
		FROM `tabMaterial Planning Available Raw Material` arm
		WHERE arm.is_reserved = 1 AND arm.batch_no IN %(batches)s
		""",
		{"batches": batch_nos},
		as_dict=True,
	)

	if not rows:
		return {}

	# Enrich with customer and project from Sales Order in one query
	so_names = list({r.sales_order for r in rows if r.get("sales_order")})
	so_map = {}
	if so_names:
		for so in frappe.get_all(
			"Sales Order",
			filters={"name": ["in", so_names]},
			fields=["name", "customer", "project"],
		):
			so_map[so.name] = so

	result = {}
	for row in rows:
		bn = row.batch_no
		if bn not in result:
			result[bn] = {
				"reserved_qty": 0.0,
				"mp_names": [],
				"sales_orders": [],
				"projects": [],
				"customers": [],
			}

		result[bn]["reserved_qty"] += flt(row.reserved_qty)

		if row.mp_name and row.mp_name not in result[bn]["mp_names"]:
			result[bn]["mp_names"].append(row.mp_name)

		so = row.get("sales_order") or ""
		if so and so not in result[bn]["sales_orders"]:
			result[bn]["sales_orders"].append(so)

		so_data = so_map.get(so) or frappe._dict()
		customer = so_data.get("customer") or ""
		project = so_data.get("project") or ""

		if customer and customer not in result[bn]["customers"]:
			result[bn]["customers"].append(customer)
		if project and project not in result[bn]["projects"]:
			result[bn]["projects"].append(project)

	for bn in result:
		d = result[bn]
		d["reserved_mp"] = ", ".join(d.pop("mp_names"))
		d["reserved_sales_order"] = ", ".join(d.pop("sales_orders"))
		d["reserved_project"] = ", ".join(d.pop("projects"))
		d["reserved_customer"] = ", ".join(d.pop("customers"))

	return result


def get_stock_ledger_entries(filters):
	return _get_sle_via_batch_no(filters) + _get_sle_via_batch_bundle(filters)


def _get_sle_via_batch_no(filters):
	"""Handles older-style SLEs that carry batch_no directly on the entry."""
	sle = frappe.qb.DocType("Stock Ledger Entry")
	query = (
		frappe.qb.from_(sle)
		.select(
			sle.item_code,
			sle.warehouse,
			sle.batch_no,
			fn.Sum(sle.actual_qty).as_("actual_qty"),
		)
		.where(
			(sle.docstatus < 2)
			& (sle.is_cancelled == 0)
			& (sle.batch_no.isnotnull())
			& (sle.batch_no != "")
		)
		.groupby(sle.voucher_no, sle.batch_no, sle.item_code, sle.warehouse)
	)

	query = apply_warehouse_filter(query, sle, filters)

	if filters.get("storage_location"):
		query = query.where(sle.storage_location == filters["storage_location"])

	for field in ["item_code", "batch_no", "company"]:
		if filters.get(field):
			query = query.where(sle[field] == filters.get(field))

	return query.run(as_dict=True) or []


def _get_sle_via_batch_bundle(filters):
	"""Handles modern SLEs that use serial-and-batch bundles."""
	sle = frappe.qb.DocType("Stock Ledger Entry")
	batch_package = frappe.qb.DocType("Serial and Batch Entry")

	query = (
		frappe.qb.from_(sle)
		.inner_join(batch_package)
		.on(batch_package.parent == sle.serial_and_batch_bundle)
		.select(
			sle.item_code,
			sle.warehouse,
			batch_package.batch_no,
			fn.Sum(batch_package.qty).as_("actual_qty"),
		)
		.where(
			(sle.docstatus < 2)
			& (sle.is_cancelled == 0)
			& (sle.has_batch_no == 1)
		)
		.groupby(sle.voucher_no, sle.item_code, sle.warehouse, batch_package.batch_no)
	)

	query = apply_warehouse_filter(query, sle, filters)

	if filters.get("storage_location"):
		query = query.where(sle.storage_location == filters["storage_location"])

	for field in ["item_code", "company"]:
		if filters.get(field):
			query = query.where(sle[field] == filters.get(field))

	if filters.get("batch_no"):
		query = query.where(batch_package.batch_no == filters.get("batch_no"))

	return query.run(as_dict=True) or []


def get_item_warehouse_batch_map(filters, float_precision):
	sle = get_stock_ledger_entries(filters)
	iwb_map = {}

	for d in sle:
		iwb_map.setdefault(d.item_code, {}).setdefault(d.warehouse, {}).setdefault(
			d.batch_no,
			frappe._dict({"bal_qty": 0.0, "received_qty": 0.0}),
		)
		qty_dict = iwb_map[d.item_code][d.warehouse][d.batch_no]
		qty_dict.bal_qty = flt(qty_dict.bal_qty, float_precision) + flt(d.actual_qty, float_precision)
		if flt(d.actual_qty) > 0:
			qty_dict.received_qty = (
				flt(qty_dict.received_qty, float_precision) + flt(d.actual_qty, float_precision)
			)

	return iwb_map


def get_item_details():
	item = frappe.qb.DocType("Item")
	return {
		d.name: d
		for d in (
			frappe.qb.from_(item)
			.select(item.name, item.item_name, item.description, item.stock_uom)
			.run(as_dict=True)
		)
	}


def get_non_batch_stock(filters, float_precision):
	"""Return balance qty per (item_code, warehouse) for non-batch items."""
	conditions = [
		"(sle.batch_no IS NULL OR sle.batch_no = '')",
		"sle.is_cancelled = 0",
		"sle.docstatus < 2",
		"i.has_batch_no = 0",
	]
	values = {}

	if filters.get("company"):
		conditions.append("sle.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("warehouse"):
		conditions.append("sle.warehouse = %(warehouse)s")
		values["warehouse"] = filters["warehouse"]
	if filters.get("item_code"):
		conditions.append("sle.item_code = %(item_code)s")
		values["item_code"] = filters["item_code"]
	if filters.get("item_group"):
		conditions.append("i.item_group = %(item_group)s")
		values["item_group"] = filters["item_group"]

	where_clause = " AND ".join(conditions)
	return frappe.db.sql(
		f"""
		SELECT sle.item_code, sle.warehouse, COALESCE(SUM(sle.actual_qty), 0) AS bal_qty
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` i ON i.name = sle.item_code
		WHERE {where_clause}
		GROUP BY sle.item_code, sle.warehouse
		HAVING COALESCE(SUM(sle.actual_qty), 0) > 0
		""",
		values,
		as_dict=True,
	) or []


def get_non_batch_reservations_map(item_warehouse_pairs):
	"""Return reservation totals per (item_code, warehouse) for non-batch items."""
	if not item_warehouse_pairs:
		return {}

	rows = frappe.db.sql(
		"""
		SELECT arm.item_code, arm.warehouse, arm.parent AS mp_name, arm.reserved_qty
		FROM `tabMaterial Planning Available Raw Material` arm
		WHERE arm.is_reserved = 1
		  AND (arm.batch_no IS NULL OR arm.batch_no = '')
		""",
		as_dict=True,
	)

	result = {}
	for row in rows:
		key = (row.item_code, row.warehouse)
		if key not in result:
			result[key] = {"reserved_qty": 0.0, "mp_names": []}
		result[key]["reserved_qty"] += flt(row.reserved_qty)
		if row.mp_name and row.mp_name not in result[key]["mp_names"]:
			result[key]["mp_names"].append(row.mp_name)

	for key in result:
		result[key]["reserved_mp"] = ", ".join(result[key].pop("mp_names"))

	return result


def get_batch_details():
	batch = frappe.qb.DocType("Batch")
	return {
		d.name: d
		for d in (
			frappe.qb.from_(batch)
			.select(
				batch.name,
				batch.custom_sec_qty,
				batch.custom_sec_uom,
				batch.custom_thickness,
				batch.custom_width,
				batch.custom_length,
			)
			.run(as_dict=True)
		)
	}
