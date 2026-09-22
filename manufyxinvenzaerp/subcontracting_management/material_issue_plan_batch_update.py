"""Reassign the batch behind a whole Consolidate Items line.

The Raw Materials grid already has an Update Batch dialog, and it works one Material
Planning child row at a time. A Consolidate Items line cannot: it is a *merge* of N
raw-material rows, which point at N child rows across possibly several Material
Planning documents. Reassigning one line means reassigning all of them.

What makes that tractable is Reserve Without Dimensions. A row in that mode reserves
exactly its required Kg and expresses the piece count as a fraction, so per-row
dimension matching disappears and only one number has to reconcile: total Kg. A line
needing 1,000 Kg across 50 rows can move to a new batch whatever mixture of
dimension-mapped and dimensionless rows it started as.

It expands a line to its members, prices the target batches, previews what a
reassignment would do, and applies it. Behaviour, decisions and the verified examples
are in manufyxinvenzaerp_features.md, section 20.

It lives beside material_issue_plan_transfer.py rather than inside
material_issue_plan.py for the same reason that module does: it is a large MIP action
with its own vocabulary, and material_planning.py is already past 4,900 lines.

Two things to know before changing anything here.

**A consolidate row has no back-link.** It carries no material_planning, source_table
or source_row -- it is regenerated wholesale on every save. Members are therefore
*re-derived* from mip.raw_materials by the same grouping key the sync uses, never read
from client input. That is what makes a re-run after a partial failure safe: rows that
already moved have a different key and are simply no longer members.

**The Kg a member will consume is not the Kg it consumes today.** After a dimensionless
reassign a Material Mapping row reserves its *requirement* (`reqd_kg`), which is what
_apply_rwd_fractional_nos writes into batch_calc_qty on save. Its current `qty` is the
batch-derived weight and can be larger or smaller. Sizing the fill off `qty` would
quietly plan for the wrong tonnage -- see _member_target_kg.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import flt

from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    _apply_batch_to_arm_row,
    _apply_batch_to_mapping_row,
    _batch_change_remarks,
    _calc_batch_qty,
    _calc_kg_per_nos,
    _get_batch_dims,
    _get_batch_inspection_block_reason,
    _get_batch_reserved_by_others,
    _get_batch_total_stock,
    _mark_excess_item_mapped,
    _resync_excess_item_mapping,
    _require_write,
    get_batch_item,
    reserve_batches,
    reserve_exact_match_batches,
    unreserve_batches,
    unreserve_exact_match_batches,
)
from manufyxinvenzaerp.utils.decision_log import log_decision

# The child tables store three decimals, so anything finer is noise. Matches the
# tolerance _validate_batch_calc_qty works to.
EPS = 0.001

MATERIAL_MAPPING = "Material Planning Material Mapping"
AVAILABLE_RAW_MATERIAL = "Material Planning Available Raw Material"
UNAVAILABLE_ITEM = "Material Planning Unavailable Item"

# Reserve Without Dimensions only applies where a piece has a computable weight.
# _apply_rwd_fractional_nos guards on exactly this set.
RWD_GROUPS = ("Structurals", "Plates")


# ─────────────────────────────────────────────────────────────────────────────
# Grouping — the single definition of what a consolidate line is
# ─────────────────────────────────────────────────────────────────────────────

def consolidate_group_key(row):
    """The (item, batch, CNC leg) tuple that defines one Consolidate Items line.

    Deliberately works on BOTH a raw-material row and a consolidate row, so the
    sync and the expansion below can never drift apart. A raw-material row carries
    `planned_item` (the batch's own item, which differs from the requirement's on an
    alternate-item row); a consolidate row has already resolved that, and `.get()`
    returns None there, so the fallback does the right thing for both.

    `batch_no` is normalised to "" rather than left None. _sync_consolidate_items
    skips batch-less rows outright so the two agree today, but a key that can hold
    None is a key that sorts and compares inconsistently the first time something
    stops skipping them.
    """
    return (
        row.get("planned_item") or row.get("item_code"),
        row.get("batch_no") or "",
        1 if row.get("cnc_process") else 0,
    )


def expand_consolidate_row(mip, consolidate_row_name):
    """Expand one Consolidate Items line back to the raw-material rows it merges.

    Returns `(key, members)`. Members are in `mip.raw_materials` order, which is
    deterministic: for each Material Planning in sorted name order, all Material
    Mapping rows in idx order, then all Available Raw Material rows, then Unavailable
    (see refresh_mip_raw_materials). That order is what the preview table shows and
    what the fill consumes, so the user can predict the split by reading top to bottom.
    """
    target = None
    for row in (mip.consolidate_items or []):
        if row.name == consolidate_row_name:
            target = row
            break
    if not target:
        frappe.throw(
            _("Consolidate row {0} no longer exists on {1}. Reload the plan and try again.")
            .format(consolidate_row_name, mip.name)
        )

    key = consolidate_group_key(target)

    # The row number in the PLANNING document, looked up once per table rather than
    # per member. The dialog shows the Material Issue Plan's own idx beside the plan's
    # name, which reads as the plan's row and is not: MIP-2026-00060's rows 1, 7 and 11
    # are MP-2026-00260's rows 16, 22 and 26. Both numbers are shown now so the user can
    # check the reassignment against the plan itself.
    wanted = {}
    for row in (mip.raw_materials or []):
        if row.batch_no and row.source_table and row.source_row:
            wanted.setdefault(row.source_table, set()).add(row.source_row)
    mp_idx_by_row = {}
    for child_dt, names in wanted.items():
        for r in frappe.get_all(child_dt, filters={"name": ["in", list(names)]},
                                fields=["name", "idx"]):
            mp_idx_by_row[r.name] = r.idx

    members = []
    for row in (mip.raw_materials or []):
        if not row.batch_no:
            continue
        if consolidate_group_key(row) != key:
            continue
        members.append(frappe._dict({
            "idx": row.idx,
            "raw_material_row": row.name,
            "material_planning": row.material_planning,
            "source_table": row.source_table,
            "source_row": row.source_row,
            "item_code": row.item_code,
            "planned_item": row.planned_item,
            "batch_no": row.batch_no,
            "qty": flt(row.qty, 3),
            "reqd_kg": flt(row.reqd_kg, 3),
            "sec_qty": flt(row.sec_qty, 3),
            "transferred_qty": flt(row.transferred_qty, 3),
            "is_reserved": 1 if row.is_reserved else 0,
            "parent_item_group": row.parent_item_group or "",
            "unit_weight": flt(row.unit_weight),
            "mp_idx": mp_idx_by_row.get(row.source_row),
            "duno_mark_no": row.duno_mark_no or "",
            "customer_drawing_number": row.customer_drawing_number or "",
            "sales_order": row.sales_order or "",
            "cut_sheet_ref": row.get("cut_sheet_ref") or "",
            "target_kg": _member_target_kg(row),
        }))

    return key, members


def _member_target_kg(row):
    """How much of the NEW batch this member will consume once reassigned.

    Not the same as what it consumes now, and the two tables differ:

    - **Material Mapping** reserves its *requirement* under RWD --
      _apply_rwd_fractional_nos sets `batch_calc_qty = row.qty`, and the MIP row's
      `reqd_kg` is a copy of exactly that field. The MIP row's own `qty` is the
      batch-derived weight, which is what the OLD batch happened to give.
    - **Available Raw Material** has no such indirection: reserve_exact_match_batches
      reserves `required_qty` verbatim with no dimension arithmetic, and the MIP row's
      `qty` is a copy of that. Its `reqd_kg` is `overall_required_qty`, the whole
      requirement -- which is wrong to use here, because one requirement can be split
      across several exact-match rows and summing it would double-count.
    """
    if row.source_table == AVAILABLE_RAW_MATERIAL:
        return flt(row.qty, 3)
    return flt(row.reqd_kg, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Target batches — what one candidate batch can actually supply
# ─────────────────────────────────────────────────────────────────────────────

def _batch_free_kg(batch_no, warehouse):
    """Free Kg of a batch in a warehouse, counting EVERY plan's reservations.

    Deliberately not get_batch_stock_summary: that helper takes an `exclude_mp` and
    drops all of that plan's reservations from the total, which is right when you are
    asking "how much more can THIS plan take". Here the question spans several plans
    at once, so excluding any of them overstates what is free. Passing "" as the
    exclusion makes `parent != ''` match every row, which is the whole point.
    """
    total = flt(_get_batch_total_stock(batch_no, warehouse))
    reserved = flt(_get_batch_reserved_by_others(batch_no, "", None))
    return flt(total - reserved, 3)


@frappe.whitelist()
def get_batch_capacity(batch_no, warehouse, pieces=0):
    """Price one candidate batch for the dialog. Read-only.

    Weight and free stock are returned SEPARATELY and both are shown, because they
    answer different questions: weight is how much the user says they are taking
    from this batch, free stock is how much of it is actually in the warehouse and
    unclaimed. A weight above free stock is a piece count nobody can honour, and it
    has to read as a warning rather than be silently clamped.

    Always priced at the batch's OWN recorded size. The dialog used to let the user
    type a Length and Width here, but nothing typed was ever saved or transferred --
    each row keeps the batch's real dimensions, and those are what reach the Stock
    Entry -- so a typed cut size planned against one size and shipped another. Only
    the piece count is taken from the user now (client decision, Sep 2026).
    """
    item_code = get_batch_item(batch_no) if batch_no else None
    if not item_code:
        return {"ok": False, "error": _("Batch {0} not found.").format(batch_no)}

    item = frappe.db.get_value(
        "Item", item_code, ["custom_parent_item_group", "custom_unit_weight"], as_dict=True
    ) or {}
    group = item.get("custom_parent_item_group") or ""
    unit_weight = flt(item.get("custom_unit_weight"))

    length, width, thickness = (flt(v) for v in _get_batch_dims(batch_no))
    b_length, b_width, b_thickness = length, width, thickness
    pieces = flt(pieces)

    kg_per_piece = flt(_calc_kg_per_nos(group, length, width, thickness, unit_weight), 3)
    capacity_kg = flt(_calc_batch_qty(group, length, width, thickness, pieces, unit_weight), 3)
    free_kg = _batch_free_kg(batch_no, warehouse) if warehouse else 0.0

    return {
        "ok": True,
        "batch_no": batch_no,
        "item_code": item_code,
        "parent_item_group": group,
        "unit_weight": unit_weight,
        "batch_length": flt(b_length),
        "batch_width": flt(b_width),
        "batch_thickness": flt(b_thickness),
        "length": length,
        "width": width,
        "thickness": thickness,
        "pieces": pieces,
        "kg_per_piece": kg_per_piece,
        "capacity_kg": capacity_kg,
        "free_kg": free_kg,
        # min() of the two, because you can neither cut more than you declared nor
        # take more than is there.
        "effective_capacity_kg": flt(min(capacity_kg, free_kg), 3) if capacity_kg else free_kg,
        "inspection_block": _get_batch_inspection_block_reason(batch_no) or "",
        "rwd_applies": group in RWD_GROUPS,
    }


# ─────────────────────────────────────────────────────────────────────────────
# The fill — which member lands on which batch
# ─────────────────────────────────────────────────────────────────────────────

def plan_fill(members, targets):
    """Assign members to target batches, first-fit in table order, never splitting a row.

    A single row cannot be split across two batches -- one row holds one batch link --
    so a member that does not fit the current target moves wholly to the next one and
    whatever was left on the previous target is stranded.

    Once the cursor passes a target it never returns. That is the only variant an
    operator can predict by reading the table top to bottom, which is what the
    consolidate view is for. Best-fit or back-filling would pack the batches better and
    produce an assignment nobody can anticipate from the grid.

    Stranded capacity is reported per target rather than hidden, so an oversized row
    early in the list that pushes everything onto batch 2 is visible as the cause.

    `targets` are dicts from get_batch_capacity. Mutates neither argument.
    """
    leftover = [flt(t.get("effective_capacity_kg"), 3) for t in targets]
    # Which member's weight closed each target. Reported because "226 Kg unused and the
    # smallest unplaced row needs 141 Kg" invites the user to raise the count by 141 --
    # and it still would not fit, because the batch closed earlier on a bigger row and
    # the cursor never goes back. Naming the row that closed it is the only way that
    # figure is actionable.
    closed_by = [None] * len(targets)
    assignments, unassigned = [], []

    cursor = 0
    for member in members:
        need = flt(member.target_kg, 3)
        while cursor < len(targets) and need > leftover[cursor] + EPS:
            closed_by[cursor] = need
            cursor += 1
        if cursor >= len(targets):
            unassigned.append(member)
            continue
        leftover[cursor] = flt(leftover[cursor] - need, 3)
        assignments.append(frappe._dict({
            "member": member,
            "target_index": cursor,
            "batch_no": targets[cursor].get("batch_no"),
        }))

    assigned_kg = [0.0] * len(targets)
    assigned_rows = [0] * len(targets)
    for a in assignments:
        assigned_kg[a.target_index] = flt(assigned_kg[a.target_index] + a.member.target_kg, 3)
        assigned_rows[a.target_index] += 1

    return frappe._dict({
        "assignments": assignments,
        "unassigned": unassigned,
        "leftover_kg": leftover,
        "closed_by_kg": closed_by,
        "assigned_kg": assigned_kg,
        "assigned_rows": assigned_rows,
        "shortfall_kg": flt(sum(flt(m.target_kg) for m in unassigned), 3),
    })


# ─────────────────────────────────────────────────────────────────────────────
# What to write onto each member's row
# ─────────────────────────────────────────────────────────────────────────────

def plan_member_writes(fill, targets):
    """Decide, per member, the waiver flag and Sec Nos the reassign will write.

    This is the single most dangerous decision in the whole feature, and the
    reason it lives in its own function is that getting it wrong fails SILENTLY.

    _apply_batch_to_mapping_row, handed `reserve_without_dimensions = 0` and no
    Sec Nos, leaves the row's EXISTING batch_sec_qty in place and recomputes
    batch_calc_qty from it against the NEW batch's dimensions. Nothing throws.
    The row simply comes to hold a weight that is the old batch's piece count
    priced at the new batch's size -- a number that means nothing, and which then
    flows into the reservation, the Stock Entry and the excess figures.

    So the rule is asserted here rather than trusted to the dialog:

    - **Structurals and Plates** -- waiver ON, Sec Nos left for the server.
      _apply_rwd_fractional_nos derives it on save, fractional by design, from the
      weight the row actually reserves. A dialog that forgot to tick the box cannot
      produce the silent case above, because this function never emits it.
    - **Nuts and Bolts** -- waiver OFF, because a bolt's weight is exact and a
      fractional bolt is meaningless. But Sec Nos must then be computed HERE and
      sent explicitly, for exactly the reason above. A count that does not come out
      whole is surfaced as a warning, not silently rounded: rounding it changes the
      line's total weight.

    Returns (writes, blockers, warnings).
    """
    writes, blockers, warnings = [], [], []
    fractional_bolts = []

    for assignment in fill.assignments:
        member = assignment.member
        target = targets[assignment.target_index]
        # The batch's own item group decides, not the requirement's: it is the
        # batch that is being cut into pieces.
        group = target.get("parent_item_group") or member.parent_item_group or ""

        if group in RWD_GROUPS:
            writes.append(frappe._dict({
                "member": member,
                "target_index": assignment.target_index,
                "batch_no": target["batch_no"],
                "batch_item": target.get("item_code"),
                "reserve_without_dimensions": 1,
                "sec_qty": None,
            }))
            continue

        unit_weight = flt(target.get("unit_weight"))
        if not unit_weight:
            blockers.append(
                _("Batch {0} is {1}, whose Sec Nos must be counted rather than derived, "
                  "but its item has no Unit Weight set. Set it on the Item first.")
                .format(target["batch_no"], group or _("an unsupported item group"))
            )
            continue

        pieces = flt(flt(member.target_kg) / unit_weight, 3)
        if abs(pieces - round(pieces)) > EPS:
            fractional_bolts.append((member, pieces))
        writes.append(frappe._dict({
            "member": member,
            "target_index": assignment.target_index,
            "batch_no": target["batch_no"],
            "batch_item": target.get("item_code"),
            "reserve_without_dimensions": 0,
            "sec_qty": pieces,
        }))

    if fractional_bolts:
        warnings.append(
            _("{0} row(s) work out to a fractional piece count (e.g. {1} on row {2}). "
              "The weight is kept exactly as planned rather than rounded, so the piece "
              "count carries the fraction.")
            .format(len(fractional_bolts),
                    flt(fractional_bolts[0][1], 3),
                    fractional_bolts[0][0].idx)
        )

    return writes, blockers, warnings


# ─────────────────────────────────────────────────────────────────────────────
# Preview — every refusal happens here, before anything is written
# ─────────────────────────────────────────────────────────────────────────────

def _plan_hash(mip_name, key, members, targets):
    """Fingerprint of everything the plan was computed against.

    The apply path re-runs the preview and compares this. If stock moved, a row was
    transferred, or someone else reassigned a member between preview and confirm, the
    fingerprint changes and the stale plan is refused rather than applied to a world
    that no longer matches it.
    """
    payload = json.dumps({
        "mip": mip_name,
        "key": list(key),
        "members": sorted(
            [m.source_table, m.source_row, m.batch_no, m.target_kg, m.transferred_qty]
            for m in members
        ),
        "targets": [[t.get("batch_no"), t.get("effective_capacity_kg")] for t in targets],
    }, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _member_flags(members):
    """Per-member flags that live on the Material Planning child row, not the MIP copy.

    `is_virtual_excess` is not copied onto the MIP raw-material row at all, and
    `cut_sheet_ref` is copied but can go stale. Both decide whether a member may be
    touched, so both are read from the source of truth. One query per table.
    """
    flags = {}
    by_table = {}
    for m in members:
        by_table.setdefault(m.source_table, []).append(m.source_row)

    for table, names in by_table.items():
        if table == UNAVAILABLE_ITEM:
            continue
        fields = ["name", "cut_sheet_ref", "is_reserved", "reserved_qty"]
        if table == MATERIAL_MAPPING:
            fields.append("is_virtual_excess")
        for r in frappe.get_all(table, filters={"name": ["in", names]}, fields=fields):
            flags[(table, r.name)] = frappe._dict({
                "cut_sheet_ref": r.get("cut_sheet_ref") or "",
                "is_virtual_excess": 1 if r.get("is_virtual_excess") else 0,
                "is_reserved": 1 if r.get("is_reserved") else 0,
                "reserved_qty": flt(r.get("reserved_qty"), 3),
            })
    return flags


def _build_plan(mip_name, consolidate_row_name, targets_json=None):
    """Work out the whole reassignment from live state: members, targets, fill,
    per-row writes, and every reason it would be refused.

    Mutates nothing. Both the preview and the apply path go through here, and that
    is the point -- the apply path must not be able to act on a plan computed even
    slightly differently from the one the user was shown. It returns the client
    payload under `response` and the objects the apply path needs alongside it.

    This is also where the operation is ALLOWED to fail. Once applying starts, the
    internal commits in the reserve/unreserve helpers mean a failure half way
    through leaves one plan already changed, so every condition that can be
    established up front is established here.
    """
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    key, members = expand_consolidate_row(mip, consolidate_row_name)

    blockers, warnings = [], []

    # Refused before anything is priced: once a transfer or any other stock action exists
    # on the plan, no line on it may change batch. Enforced here so the apply path, which
    # goes through this same builder, can never get past it.
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        _mip_batch_change_blocked_message,
    )
    stock_block = _mip_batch_change_blocked_message(mip)
    if stock_block:
        return frappe._dict({
            "response": {"ok": False, "blockers": [stock_block], "warnings": [],
                         "members": [], "material_plannings": [], "targets": [],
                         "stock_actions_block": True},
            "mip": mip, "key": key, "members": [], "warehouse": "",
            "mp_names": [], "targets": [], "fill": None, "writes": [],
        })

    if not members:
        blockers.append(_("This line no longer has any raw-material rows behind it. "
                          "Refresh Raw Materials and try again."))
        return frappe._dict({
            "response": {"ok": False, "blockers": blockers, "warnings": warnings,
                         "members": [], "material_plannings": [], "targets": []},
            "mip": mip, "key": key, "members": [], "warehouse": "",
            "mp_names": [], "targets": [], "fill": None, "writes": [],
        })

    # 0.2 — a transferred line is refused whole. Reassigning only the untransferred
    # remainder would split the line in two on the next rebuild, which is exactly the
    # confusion this feature exists to remove.
    moved = [m for m in members if m.transferred_qty > EPS]
    if moved:
        blockers.append(
            _("{0} of {1} rows on this line have already been transferred ({2} Kg). "
              "A line cannot be reassigned once any of it has shipped.")
            .format(len(moved), len(members), flt(sum(m.transferred_qty for m in moved), 3))
        )

    # 0.3 — rows whose unreserve has side effects on ANOTHER document. unreserve_batches
    # blanks a virtual-excess or cut-sheet row and hands its pieces back to the Cut Sheet
    # or the SCO Excess Material Item it claimed them from. A re-run cannot undo that, so
    # these are refused rather than risked.
    flags = _member_flags(members)
    claimed = [m for m in members if flags.get((m.source_table, m.source_row), {}).get("is_virtual_excess")]
    on_sheet = [m for m in members if flags.get((m.source_table, m.source_row), {}).get("cut_sheet_ref")]
    if claimed:
        blockers.append(
            _("{0} row(s) on this line hold material claimed from another plan's excess. "
              "Unlink the claim on the Material Planning first.").format(len(claimed))
        )
    if on_sheet:
        blockers.append(
            _("{0} row(s) on this line are cutting from a Cut Sheet. "
              "Release the allocation on the Cut Sheet first.").format(len(on_sheet))
        )

    # Only the two batched tables can be reassigned. An Unavailable Item row has no
    # batch to move and no reservation to release, and would otherwise fail deep in
    # the apply loop with "row is no longer in Exact Match" -- a confusing way to be
    # told something that can be said plainly here.
    wrong_table = [m for m in members
                   if m.source_table not in (MATERIAL_MAPPING, AVAILABLE_RAW_MATERIAL)]
    if wrong_table:
        blockers.append(
            _("{0} row(s) on this line are not batched stock and cannot be reassigned.")
            .format(len(wrong_table))
        )
    orphan = [m for m in members if not m.material_planning]
    if orphan:
        blockers.append(
            _("{0} row(s) on this line have lost their link to a Material Planning. "
              "Refresh Raw Materials and try again.").format(len(orphan))
        )

    # 0.4 / 0.5 — every plan must be writable, and they must share one warehouse or the
    # reservation arithmetic below spans incomparable stock.
    mp_names = sorted({m.material_planning for m in members if m.material_planning})
    plans, warehouses = [], set()
    for name in mp_names:
        try:
            mp = frappe.get_doc("Material Planning", name)
            _require_write(mp)
        except frappe.PermissionError:
            blockers.append(_("You do not have permission to change reservations on {0}.").format(name))
            continue
        warehouses.add(mp.for_warehouse or "")
        rows = [m for m in members if m.material_planning == name]
        plans.append({
            "material_planning": name,
            "for_warehouse": mp.for_warehouse or "",
            "rows": len(rows),
            "qty": flt(sum(m.target_kg for m in rows), 3),
        })

    if len(warehouses) > 1:
        blockers.append(
            _("The plans behind this line use different Raw Material Warehouses ({0}). "
              "They cannot be reassigned together.").format(", ".join(sorted(w or "—" for w in warehouses)))
        )
    warehouse = next(iter(warehouses), "") if len(warehouses) == 1 else ""
    if not warehouse:
        blockers.append(_("No Raw Materials Warehouse is set on the linked Material Planning."))

    # 0.11 — the parked transfer draft is keyed on the batch, so changing it discards
    # whatever was typed into the transfer popup and saved without transferring.
    for row in (mip.consolidate_items or []):
        if row.name == consolidate_row_name and row.get("draft_saved_on"):
            warnings.append(
                _("This line has unfinished entries saved from \"Select Materials to Transfer\" "
                  "on {0} (not yet transferred). Changing the batch clears them — you will need "
                  "to re-enter them in the transfer popup.")
                .format(frappe.utils.format_datetime(row.draft_saved_on))
            )

    # ── Targets ──────────────────────────────────────────────────────────────
    targets_in = json.loads(targets_json) if isinstance(targets_json, str) else (targets_json or [])
    targets = []
    for t in targets_in:
        # Batch and piece count only. Any length/width a caller sends is ignored:
        # a batch is always priced at its own size, which is the size it ships at.
        priced = get_batch_capacity(t.get("batch_no"), warehouse, t.get("pieces") or 0)
        if not priced.get("ok"):
            blockers.append(priced.get("error"))
            continue
        targets.append(priced)

        # 0.6 — reassigning to the batch it already has is a no-op that would still
        # unreserve and re-reserve every row.
        if priced["batch_no"] == key[1]:
            blockers.append(
                _("Batch {0} is the one this line already uses.").format(priced["batch_no"])
            )
        # A batch of another item is allowed -- that is the point of the screen. It is
        # not silent, though: the line goes on asking for its own item and the batch
        # records what is really going, so the substitution is stated rather than
        # assumed. Availability is what decides whether it can happen, and that is
        # checked just below.
        if priced["item_code"] != key[0]:
            warnings.append(
                _("Batch {0} holds {1}, not {2}. The requirement stays {2}; {1} is what "
                  "will be sent, and the rows will record it as the planned item.")
                .format(priced["batch_no"], priced["item_code"], key[0])
            )
        # 0.9b — a batch with no free stock does NOT get caught downstream:
        # _validate_batch_calc_qty skips its coverage check entirely when batch_stock is
        # zero, so the save succeeds and the reservation silently comes back as nothing.
        if priced["free_kg"] <= EPS:
            blockers.append(
                _("Batch {0} has no free stock in {1}.").format(priced["batch_no"], warehouse)
            )
        elif priced["capacity_kg"] > priced["free_kg"] + EPS:
            warnings.append(
                _("Batch {0}: {1} Kg was declared but only {2} Kg is free in {3}. "
                  "Only what is free can be used.")
                .format(priced["batch_no"], priced["capacity_kg"], priced["free_kg"], warehouse)
            )
        # 0.10 — an uninspected batch reserves nothing. A warning, not a blocker: the
        # inspection may well complete before the transfer.
        if priced["inspection_block"]:
            warnings.append(
                _("Batch {0}: {1}").format(priced["batch_no"], priced["inspection_block"])
            )

    # 0.9c — rows elsewhere with a target batch ASSIGNED but not reserved. Nothing is
    # held for them, so they do not reduce free stock and do not block -- but moving
    # this line onto the batch can leave them less than they were planned against, and
    # that Material Planning then refuses to save until someone changes them. That is
    # exactly how MP-2026-00015 became unsaveable (14 Sep 2026), so it is said up front.
    member_rows = {(m.source_table, m.source_row) for m in members}
    for priced in targets:
        waiting = _assigned_elsewhere(priced["batch_no"], warehouse, member_rows)
        if not waiting:
            continue
        need = flt(sum(w["qty"] for w in waiting), 3)
        taking = flt(sum(m.target_kg for m in members), 3) if len(targets) == 1 else None
        left = flt(priced["free_kg"] - (taking or 0), 3)
        if taking is not None and left + EPS >= need:
            continue
        rows_html = "".join(
            "<li>{0} — {1} {2}{3}: {4} Kg</li>".format(
                frappe.utils.escape_html(w["material_planning"]), _("row"), w["idx"],
                " (" + _("DUNO") + " " + frappe.utils.escape_html(w["duno"]) + ")" if w["duno"] else "", w["qty"])
            for w in waiting)
        warnings.append(
            _("Batch {0} is also assigned — but not reserved — to other rows needing {1} Kg:")
            .format(priced["batch_no"], need)
            + "<ul style='margin:4px 0 4px 18px'>" + rows_html + "</ul>"
            + (_("After this reassignment only {0} Kg of it is left for them. Their Material Planning "
                 "will refuse to save until those rows are given another batch.").format(max(0.0, left))
               if taking is not None else
               _("This line may take the stock they were planned against. Their Material Planning "
                 "will refuse to save if it does."))
        )

    # 0.7 — a batch already sitting in the OTHER child table of a plan we are about to
    # save makes _validate_no_cross_table_batch_duplicate throw at save time. Catch it
    # here, where nothing has moved yet.
    if mp_names and targets:
        blockers.extend(_cross_table_conflicts(mp_names, [t["batch_no"] for t in targets], members))

    # ── Fill ─────────────────────────────────────────────────────────────────
    total_kg = flt(sum(m.target_kg for m in members), 3)
    fill = plan_fill(members, targets) if targets else None

    if fill and fill.shortfall_kg > EPS:
        placed_kg = flt(total_kg - fill.shortfall_kg, 3)
        stranded_kg = flt(sum(fill.leftover_kg), 3)
        blockers.append(
            _("Only {0} Kg of this line's {1} Kg could be placed — {2} Kg short across "
              "{3} row(s).").format(placed_kg, total_kg, fill.shortfall_kg, len(fill.unassigned))
        )
        # Capacity left over while rows go unplaced is NOT "not enough material" -- it
        # is "no remaining row is small enough to fit what is left". Saying only
        # "N Kg short" there reads as an empty batch and sends the user hunting for
        # stock they already have.
        if stranded_kg > EPS:
            closers = [kg for kg in fill.closed_by_kg if kg]
            detail = (
                _("A batch closes as soon as a row does not fit, and rows are never split "
                  "or reordered — here a row needing {0} Kg closed one.")
                .format(flt(max(closers), 3))
                if closers else
                _("Rows are placed in table order and are never split.")
            )
            blockers.append(
                _("{0} Kg of the capacity entered could not be used. {1} "
                  "Raise that batch's piece count so the row fits, or add another batch.")
                .format(stranded_kg, detail)
            )

    # Decide what each member's row will actually be given. This can refuse too --
    # an item group whose Sec Nos must be counted rather than derived, with no unit
    # weight to count it by -- so it runs before "ok" is settled.
    writes, write_blockers, write_warnings = plan_member_writes(fill, targets) if fill else ([], [], [])
    blockers.extend(write_blockers)
    warnings.extend(write_warnings)

    response = {
        "ok": not blockers and bool(targets),
        "blockers": blockers,
        "warnings": warnings,
        "plan_hash": _plan_hash(mip_name, key, members, targets),
        "group": {
            "item_code": key[0], "batch_no": key[1], "cnc_process": key[2],
            "rows": len(members), "total_kg": total_kg,
            "plans": len(mp_names),
            "parent_item_group": members[0].parent_item_group,
            "rwd_applies": members[0].parent_item_group in RWD_GROUPS,
        },
        "material_plannings": plans,
        "targets": [
            dict(t,
                 assigned_kg=fill.assigned_kg[i] if fill else 0.0,
                 assigned_rows=fill.assigned_rows[i] if fill else 0,
                 leftover_kg=fill.leftover_kg[i] if fill else flt(t["effective_capacity_kg"], 3))
            for i, t in enumerate(targets)
        ],
        # is_reserved / reserved_qty come from the Material Planning row, not the
        # Issue Plan's copy -- the confirmation shows what is about to be released,
        # so it must be the reservation as it stands, not a snapshot of it.
        "members": [
            dict(m,
                 target_index=_target_index_of(fill, m),
                 is_reserved=flags.get((m.source_table, m.source_row), {}).get("is_reserved", m.is_reserved),
                 reserved_qty=flags.get((m.source_table, m.source_row), {}).get("reserved_qty", 0.0))
            for m in members
        ],
        "shortfall_kg": fill.shortfall_kg if fill else total_kg,
    }

    return frappe._dict({
        "response": response,
        "mip": mip, "key": key, "members": members, "warehouse": warehouse,
        "mp_names": mp_names, "targets": targets, "fill": fill, "writes": writes,
    })


@frappe.whitelist()
def preview_consolidate_batch_update(mip_name, consolidate_row_name, targets_json=None):
    """What a reassignment would do, and every reason it would be refused. Read-only."""
    return _build_plan(mip_name, consolidate_row_name, targets_json).response


def _assigned_elsewhere(batch_no, warehouse, exclude_rows):
    """Rows on other plans with this batch assigned but not reserved, still needing it.

    A row released by its own transfer looks exactly like one never reserved, so rows
    on plans that have already issued this batch are left out -- the same rule the
    transfer popup uses (_mps_that_moved_batch). When that cannot be told apart, nothing
    is returned rather than a list that might be wrong.
    """
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _mps_that_moved_batch,
    )
    rows = []
    for table, field, need_field in ((MATERIAL_MAPPING, "batch", "batch_calc_qty"),
                                     (AVAILABLE_RAW_MATERIAL, "batch_no", "required_qty")):
        for r in frappe.get_all(
            table, filters={field: batch_no, "is_reserved": 0},
            fields=["name", "parent", "idx", "duno_mark_no", need_field + " as need"],
            order_by="parent asc, idx asc",
        ):
            if (table, r.name) in exclude_rows or flt(r.need) <= EPS:
                continue
            if warehouse and (frappe.db.get_value("Material Planning", r.parent, "for_warehouse") or "") != warehouse:
                continue
            rows.append({"material_planning": r.parent, "idx": r.idx,
                         "duno": r.duno_mark_no or "", "qty": flt(r.need, 3)})
    if not rows:
        return []
    moved = _mps_that_moved_batch(batch_no)
    if moved is None:
        return []
    return [r for r in rows if r["material_planning"] not in moved]


def _target_index_of(fill, member):
    if not fill:
        return None
    for a in fill.assignments:
        if a.member.source_row == member.source_row and a.member.source_table == member.source_table:
            return a.target_index
    return None


def _cross_table_conflicts(mp_names, batch_nos, members):
    """Target batches that would end up in BOTH child tables of one plan.

    _validate_no_cross_table_batch_duplicate refuses a Material Planning that holds
    one batch in Material Mapping and Available Raw Material at the same time. It
    fires at save time, which is far too late here: by then the members have been
    unreserved and the plan is half-changed.

    What is emphatically NOT a conflict is many rows of the SAME table sharing one
    batch. That is the ordinary case -- one plate cut into a dozen parts -- and
    treating it as a clash refuses nearly every real reassignment.

    So the duplicate can only arise two ways, and both are checked per plan:
      1. the target batch already sits in the table the members are NOT in, or
      2. this line's own members straddle both tables, so moving them all onto one
         batch puts that batch in both by itself.
    """
    member_rows = {(m.source_table, m.source_row) for m in members}
    tables_by_mp = {}
    for m in members:
        tables_by_mp.setdefault(m.material_planning, set()).add(m.source_table)

    problems = []
    for mp_name in sorted(tables_by_mp):
        tables = tables_by_mp[mp_name]

        if MATERIAL_MAPPING in tables and AVAILABLE_RAW_MATERIAL in tables:
            problems.append(
                _("On {0} this line's rows sit in both Material Mapping and Exact Match. "
                  "Moving them all to one batch would put that batch in both tables, which "
                  "a Material Planning does not allow. Reassign them separately.")
                .format(mp_name)
            )
            continue

        other = AVAILABLE_RAW_MATERIAL if MATERIAL_MAPPING in tables else MATERIAL_MAPPING
        field = "batch_no" if other == AVAILABLE_RAW_MATERIAL else "batch"
        for r in frappe.get_all(
            other,
            filters={"parent": mp_name, field: ["in", batch_nos]},
            fields=["name", "idx", field + " as batch_no"],
        ):
            if (other, r.name) in member_rows:
                continue
            problems.append(
                _("Batch {0} is already used on {1} row {2} of {3}. "
                  "A plan cannot hold one batch in both tables.")
                .format(r.batch_no,
                        _("Exact Match") if other == AVAILABLE_RAW_MATERIAL else _("Material Mapping"),
                        r.idx, mp_name)
            )
    return problems


@frappe.whitelist()
def get_consolidate_line_context(mip_name, consolidate_row_name):
    """The item and warehouse for one line, resolved the way the preview resolves them.

    The dialog used to take the warehouse from the Material Issue Plan's own
    `source_warehouse`, but every stock figure the server computes comes from the
    Material Planning's `for_warehouse`. On a plan where the two differ -- or where
    the Material Issue Plan's is simply blank, which happens -- the candidate list
    and the live capacity were priced against a different warehouse from the one the
    reassignment would actually use, or came back empty for no visible reason.

    Asking the server settles it: there is one answer and both halves use it.
    """
    mip = frappe.get_doc("Material Issue Plan", mip_name)
    key, members = expand_consolidate_row(mip, consolidate_row_name)

    warehouses = set()
    for name in sorted({m.material_planning for m in members if m.material_planning}):
        warehouses.add(frappe.db.get_value("Material Planning", name, "for_warehouse") or "")

    return {
        "item_code": key[0],
        "batch_no": key[1],
        "rows": len(members),
        # Empty when the plans disagree; the preview refuses that case outright, and
        # the dialog should not pretend to price it in the meantime.
        "warehouse": next(iter(warehouses), "") if len(warehouses) == 1 else "",
        "warehouses": sorted(w for w in warehouses if w),
    }


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def consolidate_batch_query(doctype, txt, searchfield, start, page_len, filters):
    """The searchable batch picker for a Consolidate Items line.

    Same shape as material_mapping_batch_query, deliberately: that is the picker this
    one sits beside, and a planner should not have to learn two. Type part of a batch
    name or an item code and it narrows; the columns are item, free Kg and size.

    What differs is which quantity is shown. The mapping picker shows what the batch
    holds; this one shows what is FREE -- the batch's stock less every plan's
    reservations -- because a line can only move onto steel nobody else is counting on.

    Not filtered by item, and not by size. Before a transfer the planner may decide to
    send one ISMB800 in place of four ISMB200; the requirement does not change, the
    steel does. Reserve Without Dimensions makes the size question go away, so Kg is
    the only number that has to reconcile, and availability is the only test.

    The line's own item sorts first so the ordinary choice stays at the top.
    """
    warehouse = (filters or {}).get("warehouse")
    if not warehouse:
        # Nothing to measure free stock against. Offering the whole site here would
        # put batches from another shed in front of the planner.
        return []
    own_item = (filters or {}).get("item_code") or ""

    needle = (txt or "").lower()
    rows = []
    for b in frappe.get_all("Batch", filters={"disabled": 0}, fields=["name", "item"]):
        if needle and needle not in b.name.lower() and needle not in (b.item or "").lower():
            continue
        free = _batch_free_kg(b.name, warehouse)
        if free <= EPS:
            continue
        rows.append((b.name, b.item or "", free))

    rows.sort(key=lambda r: (0 if r[1] == own_item else 1, -r[2], r[0]))

    out = []
    for name, item, free in rows:
        length, width, thickness = _get_batch_dims(name)
        dims = " x ".join(str(flt(d, 2)) for d in (length, width, thickness) if flt(d))
        out.append((name, item, "%s Kg free" % flt(free, 3), dims))

    start, page_len = int(start or 0), int(page_len or 20)
    return out[start:start + page_len]


@frappe.whitelist()
def get_candidate_batches(item_code, warehouse, limit=400):
    """Every batch with free stock in this warehouse -- any item, any size.

    Deliberately NOT filtered to the line's own item. Before a transfer the planner may
    decide to send something else entirely: one ISMB800 instead of four ISMB200, a plate
    in place of a section. The requirement does not change, the steel that goes does, and
    that decision is made on this screen. Offering only the requirement's own item made
    the commonest reason for opening the dialog impossible.

    Size is not filtered either, and does not need to be: Reserve Without Dimensions
    reserves a row's required Kg and expresses the piece count as a fraction, so a line
    can move to a batch of any size. Only one number has to reconcile, and that is Kg.

    Zero-stock batches are still left out, because that is the one failure downstream
    validation does NOT catch -- _validate_batch_calc_qty skips its coverage check when
    batch_stock is zero, so the save succeeds and the reservation quietly comes back as
    nothing.

    Sorted with the line's own item first and by free stock within each group: the
    ordinary choice stays at the top, the substitutions sit below it.
    """
    if not warehouse:
        return []

    out = []
    for b in frappe.get_all(
        "Batch", filters={"disabled": 0}, fields=["name", "item"]
    ):
        free = _batch_free_kg(b.name, warehouse)
        if free <= EPS:
            continue
        length, width, thickness = _get_batch_dims(b.name)
        out.append({
            "batch_no": b.name,
            "item_code": b.item,
            "same_item": 1 if (item_code and b.item == item_code) else 0,
            "free_kg": free,
            "length": flt(length),
            "width": flt(width),
            "thickness": flt(thickness),
        })

    out.sort(key=lambda b: (-b["same_item"], -b["free_kg"]))
    return out[: int(limit)]
# ─────────────────────────────────────────────────────────────────────────────
# Apply — the only code in this module that writes
# ─────────────────────────────────────────────────────────────────────────────

def _apply_to_one_plan(mp_name, plan_writes, mip_name, progress=None):
    """Reassign every member belonging to ONE Material Planning, and re-reserve it.

    The unit of atomicity. unreserve_batches, unreserve_exact_match_batches,
    reserve_batches and reserve_exact_match_batches each commit internally, and
    MariaDB destroys every SAVEPOINT on COMMIT, so a savepoint taken before the
    first of them no longer exists by the time you would roll back to it. There is
    no way to make the whole fan-out atomic without changing those four functions
    (see Phase 7 in the task plan). What there IS a way to do is bound the damage:
    do one plan completely before starting the next, so a failure leaves at most
    one plan's reservations released, and release them only as late as possible.

    Returns what happened, for the composed report. Raises to stop the fan-out.
    """
    mm_writes = [w for w in plan_writes if w.member.source_table == MATERIAL_MAPPING]
    arm_writes = [w for w in plan_writes if w.member.source_table == AVAILABLE_RAW_MATERIAL]

    # 1/2 — release first. _validate_batch_calc_qty refuses outright to save a
    # reserved row whose batch changed ("Unreserve the stock to update"), so the
    # release cannot be deferred until after the write. Each call takes the whole
    # list at once; never mix the two tables' row names, and never call with an
    # empty list -- both helpers throw "No matching reserved rows found." when
    # nothing they were given exists in their own table.
    if mm_writes:
        unreserve_batches(mp_name, json.dumps([w.member.source_row for w in mm_writes]))
    if arm_writes:
        unreserve_exact_match_batches(mp_name, json.dumps([w.member.source_row for w in arm_writes]))

    # Past this line the rows are released and COMMITTED. The caller needs to know,
    # because the two failure states read very differently to whoever has to clean up:
    # a failure before here changed nothing at all, a failure after here left rows
    # unreserved on their old batch.
    if progress is not None:
        progress["released"] = True

    # 3 — re-fetch: those calls saved and committed the document underneath us.
    mp = frappe.get_doc("Material Planning", mp_name)
    mm_by_name = {r.name: r for r in mp.material_mapping}
    arm_by_name = {r.name: r for r in mp.available_raw_materials}

    # 4 — apply, and log one audit row per member, mirroring reassign_batch.
    first_row_for_batch = {}
    old_batches = set()
    for w in plan_writes:
        member = w.member
        if member.source_table == MATERIAL_MAPPING:
            row = mm_by_name.get(member.source_row)
            if not row:
                frappe.throw(_("Row {0} is no longer in Material Mapping on {1}.")
                             .format(member.source_row, mp_name))
            old_batch = row.batch
            old_sec, old_qty = flt(row.batch_sec_qty), flt(row.batch_calc_qty)
            # Dimensions are deliberately NOT passed. On a Material Mapping row
            # length/width/thickness are the REQUIREMENT's -- what the drawing asks
            # for -- and the batch's own live in batch_length/width/thickness, which
            # _apply_batch_to_mapping_row refreshes from the Batch record itself.
            # Passing dimensions here would rewrite the demand, not the supply.
            _apply_batch_to_mapping_row(
                row, w.batch_no, w.batch_item, {}, w.sec_qty, w.reserve_without_dimensions
            )
            new_sec, new_qty = flt(row.batch_sec_qty), flt(row.batch_calc_qty)
            planned_item = row.planned_item if row.planned_item and row.planned_item != row.item_code else ""
        else:
            row = arm_by_name.get(member.source_row)
            if not row:
                frappe.throw(_("Row {0} is no longer in Exact Match on {1}.")
                             .format(member.source_row, mp_name))
            old_batch = row.batch_no
            old_sec, old_qty = flt(row.sec_qty), flt(row.required_qty)
            # Here the opposite is true: an exact-match row has ONE set of
            # dimensions and they ARE the batch's, so _apply_batch_to_arm_row
            # refreshes them from the new batch. required_qty is never touched.
            _apply_batch_to_arm_row(
                row, w.batch_no, {}, w.sec_qty, w.reserve_without_dimensions,
                old_batch=old_batch, new_item=w.batch_item,
            )
            new_sec, new_qty = flt(row.sec_qty), flt(row.required_qty)
            planned_item = row.planned_item if row.get("planned_item") else ""

        first_row_for_batch.setdefault(w.batch_no, member.source_row)
        if old_batch and old_batch != w.batch_no:
            old_batches.add(old_batch)
        mp.append("batch_change_log", {
            "material_issue_plan": mip_name or "",
            "source_table": member.source_table,
            "source_row": member.source_row,
            "item_code": row.item_code,
            "planned_item": planned_item,
            "old_batch": old_batch,
            "new_batch": w.batch_no or "",
            "old_sec_qty": old_sec,
            "new_sec_qty": new_sec,
            "old_qty": old_qty,
            "new_qty": new_qty,
            "remarks": _batch_change_remarks(row.item_code, old_batch, w.batch_no, mip_name),
        })

    # 5 — ONE save for the whole plan. This is where _apply_rwd_fractional_nos
    # turns every waived row's Sec Nos into the fraction, and it runs BEFORE
    # _validate_batch_calc_qty checks coverage, which is the order that makes
    # sending sec_qty=None safe for Structurals and Plates.
    mp.save(ignore_permissions=True)

    # 6 — a batch recovered from someone's excess return records where it landed.
    for batch_no, row_name in first_row_for_batch.items():
        _mark_excess_item_mapped(batch_no, mp_name, row_name)
    # ...and a batch the rows just LEFT must stop claiming them. See
    # _resync_excess_item_mapping.
    for batch_no in sorted(old_batches):
        _resync_excess_item_mapping(batch_no)

    # 7/8 — re-reserve. Guarded exactly as reassign_batch guards it, including the
    # substring re-raise: a batch still awaiting inspection is a warning to carry
    # back, not a reason to abandon a reassignment that has already been saved.
    #
    # reserve_batches and reserve_exact_match_batches reserve the WHOLE plan and
    # report every row they could not fill. Most of those have nothing to do with
    # this reassignment: on MP-2026-00260 three ISMB400 rows sit 8,870.400 Kg short
    # because that steel has already shipped, and reporting them here said the three
    # rows just moved were only partly reserved when every one of them was full.
    # Only the rows this call touched are ours to report on.
    touched = {w.member.source_row for w in plan_writes}
    partial, inspection = [], []
    mp = frappe.get_doc("Material Planning", mp_name)
    if any(not r.is_reserved and r.batch for r in mp.material_mapping):
        try:
            partial.extend(
                p for p in ((reserve_batches(mp_name) or {}).get("partial") or [])
                if p.get("name") in touched
            )
        except frappe.ValidationError as e:
            if "blocked pending inspection completion" not in str(e):
                raise
            inspection.append(str(e))
        mp = frappe.get_doc("Material Planning", mp_name)
    if any(not r.is_reserved and r.batch_no for r in mp.available_raw_materials):
        try:
            partial.extend(
                p for p in ((reserve_exact_match_batches(mp_name) or {}).get("partial") or [])
                if p.get("name") in touched
            )
        except frappe.ValidationError as e:
            if "blocked pending inspection completion" not in str(e):
                raise
            inspection.append(str(e))

    # 9 — one entry per plan. Unlike the per-row dialog, this IS one decision.
    kg = flt(sum(flt(w.member.target_kg) for w in plan_writes), 3)
    batches = sorted({w.batch_no for w in plan_writes})
    log_decision(
        "Reassign Batch",
        reference_doctype="Material Planning",
        reference_name=mp_name,
        rows_affected=len(plan_writes),
        qty=kg,
        new_batch_no=", ".join(batches),
        details=_("Reassigned {0} row(s) ({1} Kg) to {2} from Material Issue Plan {3}.")
                .format(len(plan_writes), kg, ", ".join(batches), mip_name or "-"),
    )

    return frappe._dict({
        "material_planning": mp_name,
        "rows": len(plan_writes),
        "qty": kg,
        "batches": batches,
        "partial": partial,
        "inspection_warnings": inspection,
    })


def _composed_failure(applied, stopped_mp, reason, untouched, released=True):
    """The message a part-way failure leaves behind.

    Written out in full because the state it describes is genuinely mixed, and an
    operator who is told only "it failed" will either re-run blindly or go looking
    for damage that is not there. Each plan is in exactly one of three states and
    each needs a different response, so each is named.
    """
    lines = [_("<b>Batch update stopped part-way.</b>")]

    if applied:
        lines.append("<br><b>" + _("Applied and committed") + "</b>")
        for a in applied:
            lines.append(_("• {0} — {1} row(s) → {2} ({3} Kg), reserved.")
                         .format(a.material_planning, a.rows, ", ".join(a.batches), a.qty))

    lines.append("<br><b>" + _("Stopped at") + "</b>")
    lines.append(_("• {0} — {1}").format(stopped_mp, reason))
    if released:
        lines.append(_("Its rows are <b>released from reservation but still carry their "
                       "original batch</b>. Nothing was lost. Reserve them again, or simply "
                       "re-run this update — it recomputes from the current state, so the "
                       "plans above are no longer part of it."))
    else:
        lines.append(_("<b>Nothing on this plan was changed</b> — it failed before anything "
                       "was released. Re-running is safe: it recomputes from the current "
                       "state, so the plans above are no longer part of it."))

    if untouched:
        lines.append("<br><b>" + _("Not touched") + "</b>")
        lines.append("• " + ", ".join(untouched))

    lines.append(_("<br>If the reason above looks unrelated to the batch change, that plan "
                   "most likely has a pre-existing validation problem that this save was "
                   "the first to re-check."))
    return "<br>".join(lines)


@frappe.whitelist()
def apply_consolidate_batch_update(mip_name, consolidate_row_name, targets_json, plan_hash=None):
    """Reassign every row behind one Consolidate Items line. Writes.

    Runs the plan again from live state and refuses unless it still agrees with the
    one the user confirmed -- see plan_hash. Then works through the Material
    Plannings one at a time, in sorted name order, each fully finished before the
    next is started.

    That ordering is the safety property. The four reserve/unreserve helpers commit
    internally, so there is no transaction spanning the fan-out and a failure cannot
    be rolled back wholesale. Doing one plan at a time bounds what a failure can
    leave behind to a single plan's reservations, and leaves that plan holding its
    ORIGINAL batch -- a state that is recoverable by re-running, because the members
    are re-derived by grouping key each time and rows that already moved no longer
    match the line.
    """
    plan = _build_plan(mip_name, consolidate_row_name, targets_json)
    response = plan.response

    if response.get("stock_actions_block"):
        frappe.throw(response["blockers"][0], title=_("Batch Cannot Be Reassigned"))
    if not response.get("ok"):
        frappe.throw(
            "<br>• ".join([_("This reassignment cannot be applied:")]
                          + (response.get("blockers") or [_("No target batch was given.")])),
            title=_("Batch Update Refused"),
        )

    # A plan is confirmed against figures that were true when it was previewed. If
    # stock moved, a row shipped, or someone else reassigned a member in between,
    # the fingerprint changes and the stale plan is refused rather than applied to a
    # world it no longer describes.
    if plan_hash and response.get("plan_hash") != plan_hash:
        frappe.throw(
            _("The figures behind this line changed while the dialog was open — stock "
              "moved, a row was transferred, or someone else reassigned one of these "
              "rows. Preview it again and check before applying."),
            title=_("Plan Out Of Date"),
        )

    writes_by_mp = {}
    for w in plan.writes:
        writes_by_mp.setdefault(w.member.material_planning, []).append(w)

    ordered = sorted(writes_by_mp)
    applied, partial, inspection = [], [], []

    for i, mp_name in enumerate(ordered):
        progress = {"released": False}
        try:
            result = _apply_to_one_plan(mp_name, writes_by_mp[mp_name], mip_name, progress)
        except Exception as e:
            frappe.throw(
                _composed_failure(applied, mp_name, str(e), ordered[i + 1:],
                                  released=progress["released"]),
                title=_("Batch Update Stopped"),
            )
        applied.append(result)
        partial.extend(result.partial)
        inspection.extend(result.inspection_warnings)

    # Stage 2 — one rebuild of the MIP's read-only snapshot, after every plan is
    # done. The consolidate table regenerates from it, so the line the user was
    # looking at is replaced by one keyed on the new batch.
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        refresh_mip_raw_materials,
    )
    refresh_mip_raw_materials(mip_name)

    # Only what happened DURING the apply. The preview's warnings (a parked transfer
    # draft, an uninspected batch) were already shown on the confirmation the user said
    # Yes to; repeating them afterwards reads as a new problem.
    warnings = list(inspection)
    if partial:
        # reserve_batches does NOT throw on a shortfall -- it reserves what it can
        # and records the rest. Without surfacing that, a fan-out that reserved half
        # of what it moved would report success.
        warnings.append(
            _("{0} row(s) could only be partly reserved ({1} Kg short in total). "
              "The batch was reassigned; the reservation is incomplete.")
            .format(len(partial), flt(sum(flt(p.get("shortfall_qty")) for p in partial), 3))
        )

    return {
        "ok": True,
        "from_batch": plan.key[1],
        "to_batches": sorted({b for a in applied for b in a.batches}),
        "applied": [dict(a) for a in applied],
        "rows": sum(a.rows for a in applied),
        "qty": flt(sum(a.qty for a in applied), 3),
        "warnings": warnings,
        "partial": partial,
    }
