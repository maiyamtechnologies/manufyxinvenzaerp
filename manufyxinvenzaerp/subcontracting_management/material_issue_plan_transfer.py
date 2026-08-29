"""Transfer / CNC / excess-return Stock Entries issued from a Material Issue Plan.

Keyed by Material Issue Plan rather than by SCO/WO directly, so one implementation
serves both this round (SCO) and the deferred WO round without changes. It replaced an
equivalent set of SCO-keyed functions in subcontracting.py, which nothing called once
the issue plan became the way material leaves the warehouse; those have since been
removed.
Every Stock Entry created here dual-writes custom_mip_ref alongside the standard
subcontracting_order/custom_sco_ref (or custom_wo_ref) fields, so the existing SCO/WO weight
rollups in production_management/stock_entry.py keep working unchanged, fed by these entries
instead of the old SCO-button-created ones.
"""

import json as _json

import frappe
from frappe import _
from frappe.utils import flt

from manufyxinvenzaerp.utils.decision_log import log_decision
from manufyxinvenzaerp.subcontracting_management.subcontracting import _get_mp_reserved_batches
from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
    _clear_transfer_draft,
    get_target_context,
    _throw_claimed_excess_locked,
)
from manufyxinvenzaerp.utils.dimension_formula import calculate_qty

_DIMENSION_DRIVEN_GROUPS = {"Structurals", "Plates"}


def _ensure_mip_editable(mip):
    """Server-side lock: once a Material Issue Plan is Completed (see
    _maybe_mark_completed), block every action here that would create a new Stock
    Entry against it. Defense-in-depth alongside disable_form() in
    material_issue_plan.js, which is what actually hides these buttons in the UI --
    this guard is what stops a direct/scripted call from bypassing that."""
    if mip.status == "Completed":
        frappe.throw(_("{0} is Completed and locked for further changes.").format(mip.name))


def _cnc_rows_missing_warehouse(mip):
    """CNC Process rows on this plan that have no CNC Warehouse to go to."""
    if mip.cnc_warehouse:
        return []
    return [r for r in (mip.raw_materials or []) if r.cnc_process and r.item_code]


def _ensure_cnc_routing(mip):
    """CNC Process is a routing instruction, not a preference: material flagged for
    it must reach the CNC warehouse before the supplier/WIP warehouse, never skip
    straight there.

    Transfer resolves the target as `cnc_process AND cnc_warehouse`, so with no CNC
    Warehouse set the flag would be quietly dropped and the stock issued directly to
    the supplier -- physically past the CNC step, and only correctable afterwards
    with a reverse Stock Entry. Refuse the transfer instead, and say which rows and
    which two ways out (set the warehouse, or untick CNC Process on the Material
    Planning row if the step genuinely isn't needed).
    """
    rows = _cnc_rows_missing_warehouse(mip)
    if not rows:
        return

    listed = "".join(
        "<li>{0} — {1} ({2} {3}){4}</li>".format(
            frappe.utils.escape_html(r.item_code),
            frappe.utils.escape_html(r.batch_no or _("no batch")),
            flt(r.qty, 3), frappe.utils.escape_html(r.uom or "Kg"),
            " — DUNO {0}".format(frappe.utils.escape_html(r.duno_mark_no)) if r.duno_mark_no else "",
        )
        for r in rows[:15]
    )
    more = _("<li>… and {0} more</li>").format(len(rows) - 15) if len(rows) > 15 else ""

    frappe.throw(
        _("{0} item(s) are marked <b>CNC Process</b> but this Material Issue Plan has no "
          "<b>CNC Warehouse</b>. They must reach CNC before the supplier/WIP warehouse, so "
          "this transfer cannot proceed.<br><br><ul>{1}{2}</ul>"
          "Either set <b>CNC Warehouse</b> in the Warehouses section, or untick "
          "<b>CNC Process</b> on those rows in the Material Planning if the CNC step "
          "is not required.").format(len(rows), listed, more),
        title=_("CNC Warehouse Required"),
    )


def _validate_selected_against_stock(mip, selected):
    """Re-check every selected line against real free stock, and against what is
    still outstanding, immediately before the Stock Entry is built.

    The transfer popup lets Sec Nos and Qty be edited by hand, and the figures it
    was opened with can be minutes old -- another plan may have transferred from
    the same batch in between. Validating here, server-side, is what makes the
    edited numbers safe: a browser-side check alone would be trivially stale, and
    a partial transfer that quietly over-issues is only discoverable once the
    stock has physically moved.
    """
    if not selected:
        return

    # Keyed by CNC leg as well as item+batch: one batch feeding both a CNC drawing
    # and a direct one appears TWICE in the pending list, and collapsing those two
    # into one key silently validates a line against the other leg's figures.
    pending_by_key = {
        (p["item_code"], p.get("batch_no") or "", 1 if p.get("cnc_process") else 0): p
        for p in get_mip_pending_items(mip.name)
    }

    problems = []
    wanted_by_batch = {}
    for item in selected:
        item_code = item["item_code"]
        batch_no = item.get("batch_no") or ""
        key = (item_code, batch_no, 1 if item.get("cnc_process") else 0)
        qty = flt(item.get("qty"))
        if qty <= 0:
            problems.append(_("{0} ({1}): transfer qty must be greater than zero.").format(item_code, batch_no or "-"))
            continue

        row = pending_by_key.get(key)
        if not row:
            problems.append(
                _("{0} ({1}): nothing is pending transfer for this item/batch any more.").format(item_code, batch_no or "-"))
            continue

        # Taking MORE than the plan is the designed workflow, not an error: a
        # fractional 2.818 pieces has to become 3 whole ones before anything can
        # physically leave the rack. The surplus over the plan is booked as excess
        # to return, so it is measured here -- server-side, rather than trusting
        # the figure the browser sent -- and stamped onto the line for
        # _log_round_up_excess to pick up. Only genuine lack of free stock blocks.
        over_kg = flt(qty - flt(row["qty"]), 3)
        if over_kg > 0.001:
            item["round_up_excess_kg"] = over_kg
            item["round_up_excess_pieces"] = flt(
                flt(item.get("custom_sec_qty")) - flt(row.get("custom_sec_qty")), 3)
            item["_planned_qty"] = flt(row["qty"], 3)

        # Free stock is per physical batch, so both legs share one running total.
        bkey = (item_code, batch_no)
        wanted_by_batch[bkey] = flt(wanted_by_batch.get(bkey, 0) + qty, 3)

    # One batch can appear on several selected lines -- check the batch's free
    # stock against their combined total, not each line on its own.
    planned_by_batch = {}
    for item in selected:
        bkey = (item["item_code"], item.get("batch_no") or "")
        key = (item["item_code"], item.get("batch_no") or "", 1 if item.get("cnc_process") else 0)
        row = pending_by_key.get(key)
        if row:
            planned_by_batch[bkey] = flt(planned_by_batch.get(bkey, 0) + flt(row["qty"]), 3)

    for (item_code, batch_no), wanted in wanted_by_batch.items():
        available = flt(_batch_free_qty(item_code, batch_no, mip.source_warehouse), 3)
        if wanted > available + 0.001:
            planned = flt(planned_by_batch.get((item_code, batch_no), 0), 3)
            # Spell out all three figures: what the plan wanted, what the edit
            # raised it to, and what is actually in the rack -- the shortfall is
            # only actionable if you can see which of those to change.
            problems.append(
                _("<b>{0}</b> ({1}) — planned <b>{2} Kg</b>, updated to <b>{3} Kg</b>, "
                  "but only <b>{4} Kg</b> is free in {5}. Short by {6} Kg — lower the Sec Nos, "
                  "or transfer what is available now and the rest later.").format(
                    item_code, batch_no or "-", planned, wanted, available,
                    mip.source_warehouse, flt(wanted - available, 3)))

    if problems:
        frappe.throw(
            _("Stock validation failed — nothing has been transferred:<br><br><ul>{0}</ul>"
              "Reopen <b>Select Materials to Transfer</b> to see the current pending and "
              "available quantities.").format("".join("<li>%s</li>" % p for p in problems)),
            title=_("Cannot Transfer"),
        )


def _linked_mp_names(mip):
    return _linked_mp_names_and_duno_scope(mip)[0]


def _linked_mp_names_and_duno_scope(mip):
    """Material Plannings linked to this MIP's Production Plan items, each paired
    with the set of DUNO/Mark Nos this Production Plan actually covers for it.

    A single Material Planning document can be shared across several Production
    Plans -- only some of its drawings pulled into any one of them at a time.
    Without this scope, every reserved batch in the WHOLE Material Planning gets
    offered for transfer here, including batches reserved for drawings that
    belong to a completely different, not-yet-planned job (they'd move to the
    wrong supplier/warehouse if transferred from here). A Material Planning where
    any po_items row is missing a duno_mark_no falls back to no filtering for it
    -- the same "take the whole Material Planning's totals" fallback already used
    elsewhere (create_sco_from_production_plan) for undated rows.
    """
    pp = frappe.get_doc("Production Plan", mip.production_plan)
    mp_names = []
    seen = set()
    dunos_by_mp = {}
    has_blank_by_mp = set()
    for pi in pp.po_items:
        mp_name = pi.get("custom_material_planning")
        if not mp_name:
            continue
        if mp_name not in seen:
            seen.add(mp_name)
            mp_names.append(mp_name)
        duno = pi.get("custom_duno_mark_no")
        if duno:
            dunos_by_mp.setdefault(mp_name, set()).add(duno)
        else:
            has_blank_by_mp.add(mp_name)
    duno_scope = {mp: (None if mp in has_blank_by_mp else dunos_by_mp.get(mp)) for mp in mp_names}
    return mp_names, duno_scope


def _tag_stock_entry(se_dict, mip_name, ctx):
    se_dict["custom_mip_ref"] = mip_name
    se_dict[ctx.link_field] = ctx.name
    se_dict[ctx.ref_field] = ctx.name
    return se_dict


def _cut_sheet_caps(mip):
    """The To Use (W1) weight each cut batch may offer, keyed by (item, batch).

    Read from the Material Planning rows, which is where the cut plan is decided and
    where the Cut Sheet is chosen. It used to be read from the Material Issue Plan's
    own copy of those fields; those copies are gone, along with the second, parallel
    way of cutting a sheet that came with them.

    Keyed on the BATCH's item (planned_item where the batch belongs to a different
    item from the requirement), matching how _get_mp_reserved_batches names its rows.
    """
    caps = {}
    mp_names = _linked_mp_names(mip)
    if not mp_names:
        return caps

    for child_dt, batch_field in (
        ("Material Planning Material Mapping", "batch"),
        ("Material Planning Available Raw Material", "batch_no"),
    ):
        for r in frappe.get_all(
            child_dt,
            filters={"parent": ["in", list(mp_names)], "cut_sheet": 1},
            fields=["item_code", batch_field + " as batch_no", "use_calc_qty"]
                   + (["planned_item"] if child_dt.endswith("Material Mapping") else []),
        ):
            if not r.batch_no or not flt(r.use_calc_qty):
                continue
            key = (r.get("planned_item") or r.item_code, r.batch_no)
            # Several rows can cut the same batch; the batch may offer all their
            # pieces, so the caps add up rather than the last one winning.
            caps[key] = flt(flt(caps.get(key, 0)) + flt(r.use_calc_qty), 3)
    return caps


@frappe.whitelist()
def get_mip_process_loss_state(mip_name):
    """What is left unexplained on this job, and what stands in the way of closing it.

    Answers the question the plan cannot: 1,836 Kg went out, 116 was used, 1,450 came
    back -- so where are the other 270? Until they are either returned or written off,
    they sit at the supplier as real stock belonging to nobody's plan.

    Returns the figures the dialog shows, plus two things that must be dealt with
    first: excess still declared-but-not-returned, and any of it another Material
    Planning has already claimed.
    """
    mip = frappe.get_doc("Material Issue Plan", mip_name)

    at_supplier = _job_stock_at_supplier(mip)
    remaining = flt(sum(at_supplier.values()), 3)

    pending, claimed = [], []
    for r in (mip.excess_return_items or []):
        if r.stock_entry_created or flt(r.qty) <= 0:
            continue
        pending.append({
            "row": r.name, "idx": r.idx, "item_code": r.item_code,
            "qty": flt(r.qty, 3),
            "length": flt(r.length, 3), "width": flt(r.width, 3),
            "sec_qty": flt(r.sec_qty, 3),
        })
        if r.mapped_material_planning:
            claimed.append({
                "row": r.name, "idx": r.idx, "item_code": r.item_code,
                "plan": r.mapped_material_planning, "qty": flt(r.qty, 3),
            })

    planned_return = flt(sum(flt(r.qty) for r in (mip.excess_return_items or [])), 3)
    returned = flt(sum(
        flt(r.qty) for r in (mip.excess_return_items or []) if r.stock_entry_created
    ), 3)

    threshold_pct = flt(frappe.db.get_single_value(
        "Manufyxinvenza Settings", "process_loss_warning_percent"
    )) or 5.0
    transferred = flt(mip.transferred_weight_kg)
    over_threshold = bool(transferred) and remaining > (transferred * threshold_pct / 100.0)

    return {
        "transferred": transferred,
        "used_in_fg": flt(mip.used_in_fg_weight_kg, 3),
        "planned_return": planned_return,
        "returned": returned,
        "remaining": remaining,
        "pending_return": pending,
        "pending_return_kg": flt(sum(p["qty"] for p in pending), 3),
        "claimed": claimed,
        "threshold_pct": threshold_pct,
        "over_threshold": over_threshold,
        "final_entry_exists": bool(_final_manufacture_entry(mip)),
    }


def _final_manufacture_entry(mip):
    """The job's final Stock Entry, if it has been made. Process loss cannot be
    judged before it exists -- until the finished goods are booked, material still
    at the supplier is work in progress, not loss."""
    if not mip.subcontracting_order:
        return None
    return frappe.db.get_value(
        "Stock Entry",
        {"subcontracting_order": mip.subcontracting_order,
         "stock_entry_type": "Manufacture", "docstatus": 1},
        "name",
    )


@frappe.whitelist()
def create_mip_process_loss_entry(mip_name, reason, absorb_unreturned=0):
    """Write off what never came back, with a reason, and close the job's material.

    The last step of the chain: transferred, less what the job used, less what
    physically returned, is what the supplier could not account for -- offcut dust,
    cutting loss, short return. It is real stock standing in the supplier warehouse
    under this job's name, and until it is issued out the warehouse says the job
    still has material it does not have.

    Refused before the final Stock Entry exists: material at the supplier is work in
    progress until the finished goods are booked, not loss.

    `absorb_unreturned` is the user's answer to the one question this cannot decide:
    excess was declared to return and has not. Either make that return entry first,
    or say plainly that it is not coming -- in which case those rows are folded into
    the loss. Refused while another Material Planning has claimed any of it: a plan
    is counting on that steel, and it must be unallocated there first rather than
    written off underneath it.
    """
    if not frappe.has_permission("Material Issue Plan", "write"):
        frappe.throw(_("Not permitted to modify this Material Issue Plan"), frappe.PermissionError)

    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Enter a reason — a write-off with no explanation is not one."),
                     title=_("Reason Required"))

    mip = frappe.get_doc("Material Issue Plan", mip_name)
    _ensure_mip_editable(mip)

    if not _final_manufacture_entry(mip):
        frappe.throw(
            _("Make the Final Stock Entry first. Until the finished goods are booked, "
              "material at the supplier is work in progress — not loss."),
            title=_("Final Stock Entry Not Made"),
        )

    state = get_mip_process_loss_state(mip_name)
    absorb = bool(int(absorb_unreturned or 0))

    if state["pending_return_kg"] > 0.001 and not absorb:
        frappe.throw(
            _("{0} Kg is still declared to return but has not come back.<br><br>"
              "Make the Return Excess entry for it first — or confirm it is not coming, "
              "and it will be written off with the rest.")
            .format(state["pending_return_kg"]),
            title=_("Excess Still Awaiting Return"),
        )

    if absorb and state["claimed"]:
        frappe.throw(
            _("Another Material Planning is counting on this material, so it cannot be "
              "written off:<br><br>{0}<br><br>Unallocate it there first.")
            .format("<br>".join(
                "<b>{0}</b> — row {1} ({2}, {3} Kg)".format(c["plan"], c["idx"], c["item_code"], c["qty"])
                for c in state["claimed"]
            )),
            title=_("Claimed by Another Plan"),
        )

    at_supplier = _job_stock_at_supplier(mip)
    if not at_supplier:
        frappe.throw(_("Nothing is left at the supplier for this job — there is nothing to write off."),
                     title=_("Nothing to Write Off"))

    se_items = [
        {
            "item_code": item_code,
            "qty": qty,
            "uom": frappe.db.get_value("Item", item_code, "stock_uom") or "Kg",
            "s_warehouse": mip.supplier_warehouse,
            "batch_no": batch_no or None,
            "use_serial_batch_fields": 1 if batch_no else 0,
        }
        for (item_code, batch_no), qty in sorted(at_supplier.items())
        if qty > 0.001
    ]

    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Issue",
        "company": mip.company,
        "custom_mip_ref": mip_name,
        "custom_sco_ref": mip.subcontracting_order or None,
        "items": se_items,
    })
    se.insert(ignore_permissions=True)

    # The rows folded in are no longer awaiting anything -- they were written off.
    if absorb:
        for r in (mip.excess_return_items or []):
            if not r.stock_entry_created and flt(r.qty) > 0:
                r.return_reason = (
                    (r.return_reason or "").strip() + " " if r.return_reason else ""
                ) + _("[Written off as process loss: {0}]").format(reason)
                r.stock_entry_created = 1

    mip.process_loss_weight_kg = flt(sum(i["qty"] for i in se_items), 3)
    mip.process_loss_reason = reason
    mip.flags.mfx_saved_by_another_document = True
    mip.save(ignore_permissions=True)
    mip.add_comment("Comment", _("Process loss {0} Kg written off: {1}").format(
        mip.process_loss_weight_kg, reason))

    return {"stock_entry": se.name, "process_loss_kg": mip.process_loss_weight_kg}


def _job_stock_at_supplier(mip):
    """What this job still has standing at the supplier, per (item, batch).

    Netted across the supplier warehouse boundary from this job's own Stock
    Entries -- in adds, out subtracts -- rather than read from the warehouse's live
    stock, because a supplier warehouse is shared across every order placed with
    that supplier and reading it would pull in other jobs' material.
    """
    if not (mip.supplier_warehouse and mip.subcontracting_order):
        return {}
    rows = frappe.db.sql(
        """
        SELECT sed.item_code, IFNULL(sed.batch_no, '') AS batch_no,
               SUM(CASE WHEN sed.t_warehouse = %(wh)s THEN sed.qty
                        WHEN sed.s_warehouse = %(wh)s THEN -sed.qty
                        ELSE 0 END) AS qty
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE (se.custom_sco_ref = %(sco)s OR se.subcontracting_order = %(sco)s)
          AND se.docstatus = 1
          AND (sed.t_warehouse = %(wh)s OR sed.s_warehouse = %(wh)s)
        GROUP BY sed.item_code, sed.batch_no
        HAVING SUM(CASE WHEN sed.t_warehouse = %(wh)s THEN sed.qty
                        WHEN sed.s_warehouse = %(wh)s THEN -sed.qty
                        ELSE 0 END) > 0
        """,
        {"wh": mip.supplier_warehouse, "sco": mip.subcontracting_order},
        as_dict=True,
    )
    return {(r.item_code, r.batch_no): flt(r.qty, 3) for r in rows}


def _excess_return_source_rows(mip, in_rows):
    """The 'out' half of the return: what to take from the supplier for each off-cut.

    An excess row carries no batch on purpose -- an off-cut comes back as one shape
    however many batches it was drawn from -- so the batches are chosen here, from
    what this job actually has standing at the supplier, largest first. A row's
    weight can therefore be met from more than one batch.

    Returns (rows, shortfalls). A shortfall means the plan is asking to return more
    than is left, which the caller refuses rather than quietly returning less: the
    difference is either already consumed or already returned, and pretending
    otherwise is how the counts drifted in the first place.
    """
    available = _job_stock_at_supplier(mip)
    out_rows, shortfalls = [], []

    for item in in_rows:
        wanted = flt(item["qty"], 3)
        item_code = item["item_code"]
        candidates = sorted(
            [(k, v) for k, v in available.items() if k[0] == item_code and v > 0],
            key=lambda kv: -kv[1],
        )
        for key, have in candidates:
            if wanted <= 0.001:
                break
            take = flt(min(wanted, have), 3)
            if take <= 0:
                continue
            out_rows.append({
                "item_code": item_code,
                "qty": take,
                "uom": item.get("uom") or "Kg",
                "s_warehouse": mip.supplier_warehouse,
                # The quantity is a ledger fact, so this row carries no dimensions:
                # validate_stock_entry recomputes Qty from Length x Sec Qty for
                # Structurals and Plates, and the batch's own length would make it
                # try to move a whole plate that is no longer there.
                "batch_no": key[1] or None,
                "use_serial_batch_fields": 1 if key[1] else 0,
            })
            available[key] = flt(have - take, 3)
            wanted = flt(wanted - take, 3)

        if wanted > 0.001:
            shortfalls.append(
                _("{0}: {1} Kg short").format(item_code, flt(wanted, 3))
            )

    return out_rows, shortfalls


def _cut_sheet_w1_totals(raw_items):
    """W1 weight per batch, from the Cut Sheet governing it — the most a cut plate
    can yield in pieces, whatever the uncut plate happens to weigh.

    Keyed by batch alone: a Cut Sheet is unique per batch, and the batch is what
    the popup's stock figure is about."""
    batches = {i.get("batch_no") for i in raw_items if i.get("batch_no")}
    if not batches:
        return {}
    return {
        cs.batch_no: flt(cs.w1_total_qty)
        for cs in frappe.get_all(
            "Cut Sheet",
            # A sheet set aside is not a cut plan any more, so it must not cap
            # anything either.
            filters={"batch_no": ["in", list(batches)], "status": ["!=", "Inactive"]},
            fields=["batch_no", "w1_total_qty"],
        )
        if flt(cs.w1_total_qty) > 0
    }


def _available_for_transfer(item_code, batch_no, warehouse, w1_totals):
    """Free stock, never more than the cut plan can actually yield."""
    free = flt(_batch_free_qty(item_code, batch_no, warehouse), 3)
    w1 = w1_totals.get(batch_no)
    if w1 is None:
        return free
    return flt(min(free, w1), 3)


@frappe.whitelist()
def get_mip_pending_items(mip_name):
    """Raw-material items reserved for this plan but not yet transferred. Each row
    also carries duno_mark_no/drawing so the transfer popup can filter by them."""
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    ctx = get_target_context(mip)
    if not mip.source_warehouse:
        frappe.throw(_("Please set the Source Warehouse (RM) on this Material Issue Plan first."))

    source_warehouse = mip.source_warehouse
    primary_warehouse = ctx.primary_warehouse
    cnc_warehouse = mip.cnc_warehouse or ""

    raw_items = []
    mp_names, duno_scope = _linked_mp_names_and_duno_scope(mip)
    # Sec Qty is returned exactly as planned -- fractional when several drawings
    # share one batch (e.g. 4.5 Nos). Nothing is rounded automatically: turning a
    # fraction into whole physical pieces is the user's call, made row by row in
    # the transfer popup, which books the resulting surplus as excess to return
    # (see update_transfer_sec_qty).
    for mp_name in mp_names:
        raw_items.extend(_get_mp_reserved_batches(
            mp_name, source_warehouse, primary_warehouse, duno_filter=duno_scope.get(mp_name)
        ))

    # A row drawing from a Cut Sheet only ever offers its To Use (W1) weight for
    # transfer -- the Balance (W2) is what stays behind on the batch, not more
    # material to send onward. Capping here (rather than after the primary_done/
    # cnc_done netting below) means once W1 has been fully transferred the row
    # simply stops appearing as pending; the remainder is never offered.
    cut_sheet_qty_by_key = _cut_sheet_caps(mip)
    for item in raw_items:
        cap = cut_sheet_qty_by_key.get((item["item_code"], item.get("batch_no")))
        if cap is not None:
            item["qty"] = flt(min(flt(item["qty"]), cap), 3)

    # What a cut batch can offer at all, for the popup's "In Stock" column.
    #
    # That column reported the batch's whole free weight, which on a cut plate is
    # the entire uncut sheet -- 5,877.600 Kg against a planned 1,248.503, when only
    # the W1 pieces (2,449.000 Kg) are being cut from it at all. Read straight, it
    # said there was four times more of this material available than the cut plan
    # would ever yield.
    #
    # Capped at the sheet's W1 total rather than replaced by it: the column still
    # has to answer "has the stock actually arrived", so a batch not yet received
    # must still read 0 (a Material Issue Plan is routinely made before the
    # Purchase Receipt lands).
    w1_totals = _cut_sheet_w1_totals(raw_items)

    if not raw_items:
        return []

    # duno/drawing/sales_order/customer_drawing_number lookup per (item_code, batch_no),
    # from the MIP's own raw_materials snapshot, for the transfer popup's filters.
    #
    # Keyed on `planned_item or item_code` -- the item the BATCH belongs to -- because
    # that is the item_code _get_mp_reserved_batches puts on the rows being looked up.
    # Keying on the requirement's own item_code instead missed every alternate-item
    # row (a requirement for ISMB450 filled from an ISA150 batch), leaving its DUNO,
    # Sales Order and Customer Drawing Number blank in the transfer popup and
    # unreachable by its filters.
    def _by_key(fieldname):
        return {
            ((r.planned_item or r.item_code), r.batch_no or ""): r.get(fieldname) or ""
            for r in (mip.raw_materials or [])
        }

    duno_by_key = _by_key("duno_mark_no")
    # What the drawings actually call for, as opposed to what the reserved batches
    # weigh. The consolidated excess tab is the difference between the two.
    #
    # drawing_planned_weight on a row is the WHOLE requirement's weight, not that
    # row's share of it: a drawing needing 324.224 Kg of ISA100 that is filled
    # from two batches carries 324.224 on both rows. So neither reading is right
    # on its own -- taking one row's figure understates a batch covering many
    # requirements, and adding them up counts a split requirement twice. Each row
    # is given its share instead, in proportion to the weight it actually carries,
    # so the shares add back to the requirement exactly.
    req_totals = {}
    for r in (mip.raw_materials or []):
        req_key = ((r.planned_item or r.item_code), r.customer_drawing_number or "",
                   flt(r.length), flt(r.width), flt(r.thickness))
        agg = req_totals.setdefault(req_key, {"weight": 0.0, "qty": 0.0})
        agg["weight"] = flt(r.drawing_planned_weight)
        agg["qty"] = flt(agg["qty"] + flt(r.qty), 3)

    drawing_wt_by_key = {}
    for r in (mip.raw_materials or []):
        req_key = ((r.planned_item or r.item_code), r.customer_drawing_number or "",
                   flt(r.length), flt(r.width), flt(r.thickness))
        agg = req_totals.get(req_key) or {"weight": 0.0, "qty": 0.0}
        share = (
            flt(agg["weight"]) * (flt(r.qty) / flt(agg["qty"]))
            if flt(agg["qty"]) else flt(agg["weight"])
        )
        key = ((r.planned_item or r.item_code), r.batch_no or "")
        drawing_wt_by_key[key] = flt(drawing_wt_by_key.get(key, 0) + share, 3)

    so_by_key = _by_key("sales_order")
    cdn_by_key = _by_key("customer_drawing_number")
    drawing_by_duno = {d.duno_mark_no: d.drawing for d in (mip.drawing_items or []) if d.duno_mark_no}

    totals = {}
    for item in raw_items:
        is_cnc = bool(item.get("cnc_process")) and bool(cnc_warehouse)
        key = (item["item_code"], item.get("batch_no") or "", is_cnc)
        if key in totals:
            totals[key]["qty"] = flt(totals[key]["qty"] + item["qty"], 3)
            totals[key]["custom_sec_qty"] = flt(
                totals[key]["custom_sec_qty"] + item.get("custom_sec_qty", 0), 3
            )
        else:
            totals[key] = dict(item)
            totals[key]["cnc_process"] = 1 if is_cnc else 0

    primary_done = {}
    for r in frappe.db.sql("""
        SELECT sed.item_code, sed.batch_no, SUM(sed.qty) AS qty
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.custom_mip_ref = %s
          AND se.stock_entry_type = %s
          AND se.docstatus != 2
        GROUP BY sed.item_code, sed.batch_no
    """, (mip_name, ctx.primary_se_type), as_dict=True):
        primary_done[(r.item_code, r.batch_no or "")] = flt(r.qty)

    cnc_done = {}
    if cnc_warehouse:
        for r in frappe.db.sql("""
            SELECT sed.item_code, sed.batch_no, SUM(sed.qty) AS qty
            FROM `tabStock Entry Detail` sed
            JOIN `tabStock Entry` se ON se.name = sed.parent
            WHERE se.custom_mip_ref = %s
              AND se.stock_entry_type = 'Material Transfer'
              AND se.docstatus != 2
              AND sed.t_warehouse = %s
            GROUP BY sed.item_code, sed.batch_no
        """, (mip_name, cnc_warehouse), as_dict=True):
            cnc_done[(r.item_code, r.batch_no or "")] = flt(r.qty)

    result = []
    for (item_code, batch_no, is_cnc), item in totals.items():
        done_qty = (cnc_done if is_cnc else primary_done).get((item_code, batch_no), 0)
        pending_qty = flt(item["qty"] - done_qty, 3)
        if pending_qty <= 0:
            continue
        total_qty = flt(item["qty"])
        ratio = pending_qty / total_qty if total_qty else 0
        duno = duno_by_key.get((item_code, batch_no), "")
        result.append({
            "item_code": item_code,
            "item_name": frappe.db.get_value("Item", item_code, "item_name") or item_code,
            "batch_no": batch_no,
            "qty": pending_qty,
            # Progress so far, so a second visit to the transfer popup can show what
            # an earlier partial transfer already sent rather than only what is left.
            "planned_qty": total_qty,
            "transferred_qty": flt(done_qty, 3),
            # What the batch physically holds in the source warehouse right now. A
            # Material Issue Plan is often created before the Purchase Receipt lands,
            # so a row can be planned and reserved while the stock is not in yet --
            # showing 0 here is the difference between "nothing to send" and "not
            # arrived yet".
            "available_qty": _available_for_transfer(
                item_code, batch_no, source_warehouse, w1_totals
            ),
            "uom": item.get("uom") or "Kg",
            "custom_sec_qty": flt(flt(item.get("custom_sec_qty", 0)) * ratio, 3),
            "custom_sec_uom": item.get("custom_sec_uom") or "",
            "s_warehouse": source_warehouse,
            "t_warehouse": cnc_warehouse if is_cnc else primary_warehouse,
            "cnc_process": 1 if is_cnc else 0,
            "use_serial_batch_fields": 1,
            "custom_length": flt(item.get("custom_length", 0), 3),
            "custom_width": flt(item.get("custom_width", 0), 3),
            "custom_thickness": flt(item.get("custom_thickness", 0), 3),
            "custom_unit_weight": flt(item.get("custom_unit_weight", 0), 4),
            "custom_parent_item_group": item.get("custom_parent_item_group") or "",
            "duno_mark_no": duno,
            "drawing": drawing_by_duno.get(duno, ""),
            "sales_order": so_by_key.get((item_code, batch_no), ""),
            "customer_drawing_number": cdn_by_key.get((item_code, batch_no), ""),
            # Scaled by the same ratio as qty and Sec Qty: on a partial transfer
            # the tab must compare what is being sent against the share of the
            # requirement it covers, not against the whole of it.
            "drawing_planned_weight": flt(
                flt(drawing_wt_by_key.get((item_code, batch_no), 0)) * ratio, 3),
        })

    for row in result:
        # No automatic rounding -- these stay 0 unless the user chooses to round
        # a row up in the transfer popup (update_transfer_sec_qty fills them in).
        row["round_up_excess_kg"] = 0.0
        row["round_up_excess_pieces"] = 0.0

    # Keep every row of one item together, batches in a stable order within it.
    # Rows are collected per Material Planning and then per source table, so an item
    # drawn from two plans (or from both Material Mapping and Exact Match) came out
    # scattered down the list. Two batches of the same item are two legitimate lines --
    # a transfer has to move a specific batch -- but split apart by unrelated rows they
    # read as a duplicate with the wrong total, which is exactly how this was reported.
    result.sort(key=lambda r: (r["item_code"], r.get("batch_no") or ""))

    return result


@frappe.whitelist()
def update_transfer_sec_qty(mip_name, item_code, batch_no, planned_sec_qty, planned_qty, new_sec_qty):
    """Recalculate one transfer row after the user edits its Sec Qty by hand.

    Nothing rounds automatically any more: the plan hands over the exact
    fractional Sec Qty a drawing needs (e.g. 2.5 Nos), and it is the user who
    decides — here, in the transfer popup — whether to hand over whole pieces
    instead. Raising 2.5 to 3 issues one extra half-piece worth of weight, and
    that surplus is what comes back through Return Excess Entry.

    Validates the new figure against real free stock in the source warehouse
    before accepting it, so a manual bump can never plan a transfer the batch
    cannot cover. Returns the recomputed Kg/excess plus a `blocked` flag and
    message; it only computes, it never writes.
    """
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    planned_sec_qty, planned_qty, new_sec_qty = flt(planned_sec_qty), flt(planned_qty), flt(new_sec_qty)

    if new_sec_qty <= 0:
        frappe.throw(_("Sec Qty must be greater than zero."))
    if planned_sec_qty <= 0 or planned_qty <= 0:
        frappe.throw(_("This row has no planned Sec Qty to recalculate from."))

    kg_per_piece = planned_qty / planned_sec_qty
    new_qty = flt(new_sec_qty * kg_per_piece, 3)
    excess_pieces = flt(new_sec_qty - planned_sec_qty, 3)
    excess_kg = flt(new_qty - planned_qty, 3)

    available = flt(_batch_free_qty(item_code, batch_no, mip.source_warehouse), 3)
    blocked = new_qty > available + 0.001
    message = None
    if blocked:
        message = _(
            "Batch {0} has only {1} Kg free in {2}. {3} Nos needs {4} Kg."
        ).format(batch_no, available, mip.source_warehouse, flt(new_sec_qty, 3), new_qty)

    return {
        "qty": new_qty,
        "custom_sec_qty": flt(new_sec_qty, 3),
        "round_up_excess_kg": max(0.0, excess_kg),
        "round_up_excess_pieces": max(0.0, excess_pieces),
        "available_qty": available,
        "blocked": blocked,
        "message": message,
    }


def _batch_free_qty(item_code, batch_no, warehouse):
    """Physical qty of `batch_no` sitting in `warehouse` right now."""
    if not (batch_no and warehouse):
        return 0.0
    from erpnext.stock.doctype.batch.batch import get_batch_qty

    return flt(get_batch_qty(batch_no=batch_no, warehouse=warehouse, item_code=item_code) or 0)


def _apply_transfer_excess_to_raw_materials(mip, item, excess_kg):
    """Book a transfer's rounding surplus onto the raw-material rows it came from, so
    the difference between the whole pieces issued and the fractional Sec Nos planned
    is visible on the item table itself and not only in Excess Material Items.

    One batch is routinely shared by several DUNO rows, and the transfer popup shows
    them as a single aggregated line -- so the surplus that line produces belongs to
    all of its contributors, not to whichever row happens to sort first. It is split
    in proportion to each row's Sec Qty, which is the same weighting the popup used
    to aggregate them in the first place, so the parts add back up to the whole.

    Accumulates: a second partial transfer that rounds up again adds to what is
    already booked, matching how _log_round_up_excess accumulates its own row."""
    # Match on the item the BATCH belongs to (planned_item), falling back to the
    # requirement's own item -- the same `planned_item or item_code` rule the transfer
    # Stock Entry itself uses to pick its row's item. Comparing item_code alone missed
    # every alternate-item row: a requirement for ISMB450 satisfied by an ISA150 batch
    # produces a transfer line whose item_code is ISA150, which matched no row, so the
    # rounding surplus was silently dropped instead of landing in transfer_excess_kg.
    rows = [
        r for r in (mip.raw_materials or [])
        if (r.planned_item or r.item_code) == item["item_code"]
        and (r.batch_no or "") == (item.get("batch_no") or "")
        and bool(r.cnc_process) == bool(item.get("cnc_process"))
    ]
    if not rows:
        return

    total_sec = sum(flt(r.sec_qty) for r in rows)
    shares = [
        flt(excess_kg * flt(r.sec_qty) / total_sec, 3) if total_sec
        else flt(excess_kg / len(rows), 3)
        for r in rows
    ]
    # The last row absorbs the rounding remainder, so the parts always sum to
    # excess_kg exactly instead of drifting a few grams away from the Excess
    # Material Items row they are supposed to reconcile against.
    shares[-1] = flt(excess_kg - sum(shares[:-1]), 3)

    for r, share in zip(rows, shares):
        r.transfer_excess_kg = flt(flt(r.transfer_excess_kg) + share, 3)


def _log_round_up_excess(mip, items, excess_plan=None):
    """After a transfer whose Sec Qty the user rounded up (see update_transfer_sec_qty), log the
    rounding surplus into excess_return_items so it flows through the existing Return
    Excess Entry workflow once physically confirmed. Keyed by (item_code, batch_no) via
    the same source_table/source_row find-or-update pattern
    _sync_excess_return_from_raw_materials already uses -- a second transfer that rounds
    up the SAME item/batch again ACCUMULATES into the one existing row instead of piling
    up a new row every time.

    Length/Width/Thickness/Sec Qty come from the popup's own excess row when the user
    filled it in -- they are looking at the actual off-cut, which is the only place its
    real shape is known.

    Where they did not, these fall back to the BATCH's standard dimensions and the
    fractional excess-piece count. Those recompute back to exactly the tracked excess
    Kg, so the Return Excess Entry dialog opens on a correct, non-zero figure rather
    than losing the tracked amount (its live preview recalculates Qty FROM these
    fields). That fallback is only a placeholder standing in for "one standard piece,
    mostly unused" -- the real leftover is rarely that shape, so it is still worth
    correcting later if it was not entered at transfer time.

    Return Warehouse defaults to the plan's raw-material warehouse, which is where an
    off-cut normally goes back to; the popup lets it be pointed at a scrap warehouse
    instead, per row."""
    SOURCE_TABLE = "Round Up Sec Qty for Transfer"
    by_key = {
        (r.source_table, r.source_row): r
        for r in (mip.excess_return_items or [])
        if r.source_table == SOURCE_TABLE
    }
    changed = False
    for item in items:
        excess_kg = flt(item.get("round_up_excess_kg"))
        if excess_kg <= 0:
            continue
        _apply_transfer_excess_to_raw_materials(mip, item, excess_kg)

        # Rounding a fractional piece count up to whole pieces is a person's decision,
        # taken here rather than by the plan, and the surplus it creates is exactly the
        # kind of figure someone asks about weeks later. One entry per row rounded.
        log_decision(
            "Round Up at Transfer",
            reference_doctype="Material Issue Plan",
            reference_name=mip.name,
            item_code=item.get("item_code"),
            batch_no=item.get("batch_no"),
            previous_sec_qty=flt(item.get("planned_sec_qty")),
            sec_qty=flt(item.get("custom_sec_qty")),
            qty=excess_kg,
            details=_("Rounded {0} up to {1} Nos on batch {2}, {3} Kg of surplus to return.").format(
                flt(item.get("planned_sec_qty"), 3), flt(item.get("custom_sec_qty"), 3),
                item.get("batch_no") or "", flt(excess_kg, 3),
            ),
        )

        # What the user measured in the popup's excess row wins over the placeholder
        # derived from the batch. They are looking at the actual off-cut; the batch's
        # standard dimensions are only a stand-in for "one whole piece, mostly unused"
        # and are almost never the real shape.
        # An item the user planned on the consolidated tab is booked once, by item,
        # in _log_consolidated_excess. Booking it here as well -- once per batch row
        # -- would count the same off-cut two and three times over.
        if (excess_plan or {}).get(item["item_code"]):
            continue
        measured = item.get("excess_entry") or {}
        excess_pieces = flt(measured.get("sec_qty")) or flt(item.get("round_up_excess_pieces"))
        length = flt(measured.get("length")) or flt(item.get("custom_length"))
        width = flt(measured.get("width")) or flt(item.get("custom_width"))
        thickness = flt(measured.get("thickness")) or flt(item.get("custom_thickness"))
        return_warehouse = measured.get("return_warehouse") or mip.source_warehouse or ""
        source_row = f"{item['item_code']}|{item.get('batch_no') or ''}"
        key = (SOURCE_TABLE, source_row)
        target = by_key.get(key)
        if target and (target.stock_entry_created or target.mapped_material_planning):
            # Already returned to stock, or already claimed elsewhere -- start a fresh
            # row instead of drifting a historical, already-settled entry.
            target = None
        if target:
            new_qty = flt(flt(target.qty) + excess_kg, 3)
            new_pieces = flt(flt(target.sec_qty) + excess_pieces, 3)
            target.qty = new_qty
            target.sec_qty = new_pieces
            if not target.length:
                target.length = length
            if not target.width:
                target.width = width
            if not target.thickness:
                target.thickness = thickness
            if not target.get("return_warehouse"):
                target.return_warehouse = return_warehouse
        else:
            target = mip.append("excess_return_items", {
                "source_table": SOURCE_TABLE,
                "source_row": source_row,
                "item_code": item["item_code"],
                "item_name": item.get("item_name") or item["item_code"],
                "parent_item_group": item.get("custom_parent_item_group") or "",
                "unit_weight": flt(item.get("custom_unit_weight")),
                "length": length,
                "width": width,
                "thickness": thickness,
                "sec_qty": excess_pieces,
                "sec_uom": item.get("custom_sec_uom") or "",
                "uom": item.get("uom") or "Kg",
                "qty": excess_kg,
                "return_warehouse": return_warehouse,
                "return_reason": _(
                    "Rounding surplus from \"Round Up Sec Qty for Transfer\" -- placeholder "
                    "dimensions (standard piece size); confirm the exact leftover once "
                    "this material is cut."
                ),
            })
            by_key[key] = target
        changed = True
    if changed:
        mip.save(ignore_permissions=True)


CONSOLIDATED_EXCESS_SOURCE = "Consolidated Excess Return Plan"


def _log_consolidated_excess(mip, items, excess_plan):
    """Book the excess the user planned on the transfer popup's second tab.

    One row per ITEM, with no batch reference: the tab consolidates the transfer by
    item precisely because an off-cut comes back as one shape however many batches
    it was drawn from.

    Two figures are in play and both are kept. The Kg booked is what the user
    measured, because that is the off-cut that will physically come back. The
    system's own figure -- what the transfer sent beyond what the drawings called
    for -- is written into the reason line beside it, so a row that does not
    reconcile says so on its face rather than only in the popup that created it.

    A second transfer for the same item accumulates into the existing row, matching
    how _log_round_up_excess treats its own, and skips a row already returned to
    stock or claimed elsewhere rather than drifting a settled entry.
    """
    if not excess_plan:
        return

    planned_kg, meta = {}, {}
    for item in items:
        code = item["item_code"]
        if code not in excess_plan:
            continue
        planned_kg[code] = flt(planned_kg.get(code, 0) + flt(item.get("qty")), 3)
        drawing = flt(planned_kg.get("_drawing_" + code, 0) + flt(item.get("drawing_planned_weight")), 3)
        planned_kg["_drawing_" + code] = drawing
        meta.setdefault(code, item)

    by_key = {
        r.source_row: r
        for r in (mip.excess_return_items or [])
        if r.source_table == CONSOLIDATED_EXCESS_SOURCE
    }

    changed = False
    for code, entry in excess_plan.items():
        item = meta.get(code)
        if not item:
            continue
        length = flt(entry.get("length"))
        width = flt(entry.get("width"))
        sec_qty = flt(entry.get("sec_qty"))
        thickness = flt(item.get("custom_thickness"))
        entered_kg = flt(calculate_qty(
            item.get("custom_parent_item_group") or "",
            length, width, thickness,
            flt(item.get("custom_unit_weight")), sec_qty,
        ) or 0, 3)
        if entered_kg <= 0:
            # Nothing measurable was typed for this item -- no row to book.
            continue

        system_kg = flt(planned_kg.get(code, 0) - planned_kg.get("_drawing_" + code, 0), 3)
        if system_kg <= 0:
            # The transfer sent no more than the drawings called for, so there is no
            # off-cut for this item however convincing the measurements look. The popup
            # closes the boxes on such a row; this is the same rule for an import or an
            # API call, which would otherwise book an off-cut nobody cut and leave it
            # sitting on the plan waiting to be collected.
            continue

        difference = flt(entered_kg - system_kg, 3)
        reason = _(
            "Planned on the transfer popup's consolidated excess tab. "
            "Transfer sent {0} Kg against {1} Kg planned on the drawings, so the "
            "system figure is {2} Kg; {3} Kg was measured, a difference of {4} Kg."
        ).format(
            flt(planned_kg.get(code, 0), 3), flt(planned_kg.get("_drawing_" + code, 0), 3),
            system_kg, entered_kg, ("+%s" % difference) if difference > 0 else difference,
        )

        target = by_key.get(code)
        if target and (target.stock_entry_created or target.mapped_material_planning):
            target = None
        if target:
            target.qty = flt(flt(target.qty) + entered_kg, 3)
            target.sec_qty = flt(flt(target.sec_qty) + sec_qty, 3)
            target.length = length or target.length
            target.width = width or target.width
            target.return_reason = reason
        else:
            target = mip.append("excess_return_items", {
                "source_table": CONSOLIDATED_EXCESS_SOURCE,
                "source_row": code,
                "item_code": code,
                "item_name": item.get("item_name") or code,
                "parent_item_group": item.get("custom_parent_item_group") or "",
                "unit_weight": flt(item.get("custom_unit_weight")),
                "length": length,
                "width": width,
                "thickness": thickness,
                "sec_qty": sec_qty,
                "sec_uom": item.get("custom_sec_uom") or "",
                "uom": item.get("uom") or "Kg",
                "qty": entered_kg,
                "return_warehouse": entry.get("return_warehouse") or mip.source_warehouse or "",
                "return_reason": reason,
            })
            by_key[code] = target
        changed = True

    if changed:
        mip.save(ignore_permissions=True)


@frappe.whitelist()
def has_cnc_stock(mip_name):
    """Returns True if at least one submitted Stock Entry has transferred material
    to this MIP's CNC warehouse, so the UI can conditionally show 'CNC to Supplier/WIP'."""
    mip = frappe.get_cached_doc("Material Issue Plan", mip_name)
    if not mip.cnc_warehouse:
        return False
    result = frappe.db.sql("""
        SELECT 1
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.custom_mip_ref = %s
          AND se.stock_entry_type = 'Material Transfer'
          AND se.docstatus = 1
          AND sed.t_warehouse = %s
        LIMIT 1
    """, (mip_name, mip.cnc_warehouse))
    return bool(result)


@frappe.whitelist()
def get_mip_cnc_button_state(mip_name):
    """Which of the two CNC transfer buttons the form should show.

    {"show_to_cnc": bool, "show_cnc_forward": bool}

    show_to_cnc — is any CNC-flagged row still waiting to go TO the CNC warehouse?
    "To CNC Warehouse" used to appear whenever a CNC warehouse was merely SET, so it
    stayed on screen forever, long after every CNC row had moved and its popup could
    only ever open empty. Deriving it from what is actually pending also makes it
    self-correcting in the case the client asked about: tick CNC on another Material
    Planning row, it flows into this plan, that row is pending again, and the button
    comes back on its own -- no stored state to keep in step.

    show_cnc_forward — is anything sitting AT the CNC warehouse RIGHT NOW to forward
    onward? This used to come from has_cnc_stock, which answers a historical question
    ("has anything ever been sent to CNC?"), so the button stayed on screen after the
    last batch had been forwarded and its popup could only report "Nothing at CNC".
    Asking what is actually pending fixes the same complaint on both buttons.

    Both are read fresh on every form refresh, so neither can go stale."""
    mip = frappe.get_cached_doc("Material Issue Plan", mip_name)
    if not mip.cnc_warehouse:
        return {"show_to_cnc": False, "show_cnc_forward": False}

    def _any(fn, predicate=bool):
        # A plan that is not transfer-ready yet (no linked order, no source warehouse)
        # raises here. Show the button in that case so the user still gets the readiness
        # message explaining what is missing, rather than a silently absent button.
        try:
            return any(predicate(row) for row in fn(mip_name))
        except Exception:
            return True

    # Same sources the two popups themselves filter on, so each button appears exactly
    # when its popup would have something to offer.
    return {
        "show_to_cnc": _any(get_mip_pending_items, lambda r: r.get("cnc_process")),
        "show_cnc_forward": _any(get_mip_cnc_pending_items),
    }


def _get_mip_transfer_stock_entry_names(mip):
    """Names of submitted Stock Entries that physically transferred material for this
    MIP's SCO/WO (Send to Subcontractor / Material Transfer, tagged via
    custom_sco_ref/custom_wo_ref by _tag_stock_entry) -- the ones that make raw-material
    refresh unsafe/blocked. Shared by _get_already_transferred_batches and the
    "Refresh Raw Materials" guard, which needs the names themselves (not just the
    batches) to tell the user exactly what to delete to unblock a refresh."""
    filters = {"docstatus": 1}
    if mip.subcontracting_order:
        filters["custom_sco_ref"] = mip.subcontracting_order
    elif mip.work_order:
        filters["custom_wo_ref"] = mip.work_order
    else:
        return []
    return frappe.db.get_all("Stock Entry", filters=filters, pluck="name")


def _get_already_transferred_batches(mip):
    """Return the set of batch_nos already physically moved by submitted SEs for this MIP.
    After SE submission, is_reserved is cleared on MP rows, so without this exclusion
    already-transferred batches would appear as false-positive 'unreserved' warnings."""
    se_names = _get_mip_transfer_stock_entry_names(mip)
    if not se_names:
        return set()
    batch_nos = frappe.db.get_all(
        "Stock Entry Detail",
        filters={"parent": ["in", se_names]},
        pluck="batch_no",
    )
    return {b for b in batch_nos if b}


@frappe.whitelist()
def get_mip_readiness_check(mip_name):
    """Return a readiness summary for the MIP transfer pre-flight check.
    Checks all linked MPs for:
      - unmapped items (in unavailable_items — no batch, no stock)
      - unreserved items (batch assigned in mapping/ARM but not reserved AND not yet transferred)
    Returns {"unmapped": [...], "unreserved": [...]} so JS can warn the user
    before initiating transfer."""
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    mp_names = sorted({r.material_planning for r in (mip.drawing_items or []) if r.material_planning})

    transferred_batches = _get_already_transferred_batches(mip)

    unmapped = []
    unreserved = []
    at_supplier = []

    for mp_name in mp_names:
        mp = frappe.get_doc("Material Planning", mp_name)

        # Items in unavailable_items = no stock found / not yet purchased
        for r in (mp.unavailable_items or []):
            if not r.item_code:
                continue
            unmapped.append({
                "material_planning": mp_name,
                "table": "Unavailable Items",
                "row": r.idx,
                "item_code": r.item_code,
                "item_name": r.item_name or "",
                "duno_mark_no": r.duno_mark_no or "",
                "qty": flt(r.qty, 3),
                "uom": r.uom or "Kg",
            })

        # Material Mapping rows with batch but not reserved and not already transferred
        for r in (mp.material_mapping or []):
            if r.item_code and r.batch and not r.is_reserved:
                if r.batch not in transferred_batches:
                    unreserved.append({
                        "material_planning": mp_name,
                        "table": "Material Mapping",
                        "row": r.idx,
                        "item_code": r.item_code,
                        "item_name": r.item_name or "",
                        "batch": r.batch,
                        "duno_mark_no": r.duno_mark_no or "",
                        "qty": flt(r.qty, 3),
                        "uom": r.uom or "Kg",
                    })
            elif r.item_code and not r.batch and r.is_virtual_excess:
                # Not unmapped at all -- this row is an off-cut claimed through
                # Excess Material Mapping that is still physically at the supplier.
                # There is no batch in the source warehouse to move, so it can never
                # appear in the transfer list (_get_mp_reserved_batches skips rows
                # with no batch); reported separately so the popup can say why
                # rather than leaving the user hunting for a missing line.
                at_supplier.append({
                    "material_planning": mp_name,
                    "row": r.idx,
                    "item_code": r.item_code,
                    "item_name": r.item_name or "",
                    "duno_mark_no": r.duno_mark_no or "",
                    "qty": flt(r.qty, 3),
                    "uom": r.uom or "Kg",
                    "source_mip": r.virtual_excess_source_mip or "",
                })
            elif r.item_code and not r.batch:
                unmapped.append({
                    "material_planning": mp_name,
                    "table": "Material Mapping",
                    "row": r.idx,
                    "item_code": r.item_code,
                    "item_name": r.item_name or "",
                    "duno_mark_no": r.duno_mark_no or "",
                    "qty": flt(r.qty, 3),
                    "uom": r.uom or "Kg",
                })

        # Exact Match rows — batch assigned but not reserved / no batch assigned yet
        for r in (mp.available_raw_materials or []):
            if not r.item_code:
                continue
            if r.batch_no and not r.is_reserved:
                if r.batch_no not in transferred_batches:
                    unreserved.append({
                        "material_planning": mp_name,
                        "table": "Exact Match",
                        "row": r.idx,
                        "item_code": r.item_code,
                        "item_name": r.item_name or "",
                        "batch": r.batch_no,
                        "duno_mark_no": r.duno_mark_no or "",
                        "qty": flt(r.required_qty, 3),
                        "uom": r.uom or "Kg",
                    })
            elif not r.batch_no:
                unmapped.append({
                    "material_planning": mp_name,
                    "table": "Exact Match",
                    "row": r.idx,
                    "item_code": r.item_code,
                    "item_name": r.item_name or "",
                    "duno_mark_no": r.duno_mark_no or "",
                    "qty": flt(r.required_qty, 3),
                    "uom": r.uom or "Kg",
                })

    # CNC Process rows with nowhere to route to. Transfer decides the target
    # warehouse as `cnc_process AND cnc_warehouse` -- so with the CNC Warehouse
    # left blank the flag is quietly ignored and the material is issued straight
    # to the supplier, skipping CNC altogether. Nothing errors, and by the time
    # anyone notices the stock has physically moved, so surface it here, before
    # the transfer, rather than letting it pass silently.
    cnc_without_warehouse = []
    if not mip.cnc_warehouse:
        for r in (mip.raw_materials or []):
            if r.cnc_process and r.item_code:
                cnc_without_warehouse.append({
                    "material_planning": r.material_planning or "",
                    "table": "Raw Materials",
                    "row": r.idx,
                    "item_code": r.item_code,
                    "item_name": r.item_name or "",
                    "batch": r.batch_no or "",
                    "duno_mark_no": r.duno_mark_no or "",
                    "qty": flt(r.qty, 3),
                    "uom": r.uom or "Kg",
                })

    # Which Material Plannings the unreserved rows sit on, and how much they hold --
    # a reservation is a separate deliberate step there, and stock that is mapped but
    # not reserved is simply never offered for transfer, with nothing on this page to
    # say why. Name the plan and the weight so the fix is one click away.
    unreserved_by_mp = {}
    for r in unreserved:
        agg = unreserved_by_mp.setdefault(r["material_planning"], {"rows": 0, "qty": 0.0})
        agg["rows"] += 1
        agg["qty"] = flt(agg["qty"] + flt(r["qty"]), 3)
    unreserved_summary = [
        {"material_planning": k, "rows": v["rows"], "qty": v["qty"]}
        for k, v in sorted(unreserved_by_mp.items())
    ]

    return {
        "unmapped": unmapped,
        "unreserved": unreserved,
        "unreserved_summary": unreserved_summary,
        "cnc_without_warehouse": cnc_without_warehouse,
        # Informational, deliberately NOT part of has_issues: material already at
        # the supplier is a correct, finished state, not something to fix before
        # transferring the rest.
        "at_supplier": at_supplier,
        "supplier_warehouse": mip.supplier_warehouse or "",
        "has_issues": bool(unmapped or unreserved or cnc_without_warehouse),
    }


@frappe.whitelist()
def create_mip_transfer_entry(mip_name):
    """Transfer ALL pending non-CNC reserved material to the primary (Supplier/WIP)
    warehouse. CNC items are intentionally excluded — use 'To CNC Warehouse' for those.

    WARNING (Phase 1 H-07 / Report 3 Finding H-07): the frappe.db.commit()
    below ends the request's transaction early on purpose, to release
    read-locks before the Stock Entry insert and avoid a MySQL gap-lock
    deadlock. This means everything before that line is permanently committed
    regardless of what happens afterward -- there is no rollback path if a
    later step in this function fails. Do NOT add a write above the
    frappe.db.commit() line without re-reading this warning: a write
    introduced there would no longer be all-or-nothing with the rest of this
    function.
    """
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    _ensure_mip_editable(mip)
    _ensure_cnc_routing(mip)
    ctx = get_target_context(mip)
    pending = get_mip_pending_items(mip_name)
    if not pending:
        frappe.throw(_("No reserved batches pending transfer. Ensure batches are reserved in the linked Material Planning documents."))

    primary_rows = [p for p in pending if not p["cnc_process"]]
    if not primary_rows:
        frappe.throw(_("No pending items for the primary warehouse. CNC items can be transferred using 'To CNC Warehouse'."))

    # get_mip_pending_items() returns unprefixed keys (duno_mark_no/drawing/sales_order/
    # customer_drawing_number) for the transfer-picker dialog's own filters -- map them onto
    # Stock Entry Detail's custom_* fieldnames here (client change request Phase 1.3).
    for row in primary_rows:
        row["custom_drawing"] = row.get("drawing") or ""
        row["custom_duno_mark_no"] = row.get("duno_mark_no") or ""
        row["custom_customer_drawing_number"] = row.get("customer_drawing_number") or ""
        row["custom_sales_order"] = row.get("sales_order") or ""

    se = frappe.get_doc(_tag_stock_entry({
        "doctype": "Stock Entry",
        "stock_entry_type": ctx.primary_se_type,
        "company": ctx.company,
        "items": primary_rows,
    }, mip_name, ctx))
    frappe.db.commit()  # release read-locks before SE insert to avoid gap-lock deadlock
    se.insert(ignore_permissions=True)
    _log_round_up_excess(mip, primary_rows)
    # The parked popup state described what was about to happen; it just did.
    _clear_transfer_draft(mip.name, primary_rows)
    return {"primary_se": se.name}


@frappe.whitelist()
def create_mip_partial_transfer(mip_name, selected_items_json, transfer_type, excess_plan_json=None):
    """Create a draft Stock Entry for the caller-selected raw-material items.

    transfer_type: "primary" -> Send to Subcontractor/Material Transfer to the
                                supplier/WIP warehouse
                   "cnc"     -> Material Transfer to the CNC warehouse

    WARNING (Phase 1 H-07 / Report 3 Finding H-07): same manual mid-request
    frappe.db.commit() pattern as create_mip_transfer_entry above (releases
    read-locks before the Stock Entry insert to avoid a gap-lock deadlock) --
    do NOT add a write above that commit() call without re-reading its
    warning there first.
    """
    selected = _json.loads(selected_items_json) if isinstance(selected_items_json, str) else selected_items_json
    if not selected:
        frappe.throw(_("No items selected for transfer."))

    # One measured off-cut per ITEM, from the transfer popup's second tab. Keyed by
    # item_code and carrying no batch: an off-cut comes back as one shape however
    # many batches the item was drawn from. Absent when nothing was measured, and
    # _log_round_up_excess then falls back to its own placeholder as before.
    excess_plan = _json.loads(excess_plan_json) if isinstance(excess_plan_json, str) else (excess_plan_json or {})

    mip = frappe.get_doc("Material Issue Plan", mip_name)
    _ensure_mip_editable(mip)
    _ensure_cnc_routing(mip)
    ctx = get_target_context(mip)
    if not mip.source_warehouse:
        frappe.throw(_("Please set the Source Warehouse (RM) on this Material Issue Plan first."))

    if transfer_type == "cnc":
        if not mip.cnc_warehouse:
            frappe.throw(_("No CNC Warehouse set on this Material Issue Plan."))
        t_warehouse = mip.cnc_warehouse
        se_type = "Material Transfer"
    else:
        t_warehouse = ctx.primary_warehouse
        se_type = ctx.primary_se_type

    _validate_selected_against_stock(mip, selected)

    se_items = []
    for item in selected:
        se_items.append({
            "item_code": item["item_code"],
            "batch_no": item.get("batch_no") or "",
            "use_serial_batch_fields": 1,
            "qty": flt(item["qty"]),
            "uom": item.get("uom") or "Kg",
            "s_warehouse": mip.source_warehouse,
            "t_warehouse": t_warehouse,
            "custom_sec_qty": flt(item.get("custom_sec_qty") or 0),
            "custom_sec_uom": item.get("custom_sec_uom") or "",
            "custom_length": flt(item.get("custom_length") or 0),
            "custom_width": flt(item.get("custom_width") or 0),
            "custom_thickness": flt(item.get("custom_thickness") or 0),
            "custom_unit_weight": flt(item.get("custom_unit_weight") or 0),
            "custom_parent_item_group": item.get("custom_parent_item_group") or "",
            "custom_drawing": item.get("drawing") or "",
            "custom_duno_mark_no": item.get("duno_mark_no") or "",
            "custom_customer_drawing_number": item.get("customer_drawing_number") or "",
            "custom_sales_order": item.get("sales_order") or "",
        })

    se = frappe.get_doc(_tag_stock_entry({
        "doctype": "Stock Entry",
        "stock_entry_type": se_type,
        "company": ctx.company,
        "items": se_items,
    }, mip_name, ctx))
    frappe.db.commit()
    se.insert(ignore_permissions=True)
    _log_round_up_excess(mip, selected, excess_plan=excess_plan)
    _log_consolidated_excess(mip, selected, excess_plan)
    return se.name


@frappe.whitelist()
def get_mip_cnc_pending_items(mip_name):
    """Material sitting in the CNC warehouse still waiting to go on to the
    supplier/WIP warehouse.

    The CNC leg is deliberately a SECOND, separate Stock Entry: nothing can be
    forwarded that has not physically arrived at CNC first, so this reads only
    submitted transfers INTO the CNC warehouse and nets off whatever has already
    been forwarded out of it. Same row shape as get_mip_pending_items so the
    transfer popup can render either leg without knowing which it is.
    """
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    ctx = get_target_context(mip)
    if not mip.cnc_warehouse:
        frappe.throw(_("No CNC Warehouse set on this Material Issue Plan."))

    sent, already = _cnc_sent_and_forwarded(mip_name, mip.cnc_warehouse, ctx.primary_warehouse)

    result = []
    for r in sent:
        key = (r.item_code, r.batch_no or "")
        done = flt(already.get(key, 0), 3)
        total = flt(r.qty, 3)
        pending = flt(total - done, 3)
        if pending <= 0:
            continue
        ratio = pending / total if total else 0
        result.append({
            "item_code": r.item_code,
            "item_name": frappe.db.get_value("Item", r.item_code, "item_name") or r.item_code,
            "batch_no": r.batch_no or "",
            "qty": pending,
            "planned_qty": total,
            "transferred_qty": done,
            "available_qty": flt(_batch_free_qty(r.item_code, r.batch_no, mip.cnc_warehouse), 3),
            "uom": r.uom or frappe.db.get_value("Item", r.item_code, "stock_uom") or "Kg",
            "custom_sec_qty": flt(flt(r.custom_sec_qty) * ratio, 3),
            "custom_sec_uom": r.custom_sec_uom or "",
            "s_warehouse": mip.cnc_warehouse,
            "t_warehouse": ctx.primary_warehouse,
            "cnc_process": 0,
            "use_serial_batch_fields": 1,
            "custom_length": flt(r.custom_length, 3),
            "custom_width": flt(r.custom_width, 3),
            "custom_thickness": flt(r.custom_thickness, 3),
            "custom_unit_weight": flt(r.custom_unit_weight, 4),
            "custom_parent_item_group": r.custom_parent_item_group or "",
            "duno_mark_no": r.custom_duno_mark_no or "",
            "drawing": r.custom_drawing or "",
            "sales_order": r.custom_sales_order or "",
            "customer_drawing_number": r.custom_customer_drawing_number or "",
            "round_up_excess_kg": 0.0,
            "round_up_excess_pieces": 0.0,
        })
    return result


@frappe.whitelist()
def create_mip_cnc_partial_forward(mip_name, selected_items_json):
    """Forward a caller-selected subset out of the CNC warehouse -- the partial
    counterpart to create_mip_cnc_forward_entry, so a CNC batch can be released to
    the supplier in stages as machining finishes rather than all at once."""
    selected = _json.loads(selected_items_json) if isinstance(selected_items_json, str) else selected_items_json
    if not selected:
        frappe.throw(_("No items selected for transfer."))

    mip = frappe.get_doc("Material Issue Plan", mip_name)
    _ensure_mip_editable(mip)
    ctx = get_target_context(mip)
    if not mip.cnc_warehouse:
        frappe.throw(_("No CNC Warehouse set on this Material Issue Plan."))

    pending_by_key = {
        (p["item_code"], p.get("batch_no") or ""): p for p in get_mip_cnc_pending_items(mip_name)
    }
    problems, se_items = [], []
    for item in selected:
        key = (item["item_code"], item.get("batch_no") or "")
        qty = flt(item.get("qty"))
        row = pending_by_key.get(key)
        if qty <= 0:
            problems.append(_("{0} ({1}): qty must be greater than zero.").format(key[0], key[1] or "-"))
            continue
        if not row:
            problems.append(_("{0} ({1}): nothing is waiting at CNC for this item/batch.").format(key[0], key[1] or "-"))
            continue
        if qty > flt(row["qty"]) + 0.001:
            problems.append(_("{0} ({1}): {2} selected but only {3} is still at CNC.").format(
                key[0], key[1] or "-", qty, flt(row["qty"], 3)))
            continue
        se_items.append({
            "item_code": row["item_code"],
            "batch_no": row["batch_no"],
            "use_serial_batch_fields": 1,
            "qty": flt(qty, 3),
            "uom": row["uom"],
            "s_warehouse": mip.cnc_warehouse,
            "t_warehouse": ctx.primary_warehouse,
            "custom_sec_qty": flt(item.get("custom_sec_qty") or row["custom_sec_qty"], 3),
            "custom_sec_uom": row["custom_sec_uom"],
            "custom_length": row["custom_length"],
            "custom_width": row["custom_width"],
            "custom_thickness": row["custom_thickness"],
            "custom_unit_weight": row["custom_unit_weight"],
            "custom_parent_item_group": row["custom_parent_item_group"],
            "custom_drawing": row["drawing"],
            "custom_duno_mark_no": row["duno_mark_no"],
            "custom_customer_drawing_number": row["customer_drawing_number"],
            "custom_sales_order": row["sales_order"],
        })

    if problems:
        frappe.throw(
            _("Cannot forward from CNC — nothing has been transferred:<br><br><ul>{0}</ul>").format(
                "".join("<li>%s</li>" % p for p in problems)),
            title=_("Cannot Transfer"),
        )

    se = frappe.get_doc(_tag_stock_entry({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Transfer",
        "company": ctx.company,
        "items": se_items,
    }, mip_name, ctx))
    frappe.db.commit()
    se.insert(ignore_permissions=True)
    return se.name


def _cnc_sent_and_forwarded(mip_name, cnc_warehouse, primary_warehouse):
    """(rows submitted INTO the CNC warehouse, qty already forwarded OUT of it)."""
    sent_rows = frappe.db.sql(
        """
        SELECT sed.item_code, sed.batch_no,
               SUM(sed.qty) AS qty,
               MAX(sed.uom) AS uom,
               MAX(sed.custom_sec_qty) AS custom_sec_qty,
               MAX(sed.custom_sec_uom) AS custom_sec_uom,
               MAX(sed.custom_length) AS custom_length,
               MAX(sed.custom_width) AS custom_width,
               MAX(sed.custom_thickness) AS custom_thickness,
               MAX(sed.custom_unit_weight) AS custom_unit_weight,
               MAX(sed.custom_parent_item_group) AS custom_parent_item_group,
               MAX(sed.custom_drawing) AS custom_drawing,
               MAX(sed.custom_duno_mark_no) AS custom_duno_mark_no,
               MAX(sed.custom_customer_drawing_number) AS custom_customer_drawing_number,
               MAX(sed.custom_sales_order) AS custom_sales_order
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.custom_mip_ref = %s
          AND se.stock_entry_type = 'Material Transfer'
          AND se.docstatus = 1
          AND sed.t_warehouse = %s
        GROUP BY sed.item_code, sed.batch_no
        HAVING SUM(sed.qty) > 0
        """,
        (mip_name, cnc_warehouse),
        as_dict=True,
    )

    fwd_rows = frappe.db.sql(
        """
        SELECT sed.item_code, sed.batch_no, SUM(sed.qty) AS qty
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.custom_mip_ref = %s
          AND se.stock_entry_type = 'Material Transfer'
          AND se.docstatus = 1
          AND sed.s_warehouse = %s
          AND sed.t_warehouse = %s
        GROUP BY sed.item_code, sed.batch_no
        """,
        (mip_name, cnc_warehouse, primary_warehouse),
        as_dict=True,
    )
    already = {(r.item_code, r.batch_no or ""): flt(r.qty) for r in fwd_rows}
    return sent_rows, already


@frappe.whitelist()
def create_mip_cnc_forward_entry(mip_name):
    """Forward EVERYTHING still sitting at CNC on to the supplier/WIP warehouse.
    create_mip_cnc_partial_forward covers releasing it in stages instead.

    WARNING (Phase 1 H-07 / Report 3 Finding H-07): same manual mid-request
    frappe.db.commit() pattern as create_mip_transfer_entry above -- do NOT
    add a write above that commit() call without re-reading its warning there
    first.
    """
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    _ensure_mip_editable(mip)
    ctx = get_target_context(mip)
    cnc_warehouse = mip.cnc_warehouse
    if not cnc_warehouse:
        frappe.throw(_("No CNC Warehouse set on this Material Issue Plan."))

    sent_rows, already = _cnc_sent_and_forwarded(mip_name, cnc_warehouse, ctx.primary_warehouse)
    if not sent_rows:
        frappe.throw(_("No CNC materials found. Ensure the CNC stock entry has been submitted."))

    se_items = []
    for r in sent_rows:
        key = (r.item_code, r.batch_no or "")
        net_qty = flt(r.qty, 3) - already.get(key, 0)
        if net_qty <= 0:
            continue
        se_items.append({
            "item_code": r.item_code,
            "batch_no": r.batch_no,
            "use_serial_batch_fields": 1,
            "qty": flt(net_qty, 3),
            "uom": r.uom or frappe.db.get_value("Item", r.item_code, "stock_uom") or "Kg",
            "s_warehouse": cnc_warehouse,
            "t_warehouse": ctx.primary_warehouse,
            "custom_sec_qty": flt(r.custom_sec_qty, 3),
            "custom_sec_uom": r.custom_sec_uom or "",
            "custom_length": flt(r.custom_length, 3),
            "custom_width": flt(r.custom_width, 3),
            "custom_thickness": flt(r.custom_thickness, 3),
            "custom_unit_weight": flt(r.custom_unit_weight, 4),
            "custom_parent_item_group": r.custom_parent_item_group or "",
            "custom_drawing": r.custom_drawing or "",
            "custom_duno_mark_no": r.custom_duno_mark_no or "",
            "custom_customer_drawing_number": r.custom_customer_drawing_number or "",
            "custom_sales_order": r.custom_sales_order or "",
        })

    if not se_items:
        frappe.throw(_("All CNC materials have already been transferred onward."))

    se = frappe.get_doc(_tag_stock_entry({
        "doctype": "Stock Entry",
        "stock_entry_type": "Material Transfer",
        "company": ctx.company,
        "items": se_items,
    }, mip_name, ctx))
    frappe.db.commit()
    se.insert(ignore_permissions=True)
    return se.name


def _override_changes_dimensions(excess_row, override, group):
    """True when a Return Excess Entry dialog override would actually move an excess
    row's numbers. A return reason is not a dimension, so adding one to a claimed row
    stays allowed -- only the measurements are frozen by a claim."""
    fields = ("length", "width", "sec_qty") if group in _DIMENSION_DRIVEN_GROUPS else ("qty",)
    return any(
        override.get(f) not in (None, "") and flt(override.get(f), 3) != flt(excess_row.get(f), 3)
        for f in fields
    )


@frappe.whitelist()
def create_mip_excess_return_entry(mip_name, rows_json=None):
    """Receive unconsumed/off-cut material back into stock as fresh Material
    Receipt stock (new batches, new dimensions) from mip.excess_return_items.

    `rows_json` (client change request Phase 5.6): an optional JSON list of
    {"name": <excess_return_items row name>, "return_reason": <text>, plus
    either "length"/"width"/"sec_qty" (Structurals/Plates rows) or "qty"
    (every other item group, e.g. Nuts and Bolts) } -- lets the "Return
    Excess Entry" dialog let the user edit the planned Qty and record why,
    right before this actually creates the Stock Entry, without re-opening
    the form first.

    Structurals/Plates rows take dimension overrides (Length/Width/Sec Qty),
    NOT a direct Qty override, and Qty is recomputed here via the same shared
    utils.dimension_formula.calculate_qty used everywhere else in this app --
    Stock Entry's own validate_stock_entry hook unconditionally recalculates
    Qty from custom_length/custom_sec_qty/custom_unit_weight for these two
    groups on Material Receipt entries, so a directly-set Qty override would
    otherwise be silently discarded the moment the Stock Entry is inserted.

    A Return Reason is mandatory for every row being processed -- either
    supplied fresh here or already saved on the row from a previous edit --
    so a direct/scripted call with no rows_json still enforces it against
    whatever the row itself already carries.

    WARNING (Phase 1 H-07 / Report 3 Finding H-07): same manual mid-request
    frappe.db.commit() pattern as create_mip_transfer_entry above -- do NOT
    add a write above that commit() call without re-reading its warning there
    first. (The mip.excess_return_items flag updates and mip.save() further
    down in this function run AFTER the commit, which is fine -- the warning
    is specifically about writes introduced ABOVE the commit() line.)
    """
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    _ensure_mip_editable(mip)
    if not mip.excess_return_warehouse:
        frappe.throw(_("Please set the Finished Goods Warehouse on this Material Issue Plan first."))

    overrides = {o.get("name"): o for o in _json.loads(rows_json)} if rows_json else {}

    se_items = []
    new_row_names = []
    for r in (mip.excess_return_items or []):
        if r.get("stock_entry_created"):
            continue
        # "Billed to Consume" used to sit here: a row marked never-coming-back was
        # skipped, left at the supplier, and swept up by the job's final Stock
        # Entry. It is gone. Material that does not come back is now Process Loss --
        # declared deliberately, with a reason, and issued out of the supplier
        # warehouse by its own entry rather than absorbed silently into finished
        # goods.
        #
        # A claimed row is deliberately NOT skipped: bringing the off-cut back is
        # exactly how a virtual claim stops being a paper promise. The batch this
        # creates is attached to the claiming Material Mapping row automatically on
        # submit (materialize_virtual_excess_claim), so it never lands in the free
        # pool where another job could take it. Dimension overrides on such a row
        # are refused below -- what returns must be what was claimed.

        override = overrides.get(r.name)
        if override:
            group = r.parent_item_group
            if r.get("mapped_material_planning") and _override_changes_dimensions(r, override, group):
                # Caught here rather than by the same guard on mip.save() below,
                # because that save runs AFTER the Stock Entry is inserted -- by
                # then a refused edit would already have left a stray draft behind.
                _throw_claimed_excess_locked(r)
            if group in _DIMENSION_DRIVEN_GROUPS and not r.get("enter_weight_instead_of_pieces"):
                if override.get("length") not in (None, ""):
                    r.length = flt(override.get("length"), 3)
                if override.get("width") not in (None, ""):
                    r.width = flt(override.get("width"), 3)
                if override.get("sec_qty") not in (None, ""):
                    r.sec_qty = flt(override.get("sec_qty"), 3)
                calc_qty = calculate_qty(group, r.length, r.width, r.thickness, r.unit_weight, r.sec_qty)
                if calc_qty is not None:
                    r.qty = flt(calc_qty, 3)
            elif override.get("qty") not in (None, ""):
                r.qty = flt(override.get("qty"), 3)
            if (override.get("return_reason") or "").strip():
                r.return_reason = override.get("return_reason").strip()

        # "Enter Weight, Not Pieces": the weight is what somebody typed, so the piece
        # count is derived from it rather than the other way round. It matters that
        # this happens BEFORE the Stock Entry is built: for Structurals and Plates the
        # entry recomputes its own qty from Length x Sec Nos, so a row whose Sec Nos
        # did not agree with its weight would quietly ship a different amount than the
        # one on screen. Left fractional on purpose -- 18 Kg of a 4.906 Kg piece is
        # 3.669 of one, and rounding up would claim a piece that is not coming back.
        if r.get("enter_weight_instead_of_pieces") and (r.parent_item_group or "") in _DIMENSION_DRIVEN_GROUPS:
            per_piece = calculate_qty(r.parent_item_group, r.length, r.width, r.thickness, r.unit_weight, 1)
            if per_piece:
                r.sec_qty = flt(flt(r.qty) / flt(per_piece), 3)

        qty = flt(r.qty, 3)
        if not r.item_code or qty <= 0:
            continue
        if not (r.return_reason or "").strip():
            frappe.throw(_("Row {0} ({1}): a Return Reason is required before creating the return entry.")
                         .format(r.idx, r.item_code))

        new_row_names.append(r.name)
        se_items.append({
            "item_code": r.item_code,
            "qty": qty,
            "uom": r.get("uom") or frappe.db.get_value("Item", r.item_code, "stock_uom") or "Kg",
            "t_warehouse": mip.excess_return_warehouse,
            "custom_parent_item_group": r.get("parent_item_group") or "",
            "custom_unit_weight": flt(r.get("unit_weight"), 4),
            "custom_sec_qty": flt(r.get("sec_qty"), 3),
            "custom_sec_uom": r.get("sec_uom") or "",
            "custom_length": flt(r.get("length"), 3),
            "custom_width": flt(r.get("width"), 3),
            "custom_thickness": flt(r.get("thickness"), 3),
            # Same-named custom field on Batch -- ERPNext copies matching custom
            # fields from a Stock Entry item onto the batch it auto-creates, so
            # this reaches the Batch record itself, letting Excess Material
            # Mapping trace a reservation back to the row it came from.
            "custom_source_mip_excess_row": r.name,
        })

    if not se_items:
        frappe.throw(_("No new off-cut items to process. All rows already have a Stock Entry created, "
                       "or no rows with Weight (Kg) > 0 exist."))

    # A Repack, not a Material Receipt.
    #
    # This used to receive the off-cut as brand-new stock with no source at all, so
    # the same steel was created in stores while every kilo of it was still standing
    # at the supplier -- and the final Stock Entry then consumed it. The material was
    # counted twice, and the job was charged for material it never used.
    #
    # A Repack does both halves in one document: out rows empty what this job has at
    # the supplier, an in row receives the off-cut at its measured size as a NEW
    # batch. In and out are not required to match, which is exactly right here --
    # the difference is the cut, and what it leaves behind is process loss, declared
    # separately with a reason.
    #
    # Tagged with custom_sco_ref as well as custom_mip_ref: the consumption netting
    # (_get_supplier_wh_consumption_items) matches on the SCO, so without it a return
    # was invisible to the very query whose docstring says a return "correctly
    # reduces what is left to consume".
    # A plan with no supplier warehouse never sent material anywhere this app can
    # follow -- excess claimed straight off another plan's table, for instance, which
    # never involves a supplier at all. There is nothing to take the off-cut OUT of,
    # so it is received as it always was. The double-count this Repack exists to stop
    # cannot arise there either: the final Stock Entry consumes from the supplier
    # warehouse, and there isn't one.
    supplier_tracked = bool(mip.supplier_warehouse and mip.subcontracting_order)

    out_rows, shortfalls = (
        _excess_return_source_rows(mip, se_items) if supplier_tracked else ([], [])
    )
    if shortfalls:
        frappe.throw(
            _("There is not enough of this material left at {0} to return:<br><br>{1}<br><br>"
              "It has already been consumed by the final Stock Entry, or returned before. "
              "Reduce the return quantity, or write the difference off as Process Loss.")
            .format(mip.supplier_warehouse or _("the supplier"), "<br>".join(shortfalls)),
            title=_("Not Enough Left to Return"),
        )

    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Repack" if out_rows else "Material Receipt",
        "company": mip.company,
        "custom_mip_ref": mip_name,
        "custom_sco_ref": mip.subcontracting_order or None,
        "items": out_rows + se_items,
    })
    frappe.db.commit()
    se.insert(ignore_permissions=True)

    # The excess row itself is the record of what came back, dimensions and all.
    # This used to copy those dimensions onto the raw-material row as well, because
    # that row carried its own editable Excess Length/Width/Sec Qty and a recompute
    # on every save that would otherwise have overwritten them. Both are gone: the
    # Excess Material Items table is the one place an off-cut is described.
    for r in mip.excess_return_items:
        if r.name in new_row_names:
            r.stock_entry_created = 1

    mip.save(ignore_permissions=True)

    return se.name
