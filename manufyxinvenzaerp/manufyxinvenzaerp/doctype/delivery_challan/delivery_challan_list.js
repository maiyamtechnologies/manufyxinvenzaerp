// The Overdue flip is normally the daily scheduler's job, but this bench runs with
// "pause_scheduler": 1 in common_site_config.json -- so the sweep is fired here too,
// on every list load, and get_indicator derives Overdue live from expected_return_date
// so the colour is right even before that call returns.

frappe.listview_settings["Delivery Challan"] = {
	add_fields: ["status", "challan_type", "expected_return_date", "docstatus"],

	onload() {
		frappe.call({
			method: "manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan.refresh_overdue_gate_passes",
			callback(r) {
				if (r.message && cur_list) {
					cur_list.refresh();
				}
			},
		});
	},

	get_indicator(doc) {
		if (doc.docstatus === 2) return [__("Cancelled"), "darkgrey", "status,=,Cancelled"];
		if (doc.docstatus === 0) return [__("Draft"), "grey", "status,=,Draft"];

		const overdue =
			doc.challan_type === "Returnable" &&
			doc.status !== "Returned" &&
			doc.expected_return_date &&
			frappe.datetime.get_diff(doc.expected_return_date, frappe.datetime.get_today()) < 0;
		if (overdue) return [__("Overdue"), "red", "status,=,Overdue"];

		const colours = {
			"Material Out": "blue",
			"Material In": "blue",
			"Partially Returned": "orange",
			Returned: "green",
		};
		return [__(doc.status), colours[doc.status] || "grey", "status,=," + doc.status];
	},
};
