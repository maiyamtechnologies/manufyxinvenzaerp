// Copyright (c) 2026, Manufyxinvenza and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Excess Material Return Report"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "Pending Return\nPending\nReturned\nAll",
			default: "Pending Return",
			// "Pending Return" is the chase-list: still out there AND actually coming
			// back. It drops anything already returned, and anything flagged Retain at
			// Supplier, which by definition never returns. "Pending" keeps the old
			// behaviour of showing every unreturned row.
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "material_issue_plan",
			label: __("Material Issue Plan"),
			fieldtype: "Link",
			options: "Material Issue Plan",
		},
		{
			fieldname: "subcontracting_order",
			label: __("Subcontracting Order"),
			fieldtype: "Link",
			options: "Subcontracting Order",
		},
		{
			fieldname: "item_code",
			label: __("Item Code"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
		},
		{
			fieldname: "job_type",
			label: __("Job Type"),
			fieldtype: "Select",
			options: "\nInternal Job\nSupplier Job\nSupplier with Material",
		},
		{
			// Defaults to the last three months so the report opens on the question
			// it exists to answer: what was due back a while ago and never came.
			// Matched against the Material Issue Plan's posting date.
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
			reqd: 0,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 0,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// Highlight excess items pending return/claim for a while, so the
		// team notices ageing off-cuts without a separate notification
		// channel (client change request Phase 7.1).
		if (column.fieldname === "days_pending" && data && data.days_pending > 7) {
			value = `<span style="color:#e03131;font-weight:600;">${value}</span>`;
		}
		// An off-cut other jobs are already waiting on is the one worth chasing first.
		if (column.fieldname === "reserved_material_plannings" && data && data.reserved_count) {
			value = `<span style="color:#1971c2;">${value}</span>`;
		}
		return value;
	},
};
