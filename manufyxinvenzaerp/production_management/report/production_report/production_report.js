// Copyright (c) 2026, Manufyxinvenza and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Production Report"] = {
	filters: [
		{
			fieldname: "production_plan",
			label: __("Production Plan (Team)"),
			fieldtype: "Link",
			options: "Production Plan",
		},
		{
			fieldname: "job_type",
			label: __("Job Type"),
			fieldtype: "Select",
			options: "\nInternal Job\nSupplier Job\nSupplier with Material",
		},
		{
			fieldname: "subcontracting_order",
			label: __("Job Work Order"),
			fieldtype: "Link",
			options: "Subcontracting Order",
		},
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
		},
		{
			// Narrows which operation column blocks appear, rather than which rows do:
			// the report is one row per drawing now, and an operation is a set of
			// columns on it.
			fieldname: "operation",
			label: __("Operation"),
			fieldtype: "Link",
			options: "Operation",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nOpen\nIn Progress\nCompleted",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],

	// Negative waste is not a small number, it is an impossible one: the plan holds
	// less material than the finished part weighs, so the part cannot be cut from it.
	// Worth seeing at a glance rather than hunting for in a column of decimals.
	formatter(value, row, column, data, default_formatter) {
		// The total row is built by the report, not by Frappe (whose total would add up
		// every rate and percentage), so its "Total" sits in the Sales Order column --
		// shown as plain text here, not as a link to a Sales Order called "Total".
		var is_total = data && data.is_total_row;
		if (is_total && column.fieldname === "sales_order") {
			return "<b>" + frappe.utils.escape_html(value || "") + "</b>";
		}
		var formatted = default_formatter(value, row, column, data);
		if (column.fieldname === "waste_pct" && value !== null && value !== undefined) {
			if (value < 0) {
				formatted = "<span style='color:var(--red-500,#e24c4c);font-weight:600'>" + formatted + "</span>";
			}
		}
		if (is_total && value !== null && value !== undefined && value !== "") {
			formatted = "<b>" + formatted + "</b>";
		}
		return formatted;
	},
};
