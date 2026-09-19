// Stock Reconciliation: blocked on this site (sep14 FG plan, D21).
//
// The inventory is fully customised (dimensions, Sec Qty on batches, one finished-
// goods batch per drawing with its Nos per warehouse) and a reconciliation rewrites
// the Kg without any of that. The form says so and cannot be saved; the server
// (stock_management/stock_reconciliation.py) refuses regardless, with the same words.

const SR_BLOCKED_MESSAGE = __(
	"As the inventory module is completely customized, Stock Reconciliation cannot be used. Instead, use a Stock Entry of type Material Issue to remove the product from inventory, then a Material Receipt to add the updated stock."
);

frappe.ui.form.on("Stock Reconciliation", {
	onload(frm) {
		// Said once, up front, before anyone spends time filling rows in.
		frappe.msgprint({
			title: __("Stock Reconciliation Not Used"),
			message: SR_BLOCKED_MESSAGE,
			indicator: "red",
		});
	},

	refresh(frm) {
		frm.disable_save();
		frm.set_intro(SR_BLOCKED_MESSAGE, "red");
	},
});
