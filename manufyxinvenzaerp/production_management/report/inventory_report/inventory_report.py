# Copyright (c) 2026, Manufyxinvenza and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def _params(filters):
	params = {}
	if filters.get("item_code"):
		params["item_code"] = filters["item_code"]
	if filters.get("sales_order"):
		params["sales_order"] = filters["sales_order"]
	if filters.get("project"):
		params["project"] = filters["project"]
	if filters.get("company"):
		params["company"] = filters["company"]
	if filters.get("from_date"):
		params["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		params["to_date"] = filters["to_date"]
	return params


def _clause(filters, item_alias, parent_alias, date_field):
	parts = []
	if filters.get("item_code"):
		parts.append(f"{item_alias}.item_code = %(item_code)s")
	if filters.get("sales_order"):
		parts.append(f"{item_alias}.sales_order = %(sales_order)s")
	if filters.get("project"):
		parts.append(f"{item_alias}.project = %(project)s")
	if filters.get("company"):
		parts.append(f"{parent_alias}.company = %(company)s")
	if filters.get("from_date"):
		parts.append(f"{parent_alias}.{date_field} >= %(from_date)s")
	if filters.get("to_date"):
		parts.append(f"{parent_alias}.{date_field} <= %(to_date)s")
	return (" AND " + " AND ".join(parts)) if parts else ""


def get_data(filters):
	params = _params(filters)

	ordered_rows = frappe.db.sql(f"""
		SELECT poi.item_code, poi.sales_order, poi.project, SUM(poi.qty) AS qty
		FROM `tabPurchase Order Item` poi
		JOIN `tabPurchase Order` po ON po.name = poi.parent
		WHERE po.docstatus = 1 {_clause(filters, "poi", "po", "transaction_date")}
		GROUP BY poi.item_code, poi.sales_order
	""", params, as_dict=True)

	received_rows = frappe.db.sql(f"""
		SELECT pri.item_code, pri.sales_order, pri.project, SUM(pri.qty) AS qty
		FROM `tabPurchase Receipt Item` pri
		JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pr.docstatus = 1 {_clause(filters, "pri", "pr", "posting_date")}
		GROUP BY pri.item_code, pri.sales_order
	""", params, as_dict=True)

	# "Issued" = material physically transferred out via this app's MIP transfer
	# flow: Send to Subcontractor and Material Transfer entries tagged
	# custom_mip_ref, and only those.
	#
	# Named rather than excluded. This used to read `!= 'Material Receipt'`, which
	# was right only while the excess return WAS a Material Receipt -- it became a
	# Repack (a receipt with no source warehouse created stock while the same kilos
	# still stood at the supplier), and process loss arrived as a Material Issue.
	# Both carry custom_mip_ref, neither is a Material Receipt, so both were being
	# counted as issued and the figure was overstated by the return plus the
	# write-off. A blacklist has to be revisited every time the chain gains a step
	# and silently reports wrong numbers when it is not; this cannot.
	issued_rows = frappe.db.sql(f"""
		SELECT sed.item_code, sed.custom_sales_order AS sales_order, SUM(sed.qty) AS qty
		FROM `tabStock Entry Detail` sed
		JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.docstatus = 1 AND se.custom_mip_ref IS NOT NULL AND se.custom_mip_ref != ''
		  AND se.stock_entry_type IN ('Send to Subcontractor', 'Material Transfer')
		  {_clause(filters, "sed", "se", "posting_date")}
		GROUP BY sed.item_code, sed.custom_sales_order
	""", params, as_dict=True)

	item_codes = set()
	keys = set()
	for rows in (ordered_rows, received_rows, issued_rows):
		for r in rows:
			item_codes.add(r.item_code)
			keys.add((r.item_code, r.sales_order or ""))

	if not keys:
		return []

	ordered_map = {(r.item_code, r.sales_order or ""): flt(r.qty) for r in ordered_rows}
	received_map = {(r.item_code, r.sales_order or ""): flt(r.qty) for r in received_rows}
	issued_map = {(r.item_code, r.sales_order or ""): flt(r.qty) for r in issued_rows}

	item_data = {
		i.name: i for i in frappe.get_all(
			"Item", filters={"name": ["in", list(item_codes)]},
			fields=["name", "item_name", "item_group", "stock_uom"],
		)
	}

	so_names = {k[1] for k in keys if k[1]}
	so_map = {}
	if so_names:
		for so in frappe.get_all("Sales Order", filters={"name": ["in", list(so_names)]},
								  fields=["name", "customer", "project"]):
			so_map[so.name] = so

	# Closing stock isn't SO-tagged in the ledger -- reported per item_code
	# only (overall on-hand across warehouses, optionally scoped by
	# company), duplicated across every SO row for that item.
	closing_filters = {"actual_qty": ["!=", 0]}
	if filters.get("item_code"):
		closing_filters["item_code"] = filters["item_code"]
	bin_rows = frappe.get_all("Bin", filters=closing_filters, fields=["item_code", "actual_qty"])
	closing_map = {}
	for b in bin_rows:
		closing_map[b.item_code] = closing_map.get(b.item_code, 0) + flt(b.actual_qty)

	data = []
	for item_code, sales_order in sorted(keys):
		item = item_data.get(item_code, frappe._dict())
		so = so_map.get(sales_order, frappe._dict())
		ordered = ordered_map.get((item_code, sales_order), 0)
		received = received_map.get((item_code, sales_order), 0)
		issued = issued_map.get((item_code, sales_order), 0)
		data.append({
			"item_code": item_code,
			"item_name": item.get("item_name") or item_code,
			"item_group": item.get("item_group") or "",
			"sales_order": sales_order or "",
			"customer": so.get("customer") or "",
			"project": so.get("project") or "",
			"ordered_qty": ordered,
			"received_qty": received,
			"pending_receipt_qty": flt(ordered - received, 3),
			"issued_qty": issued,
			"closing_stock_qty": flt(closing_map.get(item_code, 0), 3),
			"uom": item.get("stock_uom") or "",
		})

	return data


def get_columns():
	return [
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 110},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 120},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 130},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": _("Ordered Qty"), "fieldname": "ordered_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Received Qty"), "fieldname": "received_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Pending Receipt"), "fieldname": "pending_receipt_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Issued Qty"), "fieldname": "issued_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Closing Stock (Overall)"), "fieldname": "closing_stock_qty", "fieldtype": "Float", "width": 140},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 80},
	]
