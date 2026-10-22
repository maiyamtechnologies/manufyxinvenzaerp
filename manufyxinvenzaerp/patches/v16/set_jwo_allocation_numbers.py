"""Give every existing Job Work Order's operations their JWO Allocation No. and their
Drawing Weight (client, 22 Oct 2026). New operations get both as they are created and
saved; this fills the ones raised before the fields existed.

Operation Start / End Date are not guessed for old operations: they fill in as each one
is next worked on, and can be typed on a completed one."""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.subcontracting_management.subcontracting import set_jwo_allocation_numbers


def execute():
	for sco_name in frappe.get_all(
		"Supplier Operation Entry", filters={"docstatus": ["!=", 2]}, pluck="subcontracting_order", distinct=True
	):
		if sco_name:
			set_jwo_allocation_numbers(sco_name)

	for parent, weight in frappe.db.sql(
		"""SELECT parent, SUM(customer_provided_weight_kg) FROM `tabSOE Drawing Detail`
		   WHERE parenttype = 'Supplier Operation Entry' GROUP BY parent"""
	):
		frappe.db.set_value("Supplier Operation Entry", parent, "drawing_weight_kg", flt(weight, 3),
							update_modified=False)
