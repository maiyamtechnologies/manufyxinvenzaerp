"""Verify Phase 0.4/4.1 core fix: a purely Internal-Jobcard Production Plan
(no Subcontractor rows, no vendor/contractor) can now create a Subcontracting
Order -- previously create_sco_from_production_plan hard-threw "No Subcontractor
operations found" for such plans, which would have left Internal Job plans with
no create path at all once Work Order was removed.

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_internal_job_sco.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties


def run():
	company = frappe.db.get_value("Company", {}, "name")
	bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1}, ["name", "item", "quantity"], as_dict=True)
	print("company=", company, "bom=", bom)
	if not bom:
		print("No active submitted BOM found on this site -- cannot run this check.")
		return

	stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos"

	pp = frappe.new_doc("Production Plan")
	pp.custom_type = "Internal Job"
	pp.company = company
	pp.posting_date = frappe.utils.today()
	pp.get_items_from = ""
	pp.append("po_items", {
		"item_code": bom.item,
		"bom_no": bom.name,
		"planned_qty": bom.quantity or 1,
		"stock_uom": stock_uom,
	})
	pp.append("custom_process_planning", {"operation_name": "Fit-up", "work_type": "Internal Jobcard"})
	pp.append("custom_process_planning", {"operation_name": "Welding", "work_type": "Internal Jobcard"})
	pp.insert(ignore_permissions=True)
	fill_process_planning_parties(pp)
	pp.submit()
	print("Internal-Job Production Plan created+submitted:", pp.name)

	from manufyxinvenzaerp.subcontracting_management.subcontracting import (
		create_sco_from_production_plan,
		_create_soes_for_sco,
	)

	sco_name = create_sco_from_production_plan(pp.name)
	print("Subcontracting Order created for Internal-Job-only plan:", sco_name)

	sco = frappe.get_doc("Subcontracting Order", sco_name)
	print("SCO supplier (should be blank):", repr(sco.supplier))

	soe_names = _create_soes_for_sco(sco)
	print("SOEs created:", soe_names)
	for n in soe_names:
		soe = frappe.get_doc("Supplier Operation Entry", n)
		print(" ", n, "| operation=", soe.operation, "| supplier=", repr(soe.supplier),
			"| supplier_warehouse=", repr(soe.supplier_warehouse))

	frappe.db.commit()
	print("ALL CHECKS DONE")
