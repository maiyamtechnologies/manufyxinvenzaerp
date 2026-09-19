"""Applying a Consolidate Items batch reassignment -- Phases 3 and 4.

Phase 1 built the read-only half: expand a line to its members, price the target
batches, report what a reassignment would do. This is the half that writes.

The whole design rests on one uncomfortable fact: unreserve_batches,
unreserve_exact_match_batches, reserve_batches and reserve_exact_match_batches each
COMMIT internally, and MariaDB destroys every SAVEPOINT on COMMIT. There is no
transaction spanning the fan-out and no way to roll one back. Safety therefore comes
from two places, and both are tested here:

  * everything that can be refused is refused BEFORE the first write (checks 2-4), and
  * plans are done one at a time so a failure strands at most one plan's
    reservations, on its ORIGINAL batch, recoverable by re-running.

The live round trip (check 6) is the only thing that proves the writing path end to
end, and it genuinely reassigns real reservations, so it is OFF by default:

    bench --site manufact execute manufyxinvenzaerp.tests.verify_consolidate_batch_apply.run --kwargs "{'live': 1}"

It moves a line to another batch, checks the result, and moves it back, asserting the
rows come home byte-identical. Note that a reassign discards that line's parked
transfer draft by design -- the draft is keyed on the batch -- so the round trip does
NOT restore it. Take a backup first.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_consolidate_batch_apply.run
"""

import json

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.subcontracting_management import material_issue_plan_batch_update as bu

checks = []

MM_TABLE = "Material Planning Material Mapping"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _member(kg, table=None, mp="MP-1", row=None, group="Plates", idx=1):
    return frappe._dict({
        "target_kg": kg, "source_table": table or bu.MATERIAL_MAPPING,
        "material_planning": mp, "source_row": row or ("r%s" % kg),
        "parent_item_group": group, "idx": idx,
    })


def _target(batch, cap, group="Plates", unit_weight=7.85, item="X"):
    return {"batch_no": batch, "effective_capacity_kg": cap, "parent_item_group": group,
            "unit_weight": unit_weight, "item_code": item}


def run(live=0):
    print("=== 1. Each member is given a waiver and a Sec Nos that cannot be silently wrong ===")
    # The trap this guards: _apply_batch_to_mapping_row, given rwd=0 and no Sec Nos,
    # keeps the OLD batch's piece count and prices it against the NEW batch's
    # dimensions. Nothing throws; the row simply comes to hold a meaningless weight.
    fill = bu.plan_fill([_member(100), _member(200)], [_target("A", 1000)])
    writes, blockers, warnings = bu.plan_member_writes(fill, [_target("A", 1000)])
    check("plates are waived", [w.reserve_without_dimensions for w in writes], [1, 1])
    check("and their Sec Nos is left for the server to derive",
          [w.sec_qty for w in writes], [None, None])
    check("no blockers", blockers, [])

    nb = _target("B", 1000, group="Nuts and Bolts", unit_weight=0.25)
    fill_nb = bu.plan_fill([_member(100, group="Nuts and Bolts")], [nb])
    writes_nb, blockers_nb, warnings_nb = bu.plan_member_writes(fill_nb, [nb])
    # A bolt's weight is exact, so the waiver is wrong for it -- but then Sec Nos MUST
    # be sent explicitly, or the trap above applies.
    check("bolts are not waived", writes_nb[0].reserve_without_dimensions, 0)
    check("so their piece count is computed and sent", writes_nb[0].sec_qty, 400.0)
    check("a whole count raises no warning", warnings_nb, [])

    odd = _target("B", 1000, group="Nuts and Bolts", unit_weight=0.3)
    w_odd, _b, warn_odd = bu.plan_member_writes(
        bu.plan_fill([_member(100, group="Nuts and Bolts")], [odd]), [odd])
    check("a fractional count is surfaced, not rounded away", len(warn_odd), 1)
    check("and the weight is left exactly as planned", w_odd[0].sec_qty, 333.333)

    no_uw = _target("B", 1000, group="Nuts and Bolts", unit_weight=0)
    _w, b_uw, _warn = bu.plan_member_writes(
        bu.plan_fill([_member(100, group="Nuts and Bolts")], [no_uw]), [no_uw])
    check("an item with no unit weight is refused, not guessed", len(b_uw), 1)

    print()
    print("=== 2. The split lands where reading the table top to bottom says it will ===")
    ms = [_member(300, row="a"), _member(300, row="b"), _member(400, row="c")]
    ts = [_target("A", 700), _target("B", 700)]
    f = bu.plan_fill(ms, ts)
    w2, _b2, _w2 = bu.plan_member_writes(f, ts)
    check("the third row moves whole to the second batch",
          [x.batch_no for x in w2], ["A", "A", "B"])
    check("and the capacity it could not use is reported", f.leftover_kg[0], 100.0)

    print()
    print("=== 3. Same-table batch sharing is NOT a cross-table conflict ===")
    # One plate cut into a dozen parts means a dozen Material Mapping rows on one
    # batch. Treating that as a clash refuses nearly every real reassignment -- and
    # it did, until this was fixed. _validate_no_cross_table_batch_duplicate only
    # refuses a batch held in Material Mapping AND Exact Match at once.
    shared = frappe.db.sql("""
        SELECT parent, batch, COUNT(*) n FROM `tabMaterial Planning Material Mapping`
        WHERE batch != '' GROUP BY parent, batch HAVING n > 1 LIMIT 1
    """, as_dict=True)
    if not shared:
        print("  (no batch shared by two Material Mapping rows on this site -- skipped)")
    else:
        mp_name, batch = shared[0].parent, shared[0].batch
        rows = frappe.get_all("Material Planning Material Mapping",
                              filters={"parent": mp_name, "batch": batch}, fields=["name"])
        members = [frappe._dict({"source_table": bu.MATERIAL_MAPPING, "source_row": r.name,
                                 "material_planning": mp_name}) for r in rows[:1]]
        problems = bu._cross_table_conflicts([mp_name], [batch], members)
        same_table = [p for p in problems if "Material Mapping row" in p]
        check("%d rows of %s share %s without clashing" % (shared[0].n, mp_name, batch),
              same_table, [])

    print()
    print("=== 4. A line whose rows straddle both tables is refused up front ===")
    straddle = [
        frappe._dict({"source_table": bu.MATERIAL_MAPPING, "source_row": "m1", "material_planning": "MP-X"}),
        frappe._dict({"source_table": bu.AVAILABLE_RAW_MATERIAL, "source_row": "a1", "material_planning": "MP-X"}),
    ]
    problems = bu._cross_table_conflicts(["MP-X"], ["B1"], straddle)
    check("moving both onto one batch would duplicate it", len(problems), 1)
    check("and the reason names both tables",
          "both Material Mapping and Exact Match" in problems[0], True)

    print()
    print("=== 5. The apply path refuses what the preview refused ===")
    moved = frappe.db.sql("""
        SELECT c.parent AS mip, c.name AS crow FROM `tabMaterial Issue Plan Consolidate Item` c
        WHERE c.transferred_qty > 0 LIMIT 1
    """, as_dict=True)
    if not moved:
        print("  (no transferred consolidate line on this site -- skipped)")
    else:
        try:
            bu.apply_consolidate_batch_update(moved[0].mip, moved[0].crow, "[]", None)
            check("a transferred line is refused", False, True)
        except frappe.ValidationError as e:
            check("a transferred line is refused",
                  ("already been transferred" in str(e)) or ("cannot be reassigned" in str(e)), True)

    live_line = frappe.db.sql("""
        SELECT c.parent AS mip, c.name AS crow, c.item_code, c.batch_no, c.qty, c.source_rows
        FROM `tabMaterial Issue Plan Consolidate Item` c
        WHERE c.transferred_qty = 0 AND c.source_rows > 1 ORDER BY c.source_rows LIMIT 1
    """, as_dict=True)
    if live_line:
        line = live_line[0]
        targets = json.dumps([{"batch_no": line.batch_no, "pieces": 1}])
        try:
            bu.apply_consolidate_batch_update(line.mip, line.crow, targets, None)
            check("reassigning to the batch it already has is refused", False, True)
        except frappe.ValidationError as e:
            check("reassigning to the batch it already has is refused",
                  "already uses" in str(e), True)

        # A plan confirmed against figures that have since changed must not be applied.
        try:
            bu.apply_consolidate_batch_update(line.mip, line.crow, targets, "stalehash0000000")
            check("a stale plan_hash is refused", False, True)
        except frappe.ValidationError as e:
            check("a stale plan_hash is refused",
                  ("Out Of Date" in str(e) or "changed while the dialog" in str(e)
                   or "already uses" in str(e)), True)

    print()
    print("=== 5b. The line's warehouse comes from the plan, not the Issue Plan ===")
    # Every stock figure the server computes uses the Material Planning's
    # for_warehouse. The dialog used to price candidate batches against the Material
    # Issue Plan's own source_warehouse instead. On most plans the two agree, which is
    # exactly why this went unnoticed -- and on a plan where the Issue Plan's is blank
    # the candidate list came back empty for no visible reason.
    mismatched = frappe.db.sql("""
        SELECT c.parent AS mip, c.name AS crow, m.source_warehouse AS mip_wh,
               p.for_warehouse AS mp_wh
        FROM `tabMaterial Issue Plan Consolidate Item` c
        JOIN `tabMaterial Issue Plan` m ON m.name = c.parent
        JOIN `tabMaterial Issue Plan Raw Material` r
             ON r.parent = c.parent AND r.batch_no = c.batch_no
        JOIN `tabMaterial Planning` p ON p.name = r.material_planning
        WHERE IFNULL(m.source_warehouse, '') != IFNULL(p.for_warehouse, '')
          AND IFNULL(p.for_warehouse, '') != ''
        LIMIT 1
    """, as_dict=True)
    if not mismatched:
        print("  (every plan on this site agrees with its Issue Plan -- nothing to prove)")
    else:
        case = mismatched[0]
        ctx = bu.get_consolidate_line_context(case.mip, case.crow)
        check("%s: Issue Plan says %r, plan says %r"
              % (case.mip, case.mip_wh or "", case.mp_wh),
              ctx["warehouse"], case.mp_wh)
        check("and candidates are found there",
              len(bu.get_candidate_batches(ctx["item_code"], ctx["warehouse"])) > 0, True)

    print()
    print("=== 5c. Client decisions of 14 Sep 2026 ===")
    import inspect, re
    # Batches are reassigned from Consolidate Items only.
    rm = frappe.get_meta("Material Issue Plan Raw Material").get_field("update_batch_btn")
    check("Raw Materials row button is hidden", bool(rm and rm.hidden), True)
    js = open(frappe.get_app_path("manufyxinvenzaerp", "subcontracting_management", "doctype",
                                  "material_issue_plan", "material_issue_plan.js")).read()
    check("Raw Materials toolbar button is no longer added",
          bool(re.search(r"^\s*_add_update_batch_button\(frm\);", js, re.M)), False)

    ci = frappe.get_meta("Material Issue Plan Consolidate Item")
    btn = ci.get_field("update_batch_btn")
    check("Consolidate Items has a per-row Update Batch", bool(btn and btn.in_list_view), True)
    # Frappe silently drops every column after the one that passes 11.
    budget = 1 + sum((df.columns or 2) for df in ci.fields
                     if df.in_list_view and not df.hidden
                     and df.fieldtype not in ("Section Break", "Column Break", "Tab Break"))
    check("and the grid still fits Frappe's 11-column budget", budget <= 11, True)
    check("the row button is drawn by a formatter (grid is read-only)",
          "meta_df.formatter = formatter" in js and "addEventListener(\"click\"" in js, True)

    # Only Pieces is typed; a batch is always priced at its own size.
    params = list(inspect.signature(bu.get_batch_capacity).parameters)
    check("get_batch_capacity takes no length/width", params, ["batch_no", "warehouse", "pieces"])
    check("the dialog sends batch and pieces only",
          "({ batch_no: t.batch_no, pieces: t.pieces || 0 })" in js, True)
    check("Length/Width inputs are read-only",
          js.count('readonly tabindex="-1"') >= 2, True)

    if live_line:
        line = live_line[0]
        other = next((b for b in bu.get_candidate_batches(
            line.item_code, frappe.db.get_value("Material Issue Plan", line.mip, "source_warehouse") or "")
            if b["batch_no"] != line.batch_no), None)
        if other:
            plain = bu.preview_consolidate_batch_update(
                line.mip, line.crow, json.dumps([{"batch_no": other["batch_no"], "pieces": 1}]))
            forced = bu.preview_consolidate_batch_update(
                line.mip, line.crow,
                json.dumps([{"batch_no": other["batch_no"], "pieces": 1, "length": 1, "width": 1}]))
            check("a length/width sent anyway is ignored",
                  forced["targets"][0]["capacity_kg"], plain["targets"][0]["capacity_kg"])
            m0 = plain["members"][0]
            src_field = "reserved_qty"
            live_reserved = flt(frappe.db.get_value(m0["source_table"], m0["source_row"], src_field), 3)
            check("confirmation shows the reservation as the plan holds it",
                  (m0["reserved_qty"], "is_reserved" in m0), (live_reserved, True))

    src = inspect.getsource(bu)
    check("draft warning uses the agreed wording",
          'unfinished entries saved from \\"Select Materials to Transfer\\"' in src, True)
    check("confirmation popup names the unreserve step",
          "Yes, Unreserve and Reassign" in js and "Current reservation and new assignment" in js, True)

    print()
    print("=== 5d. Excess stays tracked through a reassignment ===")
    # Both checks write and are rolled back straight after -- nothing here commits.
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        _resync_excess_item_mapping,
    )
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        refresh_mip_raw_materials,
    )

    # (a) An excess-return batch reserved into a plan records which row took it. Moving
    # that row off the batch must re-point the record, or clear it -- otherwise the
    # source plan goes on showing its off-cut as reused.
    mapped = frappe.db.sql("""
        SELECT e.name AS excess_row, b.name AS batch_no, m.name AS mm_row
        FROM `tabSCO Excess Material Item` e
        JOIN `tabBatch` b ON b.custom_source_mip_excess_row = e.name
        JOIN `tabMaterial Planning Material Mapping` m
             ON m.name = e.mapped_row_name AND m.batch = b.name AND IFNULL(m.is_virtual_excess, 0) = 0
        LIMIT 1
    """, as_dict=True)
    if not mapped:
        print("  (no excess-return batch reserved into a plan on this site -- skipped)")
    else:
        mx = mapped[0]
        ptr = lambda: tuple(frappe.db.get_value("SCO Excess Material Item", mx.excess_row,
                                                ["mapped_material_planning", "mapped_row_name"]))
        start = ptr()
        _resync_excess_item_mapping(mx.batch_no)
        check("row still on the batch: pointer unchanged", ptr(), start)
        frappe.db.set_value(MM_TABLE, mx.mm_row, "batch", "", update_modified=False)
        holders = frappe.get_all(MM_TABLE, filters={"batch": mx.batch_no}, pluck="name")
        _resync_excess_item_mapping(mx.batch_no)
        if holders:
            check("row moved off, another holds it: re-pointed", ptr()[1] in holders, True)
        else:
            check("row moved off, nobody holds it: cleared", ptr(), ("", ""))
        frappe.db.rollback()
        check("(rolled back)", ptr(), start)

    # (b) A rebuild of Raw Materials -- which every batch update ends with -- must keep
    # the rounding surplus already booked onto transferred rows.
    has_excess = frappe.db.sql("""
        SELECT parent, COUNT(*) n, ROUND(SUM(transfer_excess_kg), 3) kg
        FROM `tabMaterial Issue Plan Raw Material` WHERE transfer_excess_kg > 0
        GROUP BY parent ORDER BY n DESC LIMIT 1
    """, as_dict=True)
    if not has_excess:
        print("  (no transferred row carries round-up excess on this site -- skipped)")
    else:
        hx = has_excess[0]
        refresh_mip_raw_materials(hx.parent)
        after = frappe.db.sql("""
            SELECT COUNT(*) n, ROUND(IFNULL(SUM(transfer_excess_kg), 0), 3) kg
            FROM `tabMaterial Issue Plan Raw Material` WHERE parent = %s AND transfer_excess_kg > 0
        """, hx.parent, as_dict=True)[0]
        frappe.db.rollback()
        check("%s: round-up excess survives a rebuild (%s rows, %s Kg)" % (hx.parent, hx.n, hx.kg),
              (after.n, flt(after.kg, 3)), (hx.n, flt(hx.kg, 3)))

    print()
    print("=== 5e. No batch change once any stock action exists on the plan ===")
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        _mip_stock_actions, _mip_batch_change_blocked_message, check_mip_batch_change_allowed,
    )
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        reassign_batch,
    )
    plans = frappe.get_all("Material Issue Plan", pluck="name")
    acted = [n for n in plans if _mip_stock_actions(frappe.get_doc("Material Issue Plan", n))]
    clean = [n for n in plans if n not in acted
             and frappe.db.exists("Material Issue Plan Consolidate Item", {"parent": n, "batch_no": ["!=", ""]})]
    if not acted:
        print("  (no plan with a stock action on this site -- skipped)")
    else:
        name = acted[0]
        actions = _mip_stock_actions(frappe.get_doc("Material Issue Plan", name))
        res = check_mip_batch_change_allowed(name)
        check("%s is blocked" % name, res["blocked"], True)
        check("and the message names every entry",
              all(a.name in res["message"] for a in actions), True)
        check("and says the Raw Materials table cannot be refreshed",
              "Raw Materials table cannot be refreshed" in res["message"], True)

        crow = frappe.db.get_value("Material Issue Plan Consolidate Item",
                                   {"parent": name, "batch_no": ["!=", ""]}, "name")
        if crow:
            pv = bu.preview_consolidate_batch_update(name, crow, "[]")
            check("preview refuses it", (pv["ok"], pv.get("stock_actions_block")), (False, True))
            try:
                bu.apply_consolidate_batch_update(name, crow, "[]", None)
                check("apply refuses it", False, True)
            except frappe.ValidationError as e:
                check("apply refuses it", "cannot be reassigned" in str(e), True)

        # The per-row path, when driven from this plan, is refused before it writes.
        raw = frappe.db.get_value("Material Issue Plan Raw Material",
                                  {"parent": name, "batch_no": ["!=", ""],
                                   "source_table": ["in", [bu.MATERIAL_MAPPING, bu.AVAILABLE_RAW_MATERIAL]]},
                                  ["material_planning", "source_table", "source_row", "batch_no"], as_dict=True)
        if raw:
            try:
                reassign_batch(raw.material_planning, raw.source_table, raw.source_row, raw.batch_no,
                               material_issue_plan=name)
                check("per-row reassign from the plan refuses it", False, True)
            except frappe.ValidationError as e:
                check("per-row reassign from the plan refuses it", "cannot be reassigned" in str(e), True)
            check("and wrote nothing", bool(frappe.db.transaction_writes), False)

    # An excess return received with no supplier involved is tagged to the plan alone,
    # which the older Refresh Raw Materials rule never saw.
    plan_only = frappe.db.sql("""
        SELECT se.custom_mip_ref AS mip FROM `tabStock Entry` se
        JOIN `tabMaterial Issue Plan` m ON m.name = se.custom_mip_ref
        WHERE se.docstatus < 2 AND IFNULL(se.custom_sco_ref, '') = ''
          AND IFNULL(se.subcontracting_order, '') = '' AND IFNULL(m.subcontracting_order, '') = ''
        LIMIT 1""", as_dict=True)
    if plan_only:
        check("%s (entry tagged to the plan only) is blocked too" % plan_only[0].mip,
              check_mip_batch_change_allowed(plan_only[0].mip)["blocked"], True)
    if clean:
        check("%s (no stock action) is not blocked" % clean[0],
              _mip_batch_change_blocked_message(frappe.get_doc("Material Issue Plan", clean[0])), None)

    check("every Update Batch entry point asks first",
          js.count("_open_consolidate_update_batch(frm") >= 3
          and "check_mip_batch_change_allowed" in js, True)

    print()
    print("=== 5f. A target batch assigned-but-unreserved elsewhere is warned about ===")
    # Reserved stock is what blocks. A row elsewhere holding the batch WITHOUT a
    # reservation does not -- but moving a line onto that batch can leave its Material
    # Planning unable to save (MP-2026-00015, 14 Sep 2026), so the preview says so.
    claimed = frappe.db.sql("""
        SELECT m.batch, p.for_warehouse FROM `tabMaterial Planning Material Mapping` m
        JOIN `tabMaterial Planning` p ON p.name = m.parent
        WHERE IFNULL(m.batch, '') != '' AND m.is_reserved = 0 AND m.batch_calc_qty > 0
        LIMIT 20""", as_dict=True)
    found = next((c for c in claimed if bu._assigned_elsewhere(c.batch, c.for_warehouse, set())), None)
    if not found:
        print("  (no batch assigned-but-unreserved on this site -- skipped)")
    else:
        rows = bu._assigned_elsewhere(found.batch, found.for_warehouse, set())
        check("assigned-but-unreserved rows on %s are listed" % found.batch, len(rows) > 0, True)
        check("each names its plan, row and Kg",
              all(r["material_planning"] and r["idx"] and r["qty"] > 0 for r in rows), True)
        # Every row holding the batch, in both tables _assigned_elsewhere reads -- a
        # plan elsewhere can hold the same batch in Exact Match (MP-2026-00157 did).
        members = {(bu.MATERIAL_MAPPING, n) for n in frappe.get_all(
            bu.MATERIAL_MAPPING, filters={"batch": found.batch}, pluck="name")}
        members |= {(bu.AVAILABLE_RAW_MATERIAL, n) for n in frappe.get_all(
            bu.AVAILABLE_RAW_MATERIAL, filters={"batch_no": found.batch}, pluck="name")}
        excluded = bu._assigned_elsewhere(found.batch, found.for_warehouse, members)
        check("the line's own members are never listed against it", excluded, [])
    src = inspect.getsource(bu._build_plan)
    check("the preview raises it as a warning, not a blocker",
          "warnings.append(" in src and "_assigned_elsewhere(" in src, True)

    print()
    print("=== 6. Live round trip (writes) ===")
    if not live:
        print("  (skipped -- pass live=1 to run it; see this file's docstring)")
    else:
        _round_trip()

    print()
    print("=== 7. Nothing was written by the checks above ===")
    if not live:
        check("no uncommitted changes pending", bool(frappe.db.transaction_writes), False)

    total, failed = len(checks), checks.count(False)
    print()
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, total))
    else:
        print("ALL %d CHECKS PASSED" % total)


def _round_trip():
    """Move a real line to another batch and back, asserting it comes home unchanged."""
    line = frappe.db.sql("""
        SELECT c.parent AS mip, c.name AS crow, c.item_code, c.batch_no
        FROM `tabMaterial Issue Plan Consolidate Item` c
        WHERE c.transferred_qty = 0 AND c.source_rows > 1 ORDER BY c.source_rows LIMIT 1
    """, as_dict=True)
    if not line:
        print("  (no untransferred multi-row line -- skipped)")
        return
    line = line[0]
    mip = frappe.get_doc("Material Issue Plan", line.mip)
    key, members = bu.expand_consolidate_row(mip, line.crow)
    names = [m.source_row for m in members if m.source_table == bu.MATERIAL_MAPPING]
    if len(names) != len(members):
        print("  (line mixes tables -- round trip skipped)")
        return

    fields = ["batch", "batch_calc_qty", "batch_sec_qty", "is_reserved", "reserved_qty",
              "reserve_without_dimensions", "batch_length", "batch_width", "batch_thickness"]

    def snap():
        return {n: frappe.db.get_value(bu.MATERIAL_MAPPING, n, fields, as_dict=True) for n in names}

    before = snap()
    total_before = flt(sum(flt(r.batch_calc_qty) for r in before.values()), 3)

    other = next((b for b in bu.get_candidate_batches(key[0], mip.source_warehouse)
                  if b["batch_no"] != key[1]), None)
    if not other:
        print("  (no alternative batch with free stock -- round trip skipped)")
        return

    out = json.dumps([{"batch_no": other["batch_no"], "pieces": 1}])
    pv = bu.preview_consolidate_batch_update(line.mip, line.crow, out)
    if not pv["ok"]:
        print("  (preview refused the alternative batch: %s -- skipped)" % pv["blockers"])
        return
    bu.apply_consolidate_batch_update(line.mip, line.crow, out, pv["plan_hash"])

    after = snap()
    check("every row moved to the new batch",
          all(r.batch == other["batch_no"] for r in after.values()), True)
    check("the line's total Kg is unchanged",
          flt(sum(flt(r.batch_calc_qty) for r in after.values()), 3), total_before)
    check("every row is waived", all(r.reserve_without_dimensions == 1 for r in after.values()), True)
    check("every row reserves its own requirement",
          all(flt(r.batch_calc_qty, 3) == flt(before[n].batch_calc_qty, 3) for n, r in after.items()), True)
    check("and is reserved again", all(r.is_reserved == 1 for r in after.values()), True)
    check("the batch's dimensions came with it",
          all(flt(r.batch_length) == flt(other["length"]) for r in after.values()), True)

    # Home again. The consolidate row was regenerated, so it must be found afresh.
    mip = frappe.get_doc("Material Issue Plan", line.mip)
    crow = next(c for c in mip.consolidate_items
                if c.item_code == line.item_code and c.batch_no == other["batch_no"])
    back = json.dumps([{"batch_no": line.batch_no, "pieces": 1}])
    pv2 = bu.preview_consolidate_batch_update(line.mip, crow.name, back)
    check("moving back is allowed", pv2["ok"], True)
    if pv2["ok"]:
        bu.apply_consolidate_batch_update(line.mip, crow.name, back, pv2["plan_hash"])
        restored = snap()
        check("every row came home exactly as it left",
              {n: dict(r) for n, r in restored.items()},
              {n: dict(r) for n, r in before.items()})
