"""Regression check for Phase 0.4/4.1 changes to create_sco_from_production_plan /
_create_soes_for_sco: confirm Subcontractor-row plans still work as before --
vendor/contractor still required when a Subcontractor row exists, supplier still
flows through to both the SCO and its Subcontractor-row SOEs, and a MIXED plan
(one Subcontractor + one Internal Jobcard row) creates SOEs with the right
supplier per row.

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_mixed_sco_regression.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties


def run():
	company = frappe.db.get_value("Company", {}, "name")
	bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1}, ["name", "item", "quantity"], as_dict=True)
	supplier = frappe.db.get_value("Supplier", {}, "name")
	stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos"
	print("company=", company, "bom=", bom, "supplier=", supplier)

	# 1) Subcontractor row but NO vendor/contractor -> should still throw
	pp1 = frappe.new_doc("Production Plan")
	pp1.custom_type = "Supplier Job"
	pp1.company = company
	pp1.posting_date = frappe.utils.today()
	pp1.get_items_from = ""
	pp1.append("po_items", {"item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1, "stock_uom": stock_uom})
	pp1.append("custom_process_planning", {"operation_name": "Fit-up", "work_type": "Subcontractor"})

	from manufyxinvenzaerp.subcontracting_management.subcontracting import (
		create_sco_from_production_plan,
		_create_soes_for_sco,
	)

	try:
		pp1.insert(ignore_permissions=True)
		print("ERROR: should have thrown for missing vendor/contractor")
	except frappe.exceptions.ValidationError as e:
		print("OK blocked missing vendor/contractor (at Production Plan save, pre-existing validation):", str(e)[:120])

	# 2) Mixed plan: Subcontractor + Internal Jobcard, WITH vendor/contractor set
	pp2 = frappe.new_doc("Production Plan")
	pp2.custom_type = "Supplier with Material"
	pp2.company = company
	pp2.posting_date = frappe.utils.today()
	pp2.get_items_from = ""
	pp2.custom_vendor_contractor = supplier
	pp2.append("po_items", {"item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1, "stock_uom": stock_uom})
	pp2.append("custom_process_planning", {"operation_name": "Fit-up", "work_type": "Subcontractor"})
	pp2.append("custom_process_planning", {"operation_name": "Welding", "work_type": "Internal Jobcard"})
	pp2.insert(ignore_permissions=True)
	fill_process_planning_parties(pp2)
	pp2.submit()

	sco_name = create_sco_from_production_plan(pp2.name)
	sco = frappe.get_doc("Subcontracting Order", sco_name)
	print("\nMixed plan SCO created:", sco_name, "| supplier:", sco.supplier)

	soe_names = _create_soes_for_sco(sco)
	for n in soe_names:
		soe = frappe.get_doc("Supplier Operation Entry", n)
		print(" ", n, "| operation=", soe.operation, "| supplier=", repr(soe.supplier))

	frappe.db.commit()
	print("\nALL CHECKS DONE")
