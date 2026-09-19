import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now
from manufyxinvenzaerp.utils.dimension_formula import calculate_qty

STRUCTURALS_REQUIRED = ["length", "unit_weight", "sec_qty"]
PLATES_REQUIRED = ["length", "width", "thickness", "unit_weight", "sec_qty"]
NUTS_AND_BOLTS_REQUIRED = ["qty"]
FIELD_LABELS = {
    "length": "Length",
    "width": "Width",
    "thickness": "Thickness",
    "unit_weight": "Unit Weight",
    "sec_qty": "Sec Qty",
    "qty": "Primary Qty",
}

class Drawing(Document):
    def before_insert(self):
        if self.amended_from:
            prev_rev = frappe.db.get_value("Drawing", self.amended_from, "rev_no") or 0
            self.rev_no = prev_rev + 1
        else:
            self.rev_no = 0
        self.status = "Working"

    def validate(self):
        self.customer_no = self.customer or ""
        self._warn_duno_reused_elsewhere()
        self._recalculate_all()
        self._check_missing_fields(throw=False)
        self._calculate_totals()
        self._set_cust_weight_total()

    def _set_cust_weight_total(self):
        """Cust Weight (Total) is per Nos x Nos, never typed (sep14 FG plan, D2).

        The per Nos figure is what the customer states and what Update Customer
        Weight edits; the Total is what every downstream document carries. Deriving
        the Total here means a change to either input -- a new per Nos, or a
        corrected No of Qty to Manufacture on a draft -- cannot leave the two
        disagreeing. A drawing without a per Nos figure (made before the Kg / Nos
        change, D13) keeps the Total it was given.

        Not to be confused with total_weight, which is the raw-material roll-up."""
        if flt(self.get("weight_per_pcs")):
            self.customer_provided_wt = flt(
                flt(self.weight_per_pcs) * flt(self.no_of_qty_to_manufacture), 3
            )

    def _warn_duno_reused_elsewhere(self):
        """Say so when this mark is already used by a different Sales Order.

        Closes the back door left by the Sales Order gate: a Drawing created by hand
        never goes through Verify Raw Materials, so without this the first anyone
        hears of a clash is a Material Planning refusing to save much later.

        A warning, not a block, for the same reason it is a warning there -- the mark
        is the customer's. Only a plan that would actually combine the two jobs
        refuses, and Material Planning / Production Plan do that themselves.

        Skipped for a revision: create_revision cancels the old drawing before
        inserting the new one, so the only drawing that could match is this one's own
        previous revision -- and find_clashes_on_other_sales_orders ignores cancelled
        drawings and this Sales Order anyway.
        """
        if not (self.duno_mark_no and self.sales_order):
            return

        from manufyxinvenzaerp.drawing_management.duno_uniqueness import (
            find_clashes_on_other_sales_orders, warn_text_for_clashes, warnings_enabled,
        )

        # Manufyxinvenza Settings -> "Show Warning for Duplicate DUNO". Off means
        # silent here; it does NOT relax Material Planning or Production Plan.
        if not warnings_enabled():
            return

        clashes = find_clashes_on_other_sales_orders(self.sales_order, [self.duno_mark_no])
        for line in warn_text_for_clashes(clashes):
            frappe.msgprint(line, title=_("DUNO/Mark No Reused"), indicator="orange")

    def before_submit(self):
        self._check_missing_fields(throw=True)

    def on_submit(self):
        _link_to_sales_order_row(self)

    def on_cancel(self):
        self.db_set("status", "Old Revision")
        _release_sales_order_row(self)

    def _recalculate_all(self):
        no_of_qty = flt(self.no_of_qty_to_manufacture)
        for row in self.items:
            _recalculate_row_qty(row)
            _recalculate_row_totals(row, no_of_qty)

    def _check_missing_fields(self, throw):
        for row in self.items:
            _check_row_missing_fields(row, throw)

    def _calculate_totals(self):
        total_weight = flt(0)
        for row in self.items:
            uom = (row.uom or "").lower()
            sec_uom = (row.sec_uom or "").lower()
            if uom in ("kg", "kgs"):
                total_weight += flt(row.qty)
            elif sec_uom in ("kg", "kgs"):
                total_weight += flt(row.sec_qty)
        self.total_weight = flt(total_weight, 3)



def _sales_order_row(doc):
    """The Sales Order DUNO Item row this drawing belongs to, if it still exists."""
    if not (doc.sales_order and doc.duno_mark_no):
        return None
    filters = {"parent": doc.sales_order, "duno_mark_no": doc.duno_mark_no}
    if doc.customer_drawing_number:
        filters["drawing_number"] = doc.customer_drawing_number
    return frappe.db.get_value("Sales Order DUNO Item", filters, ["name", "drawing"], as_dict=True)



def _touch_sales_order(sales_order):
    """Move the Sales Order's own timestamp after re-pointing one of its rows.

    The row is written with frappe.db.set_value, which does not go near an order
    somebody already has open in a browser. Without this the form keeps the link it
    was loaded with -- the cancelled one -- and, because its timestamp still matched,
    Frappe's "this document has been modified" guard stayed quiet and let it submit
    that dead link straight back. The symptom is the original error reappearing on an
    order the database has already fixed.

    Moving the timestamp turns that silent overwrite into a reload prompt, which is
    what should have happened."""
    if sales_order:
        frappe.db.set_value(
            "Sales Order", sales_order, "modified", now(), update_modified=False
        )


def _release_sales_order_row(doc):
    """Cancelling a drawing lets go of the Sales Order row it was made for.

    Two things went wrong while the link stayed behind. The Sales Order could no
    longer be submitted at all -- Frappe refuses to link a cancelled document, and
    says so as a row number with no hint of which drawing or DUNO it means. And the
    row still looked answered, so "Create Drawings" never offered it again: the one
    obvious way to put it right was closed off by the very thing that broke it.

    Letting go puts the row back to how it looked before the drawing existed, which
    is what it now describes: a DUNO with no drawing against it. Amending the
    cancelled drawing re-attaches it on submit (see _link_to_sales_order_row), and
    re-importing it works too."""
    row = _sales_order_row(doc)
    if not row or row.drawing != doc.name:
        return
    frappe.db.set_value("Sales Order DUNO Item", row.name, "drawing", "", update_modified=False)
    _touch_sales_order(doc.sales_order)


def _link_to_sales_order_row(doc):
    """Submitting a drawing attaches it to its Sales Order row, where that row is
    waiting for one.

    Normally the import has already done this. It matters for an AMENDED drawing:
    the cancelled original let the row go, and this is what fills it back in with
    the revision that replaced it, so the Sales Order can be submitted again without
    anybody having to know a link was ever broken.

    It also takes over a row still holding the very document this one amends. That is
    the state every order cancelled before this existed is in: nothing let the row go
    at the time, so it is still naming a cancelled drawing and the order cannot be
    submitted. Replacing it is safe precisely because the match is exact -- this
    drawing IS the revision of the one the row names.

    A row naming any OTHER drawing is left alone. It is answered, and quietly
    repointing it would be a worse surprise than doing nothing."""
    row = _sales_order_row(doc)
    if not row:
        return
    if row.drawing and row.drawing != doc.amended_from:
        return
    frappe.db.set_value("Sales Order DUNO Item", row.name, "drawing", doc.name, update_modified=False)
    _touch_sales_order(doc.sales_order)


def _recalculate_row_qty(row):
    group = row.parent_item_group
    if group in ("Structurals", "Plates"):
        qty = calculate_qty(group, row.length, row.width, row.thickness, row.unit_weight, row.sec_qty)
        if qty is not None:
            row.qty = qty
    elif group == "Nuts and Bolts":
        if row.qty and row.unit_weight:
            row.sec_qty = flt(row.qty * row.unit_weight, 3)


def _recalculate_row_totals(row, no_of_qty):
    group = row.parent_item_group
    if group == "Nuts and Bolts":
        row.total_qty = flt(flt(row.qty) * no_of_qty, 3)
        row.total_sec_qty = flt(row.total_qty * flt(row.unit_weight), 3)
        return
    row.total_sec_qty = flt(row.sec_qty) * no_of_qty
    if group in ("Structurals", "Plates"):
        total_qty = calculate_qty(group, row.length, row.width, row.thickness, row.unit_weight, row.total_sec_qty)
        row.total_qty = flt(total_qty, 3) if total_qty is not None else 0
    else:
        row.total_qty = 0


def _check_row_missing_fields(row, throw):
    group = row.parent_item_group
    required = {
        "Structurals": STRUCTURALS_REQUIRED,
        "Plates": PLATES_REQUIRED,
        "Nuts and Bolts": NUTS_AND_BOLTS_REQUIRED,
    }.get(group)
    if not required:
        return
    missing = [FIELD_LABELS[f] for f in required if not getattr(row, f, None)]
    if not missing:
        return
    msg = _("Row {0}: Missing for {1} formula: {2}").format(
        row.idx, group, ", ".join(missing)
    )
    if throw:
        frappe.throw(msg)
    else:
        frappe.msgprint(msg, indicator="orange", title=_("Missing Fields"))


@frappe.whitelist()
def check_existing_bom(drawing_name):
    return bool(frappe.get_all(
        "BOM",
        filters={
            "custom_drawing": drawing_name,
            "docstatus": ["in", [0, 1]]
        },
        limit=1
    ))