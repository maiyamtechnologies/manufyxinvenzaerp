"""A Material Planning row that has shipped stays settled — the reservation is gone.

Reserving a row locks its batch and the figures the reservation was measured from. But
transferring is precisely what RELEASES a reservation, so the moment material ships,
is_reserved goes back to 0 and the lock lets go -- of a row whose steel has already left
the building. The batch, the dimension waiver, the Sec Nos and the CNC routing all became
editable again on rows where none of them could still be true.

CNC Process has since been split off onto a NARROWER lock (22 Sep 2026, at the client's
request): a transfer settles it, a reservation does not, because a reservation is a
reversible paper hold that never touched the CNC warehouse in the first place. It is what
this file's "settled" rule was always about -- the shipped half of it -- so it is still
checked here, against _mp_row_transferred instead of _mp_row_settled. See
verify_mp_cnc_process_editable for the reasoning in full.

The same blind spot reached Check Mapping, which reads "batch selected but not reserved"
as an error to fix: MP-2026-00260 reported 32 issues the moment its first transfer went
out, every one of them settled work, each telling the user to go and reserve stock that
was already standing at the supplier.

So the plan row now records what it has shipped. transferred_qty accumulates as each
transfer releases the reservation it was holding, fully_transferred is set once that
reaches what the row needed, and cancelling an entry unwinds both. A row is settled when
it is reserved OR has shipped anything at all -- partial counts, because the batch is
decided from the first kilo that moves.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_transferred_row_locked.run
"""

import inspect
import json
import os

import frappe
from frappe.utils import flt

checks = []

MAPPING = "Material Planning Material Mapping"
EXACT = "Material Planning Available Raw Material"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _js():
    return open(os.path.join(
        frappe.get_app_path("manufyxinvenzaerp"), "production_management",
        "doctype", "material_planning", "material_planning.js")).read()


def run():
    from manufyxinvenzaerp.production_management import stock_entry as se_mod
    from manufyxinvenzaerp.production_management.doctype.material_planning import (
        material_planning as mp_mod,
    )

    print("=== both tables carry the two fields, and neither is typed into ===")
    for dt in (MAPPING, EXACT):
        meta = frappe.get_meta(dt)
        for fieldname, fieldtype in (("transferred_qty", "Float"), ("fully_transferred", "Check")):
            df = meta.get_field(fieldname)
            check("%s.%s exists" % (dt.split()[-2] + " " + dt.split()[-1], fieldname), bool(df), True)
            if df:
                check("   ...is %s and read-only" % fieldtype,
                      (df.fieldtype, df.read_only), (fieldtype, 1))

    print()
    print("=== ...and Material Mapping's field_order lets them render ===")
    # That table's order is pinned by a Property Setter which overrides the doctype's
    # own. A field missing from it never appears on the form at all.
    order = frappe.db.get_value(
        "Property Setter",
        {"doc_type": MAPPING, "property": "field_order"}, "value")
    if not order:
        print("  SKIP no field_order Property Setter on this site")
    else:
        names = json.loads(order)
        check("transferred_qty is in the pinned order", "transferred_qty" in names, True)
        check("fully_transferred is in the pinned order", "fully_transferred" in names, True)

    print()
    print("=== the server keeps them as transfers go out and come back ===")
    rel = inspect.getsource(se_mod._release_rows_by_qty)
    check("a release adds what the row gave up",
          'flt(flt(r.get("transferred_qty")) + take, 3)' in rel, True)
    check("...and flags the row once it covers the requirement",
          '"fully_transferred": 1 if needed and gone >=' in rel, True)
    check("the requirement field is passed in, not guessed",
          "def _release_rows_by_qty(child_dt, rows, moved_qty, se_is_cnc_transfer, qty_field)" in rel, True)

    res = inspect.getsource(se_mod._restore_rows_by_qty)
    check("a cancel takes it back off",
          'flt(max(flt(r.get("transferred_qty")) - give, 0.0), 3)' in res, True)
    check("...and clears the flag", '"fully_transferred": 0' in res, True)

    caller = inspect.getsource(se_mod._release_material_planning_reservations)
    check("each table's requirement field is named", '"required_qty"' in caller and '"qty"' in caller, True)

    print()
    print("=== the form locks a settled row, shipped or reserved ===")
    js = _js()
    check("settled means reserved OR shipped",
          "row.is_reserved || row.fully_transferred || flt(row.transferred_qty) > 0" in js, True)
    check("Material Mapping locks the batch and its figures",
          '"batch", "reserve_without_dimensions", "batch_sec_qty",' in js, True)
    check("Exact Match locks its own two",
          '"reserve_without_dimensions", "skip_auto_suggest_batch",' in js, True)
    # CNC Process used to sit in those two lists, locked by _mp_row_settled. A
    # reservation does not settle a ROUTE -- it is reversible and holds nothing in the
    # CNC warehouse -- so it is locked by the transfer alone now. The shipped half of
    # this file's rule still applies to it, which is what these three check.
    check("CNC Process is locked by the transfer alone",
          '"cnc_process",\n];' in js.replace("\t", ""), True)
    check("...on its own list", "_MP_TRANSFER_LOCKED_FIELDS" in js, True)
    check("...driven by a predicate that ignores is_reserved",
          "return !!(row.fully_transferred || flt(row.transferred_qty) > 0);" in js, True)
    check("...and no longer by the reservation lock",
          '"batch_sec_qty", "cnc_process"' in js or '"reserve_without_dimensions", "cnc_process"' in js,
          False)
    check("both grids are swept, not just the expanded row",
          'function _mp_lock_settled_rows(frm)' in js, True)
    check("...and it runs on refresh", "_mp_lock_settled_rows(frm);" in js, True)
    check("the expanded Material Mapping row uses the shared list",
          "_MP_LOCKED_MAPPING_FIELDS.forEach" in js, True)
    check("the expanded Exact Match row does too",
          "_MP_LOCKED_EXACT_FIELDS.forEach" in js, True)
    check("no lock still keys on is_reserved alone",
          "df.read_only = row.is_reserved ? 1 : 0;" in js, False)

    print()
    print("=== the plan-wide waiver is locked once anything is settled ===")
    check("check stock without dimensions follows it",
          'frm.set_df_property("check_stock_without_dimensions", "read_only", any_settled ? 1 : 0);' in js, True)

    print()
    print("=== Check Mapping stops calling shipped rows unreserved ===")
    issues_src = inspect.getsource(mp_mod._collect_batch_mapping_issues)
    check("the Material Mapping check skips them",
          "if r.batch and not r.is_reserved and not _row_has_shipped(r):" in issues_src, True)
    check("the Exact Match check skips them",
          "if r.batch_no and not r.is_reserved and not _row_has_shipped(r):" in issues_src, True)
    shipped = inspect.getsource(mp_mod._row_has_shipped)
    check("partly shipped counts as shipped",
          'flt(row.get("transferred_qty")) > 0.0005' in shipped, True)

    print()
    print("=== a fully transferred line is not offered in the popup ===")
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as mipt
    for fn in (mipt.get_mip_pending_items, mipt.get_mip_cnc_pending_items):
        src = inspect.getsource(fn)
        check("%s drops rows with nothing left" % fn.__name__,
              "pending_qty <= 0" in src or "if pending <= 0:" in src, True)

    print()
    print("=== live: every plan row the MIP has shipped is marked ===")
    mip_rows = frappe.get_all(
        "Material Issue Plan Raw Material", filters={"transferred_qty": [">", 0]},
        fields=["source_table", "source_row", "transferred_qty"])
    qty_field = {MAPPING: "qty", EXACT: "required_qty"}
    seen = 0
    wrong = []
    for r in mip_rows:
        if r.source_table not in qty_field or not r.source_row:
            continue
        row = frappe.db.get_value(
            r.source_table, r.source_row,
            ["transferred_qty", "fully_transferred", qty_field[r.source_table]], as_dict=True)
        if not row:
            continue
        seen += 1
        need = flt(row.get(qty_field[r.source_table]), 3)
        want_full = 1 if need and flt(row.transferred_qty) >= flt(need - 0.0005, 3) else 0
        if flt(row.transferred_qty) <= 0 or row.fully_transferred != want_full:
            wrong.append(r.source_row)
    if not seen:
        print("  SKIP no transferred Material Issue Plan rows on this site")
    else:
        check("%d shipped plan row(s), all consistent" % seen, wrong, [])

    print()
    print("=== live: Check Mapping no longer reports them ===")
    mp_name = frappe.db.get_value(
        "Material Issue Plan Raw Material", {"transferred_qty": [">", 0]}, "material_planning")
    if not mp_name:
        print("  SKIP nothing transferred on this site")
    else:
        mp = frappe.get_doc("Material Planning", mp_name)
        issues = mp_mod._collect_batch_mapping_issues(mp)
        noisy = [i for i in issues if "selected but not reserved" in i]
        would_have = sum(
            1 for r in (mp.material_mapping or []) if r.batch and not r.is_reserved
        ) + sum(
            1 for r in (mp.available_raw_materials or []) if r.batch_no and not r.is_reserved
        )
        shipped_rows = would_have - len(noisy)
        print("  %s: %d row(s) read as unreserved, %d of them shipped" % (mp_name, would_have, shipped_rows))
        check("no shipped row is reported",
              all(not mp_mod._row_has_shipped(r)
                  for r in list(mp.material_mapping or []) + list(mp.available_raw_materials or [])
                  if (r.get("batch") or r.get("batch_no")) and not r.is_reserved
                  and mp_mod._row_has_shipped(r) and len(noisy) == would_have), True)
        check("the shipped ones were filtered out", shipped_rows > 0, True)

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
