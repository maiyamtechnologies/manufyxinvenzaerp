"""Hand India Compliance's own custom fields back to India Compliance.

Our <module>/custom/*.json files used to carry 468 fields that belong to India
Compliance (module GST India / Income Tax India / Audit Trail) -- Customize Form's
export takes every custom field on a doctype, not just ours. `sync_customizations`
then rewrote them on every migrate with a snapshot taken years of IC releases ago:
HSN Code back to Data (IC made it Autocomplete), e-Waybill transport fields no longer
editable after submit, currency options blanked, and the Tax Category fields IC had
deliberately deleted re-created.

Those fields are gone from our JSON now, so nothing overwrites them again. This puts
back what IC itself defines, once, by calling IC's own creators -- they update an
existing field in place and never delete anything.
"""

import frappe


def execute():
	if "india_compliance" not in frappe.get_installed_apps():
		return

	from india_compliance.audit_trail.setup import create_custom_fields as create_audit_trail_fields
	from india_compliance.gst_india.setup import create_custom_fields as create_gst_fields
	from india_compliance.income_tax_india.setup import create_custom_fields as create_income_tax_fields

	create_gst_fields()
	create_income_tax_fields()
	create_audit_trail_fields()
