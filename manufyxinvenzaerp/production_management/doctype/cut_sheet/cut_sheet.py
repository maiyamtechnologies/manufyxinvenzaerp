"""Cut Sheet -- a nesting plan for one physical sheet, shared across jobs.

A plate arrives as one batch and is cut into repeated pieces (W1), leaving a
remnant (W2). Before this doctype the cut was described row by row on each
Material Planning / Material Issue Plan line, which meant re-typing the balance on
every row and gave no way for two jobs to draw from the same sheet without each
one claiming the whole thing.

Here the nesting is stated ONCE against the batch: this piece, this many of them,
this remnant. Jobs then take pieces from it the same way they reserve batch stock
-- a Sec Nos figure with an available remainder -- and the same sheet can serve
several Material Plannings.

Nothing here is physical. There is no stock ledger behind W1: the batch still
holds its own Kg and the real movement is the ordinary Material Issue Plan
transfer, which simply carries W1's dimensions instead of the batch's. What this
document owns is the arithmetic and the bookkeeping of who has claimed what.

W2 is written onto the batch when the FIRST transfer from this sheet is submitted
(the client's rule -- the sheet is physically cut at that point, whether or not
every piece has been issued yet), and taken back off if that transfer is
cancelled. See apply_w2_to_batch / revert_w2_from_batch.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now

from manufyxinvenzaerp.utils.decision_log import log_decision
from manufyxinvenzaerp.utils.dimension_formula import calculate_qty

# Sec Nos comparisons are made to 3 decimals everywhere else in this app; the same
# slack keeps "allocated exactly everything" from failing on a float remainder.
QTY_EPSILON = 0.001


class CutSheet(Document):
    # The cut itself: the piece being taken and the off-cut left behind. Once a job
    # is holding pieces of this sheet, none of these may move under it.
    CUT_FIELDS = (
        ("w1_length", "W1 Length"),
        ("w1_width", "W1 Width"),
        ("w1_sec_qty", "W1 Sec Nos"),
        ("w2_length", "W2 Length"),
        ("w2_width", "W2 Width"),
        ("w2_sec_qty", "W2 Sec Nos"),
    )

    # What this sheet IS: the company, the material, the physical batch and where
    # that batch sits. Chosen once, when the sheet is created.
    IDENTITY_FIELDS = (
        ("company", "Company"),
        ("item_code", "Item Code"),
        ("batch_no", "Batch"),
        ("warehouse", "Warehouse"),
    )

    def validate(self):
        self._block_identity_changes()
        self._fetch_batch_dimensions()
        self._block_cut_changes_while_claimed()
        self._sync_allocations_from_rows()
        self._calculate()
        self._validate_allocations_fit()
        self._set_status()

    def _sync_allocations_from_rows(self):
        """Rebuild the Allocations table from the Material Mapping rows actually
        holding pieces of this sheet.

        The rows are the truth, not this table. A batch can be put on a Material
        Mapping row by hand through Update Batch, which never goes near
        allocate_cut_sheet -- so a table maintained only by that one path missed
        those claims entirely and the sheet reported 0 allocated while a job was
        genuinely holding pieces. Deriving it here means the figures are right no
        matter how the batch got onto the row, and the same query backs the
        availability check in material_planning._sync_cut_sheet_flag, so the two
        can no longer disagree.

        Transfer state (stock_entry / is_consumed / allocated_on) is carried over
        per source row, since that is this table's own bookkeeping and cannot be
        recovered from the mapping row."""
        if not self.name or str(self.name).startswith("new-"):
            return

        previous = {a.source_row: a for a in (self.allocations or []) if a.source_row}

        claims = frappe.get_all(
            "Material Planning Material Mapping",
            filters={"cut_sheet_ref": self.name, "is_reserved": 1},
            fields=["name", "parent", "duno_mark_no", "batch_sec_qty", "batch_calc_qty"],
            order_by="parent asc, idx asc",
        )

        self.allocations = []
        for c in claims:
            old = previous.get(c.name)
            self.append("allocations", {
                "material_planning": c.parent,
                "source_table": "Material Planning Material Mapping",
                "source_row": c.name,
                "duno_mark_no": c.duno_mark_no or "",
                "sec_qty": flt(c.batch_sec_qty),
                "qty": flt(c.batch_calc_qty),
                "allocated_on": (old.allocated_on if old else None) or now(),
                "stock_entry": old.stock_entry if old else None,
                "is_consumed": old.is_consumed if old else 0,
            })

    def on_trash(self):
        """A sheet cannot vanish while anything is still standing on it, and if it
        does go it has to put the batch back the way it found it.

        Three things can be standing on it: a Material Planning row still pointing
        at it (reserved or not -- either way the row would be left referring to a
        plan that no longer exists), a transfer already taken from it, and the
        balance written onto the batch.

        That last one is why this method exists in its present form. W2 replaces
        the batch's Length and Sec Qty with the remnant's, and the batch keeps its
        original name -- so once the sheet is gone there is nothing left on the
        site that explains why a batch called ...L12000... says 6000, and nothing
        that knows what to restore. The ledger still holds every kilo, so the
        Manufyx Stock Balance report and Material Planning -- which works from the
        dimensions -- disagree, with no visible cause. Reverting here is what keeps
        deletion from being a one-way door.

        Only plans that still EXIST can object. An allocation naming a deleted
        Material Planning is a dangling row, not a claim: it protects nothing, and
        counting it made the sheet permanently undeletable -- the error named a
        plan the user could not go and release, because it was already gone."""
        self._block_if_claimed()
        self._block_if_transferred()

        # Nothing is holding it: hand the batch back its own dimensions before the
        # record that knows them disappears.
        if self.w2_applied:
            revert_w2_from_batch(self.name)

    def _block_identity_changes(self):
        """A saved Cut Sheet cannot be re-pointed at different material.

        Every figure on this document is derived from one physical plate in one
        warehouse -- the sheet's own dimensions are read off that batch, the cut is
        planned against them, and jobs allocate pieces of it. Repointing a saved
        sheet at another batch keeps the cut, the allocations and the status while
        changing what they describe, which is not an edit anybody could mean. Make
        a new sheet for a different plate.
        """
        before = self.get_doc_before_save()
        if not before:
            return

        changed = [
            label for field, label in self.IDENTITY_FIELDS
            if (self.get(field) or "") != (before.get(field) or "")
        ]
        if changed:
            frappe.throw(
                _("{0} cannot be changed after a Cut Sheet is saved — every figure on it "
                  "describes one plate in one warehouse. Create a new Cut Sheet for "
                  "different material.")
                .format(", ".join(changed)),
                title=_("Cannot Change What Is Being Cut"),
            )

    def claiming_rows(self):
        """Material Planning rows holding pieces of this sheet, live from the
        database. Both raw-material tables carry a cut-sheet reference.

        Not read from self.allocations: that table is rebuilt during validate, so on
        a document loaded and edited it holds whatever was true when it was last
        written -- a claim made since then would not appear in it."""
        rows = []
        for child_dt in (
            "Material Planning Material Mapping",
            "Material Planning Available Raw Material",
        ):
            for r in frappe.get_all(
                child_dt,
                filters={"cut_sheet_ref": self.name},
                fields=["name", "parent", "idx", "item_code", "is_reserved"],
            ):
                if frappe.db.exists("Material Planning", r.parent):
                    r.child_doctype = child_dt
                    rows.append(r)
        return rows

    def _block_cut_changes_while_claimed(self):
        """The cut cannot be re-drawn under a job that is already planning to it.

        A Material Issue Plan does not keep its own copy of these sizes -- it reads
        W1/W2 back off this sheet every time its raw materials refresh
        (material_issue_plan._cut_sheet_reference) -- so changing them here silently
        rewrites what an existing plan will transfer, for material somebody already
        committed to. The planner never sees the change and never agreed to it.

        Only _validate_allocations_fit guarded any of this before, and only for one
        case: W1 Sec Nos reduced below the number of pieces taken. Length and Width,
        on both W1 and W2, could be changed freely with jobs holding the sheet.

        The way through is deliberate rather than blocked: release the allocations
        (Release Allocations, which refuses while anything is reserved), then the
        sizes are free and the plan picks up the new ones when its batch is
        assigned again."""
        before = self.get_doc_before_save()
        if not before:
            return  # new sheet -- nothing can be claiming it yet

        changed = [
            label for field, label in self.CUT_FIELDS
            if flt(self.get(field), 3) != flt(before.get(field), 3)
        ]
        if not changed:
            return

        claims = self.claiming_rows()
        if not claims:
            return

        by_plan = {}
        for r in claims:
            by_plan.setdefault(r.parent, []).append(r)
        described = "<br>".join(
            "<b>{0}</b> — row {1}{2}".format(
                plan,
                ", ".join(str(r.idx) for r in sorted(rows_, key=lambda x: x.idx)),
                _(" (reserved)") if any(r.is_reserved for r in rows_) else "",
            )
            for plan, rows_ in sorted(by_plan.items())
        )
        frappe.throw(
            _("{0} cannot be changed — this Cut Sheet is already being planned from:"
              "<br><br>{1}<br><br>"
              "Use <b>Release Allocations</b> to hand the pieces back first. Anything "
              "still reserved has to be unreserved on its Material Planning before "
              "that will work, so the plan is re-made deliberately rather than "
              "changing underneath it.")
            .format(", ".join(changed), described),
            title=_("Cut Sheet In Use"),
        )

    def _block_if_claimed(self):
        """Material Planning rows still pointing at this sheet.

        Read from the database, not from self.allocations: that table is rebuilt
        during validate, so on a document loaded and deleted without saving it
        holds whatever was true when it was last written. A claim made since then
        would not appear in it, and the sheet would delete out from under a
        reserved row."""
        claims = frappe.get_all(
            "Material Planning Material Mapping",
            filters={"cut_sheet_ref": self.name},
            fields=["parent", "is_reserved"],
        )
        live = {}
        for c in claims:
            if frappe.db.exists("Material Planning", c.parent):
                live[c.parent] = live.get(c.parent) or c.is_reserved
        if not live:
            return
        described = ", ".join(
            "{0}{1}".format(mp, _(" (reserved)") if reserved else "")
            for mp, reserved in sorted(live.items())
        )
        frappe.throw(
            _("This Cut Sheet is in use by {0}. Release those allocations first.")
            .format(described)
        )

    def _block_if_transferred(self):
        """Transfers taken from this sheet.

        A submitted transfer is the physical cut: the steel has moved and the
        batch has been rewritten to match. Reverting the batch under a live
        transfer would claim the sheet is whole again while its pieces are out on
        the floor, so the transfer has to be cancelled first -- which reverts the
        batch through the ordinary path."""
        names = {a.stock_entry for a in (self.allocations or []) if a.stock_entry}
        if self.w2_applied_stock_entry:
            names.add(self.w2_applied_stock_entry)
        live = sorted(
            n for n in names
            if frappe.db.get_value("Stock Entry", n, "docstatus") == 1
        )
        if live:
            frappe.throw(
                _("Material has already been transferred from this Cut Sheet by {0}. "
                  "Cancel {1} first — that puts the batch's dimensions back — and then "
                  "delete this sheet.")
                .format(", ".join(live), _("it") if len(live) == 1 else _("them"))
            )

    # ── derived values ────────────────────────────────────────────────────────

    def _fetch_batch_dimensions(self):
        """The sheet's own size, read from the batch rather than typed, so the two can
        never disagree. Thickness in particular is the batch's for good: cutting
        changes Length and Width only."""
        if not self.batch_no:
            return
        batch = frappe.db.get_value(
            "Batch", self.batch_no,
            ["item", "custom_length", "custom_width", "custom_thickness", "custom_sec_qty"],
            as_dict=True,
        )
        if not batch:
            return
        if self.item_code and batch.item and batch.item != self.item_code:
            frappe.throw(
                _("Batch {0} belongs to item {1}, not {2}.")
                .format(self.batch_no, batch.item, self.item_code)
            )
        self.item_code = self.item_code or batch.item
        self.sheet_length = flt(batch.custom_length)
        self.sheet_width = flt(batch.custom_width)
        self.sheet_thickness = flt(batch.custom_thickness)
        self.sheet_sec_qty = flt(batch.custom_sec_qty)

    def _calculate(self):
        group = self.parent_item_group
        unit_weight = flt(self.unit_weight)

        self.sheet_qty = flt(calculate_qty(
            group, self.sheet_length, self.sheet_width, self.sheet_thickness,
            unit_weight, self.sheet_sec_qty or 1,
        ) or 0, 3)

        # Kg for ONE piece -- displayed, and the basis for a partial claim.
        self.w1_qty_per_nos = flt(calculate_qty(
            group, self.w1_length, self.w1_width, self.sheet_thickness, unit_weight, 1,
        ) or 0, 3)
        # Totals are computed at FULL precision from the dimensions, never as
        # (rounded per-piece x count). A 500x250x5 piece is 4.90625 Kg, which stores
        # as 4.906 -- times four that is 19.624 instead of 19.625, and one milligram
        # is enough to make a requirement of exactly 19.625 Kg look uncovered.
        self.w1_total_qty = flt(calculate_qty(
            group, self.w1_length, self.w1_width, self.sheet_thickness,
            unit_weight, self.w1_sec_qty,
        ) or 0, 3)

        # W2 is what the sheet has LEFT once W1 comes off it, not an independent
        # measurement. Calculating both halves from their own dimensions let them
        # disagree with the sheet they came from: the stock entry consumes W1, so the
        # batch is left holding (sheet - W1) while W2 claimed something else, and the
        # batch's available qty stopped matching its own W2 details. Deriving it means
        # they cannot drift apart. The W2 DIMENSIONS stay entered by hand -- they
        # describe the off-cut's shape, which cannot be inferred (a plate can be cut
        # along either edge) -- and are what gets written onto the batch.
        self.w2_calc_qty = flt(max(self.sheet_qty - self.w1_total_qty, 0.0), 3)

        self.allocated_sec_qty = flt(sum(flt(a.sec_qty) for a in (self.allocations or [])), 3)
        self.allocated_qty = flt(sum(flt(a.qty) for a in (self.allocations or [])), 3)
        self.available_sec_qty = flt(flt(self.w1_sec_qty) - self.allocated_sec_qty, 3)
        self.available_qty = flt(calculate_qty(
            group, self.w1_length, self.w1_width, self.sheet_thickness,
            unit_weight, self.available_sec_qty,
        ) or 0, 3)

    def _validate_allocations_fit(self):
        """Reducing W1 Sec Nos below what jobs have already taken would silently
        oversubscribe the sheet."""
        if self.allocated_sec_qty - flt(self.w1_sec_qty) > QTY_EPSILON:
            frappe.throw(
                _("{0} pieces are already allocated to other jobs, so W1 Sec Nos cannot be set to {1}. "
                  "Release an allocation first.")
                .format(flt(self.allocated_sec_qty, 3), flt(self.w1_sec_qty, 3))
            )

    def _set_status(self):
        # Inactive is a decision, not a derived state: someone set this sheet aside
        # and said why. Recomputing over it would quietly bring it back to Active on
        # the next save.
        if self.status == "Inactive":
            return
        if self.w2_applied:
            self.status = "Consumed"
        elif not flt(self.w1_sec_qty):
            self.status = "Draft"
        elif flt(self.available_sec_qty) <= QTY_EPSILON:
            self.status = "Fully Allocated"
        else:
            self.status = "Active"


# ── suggestion helper ─────────────────────────────────────────────────────────

@frappe.whitelist()
def suggest_w1_sec_qty(cut_sheet_name=None, sheet_length=None, sheet_width=None,
                       w1_length=None, w1_width=None):
    """How many W1 pieces the sheet could yield, purely geometrically.

    Offered as a starting point only -- the real answer depends on the nesting and
    the saw, so the client's rule is that the user types the figure. Deliberately
    NOT derived from Kg: a 1800x6300 sheet is 2.1 times the weight of a 1800x3000
    piece, but it yields 2 of them, and a Kg-based figure would over-issue on every
    sheet."""
    if cut_sheet_name:
        cs = frappe.db.get_value(
            "Cut Sheet", cut_sheet_name,
            ["sheet_length", "sheet_width", "w1_length", "w1_width"], as_dict=True,
        ) or {}
        sheet_length = sheet_length or cs.get("sheet_length")
        sheet_width = sheet_width or cs.get("sheet_width")
        w1_length = w1_length or cs.get("w1_length")
        w1_width = w1_width or cs.get("w1_width")

    sheet_length, sheet_width = flt(sheet_length), flt(sheet_width)
    w1_length, w1_width = flt(w1_length), flt(w1_width)
    if not (sheet_length and w1_length):
        return 0

    # Plates nest in two directions; a structural section only runs along its length.
    if sheet_width and w1_width:
        along = int(sheet_length // w1_length) * int(sheet_width // w1_width)
        rotated = int(sheet_length // w1_width) * int(sheet_width // w1_length)
        return max(along, rotated)
    return int(sheet_length // w1_length)


# ── allocation ────────────────────────────────────────────────────────────────
#
# A cut allocation is deliberately shaped like an ordinary batch reservation: the
# Material Mapping row keeps the REAL batch (so the stock ledger and every transfer
# path work untouched) and carries W1's dimensions in its batch_* fields. That is
# the whole trick -- downstream code never needs to know a Cut Sheet exists, it just
# sees a row reserving so many Kg of a batch at these dimensions.

@frappe.whitelist()
def get_available_cut_sheets(mp_name, item_code=None):
    """Cut Sheets with pieces still free, for the mapping picker. Filtered to the
    Material Planning's own company, and to one item when the picker is opened from
    a row that already knows what it needs."""
    mp = frappe.db.get_value("Material Planning", mp_name, ["company", "for_warehouse"], as_dict=True)
    if not mp:
        frappe.throw(_("Material Planning {0} not found.").format(mp_name))

    # Inactive sheets are set aside deliberately and must stop being offered as
    # material to cut -- that is what marking one Inactive is for.
    filters = {"company": mp.company, "w2_applied": 0, "status": ["!=", "Inactive"]}
    if item_code:
        filters["item_code"] = item_code

    rows = frappe.get_all(
        "Cut Sheet", filters=filters,
        fields=["name", "item_code", "item_name", "parent_item_group", "unit_weight",
                "batch_no", "warehouse", "sheet_length", "sheet_width", "sheet_thickness",
                "w1_length", "w1_width", "w1_sec_qty", "w1_qty_per_nos",
                "available_sec_qty", "available_qty", "status"],
        order_by="modified desc",
    )
    return [r for r in rows if flt(r.available_sec_qty) > QTY_EPSILON]


@frappe.whitelist()
def get_cut_sheet_for_batch(batch_no, exclude_row=None):
    """The nesting plan against a batch, if it has one, for the moment a batch is
    picked on a Material Mapping row.

    The server-side sync only runs on save, which left the user selecting a batch and
    seeing nothing about the cut until they saved -- so this answers the same question
    immediately, and the row can show W1's size and the free piece count straight
    away. exclude_row keeps the row's own claim from counting against itself."""
    if not batch_no:
        return None
    cs = frappe.db.get_value(
        "Cut Sheet", {"batch_no": batch_no, "status": ["!=", "Inactive"]},
        ["name", "item_code", "parent_item_group", "unit_weight", "status",
         "sheet_length", "sheet_width", "sheet_thickness",
         "w1_length", "w1_width", "w1_sec_qty", "w1_qty_per_nos",
         "w2_length", "w2_width", "w2_sec_qty", "w2_calc_qty", "w2_applied"],
        as_dict=True,
    )
    if not cs:
        return None

    taken_by_others = flt(sum(
        flt(c.batch_sec_qty) for c in frappe.get_all(
            "Material Planning Material Mapping",
            filters={"cut_sheet_ref": cs.name, "is_reserved": 1},
            fields=["name", "batch_sec_qty"])
        if c.name != exclude_row
    ), 3)
    cs["available_sec_qty"] = flt(flt(cs.w1_sec_qty) - taken_by_others, 3)
    cs["allocated_sec_qty"] = taken_by_others
    return cs


@frappe.whitelist()
def allocate_cut_sheet(mp_name, cut_sheet_name, sec_qty, row_name=None, unavailable_item_row=None):
    """Take `sec_qty` pieces off a Cut Sheet and reserve them into a Material Mapping
    row -- either an existing row, or a new one covering an Unavailable Item.

    Partial by design: 10 pieces on the sheet can go 2 to this plan, 2 to the next,
    and the rest stay free. What is taken here is recorded on the Cut Sheet itself,
    so the sheet is the one place that knows who holds what."""
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        BATCH_CUT_SHEET_MAPPED, _release_row_pool_claims,
    )

    mp = frappe.get_doc("Material Planning", mp_name)
    if not frappe.has_permission("Material Planning", "write", doc=mp):
        frappe.throw(_("Not permitted to modify this Material Planning"), frappe.PermissionError)

    sec_qty = flt(sec_qty)
    if sec_qty <= 0:
        frappe.throw(_("Enter how many pieces to take (Sec Nos greater than 0)."))

    cs = frappe.get_doc("Cut Sheet", cut_sheet_name)
    if cs.w2_applied:
        frappe.throw(_("This sheet has already been cut and its balance written back to batch {0}.")
                     .format(cs.batch_no))
    if sec_qty - flt(cs.available_sec_qty) > QTY_EPSILON:
        frappe.throw(
            _("Only {0} piece(s) are still free on this Cut Sheet — {1} requested.")
            .format(flt(cs.available_sec_qty, 3), flt(sec_qty, 3))
        )

    # Full precision, not sec_qty x the rounded per-piece figure -- see _calculate.
    qty = flt(calculate_qty(
        cs.parent_item_group, cs.w1_length, cs.w1_width, cs.sheet_thickness,
        flt(cs.unit_weight), sec_qty,
    ) or 0, 3)

    if row_name:
        row = next((r for r in mp.material_mapping if r.name == row_name), None)
        if not row:
            frappe.throw(_("Row {0} not found.").format(row_name))
        if row.item_code and row.item_code != cs.item_code:
            frappe.throw(
                _("This Cut Sheet is for <b>{0}</b>, but row {1} is planned for <b>{2}</b>.")
                .format(cs.item_code, row.idx, row.item_code)
            )
        # Whatever this row was drawing from before -- another cut sheet, an excess
        # claim -- is handed back before it takes something new, or the old pool would
        # go on believing this row still holds its pieces.
        _release_row_pool_claims(row)
        row.is_reserved = 0
        row.reserved_qty = 0
        row.shortfall_qty = 0
        row.reserved_on = None
    else:
        base = {
            "item_number": "", "sales_order": "", "item_code": cs.item_code,
            "item_name": cs.item_name or cs.item_code, "bom_no": "", "drawing": "",
            "duno_mark_no": "", "customer_drawing_number": "",
        }
        if unavailable_item_row:
            src = next((r for r in (mp.unavailable_items or []) if r.name == unavailable_item_row), None)
            if not src:
                frappe.throw(_("Unavailable Item row {0} not found.").format(unavailable_item_row))
            if src.item_code != cs.item_code:
                frappe.throw(
                    _("This Cut Sheet is for {0}, which does not match the Unavailable Item row's {1}.")
                    .format(cs.item_code, src.item_code)
                )
            base.update({
                "item_number": src.item_number, "sales_order": src.sales_order,
                "bom_no": src.bom_no, "drawing": src.drawing,
                "duno_mark_no": src.duno_mark_no,
                "customer_drawing_number": src.customer_drawing_number,
            })
            old_qty = flt(src.qty)
            remaining = flt(old_qty - qty, 3)
            if remaining <= QTY_EPSILON:
                mp.unavailable_items = [r for r in mp.unavailable_items if r.name != unavailable_item_row]
            else:
                ratio = (remaining / old_qty) if old_qty else 0.0
                src.qty = remaining
                src.sec_qty = flt(flt(src.sec_qty) * ratio, 3)
        row = mp.append("material_mapping", base)

    # The REAL batch, carrying W1's dimensions -- so the row describes the piece it
    # will actually receive, and the ordinary dimensional checks hold.
    #
    # reserve_without_dimensions is deliberately OFF. It means the reverse of a cut:
    # "Kg is what was asked for, Sec Nos is that weight expressed as a fraction of the
    # batch". Here the piece COUNT is what the user chose and the Kg follows from it,
    # so leaving the flag on had reserve_batches recompute Sec Nos back out of the
    # requirement's weight and quietly replace the count.
    row.batch = cs.batch_no
    row.planned_item = cs.item_code
    row.batch_mapped = BATCH_CUT_SHEET_MAPPED
    row.reserve_without_dimensions = 0
    row.cut_sheet = 1
    row.cut_sheet_ref = cs.name
    row.batch_parent_item_group = cs.parent_item_group or ""
    row.batch_length = flt(cs.w1_length)
    row.batch_width = flt(cs.w1_width)
    row.batch_thickness = flt(cs.sheet_thickness)
    row.batch_unit_weight = flt(cs.unit_weight)
    row.batch_sec_qty = sec_qty
    row.batch_calc_qty = qty

    # is_reserved is flipped after the save, not in it: _validate_batch_calc_qty
    # refuses a save that changes a reserved row's qty or batch.
    mp.save(ignore_permissions=True)

    frappe.db.set_value(
        "Material Planning Material Mapping", row.name,
        {"is_reserved": 1, "reserved_qty": qty, "shortfall_qty": 0, "reserved_on": now()},
        update_modified=False,
    )

    # No manual append: the row is reserved in the database by now, and the sheet
    # derives its Allocations from the rows holding it (_sync_allocations_from_rows).
    # Appending here as well would double-count this claim.
    refresh_cut_sheet_allocations(cs.name)
    frappe.db.commit()
    return {"row_name": row.name, "cut_sheet": cs.name, "sec_qty": sec_qty, "qty": qty}


def refresh_cut_sheet_allocations(cut_sheet_name):
    """Re-derive a sheet's Allocations table and its Allocated/Available figures.

    Called whenever a Material Mapping row starts or stops holding pieces, so the
    sheet is correct immediately rather than only after someone opens and saves it.
    A plain save is enough -- validate() does the rebuild -- but it is wrapped here
    so callers do not need to know that, and so a failure to refresh can never take
    down the reservation that triggered it."""
    if not cut_sheet_name or not frappe.db.exists("Cut Sheet", cut_sheet_name):
        return
    try:
        frappe.get_doc("Cut Sheet", cut_sheet_name).save(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title="Cut Sheet allocation refresh failed",
            message=frappe.get_traceback(),
        )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def cut_sheet_warehouse_query(doctype, txt, searchfield, start, page_len, filters):
    """Warehouses that actually hold the batch being cut.

    The field offered every warehouse on the site, and only one of them contains
    this plate -- picking any other names a place the sheet's own material is not,
    and the split happens against the batch in the warehouse named here.

    Stock is read through ERPNext's get_batch_qty rather than summing the ledger:
    a batch received on a Purchase Receipt records its quantity in a Serial and
    Batch Bundle and leaves Stock Ledger Entry.batch_no empty, so a GROUP BY on
    that column reports zero for exactly the batches most likely to be picked.
    """
    from erpnext.stock.doctype.batch.batch import get_batch_qty

    batch_no = (filters or {}).get("batch_no")
    if not batch_no:
        return []

    by_warehouse = {}
    for row in get_batch_qty(batch_no=batch_no) or []:
        wh = row.get("warehouse")
        if wh:
            by_warehouse[wh] = by_warehouse.get(wh, 0.0) + flt(row.get("qty"))

    company = (filters or {}).get("company")
    out = []
    for wh, qty in sorted(by_warehouse.items(), key=lambda kv: -kv[1]):
        if qty <= 0:
            continue
        if txt and txt.lower() not in wh.lower():
            continue
        if company and frappe.db.get_value("Warehouse", wh, "company") != company:
            continue
        # Second column is shown beside the name in the picker: which of these
        # holds enough is the actual question being asked here.
        out.append((wh, _("{0} in stock").format(flt(qty, 3))))
    return out[start:start + page_len]


@frappe.whitelist()
def mark_cut_sheet_inactive(cut_sheet_name, reason):
    """Set an unused Cut Sheet aside, with a reason, instead of deleting it.

    A sheet raised by mistake had nowhere to go: deleting it loses the record that
    it was ever made, and leaving it Active means it keeps appearing in the picker
    as material available to cut. Inactive is neither -- the sheet stays for
    reference and stops being offered anywhere (get_available_cut_sheets,
    get_cut_sheet_for_batch and Material Planning's own batch sync all skip it).

    Only while nothing has been done with it: no job holding pieces, no transfer
    taken, no balance written back to the batch. A sheet that has been used is a
    record of a real cut and is not something to set aside; release the
    allocations or cancel the transfer first, and then it can be.

    The reason is required. Six months later "why is this sheet inactive" has no
    other answer, and the sheet is being kept precisely for that question.
    """
    if not frappe.has_permission("Cut Sheet", "write"):
        frappe.throw(_("Not permitted to modify Cut Sheets"), frappe.PermissionError)

    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Enter a reason — it is what this sheet is being kept for."),
                     title=_("Reason Required"))

    cs = frappe.get_doc("Cut Sheet", cut_sheet_name)
    if cs.status == "Inactive":
        frappe.throw(_("This Cut Sheet is already Inactive."))

    blockers = []
    claims = cs.claiming_rows()
    if claims:
        blockers.append(
            _("pieces are allocated to {0}").format(
                ", ".join(sorted({r.parent for r in claims}))
            )
        )
    transferred = sorted({
        a.stock_entry for a in (cs.allocations or [])
        if a.stock_entry and frappe.db.get_value("Stock Entry", a.stock_entry, "docstatus") == 1
    })
    if transferred:
        blockers.append(_("material has been transferred by {0}").format(", ".join(transferred)))
    if cs.w2_applied:
        blockers.append(_("the balance has already been written back to the batch"))

    if blockers:
        frappe.throw(
            _("This Cut Sheet has been used, so it cannot be set aside: {0}.<br><br>"
              "Release the allocations, or cancel the transfer, and then mark it Inactive.")
            .format("; ".join(blockers)),
            title=_("Cut Sheet Already In Use"),
        )

    cs.status = "Inactive"
    cs.inactive_reason = reason
    cs.save(ignore_permissions=True)
    cs.add_comment("Comment", _("Marked Inactive: {0}").format(reason))
    return {"status": cs.status}


@frappe.whitelist()
def release_all_cut_sheet_allocations(cut_sheet_name):
    """Hand every job's pieces back, so the sheet can be re-cut.

    A sheet with allocations against it cannot have its W1 Sec Nos reduced below
    what jobs have already taken (_validate_allocations_fit) -- correct, because
    lowering it would silently oversubscribe pieces someone is relying on. But
    there was no way to undo those claims either: re-cutting a plate meant
    editing every claiming Material Planning by hand to find and clear the rows.

    This is that missing step. It clears the cut-sheet markers AND the cut
    figures on every Material Mapping row pointing here, then rebuilds the sheet
    -- which empties Allocations, since that table is derived from those rows.
    W1/W2 dimensions and Sec Nos are then free to change.

    Refused once material has physically moved: a submitted transfer means the
    steel is cut and the batch rewritten to match, so handing the pieces back on
    paper would claim a whole plate that is out on the floor in pieces. Cancel
    the transfer first, which reverts the batch through the ordinary path.

    Refused, too, while any claiming row is RESERVED. A reservation is a
    commitment against real stock, and quietly detaching the cut plan behind one
    would leave the job holding a batch on terms nobody re-agreed. Unreserving is
    a decision to be made on the Material Planning, looking at that plan -- so
    this says which rows, and stops. Rows merely allocated are released here,
    which is the ordinary case.

    The rows released are named in the return value and in a comment on the
    sheet, because "which jobs did I just detach" is the question anyone asks
    immediately afterwards.
    """
    if not frappe.has_permission("Cut Sheet", "write"):
        frappe.throw(_("Not permitted to modify Cut Sheets"), frappe.PermissionError)

    cs = frappe.get_doc("Cut Sheet", cut_sheet_name)

    transferred = sorted({
        a.stock_entry for a in (cs.allocations or [])
        if a.stock_entry and frappe.db.get_value("Stock Entry", a.stock_entry, "docstatus") == 1
    })
    if transferred:
        frappe.throw(
            _("Material has already been transferred from this Cut Sheet by {0}. "
              "Cancel {1} first — that puts the batch's dimensions back — and then "
              "release the allocations.")
            .format(", ".join(transferred), _("it") if len(transferred) == 1 else _("them")),
            title=_("Already Cut"),
        )

    rows = cs.claiming_rows()

    reserved = [r for r in rows if r.is_reserved]
    if reserved:
        by_plan = {}
        for r in reserved:
            by_plan.setdefault(r.parent, []).append(str(r.idx))
        frappe.throw(
            _("Stock is still reserved against this Cut Sheet:<br><br>{0}<br><br>"
              "Open each Material Planning, unreserve those rows and take the batch "
              "off them, then release the allocations. A reservation is a claim on "
              "real stock — it is not something to undo from here without looking at "
              "the plan that made it.")
            .format("<br>".join(
                "<b>{0}</b> — row {1}".format(plan, ", ".join(idxs))
                for plan, idxs in sorted(by_plan.items())
            )),
            title=_("Reserved — Unreserve on the Plan First"),
        )

    released = []
    for row in rows:
        frappe.db.set_value(
            row.child_doctype, row.name,
            {
                "cut_sheet": 0, "cut_sheet_ref": "", "cut_sheet_avail_sec_qty": 0,
                # The cut figures go with the claim -- left behind they describe a
                # cut this row is no longer part of, and the Material Issue Plan
                # reads them back for the transfer.
                "use_length": 0, "use_width": 0, "use_sec_qty": 0, "use_calc_qty": 0,
                "balance_length": 0, "balance_width": 0, "balance_sec_qty": 0,
                "balance_calc_qty": 0,
            },
            update_modified=False,
        )
        released.append(row)

    # Rebuild after the rows are cleared, not before: the table is derived from
    # whatever still points here, so refreshing first would simply find them again.
    refresh_cut_sheet_allocations(cut_sheet_name)

    if released:
        cs.add_comment(
            "Comment",
            _("Allocations released: {0}").format(
                ", ".join("%s row %s (%s)" % (r.parent, r.idx, r.item_code) for r in released)
            ),
        )

    return {
        "released": len(released),
        "plans": sorted({r.parent for r in released}),
    }


def release_cut_sheet_allocation(row):
    """Hand a row's pieces back to its Cut Sheet. Caller saves the Material Planning.

    The row's own markers are cleared in the database FIRST, because the sheet now
    rebuilds its Allocations from whatever rows still point at it -- refreshing
    before the row was released would simply find it again and put it straight
    back."""
    if not row.get("cut_sheet_ref"):
        return
    cs_name = row.cut_sheet_ref

    if row.name and not str(row.name).startswith("new-"):
        frappe.db.set_value(
            "Material Planning Material Mapping", row.name,
            {"cut_sheet": 0, "cut_sheet_ref": "", "cut_sheet_avail_sec_qty": 0},
            update_modified=False,
        )
    row.cut_sheet = 0
    row.cut_sheet_ref = ""
    row.cut_sheet_avail_sec_qty = 0

    refresh_cut_sheet_allocations(cs_name)


# ── W2 write-back ─────────────────────────────────────────────────────────────

def apply_w2_to_batch(cut_sheet_name, stock_entry):
    """Write the balance onto the batch, on the FIRST transfer taken from this sheet.

    The client's rule, and it is about the physical world rather than the paperwork:
    the moment anyone cuts a piece out, the sheet in the rack IS the remnant --
    whether or not the other jobs have collected their pieces yet. Waiting until
    every piece had shipped would leave the batch advertising a full sheet that no
    longer exists.

    The batch KEEPS its original name, which still spells out the original
    dimensions. The client is aware and has chosen to live with it for now."""
    cs = frappe.get_doc("Cut Sheet", cut_sheet_name)
    if cs.w2_applied or not cs.batch_no:
        return False
    if not (flt(cs.w2_length) or flt(cs.w2_width) or flt(cs.w2_sec_qty)):
        # No balance was planned -- the sheet is used up rather than leaving a remnant.
        return False

    frappe.db.set_value("Batch", cs.batch_no, {
        "custom_length": flt(cs.w2_length),
        "custom_width": flt(cs.w2_width),
        "custom_sec_qty": flt(cs.w2_sec_qty),
    })
    frappe.db.set_value("Cut Sheet", cs.name, {
        "w2_applied": 1,
        "w2_applied_stock_entry": stock_entry,
        "w2_applied_on": now(),
        "status": "Consumed",
    }, update_modified=False)
    log_decision(
        "Cut Sheet Balance",
        reference_doctype="Cut Sheet",
        reference_name=cs.name,
        item_code=cs.item_code,
        batch_no=cs.batch_no,
        previous_sec_qty=flt(cs.sheet_sec_qty),
        sec_qty=flt(cs.w2_sec_qty),
        qty=flt(cs.w2_calc_qty),
        details=_("Batch {0} resized in place to the balance: {1} x {2}, {3} Nos.").format(
            cs.batch_no, flt(cs.w2_length), flt(cs.w2_width), flt(cs.w2_sec_qty)),
    )
    return True


def revert_w2_from_batch(cut_sheet_name):
    """Undo the write-back when the transfer that triggered it is cancelled -- the
    steel is back in the rack uncut, so the batch has to say so again.

    Which "write-back" that was depends on how the sheet was applied. With
    "Create New Batch for Cut Sheet Stock Entry" switched on there is nothing to put
    back on the batch, because its dimensions were never touched: what has to be
    undone is the Repack that emptied it, which puts the steel back under the
    original batch and empties the balance batch again."""
    cs = frappe.get_doc("Cut Sheet", cut_sheet_name)
    if not cs.w2_applied:
        return False

    if cs.get("w2_repack_entry"):
        from manufyxinvenzaerp.production_management.stock_entry import (
            _cancel_cut_sheet_repack,
        )
        _cancel_cut_sheet_repack(cs.w2_repack_entry, cs.batch_no)
    else:
        frappe.db.set_value("Batch", cs.batch_no, {
            "custom_length": flt(cs.sheet_length),
            "custom_width": flt(cs.sheet_width),
            "custom_sec_qty": flt(cs.sheet_sec_qty),
        })

    frappe.db.set_value("Cut Sheet", cs.name, {
        "w2_applied": 0, "w2_applied_stock_entry": "", "w2_applied_on": None,
        "w2_repack_entry": "", "w2_batch_no": "",
        "status": "Fully Allocated" if flt(cs.available_sec_qty) <= QTY_EPSILON else "Active",
    }, update_modified=False)
    return True
