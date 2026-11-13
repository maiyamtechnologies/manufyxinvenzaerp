frappe.listview_settings["Payment Approval"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colors = {
			Draft: "gray",
			"Pending Approval": "orange",
			Approved: "blue",
			Rejected: "red",
			Submitted: "purple",
			Paid: "green",
			Cancelled: "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
