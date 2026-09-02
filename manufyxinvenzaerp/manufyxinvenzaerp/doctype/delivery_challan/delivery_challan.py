"""Delivery Challan (Gate Pass).

A standalone digital copy of the pre-printed gate pass pad. It records what left
the gate, for whom, on whose vehicle, and -- when the challan is Returnable --
whether it ever came back.

It moves NO STOCK. Submitting a challan creates no Stock Entry, no Stock Ledger
Entry and no reservation; it is a paper document held in the database, kept for
gate reference and return chasing. verify_delivery_challan.py asserts that.

Returns are their own challan (challan_type "Return Entry") pointing back at the
original through `against_gate_pass`, with each row anchored to the source row
through `against_challan_item`. That row anchor is what makes a partial return
exact: without it, two rows carrying the same item on one challan cannot be
netted apart.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

# Quantities are carried at precision 3; anything under this is noise, not a
# pending return. Without it a challan returned in full sits on "Partially
# Returned" forever because of a 1e-9 float residue.
TOLERANCE = 0.001

RETURNABLE = "Returnable"
NON_RETURNABLE = "Non Returnable"
RETURN_ENTRY = "Return Entry"

DEFAULT_TERMS = (
    "<ol>"
    "<li>Material receipt should be acknowledged with in 48 hours. If not acknowledged "
    "it will be consider as all materials delivered as per Gate Pass and further claim "
    "will not be accepted.</li>"
    "<li>Material description should be mentioned as per Po Line item in all your documents.</li>"
    "<li>Gate pass no &amp; date should be mentioned in all your documents while return "
    "the materials.</li>"
    "<li>Our Company name &amp; address &amp; GST No should be mentioned in all your "
    "documents without any error.</li>"
    "</ol>"
)


class DeliveryChallan(Document):
    def validate(self):
        self._set_defaults()
        self._validate_type_rules()
        self._validate_against_gate_pass()
        self._validate_items()
        self._calculate_totals()
        self._validate_return_quantities()
        self._set_status()

    def on_submit(self):
        self._set_status()
        if self.challan_type == RETURN_ENTRY and self.against_gate_pass:
            _refresh_source_gate_pass(self.against_gate_pass)

    def on_cancel(self):
        self.db_set("status", "Cancelled")
        # The source must fall back to Material Out / Overdue: cancelling a return
        # puts the material back on the original challan's books.
        if self.challan_type == RETURN_ENTRY and self.against_gate_pass:
            _refresh_source_gate_pass(self.against_gate_pass)

    # ── defaults ────────────────────────────────────────────────────────────

    def _set_defaults(self):
        if not self.company:
            self.company = frappe.defaults.get_user_default("Company")
        if not self.gp_date:
            self.gp_date = nowdate()
        if self.is_new() and not self.terms:
            self.terms = DEFAULT_TERMS

        # Filled only when blank, so a hand-corrected name or address is never
        # clobbered by a re-save.
        if self.party_type and self.party:
            if not self.party_display_name:
                self.party_display_name = _party_display_name(self.party_type, self.party)
            if not self.party_address:
                self.party_address = _party_address(self.party_type, self.party)

    # ── validation ──────────────────────────────────────────────────────────

    def _validate_type_rules(self):
        if self.challan_type == RETURNABLE:
            if not self.expected_return_date:
                frappe.throw(_("Expected Date of Return is required on a Returnable gate pass."))
            if getdate(self.expected_return_date) < getdate(self.gp_date):
                frappe.throw(
                    _("Expected Date of Return ({0}) cannot be before the GP Date ({1}).").format(
                        frappe.utils.formatdate(self.expected_return_date),
                        frappe.utils.formatdate(self.gp_date),
                    )
                )
            self.against_gate_pass = None

        elif self.challan_type == NON_RETURNABLE:
            self.expected_return_date = None
            self.against_gate_pass = None

        elif self.challan_type == RETURN_ENTRY:
            self.expected_return_date = None
            if not self.against_gate_pass:
                frappe.throw(_("A Return Entry must name the gate pass it returns against."))

    def _validate_against_gate_pass(self):
        if self.challan_type != RETURN_ENTRY or not self.against_gate_pass:
            return

        if self.against_gate_pass == self.name:
            frappe.throw(_("A gate pass cannot be a Return Entry against itself."))

        source = frappe.db.get_value(
            "Delivery Challan",
            self.against_gate_pass,
            ["docstatus", "challan_type", "status", "pending_qty", "company"],
            as_dict=True,
        )
        if not source:
            frappe.throw(_("Gate pass {0} does not exist.").format(self.against_gate_pass))

        if source.docstatus != 1:
            frappe.throw(
                _("Gate pass {0} is not submitted. A Return Entry can only be made against a "
                  "submitted gate pass.").format(self.against_gate_pass)
            )

        if source.challan_type != RETURNABLE:
            frappe.throw(
                _("Gate pass {0} is {1}, so nothing is expected back against it. A Return Entry "
                  "can only be made against a Returnable gate pass.").format(
                      self.against_gate_pass, source.challan_type)
            )

        # The link query only OFFERS same-company gate passes; nothing enforced it,
        # so a name typed or pasted in -- or set over the API -- could return
        # material against another company's pass and quietly cross the books.
        if source.company and self.company and source.company != self.company:
            frappe.throw(
                _("Gate pass {0} belongs to {1}, but this Return Entry is for {2}. A return must "
                  "be made against a gate pass of the same company.").format(
                      self.against_gate_pass, source.company, self.company)
            )

    def _validate_items(self):
        if not self.items:
            frappe.throw(_("Add at least one material row."))
        for row in self.items:
            if not row.material_description and row.item_code:
                row.material_description = frappe.db.get_value("Item", row.item_code, "item_name")
            if flt(row.qty) < 0 or flt(row.weight_kg) < 0:
                frappe.throw(_("Row {0}: Qty and Weight cannot be negative.").format(row.idx))

    def _calculate_totals(self):
        self.total_qty = flt(sum(flt(r.qty) for r in self.items), 3)
        self.total_weight_kg = flt(sum(flt(r.weight_kg) for r in self.items), 3)

        # Pending MUST be seeded here, not only by the return refresh. The status
        # machine reads "pending <= tolerance" as Returned, so a Returnable gate
        # pass whose pending_qty was still 0 from insert submitted straight into
        # "Returned" -- born closed, never chased, never overdue.
        if self.challan_type == RETURNABLE:
            self.pending_qty = max(
                flt(flt(self.total_qty) - flt(self.returned_qty), 3), 0.0
            )
            self.pending_weight_kg = max(
                flt(flt(self.total_weight_kg) - flt(self.returned_weight_kg), 3), 0.0
            )
        else:
            # Nothing is expected back against these, so the return columns would
            # only mislead whoever reads them.
            self.returned_qty = 0
            self.returned_weight_kg = 0
            self.pending_qty = 0
            self.pending_weight_kg = 0

    def _validate_return_quantities(self):
        """A Return Entry may never hand back more than is still out.

        Quantities already returned by OTHER submitted return entries are counted;
        this document's own rows are excluded so that re-saving or amending it does
        not double-count itself out of validity.
        """
        if self.challan_type != RETURN_ENTRY or not self.against_gate_pass:
            return

        source_rows = {
            r.name: r
            for r in frappe.get_all(
                "Delivery Challan Item",
                filters={"parent": self.against_gate_pass, "parenttype": "Delivery Challan"},
                fields=["name", "idx", "material_description", "qty", "weight_kg"],
            )
        }
        returned = _returned_by_row(self.against_gate_pass, exclude_challan=self.name)

        for row in self.items:
            if not row.against_challan_item:
                frappe.throw(
                    _("Row {0}: this Return Entry row is not linked to a row on gate pass {1}. "
                      "Build return entries with the Create &gt; Return Entry button so the link "
                      "is set.").format(row.idx, self.against_gate_pass)
                )

            source = source_rows.get(row.against_challan_item)
            if not source:
                frappe.throw(
                    _("Row {0}: the linked row no longer exists on gate pass {1}.").format(
                        row.idx, self.against_gate_pass)
                )

            already = returned.get(row.against_challan_item) or {}
            pending_qty = flt(source.qty) - flt(already.get("qty"))
            pending_weight = flt(source.weight_kg) - flt(already.get("weight_kg"))

            if flt(row.qty) - pending_qty > TOLERANCE:
                frappe.throw(
                    _("Row {0} ({1}): returning {2} but only {3} is still out against row {4} of "
                      "gate pass {5}.").format(
                          row.idx, source.material_description or "", flt(row.qty, 3),
                          flt(pending_qty, 3), source.idx, self.against_gate_pass)
                )

            if flt(row.weight_kg) - pending_weight > TOLERANCE:
                frappe.throw(
                    _("Row {0} ({1}): returning {2} Kg but only {3} Kg is still out against row "
                      "{4} of gate pass {5}.").format(
                          row.idx, source.material_description or "", flt(row.weight_kg, 3),
                          flt(pending_weight, 3), source.idx, self.against_gate_pass)
                )

    # ── status ──────────────────────────────────────────────────────────────

    def _set_status(self):
        self.status = _compute_status(self)


# ─────────────────────────────────────────────────────────────────────────────
# Status. One state machine, three callers (validate/submit/cancel, the return
# refresh, and the overdue sweep) -- so they cannot disagree about what a
# challan's status should be.
# ─────────────────────────────────────────────────────────────────────────────

def _compute_status(doc):
    if doc.docstatus == 2:
        return "Cancelled"
    if doc.docstatus == 0:
        return "Draft"
    if doc.challan_type == RETURN_ENTRY:
        return "Material In"
    if doc.challan_type == NON_RETURNABLE:
        return "Material Out"
    return _status_for_returnable(
        doc.expected_return_date, doc.returned_qty, doc.pending_qty
    )


def _status_for_returnable(expected_return_date, returned_qty, pending_qty):
    """The submitted-Returnable branch, kept separate so the overdue sweep can
    reuse it from stored column values without loading whole documents.

    Returned beats Overdue -- a late but complete return clears the flag.
    Overdue beats Partially Returned -- an overdue part-return is still overdue,
    and the exact split stays readable in returned_qty / pending_qty.
    """
    if flt(pending_qty) <= TOLERANCE:
        return "Returned"
    if expected_return_date and getdate(expected_return_date) < getdate(nowdate()):
        return "Overdue"
    if flt(returned_qty) > TOLERANCE:
        return "Partially Returned"
    return "Material Out"


# ─────────────────────────────────────────────────────────────────────────────
# Return netting
# ─────────────────────────────────────────────────────────────────────────────

def _returned_by_row(source_name, exclude_challan=None):
    """{source row name: {qty, weight_kg}} summed over SUBMITTED return entries."""
    conditions = ""
    values = {"source": source_name, "return_entry": RETURN_ENTRY}
    if exclude_challan:
        conditions = " and dc.name != %(exclude)s"
        values["exclude"] = exclude_challan

    rows = frappe.db.sql(
        """
        select dci.against_challan_item as row_name,
               sum(dci.qty) as qty,
               sum(dci.weight_kg) as weight_kg
        from `tabDelivery Challan Item` dci
        inner join `tabDelivery Challan` dc on dc.name = dci.parent
        where dc.docstatus = 1
          and dc.challan_type = %(return_entry)s
          and dc.against_gate_pass = %(source)s
          and ifnull(dci.against_challan_item, '') != ''
          {conditions}
        group by dci.against_challan_item
        """.format(conditions=conditions),
        values,
        as_dict=True,
    )
    return {r.row_name: {"qty": flt(r.qty), "weight_kg": flt(r.weight_kg)} for r in rows}


def _refresh_source_gate_pass(source_name):
    """Re-net a Returnable gate pass against every submitted return entry and
    re-derive its status. Called whenever a Return Entry is submitted or
    cancelled."""
    source = frappe.get_doc("Delivery Challan", source_name)
    if source.docstatus != 1 or source.challan_type != RETURNABLE:
        return

    returned = _returned_by_row(source_name)

    total_returned_qty = 0.0
    total_returned_weight = 0.0
    for row in source.items:
        got = returned.get(row.name) or {}
        row_qty = flt(got.get("qty"), 3)
        row_weight = flt(got.get("weight_kg"), 3)
        total_returned_qty += row_qty
        total_returned_weight += row_weight
        # Submitted parent: write the child columns straight to the database.
        frappe.db.set_value(
            "Delivery Challan Item",
            row.name,
            {"returned_qty": row_qty, "returned_weight_kg": row_weight},
            update_modified=False,
        )
        row.returned_qty = row_qty
        row.returned_weight_kg = row_weight

    values = {
        "returned_qty": flt(total_returned_qty, 3),
        "returned_weight_kg": flt(total_returned_weight, 3),
        "pending_qty": max(flt(flt(source.total_qty) - total_returned_qty, 3), 0.0),
        "pending_weight_kg": max(
            flt(flt(source.total_weight_kg) - total_returned_weight, 3), 0.0
        ),
    }
    for field, value in values.items():
        source.set(field, value)
    values["status"] = _compute_status(source)

    frappe.db.set_value("Delivery Challan", source_name, values, update_modified=False)


# ─────────────────────────────────────────────────────────────────────────────
# Overdue
#
# NOTE: sites/common_site_config.json on this bench sets "pause_scheduler": 1,
# and this app had no scheduler_events at all before this doctype. A purely
# scheduler-driven overdue flip would register cleanly and then never once run
# here -- silently. So the same function is reachable three ways: the daily
# scheduler hook (correct on the live server), the list view's onload, and the
# tests. The list view additionally derives the Overdue colour client-side so
# the indicator is right even before this call returns.
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def refresh_overdue_gate_passes():
    """Flip submitted Returnable gate passes past their return date to Overdue
    (and back out again when they are settled). Idempotent -- safe to call on
    every list view load."""
    candidates = frappe.get_all(
        "Delivery Challan",
        filters={
            "docstatus": 1,
            "challan_type": RETURNABLE,
            "status": ["in", ["Material Out", "Partially Returned", "Overdue"]],
        },
        fields=["name", "status", "expected_return_date", "returned_qty", "pending_qty"],
    )

    changed = 0
    for row in candidates:
        new_status = _status_for_returnable(
            row.expected_return_date, row.returned_qty, row.pending_qty
        )
        if new_status != row.status:
            frappe.db.set_value(
                "Delivery Challan", row.name, "status", new_status, update_modified=False
            )
            changed += 1

    if changed:
        frappe.db.commit()
    return changed


# ─────────────────────────────────────────────────────────────────────────────
# Creating a Return Entry from a Returnable gate pass
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def make_return_entry(source_name, target_doc=None):
    from frappe.model.mapper import get_mapped_doc

    # Refuse at the button, not later at save. get_mapped_doc's own validation only
    # checks docstatus, so without this a Non Returnable gate pass would happily
    # build a return entry and only complain once the user tried to save it.
    source = frappe.db.get_value(
        "Delivery Challan", source_name, ["docstatus", "challan_type"], as_dict=True
    )
    if not source:
        frappe.throw(_("Gate pass {0} does not exist.").format(source_name))
    if source.docstatus != 1:
        frappe.throw(
            _("Gate pass {0} is not submitted, so nothing has gone out against it "
              "yet.").format(source_name)
        )
    if source.challan_type != RETURNABLE:
        frappe.throw(
            _("Gate pass {0} is {1}, so nothing is expected back against it. A Return "
              "Entry can only be made against a Returnable gate pass.").format(
                  source_name, source.challan_type)
        )

    pending = _pending_by_row(source_name)

    def postprocess(source, target):
        target.challan_type = RETURN_ENTRY
        target.against_gate_pass = source.name
        target.expected_return_date = None
        target.gp_date = nowdate()
        target.status = "Draft"
        # Both belong to the outbound trip, not the return.
        target.ref_dc_no = None
        target.total_value_of_goods = 0
        target.material_received_by = None

    def update_item(source_row, target_row, source_parent):
        still_out = pending.get(source_row.name) or {}
        target_row.qty = flt(still_out.get("qty"), 3)
        target_row.weight_kg = flt(still_out.get("weight_kg"), 3)
        target_row.returned_qty = 0
        target_row.returned_weight_kg = 0

    doc = get_mapped_doc(
        "Delivery Challan",
        source_name,
        {
            "Delivery Challan": {
                "doctype": "Delivery Challan",
                "validation": {"docstatus": ["=", 1]},
            },
            "Delivery Challan Item": {
                "doctype": "Delivery Challan Item",
                # The row anchor that makes partial returns exact.
                "field_map": {"name": "against_challan_item"},
                "postprocess": update_item,
                "condition": lambda row: flt(
                    (pending.get(row.name) or {}).get("qty")
                ) > TOLERANCE
                or flt((pending.get(row.name) or {}).get("weight_kg")) > TOLERANCE,
            },
        },
        target_doc,
        postprocess,
    )

    if not doc.items:
        frappe.throw(
            _("Nothing is pending return against gate pass {0}.").format(source_name)
        )

    return doc


def _pending_by_row(source_name):
    """{source row name: {qty, weight_kg}} still out against a gate pass."""
    source_rows = frappe.get_all(
        "Delivery Challan Item",
        filters={"parent": source_name, "parenttype": "Delivery Challan"},
        fields=["name", "qty", "weight_kg"],
    )
    returned = _returned_by_row(source_name)

    pending = {}
    for row in source_rows:
        got = returned.get(row.name) or {}
        pending[row.name] = {
            "qty": max(flt(flt(row.qty) - flt(got.get("qty")), 3), 0.0),
            "weight_kg": max(flt(flt(row.weight_kg) - flt(got.get("weight_kg")), 3), 0.0),
        }
    return pending


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def gate_pass_return_query(doctype, txt, searchfield, start, page_len, filters):
    """Link query for `against_gate_pass`: only submitted Returnable gate passes
    that still have something out."""
    conditions = ""
    values = {
        "txt": "%%%s%%" % (txt or ""),
        "returnable": RETURNABLE,
        "tolerance": TOLERANCE,
        "start": start,
        "page_len": page_len,
    }
    if filters and filters.get("company"):
        conditions += " and dc.company = %(company)s"
        values["company"] = filters.get("company")

    return frappe.db.sql(
        """
        select dc.name, dc.party_display_name, dc.pending_qty
        from `tabDelivery Challan` dc
        where dc.docstatus = 1
          and dc.challan_type = %(returnable)s
          and ifnull(dc.pending_qty, 0) > %(tolerance)s
          and (dc.name like %(txt)s or ifnull(dc.party_display_name, '') like %(txt)s)
          {conditions}
        order by dc.gp_date asc, dc.name asc
        limit %(start)s, %(page_len)s
        """.format(conditions=conditions),
        values,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Party lookups. Both fill the form only when the field is blank, so a
# hand-corrected name or address survives every re-save.
# ─────────────────────────────────────────────────────────────────────────────

def _default_address(link_doctype, link_name):
    """The address to print for a party or the company.

    NOT frappe's get_default_address: where a record has several addresses and
    none is flagged primary -- which is the case for this company's Billing and
    Shipping pair -- that returns them in unstable order, so the same gate pass
    printed twice showed two different company addresses. Primary wins here, then
    the alphabetically first name, so a given document always prints the same.
    """
    row = frappe.db.sql(
        """
        select a.name
        from `tabAddress` a
        inner join `tabDynamic Link` dl
            on dl.parent = a.name and dl.parenttype = 'Address'
        where dl.link_doctype = %s and dl.link_name = %s
          and ifnull(a.disabled, 0) = 0
        order by ifnull(a.is_primary_address, 0) desc, a.name asc
        limit 1
        """,
        (link_doctype, link_name),
    )
    return row[0][0] if row else None


def _party_display_name(party_type, party):
    field = {"Supplier": "supplier_name", "Customer": "customer_name"}.get(party_type)
    if not field:
        return None
    return frappe.db.get_value(party_type, party, field) or party


def _party_address(party_type, party):
    if party_type == "Other":
        return None
    try:
        from frappe.contacts.doctype.address.address import get_address_display

        address = _default_address(party_type, party)
        if not address:
            return None
        return _html_to_lines(get_address_display(address))
    except Exception:
        # An address is a convenience on a gate pass, never a reason to block one.
        frappe.log_error(
            title="Delivery Challan: address lookup failed",
            message=frappe.get_traceback(),
        )
        return None


def _html_to_lines(html):
    import re

    if not html:
        return None
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line) or None


# ─────────────────────────────────────────────────────────────────────────────
# Print. get_delivery_challan_html and download_delivery_challan_pdf both render
# from the one builder, so the on-screen preview and the downloaded PDF can
# never drift apart -- the same arrangement as the Material Issue Plan batch
# plan (material_issue_plan.py).
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_delivery_challan_html(name):
    doc = frappe.get_doc("Delivery Challan", name)
    doc.check_permission("read")
    return _render_delivery_challan_html(doc)


@frappe.whitelist()
def download_delivery_challan_pdf(name):
    from frappe.utils.pdf import get_pdf

    doc = frappe.get_doc("Delivery Challan", name)
    doc.check_permission("read")
    html = _render_delivery_challan_html(doc)
    frappe.local.response.filename = "{0}.pdf".format(
        name.replace(" ", "-").replace("/", "-")
    )
    frappe.local.response.filecontent = get_pdf(html)
    frappe.local.response.type = "download"


_CHALLAN_CSS = """
<style>
.dc-page { font-family: Arial, Helvetica, sans-serif; color: #000; font-size: 11px; }
.dc-page .head { text-align: center; border: 1.5px solid #000; padding: 6px 8px; }
.dc-page .head h1 { margin: 0; font-size: 20px; letter-spacing: .3px; }
.dc-page .head .line { font-size: 11.5px; line-height: 1.45; }
.dc-page .title { background: #000; color: #fff; text-align: center; font-size: 14px;
    font-weight: bold; letter-spacing: .5px; padding: 4px 0; border: 1.5px solid #000;
    border-top: 0; }
.dc-page .title .off { color: #9a9a9a; font-weight: normal; }
.dc-page table { width: 100%; border-collapse: collapse; }
.dc-page td, .dc-page th { border: 1px solid #000; padding: 4px 6px; vertical-align: top; }
/* Fixed layout + a colgroup on every meta table. These used to be auto-layout
   with `white-space: nowrap; width: 1%` on the labels, and three long ones
   ("Expected Date of Return", "Production Plan No", "Total Value of Goods")
   pushed the table's min-content width past 100% -- so the whole right-hand
   column ran off the page and Vehicle No, Driver Name and Mobile No printed
   cut in half. Labels now wrap instead of forcing the table wider. */
.dc-page .meta { table-layout: fixed; }
.dc-page .meta td { height: 20px; word-wrap: break-word; }
/* wkhtmltopdf breaks a line at any hyphen, which split '03-09-2026' and
   'PP-INT-2026-00001' across two and three lines. Short values are pinned. */
.dc-page .nw { white-space: nowrap; }
.dc-page .lbl { font-weight: bold; }
.dc-page .to .cap { font-weight: bold; }
.dc-page .to .who { font-weight: bold; font-size: 12.5px; }
.dc-page .to .addr { white-space: pre-line; line-height: 1.4; }
.dc-page .gpno { font-size: 18px; font-weight: bold; text-align: center; }
/* Fixed layout with an explicit colgroup: left to itself the browser hands the
   widest HEADER the widest column, which gave "Weight in Kgs" more room than
   Material Description. */
.dc-page .items { table-layout: fixed; }
.dc-page .items th { background: #efefef; text-align: center; font-weight: bold; }
.dc-page .items td { word-wrap: break-word; }
.dc-page .items td.num { text-align: right; }
.dc-page .items td.ctr { text-align: center; }
.dc-page .items tr.total td { font-weight: bold; }
.dc-page .items .pad td { height: 18px; }
.dc-page .terms { border: 1px solid #000; border-top: 0; padding: 5px 7px; font-size: 10px;
    line-height: 1.45; }
.dc-page .terms .cap { font-weight: bold; text-decoration: underline; }
.dc-page .terms ol { margin: 3px 0 0 16px; padding: 0; }
/* Four equal boxes, as the pad prints them. Without the fixed layout the
   "For <company>" line in the last cell ate ~80% of the row and squeezed the
   other three signature labels into an unreadable sliver. */
.dc-page .sign { table-layout: fixed; }
.dc-page .sign td { width: 25%; height: 62px; position: relative; font-size: 10px;
    padding-bottom: 18px; }
.dc-page .sign .for { font-weight: bold; }
.dc-page .sign .who { color: #333; }
.dc-page .sign .role { font-weight: bold; text-align: center; }
.dc-page .note { margin-top: 6px; font-size: 10px; }
</style>
"""


def _esc(value):
    if value is None or value == "":
        return ""
    return frappe.utils.escape_html(str(value))


def _date(value):
    if not value:
        return ""
    return '<span class="nw">{0}</span>'.format(frappe.utils.formatdate(value))


def _num(value):
    return "{:,.3f}".format(flt(value)).rstrip("0").rstrip(".") if flt(value) else ""


def _company_header(company):
    """Name, address, GST/CIN and phone for the letterhead block. Everything but
    the name is best-effort -- a missing address must not stop a gate pass
    printing."""
    lines = []
    gstin = ""
    phone = ""
    try:
        address = _default_address("Company", company)
        if address:
            fields = frappe.db.get_value(
                "Address",
                address,
                ["address_line1", "address_line2", "city", "state", "pincode",
                 "country", "phone", "gstin"],
                as_dict=True,
            ) or {}
            # Address lines are hand-typed and often already end in a comma,
            # which turned the join into "PuduKudi,, SIDCO Industrial Estate".
            street = ", ".join(
                p.strip().rstrip(",").strip()
                for p in [fields.get("address_line1"), fields.get("address_line2")]
                if p and p.strip().rstrip(",").strip()
            )
            locality = ", ".join(
                p for p in [fields.get("city"), fields.get("state")] if p
            )
            if fields.get("pincode"):
                locality = "{0}-{1}".format(locality, fields.get("pincode")).strip("-")
            if street:
                lines.append(street)
            if locality:
                lines.append(locality)
            gstin = fields.get("gstin") or ""
            phone = fields.get("phone") or ""
    except Exception:
        frappe.log_error(
            title="Delivery Challan: company address lookup failed",
            message=frappe.get_traceback(),
        )

    if not gstin:
        gstin = frappe.db.get_value("Company", company, "gstin") or ""
    if not phone:
        phone = frappe.db.get_value("Company", company, "phone_no") or ""

    return lines, gstin, phone


def _title_bar(challan_type):
    if challan_type == RETURN_ENTRY:
        return "DELIVERY CHALLAN (RETURN ENTRY)"
    on, off = ("RETURNABLE", "NON RETURNABLE")
    if challan_type == NON_RETURNABLE:
        on, off = ("NON RETURNABLE", "RETURNABLE")
    return 'DELIVERY CHALLAN (<span>{0}</span> / <span class="off">{1}</span>)'.format(on, off)


def _render_delivery_challan_html(doc):
    address_lines, gstin, phone = _company_header(doc.company)

    head_lines = "".join(
        '<div class="line">{0}</div>'.format(_esc(line)) for line in address_lines
    )
    if gstin:
        head_lines += '<div class="line">GST NO : {0}</div>'.format(_esc(gstin))
    if phone:
        head_lines += '<div class="line"><b>{0}</b></div>'.format(_esc(phone))

    # ── To / GP block ───────────────────────────────────────────────────────
    to_block = '<div class="cap">To.</div>'
    if doc.party_display_name:
        to_block += '<div class="who">{0}</div>'.format(_esc(doc.party_display_name))
    if doc.party_address:
        to_block += '<div class="addr">{0}</div>'.format(_esc(doc.party_address))

    meta_top = (
        '<table class="meta">'
        '<colgroup><col style="width:62%"><col style="width:14%">'
        '<col style="width:24%"></colgroup>'
        '<tr>'
        '<td class="to" rowspan="2">{to}</td>'
        '<td class="lbl">GP No.</td><td class="gpno">{gp_no}</td>'
        '</tr>'
        '<tr><td class="lbl">GP Date</td><td>{gp_date}</td></tr>'
        '</table>'
    ).format(to=to_block, gp_no=_esc(doc.name), gp_date=_date(doc.gp_date))

    # Row 3 column 1 carries the return date on an outbound pass, and the gate
    # pass being returned against on a Return Entry.
    if doc.challan_type == RETURN_ENTRY:
        third_label, third_value = "Against Gate Pass", _esc(doc.against_gate_pass)
    else:
        third_label, third_value = (
            "Expected Date of Return",
            _date(doc.expected_return_date),
        )

    meta_grid = (
        '<table class="meta">'
        # Three label/value pairs across, matching the pad's own 3x3 grid. The
        # widths are deliberate: column 1 holds "Expected Date of Return" and
        # column 3 "Total Value of Goods", the two longest labels.
        '<colgroup>'
        '<col style="width:20%"><col style="width:15%">'
        '<col style="width:18%"><col style="width:18%">'
        '<col style="width:11%"><col style="width:18%">'
        '</colgroup>'
        '<tr><td class="lbl">Job No.</td><td>{job}</td>'
        '<td class="lbl">Production Plan No</td><td>{pp}</td>'
        '<td class="lbl">Vehicle No</td><td>{veh}</td></tr>'
        '<tr><td class="lbl">Ref. DC. No.</td><td>{ref}</td>'
        '<td class="lbl">WO Date</td><td>{wo}</td>'
        '<td class="lbl">Driver Name</td><td>{drv}</td></tr>'
        '<tr><td class="lbl">{t_lbl}</td><td>{t_val}</td>'
        '<td class="lbl">Total Value of Goods</td><td>{val}</td>'
        '<td class="lbl">Mobile No</td><td>{mob}</td></tr>'
        '</table>'
    ).format(
        job=_esc(doc.job_no),
        pp=_esc(doc.production_plan),
        veh=_esc(doc.vehicle_no),
        ref=_esc(doc.ref_dc_no),
        wo=_date(doc.wo_date),
        drv=_esc(doc.driver_name),
        t_lbl=third_label,
        t_val=third_value,
        val=frappe.utils.fmt_money(doc.total_value_of_goods, currency=None)
        if flt(doc.total_value_of_goods)
        else "",
        mob=_esc(doc.mobile_no),
    )

    # ── Items ───────────────────────────────────────────────────────────────
    item_rows = "".join(
        '<tr><td class="ctr">{idx}</td><td>{desc}</td><td class="ctr">{uom}</td>'
        '<td class="num">{qty}</td><td class="num">{wt}</td><td>{purpose}</td>'
        '<td>{remarks}</td></tr>'.format(
            idx=row.idx,
            desc=_esc(row.material_description),
            uom=_esc(row.uom),
            qty=_num(row.qty),
            wt=_num(row.weight_kg),
            purpose=_esc(row.purpose),
            remarks=_esc(row.remarks),
        )
        for row in doc.items
    )
    # Keep the printed table roughly pad-height so it can be written on.
    for _i in range(max(0, 8 - len(doc.items))):
        item_rows += '<tr class="pad"><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>'

    items_table = (
        '<table class="items">'
        '<colgroup>'
        '<col style="width:6%"><col style="width:32%"><col style="width:8%">'
        '<col style="width:8%"><col style="width:12%"><col style="width:15%">'
        '<col style="width:19%">'
        '</colgroup>'
        '<tr><th>Sl No</th><th>Material Description</th><th>UOM</th><th>Qty</th>'
        '<th>Weight in Kgs</th><th>Purpose</th><th>Remarks</th></tr>'
        '{rows}'
        '<tr class="total"><td colspan="3" style="text-align:center">Total</td>'
        '<td class="num">{tq}</td><td class="num">{tw}</td><td></td><td></td></tr>'
        '</table>'
    ).format(rows=item_rows, tq=_num(doc.total_qty), tw=_num(doc.total_weight_kg))

    # ── Terms ───────────────────────────────────────────────────────────────
    terms = (
        '<div class="terms"><span class="cap">Terms &amp; Conditions : -</span>{body}</div>'
    ).format(body=doc.terms or DEFAULT_TERMS)

    # ── Sign-off ────────────────────────────────────────────────────────────
    def sign_cell(role, who, for_line=""):
        top = '<div class="for">{0}</div>'.format(_esc(for_line)) if for_line else ""
        name = '<div class="who">{0}</div>'.format(_esc(who)) if who else ""
        return '<td>{top}{name}<div class="role" style="position:absolute;bottom:4px;left:0;right:0">{role}</div></td>'.format(
            top=top, name=name, role=_esc(role)
        )

    sign = (
        '<table class="sign"><tr>'
        + sign_cell("Material Received by", doc.material_received_by)
        + sign_cell("Production / Planning", doc.production_planning_by)
        + sign_cell("Stores Incharge", doc.stores_incharge)
        + sign_cell(
            "Factory Head",
            doc.factory_head,
            for_line="For {0}".format(doc.company or ""),
        )
        + "</tr></table>"
    )

    note = ""
    if doc.challan_type == RETURNABLE and doc.docstatus == 1:
        note = (
            '<div class="note">Status: <b>{status}</b> &nbsp;|&nbsp; Returned: {rq} '
            "&nbsp;|&nbsp; Pending: {pq}</div>"
        ).format(
            status=_esc(doc.status),
            rq=_num(doc.returned_qty) or "0",
            pq=_num(doc.pending_qty) or "0",
        )

    return (
        _CHALLAN_CSS
        + '<div class="dc-page">'
        + '<div class="head"><h1>{name}</h1>{lines}</div>'.format(
            name=_esc(doc.company), lines=head_lines
        )
        + '<div class="title">{0}</div>'.format(_title_bar(doc.challan_type))
        + meta_top
        + meta_grid
        + items_table
        + terms
        + sign
        + note
        + "</div>"
    )
