# Copyright (c) 2026, Manufyxinvenza and Contributors
# License: GNU General Public License v3. See license.txt
"""Cut Sheet Report -- which plates are cut, who is drawing from them, what is left.

Answers the two questions the Cut Sheet list view cannot:

  * Which sheets still have pieces free, and which jobs hold the rest. An off-cut
    plan is shared across Material Plannings, so "who has claimed this" is a LIST,
    and it is read from the rows actually holding pieces rather than the Cut Sheet's
    own allocation table -- a batch can also be put on a row by hand through Update
    Batch, which never writes an allocation row.

  * Which sheets have been cut but never had their balance written back (the
    "W2 Not Written" filter). That is the state where the plate in the rack no
    longer matches what the system believes it is, so it is worth chasing.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_data(filters):
	cs_filters = {}
	for key in ("company", "item_code", "batch_no", "warehouse"):
		if filters.get(key):
			cs_filters[key] = filters[key]

	# The status filter is about what still needs attention, so it is expressed in
	# those terms rather than mirroring the doctype's own Status field exactly.
	status = filters.get("status") or "Active"
	if status == "Active":
		# Still usable: the balance has not been written back, so pieces can still
		# be taken off it.
		cs_filters["w2_applied"] = 0
	elif status == "W2 Not Written":
		cs_filters["w2_applied"] = 0
	elif status == "Consumed":
		cs_filters["w2_applied"] = 1

	if filters.get("from_date") and filters.get("to_date"):
		cs_filters["creation"] = ["between", [filters["from_date"], filters["to_date"]]]
	elif filters.get("from_date"):
		cs_filters["creation"] = [">=", filters["from_date"]]
	elif filters.get("to_date"):
		cs_filters["creation"] = ["<=", filters["to_date"]]

	sheets = frappe.get_all(
		"Cut Sheet",
		filters=cs_filters,
		fields=["name", "company", "status", "item_code", "item_name", "parent_item_group",
				"batch_no", "warehouse", "creation",
				"sheet_length", "sheet_width", "sheet_thickness", "sheet_qty",
				"w1_length", "w1_width", "w1_sec_qty", "w1_qty_per_nos", "w1_total_qty",
				"w2_length", "w2_width", "w2_sec_qty", "w2_calc_qty",
				"w2_applied", "w2_applied_stock_entry", "w2_applied_on"],
		order_by="creation desc",
	)
	if not sheets:
		return []

	# Who holds pieces of each sheet. Counted from the mapping rows themselves for
	# the reason given in the module docstring.
	holders = {}
	for c in frappe.get_all(
		"Material Planning Material Mapping",
		filters={"cut_sheet_ref": ["in", [s.name for s in sheets]], "is_reserved": 1},
		fields=["parent", "cut_sheet_ref", "batch_sec_qty", "batch_calc_qty",
				"duno_mark_no", "sales_order"],
	):
		holders.setdefault(c.cut_sheet_ref, []).append(c)

	today = getdate(nowdate())
	data = []
	for s in sheets:
		claims = holders.get(s.name, [])
		allocated_sec = flt(sum(flt(c.batch_sec_qty) for c in claims), 3)
		allocated_kg = flt(sum(flt(c.batch_calc_qty) for c in claims), 3)
		available_sec = flt(flt(s.w1_sec_qty) - allocated_sec, 3)

		if status == "Has Free Pieces" and available_sec <= 0.001:
			continue
		if status == "Fully Allocated" and available_sec > 0.001:
			continue
		if filters.get("material_planning") and not any(
			c.parent == filters["material_planning"] for c in claims
		):
			continue

		# Named, not counted: chasing a plate is about knowing which jobs are waiting.
		mp_list = ", ".join(sorted({
			c.parent + (" (" + c.duno_mark_no + ")" if c.duno_mark_no else "")
			for c in claims
		}))

		data.append({
			"cut_sheet": s.name,
			"cut_status": s.status,
			"company": s.company,
			"item_code": s.item_code,
			"item_name": s.item_name,
			"parent_item_group": s.parent_item_group,
			"batch_no": s.batch_no,
			"warehouse": s.warehouse,
			"created_on": getdate(s.creation),
			"age_days": (today - getdate(s.creation)).days,
			"sheet_length": flt(s.sheet_length),
			"sheet_width": flt(s.sheet_width),
			"sheet_thickness": flt(s.sheet_thickness),
			"sheet_qty": flt(s.sheet_qty),
			"w1_length": flt(s.w1_length),
			"w1_width": flt(s.w1_width),
			"w1_qty_per_nos": flt(s.w1_qty_per_nos),
			"w1_sec_qty": flt(s.w1_sec_qty),
			"w1_total_qty": flt(s.w1_total_qty),
			"allocated_sec_qty": allocated_sec,
			"allocated_kg": allocated_kg,
			"available_sec_qty": available_sec,
			"available_kg": flt(available_sec * flt(s.w1_qty_per_nos), 3),
			"holder_count": len(claims),
			"material_plannings": mp_list,
			"w2_length": flt(s.w2_length),
			"w2_width": flt(s.w2_width),
			"w2_sec_qty": flt(s.w2_sec_qty),
			"w2_calc_qty": flt(s.w2_calc_qty),
			"w2_applied": 1 if s.w2_applied else 0,
			"w2_applied_stock_entry": s.w2_applied_stock_entry,
			"w2_applied_on": s.w2_applied_on,
		})

	data.sort(key=lambda d: (-d["age_days"], d["cut_sheet"]))
	return data


def get_columns():
	return [
		{"label": _("Cut Sheet"), "fieldname": "cut_sheet", "fieldtype": "Link", "options": "Cut Sheet", "width": 130},
		{"label": _("Status"), "fieldname": "cut_status", "fieldtype": "Data", "width": 120},
		{"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 210},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Item Group"), "fieldname": "parent_item_group", "fieldtype": "Data", "width": 100},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 140},
		{"label": _("Created"), "fieldname": "created_on", "fieldtype": "Date", "width": 100},
		{"label": _("Age (days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 90},

		{"label": _("Sheet L (mm)"), "fieldname": "sheet_length", "fieldtype": "Float", "width": 105},
		{"label": _("Sheet W (mm)"), "fieldname": "sheet_width", "fieldtype": "Float", "width": 105},
		{"label": _("Sheet T (mm)"), "fieldname": "sheet_thickness", "fieldtype": "Float", "width": 105},
		{"label": _("Sheet (Kg)"), "fieldname": "sheet_qty", "fieldtype": "Float", "width": 100},

		{"label": _("W1 L (mm)"), "fieldname": "w1_length", "fieldtype": "Float", "width": 95},
		{"label": _("W1 W (mm)"), "fieldname": "w1_width", "fieldtype": "Float", "width": 95},
		{"label": _("Kg per Piece"), "fieldname": "w1_qty_per_nos", "fieldtype": "Float", "width": 110},
		{"label": _("W1 NOS"), "fieldname": "w1_sec_qty", "fieldtype": "Float", "width": 100},
		{"label": _("W1 Total (Kg)"), "fieldname": "w1_total_qty", "fieldtype": "Float", "width": 110},

		{"label": _("Allocated NOS"), "fieldname": "allocated_sec_qty", "fieldtype": "Float", "width": 130},
		{"label": _("Allocated (Kg)"), "fieldname": "allocated_kg", "fieldtype": "Float", "width": 115},
		{"label": _("Free NOS"), "fieldname": "available_sec_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Free (Kg)"), "fieldname": "available_kg", "fieldtype": "Float", "width": 100},
		{"label": _("Jobs"), "fieldname": "holder_count", "fieldtype": "Int", "width": 60},
		{"label": _("Allocated To (Material Planning)"), "fieldname": "material_plannings", "fieldtype": "Data", "width": 280},

		{"label": _("W2 L (mm)"), "fieldname": "w2_length", "fieldtype": "Float", "width": 95},
		{"label": _("W2 W (mm)"), "fieldname": "w2_width", "fieldtype": "Float", "width": 95},
		{"label": _("W2 NOS"), "fieldname": "w2_sec_qty", "fieldtype": "Float", "width": 100},
		{"label": _("W2 Balance (Kg)"), "fieldname": "w2_calc_qty", "fieldtype": "Float", "width": 120},
		{"label": _("W2 Written"), "fieldname": "w2_applied", "fieldtype": "Check", "width": 90},
		{"label": _("Written By"), "fieldname": "w2_applied_stock_entry", "fieldtype": "Link", "options": "Stock Entry", "width": 140},
		{"label": _("Written On"), "fieldname": "w2_applied_on", "fieldtype": "Datetime", "width": 150},
	]
