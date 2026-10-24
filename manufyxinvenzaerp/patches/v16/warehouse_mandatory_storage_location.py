"""Move "Storage Location is mandatory" from the Warehouse Type onto each Warehouse
(client, 23 Oct 2026). Every warehouse whose type had Storage Location Applicable gets
Mandatory Storage Location ticked, so nothing changes on the day this lands."""

import frappe

from manufyxinvenzaerp.setup import create_warehouse_storage_location_field


def execute():
	create_warehouse_storage_location_field()
	if not frappe.db.has_column("Warehouse Type", "custom_storage_location_applicable"):
		return
	types = frappe.get_all("Warehouse Type", filters={"custom_storage_location_applicable": 1}, pluck="name")
	for warehouse in frappe.get_all("Warehouse", filters={"warehouse_type": ["in", types]}, pluck="name") if types else []:
		frappe.db.set_value("Warehouse", warehouse, "custom_mandatory_storage_location", 1, update_modified=False)
