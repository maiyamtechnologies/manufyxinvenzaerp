// Copyright (c) 2026, Manufyxinvenza and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Customer Fund Usage"] = {
	filters: [
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			// Narrows to the customer payments booked against this Sales Order, and
			// therefore to every supplier payment funded out of them -- the same shape
			// as the Customer filter above, which also selects wallets rather than
			// individual requests.
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
		},
		{
			fieldname: "source_of_funds",
			label: __("Source of Funds (Customer Payment Entry)"),
			fieldtype: "Link",
			options: "Payment Entry",
			get_query: function () {
				return {
					query: "manufyxinvenzaerp.accounts_management.doctype.payment_approval.payment_approval.payment_entry_query",
				};
			},
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Paid", "Unpaid"],
		},
		{
			fieldname: "group_by_customer_payment",
			label: __("Group by Customer Payment"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
