"""BOM override: ERPNext's BOM with five changes, and nothing else.

This used to be a full copy of ERPNext v15's bom.py (1,655 lines). A copy goes stale
the day it is taken -- it had already missed v15's per-operation costing -- and on v16
it would not even import, because `BOM Scrap Item` became `BOM Secondary Item` and
`stock_entry.get_operating_cost_per_unit` was removed. So only the methods we actually
change are overridden here; everything else is inherited from ERPNext.

Each override below is ERPNext v16's method, copied, with our change applied and marked
"manufyx:". When upgrading ERPNext, re-copy each one from the new bom.py and re-apply
the marked lines -- do not copy the whole file again.

  1. before_insert         -- new BOMs default to operations + Standard Manufacturing Routing
  2. set_bom_material_details -- never auto-link sub-BOMs (flat BOM only)
  3. manage_default_bom    -- no Item ever carries a default BOM
  4. calculate_rm_cost     -- BOMs made by BOM Creator keep their own rates
  5. get_exploded_items    -- exploded rows carry Length / Width / Thickness
"""

import frappe
from frappe.utils import flt

from erpnext.manufacturing.doctype.bom.bom import BOM as ERPNextBOM

# Module-level functions and classes of ERPNext's bom.py, re-exported so any dotted path
# that ever pointed here keeps resolving. The BOM form and tree view call ERPNext's own
# copies (erpnext.manufacturing.doctype.bom.bom.*), not these.
from erpnext.manufacturing.doctype.bom.bom import (  # noqa: F401
	BOMRecursionError,
	BOMTree,
	add_additional_cost,
	add_non_stock_items_cost,
	add_operations_cost,
	get_bom_diff,
	get_bom_item_rate,
	get_bom_items,
	get_bom_items_as_dict,
	get_children,
	get_list_context,
	get_op_cost_from_sub_assemblies,
	get_valuation_rate,
	item_query,
	make_variant_bom,
	validate_bom_no,
)


class BOM(ERPNextBOM):
	def before_insert(self):
		parent = getattr(super(), "before_insert", None)
		if parent:
			parent()
		# manufyx: every BOM here is routed; default it rather than make users tick it.
		if not self.with_operations:
			self.with_operations = 1
		if not self.routing:
			self.routing = "Standard Manufacturing Routing"

	def set_bom_material_details(self):
		for item in self.get("items"):
			self.validate_bom_currency(item)

			if item.do_not_explode:
				item.bom_no = ""

			ret = self.get_bom_material_detail(
				{
					"company": self.company,
					"item_code": item.item_code,
					"item_name": item.item_name,
					"bom_no": item.bom_no,
					"stock_qty": item.stock_qty,
					"include_item_in_manufacturing": item.include_item_in_manufacturing,
					"qty": item.qty,
					"uom": item.uom,
					"stock_uom": item.stock_uom,
					"conversion_factor": item.conversion_factor,
					"sourced_by_supplier": item.sourced_by_supplier,
					"do_not_explode": item.do_not_explode,
					"source_warehouse": item.source_warehouse or self.default_source_warehouse,
					"fetch_rate": True,
				}
			)

			for r in ret:
				if r == "bom_no":
					continue  # manufyx: never auto-link sub-BOMs; flat BOM structure only
				if not item.get(r):
					item.set(r, ret[r])

	def manage_default_bom(self):
		"""No item here has a default BOM, and none ever gets one.

		Stock ERPNext assumes one BOM per item, so it nominates a default and writes it
		onto the Item -- and every Sales Order line for that item then arrives carrying
		that BOM. In this app an item is a shape of steel, not a product: FINGOODS001
		alone has hundreds of BOMs, one per drawing, and which one applies is decided by
		the drawing, never by the item. Nominating one of them means every Sales Order
		line starts with an arbitrary drawing's BOM attached.

		It also breaks outright the moment that BOM goes: a Sales Order refuses to open
		with "Could not find Row #1: BOM No: BOM-FINGOODS001-245" when the Item still
		points at a BOM that has been deleted.

		So the flag is kept clear on the BOM and the field kept empty on the Item. The
		method still runs everywhere it used to -- ERPNext calls it on submit, on cancel
		and on update after submit -- because leaving it out would let a value set by
		some other route survive. Restoring stock behaviour means deleting this override;
		ERPNext's version lives in erpnext/manufacturing/doctype/bom/bom.py."""
		if self.is_default:
			self.db_set("is_default", 0)
		if frappe.db.get_value("Item", self.item, "default_bom"):
			frappe.db.set_value("Item", self.item, "default_bom", None)

	def calculate_rm_cost(self, save=False):
		"""Fetch RM rate as per today's valuation rate and calculate totals"""

		total_rm_cost = 0
		base_total_rm_cost = 0

		for d in self.get("items"):
			old_rate = d.rate
			# manufyx: a BOM made by BOM Creator keeps the rates it was created with.
			if not self.bom_creator and (d.is_stock_item or d.is_phantom_item):
				d.rate = self.get_rm_rate(
					{
						"company": self.company,
						"item_code": d.item_code,
						"bom_no": d.bom_no,
						"qty": d.qty,
						"uom": d.uom,
						"stock_uom": d.stock_uom,
						"conversion_factor": d.conversion_factor,
						"sourced_by_supplier": d.sourced_by_supplier,
						"is_phantom_item": d.is_phantom_item,
						"source_warehouse": d.source_warehouse or self.default_source_warehouse,
					},
					notify=False,
				)

			d.base_rate = flt(d.rate) * flt(self.conversion_rate)
			d.amount = flt(
				flt(d.rate, d.precision("rate")) * flt(d.qty, d.precision("qty")), d.precision("amount")
			)
			d.base_amount = d.amount * flt(self.conversion_rate)
			d.qty_consumed_per_unit = flt(d.stock_qty, d.precision("stock_qty")) / flt(
				self.quantity, self.precision("quantity")
			)

			total_rm_cost += d.amount
			base_total_rm_cost += d.base_amount
			if save and (old_rate != d.rate):
				d.db_update()

		self.raw_material_cost = total_rm_cost
		self.base_raw_material_cost = base_total_rm_cost

	def get_exploded_items(self):
		"""Get all raw materials including items from child bom"""
		self.cur_exploded_items = {}
		for d in self.get("items"):
			if d.bom_no:
				self.get_child_exploded_items(d.bom_no, d.stock_qty, d.operation)
			elif d.item_code:
				self.add_to_cur_exploded_items(
					frappe._dict(
						{
							"item_code": d.item_code,
							"item_name": d.item_name,
							"operation": d.operation,
							"is_sub_assembly_item": d.is_sub_assembly_item,
							"source_warehouse": d.source_warehouse,
							"description": d.description,
							"image": d.image,
							"stock_uom": d.stock_uom,
							"stock_qty": flt(d.stock_qty),
							"rate": flt(d.base_rate) / (flt(d.conversion_factor) or 1.0),
							"include_item_in_manufacturing": d.include_item_in_manufacturing,
							"sourced_by_supplier": d.sourced_by_supplier,
							# manufyx: the cut size travels with the row.
							"custom_thickness": d.custom_thickness,
							"custom_length": d.custom_length,
							"custom_width": d.custom_width,
						}
					)
				)
