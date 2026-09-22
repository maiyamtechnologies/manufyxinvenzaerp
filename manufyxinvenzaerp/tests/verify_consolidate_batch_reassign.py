"""Reassigning the batch behind a whole Consolidate Items line — Phase 1 (read-only).

A consolidate line is a merge of N raw-material rows pointing at N Material Planning
child rows, possibly across several plans. Phase 1 builds the parts that expand a line
back to those rows, price candidate batches, and report what a reassignment would do —
without writing anything.

Two things carry the most risk and are tested hardest here.

**The grouping key.** _sync_consolidate_items builds the table with it and the expansion
reads the table back with it. If the two ever disagree, the dialog edits rows that are
not on the line it is showing. The key now lives in one function; check 1 proves the
refactor is byte-identical to the tuple it replaced, on every row on this site.

**Sizing the fill.** The Kg a member will consume after a dimensionless reassign is NOT
the Kg it consumes today, and Material Mapping and Exact Match disagree about which
field holds it. Getting that wrong plans for the wrong tonnage and the error only
surfaces at reserve time. Check 3 pins it.

Read-only: no fixtures, no writes, nothing to roll back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_consolidate_batch_reassign.run
"""

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_batch_update as bu

    MM = bu.MATERIAL_MAPPING
    ARM = bu.AVAILABLE_RAW_MATERIAL

    print("=== 1. The refactored grouping key is identical to the tuple it replaced ===")
    mismatches = []
    for mip_name in frappe.get_all("Material Issue Plan", pluck="name"):
        mip = frappe.get_doc("Material Issue Plan", mip_name)
        for r in (mip.consolidate_items or []):
            old = (r.item_code, r.batch_no or "", 1 if r.cnc_process else 0)
            if bu.consolidate_group_key(r) != old:
                mismatches.append(("consolidate", mip_name, old, bu.consolidate_group_key(r)))
        for r in (mip.raw_materials or []):
            if not r.batch_no:
                continue
            old = (r.planned_item or r.item_code, r.batch_no, 1 if r.cnc_process else 0)
            if bu.consolidate_group_key(r) != old:
                mismatches.append(("raw", mip_name, old, bu.consolidate_group_key(r)))
    check("no key differs on any row on this site", mismatches, [])

    print()
    print("=== 2. Expansion returns exactly the rows the sync merged ===")
    # The consolidate row states how many rows it merged (source_rows) and their total.
    # If the expansion disagrees with either, the dialog is showing one thing and would
    # edit another.
    examined = 0
    for mip_name in frappe.get_all("Material Issue Plan", pluck="name"):
        mip = frappe.get_doc("Material Issue Plan", mip_name)
        for crow in (mip.consolidate_items or []):
            key, members = bu.expand_consolidate_row(mip, crow.name)
            examined += 1
            if len(members) != crow.source_rows:
                check("%s / %s: member count" % (mip_name, crow.item_code),
                      len(members), crow.source_rows)
            summed = flt(sum(m.qty for m in members), 3)
            if abs(summed - flt(crow.qty, 3)) > bu.EPS:
                check("%s / %s: summed qty" % (mip_name, crow.item_code),
                      summed, flt(crow.qty, 3))
    check("every consolidate line expands to its own source_rows and qty",
          examined > 0, True)
    print("  (%d consolidate line(s) examined)" % examined)

    print()
    print("=== 3. Member sizing uses the right field per source table ===")
    # Material Mapping reserves its REQUIREMENT under RWD (reqd_kg). Exact Match reserves
    # required_qty verbatim, which the MIP row copies into qty -- its reqd_kg is
    # overall_required_qty, the whole requirement, which double-counts when one
    # requirement is split across several exact-match rows.
    fake_mm = frappe._dict({"source_table": MM, "qty": 120.0, "reqd_kg": 100.0})
    fake_arm = frappe._dict({"source_table": ARM, "qty": 40.0, "reqd_kg": 100.0})
    check("Material Mapping member sizes on reqd_kg", bu._member_target_kg(fake_mm), 100.0)
    check("Exact Match member sizes on qty", bu._member_target_kg(fake_arm), 40.0)

    print()
    print("=== 4. The fill: first-fit, in order, never splitting a row ===")
    def _m(kg, tag):
        return frappe._dict({"target_kg": kg, "source_table": MM, "source_row": tag})
    def _t(batch, cap):
        return {"batch_no": batch, "effective_capacity_kg": cap}

    # 600 + 400 across two batches of 700: rows 1-2 fit A (600), row 3 needs 400 and
    # only 100 is left, so it moves wholly to B. A is left with 100 stranded.
    fill = bu.plan_fill([_m(300, "a"), _m(300, "b"), _m(400, "c")],
                        [_t("A", 700), _t("B", 700)])
    check("rows land in table order", [a.batch_no for a in fill.assignments], ["A", "A", "B"])
    check("a row too big for the remainder moves whole", fill.assignments[2].batch_no, "B")
    check("stranded capacity is reported, not silently used", fill.leftover_kg[0], 100.0)
    check("nothing is left unplaced", fill.unassigned, [])
    check("no shortfall", fill.shortfall_kg, 0.0)

    # Short capacity must be reported, not partially applied.
    short = bu.plan_fill([_m(500, "a"), _m(500, "b")], [_t("A", 600)])
    check("a row that fits nowhere is unplaced", len(short.unassigned), 1)
    check("the shortfall is the unplaced weight", short.shortfall_kg, 500.0)

    # A single target is the same algorithm, not a special case.
    one = bu.plan_fill([_m(100, "a"), _m(200, "b")], [_t("A", 1000)])
    check("single target takes everything", len(one.assignments), 2)
    check("and reports what is left", one.leftover_kg[0], 700.0)

    print()
    print("=== 5. Pricing a real batch ===")
    real = frappe.db.sql("""
        SELECT c.parent AS mip, c.name AS crow, c.item_code, c.batch_no, c.qty,
               c.source_rows, c.transferred_qty
        FROM `tabMaterial Issue Plan Consolidate Item` c
        WHERE c.transferred_qty = 0 AND c.source_rows > 1
        ORDER BY c.source_rows DESC LIMIT 1
    """, as_dict=True)
    if not real:
        print("  (no untransferred multi-row consolidate line on this site -- skipped)")
    else:
        line = real[0]
        mip = frappe.get_doc("Material Issue Plan", line.mip)
        print("  using %s / %s / %s (%d rows, %s Kg)"
              % (line.mip, line.item_code, line.batch_no, line.source_rows, line.qty))
        priced = bu.get_batch_capacity(line.batch_no, mip.source_warehouse)
        check("the line's own batch prices", priced.get("ok"), True)
        check("it holds the line's item", priced.get("item_code"), line.item_code)
        check("kg_per_piece is derived", priced.get("kg_per_piece") > 0, True)
        # capacity is zero with no piece count: nothing has been declared yet.
        check("no pieces declared means no capacity", priced.get("capacity_kg"), 0.0)

        print()
        print("=== 6. Preview refuses reassigning a line to the batch it already has ===")
        res = bu.preview_consolidate_batch_update(
            line.mip, line.crow,
            frappe.as_json([{"batch_no": line.batch_no, "pieces": 1}]),
        )
        check("refused", res["ok"], False)
        check("and says why",
              any("already uses" in b for b in res["blockers"]), True)
        check("the group summary names the line",
              res["group"]["item_code"], line.item_code)
        check("and counts its rows", res["group"]["rows"], line.source_rows)
        check("every plan behind it is named",
              len(res["material_plannings"]) >= 1, True)
        check("a plan_hash is issued", len(res["plan_hash"]), 16)

        print()
        print("=== 7. A batch holding a different item is allowed, and says so ===")
        # This used to be refused outright, which made the commonest reason to open the
        # dialog impossible: before a transfer the planner may decide to send one
        # ISMB800 in place of four ISMB200. The requirement does not move; the steel
        # does. planned_item on the rows is what records it -- see
        # verify_cross_item_batch_reassign.
        other = frappe.db.sql("""
            SELECT b.name FROM `tabBatch` b
            WHERE b.item != %s AND b.disabled = 0 LIMIT 1
        """, line.item_code, as_dict=True)
        if other:
            res2 = bu.preview_consolidate_batch_update(
                line.mip, line.crow,
                frappe.as_json([{"batch_no": other[0].name, "pieces": 1}]),
            )
            check("not refused for the item alone",
                  any("but this line moves" in b for b in res2["blockers"]), False)
            check("it is stated as a warning instead",
                  any("is what will be sent" in frappe.utils.strip_html(str(w))
                      for w in (res2["warnings"] or [])), True)

    print()
    print("=== 8. A transferred line is refused whole ===")
    moved = frappe.db.sql("""
        SELECT c.parent AS mip, c.name AS crow, c.source_rows
        FROM `tabMaterial Issue Plan Consolidate Item` c
        WHERE c.transferred_qty > 0 LIMIT 1
    """, as_dict=True)
    if not moved:
        print("  (no transferred consolidate line on this site -- skipped)")
    else:
        res3 = bu.preview_consolidate_batch_update(moved[0].mip, moved[0].crow, "[]")
        check("refused", res3["ok"], False)
        # Since 14 Sep 2026 the whole plan is refused once any stock action exists on it,
        # which a transferred line always implies -- that refusal comes first.
        check("and names the stock action as the reason",
              any(("already been transferred" in b) or ("cannot be reassigned" in b)
                  for b in res3["blockers"]), True)

    print()
    print("=== 9. Nothing was written ===")
    # The whole of Phase 1 is read-only. A stray write here would be invisible until it
    # corrupted a plan, so assert it rather than assume it.
    check("no uncommitted changes pending", bool(frappe.db.transaction_writes), False)

    total, failed = len(checks), checks.count(False)
    print()
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, total))
    else:
        print("ALL %d CHECKS PASSED" % total)
