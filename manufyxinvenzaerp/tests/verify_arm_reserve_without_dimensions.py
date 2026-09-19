"""Reserve stock without dimensions, extended to the Exact Match table (Phase 2).

Material Mapping has had the dimension waiver for a long time. Exact Match has not,
and until now a batch reassigned onto an exact-match row from the Material Issue Plan
lost the fact that the new batch is a different size from the one the row was planned
against -- the checkbox on the dialog was sent and silently dropped.

The waiver does LESS here than it does on Material Mapping, and the difference is the
thing most likely to be got wrong later:

  Material Mapping   reserves batch_calc_qty, which the waiver rewrites to the row's
                     requirement, and derives batch_sec_qty from it.
  Exact Match        has no batch_calc_qty at all. reserve_exact_match_batches
                     reserves required_qty verbatim and does no dimension arithmetic
                     anywhere, so the Kg is ALREADY dimensionless. required_qty is
                     this row's share of a requirement that check_stock_availability
                     may have split across several batches -- rewriting it would
                     redraw the plan rather than change a batch.

So the waiver's only effect on an exact-match row is Sec Nos, and check 3 pins both
halves of that: the flagged row's count is re-derived, and required_qty is not touched.

Almost everything here runs against real documents held in memory and never saved, so
there is nothing to roll back. Check 8 asserts that rather than assuming it.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_arm_reserve_without_dimensions.run
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    _apply_batch_to_arm_row,
    _get_batch_dims,
    _sec_nos_for_weight,
    _sec_nos_for_weight_arm,
)

ARM = "Material Planning Available Raw Material"
RWD_GROUPS = ("Structurals", "Plates")

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _src(*parts):
    return open(frappe.get_app_path("manufyxinvenzaerp", *parts)).read()


def _arm_row(**kw):
    """A detached Exact Match row, so the write helpers can be exercised without a plan."""
    row = frappe.new_doc(ARM)
    for k, v in kw.items():
        row.set(k, v)
    return row


def run():
    print("=== 1. The field exists, is off, and changed nothing that already existed ===")
    meta = frappe.get_meta(ARM)
    df = meta.get_field("reserve_without_dimensions")
    check("the docfield is there", bool(df), True)
    check("as a Check", df.fieldtype if df else None, "Check")
    check("defaulting to off", (df.default if df else None), "0")
    # Deliberately NOT a grid column: Material Mapping's own waiver is row-detail
    # only, and this grid already declares 22 columns against Frappe's budget of 11,
    # so a new one would be dropped before it ever rendered.
    check("and not a grid column, like Material Mapping's", (df.in_list_view if df else 1), 0)
    # Rows written before the field existed (11 Sep 2026) must not have been flagged by
    # the migration. Rows made since may be -- by a user, or by Check stock without
    # dimensions -- so the live count alone says nothing about the migration.
    check("no row from before the field was flagged by the migration",
          frappe.db.count(ARM, {"reserve_without_dimensions": 1, "creation": ["<", "2026-09-11"]}), 0)

    print()
    print("=== 2. The Exact Match adapter and the shared formula give one answer ===")
    # _sec_nos_for_weight reads five batch_* fields. An exact-match row has none of
    # them -- one set of dimensions, no unit weight -- so the adapter shims it into
    # that shape rather than writing the Kg-per-piece formula out a second time.
    plate = _arm_row(item_code="X", parent_item_group="Plates",
                     length=500, width=250, thickness=5)
    shim = frappe._dict({"batch_parent_item_group": "Plates", "batch_length": 500,
                         "batch_width": 250, "batch_thickness": 5, "batch_unit_weight": 7.85})
    check("a plate agrees with the shared helper",
          _sec_nos_for_weight_arm(plate, 18, 7.85), _sec_nos_for_weight(shim, 18))
    check("and the count is fractional, not rounded",
          _sec_nos_for_weight_arm(plate, 18, 7.85), 3.669)

    beam = _arm_row(item_code="X", parent_item_group="Structurals", length=6000)
    check("a structural is length x unit weight",
          _sec_nos_for_weight_arm(beam, 100, 10.0), flt(100 / ((6000 / 1000) * 10.0), 3))

    bare = _arm_row(item_code="X", parent_item_group="Plates", length=0)
    check("no dimensions invents no piece count", _sec_nos_for_weight_arm(bare, 18, 7.85), 0.0)

    print()
    print("=== 3. _apply_rwd_fractional_nos: only flagged rows move, and only Sec Nos ===")
    mp_name = frappe.db.get_value(
        ARM, {"batch_no": ["!=", ""], "parent_item_group": ["in", RWD_GROUPS]}, "parent"
    )
    if not mp_name:
        print("  (no plan with a batched Structurals/Plates exact-match row -- skipped)")
    else:
        mp = frappe.get_doc("Material Planning", mp_name)
        before = {r.name: (flt(r.sec_qty, 3), flt(r.required_qty, 3))
                  for r in mp.available_raw_materials}

        # (a) Flags all off -- the state every existing plan is in today.
        mp._apply_rwd_fractional_nos()
        after = {r.name: (flt(r.sec_qty, 3), flt(r.required_qty, 3))
                 for r in mp.available_raw_materials}
        check("with every flag off, %s is untouched" % mp_name, after, before)

        # Every batched exact-match row on a working site tends to be reserved, and
        # the loop skips reserved rows -- so clear it IN MEMORY to exercise the
        # derivation, then put it back to prove the skip. The document is never
        # saved; check 8 holds that.
        target = next((r for r in mp.available_raw_materials
                       if r.batch_no and (r.parent_item_group or "") in RWD_GROUPS), None)
        if not target:
            print("  (no batched Structurals/Plates exact-match row here -- skipped)")
        else:
            target.is_reserved = 0
            uw = flt(frappe.db.get_value("Item", target.item_code, "custom_unit_weight"))
            expected = _sec_nos_for_weight_arm(target, target.required_qty, uw)
            reqd_before = flt(target.required_qty, 3)

            # (b) Flag one row on, in memory only. Sec Nos is deliberately corrupted
            # first: on a genuine exact match the derived figure equals the one already
            # there, so an assertion that only compared them would pass even if the
            # loop did nothing at all.
            target.sec_qty = 123.456
            target.reserve_without_dimensions = 1
            mp._apply_rwd_fractional_nos()
            if expected:
                check("the flagged row's Sec Nos is re-derived",
                      flt(target.sec_qty, 3), flt(expected, 3))
                check("which is the count it started with, this being an exact match",
                      flt(target.sec_qty, 3), before[target.name][0])
            else:
                check("a row with no per-piece weight keeps its Sec Nos",
                      flt(target.sec_qty, 3), 123.456)
            # The single most important assertion in this file.
            check("required_qty is NOT touched", flt(target.required_qty, 3), reqd_before)

            # (b2) The point of the waiver: a batch of a DIFFERENT size. Halve the
            # piece length and the same Kg must come back as twice the pieces.
            if expected and flt(target.length):
                target.length = flt(target.length) / 2
                target.sec_qty = 0
                mp._apply_rwd_fractional_nos()
                # Within a thousandth: both figures are already rounded to 3 dp, so
                # doubling one can differ from doubling the other by that much on a
                # very small row (0.0155 -> 0.031 against 0.015 -> 0.030).
                check("half-length pieces means twice as many of them",
                      abs(flt(target.sec_qty, 3) - flt(expected * 2, 3)) <= 0.0015, True)
                check("and still no change to required_qty",
                      flt(target.required_qty, 3), reqd_before)
                target.length = flt(target.length) * 2

            # (c) A reserved row is skipped -- the flag would appear to take and do nothing.
            target.is_reserved = 1
            target.sec_qty = 999.0
            mp._apply_rwd_fractional_nos()
            check("a reserved row is left alone", flt(target.sec_qty, 3), 999.0)
            target.is_reserved = 0

            # (d) Outside Structurals/Plates there is no piece to speak of.
            keep_group = target.parent_item_group
            target.parent_item_group = "Nuts and Bolts"
            target.sec_qty = 888.0
            mp._apply_rwd_fractional_nos()
            check("a Nuts and Bolts row is left alone", flt(target.sec_qty, 3), 888.0)
            target.parent_item_group = keep_group

            # (e) Broken dimension data must not zero a good allocation: that figure
            # goes onto the Stock Entry as custom_sec_qty.
            keep_len = target.length
            target.length = 0
            target.sec_qty = 777.0
            mp._apply_rwd_fractional_nos()
            check("a row with no per-piece weight keeps what it had",
                  flt(target.sec_qty, 3), 777.0)
            target.length = keep_len

    print()
    print("=== 4. _apply_batch_to_arm_row ===")
    dimmed = frappe.db.get_value("Batch", {"custom_length": [">", 0]}, ["name", "custom_length"], as_dict=True)
    if not dimmed:
        print("  (no Batch with dimensions on this site -- skipped)")
    else:
        b_len, b_wid, b_thk = _get_batch_dims(dimmed.name)

        # The waiver is recorded.
        r = _arm_row(item_code="X", batch_no="OLD", required_qty=120.0, length=1, width=2, thickness=3)
        _apply_batch_to_arm_row(r, dimmed.name, {}, None, 1, old_batch="OLD")
        check("the waiver is stored", r.reserve_without_dimensions, 1)
        check("required_qty survives a reassign", flt(r.required_qty, 3), 120.0)
        # An exact-match row carries ONE set of dimensions and _get_mp_reserved_batches
        # puts them straight onto the Stock Entry, so a row left on the old batch's
        # size would ship the new batch labelled wrong.
        check("a new batch brings its own dimensions", flt(r.length, 3), flt(b_len, 3))

        # A caller that supplies dimensions still wins.
        r2 = _arm_row(item_code="X", batch_no="OLD", required_qty=120.0, length=1)
        _apply_batch_to_arm_row(r2, dimmed.name, {"length": 4321}, None, 0, old_batch="OLD")
        check("supplied dimensions beat the batch's", flt(r2.length, 3), 4321.0)
        check("and the waiver stays off when not asked for", r2.reserve_without_dimensions, 0)

        # Same batch, nothing supplied: the pre-existing round trip must not move.
        r3 = _arm_row(item_code="X", batch_no=dimmed.name, required_qty=120.0,
                      length=1111, width=2222, thickness=33)
        _apply_batch_to_arm_row(r3, dimmed.name, {}, None, 0, old_batch=dimmed.name)
        check("a same-batch round trip leaves dimensions alone",
              (flt(r3.length), flt(r3.width), flt(r3.thickness)), (1111.0, 2222.0, 33.0))

        # Sec Nos is only written when the caller sends one.
        r4 = _arm_row(item_code="X", batch_no="OLD", sec_qty=9.0)
        _apply_batch_to_arm_row(r4, dimmed.name, {}, None, 1, old_batch="OLD")
        check("Sec Nos is left for the server to derive", flt(r4.sec_qty, 3), 9.0)
        _apply_batch_to_arm_row(r4, dimmed.name, {}, 6, 0, old_batch="OLD")
        check("an explicit Sec Nos is honoured", flt(r4.sec_qty, 3), 6.0)

    bare_batch = frappe.db.get_value(
        "Batch", {"custom_length": ["in", [0, None]], "custom_width": ["in", [0, None]]}, "name")
    if bare_batch:
        r5 = _arm_row(item_code="X", batch_no="OLD", length=555, width=44, thickness=3)
        _apply_batch_to_arm_row(r5, bare_batch, {}, None, 1, old_batch="OLD")
        check("a batch with no dimensions recorded does not zero the row's",
              (flt(r5.length), flt(r5.width), flt(r5.thickness)), (555.0, 44.0, 3.0))
    else:
        print("  (no dimensionless Batch on this site -- zeroing guard not exercised)")

    print()
    print("=== 5. The waiver survives the skip-into-Material-Mapping move ===")
    mp_src = _src("production_management", "doctype", "material_planning", "material_planning.py")
    check("_move_skipped_arm_to_mapping carries it",
          '"reserve_without_dimensions": row.get("reserve_without_dimensions") or 0,' in mp_src, True)

    print()
    print("=== 6. Cut Sheet figures on an exact-match row are unchanged ===")
    # Both tables now carry the flag, but only Material Mapping carries
    # batch_calc_qty, so the waiver branch of _sync_cut_sheet_calc still cannot be
    # reached from an exact-match row. Verified rather than assumed -- it is the one
    # place the new field lands in code written before it existed.
    probe = _arm_row(item_code="X", parent_item_group="Plates", cut_sheet=1,
                     reserve_without_dimensions=1, required_qty=100.0,
                     use_length=500, use_width=250, thickness=5, use_sec_qty=2)
    check("an exact-match row has no batch_calc_qty to trip the branch",
          flt(probe.get("batch_calc_qty")), 0.0)

    print()
    print("=== 7. The dialog sizes an exact-match row on its own share ===")
    js = _src("subcontracting_management", "doctype", "material_issue_plan", "material_issue_plan.js")
    check("the waiver preview splits by source table",
          'selected_row.source_table === "Material Planning Available Raw Material"\n\t\t\t\t\t? selected_row.qty' in js,
          True)

    print()
    print("=== 8. Nothing was written ===")
    check("no uncommitted changes pending", bool(frappe.db.transaction_writes), False)

    total, failed = len(checks), checks.count(False)
    print()
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, total))
    else:
        print("ALL %d CHECKS PASSED" % total)
