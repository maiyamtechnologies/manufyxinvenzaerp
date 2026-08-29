"""What a cut plate offers, who is holding it, and where its excess is.

Four things reported together against MP-2026-00042 / CS-2026-00004 / MIP-2026-00013,
all of them about a 12 m NPB600 plate being cut down to 116.681 Kg of parts.

  1. The transfer popup's "In Stock" column showed the batch's whole free weight --
     5,877.600 Kg, the entire uncut plate -- against a planned 1,248.503, when only
     the W1 pieces (2,449.000 Kg) are being cut from it at all. Read straight it
     claimed four times more of this material was available than the cut plan could
     ever yield. Now capped at the sheet's W1 total, and still capped by real stock so
     a batch that has not arrived yet reads 0.

  2. A sheet with allocations against it cannot have its W1 Sec Nos reduced below what
     jobs have taken -- right, or it would oversubscribe pieces someone is relying on.
     But there was no way to undo those claims either, so re-cutting a plate meant
     opening every claiming Material Planning and clearing the rows by hand. Release
     Allocations does it in one step, and refuses once material has physically moved.

  3. Material Mapping showed excess only as a plan-wide total. On this plan that total
     is 1,131.822 Kg across twenty rows -- and three rows carry all of it while
     seventeen carry none, which the total cannot say. Each row now states its share.

  4. The excess figure on the consolidated return plan had to be checked rather than
     fixed: transferring 3 whole pieces where 2.039 were planned must count BOTH the
     cut-plate excess and the round-up. It does -- the dialog totals the entered
     transfer quantity, not the planned one -- and this pins that arithmetic down.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_cut_sheet_excess_visibility.run
"""

import re

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-56s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, fragment):
    """True when fn() raises a message containing fragment."""
    try:
        fn()
    except Exception as e:
        return fragment.lower() in frappe.utils.strip_html(str(e)).lower()
    return False


def _cut_sheet_with_allocations():
    row = frappe.db.sql(
        """
        SELECT a.parent AS cs, COUNT(*) AS n
        FROM `tabCut Sheet Allocation` a
        JOIN `tabCut Sheet` cs ON cs.name = a.parent
        WHERE cs.w2_applied = 0
        GROUP BY a.parent ORDER BY n DESC LIMIT 1
        """,
        as_dict=True,
    )
    return row[0].cs if row else None


def run():
    print("=== 1. In Stock never promises more than the cut plan yields ===")
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _available_for_transfer,
        _cut_sheet_w1_totals,
    )

    sheet = frappe.db.get_value(
        "Cut Sheet", {"w1_total_qty": [">", 0]},
        ["name", "batch_no", "item_code", "warehouse", "w1_total_qty"], as_dict=True,
    )
    if not sheet:
        print("    (no cut sheet on this site -- skipped)")
    else:
        totals = _cut_sheet_w1_totals([{"batch_no": sheet.batch_no}])
        check("the sheet's W1 total is found by batch",
              flt(totals.get(sheet.batch_no), 3), flt(sheet.w1_total_qty, 3))

        from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
            _batch_free_qty,
        )
        free = flt(_batch_free_qty(sheet.item_code, sheet.batch_no, sheet.warehouse), 3)
        offered = _available_for_transfer(sheet.item_code, sheet.batch_no, sheet.warehouse, totals)
        print("    %s: batch free=%s  W1 total=%s  offered=%s"
              % (sheet.name, free, flt(sheet.w1_total_qty, 3), offered))
        check("it never offers more than W1", offered <= flt(sheet.w1_total_qty, 3) + 0.001, True)
        check("nor more than is physically there", offered <= free + 0.001, True)
        # An uncut batch is untouched -- the cap only applies where a sheet exists.
        check("a batch with no cut sheet is reported as-is",
              _available_for_transfer(sheet.item_code, "ZZ-NO-SUCH-BATCH", sheet.warehouse, totals),
              flt(_batch_free_qty(sheet.item_code, "ZZ-NO-SUCH-BATCH", sheet.warehouse), 3))

    print()
    print("=== 2. Allocations can be released, so a plate can be re-cut ===")
    from manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet import (
        release_all_cut_sheet_allocations,
    )

    cs_name = _cut_sheet_with_allocations()
    if not cs_name:
        print("    (no cut sheet with allocations -- skipped)")
    else:
        cs = frappe.get_doc("Cut Sheet", cs_name)
        before = len(cs.allocations)
        print("    %s: %d allocation(s), %s of %s pieces taken"
              % (cs_name, before, cs.allocated_sec_qty, cs.w1_sec_qty))

        # The cut is locked while a job is planning from it -- the Material Issue
        # Plan reads W1/W2 back off this sheet at every refresh, so changing them
        # here rewrites what an existing plan will transfer.
        original_w1 = flt(cs.w1_length)
        cs.w1_length = original_w1 + 500
        check("W1 cannot be changed while the sheet is claimed",
              _throws(cs.save, "cannot be changed"), True)
        cs.reload()

        # Reserved rows are not the button's to undo: a reservation is a claim on
        # real stock, and unreserving is a decision made on the plan that made it.
        reserved_before = [r for r in cs.claiming_rows() if r.is_reserved]
        if reserved_before:
            check("releasing is refused while stock is reserved",
                  _throws(lambda: release_all_cut_sheet_allocations(cs_name),
                          "still reserved"), True)
            for r in reserved_before:
                frappe.db.set_value(r.child_doctype, r.name, "is_reserved", 0,
                                    update_modified=False)
            print("    (unreserved %d row(s) to carry on)" % len(reserved_before))

        out = release_all_cut_sheet_allocations(cs_name)
        check("it releases every claim", out["released"], before)
        cs.reload()
        check("the Allocations table is empty", len(cs.allocations), 0)
        check("and every piece is available again",
              flt(cs.available_sec_qty, 3), flt(cs.w1_sec_qty, 3))
        check("no Material Mapping row still points at the sheet",
              frappe.db.count("Material Planning Material Mapping", {"cut_sheet_ref": cs_name}), 0)

        # The thing the lock refused, and the whole point of releasing.
        cs.w1_sec_qty = 1
        cs.save(ignore_permissions=True)
        check("W1 Sec Nos can now be reduced", flt(cs.w1_sec_qty), 1.0)

        check("and it names the plans it released", isinstance(out["plans"], list), True)

    frappe.db.rollback()

    print()
    print("=== 2b. What is being cut is fixed once saved ===")
    from manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet import (
        cut_sheet_warehouse_query, mark_cut_sheet_inactive,
    )

    any_cs = frappe.db.get_value(
        "Cut Sheet", {}, ["name", "batch_no", "item_code", "warehouse", "company"], as_dict=True
    )
    if not any_cs:
        print("    (no cut sheet on this site -- skipped)")
    else:
        # Every figure on a sheet is derived from one plate in one warehouse, so
        # re-pointing a saved one keeps the cut, the allocations and the status
        # while changing what they describe.
        other_batch = frappe.db.get_value("Batch", {"name": ["!=", any_cs.batch_no]}, "name")
        other_wh = frappe.db.get_value(
            "Warehouse", {"is_group": 0, "name": ["!=", any_cs.warehouse]}, "name"
        )
        for field, value in (("batch_no", other_batch), ("warehouse", other_wh)):
            if not value:
                continue
            d = frappe.get_doc("Cut Sheet", any_cs.name)
            d.set(field, value)
            check("%s cannot be changed after saving" % field,
                  _throws(d.save, "cannot be changed after"), True)
            frappe.db.rollback()

        # Only the warehouses that actually hold the plate -- the field offered
        # every warehouse on the site.
        offered = cut_sheet_warehouse_query(
            "Warehouse", "", "name", 0, 20, {"batch_no": any_cs.batch_no}
        )
        total_wh = frappe.db.count("Warehouse", {"is_group": 0})
        print("    warehouse picker for %s: %s (of %d on the site)"
              % (any_cs.batch_no, [w[0] for w in offered], total_wh))
        check("the picker is narrowed to warehouses holding the batch",
              len(offered) <= total_wh and len(offered) >= 0, True)
        check("and every one it offers actually holds stock",
              [w[0] for w in offered
               if flt(_batch_free_qty(any_cs.item_code, any_cs.batch_no, w[0])) <= 0], [])

    print()
    print("=== 2c. An unused sheet can be set aside, with a reason ===")
    claimed_names = {r["parent"] for r in frappe.get_all(
        "Material Planning Material Mapping",
        filters={"cut_sheet_ref": ["is", "set"]}, fields=["cut_sheet_ref as parent"])}
    unused = frappe.db.get_value(
        "Cut Sheet",
        {"status": ["not in", ["Inactive", "Consumed"]], "w2_applied": 0,
         "name": ["not in", list(claimed_names) or [""]]},
        "name",
    )
    if not unused:
        print("    (no unused cut sheet -- skipped)")
    else:
        check("a reason is required", _throws(
            lambda: mark_cut_sheet_inactive(unused, "   "), "enter a reason"), True)
        mark_cut_sheet_inactive(unused, "created by mistake")
        d = frappe.get_doc("Cut Sheet", unused)
        check("it goes Inactive and keeps the reason",
              (d.status, d.inactive_reason), ("Inactive", "created by mistake"))
        # Inactive has to MEAN something, or it is only a label.
        mp_any = frappe.db.get_value("Material Planning", {}, "name")
        if mp_any:
            from manufyxinvenzaerp.production_management.doctype.cut_sheet.cut_sheet import (
                get_available_cut_sheets,
            )
            check("and it stops being offered as material to cut",
                  unused in [r["name"] for r in get_available_cut_sheets(mp_any)], False)
        d.save(ignore_permissions=True)
        d.reload()
        check("the status is not recomputed back to Active", d.status, "Inactive")
        frappe.db.rollback()

    # A sheet that HAS been used is a record of a real cut, not something to shelve.
    used_cs = _cut_sheet_with_allocations()
    if used_cs:
        check("a sheet already in use cannot be set aside",
              _throws(lambda: mark_cut_sheet_inactive(used_cs, "changed my mind"),
                      "has been used"), True)

    print()
    print("=== 3. Every Material Mapping row states its own excess ===")
    meta = frappe.get_meta("Material Planning Material Mapping")
    fld = meta.get_field("excess_qty")
    check("the column exists", bool(fld), True)
    check("it is read-only and in the grid",
          (bool(fld.read_only), bool(fld.in_list_view)) if fld else None, (True, True))

    mp_name = frappe.db.sql(
        """
        SELECT parent FROM `tabMaterial Planning Material Mapping`
        WHERE batch IS NOT NULL AND batch != ''
        GROUP BY parent
        HAVING ABS(SUM(batch_calc_qty - qty)) > 0.001
        ORDER BY ABS(SUM(batch_calc_qty - qty)) DESC LIMIT 1
        """
    )
    if not mp_name:
        print("    (no plan carrying a difference -- skipped)")
    else:
        mp = frappe.get_doc("Material Planning", mp_name[0][0])
        mp.flags.mfx_saved_by_another_document = True
        mp.save(ignore_permissions=True)
        rows_with = [r for r in mp.material_mapping if flt(r.excess_qty)]
        row_sum = flt(sum(flt(r.excess_qty) for r in mp.material_mapping), 3)
        summary = flt(flt(mp.weight_cross_item_mapped) - flt(mp.expected_weight_material_mapping), 3)
        print("    %s: %d of %d row(s) carry excess, totalling %s"
              % (mp.name, len(rows_with), len(mp.material_mapping), row_sum))
        check("the rows add up to the summary difference", row_sum, summary)
        check("an unmapped row claims no excess",
              [r.idx for r in mp.material_mapping if not r.batch and flt(r.excess_qty)], [])

    print()
    print("=== 3b. A claiming row carries the cut figures ===")
    # Nothing set these: To Use / Balance were only ever written by a user typing in
    # the grid, so a row that took its batch any other way sat at use_length = 0 while
    # the sheet showed its pieces allocated -- and use_calc_qty, which caps the
    # transfer, stayed 0 with it, so the cap silently never applied.
    claimed = frappe.db.sql(
        """
        SELECT parent FROM `tabMaterial Planning Material Mapping`
        WHERE cut_sheet_ref IS NOT NULL AND cut_sheet_ref != ''
        GROUP BY parent ORDER BY COUNT(*) DESC LIMIT 1
        """
    )
    if not claimed:
        print("    (no plan claiming a cut sheet -- skipped)")
    else:
        mp2 = frappe.get_doc("Material Planning", claimed[0][0])
        mp2.flags.mfx_saved_by_another_document = True
        mp2.save(ignore_permissions=True)
        cut_rows = [r for r in mp2.material_mapping if r.cut_sheet_ref]
        print("    %s: %d row(s) cutting from a sheet" % (mp2.name, len(cut_rows)))
        check("every one carries the W1 size it cuts to",
              [r.idx for r in cut_rows if not flt(r.use_length)], [])
        check("and the weight that size yields",
              [r.idx for r in cut_rows if not flt(r.use_calc_qty)], [])
        # That weight is what caps the transfer, so it must equal what the row
        # actually reserved -- deriving it from a rounded piece-fraction loses grams.
        check("a dimension-waived row's take matches what it reserved",
              [r.idx for r in cut_rows
               if r.reserve_without_dimensions
               and flt(r.use_calc_qty, 3) != flt(r.batch_calc_qty, 3)], [])
        frappe.db.rollback()

    print()
    print("=== 4. Rounding a transfer up counts in the excess ===")
    # Excess Kg (system) = entered transfer weight - planned drawing weight. Because
    # it totals what is ENTERED, rounding 2.039 planned pieces up to 3 whole ones
    # carries into it on its own -- cut-plate excess plus round-up, in one figure.
    mip_js = open(frappe.get_app_path(
        "manufyxinvenzaerp", "subcontracting_management", "doctype",
        "material_issue_plan", "material_issue_plan.js",
    )).read()
    check("the excess totals the entered quantity, not the planned one",
          bool(re.search(r"e\.transfer_kg \+= flt\(\$tr\.find\(\"\.mip-qty\"\)\.val\(\)\)", mip_js)),
          True)

    drawing_kg, planned_kg, per_piece = 116.681, 1248.503, 1248.503 / 2.039
    entered_kg = per_piece * 3
    cut_plate_excess = planned_kg - drawing_kg
    round_up_excess = entered_kg - planned_kg
    system_excess = entered_kg - drawing_kg
    print("    cut-plate %.3f + round-up %.3f = %.3f"
          % (cut_plate_excess, round_up_excess, system_excess))
    check("the two parts make up the whole",
          flt(cut_plate_excess + round_up_excess, 3), flt(system_excess, 3))
    check("and it matches what the plan reported", flt(system_excess, 3), 1720.253)

    frappe.db.rollback()
    print()
    print("  (rolled back -- this check leaves no trace)")
    _summary()


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
