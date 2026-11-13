# Copyright (c) 2026, Manufyxinvenza and Contributors
# License: GNU General Public License v3. See license.txt

"""Payment Approval -- an internal, multi-Director approval for paying a supplier or a customer.

Replaces the customizations that used to sit on the core Payment Request (Source of
Funds, Payment Type). Core Payment Request is left exactly as ERPNext ships it; it is
built around a Sales/Purchase document and a payment gateway, neither of which a plain
"please pay this party" request has.

Flow: request is saved with 1-3 Director approvers -> each approver approves/rejects
with remarks (Approve/Reject buttons) -> once every selected approver has approved (and
the minimum in Payment Approval Settings is met) the document can be submitted ->
"Create Payment Entry" builds the Pay entry -> submitting that Payment Entry marks this
document Paid (see payment_entry.py).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

APPROVER_SLOTS = (1, 2, 3)
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
        selected = self.selected_approvers()
        return (
            bool(selected)
            and all(self.slot_status(n) == APPROVED for n, _u in selected)
            and len(selected) >= get_min_approvals()
        )

    @property
    def final_amount(self):
        return flt(self.approved_amount) or flt(self.requested_amount)

    def clear_slot(self, n):
        self.set(f"approver_{n}_status", PENDING if self.get(f"approver_{n}") else None)
        self.set(f"approver_{n}_on", None)
        self.set(f"approver_{n}_remarks", None)

    # --------------------------------------------------------------- lifecycle
    def validate(self):
        self.company = self.company or frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
        self.requested_by = self.requested_by or frappe.session.user
        if self.docstatus == 0:
            self.protect_approval_fields()
            self.validate_approvers()
        self.validate_amounts()
        self.validate_references()
        self.set_party_name()
        self.set_payment_accounts()
        self.validate_payment_details()
        self.set_fund_usage()
        self.set_status()
        if not self.flags.approval_action:
            self.warn_fund_balance()

    def before_submit(self):
        if self.is_rejected():
            frappe.throw(_("This Payment Approval was rejected and cannot be submitted."))
        if not self.is_fully_approved():
            frappe.throw(
                _("Every selected approver must approve before this can be submitted ({0} of {1} approved; minimum {2}).").format(
                    self.approved_count(), len(self.selected_approvers()), get_min_approvals()
                ),
                title=_("Approval Pending"),
            )
        self.require_payment_details()
        if not flt(self.approved_amount):
            self.approved_amount = self.requested_amount

    def before_update_after_submit(self):
        # Frappe runs validate() only on drafts; the Payment Details stay editable after
        # submit (until paid), so they need the same checks here.
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
        selected = self.selected_approvers()
        users = [u for _n, u in selected]
        if len(users) != len(set(users)):
            frappe.throw(_("The same user cannot be selected as approver more than once."))
        minimum = get_min_approvals()
        if len(users) < minimum:
            frappe.throw(
                _("Select at least {0} approvers (Payment Approval Settings > Minimum Approvals Required).").format(minimum)
            )
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
            for n in APPROVER_SLOTS:
                self.set(f"approver_{n}_on", None)
                self.set(f"approver_{n}_remarks", None)
                self.set(f"approver_{n}_status", PENDING if self.get(f"approver_{n}") else None)
            self.approved_amount = 0
            return

        for n in APPROVER_SLOTS:
            for suffix in ("status", "on", "remarks"):
                self.set(f"approver_{n}_{suffix}", before.get(f"approver_{n}_{suffix}"))
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
        else:
            for n in APPROVER_SLOTS:
                if before.get(f"approver_{n}") != self.get(f"approver_{n}"):
                    self.clear_slot(n)

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
        elif self.selected_approvers():
            self.status = "Pending Approval"
        else:
            self.status = "Draft"

    # ------------------------------------------------------ ToDo / notification
    def pending_approver_users(self):
        if self.docstatus != 0 or self.is_rejected():
            return []
        return [u for n, u in self.selected_approvers() if self.slot_status(n) == PENDING]

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
    return cint(frappe.db.get_single_value("Payment Approval Settings", "min_approvals")) or 2


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

    slot = next((n for n, u in doc.selected_approvers() if u == frappe.session.user), None)
    if not slot:
        frappe.throw(_("You are not an approver on this Payment Approval."), frappe.PermissionError)
    if doc.slot_status(slot) != PENDING:
        frappe.throw(_("You have already {0} this.").format(_("approved") if doc.slot_status(slot) == APPROVED else _("rejected")))
    if doc.is_rejected():
        frappe.throw(_("This Payment Approval was rejected. Reset approvals to start again."))

    doc.flags.approval_action = True
    # An approver needs no Accounts permissions: payment accounts are not touched here.
    doc.flags.skip_payment_defaults = True
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
        doc.notify(doc.owner, _("Payment Approval {0} is fully approved and can be submitted").format(doc.name))
    return {"status": doc.status, "approved_count": doc.approved_count()}


@frappe.whitelist(methods=["POST"])
def approve(name, remarks, approved_amount=None):
    return _act(name, remarks, APPROVED, approved_amount)


@frappe.whitelist(methods=["POST"])
def reject(name, remarks):
    return _act(name, remarks, REJECTED)


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
    else:
        ref = None
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
    # The party's default account is a lookup, not a disclosure; skip the
    # account-permission check core applies so any user filling the form gets the default.
    frappe.flags.ignore_account_permission = True
    if company and mode_of_payment:
        out["paid_from"] = (get_default_bank_cash_account(company, "Bank", mode_of_payment=mode_of_payment) or {}).get("account")
    if company and party_type in ("Supplier", "Customer") and party:
        out["party_account"] = get_party_account(party_type, party, company)
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
