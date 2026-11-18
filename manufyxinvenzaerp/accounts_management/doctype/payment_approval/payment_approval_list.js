frappe.listview_settings["Payment Approval"] = {
	add_fields: ["status", "approvals_received", "pending_with", "approver_1"],
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

	// Quick filters with live counts: what is waiting for me, what is waiting for anyone,
	// and what is approved but not yet submitted.
	onload(listview) {
		const dt = "Payment Approval";
		const me = frappe.session.user;
		const views = [
			{
				label: __("Pending My Approval"),
				filters: [
					[dt, "docstatus", "=", 0],
					[dt, "status", "=", "Pending Approval"],
					[dt, "pending_with", "like", `%${me}%`],
				],
			},
			{
				label: __("All Pending Approval"),
				filters: [
					[dt, "docstatus", "=", 0],
					[dt, "status", "=", "Pending Approval"],
				],
			},
			{
				label: __("Approved - Ready to Submit"),
				filters: [
					[dt, "docstatus", "=", 0],
					[dt, "status", "=", "Approved"],
				],
			},
		];
		// Counts first, then the buttons, so the label itself carries the number.
		Promise.all(
			views.map((v) => {
				const args = {};
				v.filters.forEach((f) => (args[f[1]] = f[2] === "like" ? ["like", f[3]] : f[3]));
				return frappe.db.count(dt, { filters: args }).catch(() => null);
			})
		).then((counts) => {
			views.forEach((v, i) => {
				const label = counts[i] === null ? v.label : `${v.label} (${counts[i]})`;
				listview.page.add_inner_button(
					label,
					() => listview.filter_area.clear(false).then(() => listview.filter_area.add(v.filters)),
					__("Show")
				);
			});
		});
	},
};
