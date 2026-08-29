import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now

from manufyxinvenzaerp.subcontracting_management.overrides import resolve_supplier_warehouse
from manufyxinvenzaerp.utils.dimension_formula import calculate_qty


class MaterialIssuePlan(Document):
    def after_insert(self):
        """First save populates the drawing/raw-material list automatically —
        mirrors how create_sco_from_production_plan populates SCO Drawing Items
        immediately at creation rather than requiring a separate manual step."""
        if self.production_plan:
            populate_from_production_plan(self.name)

    def validate(self):
        """Recompute Cut Sheet's To Use (W1) / Balance (W2) Calc Qty (Phase 5.2),
        auto-suggest an Excess Return row from a Cut Sheet row's Balance once
        it's calculated (Phase 5.5), then recompute Excess Calc Qty for every
        raw_materials row flagged Excess Return Applicable and sync (create/
        update, never duplicate) a matching row in excess_return_items for each
        (Phase 5.3). Order matters: the auto-suggestion must run before the
        excess-return sync so a freshly-suggested row gets picked up in the
        same save. Also mirrors each row's batch Remarks (Phase 6.3)."""
        _assert_claimed_excess_unchanged(self)
        _sync_excess_return_totals(self)
        _sync_batch_remarks(self)
        _sync_excess_availability(self)
        _sync_transferred_qty(self)
        # After _sync_transferred_qty -- the consolidated rows carry Issued Qty forward
        # from the raw-material rows, so they have to be refreshed first.
        _sync_consolidate_items(self)
        _maybe_mark_completed(self)

    def on_trash(self):
        """Remove Batch Change Log rows referencing this MIP from all linked
        Material Planning documents so no orphaned audit trail remains."""
        frappe.db.delete(
            "Material Planning Batch Change Log",
            {"material_issue_plan": self.name},
        )


@frappe.whitelist()
def create_from_subcontracting_order(sco_name):
    """Create (or return the existing) Material Issue Plan pre-filled from an SCO."""
    existing = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": sco_name})
    if existing:
        return existing

    sco = frappe.db.get_value("Subcontracting Order", sco_name, ["company", "custom_production_plan"], as_dict=True)
    if not sco or not sco.custom_production_plan:
        frappe.throw(_("This Subcontracting Order has no linked Production Plan."))

    mip = frappe.new_doc("Material Issue Plan")
    mip.company = sco.company
    mip.production_plan = sco.custom_production_plan
    mip.subcontracting_order = sco_name
    mip.insert(ignore_permissions=True)
    return mip.name


@frappe.whitelist()


@frappe.whitelist()
def populate_from_production_plan(mip_name):
    """Primary population entrypoint. The linked Production Plan's items already carry
    drawing/DUNO/sales-order/customer-drawing references (set by Material Planning's
    make_production_plan) — read the drawing list straight from there, auto-link a
    matching Subcontracting/Work Order if one exists, then cascade into raw materials
    and the weight summary."""
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    if not mip.production_plan:
        frappe.throw(_("Select a Production Plan first."))

    pp = frappe.get_doc("Production Plan", mip.production_plan)

    if not mip.subcontracting_order:
        mip.subcontracting_order = frappe.db.get_value(
            "Subcontracting Order",
            {"custom_production_plan": mip.production_plan, "docstatus": ["!=", 2]},
        ) or ""
    if not mip.work_order:
        mip.work_order = frappe.db.get_value(
            "Work Order",
            {"production_plan": mip.production_plan, "docstatus": ["!=", 2]},
        ) or ""

    # Source Warehouse defaults straight from the Production Plan's own Raw
    # Material Warehouse — the primary source now that this is asked for
    # explicitly, not just inferred from a Work Order.
    if not mip.source_warehouse:
        mip.source_warehouse = pp.custom_raw_material_warehouse or ""

    # Excess-return warehouse defaults from a linked WO's standard Finished Goods
    # Warehouse the first time. (Neither SCO nor Work Order carry Source/CNC
    # warehouse fields of their own anymore — both moved here permanently — so
    # there is nothing to default those two from on either side.)
    if mip.work_order and not mip.excess_return_warehouse:
        mip.excess_return_warehouse = frappe.db.get_value("Work Order", mip.work_order, "fg_warehouse") or ""

    # Supplier / WIP Warehouse — for a Supplier Job/Supplier with Material flow this
    # defaults from the linked SCO's Job Worker Warehouse (auto-resolved once a Job
    # Worker is set). An Internal Job SCO has no Job Worker, so that field never
    # auto-sets -- this is then the ONLY place the WIP warehouse is recorded, entered
    # by hand, and must never be silently overwritten. Only fills in when still blank,
    # same as source_warehouse/excess_return_warehouse above -- this used to run
    # unconditionally and wiped out a manually-set WIP Warehouse back to blank on every
    # refresh, which also broke SCO/SOE transfer tracking downstream (see
    # _update_sco_transferred_weight in stock_entry.py).
    if mip.subcontracting_order and not mip.supplier_warehouse:
        sco_row = frappe.db.get_value(
            "Subcontracting Order", mip.subcontracting_order,
            ["supplier_warehouse", "supplier", "company"], as_dict=True) or {}
        # Fall back to resolving the Job Worker's own warehouse by name when the
        # SCO has not filled the field in yet -- an SCO created by hand, or one
        # created in this very click, is still blank at this point, and a blank
        # Supplier Warehouse blocks every transfer this plan would later make.
        mip.supplier_warehouse = sco_row.get("supplier_warehouse") or resolve_supplier_warehouse(
            sco_row.get("supplier"), sco_row.get("company") or mip.company
        )

    mip.set("drawing_items", [])
    for row in (pp.po_items or []):
        if not row.get("custom_drawing") and not row.get("custom_material_planning"):
            continue
        mip.append("drawing_items", {
            "drawing": row.get("custom_drawing"),
            "item_code": row.item_code,
            "item_name": row.get("custom_item_name") or row.item_name,
            "qty_to_manufacture": row.planned_qty,
            "duno_mark_no": row.get("custom_duno_mark_no"),
            "customer_drawing_number": row.get("custom_customer_drawing_number"),
            "sales_order": row.get("sales_order") or "",
            "material_planning": row.get("custom_material_planning"),
            "customer_weight_kg": row.get("custom_customer_weight_kg"),
        })

    mip.save(ignore_permissions=True)
    refresh_mip_raw_materials(mip.name)
    return mip.name


# Fields the user edits directly on an otherwise-rebuilt-from-scratch raw_materials
# row (Excess Return in Phase 5.3, Cut Sheet in Phase 5.2) -- refresh_mip_raw_materials
# fully clears and rebuilds this table from the source Material Planning on every
# call, so anything the user typed here must be explicitly carried forward onto the
# freshly-rebuilt row or it would silently vanish the next time a Purchase Receipt
# (or anything else) triggers a refresh.
def _mip_refresh_blocked_message(mip):
    """Shared by check_mip_raw_materials_refreshable (pre-flight check the 'Refresh Raw
    Materials' button calls before deciding confirm-vs-block) and
    refresh_mip_raw_materials_manual's own throw -- one source of truth for both the
    condition and its wording, naming the actual Stock Entry(ies) to delete rather than
    a generic 'already transferred' notice."""
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _get_mip_transfer_stock_entry_names,
    )
    se_names = _get_mip_transfer_stock_entry_names(mip)
    if not se_names:
        return None
    return _(
        "Stock has already been transferred for this Material Issue Plan ({0}). "
        "Raw Materials cannot be refreshed. Delete the Stock Entry to refresh the raw materials."
    ).format(", ".join(se_names))


@frappe.whitelist()
def check_mip_raw_materials_refreshable(mip_name):
    """Live pre-flight check for the 'Refresh Raw Materials' button -- queries submitted
    Stock Entries directly rather than trusting raw_materials.transferred_qty on the
    currently-loaded snapshot, which only gets (re)computed by refresh_mip_raw_materials
    itself and so reads stale (still 0) right after a transfer if nothing has refreshed
    this table since. Returns {"blocked": bool, "message": str|None} so the button can
    show the correct hard-block message instead of a misleading 'are you sure?' confirm
    when a transfer has already happened but the snapshot hasn't caught up yet."""
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    message = _mip_refresh_blocked_message(mip)
    return {"blocked": bool(message), "message": message}


@frappe.whitelist()
def refresh_mip_raw_materials_manual(mip_name):
    """Wrapper around refresh_mip_raw_materials specifically for the user-facing
    'Refresh Raw Materials' button -- blocks outright once any reserved batch has
    already been physically transferred out. Server-side twin of
    check_mip_raw_materials_refreshable, so a direct/scripted call is blocked the same
    way even if the JS pre-flight check was somehow bypassed.

    Every OTHER caller of refresh_mip_raw_materials (post-purchase auto-refresh,
    batch reassignment's own re-sync, initial population from the Production Plan)
    must keep working unconditionally even after a partial transfer -- more items
    can still be purchased/reserved for drawings that haven't shipped yet -- so the
    block lives here, in this thin wrapper, not in the shared function itself."""
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    message = _mip_refresh_blocked_message(mip)
    if message:
        frappe.throw(message)
    return refresh_mip_raw_materials(mip_name)


@frappe.whitelist()
def refresh_mip_raw_materials(mip_name):
    """Rebuild the raw-material snapshot fresh from every Material Planning linked to
    this plan's drawings. Material Planning's own child tables remain the source of
    truth for reservation state — this only refreshes MIP's read-only display copy.

    A linked Material Planning commonly covers far more drawings than this one MIP
    was created for (e.g. one MP for a whole sales order's 22 beams, split across
    several MIPs of a few drawings each) -- so rows are filtered down to only the
    (sales_order, duno_mark_no) pairs actually listed in this MIP's own
    drawing_items, instead of pulling every row the linked MP(s) happen to have.
    A Material Planning is only scoped this way when EVERY drawing_items row
    pointing at it carries a real duno_mark_no -- a row with no DUNO at all
    (custom_material_planning set on the Production Plan Item without a specific
    Drawing/DUNO picked) means "pull this whole MP, unrestricted", same as before
    this filter existed, since there is no per-drawing scope to filter down to.

    User-editable fields (Excess Return / Cut Sheet — see _RAW_MATERIAL_EDITABLE_FIELDS)
    are carried forward from the row being replaced, matched by (source_table,
    source_row), since those two together uniquely identify "the same underlying
    Material Planning row" across a rebuild -- item_code/batch alone isn't enough
    when the same item appears in more than one row."""
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _get_already_transferred_batches,
    )

    mip = frappe.get_doc("Material Issue Plan", mip_name)
    mp_names = sorted({r.material_planning for r in (mip.drawing_items or []) if r.material_planning})

    drawing_keys_by_mp, wildcard_mps = {}, set()
    for r in (mip.drawing_items or []):
        if not r.material_planning:
            continue
        if not r.duno_mark_no:
            wildcard_mps.add(r.material_planning)
        else:
            drawing_keys_by_mp.setdefault(r.material_planning, set()).add((r.sales_order, r.duno_mark_no))

    transferred_batches = _get_already_transferred_batches(mip)

    old_rows_by_key = {
        (r.source_table, r.source_row): r
        for r in (mip.raw_materials or [])
        if r.source_row
    }

    # Material Planning Available Raw Material carries no unit_weight field of its
    # own (unlike Material Mapping/Unavailable Item), so it has to be looked up from
    # the Item master directly -- missing this left every ARM-sourced raw_materials
    # row (and anything derived from it, e.g. Excess Calc Qty) stuck at a wrong 0.
    unit_weight_by_item = {}
    all_mps = [frappe.get_doc("Material Planning", n) for n in mp_names]
    arm_item_codes = {r.item_code for mp in all_mps for r in (mp.available_raw_materials or []) if r.item_code}
    if arm_item_codes:
        unit_weight_by_item = dict(frappe.get_all(
            "Item", filters={"name": ["in", list(arm_item_codes)]},
            fields=["name", "custom_unit_weight"], as_list=True,
        ))

    mip.set("raw_materials", [])

    for mp in all_mps:
        mp_name = mp.name
        scoped_keys = drawing_keys_by_mp.get(mp_name) if mp_name not in wildcard_mps else None

        for row in (mp.material_mapping or []):
            if scoped_keys is not None and (row.sales_order, row.duno_mark_no) not in scoped_keys:
                continue
            qty = row.batch_calc_qty if row.batch else row.qty
            sec_qty = row.batch_sec_qty if row.batch else row.sec_qty
            planned_weight = _lookup_drawing_planned_weight(
                row.sales_order, row.customer_drawing_number, row.item_code,
                row.length, row.width, row.thickness)
            new_row = mip.append("raw_materials", {
                "material_planning": mp_name,
                "source_table": "Material Planning Material Mapping",
                "source_row": row.name,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "planned_item": row.planned_item,
                "duno_mark_no": row.duno_mark_no,
                "customer_drawing_number": row.customer_drawing_number,
                "sales_order": row.sales_order,
                "batch_no": row.batch,
                "purchase_receipt": row.purchase_receipt,
                "parent_item_group": row.parent_item_group,
                "length": row.length,
                "width": row.width,
                "thickness": row.thickness,
                "unit_weight": row.unit_weight,
                "sec_qty": sec_qty,
                "sec_uom": row.sec_uom,
                "reqd_kg": row.qty,
                "qty": qty,
                "transferred_qty": qty if row.batch and row.batch in transferred_batches else 0,
                "drawing_planned_weight": planned_weight,
                "excess_qty": flt(flt(qty) - planned_weight, 3) if planned_weight is not None else 0,
                "is_reserved": row.is_reserved,
                "is_unavailable": 0,
                "cnc_process": row.cnc_process,
                **_cut_sheet_reference(row),
            })

        for row in (mp.available_raw_materials or []):
            if scoped_keys is not None and (row.sales_order, row.duno_mark_no) not in scoped_keys:
                continue
            planned_weight = _lookup_drawing_planned_weight(
                row.sales_order, row.customer_drawing_number, row.item_code,
                row.length, row.width, row.thickness)
            new_row = mip.append("raw_materials", {
                "material_planning": mp_name,
                "source_table": "Material Planning Available Raw Material",
                "source_row": row.name,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "duno_mark_no": row.duno_mark_no,
                "customer_drawing_number": row.customer_drawing_number,
                "sales_order": row.sales_order,
                "batch_no": row.batch_no,
                "purchase_receipt": row.purchase_receipt,
                "parent_item_group": row.parent_item_group,
                "length": row.length,
                "width": row.width,
                "thickness": row.thickness,
                "unit_weight": unit_weight_by_item.get(row.item_code),
                "sec_qty": row.sec_qty,
                "sec_uom": row.sec_uom,
                "reqd_kg": row.overall_required_qty or row.required_qty,
                "qty": row.required_qty,
                "transferred_qty": row.required_qty if row.batch_no and row.batch_no in transferred_batches else 0,
                "drawing_planned_weight": planned_weight,
                "excess_qty": flt(flt(row.required_qty) - planned_weight, 3) if planned_weight is not None else 0,
                "is_reserved": row.is_reserved,
                "is_unavailable": 0,
                "cnc_process": row.cnc_process,
                **_cut_sheet_reference(row),
            })

        for row in (mp.unavailable_items or []):
            if scoped_keys is not None and (row.sales_order, row.duno_mark_no) not in scoped_keys:
                continue
            new_row = mip.append("raw_materials", {
                "material_planning": mp_name,
                "source_table": "Material Planning Unavailable Item",
                "source_row": row.name,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "duno_mark_no": row.duno_mark_no,
                "customer_drawing_number": row.customer_drawing_number,
                "sales_order": row.sales_order,
                "parent_item_group": row.parent_item_group,
                "length": row.length,
                "width": row.width,
                "thickness": row.thickness,
                "unit_weight": row.unit_weight,
                "sec_qty": row.sec_qty,
                "reqd_kg": row.qty,
                "qty": row.qty,
                "transferred_qty": 0,
                "is_reserved": 0,
                "is_unavailable": 1,
            })

    mip.save(ignore_permissions=True)
    refresh_weight_summary(mip_name)
    return mip.name


def _sync_excess_availability(mip):
    """Show, on each Excess Material Items row, how much of that off-cut is still up
    for grabs -- the same Availability block a Cut Sheet carries.

    An off-cut can now be shared out in pieces across several jobs, so "is this
    claimed?" is no longer a yes/no question. These three figures are display copies
    of a live count taken from the rows actually holding the pieces (see
    excess_row_availability); they are refreshed on every save rather than maintained
    incrementally, so they cannot drift when a claiming plan is deleted."""
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        excess_row_availability,
    )

    for row in (mip.excess_return_items or []):
        if not row.name or row.get("__islocal"):
            continue
        avail = excess_row_availability(row.name)
        row.allocated_sec_qty = avail["allocated_sec_qty"]
        row.allocated_qty = avail["allocated_qty"]
        row.available_sec_qty = avail["available_sec_qty"]
        row.available_qty = avail["available_qty"]


def _sync_transferred_qty(mip):
    """Refresh each raw_materials row's Issued Qty from the Stock Entries that actually
    moved the material.

    This field used to be written only by refresh_mip_raw_materials, which is
    deliberately blocked once any stock has been transferred (see
    _mip_refresh_blocked_message) -- so in the one situation where it finally has a
    non-zero value to show, nothing was left that could write it. Every row read 0 and
    the grid showed a fully-shipped plan as entirely pending. The transfer popup was
    never affected: it computes its own figures live (see get_mip_pending_items).

    Counted as "left the source warehouse", so the Stores -> CNC -> supplier route
    contributes once (on its first leg) rather than twice. Where several requirement
    rows share one batch they split its total by planned-qty share, the same weighting
    the transfer popup uses to aggregate them; the last row absorbs the rounding
    remainder so the parts sum back to the whole exactly."""
    if not mip.source_warehouse:
        return

    moved = {}
    for r in frappe.db.sql(
        """
        SELECT sed.item_code, sed.batch_no, SUM(sed.qty) AS qty
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.custom_mip_ref = %s AND se.docstatus = 1 AND sed.s_warehouse = %s
        GROUP BY sed.item_code, sed.batch_no
        """,
        (mip.name, mip.source_warehouse),
        as_dict=True,
    ):
        moved[(r.item_code, r.batch_no or "")] = flt(r.qty)

    # Keyed on the batch's own item -- an alternate-item row's Stock Entry line is
    # booked against planned_item, not the requirement's item_code.
    def key(row):
        return ((row.planned_item or row.item_code), row.batch_no or "")

    rows_by_key = defaultdict(list)
    for row in (mip.raw_materials or []):
        rows_by_key[key(row)].append(row)

    for k, rows in rows_by_key.items():
        total_moved = flt(moved.get(k, 0.0))
        total_planned = sum(flt(r.qty) for r in rows)
        if not total_moved or not total_planned:
            for r in rows:
                r.transferred_qty = flt(total_moved, 3) if len(rows) == 1 else 0.0
            continue
        running = 0.0
        for r in rows[:-1]:
            share = flt(total_moved * flt(r.qty) / total_planned, 3)
            r.transferred_qty = share
            running += share
        rows[-1].transferred_qty = flt(total_moved - running, 3)


@frappe.whitelist()
def save_transfer_draft(mip_name, rows_json, excess_plan_json=None):
    """Park what has been typed into the transfer popup without transferring anything.

    Deliberately unvalidated. The whole point of "Save and Close" is to step away
    mid-decision -- a half-entered Sec Nos, an off-cut not yet measured, a warehouse not
    yet chosen. Checking stock or dimensions here would refuse to save exactly the
    unfinished state the user is trying to keep. Everything is re-checked, server-side,
    when Transfer is finally pressed.

    Written straight to the child rows rather than through mip.save(): saving the parent
    would re-run validate(), which rebuilds this very table, and there is no reason to
    put the plan through that to record a scratch note."""
    rows = json.loads(rows_json) if isinstance(rows_json, str) else (rows_json or [])
    # The measured off-cut is stated once per ITEM on the popup's consolidated tab,
    # while this table is keyed per item+batch. The same figures are parked against
    # every batch row of that item and read back from whichever one is found first
    # -- they describe one off-cut, so any of them answers the question.
    excess_plan = json.loads(excess_plan_json) if isinstance(excess_plan_json, str) else (excess_plan_json or {})
    mip = frappe.get_doc("Material Issue Plan", mip_name)

    by_key = {
        (r.item_code, r.batch_no or "", 1 if r.cnc_process else 0): r
        for r in (mip.consolidate_items or [])
    }

    saved = 0
    for r in rows:
        key = (r.get("item_code"), r.get("batch_no") or "", 1 if r.get("cnc_process") else 0)
        target = by_key.get(key)
        if not target:
            # The plan changed under the popup (a row unreserved, a batch reassigned).
            # Skip rather than invent a row that no longer corresponds to anything.
            continue
        excess = excess_plan.get(r.get("item_code")) or {}
        frappe.db.set_value("Material Issue Plan Consolidate Item", target.name, {
            "draft_sec_qty": flt(r.get("custom_sec_qty")),
            "draft_excess_length": flt(excess.get("length")),
            "draft_excess_width": flt(excess.get("width")),
            "draft_excess_sec_qty": flt(excess.get("sec_qty")),
            "draft_return_warehouse": excess.get("return_warehouse") or "",
            "draft_saved_on": now(),
        }, update_modified=False)
        saved += 1

    frappe.db.commit()
    return {"saved": saved}


@frappe.whitelist()
def get_transfer_draft(mip_name):
    """The parked popup state, keyed the same way the popup keys its own rows."""
    rows = frappe.get_all(
        "Material Issue Plan Consolidate Item",
        filters={"parent": mip_name, "draft_saved_on": ["is", "set"]},
        fields=["item_code", "batch_no", "cnc_process"] + list(_CONSOLIDATE_DRAFT_FIELDS),
    )
    return {
        "%s|%s|%s" % (r.item_code, r.batch_no or "", 1 if r.cnc_process else 0): r
        for r in rows
    }


def _clear_transfer_draft(mip_name, items):
    """Drop the parked state for rows that have just been transferred -- it described
    what was about to happen, and it has now happened."""
    keys = {(i.get("item_code"), i.get("batch_no") or "", 1 if i.get("cnc_process") else 0)
            for i in (items or [])}
    if not keys:
        return
    for r in frappe.get_all(
        "Material Issue Plan Consolidate Item",
        filters={"parent": mip_name, "draft_saved_on": ["is", "set"]},
        fields=["name", "item_code", "batch_no", "cnc_process"],
    ):
        if (r.item_code, r.batch_no or "", 1 if r.cnc_process else 0) in keys:
            frappe.db.set_value(
                "Material Issue Plan Consolidate Item", r.name,
                {f: (None if f in ("draft_return_warehouse", "draft_saved_on") else 0)
                 for f in _CONSOLIDATE_DRAFT_FIELDS},
                update_modified=False,
            )


# Held across a rebuild of the Consolidate Items table -- see _sync_consolidate_items.
_CONSOLIDATE_DRAFT_FIELDS = (
    "draft_sec_qty",
    "draft_excess_length",
    "draft_excess_width",
    "draft_excess_sec_qty",
    "draft_return_warehouse",
    "draft_saved_on",
)


def _sync_consolidate_items(mip):
    """Rebuild the Consolidate Items table: one row per item + batch, merged.

    Same shape as the transfer popup, because it describes the same thing -- what will
    physically move. Grouped by (item, batch, CNC leg), which is as far as consolidation
    can go: a Stock Entry has to name a specific batch, so two batches of one item stay
    two rows. Merging them would produce a line that cannot be turned into a transfer.

    Keyed on the BATCH's item (planned_item), not the requirement's, so an alternate-item
    row lands under the item actually being moved -- the same rule the Stock Entry and
    the transfer popup use.

    Batch-assigned rows are included whether or not they are still flagged reserved:
    submitting the transfer clears that flag, and a table that emptied itself the moment
    material shipped would be useless for seeing what a plan did. Rows with no batch yet
    (nothing allocated) are left out -- there is nothing to move.

    Sorted by item then batch so a batch's siblings sit together; scattering them is
    what made two legitimate lines read as a duplicate.

    Everything here is derived and the table is rebuilt wholesale on every save -- with
    ONE exception. The draft_* fields hold what someone typed into the transfer popup
    and saved without transferring (see save_transfer_draft), so they are carried across
    the rebuild, matched on the same key the rows are grouped by. Losing them would mean
    "Save and Close" quietly discarded the work the moment anything re-saved the plan.
    """
    drafts = {
        (r.item_code, r.batch_no or "", 1 if r.cnc_process else 0): {
            f: r.get(f) for f in _CONSOLIDATE_DRAFT_FIELDS
        }
        for r in (mip.consolidate_items or [])
        if any(flt(r.get(f)) if f != "draft_return_warehouse" and f != "draft_saved_on"
               else r.get(f) for f in _CONSOLIDATE_DRAFT_FIELDS)
    }

    # Item names in one query rather than one per group. At 500 drawings a plan can
    # hold hundreds of distinct item/batch pairs, and a lookup inside the loop turned
    # a single save into hundreds of round trips.
    wanted_items = {r.planned_item or r.item_code for r in (mip.raw_materials or []) if r.batch_no}
    item_names = dict(frappe.get_all(
        "Item", filters={"name": ["in", list(wanted_items)]},
        fields=["name", "item_name"], as_list=True,
    )) if wanted_items else {}

    groups = {}
    for row in (mip.raw_materials or []):
        if not row.batch_no:
            continue
        item_code = row.planned_item or row.item_code
        key = (item_code, row.batch_no, 1 if row.cnc_process else 0)
        g = groups.get(key)
        if not g:
            g = groups[key] = {
                "item_code": item_code,
                "item_name": item_names.get(item_code) or item_code,
                "batch_no": row.batch_no,
                "cnc_process": 1 if row.cnc_process else 0,
                "parent_item_group": row.parent_item_group or "",
                "length": flt(row.length), "width": flt(row.width),
                "thickness": flt(row.thickness), "unit_weight": flt(row.unit_weight),
                "sec_uom": row.sec_uom or "", "uom": row.uom or "Kg",
                "sec_qty": 0.0, "qty": 0.0, "transferred_qty": 0.0,
                "source_rows": 0, "dunos": [],
            }
        g["sec_qty"] += flt(row.sec_qty)
        g["qty"] += flt(row.qty)
        g["transferred_qty"] += flt(row.transferred_qty)
        g["source_rows"] += 1
        if row.duno_mark_no and row.duno_mark_no not in g["dunos"]:
            g["dunos"].append(row.duno_mark_no)

    mip.set("consolidate_items", [])
    for key in sorted(groups, key=lambda k: (k[0], k[1], k[2])):
        g = groups[key]
        qty = flt(g["qty"], 3)
        done = flt(g["transferred_qty"], 3)
        row = mip.append("consolidate_items", {
            "item_code": g["item_code"], "item_name": g["item_name"],
            "batch_no": g["batch_no"], "cnc_process": g["cnc_process"],
            "parent_item_group": g["parent_item_group"],
            "length": g["length"], "width": g["width"],
            "thickness": g["thickness"], "unit_weight": g["unit_weight"],
            "sec_qty": flt(g["sec_qty"], 3), "sec_uom": g["sec_uom"],
            "qty": qty, "uom": g["uom"],
            "transferred_qty": done,
            "pending_qty": flt(max(qty - done, 0.0), 3),
            "available_qty": _batch_stock_in(g["item_code"], g["batch_no"], mip.source_warehouse),
            "source_rows": g["source_rows"],
            "duno_mark_no": ", ".join(g["dunos"]),
        })
        for fieldname, value in (drafts.get(key) or {}).items():
            row.set(fieldname, value)


def _batch_stock_in(item_code, batch_no, warehouse):
    """What the batch physically holds in a warehouse right now.

    Read through the Serial and Batch Bundle rather than Stock Ledger Entry's own
    batch_no column, which Frappe v15 leaves empty for bundled movements."""
    if not (batch_no and warehouse):
        return 0.0
    qty = frappe.db.sql(
        """
        SELECT SUM(sle.actual_qty)
        FROM `tabStock Ledger Entry` sle
        JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sle.serial_and_batch_bundle
        WHERE sle.is_cancelled = 0 AND sle.item_code = %s
          AND sle.warehouse = %s AND sbe.batch_no = %s
        """,
        (item_code, warehouse, batch_no),
    )
    return flt(qty[0][0] if qty and qty[0] else 0, 3)


_CUT_SHEET_REF_CACHE_KEY = "_mfx_cut_sheet_ref_cache"


def _cut_sheet_reference(mp_row):
    """The cut plan behind a Material Planning row, for display on the issue plan.

    Reference only. The nesting is decided on the Cut Sheet, which states it once
    against the batch and shares it across every job drawing from that sheet; this
    document used to hold an editable copy of the same figures, which meant two
    places could disagree about one physical plate. What is left here is the sizes
    themselves, because they are what the transfer's Stock Entry carries and whoever
    makes it should be able to see them without opening another document.

    Empty dict where the batch has no cut plan, so an ordinary row is untouched."""
    ref = mp_row.get("cut_sheet_ref")
    if not ref:
        return {}
    # getattr/setattr, not frappe.local.__dict__: frappe.local is a Werkzeug Local
    # proxy, and on this Werkzeug version it raises AttributeError for __dict__ --
    # which killed "Job work order & MIP" outright the moment a plan had one
    # cut-sheet row (PP-INT-2026-00013: "AttributeError: __dict__"). These two
    # reach the same per-request store without touching the proxy's internals.
    cache = getattr(frappe.local, _CUT_SHEET_REF_CACHE_KEY, None)
    if cache is None:
        cache = {}
        setattr(frappe.local, _CUT_SHEET_REF_CACHE_KEY, cache)
    if ref not in cache:
        cache[ref] = frappe.db.get_value(
            "Cut Sheet", ref,
            ["w1_length", "w1_width", "w1_sec_qty", "w2_length", "w2_width", "w2_sec_qty"],
            as_dict=True,
        ) or {}
    cs = cache[ref]
    if not cs:
        return {}
    return {
        "cut_sheet_ref": ref,
        "use_length": flt(cs.get("w1_length")),
        "use_width": flt(cs.get("w1_width")),
        "use_sec_qty": flt(cs.get("w1_sec_qty")),
        "balance_length": flt(cs.get("w2_length")),
        "balance_width": flt(cs.get("w2_width")),
        "balance_sec_qty": flt(cs.get("w2_sec_qty")),
    }


def _lookup_drawing_planned_weight(sales_order, customer_drawing_number, item_code,
                                   length=None, width=None, thickness=None):
    """Engineering/planned raw material weight for this requirement, from Sales
    Order Drawing Raw Material's own Total Weight -- the "Drawing/planned RM
    weight" Excess Qty is measured against (client change request Phase 5.3's
    worked example: 14 Kg mapped batch − 13 Kg drawing-planned = 1 Kg excess).

    Matched on DIMENSIONS as well as item + drawing. One drawing routinely needs
    the same item in several sizes -- 1B9 alone needs PLATE10 at 192.31, 200.0 and
    225.86 mm -- and matching on item + drawing alone returned whichever of those
    rows came first, then measured every one of them against that single figure.
    The result was a scatter of meaningless positives and negatives (a 3.404 Kg
    piece judged against a 5.435 Kg one reported -2.031 Kg of "excess"), even
    though the mapping covered the requirement exactly.

    Falls back to the item + drawing match when nothing matches dimensionally, so
    a row whose dimensions have since been edited still gets a figure rather than
    silently losing its comparison. Returns None (not 0) when no match exists at
    all, so callers can tell "genuinely 0 Kg planned" apart from "no comparison
    available yet"."""
    if not sales_order or not item_code:
        return None

    cached = _drawing_planned_weights(sales_order)
    cdn = customer_drawing_number or ""
    if length is not None:
        hit = cached["exact"].get(
            (cdn, item_code, flt(length), flt(width), flt(thickness)))
        if hit is not None:
            return hit
    return cached["loose"].get((cdn, item_code))


def _drawing_planned_weights(sales_order):
    """Every planned raw-material weight for a Sales Order, in one query, keyed both
    ways this is looked up: exactly (drawing, item, L, W, T) and loosely (drawing, item).

    Cached for the life of the request. This is called once per raw-material row while
    a Material Issue Plan is rebuilt, and it used to run one or two queries each time --
    at 500 drawings carrying three materials apiece that is 1,500 rows and up to 3,000
    round trips for data that never changes during the rebuild.

    frappe.local is the right scope: it is cleared between requests, so an edit to a
    Sales Order's raw materials is picked up by the next rebuild rather than being
    served stale from a longer-lived cache."""
    store = getattr(frappe.local, "_mfx_planned_weights", None)
    if store is None:
        store = frappe.local._mfx_planned_weights = {}
    if sales_order in store:
        return store[sales_order]

    exact, loose = {}, {}
    for r in frappe.get_all(
        "Sales Order Drawing Raw Material",
        filters={"parent": sales_order},
        fields=["customer_drawing_number", "material_code", "length", "width",
                "thickness", "total_weight"],
    ):
        cdn = r.customer_drawing_number or ""
        exact.setdefault(
            (cdn, r.material_code, flt(r.length), flt(r.width), flt(r.thickness)),
            r.total_weight)
        # First row wins, matching the single get_value this replaced.
        loose.setdefault((cdn, r.material_code), r.total_weight)

    store[sales_order] = {"exact": exact, "loose": loose}
    return store[sales_order]


#  Claimed-off-cut lock ────────────────────────────────────────────────────────
#  A claim reserves ONE specific off-cut, of specific dimensions, for another
#  job's Material Planning. Once claimed, those numbers are frozen until the
#  claim is released -- see _assert_claimed_excess_unchanged for why.

# Compared field-for-field between an excess row and its committed DB values.
_CLAIMED_EXCESS_FIELDS = ("length", "width", "thickness", "sec_qty", "qty")

def _throw_claimed_excess_locked(excess_row):
    """The single message every blocked path shows, naming the Material Planning
    holding the claim and the one way out of it."""
    frappe.throw(
        _("<b>{0}</b> in the Excess Material Items table is already reserved for "
          "Material Planning <b>{1}</b>, so its dimensions are locked.<br><br>"
          "Use <b>Unlink Claim</b> on that row to release it, change the dimensions, "
          "then map it again from the Material Planning.")
        .format(excess_row.item_code or _("This excess item"),
                excess_row.mapped_material_planning),
        title=_("Excess Item Already Reserved"),
    )


def _assert_claimed_excess_unchanged(mip):
    """Refuse any edit that moves the dimensions or quantity of an excess row some
    Material Planning has already reserved.

    Every route into the Excess Material Items table ends here -- typing straight
    into the grid, editing a raw-material row's Excess Length/Width/Sec Qty (which
    _sync_excess_return_from_raw_materials would propagate), or the Return Excess
    Entry dialog's per-row overrides. Validating at the table itself catches all of
    them with one message instead of three near-copies at three call sites, which
    is what the client asked for: the check belongs where the numbers land.

    Compares against the committed DB row rather than trusting a dirty flag, so it
    fires on the actual change and stays silent on saves that touch other things."""
    for row in (mip.excess_return_items or []):
        if not row.get("mapped_material_planning"):
            continue
        committed = frappe.db.get_value(
            "SCO Excess Material Item", row.name, _CLAIMED_EXCESS_FIELDS, as_dict=True,
        )
        if not committed:
            # Row was appended in this very save; it cannot already be claimed by
            # anyone, so there is no committed state to protect.
            continue
        if any(flt(row.get(f), 3) != flt(committed.get(f), 3) for f in _CLAIMED_EXCESS_FIELDS):
            _throw_claimed_excess_locked(row)


@frappe.whitelist()
def unlink_excess_claim(mip_name, excess_row_name):
    """Release a Material Planning's claim on an excess row so its dimensions can be
    corrected (the "Unlink Claim" button _throw_claimed_excess_locked points at).

    Clears both ends in one go: the claiming Material Mapping row's virtual-excess
    markers and reservation, and this row's mapped_material_planning pointer, which
    puts the off-cut back in front of Excess Material Mapping's picker for anyone to
    claim again.

    Refuses once the off-cut has physically returned -- by then it is a real batch
    reserved like any other, and the ordinary unreserve buttons on the Material
    Planning are the right tool."""
    excess = frappe.db.get_value(
        "SCO Excess Material Item", excess_row_name,
        ["name", "parent", "mapped_material_planning", "mapped_row_name", "stock_entry_created"],
        as_dict=True,
    )
    if not excess or excess.parent != mip_name:
        frappe.throw(_("Excess Material Item row {0} not found on {1}.").format(excess_row_name, mip_name))
    if not frappe.has_permission("Material Issue Plan", "write", doc=mip_name):
        frappe.throw(_("Not permitted to modify this Material Issue Plan"), frappe.PermissionError)
    if not excess.mapped_material_planning:
        frappe.throw(_("This excess item is not claimed by any Material Planning."))
    if excess.stock_entry_created:
        frappe.throw(
            _("This off-cut has already been returned to stock as a real batch. "
              "Unreserve it from Material Planning {0} instead.")
            .format(excess.mapped_material_planning)
        )

    if excess.mapped_row_name:
        row = frappe.db.get_value(
            "Material Planning Material Mapping", excess.mapped_row_name,
            ["name", "parent", "is_virtual_excess"], as_dict=True,
        )
        if row and row.parent == excess.mapped_material_planning and row.is_virtual_excess:
            frappe.db.set_value(
                "Material Planning Material Mapping", row.name,
                {
                    "is_virtual_excess": 0, "virtual_excess_source_row": "",
                    "virtual_excess_source_mip": "", "batch_mapped": "Not Mapped",
                    "is_reserved": 0, "reserved_qty": 0, "reserved_on": None,
                },
                update_modified=False,
            )

    frappe.db.set_value(
        "SCO Excess Material Item", excess_row_name,
        {"mapped_material_planning": "", "mapped_row_name": ""}, update_modified=False,
    )
    frappe.db.commit()
    return {"released_from": excess.mapped_material_planning}


def _sync_excess_return_totals(mip):
    """Sum excess_return_items rows into the parent summary fields so they are
    always correct after save — mirrors the client-side _mip_excess_totals but
    runs server-side in validate() so the values are persisted even when no
    child-row field change triggered the JS handler."""
    total_kg = 0.0
    total_nos = 0.0
    for row in (mip.excess_return_items or []):
        total_kg += flt(row.qty)
        total_nos += flt(row.sec_qty)
    mip.excess_return_total_kg = flt(total_kg, 3)
    mip.excess_return_total_nos = flt(total_nos, 3)

    # What actually came back, as opposed to what was planned to. The two differ
    # routinely: an off-cut is re-measured on the way home, so 1,500 Kg planned at
    # 150x50 can return as 1,450 at 140x50.
    mip.returned_weight_kg = flt(sum(
        flt(row.qty) for row in (mip.excess_return_items or []) if row.stock_entry_created
    ), 3)

    # What the job's own finished-goods entry consumed. Read from the entry rather
    # than assumed from the transfer: the whole point is that they are not the same
    # number, and the gap between them is what has to be returned or written off.
    mip.used_in_fg_weight_kg = _used_in_fg_weight(mip)


def _used_in_fg_weight(mip):
    """Kg consumed by this job's submitted 'Manufacture' Stock Entries.

    Only the consumed side: a Manufacture entry carries the finished good as well,
    and counting that would double the figure. A consumed row is one with a source
    warehouse and no target."""
    if not mip.subcontracting_order:
        return 0.0
    total = frappe.db.sql(
        """
        SELECT SUM(sed.qty)
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.subcontracting_order = %(sco)s
          AND se.stock_entry_type = 'Manufacture'
          AND se.docstatus = 1
          AND sed.s_warehouse IS NOT NULL AND sed.s_warehouse != ''
          AND (sed.t_warehouse IS NULL OR sed.t_warehouse = '')
        """,
        {"sco": mip.subcontracting_order},
    )
    return flt(total[0][0] if total and total[0] else 0, 3)


def _sync_batch_remarks(mip):
    """Mirror each raw_materials row's assigned batch's own Batch Remarks
    (client change request Phase 6.3) onto its own batch_remarks field. Not a
    fetch_from field -- raw_materials rows are entirely rebuilt server-side by
    refresh_mip_raw_materials, which never triggers Frappe's client-only
    fetch_from auto-populate (same reasoning as material_planning.py's own
    _sync_batch_remarks). One bulk query regardless of row count."""
    batch_nos = {r.batch_no for r in (mip.raw_materials or []) if r.batch_no}
    if not batch_nos:
        return
    remarks_by_batch = dict(frappe.get_all(
        "Batch", filters={"name": ["in", list(batch_nos)]},
        fields=["name", "custom_batch_remarks"], as_list=True,
    ))
    for row in (mip.raw_materials or []):
        if row.batch_no:
            row.batch_remarks = remarks_by_batch.get(row.batch_no) or ""


def _maybe_mark_completed(mip):
    """Auto-elevate status to Completed once both are true:
      1. Finished-goods stock has actually been received -- a submitted 'Manufacture'
         Stock Entry exists for this MIP's Subcontracting Order (created via the
         'Make Final Stock Entry' button -> create_finished_goods_entry).
      2. Every excess_return_items row is resolved: either physically returned
         (stock_entry_created), claimed straight off this table into another
         Material Planning (mapped_material_planning), or flagged to never
         physically leave the supplier (Billed to Consume). An empty
         table trivially satisfies this -- nothing to return.

    Only ever moves Open/In Progress -> Completed, never the reverse -- once set,
    later saves are no-ops here (this function returns immediately) and the
    document is locked for further edits (see the whitelisted-endpoint guards in
    material_issue_plan_transfer.py and disable_form() in material_issue_plan.js)."""
    if mip.status == "Completed":
        return
    if not mip.subcontracting_order:
        return
    fg_received = frappe.db.exists("Stock Entry", {
        "subcontracting_order": mip.subcontracting_order,
        "stock_entry_type": "Manufacture",
        "docstatus": 1,
    })
    if not fg_received:
        return
    for row in (mip.excess_return_items or []):
        if row.stock_entry_created or row.mapped_material_planning:
            continue
        return

    # And every kilo has to be somewhere. Transferred, less what the job used, less
    # what came back, is material still standing at the supplier under this job's
    # name -- either it comes home or it is written off as process loss with a
    # reason. Completing the plan over the top of it would close the job with stock
    # nobody is looking for, which is exactly how a supplier warehouse fills up with
    # weight no plan explains.
    if _unaccounted_weight(mip) > 0.001:
        return

    mip.status = "Completed"


def _unaccounted_weight(mip):
    """What this job still has standing at the supplier, per the stock ledger.

    Read from the ledger rather than as (transferred − used − returned − written
    off), because that arithmetic is only as good as the summary fields feeding it,
    and those are derived from the plan's own rows. The ledger is the thing the
    warehouse actually believes, and it is the same figure the Process Loss dialog
    shows -- so the two can never tell different stories about whether the job is
    finished.
    """
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _job_stock_at_supplier,
    )

    return flt(sum(_job_stock_at_supplier(mip).values()), 3)


def recheck_mip_completion(mip_name):
    """Re-check entrypoint for code paths that resolve an excess_return_items row via
    a raw frappe.db.set_value on the child row (bypassing this doctype's own validate())
    -- claim_virtual_excess_mapping and _mark_excess_item_mapped in material_planning.py,
    both of which claim a row straight into a Material Mapping reservation without ever
    calling mip.save(). A plain mip.save() would also re-run the full Cut Sheet/Excess
    Return sync chain for no reason; this only re-evaluates _maybe_mark_completed and, if
    now eligible, commits the status flip directly."""
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    if mip.status == "Completed":
        return
    _maybe_mark_completed(mip)
    if mip.status == "Completed":
        frappe.db.set_value("Material Issue Plan", mip_name, "status", "Completed", update_modified=False)


@frappe.whitelist()
def refresh_weight_summary(mip_name):
    """Recompute the four header weight-summary fields (and their per-drawing breakdown).

    Transferred weight is read directly from the linked SCO/WO's
    custom_transferred_weight_kg — already correctly computed by
    _update_sco/wo_transferred_weight — and distributed proportionally across
    drawings by planned weight share. This is independent of MP reservation
    status, so it stays accurate after SE submission clears is_reserved.
    """
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        _get_mp_drawing_weights_by_duno,
        _get_mp_mapped_weight_by_duno,
        _get_mp_excess_by_duno,
        _get_mp_total_weight,
    )

    mip = frappe.get_doc("Material Issue Plan", mip_name)

    # See populate_from_production_plan for why this only fills in when blank --
    # an Internal Job SCO's supplier_warehouse never auto-sets, so overwriting
    # unconditionally here (this runs on every Stock Entry submit, via
    # _refresh_linked_mip_weight) wiped out a manually-entered WIP Warehouse right
    # after the user transferred material into it.
    if mip.subcontracting_order and not mip.supplier_warehouse:
        sco_row = frappe.db.get_value(
            "Subcontracting Order", mip.subcontracting_order,
            ["supplier_warehouse", "supplier", "company"], as_dict=True) or {}
        # Fall back to resolving the Job Worker's own warehouse by name when the
        # SCO has not filled the field in yet -- an SCO created by hand, or one
        # created in this very click, is still blank at this point, and a blank
        # Supplier Warehouse blocks every transfer this plan would later make.
        mip.supplier_warehouse = sco_row.get("supplier_warehouse") or resolve_supplier_warehouse(
            sco_row.get("supplier"), sco_row.get("company") or mip.company
        )

    # Actual transferred weight — read from the linked SCO or WO
    actual_transferred = 0.0
    if mip.subcontracting_order:
        actual_transferred = flt(frappe.db.get_value(
            "Subcontracting Order", mip.subcontracting_order, "custom_transferred_weight_kg"
        ))
    elif mip.work_order:
        actual_transferred = flt(frappe.db.get_value(
            "Work Order", mip.work_order, "custom_transferred_weight_kg"
        ))

    mapped_by_mp = {}
    excess_by_mp = {}
    drawing_weight_by_mp = {}  # mp_name -> {duno_mark_no: planned_kg} (Phase 1 perf fix:
                                # was one live query per drawing_items row via
                                # _get_mp_drawing_weight; now one grouped query per
                                # unique mp_name, mirroring mapped_by_mp/excess_by_mp
                                # right above, which were already memoized this way.)

    total_planned = 0.0
    allocated = 0.0
    excess = 0.0

    for d in mip.drawing_items or []:
        mp_name = d.material_planning
        if not mp_name:
            continue
        if mp_name not in mapped_by_mp:
            mapped_by_mp[mp_name] = _get_mp_mapped_weight_by_duno(mp_name)
            excess_by_mp[mp_name] = _get_mp_excess_by_duno(mp_name)
        if mp_name not in drawing_weight_by_mp:
            drawing_weight_by_mp[mp_name] = _get_mp_drawing_weights_by_duno(mp_name)

        # Mirrors _get_mp_drawing_weight(mp_name, d.duno_mark_no) exactly: grouped
        # lookup for a real DUNO/Mark No, falling back to the MP's total weight
        # when it's blank -- same fallback _get_mp_drawing_weight itself uses.
        if d.duno_mark_no:
            planned_weight = drawing_weight_by_mp[mp_name].get(d.duno_mark_no, 0.0)
        else:
            planned_weight = _get_mp_total_weight(mp_name)
        d.total_weight_kg = flt(planned_weight, 3)
        d.mapped_weight_kg = flt(mapped_by_mp[mp_name].get(d.duno_mark_no), 3)
        d.excess_weight_kg = flt(excess_by_mp[mp_name].get(d.duno_mark_no), 3)

        total_planned += d.total_weight_kg
        allocated += d.mapped_weight_kg
        excess += d.excess_weight_kg

    # Distribute transferred weight across drawings by planned-weight share
    transferred = 0.0
    for d in mip.drawing_items or []:
        if not d.material_planning:
            continue
        d.transferred_weight_kg = (
            flt(actual_transferred * (d.total_weight_kg / total_planned), 3)
            if total_planned else 0.0
        )
        transferred += d.transferred_weight_kg

    mip.total_planned_weight_kg = flt(total_planned, 3)
    mip.allocated_weight_kg = flt(allocated, 3)
    mip.transferred_weight_kg = flt(transferred, 3)
    mip.excess_weight_kg = flt(excess, 3)

    # Per-row Issued Qty. This runs on every transfer Stock Entry submit/cancel, which
    # is exactly when the figure changes and is also the point after which
    # refresh_mip_raw_materials (the only other writer) is blocked from running.
    _sync_transferred_qty(mip)
    # Perf: this function only ever changes the 4 header weight fields above, the
    # per-row weight fields on drawing_items, and raw_materials.transferred_qty --
    # it never touches any Link field's VALUE (Material Issue Plan has no validate()
    # of its own and no doc_events registered in hooks.py, so nothing else runs here
    # either way). A plain .save() still re-validates every Link field on every row
    # of every child table, none of whose values this function changes -- on a
    # ~100-row Material Issue Plan that redundant check alone measured at ~0.35s
    # of a ~1.1s Stock Entry submission. ignore_links skips only that
    # re-validation; every other part of the normal save (timestamps, the
    # Version/track_changes log, child-table diffing) is unaffected.
    mip.flags.ignore_links = True
    mip.save(ignore_permissions=True)
    return mip.name


def get_target_context(mip):
    """Resolve which document (SCO or WO) this plan issues material against, and the
    SE type / target warehouse / Stock Entry link field that go with it. Supports
    both so this and material_issue_plan_transfer.py need no changes for the WO round."""
    if mip.subcontracting_order:
        sco = frappe.db.get_value(
            "Subcontracting Order", mip.subcontracting_order,
            ["company", "supplier_warehouse"], as_dict=True,
        )
        if not sco:
            frappe.throw(_("Linked Subcontracting Order {0} not found.").format(mip.subcontracting_order))
        # MIP's own supplier_warehouse takes priority; fall back to SCO's field
        primary_warehouse = mip.supplier_warehouse or sco.supplier_warehouse
        if not primary_warehouse:
            frappe.throw(
                _("Supplier Warehouse is not set. Please set it directly on this Material Issue Plan "
                  "(Warehouses section) or on the linked Subcontracting Order {0}.").format(mip.subcontracting_order)
            )
        return frappe._dict({
            "doctype": "Subcontracting Order",
            "name": mip.subcontracting_order,
            "company": sco.company,
            "primary_warehouse": primary_warehouse,
            "primary_se_type": "Send to Subcontractor",
            "link_field": "subcontracting_order",
            "ref_field": "custom_sco_ref",
        })
    if mip.work_order:
        wo = frappe.db.get_value("Work Order", mip.work_order, ["company", "wip_warehouse"], as_dict=True)
        if not wo:
            frappe.throw(_("Linked Work Order {0} not found.").format(mip.work_order))
        primary_warehouse = mip.supplier_warehouse or wo.wip_warehouse
        if not primary_warehouse:
            frappe.throw(
                _("WIP Warehouse is not set. Please set it in the Supplier / WIP Warehouse field on this "
                  "Material Issue Plan or on the linked Work Order {0}.").format(mip.work_order)
            )
        return frappe._dict({
            "doctype": "Work Order",
            "name": mip.work_order,
            "company": wo.company,
            "primary_warehouse": primary_warehouse,
            "primary_se_type": "Material Transfer",
            "link_field": "work_order",
            "ref_field": "custom_wo_ref",
        })
    frappe.throw(_("This Material Issue Plan has no linked Subcontracting Order or Work Order."))


# ─────────────────────────────────────────────────────────────────────────────
# Batch Plan PDF -- a simple, printable reference for the production/supplier
# team: for each item on each drawing, which physical batch (and how much of
# it, by Sec Qty) is planned. get_mip_batch_plan_html and
# download_mip_batch_plan_pdf both render from the exact same HTML builder so
# the on-screen preview and the downloaded PDF are always identical.
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_mip_batch_plan_html(mip_name):
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    return _render_mip_batch_plan_html(mip)


@frappe.whitelist()
def download_mip_batch_plan_pdf(mip_name):
    from frappe.utils.pdf import get_pdf

    mip = frappe.get_doc("Material Issue Plan", mip_name)
    html = _render_mip_batch_plan_html(mip)
    frappe.local.response.filename = "{0}-Batch-Plan.pdf".format(
        mip_name.replace(" ", "-").replace("/", "-")
    )
    frappe.local.response.filecontent = get_pdf(html)
    frappe.local.response.type = "pdf"


def _render_mip_batch_plan_html(mip):
    supplier = ""
    if mip.subcontracting_order:
        supplier = frappe.db.get_value("Subcontracting Order", mip.subcontracting_order, "supplier") or ""
    elif mip.work_order:
        supplier = _("Internal")

    rows = []
    for r in (mip.raw_materials or []):
        if not r.item_code:
            continue
        dims = " x ".join(str(flt(v, 2)) for v in (r.length, r.width, r.thickness) if flt(v)) or "-"
        rows.append({
            "duno": r.duno_mark_no or "",
            "cdn": r.customer_drawing_number or "",
            "item_code": r.item_code,
            "item_name": r.item_name or "",
            "planned_kg": flt(r.reqd_kg, 3),
            "batch_no": r.batch_no or _("Not Yet Allocated"),
            "dims": dims,
            "sec_qty": flt(r.sec_qty, 3),
            "sec_uom": r.sec_uom or "",
            "batch_weight_kg": flt(r.qty, 3),
        })
    rows.sort(key=lambda x: (not x["duno"], x["duno"], x["item_code"]))

    posting_date = frappe.utils.formatdate(mip.posting_date) if mip.posting_date else ""

    row_html = "".join("""
        <tr>
            <td>{duno}</td>
            <td>{cdn}</td>
            <td>{item_code}<br><span class="item-name">{item_name}</span></td>
            <td class="num">{planned_kg}</td>
            <td>{batch_no}</td>
            <td>{dims}</td>
            <td class="num">{sec_qty} {sec_uom}</td>
            <td class="num">{batch_weight_kg}</td>
        </tr>
    """.format(
        duno=frappe.utils.escape_html(r["duno"] or "-"),
        cdn=frappe.utils.escape_html(r["cdn"] or "-"),
        item_code=frappe.utils.escape_html(r["item_code"]),
        item_name=frappe.utils.escape_html(r["item_name"]),
        planned_kg=r["planned_kg"],
        batch_no=frappe.utils.escape_html(r["batch_no"]),
        dims=frappe.utils.escape_html(r["dims"]),
        sec_qty=r["sec_qty"],
        sec_uom=frappe.utils.escape_html(r["sec_uom"]),
        batch_weight_kg=r["batch_weight_kg"],
    ) for r in rows)

    return """
    <div class="mip-batch-plan">
        <style>
            .mip-batch-plan {{ font-family: Arial, Helvetica, sans-serif; color:#222; }}
            .mip-batch-plan h2 {{ margin:0 0 4px; }}
            .mip-batch-plan .meta {{ font-size:12px; color:#555; margin-bottom:14px; }}
            .mip-batch-plan table {{ width:100%; border-collapse:collapse; font-size:11.5px; }}
            .mip-batch-plan th {{ background:#f4f4f4; text-align:left; padding:6px 8px; border:1px solid #ccc; }}
            .mip-batch-plan td {{ padding:6px 8px; border:1px solid #ddd; vertical-align:top; }}
            .mip-batch-plan td.num {{ text-align:right; }}
            .mip-batch-plan .item-name {{ color:#777; font-size:10.5px; }}
        </style>
        <h2>{title}</h2>
        <div class="meta">
            {mip_label}: {mip_name} &nbsp;|&nbsp; {company_label}: {company} &nbsp;|&nbsp;
            {date_label}: {posting_date} &nbsp;|&nbsp; {supplier_label}: {supplier}
        </div>
        <table>
            <thead>
                <tr>
                    <th>{col_duno}</th>
                    <th>{col_cdn}</th>
                    <th>{col_item}</th>
                    <th>{col_planned}</th>
                    <th>{col_batch}</th>
                    <th>{col_dims}</th>
                    <th>{col_secqty}</th>
                    <th>{col_batchwt}</th>
                </tr>
            </thead>
            <tbody>
                {row_html}
            </tbody>
        </table>
    </div>
    """.format(
        title=_("Material Issue Plan — Batch Plan"),
        mip_label=_("MIP"), mip_name=mip.name,
        company_label=_("Company"), company=frappe.utils.escape_html(mip.company or ""),
        date_label=_("Posting Date"), posting_date=posting_date,
        supplier_label=_("Supplier"), supplier=frappe.utils.escape_html(supplier),
        col_duno=_("DUNO/Mark No"), col_cdn=_("Customer Drawing No"), col_item=_("Item"),
        col_planned=_("Planned Kg"), col_batch=_("Batch No"), col_dims=_("Dimensions (mm)"),
        col_secqty=_("Sec Qty"), col_batchwt=_("Batch Weight (Kg)"),
        row_html=row_html,
    )

    return source_warehouse, [w for w in target_warehouses if w]
