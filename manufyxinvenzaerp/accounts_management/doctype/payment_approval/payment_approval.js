// Copyright (c) 2026, Manufyxinvenza and Contributors
// License: GNU General Public License v3. See license.txt

const PA_METHOD = "manufyxinvenzaerp.accounts_management.doctype.payment_approval.payment_approval";
const PA_APPROVED = "✔ Approved";
const PA_REJECTED = "✖ Rejected";

function pa_refresh_fund_usage(frm) {
	if (!frm.doc.source_of_funds) {
		["total_customer_payment", "already_used_amount", "balance_amount"].forEach((f) => frm.set_value(f, 0));
		frm.set_value("customer_payment_date", null);
		return;
	}
	frappe.call({
		method: `${PA_METHOD}.get_fund_usage`,
		args: { payment_entry: frm.doc.source_of_funds, payment_approval: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			frm.set_value("total_customer_payment", r.message.total_customer_payment);
			frm.set_value("customer_payment_date", r.message.customer_payment_date);
			frm.set_value("already_used_amount", r.message.already_used_amount);
			frm.set_value("balance_amount", r.message.balance_amount);
		},
	});
}

function pa_act(frm, verb) {
	const approving = verb === "approve";
	const fields = [{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text", reqd: 1 }];
	if (approving) {
		fields.unshift({
			fieldname: "approved_amount",
			label: __("Approved Amount"),
			fieldtype: "Currency",
			reqd: 1,
			default: frm.doc.approved_amount || frm.doc.requested_amount,
			description: __("Cannot exceed the requested amount ({0})", [format_currency(frm.doc.requested_amount)]),
		});
	}
	frappe.prompt(
		fields,
		(values) => {
			frappe.call({
				method: `${PA_METHOD}.${verb}`,
				args: { name: frm.doc.name, remarks: values.remarks, approved_amount: values.approved_amount },
				freeze: true,
				callback: () => frm.reload_doc(),
			});
		},
		approving ? __("Approve Payment") : __("Reject Payment"),
		approving ? __("Approve") : __("Reject")
	);
}

function pa_account_filters(frm, kind) {
	return kind === "bank"
		? { company: frm.doc.company, account_type: ["in", ["Bank", "Cash"]], is_group: 0 }
		: { company: frm.doc.company, is_group: 0 };
}

// Payment Details are not needed to approve, only from submit onwards. This collects the
// missing ones in a dialog (prefilled from the Mode of Payment / party defaults) and
// hands the result to `done`.
function pa_ask_payment_details(frm, done) {
	const d = new frappe.ui.Dialog({
		title: __("Payment Details"),
		fields: [
			{
				fieldname: "mode_of_payment",
				label: __("Mode of Payment"),
				fieldtype: "Link",
				options: "Mode of Payment",
				reqd: 1,
				default: frm.doc.mode_of_payment,
				onchange() {
					const mop = d.get_value("mode_of_payment");
					if (!mop) return;
					frappe.call({
						method: `${PA_METHOD}.get_payment_defaults`,
						args: { company: frm.doc.company, party_type: frm.doc.party_type, party: frm.doc.party, mode_of_payment: mop },
						callback(r) {
							const m = r.message || {};
							d.set_value("paid_from", m.paid_from || "");
							if (!d.get_value("party_account")) d.set_value("party_account", m.party_account || "");
						},
					});
				},
			},
			{
				fieldname: "paid_from",
				label: __("Paid From (Bank / Cash Account)"),
				fieldtype: "Link",
				options: "Account",
				reqd: 1,
				default: frm.doc.paid_from,
				get_query: () => ({ filters: pa_account_filters(frm, "bank") }),
			},
			{
				fieldname: "party_account",
				label: __("Party Account"),
				fieldtype: "Link",
				options: "Account",
				reqd: 1,
				default: frm.doc.party_account,
				get_query: () => ({ filters: pa_account_filters(frm, "party") }),
			},
		],
		primary_action_label: __("Continue"),
		primary_action(values) {
			d.hide();
			done(values);
		},
	});
	d.show();
	// Prefill the blanks from defaults even when a Mode of Payment is already stored.
	if (frm.doc.mode_of_payment || !frm.doc.party_account) {
		frappe.call({
			method: `${PA_METHOD}.get_payment_defaults`,
			args: { company: frm.doc.company, party_type: frm.doc.party_type, party: frm.doc.party, mode_of_payment: frm.doc.mode_of_payment },
			callback(r) {
				const m = r.message || {};
				if (!d.get_value("paid_from")) d.set_value("paid_from", m.paid_from || "");
				if (!d.get_value("party_account")) d.set_value("party_account", m.party_account || "");
			},
		});
	}
}

function pa_payment_details_missing(doc) {
	return !(doc.mode_of_payment && doc.paid_from && doc.party_account);
}

function pa_has_approval_activity(doc) {
	return [1, 2, 3].some((n) => [PA_APPROVED, PA_REJECTED].includes(doc[`approver_${n}_status`]));
}

frappe.ui.form.on("Payment Approval", {
	setup(frm) {
		frm.set_query("paid_from", () => ({ filters: pa_account_filters(frm, "bank") }));
		frm.set_query("party_account", () => ({ filters: pa_account_filters(frm, "party") }));
		["approver_1", "approver_2", "approver_3"].forEach((f) => {
			frm.set_query(f, () => ({ query: `${PA_METHOD}.director_query` }));
		});
		frm.set_query("source_of_funds", () => ({ query: `${PA_METHOD}.payment_entry_query` }));
		frm.set_query("purchase_order", () => ({ filters: { supplier: frm.doc.party, docstatus: 1 } }));
		frm.set_query("purchase_invoice", () => ({ filters: { supplier: frm.doc.party, docstatus: 1 } }));
		frm.set_query("sales_order", () => (frm.doc.party_type === "Customer" ? { filters: { customer: frm.doc.party, docstatus: 1 } } : {}));
	},

	onload(frm) {
		if (frm.is_new()) {
			frm.set_value("requested_by", frappe.session.user);
		}
	},

	refresh(frm) {
		const doc = frm.doc;
		if (frm.is_new()) return;
		if (!frm.is_dirty()) frm._pa_saved_amount = doc.requested_amount;

		if (doc.docstatus === 0 && !frm.is_dirty()) {
			const slots = [1, 2, 3].filter((n) => doc[`approver_${n}`] === frappe.session.user);
			const my_turn = slots.some((n) => !doc[`approver_${n}_status`] || doc[`approver_${n}_status`] === "Pending");

			if (my_turn && doc.status !== "Rejected") {
				frm.add_custom_button(__("Approve"), () => pa_act(frm, "approve")).addClass("btn-primary");
				frm.add_custom_button(__("Reject"), () => pa_act(frm, "reject"));
			}

			if (doc.status === "Approved") {
				// Every selected approver has approved: only now is Submit offered.
				frm.page.set_primary_action(__("Submit"), () => {
					if (!pa_payment_details_missing(doc)) return frm.savesubmit();
					pa_ask_payment_details(frm, (values) => {
						frm.set_value({
							mode_of_payment: values.mode_of_payment,
							paid_from: values.paid_from,
							party_account: values.party_account,
						}).then(() => frm.savesubmit());
					});
				});
			} else {
				frm.page.clear_primary_action();
			}

			if (doc.status === "Rejected" && frm.perm[0].write) {
				frm.add_custom_button(__("Reset Approvals"), () => {
					frappe.confirm(__("Clear all approvals and start again?"), () => {
						frappe.call({
							method: `${PA_METHOD}.reset_approvals`,
							args: { name: doc.name },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
					});
				});
			}

			const done = [1, 2, 3].filter((n) => doc[`approver_${n}`]).length;
			const approved = [1, 2, 3].filter((n) => doc[`approver_${n}_status`] === PA_APPROVED).length;
			if (doc.status === "Pending Approval") {
				frm.dashboard.set_headline_alert(
					__("{0} of {1} approvals received", [approved, done]),
					"orange"
				);
			} else if (doc.status === "Approved") {
				frm.dashboard.set_headline_alert(__("Fully approved — ready to submit"), "green");
			} else if (doc.status === "Rejected") {
				frm.dashboard.set_headline_alert(__("Rejected"), "red");
			}
		}

		if (doc.docstatus === 1 && doc.status === "Submitted") {
			const make_pe = () =>
				frappe.call({
					method: `${PA_METHOD}.make_payment_entry`,
					args: { name: doc.name },
					freeze: true,
					callback(r) {
						if (!r.exc && r.message) {
							frappe.model.sync(r.message);
							frappe.set_route("Form", r.message.doctype, r.message.name);
						}
					},
				});
			frm.add_custom_button(__("Create Payment Entry"), () => {
				if (!pa_payment_details_missing(doc)) return make_pe();
				// Submitted without Payment Details (older requests): ask now, then continue.
				pa_ask_payment_details(frm, (values) => {
					frappe.call({
						method: `${PA_METHOD}.save_payment_details`,
						args: { name: doc.name, ...values },
						freeze: true,
						callback(r) {
							if (!r.exc) frm.reload_doc().then(make_pe);
						},
					});
				});
			}).addClass("btn-primary");
		}
	},

	before_save(frm) {
		const doc = frm.doc;
		if (frm._pa_amount_decided) {
			frm._pa_amount_decided = false;
			return;
		}
		if (
			doc.docstatus !== 0 ||
			frm.is_new() ||
			frm._pa_saved_amount === undefined ||
			flt(doc.requested_amount) === flt(frm._pa_saved_amount) ||
			!pa_has_approval_activity(doc)
		) {
			return;
		}
		// Approvals were given for the old amount: ask what to do before saving.
		frappe.validated = false;
		frappe.confirm(
			__(
				"The Requested Amount changed from {0} to {1}.<br><br>Do you want to create the approval again for the users? " +
					"<b>Yes</b> saves the new amount and every approver must approve again. " +
					"<b>No</b> keeps the previous amount and the approvals already given.",
				[format_currency(frm._pa_saved_amount), format_currency(doc.requested_amount)]
			),
			() => {
				frm._pa_amount_decided = true;
				frm.save();
			},
			() => {
				frm.set_value("requested_amount", frm._pa_saved_amount).then(() => {
					frm._pa_amount_decided = true;
					frm.save();
				});
			}
		);
	},

	party_type(frm) {
		frm.set_value("party", null);
		frm.set_value("party_account", null);
		frm.set_value("source_of_funds", null);
		frm.set_value("purchase_order", null);
		frm.set_value("purchase_invoice", null);
	},

	party(frm) {
		if (!frm.doc.party || !frm.doc.party_type) return frm.set_value("party_name", null);
		const field = frm.doc.party_type.toLowerCase() + "_name";
		frappe.db.get_value(frm.doc.party_type, frm.doc.party, field).then((r) => {
			frm.set_value("party_name", (r.message || {})[field] || null);
		});
	},

	source_of_funds(frm) {
		pa_refresh_fund_usage(frm);
	},
});
