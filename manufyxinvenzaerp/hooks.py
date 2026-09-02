app_name = "manufyxinvenzaerp"
app_title = "Manufyxinvenzaerp"
app_publisher = "Maiyamdev"
app_description = "Custom ERP application"
app_email = "prithivrajthangadurai@gmail.com"
app_license = "mit"

after_install = "manufyxinvenzaerp.setup.after_install"
after_migrate = "manufyxinvenzaerp.setup.after_migrate"

# Custom Field / Property Setter customizations moved to per-doctype
# <module>/custom/<doctype>.json files (frappe.modules.utils.export_customizations,
# sync_on_migrate=True on every file) — see manufyxinvenzaerp/*/custom/. No longer
# fixture-based.

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "manufyxinvenzaerp",
# 		"logo": "/assets/manufyxinvenzaerp/logo.png",
# 		"title": "Manufyxinvenzaerp",
# 		"route": "/manufyxinvenzaerp",
# 		"has_permission": "manufyxinvenzaerp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/manufyxinvenzaerp/css/manufyxinvenzaerp.css"
# app_include_js = "/assets/manufyxinvenzaerp/js/manufyxinvenzaerp.js"

# include js, css files in header of web template
# web_include_css = "/assets/manufyxinvenzaerp/css/manufyxinvenzaerp.css"
# web_include_js = "/assets/manufyxinvenzaerp/js/manufyxinvenzaerp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "manufyxinvenzaerp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# One content-hashed bundle rather than a list of bare /assets/... paths, so an
# edit to any of these files reaches browsers that cached the previous copy --
# see the header comment in public/js/manufyxinvenzaerp.bundle.js for what went
# wrong before. Add new app-wide scripts by importing them there, not here.
app_include_js = ["manufyxinvenzaerp.bundle.js"]
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

doctype_js = {
    "Production Plan": "public/js/production_plan.js",
    "BOM": "public/js/bom.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Receipt": "public/js/purchase_receipt.js",
    "Batch": "public/js/batch.js",
    "Supplier Operation Entry": "public/js/supplier_operation_entry.js",
    "Inspection Entry": "public/js/inspection_entry.js",
    "Payment Request": "public/js/payment_request.js",
}
# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "manufyxinvenzaerp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "manufyxinvenzaerp.utils.jinja_methods",
# 	"filters": "manufyxinvenzaerp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "manufyxinvenzaerp.install.before_install"
# after_install = "manufyxinvenzaerp.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "manufyxinvenzaerp.uninstall.before_uninstall"
# after_uninstall = "manufyxinvenzaerp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "manufyxinvenzaerp.utils.before_app_install"
# after_app_install = "manufyxinvenzaerp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "manufyxinvenzaerp.utils.before_app_uninstall"
# after_app_uninstall = "manufyxinvenzaerp.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "manufyxinvenzaerp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes
override_doctype_class = {
    "BOM": "manufyxinvenzaerp.drawing_management.bom_class_override.BOM",
    "Subcontracting Order": "manufyxinvenzaerp.subcontracting_management.overrides.CustomSubcontractingOrder",
    "Stock Entry": "manufyxinvenzaerp.subcontracting_management.overrides.CustomStockEntry",
}

# A decision log entry must never stop the document it describes from being deleted.
# Frappe refuses to delete anything a Link or Dynamic Link still points at, so
# without this a Cut Sheet became undeletable the moment its balance was recorded --
# an audit trail holding its own subject hostage. The entries survive the deletion
# and keep the name of what was deleted, which is what makes them worth reading.
ignore_links_on_delete = ["Manufyx Decision Log"]

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Item": {
		"validate": "manufyxinvenzaerp.item_management.item.validate_item",
	},
	"Sales Order": {
		"validate": "manufyxinvenzaerp.drawing_management.sales_order.recalculate_raw_material_qty",
	},
	"Purchase Order": {
		"validate": "manufyxinvenzaerp.purchase_order_management.purchase_order.validate_purchase_order",
		"before_submit": "manufyxinvenzaerp.purchase_order_management.purchase_order.before_submit_purchase_order",
	},
	"Purchase Receipt": {
		"validate": [
			"manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.validate_purchase_receipt",
			"manufyxinvenzaerp.production_management.inspection.validate_purchase_receipt_inspection",
		],
		"before_submit": "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.before_submit_purchase_receipt",
		"on_submit": "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.on_submit_purchase_receipt",
	},
	"Batch": {
		"before_insert": "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.before_insert_batch",
	},
	"BOM": {
		"validate": "manufyxinvenzaerp.drawing_management.drawing_utils.validate_bom_from_drawing",
	},
	"Material Request": {
		"validate": "manufyxinvenzaerp.material_request_management.material_request.validate_material_request",
		"before_submit": "manufyxinvenzaerp.material_request_management.material_request.before_submit_material_request",
		"on_cancel": "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.unlink_material_request_on_cancel",
		"on_trash": "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.unlink_material_request_on_cancel",
	},
	"Request for Quotation": {
		"validate": "manufyxinvenzaerp.rfq_management.request_for_quotation.validate_rfq",
	},
	"Supplier Quotation": {
		"validate": "manufyxinvenzaerp.sq_management.supplier_quotation.validate_supplier_quotation",
		"before_submit": "manufyxinvenzaerp.sq_management.supplier_quotation.before_submit_supplier_quotation",
	},
	# Work Order and Job Card carry no hooks from this app: they were reverted to
	# standard ERPNext under the client's Phase 0.4 change request, and
	# Subcontracting Order / Operation Entry do that work instead.
	"Stock Entry": {
		"validate": "manufyxinvenzaerp.production_management.stock_entry.validate_stock_entry",
		"on_submit": "manufyxinvenzaerp.production_management.stock_entry.on_submit_stock_entry",
		"on_cancel": "manufyxinvenzaerp.production_management.stock_entry.on_cancel_stock_entry",
	},
	"Supplier Operation Entry": {
		"validate": [
			"manufyxinvenzaerp.subcontracting_management.subcontracting.validate_supplier_operation_entry",
			"manufyxinvenzaerp.production_management.inspection.validate_soe_inspection",
		],
		"before_submit": [
			"manufyxinvenzaerp.subcontracting_management.subcontracting.before_submit_supplier_operation_entry",
			"manufyxinvenzaerp.production_management.inspection.before_submit_soe_inspection_gate",
		],
		"on_update": "manufyxinvenzaerp.subcontracting_management.subcontracting.on_update_supplier_operation_entry",
		"on_submit": "manufyxinvenzaerp.subcontracting_management.subcontracting.on_submit_supplier_operation_entry",
		"before_cancel": "manufyxinvenzaerp.subcontracting_management.subcontracting.before_cancel_supplier_operation_entry",
		"before_delete": "manufyxinvenzaerp.subcontracting_management.subcontracting.before_delete_supplier_operation_entry",
	},
	"Subcontracting Order": {
		"on_cancel": "manufyxinvenzaerp.subcontracting_management.subcontracting.on_cancel_subcontracting_order",
	},
	"Production Plan": {
		"autoname": "manufyxinvenzaerp.production_plan_management.production_plan.autoname_production_plan",
		"validate": [
			"manufyxinvenzaerp.production_plan_management.production_plan.after_save_production_plan",
			"manufyxinvenzaerp.production_plan_management.production_plan.validate_process_planning_contiguity",
		],
		"on_trash": "manufyxinvenzaerp.production_plan_management.production_plan.unlink_production_plan_on_trash",
		"on_cancel": "manufyxinvenzaerp.production_plan_management.production_plan.unlink_production_plan_on_trash",
	},
	"Inspection Entry": {
		"on_submit": "manufyxinvenzaerp.production_management.inspection.on_submit_inspection_entry",
	},
	"Payment Request": {
		"validate": "manufyxinvenzaerp.accounts_management.payment_request.validate_payment_request",
	},
	"Payment Entry": {
		"on_submit": "manufyxinvenzaerp.accounts_management.payment_entry.on_submit_payment_entry",
		"on_cancel": "manufyxinvenzaerp.accounts_management.payment_entry.on_cancel_payment_entry",
	},
}

override_doctype_dashboards = {
	"Sales Order": "manufyxinvenzaerp.drawing_management.drawing_utils.get_so_dashboard_data",
	"Subcontracting Order": "manufyxinvenzaerp.subcontracting_management.subcontracting.get_sco_dashboard_data",
}

# Scheduled Tasks
# ---------------

# This is the app's ONLY scheduled task, and it must not be relied on alone:
# sites/common_site_config.json on this bench sets "pause_scheduler": 1, so
# nothing registered here actually fires locally. refresh_overdue_gate_passes is
# therefore also called from the Delivery Challan list view's onload (see
# delivery_challan_list.js) and directly by the tests. This hook is what makes
# Overdue correct on a live server whose scheduler is running.
scheduler_events = {
	"daily": [
		"manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan.refresh_overdue_gate_passes"
	],
}

# scheduler_events = {
# 	"all": [
# 		"manufyxinvenzaerp.tasks.all"
# 	],
# 	"daily": [
# 		"manufyxinvenzaerp.tasks.daily"
# 	],
# 	"hourly": [
# 		"manufyxinvenzaerp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"manufyxinvenzaerp.tasks.weekly"
# 	],
# 	"monthly": [
# 		"manufyxinvenzaerp.tasks.monthly"
# 	],
# }

# Testing
# -------

# frappe.get_hooks("before_tests", app_name=app) only fires the hook registered by the
# app under test -- india_compliance's own before_tests (which sets
# frappe.flags.skip_test_records=True and seeds GST-compliant fixtures) never runs when
# testing this app, so frappe falls back to its generic test data. That generic data
# leaves Item Tax Template at india_compliance's own default (gst_treatment="Taxable",
# gst_rate=0), which india_compliance's own validation then rejects. Delegating to the
# same setup used when testing india_compliance directly avoids the conflict.
before_tests = "india_compliance.tests.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "manufyxinvenzaerp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "manufyxinvenzaerp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["manufyxinvenzaerp.utils.before_request"]
# after_request = ["manufyxinvenzaerp.utils.after_request"]

# Job Events
# ----------
# before_job = ["manufyxinvenzaerp.utils.before_job"]
# after_job = ["manufyxinvenzaerp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"manufyxinvenzaerp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

