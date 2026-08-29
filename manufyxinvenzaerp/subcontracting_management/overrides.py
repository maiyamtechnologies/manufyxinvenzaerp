import frappe
from frappe import _
from frappe.utils import flt

from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
    SubcontractingOrder,
)


def _is_pp_flow_sco(sco_name):
    """True when the linked SCO was created from a Production Plan (no supplied_items table)."""
    return bool(sco_name) and bool(
        frappe.db.get_value("Subcontracting Order", sco_name, "custom_production_plan")
    )


def resolve_supplier_warehouse(supplier, company):
    """The Warehouse a Job Worker's material sits in, by this site's naming
    convention: '<Job Worker> - <Company Abbr>' (e.g. 'INTERNATIONAL STEEL PRO -
    MIPL'). Returns "" when the supplier/company is missing or no such Warehouse
    has been created yet.

    Shared so the Material Issue Plan can resolve the same warehouse the
    Subcontracting Order would, rather than restating the convention -- an MIP is
    created in the same click as its SCO, before the SCO has had a chance to fill
    the field in, and a blank warehouse there blocks every transfer later on.
    """
    if not (supplier and company):
        return ""
    abbr = frappe.db.get_value("Company", company, "abbr")
    if not abbr:
        return ""
    warehouse = f"{supplier} - {abbr}"
    return warehouse if frappe.db.exists("Warehouse", warehouse) else ""


def _any_operation_started(sco_name):
    """True once any operation entry on this order has quantity against it.

    Reads the Consumption Log rather than the operation's own Status, so the
    order turns Working the moment the first quantity is entered and saved --
    not only when somebody remembers to move the operation off Open.
    """
    return bool(frappe.db.sql(
        """
        SELECT 1
        FROM `tabSOE Consumption Log` log
        JOIN `tabSupplier Operation Entry` soe ON soe.name = log.parent
        WHERE soe.subcontracting_order = %(sco)s
          AND soe.docstatus != 2
          AND log.qty_nos > 0
        LIMIT 1
        """,
        {"sco": sco_name},
    ))


def _final_stock_entry_submitted(sco_name):
    """True when the Material Issue Plan's final ('Manufacture') Stock Entry for
    this order has been submitted -- the point at which finished goods really
    exist in stock. Drafts do not count; see CustomSubcontractingOrder.update_status."""
    return bool(frappe.db.exists(
        "Stock Entry",
        {"subcontracting_order": sco_name, "stock_entry_type": "Manufacture", "docstatus": 1},
    ))


def refresh_sco_status(sco_name):
    """Re-derive a Job Work Order's status from the current state of its
    operations and its final Stock Entry.

    Called from the events that can change either -- an operation entry saved or
    submitted, the final Stock Entry submitted or cancelled -- so the status is
    never left behind by work that happened somewhere else. Silent for standard
    (non-Production-Plan) SCOs, which keep ERPNext's own receipt-driven status.
    """
    if not sco_name:
        return
    sco = frappe.get_doc("Subcontracting Order", sco_name)
    if not sco.get("custom_production_plan") or sco.docstatus != 1:
        return
    sco.update_status()

    # The plan above it follows the same events -- keep the two in step here rather
    # than making every caller remember both.
    from manufyxinvenzaerp.production_plan_management.production_plan import (
        refresh_production_plan_status,
    )

    refresh_production_plan_status(sco.custom_production_plan)


class CustomStockEntry(StockEntry):
    """Stock Entry override that relaxes ERPNext's standard subcontracting checks for
    'Send to Subcontractor' entries tied to a Production-Plan-flow Subcontracting Order,
    which has no 'Raw Materials Supplied' table to validate against."""

    def validate_subcontract_order(self):
        if self.purpose == "Send to Subcontractor" and _is_pp_flow_sco(self.get("subcontracting_order")):
            return
        super().validate_subcontract_order()


class CustomSubcontractingOrder(SubcontractingOrder):
    """Override of ERPNext's SubcontractingOrder that relaxes PO-dependent
    validations for SCOs created directly from a Production Plan.
    Standard SCOs (with purchase_order set) behave exactly as before.
    """

    def _is_pp_flow(self):
        return bool(self.get("custom_production_plan"))

    # ── Top-level validate override ───────────────────────────────────────────

    def validate(self):
        if not self._is_pp_flow():
            super().validate()
            return

        # PP flow: skip all PO-dependent validation; run only what's safe.
        self._pp_validate_job_worker()
        self._auto_set_supplier_warehouse()
        self._pp_validate_items()
        self.validate_supplied_items()
        self.calculate_additional_costs()
        self._pp_calculate_amounts()

    def _pp_validate_job_worker(self):
        """Job Worker is optional on Internal Job plans (setup.py's
        make_sco_job_worker_conditional relaxes the client-side/UI requirement via
        mandatory_depends_on) but still required for Supplier Job / Supplier with
        Material -- enforce that here too since reqd=0 means the core mandatory-field
        check no longer catches it server-side."""
        if self.supplier:
            return
        pp_type = self.get("custom_production_plan_type") or frappe.db.get_value(
            "Production Plan", self.get("custom_production_plan"), "custom_type"
        )
        if pp_type != "Internal Job":
            frappe.throw(_("Job Worker is mandatory for a {0} Production Plan.").format(pp_type or "non-Internal-Job"))

    def _auto_set_supplier_warehouse(self):
        """Job Worker Warehouse is hidden on the form (setup.py hide_sco_job_worker_warehouse)
        since every active Job Worker has a dedicated Warehouse named '<Job Worker> - <Company
        Abbr>' (e.g. 'INTERNATIONAL STEEL PRO - MIPL') — resolve it automatically instead of
        asking the user to pick it. Leaves the field untouched if already set (e.g. by an
        existing doc) or if no matching Warehouse exists yet (mandatory validation will then
        surface the standard "create it first" error)."""
        if self.supplier_warehouse or not self.supplier:
            return
        self.supplier_warehouse = resolve_supplier_warehouse(self.supplier, self.company) or None

    # ── on_submit / on_cancel overrides ──────────────────────────────────────

    def on_submit(self):
        if not self._is_pp_flow():
            super().on_submit()
            return
        self.update_status()
        # Skip update_subcontracted_quantity_in_po — no PO exists.
        # Auto-create one SOE per Subcontractor operation in the Production Plan.
        from manufyxinvenzaerp.subcontracting_management.subcontracting import _create_soes_for_sco
        created = _create_soes_for_sco(self)
        if created:
            count = len(created)
            frappe.msgprint(
                _("{0} Supplier Operation {1} created. "
                  "You can now transfer material to the supplier warehouse using the "
                  "<b>Raw Materials to Supplier</b> button, then enter the consumption "
                  "details for each operation in the <b>Operations</b> tab.").format(
                    count, _("Entry") if count == 1 else _("Entries")
                ),
                title=_("Supplier Operation Entries Created"),
                indicator="green",
            )

    def on_cancel(self):
        if not self._is_pp_flow():
            super().on_cancel()
            return
        self.update_status()
        self._cancel_and_delete_soes()

    # ── Status ────────────────────────────────────────────────────────────────

    def update_status(self, status=None, update_modified=True, update_bin=True):
        """Status of a Job Work Order follows its OPERATIONS, not its receipts.

        ERPNext derives an SCO's status from per_received and the Raw Materials
        Supplied table. A Production-Plan-flow order has neither -- no
        Subcontracting Receipt is ever made against it and supplied_items is
        empty -- so every one of them sat on "Open" from submit to the end of
        the job, however much work had been done.

        Here it follows what the job is actually doing:

            Open      submitted, nothing logged on any operation yet
            Working   at least one operation has quantity against it
            Completed every operation is submitted (custom_all_ops_complete)
                      AND the Material Issue Plan's final Stock Entry is
                      submitted, i.e. the finished goods are really in stock

        Completed deliberately waits for that Stock Entry to be SUBMITTED
        rather than merely created: the button hands back a draft, and a draft
        can still be edited or deleted. Cancelling it drops the order back to
        Working on its own, because this reads the state each time rather than
        latching a flag.
        """
        if not self._is_pp_flow():
            super().update_status(status=status, update_modified=update_modified, update_bin=update_bin)
            return

        if not status:
            status = self._pp_derive_status()

        if status and self.status != status:
            self.db_set("status", status, update_modified=update_modified)

    def _pp_derive_status(self):
        if self.docstatus == 0:
            return "Draft"
        if self.docstatus == 2:
            return "Cancelled"
        # Closed is a deliberate manual stop; never talk over it.
        if self.status == "Closed":
            return "Closed"

        if self.get("custom_all_ops_complete") and _final_stock_entry_submitted(self.name):
            return "Completed"

        return "Working" if _any_operation_started(self.name) else "Open"

    def _cancel_and_delete_soes(self):
        """Cancel submitted SOEs then delete all SOEs linked to this SCO.
        Blocks first if the mixed-plan handoff to a sibling Work Order's first Job
        Card has already been consumed — cancelling would silently invalidate
        quantity the internal team already logged against. Mirrors the codebase's
        existing block-rather-than-rollback style (see before_delete_supplier_operation_entry).
        """
        if self.get("custom_all_ops_complete"):
            wo_name = frappe.db.get_value(
                "Work Order",
                {"production_plan": self.get("custom_production_plan"), "docstatus": ["!=", 2]},
                "name",
            )
            if wo_name and frappe.db.exists(
                "Job Card",
                {"work_order": wo_name, "sequence_id": 1, "custom_total_consumed_kg": [">", 0]},
            ):
                frappe.throw(
                    _("The Work Order's first Job Card has already logged consumption based on "
                      "this Subcontracting Order's completed quantity. Reverse that Job Card's "
                      "consumption before cancelling this Subcontracting Order."),
                    title=_("Cannot Cancel — Handoff Already Consumed"),
                )

        soes = frappe.get_all(
            "Supplier Operation Entry",
            filters={"subcontracting_order": self.name},
            fields=["name", "docstatus"],
            order_by="sequence_id desc",
        )
        for soe in soes:
            doc = frappe.get_doc("Supplier Operation Entry", soe.name)
            if doc.docstatus == 1:
                # An operation entry refuses to be cancelled on its own (see
                # before_cancel_supplier_operation_entry) -- this cascade is the
                # one supported way, because it takes the whole chain with it.
                doc.flags.mfx_cancelled_by_sco = True
                doc.cancel()
            frappe.delete_doc("Supplier Operation Entry", soe.name, ignore_permissions=True, force=True)

    # ── Item validation ───────────────────────────────────────────────────────

    def _pp_validate_items(self):
        for item in self.items:
            if not item.bom:
                frappe.throw(
                    frappe._("Row {0}: Please set a BOM for Item {1}.").format(item.idx, item.item_code)
                )
            is_active = frappe.db.get_value("BOM", item.bom, "is_active")
            if not is_active:
                frappe.throw(
                    frappe._("Row {0}: BOM {1} is not active.").format(item.idx, item.bom)
                )

    # ── Amount calculation ────────────────────────────────────────────────────

    def _pp_calculate_amounts(self):
        total_qty = total = 0
        for item in self.items:
            item.amount = flt(item.qty) * flt(item.rate)
            total_qty += flt(item.qty)
            total += flt(item.amount)
        self.total_qty = total_qty
        self.total = total

    # Keep individual overrides so they're safe if called from elsewhere.

    def validate_purchase_order_for_subcontracting(self):
        if self._is_pp_flow():
            return
        super().validate_purchase_order_for_subcontracting()

    def validate_service_items(self):
        if self._is_pp_flow():
            return
        super().validate_service_items()

    def validate_items(self):
        if self._is_pp_flow():
            self._pp_validate_items()
            return
        super().validate_items()

    def calculate_service_costs(self):
        if self._is_pp_flow():
            return
        super().calculate_service_costs()

    def calculate_supplied_items_qty_and_amount(self):
        if self._is_pp_flow():
            return
        super().calculate_supplied_items_qty_and_amount()

    def calculate_items_qty_and_amount(self):
        if self._is_pp_flow():
            self._pp_calculate_amounts()
            return
        super().calculate_items_qty_and_amount()
