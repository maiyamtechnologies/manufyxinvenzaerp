"""One-off migration: move Custom Field / Property Setter fixtures to per-doctype
custom/<doctype>.json files via frappe.modules.utils.export_customizations — the
same whitelisted function Customize Form's "Export Customizations" button calls.

Run: bench --site manufact.local execute manufyxinvenzaerp.tests.move_fixtures_to_custom_json.run

Verified 2026-08-18: bench migrate synced all 112 files cleanly, no errors; DB counts
unchanged before/after (848 Custom Field, 337 Property Setter).
"""

import os

import frappe
from frappe import scrub
from frappe.modules.utils import export_customizations

# Only registered Module Def / modules.txt modules can own a custom/ folder that
# bench migrate will actually sync (see modules.txt). Map doctypes this app's own
# code/docs identify as owned to their matching module; everything else (fields
# belonging to other installed apps like hrms/india_compliance, or core doctypes
# with ad hoc customizations) falls back to the app's own catch-all module.
DEFAULT_MODULE = "Manufyxinvenzaerp"

MODULE_MAP = {
	# Drawing Management — BOM/Drawing/Sales Order family
	"BOM": "Drawing Management",
	"BOM Item": "Drawing Management",
	"BOM Explosion Item": "Drawing Management",
	"Drawing": "Drawing Management",
	"Drawing Item": "Drawing Management",
	"Sales Order": "Drawing Management",
	"Sales Order Item": "Drawing Management",
	# Production Management — planning/production/stock family
	"Material Planning": "Production Management",
	"Material Planning Available Raw Material": "Production Management",
	"Material Planning Material Mapping": "Production Management",
	"Material Planning Consolidate Item": "Production Management",
	"Production Plan": "Production Management",
	"Production Plan Item": "Production Management",
	"Production Plan Available Raw Material": "Production Management",
	"Production Plan BOM Raw Material": "Production Management",
	"Job Card": "Production Management",
	"Work Order": "Production Management",
	"Stock Entry": "Production Management",
	"Stock Entry Detail": "Production Management",
	"Manufacturing Settings": "Production Management",
	"Inspection Entry": "Production Management",
	# Subcontracting Management
	"Subcontracting Order": "Subcontracting Management",
	"Subcontracting Order Item": "Subcontracting Management",
	"Subcontracting Receipt": "Subcontracting Management",
	"Subcontracting Receipt Item": "Subcontracting Management",
	"Subcontracting Receipt Supplied Item": "Subcontracting Management",
	"Supplier Operation Entry": "Subcontracting Management",
	"Supplier Operation Item": "Subcontracting Management",
	"SOE Drawing Detail": "Subcontracting Management",
	"Material Issue Plan": "Subcontracting Management",
	# Accounts Management
	"Payment Entry": "Accounts Management",
}


def _all_target_doctypes():
	cf_dt = frappe.db.sql_list("select distinct dt from `tabCustom Field`")
	ps_dt = frappe.db.sql_list("select distinct doc_type from `tabProperty Setter`")
	return sorted(set(cf_dt) | set(ps_dt))


def run():
	doctypes = _all_target_doctypes()
	frappe.flags.in_import = False  # export_customizations checks conf.developer_mode only

	created = []
	skipped = []
	for doctype in doctypes:
		module = MODULE_MAP.get(doctype, DEFAULT_MODULE)
		path = export_customizations(module=module, doctype=doctype, sync_on_migrate=True, with_permissions=False)
		if path:
			created.append((doctype, module, path))
		else:
			skipped.append(doctype)

	print(f"\n{len(doctypes)} doctypes considered")
	print(f"{len(created)} custom/*.json files written")
	for doctype, module, path in created:
		print(f"  - {doctype!r:45s} -> {module:25s} {path}")

	if skipped:
		print(f"\n{len(skipped)} doctypes had no custom fields/property setters at export time (skipped):")
		for d in skipped:
			print(f"  - {d}")

	# Recursion into child tables (export_customizations walks each doctype's own
	# table fields using the SAME module as the parent) can write a doctype's
	# custom/<x>.json into a module other than the one this script assigned it to
	# explicitly. Since every doctype above already got its own explicit,
	# canonical call, remove any stray duplicate that a recursive parent call
	# dropped into a different module folder.
	removed = []
	canonical = {d: MODULE_MAP.get(d, DEFAULT_MODULE) for d in doctypes}
	all_modules = {MODULE_MAP.get(d, DEFAULT_MODULE) for d in doctypes} | {DEFAULT_MODULE}
	for module in all_modules:
		folder = os.path.join(frappe.get_module_path(module), "custom")
		if not os.path.isdir(folder):
			continue
		for fname in os.listdir(folder):
			if not fname.endswith(".json"):
				continue
			fpath = os.path.join(folder, fname)
			import json

			with open(fpath) as f:
				data = json.load(f)
			dt = data.get("doctype")
			if dt and dt in canonical and canonical[dt] != module:
				os.remove(fpath)
				removed.append((dt, module, canonical[dt]))

	if removed:
		print(f"\n{len(removed)} stray recursion-created duplicates removed (kept canonical module only):")
		for dt, wrong_module, right_module in removed:
			print(f"  - {dt!r:45s} removed from {wrong_module:25s} (kept in {right_module})")
