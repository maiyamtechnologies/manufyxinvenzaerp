# Copyright (c) 2026, Manufyxinvenza and Contributors
# License: GNU General Public License v3. See license.txt

"""Payment Approval -- an internal, multi-Director approval for paying a supplier or a customer.

Replaces the customizations that used to sit on the core Payment Request (Source of
Funds, Payment Type). Core Payment Request is left exactly as ERPNext ships it; it is
built around a Sales/Purchase document and a payment gateway, neither of which a plain
"please pay this party" request has.

Flow: the request names one Director as Approver 1 -> Approver 1 approves/rejects first
(Approve/Reject buttons, remarks mandatory) -> after that ANY other Director can approve
(the one who acts is recorded in the next free "other approver" slot) -> once Approver 1
and enough others have approved (minimum in Payment Approval Settings, Approver 1 counts)
the status becomes Approved and ANY Director (not only the requester) can submit ->
"Create Payment Entry" builds the Pay entry -> submitting that Payment Entry marks this
document Paid (see payment_entry.py).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

APPROVER_SLOTS = (1, 2, 3, 4)
OTHER_SLOTS = (2, 3, 4)  # filled by whichever other Director acts
ACCOUNTS_ROLES = {"System Manager", "Accounts Manager", "Accounts User"}
DIRECTOR_ROLE = "Director"

PENDING = "Pending"
APPROVED = "✔ Approved"
REJECTED = "✖ Rejected"
OTHERS_MATERIAL = "Others (to fill manually)"


class PaymentApproval(Document):
    # ------------------------------------------------------------------ helpers
    def selected_approvers(self):
        return [(n, self.get(f"approver_{n}")) for n in APPROVER_SLOTS if self.get(f"approver_{n}")]

    def slot_status(self, n):
        return self.get(f"approver_{n}_status") or PENDING

    def approved_count(self):
        return sum(1 for n, _u in self.selected_approvers() if self.slot_status(n) == APPROVED)

    def is_rejected(self):
        return any(self.slot_status(n) == REJECTED for n, _u in self.selected_approvers())

    def is_fully_approved(self):
        """Approver 1 has approved and, counting Approver 1, enough Directors have."""
        return (
            bool(self.approver_1)
            and self.slot_status(1) == APPROVED
            and self.approved_count() >= get_min_approvals()
        )

    def slot_of(self, user):
        return next((n for n, u in self.selected_approvers() if u == user), None)

    def free_slot(self):
        """Slot for a Director who is not yet on the document: the first empty one."""
        for n in OTHER_SLOTS:
            if not self.get(f"approver_{n}"):
                return n
        return next((n for n in OTHER_SLOTS if self.slot_status(n) == PENDING), None)

    @property
    def final_amount(self):
        return flt(self.approved_amount) or flt(self.requested_amount)

    def clear_slot(self, n):
        if n in OTHER_SLOTS:
            # Other slots only exist because a Director acted: clearing frees the slot.
            self.set(f"approver_{n}", None)
        self.set(f"approver_{n}_status", PENDING if self.get(f"approver_{n}") else None)
        self.set(f"approver_{n}_on", None)
        self.set(f"approver_{n}_remarks", None)

    # --------------------------------------------------------------- lifecycle
    def validate(self):
        self.company = self.company or frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
        if not self.requested_by:
            from manufyxinvenzaerp.accounts_management.doctype.payment_requested_by.payment_requested_by import (
                get_or_create_for_user,
            )

            self.requested_by = get_or_create_for_user(frappe.session.user)
        if self.docstatus == 0:
            self.protect_approval_fields()
            self.validate_approvers()
        self.validate_amounts()
        self.validate_references()
        self.validate_sales_order()
        self.set_party_name()
        self.set_payment_accounts()
        self.validate_payment_details()
        self.set_fund_usage()
        self.set_status()
        self.set_approval_summary()
        if not self.flags.approval_action:
            self.warn_fund_balance()

    def before_submit(self):
        if self.is_rejected():
            frappe.throw(_("This Payment Approval was rejected and cannot be submitted."))
        if not self.is_fully_approved():
            frappe.throw(
                _(
                    "Approver 1 and enough other Directors must approve before this can be submitted "
                    "({0} approved; {1} needed including Approver 1)."
                ).format(self.approved_count(), get_min_approvals()),
                title=_("Approval Pending"),
            )
        self.require_payment_details()
        if not flt(self.approved_amount):
            self.approved_amount = self.requested_amount

    def before_update_after_submit(self):
        # Frappe runs validate() only on drafts; the Payment Details stay editable after
        # submit (until paid), so they need the same checks here.
        if not (self.flags.ignore_permissions or ACCOUNTS_ROLES & set(frappe.get_roles())):
            frappe.throw(_("Only Accounts users can change a submitted Payment Approval."), frappe.PermissionError)
        self.set_payment_accounts()
        self.validate_payment_details()

    def on_submit(self):
        self.db_set("status", "Submitted")
        self.sync_assignments()

    def on_update(self):
        self.sync_assignments()

    def on_cancel(self):
        if self.payment_entry and frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus") != 2:
            frappe.throw(_("Cancel Payment Entry {0} first.").format(self.payment_entry))
        self.db_set("status", "Cancelled")
        self.sync_assignments()

    def on_trash(self):
        self.close_todos()

    # -------------------------------------------------------------- validation
    def validate_approvers(self):
        if not self.approver_1:
            frappe.throw(_("Approver 1 is required."))
        selected = self.selected_approvers()
        users = [u for _n, u in selected]
        if len(users) != len(set(users)):
            frappe.throw(_("The same user cannot be selected as approver more than once."))
        for n, user in selected:
            if DIRECTOR_ROLE not in frappe.get_roles(user):
                frappe.throw(_("Approver {0}: {1} does not have the {2} role.").format(n, user, DIRECTOR_ROLE))
        for n in APPROVER_SLOTS:
            if not self.get(f"approver_{n}"):
                self.clear_slot(n)
            elif not self.get(f"approver_{n}_status"):
                self.set(f"approver_{n}_status", PENDING)

    def protect_approval_fields(self):
        """Approval results may only be written by approve()/reject()/reset_approvals().
        Anything else (form, API, import) gets the stored values back, and a changed
        approver or a changed amount/party invalidates what was approved."""
        before = self.get_doc_before_save()
        if self.flags.approval_action:
            return
        if not before:
            for n in OTHER_SLOTS:
                self.set(f"approver_{n}", None)
            for n in APPROVER_SLOTS:
                self.set(f"approver_{n}_on", None)
                self.set(f"approver_{n}_remarks", None)
                self.set(f"approver_{n}_status", PENDING if self.get(f"approver_{n}") else None)
            self.approved_amount = 0
            return

        for n in APPROVER_SLOTS:
            for suffix in ("status", "on", "remarks"):
                self.set(f"approver_{n}_{suffix}", before.get(f"approver_{n}_{suffix}"))
        # Only Approver 1 is chosen by the requester; the other slots record who acted.
        for n in OTHER_SLOTS:
            self.set(f"approver_{n}", before.get(f"approver_{n}"))
        self.approved_amount = before.approved_amount

        had_action = any(before.get(f"approver_{n}_status") in (APPROVED, REJECTED) for n in APPROVER_SLOTS)
        if had_action and (
            flt(before.requested_amount) != flt(self.requested_amount) or (before.party_type, before.party) != (self.party_type, self.party)
        ):
            for n in APPROVER_SLOTS:
                self.clear_slot(n)
            self.approved_amount = 0
            frappe.msgprint(
                _("The amount or party changed, so all earlier approvals were cleared."), indicator="orange", alert=True
            )
        elif before.approver_1 != self.approver_1:
            self.clear_slot(1)

    def validate_amounts(self):
        if flt(self.requested_amount) <= 0:
            frappe.throw(_("Requested Amount must be greater than zero."))
        if flt(self.approved_amount) and flt(self.approved_amount) > flt(self.requested_amount):
            frappe.throw(_("Approved Amount cannot exceed the Requested Amount."))

    def validate_references(self):
        for doctype, field in (("Purchase Order", "purchase_order"), ("Purchase Invoice", "purchase_invoice")):
            name = self.get(field)
            if not name:
                continue
            if self.party_type != "Supplier":
                self.set(field, None)
                continue
            supplier, docstatus = frappe.db.get_value(doctype, name, ["supplier", "docstatus"])
            if docstatus == 2:
                frappe.throw(_("{0} {1} is cancelled.").format(doctype, name))
            if supplier != self.party:
                frappe.throw(_("{0} {1} belongs to supplier {2}, not {3}.").format(doctype, name, supplier, self.party))

    def validate_sales_order(self):
        if not self.sales_order or self.party_type != "Customer":
            return
        customer, docstatus = frappe.db.get_value("Sales Order", self.sales_order, ["customer", "docstatus"])
        if docstatus == 2:
            frappe.throw(_("Sales Order {0} is cancelled.").format(self.sales_order))
        if customer != self.party:
            frappe.throw(_("Sales Order {0} belongs to customer {1}, not {2}.").format(self.sales_order, customer, self.party))

    def set_party_name(self):
        if self.party_type not in ("Supplier", "Customer") or not self.party:
            self.party_name = None
            return
        self.party_name = frappe.db.get_value(self.party_type, self.party, f"{self.party_type.lower()}_name")

    def set_payment_accounts(self):
        """Fill the bank/cash and party accounts from the Mode of Payment and the
        party, but only the blanks -- anything the user chose stays."""
        if self.flags.skip_payment_defaults:
            return
        if self.paid_from and self.party_account:
            return
        defaults = get_payment_defaults(self.company, self.party_type, self.party, self.mode_of_payment)
        self.paid_from = self.paid_from or defaults.get("paid_from")
        self.party_account = self.party_account or defaults.get("party_account")

    def validate_payment_details(self):
        if self.paid_from:
            acct = frappe.db.get_value("Account", self.paid_from, ["company", "account_type", "is_group"], as_dict=True)
            if not acct or acct.company != self.company or acct.is_group or acct.account_type not in ("Bank", "Cash"):
                frappe.throw(_("Paid From must be a Bank or Cash account of {0}.").format(self.company))
        if self.party_account:
            acct = frappe.db.get_value("Account", self.party_account, ["company", "is_group"], as_dict=True)
            if not acct or acct.company != self.company or acct.is_group:
                frappe.throw(_("Party Account must be a ledger account of {0}.").format(self.company))

    def require_payment_details(self):
        """Needed from submit onwards -- not at approval time."""
        missing = []
        if not self.mode_of_payment:
            missing.append(_("Mode of Payment"))
        else:
            if not self.paid_from:
                missing.append(_("Paid From (set a bank/cash Account on Mode of Payment {0}, or choose one)").format(self.mode_of_payment))
        if not self.party_account:
            missing.append(_("Party Account (no default account found for {0} {1})").format(self.party_type, self.party))
        if missing:
            frappe.throw(
                _("Fill in the Payment Details before submitting:") + "<br>" + "<br>".join(missing),
                title=_("Payment Details Missing"),
            )

    def set_fund_usage(self):
        if self.party_type != "Supplier":
            self.source_of_funds = None
        if not self.source_of_funds:
            self.total_customer_payment = self.already_used_amount = self.balance_amount = 0
            self.customer_payment_date = None
            return
        usage = get_fund_usage(self.source_of_funds, self.name)
        self.total_customer_payment = usage["total_customer_payment"]
        self.customer_payment_date = usage["customer_payment_date"]
        self.already_used_amount = usage["already_used_amount"]
        self.balance_amount = usage["balance_amount"]

    def warn_fund_balance(self):
        """Non-blocking: the customer's money is a budget, not a hard limit."""
        if self.source_of_funds and self.final_amount > flt(self.balance_amount):
            frappe.msgprint(
                _("This request's amount ({0}) exceeds the remaining balance ({1}) of the selected Source of Funds ({2}).").format(
                    frappe.format(self.final_amount, {"fieldtype": "Currency"}),
                    frappe.format(self.balance_amount, {"fieldtype": "Currency"}),
                    self.source_of_funds,
                ),
                title=_("Fund Balance Exceeded"),
                indicator="orange",
            )

    def set_status(self):
        if self.docstatus == 2:
            self.status = "Cancelled"
        elif self.docstatus == 1:
            if self.status != "Paid":
                self.status = "Submitted"
        elif self.is_rejected():
            self.status = "Rejected"
        elif self.is_fully_approved():
            self.status = "Approved"
        elif self.approver_1:
            self.status = "Pending Approval"
        else:
            self.status = "Draft"

    def set_approval_summary(self):
        """Stored (not computed on read) so the list view can filter on them:
        `pending_with` holds the user ids still expected to approve, which is what the
        "Pending My Approval" filter matches."""
        self.approvals_received = self.approved_count()
        self.pending_with = ", ".join(self.pending_approver_users()) or None

    # ------------------------------------------------------ ToDo / notification
    def pending_approver_users(self):
        """Who is expected to approve next: Approver 1 first; once Approver 1 has
        approved, every other Director who has not acted yet (any one of them will do).
        Nobody once the request is fully approved or rejected."""
        if self.docstatus != 0 or self.is_rejected() or self.is_fully_approved() or not self.approver_1:
            return []
        if self.slot_status(1) == PENDING:
            return [self.approver_1]
        acted = {u for n, u in self.selected_approvers() if self.slot_status(n) != PENDING}
        return [u for u in get_directors() if u not in acted]

    def sync_assignments(self):
        """Keep one open ToDo per approver who still has to act, so the request shows
        in their ToDo list and they get notified. In-app only -- the live site has no
        outgoing Email Account, so nothing here may depend on mail."""
        wanted = set(self.pending_approver_users())
        open_todos = {
            t.allocated_to: t.name
            for t in frappe.get_all(
                "ToDo",
                filters={"reference_type": self.doctype, "reference_name": self.name, "status": "Open"},
                fields=["name", "allocated_to"],
            )
        }
        for user in wanted - set(open_todos):
            try:
                frappe.get_doc(
                    {
                        "doctype": "ToDo",
                        "allocated_to": user,
                        "reference_type": self.doctype,
                        "reference_name": self.name,
                        "assigned_by": frappe.session.user,
                        "priority": "High",
                        "description": _("Approve payment of {0} to {1} ({2})").format(
                            frappe.format(self.requested_amount, {"fieldtype": "Currency"}), self.party_name or self.party, self.purpose
                        ),
                    }
                ).insert(ignore_permissions=True)
                self.notify(user, _("Payment Approval {0} needs your approval").format(self.name))
            except Exception:
                frappe.log_error(title="Payment Approval: could not assign approver", message=frappe.get_traceback())
        for user, todo in open_todos.items():
            if user not in wanted:
                frappe.db.set_value("ToDo", todo, "status", "Closed", update_modified=False)

    def close_todos(self):
        for t in frappe.get_all("ToDo", filters={"reference_type": self.doctype, "reference_name": self.name, "status": "Open"}):
            frappe.db.set_value("ToDo", t.name, "status", "Closed", update_modified=False)

    def notify(self, user, subject):
        try:
            frappe.get_doc(
                {
                    "doctype": "Notification Log",
                    "for_user": user,
                    "from_user": frappe.session.user,
                    "type": "Alert",
                    "subject": subject,
                    "document_type": self.doctype,
                    "document_name": self.name,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="Payment Approval: notification failed", message=frappe.get_traceback())


# ---------------------------------------------------------------------- settings
def get_min_approvals():
    """Approvals needed before submit, counting Approver 1."""
    return cint(frappe.db.get_single_value("Payment Approval Settings", "min_approvals")) or 2


def get_directors():
    """Enabled users holding the Director role."""
    return frappe.db.sql(
        """
        SELECT u.name FROM `tabUser` u
        INNER JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
        WHERE hr.role = %s AND u.enabled = 1 ORDER BY u.full_name
        """,
        DIRECTOR_ROLE,
        pluck="name",
    )


# --------------------------------------------------------------------- approvals
def _act(name, remarks, result, approved_amount=None):
    remarks = (remarks or "").strip()
    if not remarks:
        frappe.throw(_("Remarks are required."))

    # Row lock until the transaction ends, so two approvers acting at the same instant
    # are applied one after the other instead of overwriting each other's result.
    frappe.db.get_value("Payment Approval", name, "name", for_update=True)
    doc = frappe.get_doc("Payment Approval", name)
    return _record_decision(doc, remarks, result, approved_amount)


def _record_decision(doc, remarks, result, approved_amount):
    if doc.docstatus != 0:
        frappe.throw(_("Only a draft Payment Approval can be approved or rejected."))
    if DIRECTOR_ROLE not in frappe.get_roles():
        frappe.throw(_("Only users with the {0} role can approve.").format(DIRECTOR_ROLE), frappe.PermissionError)

    user = frappe.session.user
    if doc.is_rejected():
        frappe.throw(_("This Payment Approval was rejected. Reset approvals to start again."))

    slot = doc.slot_of(user)
    if slot and doc.slot_status(slot) != PENDING:
        frappe.throw(_("You have already {0} this.").format(_("approved") if doc.slot_status(slot) == APPROVED else _("rejected")))
    if slot != 1:
        # Everyone except Approver 1 waits for Approver 1, then any Director may act.
        if doc.slot_status(1) != APPROVED:
            frappe.throw(
                _("Approver 1 ({0}) must approve first.").format(frappe.db.get_value("User", doc.approver_1, "full_name") or doc.approver_1),
                title=_("Approver 1 Pending"),
            )
        if not slot:
            slot = doc.free_slot()
            if not slot:
                frappe.throw(_("All approver slots are already used."))

    doc.flags.approval_action = True
    # An approver needs no Accounts permissions: payment accounts are not touched here.
    doc.flags.skip_payment_defaults = True
    doc.set(f"approver_{slot}", user)
    doc.set(f"approver_{slot}_status", result)
    doc.set(f"approver_{slot}_on", now_datetime())
    doc.set(f"approver_{slot}_remarks", remarks)
    if result == APPROVED and approved_amount not in (None, ""):
        doc.approved_amount = flt(approved_amount)
    doc.save(ignore_permissions=True)

    verb = _("approved") if result == APPROVED else _("rejected")
    doc.add_comment("Info", _("{0} {1}: {2}").format(frappe.session.user, verb, remarks))
    frappe.db.set_value(
        "ToDo",
        {"reference_type": doc.doctype, "reference_name": doc.name, "allocated_to": frappe.session.user, "status": "Open"},
        "status",
        "Closed",
        update_modified=False,
    )

    if doc.owner and doc.owner != frappe.session.user:
        doc.notify(doc.owner, _("{0} {1} Payment Approval {2}").format(frappe.session.user, verb, doc.name))
    if doc.status == "Approved":
        # Any Director can submit, so tell all of them (and the requester).
        for u in {doc.owner, *get_directors()} - {frappe.session.user}:
            doc.notify(u, _("Payment Approval {0} is approved and ready to submit").format(doc.name))
    return {"status": doc.status, "approved_count": doc.approved_count()}


@frappe.whitelist(methods=["POST"])
def approve(name, remarks, approved_amount=None):
    return _act(name, remarks, APPROVED, approved_amount)


@frappe.whitelist(methods=["POST"])
def reject(name, remarks):
    return _act(name, remarks, REJECTED)


@frappe.whitelist(methods=["POST"])
def submit_approval(name, mode_of_payment=None, paid_from=None, party_account=None):
    """Submit an approved request. Any Director (not only the requester) may do it, as may
    anyone with Submit permission. Directors have no Accounts permissions, so the submit
    is done here after checking who is asking and that the approvals are complete."""
    frappe.db.get_value("Payment Approval", name, "name", for_update=True)
    doc = frappe.get_doc("Payment Approval", name)
    if not (DIRECTOR_ROLE in frappe.get_roles() or doc.has_permission("submit")):
        frappe.throw(_("Only a Director or an Accounts user can submit a Payment Approval."), frappe.PermissionError)
    if doc.docstatus != 0:
        frappe.throw(_("This Payment Approval is already submitted."))
    if not doc.is_fully_approved():
        frappe.throw(_("It cannot be submitted until Approver 1 and enough other Directors have approved."), title=_("Approval Pending"))

    doc.flags.approval_action = True
    doc.flags.ignore_permissions = True
    if mode_of_payment:
        doc.mode_of_payment = mode_of_payment
    if paid_from:
        doc.paid_from = paid_from
    if party_account:
        doc.party_account = party_account
    doc.submit()
    doc.add_comment("Info", _("{0} submitted this Payment Approval.").format(frappe.session.user))
    return doc.status


@frappe.whitelist(methods=["POST"])
def reset_approvals(name):
    doc = frappe.get_doc("Payment Approval", name)
    doc.check_permission("write")
    if doc.docstatus != 0:
        frappe.throw(_("Only a draft Payment Approval can be reset."))
    doc.flags.approval_action = True
    for n in APPROVER_SLOTS:
        doc.clear_slot(n)
    doc.approved_amount = 0
    doc.save()
    doc.add_comment("Info", _("{0} reset all approvals.").format(frappe.session.user))
    return doc.status


# ----------------------------------------------------------------- payment entry
@frappe.whitelist()
def make_payment_entry(name):
    """Return an unsaved Pay entry for the approved amount (the caller opens it in the
    form, as core does for Payment Request). Allocated to the Purchase Invoice /
    Purchase Order when one is named; otherwise it stays an unallocated advance."""
    from erpnext.accounts.utils import get_account_currency

    doc = frappe.get_doc("Payment Approval", name)
    doc.check_permission("read")
    frappe.has_permission("Payment Entry", "create", throw=True)
    if doc.docstatus != 1 or doc.status not in ("Submitted",):
        frappe.throw(_("A Payment Entry can only be created from a submitted, unpaid Payment Approval."))
    existing = frappe.db.get_value(
        "Payment Entry", {"custom_payment_approval": doc.name, "docstatus": ["<", 2]}, "name"
    )
    if existing:
        frappe.throw(_("Payment Entry {0} already exists for this Payment Approval.").format(existing))

    amount = doc.final_amount
    doc.require_payment_details()
    party_account = doc.party_account
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Pay"
    pe.company = doc.company
    pe.posting_date = nowdate()
    pe.mode_of_payment = doc.mode_of_payment
    pe.party_type = doc.party_type
    pe.party = doc.party
    pe.paid_from = doc.paid_from
    pe.paid_to = party_account
    pe.paid_from_account_currency = get_account_currency(doc.paid_from)
    pe.paid_to_account_currency = get_account_currency(party_account)
    pe.paid_amount = pe.received_amount = amount
    pe.project = doc.project
    pe.reference_no = doc.name
    pe.reference_date = nowdate()
    pe.remarks = _("Payment against Payment Approval {0} ({1})").format(doc.name, doc.purpose or "")
    if doc.source_of_funds:
        # Reference only: named in the remarks, never allocated or posted against.
        pe.remarks += " " + _("Source of Funds (reference only): {0}").format(doc.source_of_funds)
    pe.custom_payment_approval = doc.name

    if doc.purchase_invoice:
        total, outstanding = frappe.db.get_value("Purchase Invoice", doc.purchase_invoice, ["grand_total", "outstanding_amount"])
        ref = ("Purchase Invoice", doc.purchase_invoice, flt(total), flt(outstanding))
    elif doc.purchase_order:
        po = frappe.db.get_value("Purchase Order", doc.purchase_order, ["grand_total", "advance_paid"], as_dict=True)
        ref = ("Purchase Order", doc.purchase_order, flt(po.grand_total), flt(po.grand_total) - flt(po.advance_paid))
    elif doc.sales_order and doc.party_type == "Customer":
        # Customer paid against a Sales Order (e.g. advance refund): allocate to it, the
        # same total/outstanding core Payment Entry works out for a Sales Order.
        so = frappe.db.get_value(
            "Sales Order", doc.sales_order, ["rounded_total", "grand_total", "advance_paid", "customer"], as_dict=True
        )
        total = flt(so.rounded_total) or flt(so.grand_total)
        ref = ("Sales Order", doc.sales_order, total, total - flt(so.advance_paid))
    else:
        ref = None
    if doc.party_bill_no:
        pe.remarks += " " + _("Party Bill No: {0}").format(doc.party_bill_no)
    if doc.sales_order and doc.party_type == "Supplier":
        # A Sales Order on a supplier payment is information only (core allows no Sales
        # Order allocation against a supplier), so it is named in the remarks.
        pe.remarks += " " + _("Sales Order (reference only): {0}").format(doc.sales_order)
    if ref and ref[3] > 0:
        pe.append(
            "references",
            {
                "reference_doctype": ref[0],
                "reference_name": ref[1],
                "total_amount": ref[2],
                "outstanding_amount": ref[3],
                "allocated_amount": min(amount, ref[3]),
            },
        )

    pe.setup_party_account_field()
    pe.set_missing_values()
    pe.set_exchange_rate()
    pe.set_amounts()
    return pe.as_dict()


@frappe.whitelist()
def get_payment_defaults(company, party_type=None, party=None, mode_of_payment=None):
    """Default bank/cash account for the Mode of Payment and payable account for the
    party -- used to prefill the Payment Details."""
    from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account
    from erpnext.accounts.party import get_party_account

    frappe.has_permission("Payment Approval", "read", throw=True)
    out = {}
    # The default accounts are a lookup, not a disclosure. Core checks the caller's Account
    # permission, which Directors and plain requesters do not have, so look them up as
    # Administrator (nothing but the two account names leaves this function).
    session_user = frappe.session.user
    frappe.set_user("Administrator")
    try:
        if company and mode_of_payment:
            out["paid_from"] = (get_default_bank_cash_account(company, "Bank", mode_of_payment=mode_of_payment) or {}).get("account")
        if company and party_type in ("Supplier", "Customer") and party:
            out["party_account"] = get_party_account(party_type, party, company)
    finally:
        frappe.set_user(session_user)
    return out


@frappe.whitelist(methods=["POST"])
def save_payment_details(name, mode_of_payment, paid_from=None, party_account=None):
    """Store the Payment Details on a submitted-but-unpaid Payment Approval (draft ones
    are saved from the form), so Create Payment Entry can proceed."""
    doc = frappe.get_doc("Payment Approval", name)
    doc.check_permission("write")
    if doc.docstatus != 1 or doc.status != "Submitted":
        frappe.throw(_("Payment Details can only be changed on a submitted, unpaid Payment Approval."))
    doc.flags.approval_action = True
    doc.mode_of_payment = mode_of_payment
    doc.paid_from = paid_from or None
    doc.party_account = party_account or None
    doc.set_payment_accounts()
    doc.require_payment_details()
    doc.save()
    return {"mode_of_payment": doc.mode_of_payment, "paid_from": doc.paid_from, "party_account": doc.party_account}


# -------------------------------------------------------------------- fund usage
@frappe.whitelist()
def get_fund_usage(payment_entry, payment_approval=None):
    """Given a customer Payment Entry used as a Source of Funds, return how much of it
    other *Paid* Payment Approvals have already drawn, and what remains.
    `payment_approval` (the current document, if any) is excluded from the sum."""
    pe = frappe.db.get_value("Payment Entry", payment_entry, ["paid_amount", "posting_date"], as_dict=True)
    if not pe:
        frappe.throw(_("Payment Entry {0} not found").format(payment_entry))

    used = frappe.db.sql(
        """
        SELECT COALESCE(SUM(COALESCE(NULLIF(approved_amount, 0), requested_amount)), 0)
        FROM `tabPayment Approval`
        WHERE source_of_funds = %(pe)s AND status = 'Paid' AND docstatus = 1
          AND name != %(name)s
        """,
        {"pe": payment_entry, "name": payment_approval or ""},
    )[0][0]
    total = pe.paid_amount or 0
    return {
        "total_customer_payment": total,
        "customer_payment_date": pe.posting_date,
        "already_used_amount": flt(used),
        "balance_amount": total - flt(used),
    }


# ------------------------------------------------------------------ link queries
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def payment_entry_query(doctype, txt, searchfield, start, page_len, filters):
    """Link search for Source of Funds: matches Payment Entry name, customer
    (party/party_name), or reference no. Restricted to submitted customer receipts."""
    return frappe.db.sql(
        """
        SELECT pe.name, pe.party_name, pe.reference_no, pe.paid_amount
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Receive'
          AND pe.party_type = 'Customer'
          AND (
              pe.name LIKE %(txt)s
              OR pe.party_name LIKE %(txt)s
              OR pe.party LIKE %(txt)s
              OR pe.reference_no LIKE %(txt)s
          )
        ORDER BY pe.posting_date DESC
        LIMIT %(page_len)s OFFSET %(start)s
        """,
        {"txt": f"%{txt}%", "page_len": cint(page_len), "start": cint(start)},
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def director_query(doctype, txt, searchfield, start, page_len, filters):
    """Approvers are picked from enabled users holding the Director role."""
    return frappe.db.sql(
        """
        SELECT u.name, u.full_name
        FROM `tabUser` u
        INNER JOIN `tabHas Role` hr ON hr.parent = u.name AND hr.parenttype = 'User'
        WHERE hr.role = %(role)s AND u.enabled = 1
          AND (u.name LIKE %(txt)s OR u.full_name LIKE %(txt)s)
        ORDER BY u.full_name
        LIMIT %(page_len)s OFFSET %(start)s
        """,
        {"role": DIRECTOR_ROLE, "txt": f"%{txt}%", "page_len": cint(page_len), "start": cint(start)},
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def account_query(doctype, txt, searchfield, start, page_len, filters):
    """Account search for the Payment Details dialog. Directors submit approved requests
    but hold no Account permission, so the standard link search would return nothing.
    filters: {"company": ..., "kind": "bank" | "party"}."""
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    filters = filters or {}
    frappe.has_permission("Payment Approval", "read", throw=True)
    bank = filters.get("kind") == "bank"
    return frappe.db.sql(
        f"""
        SELECT name, account_type FROM `tabAccount`
        WHERE company = %(company)s AND is_group = 0 AND disabled = 0
          {"AND account_type IN ('Bank', 'Cash')" if bank else ""}
          AND (name LIKE %(txt)s OR account_name LIKE %(txt)s)
        ORDER BY name LIMIT %(page_len)s OFFSET %(start)s
        """,
        {"company": filters.get("company"), "txt": f"%{txt}%", "page_len": cint(page_len), "start": cint(start)},
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def mode_of_payment_query(doctype, txt, searchfield, start, page_len, filters):
    frappe.has_permission("Payment Approval", "read", throw=True)
    return frappe.db.sql(
        """
        SELECT name FROM `tabMode of Payment`
        WHERE enabled = 1 AND name LIKE %(txt)s
        ORDER BY name LIMIT %(page_len)s OFFSET %(start)s
        """,
        {"txt": f"%{txt}%", "page_len": cint(page_len), "start": cint(start)},
    )


@frappe.whitelist()
def get_default_requester():
    """The Payment Requested By name for the logged-in user (created on first use), so a
    new Payment Approval opens with Requested By already filled in."""
    from manufyxinvenzaerp.accounts_management.doctype.payment_requested_by.payment_requested_by import (
        get_or_create_for_user,
    )

    return get_or_create_for_user(frappe.session.user)
