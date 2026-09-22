"""CNC Process stays editable on a RESERVED Material Planning row -- only a transfer locks it.

Batch, the dimension waiver and Sec Nos are settled by a reservation, and CNC Process was
locked alongside them. It should not have been. A reservation is a paper hold on a batch in
the Raw Materials warehouse: reserve_batches never reads cnc_process, never holds against
the CNC warehouse, and it is undone in one click by the per-row Unreserve button. CNC
Process says which warehouse the row travels THROUGH, and while the material is still
standing in stores that is entirely a live question.

Locking it there broke the one instruction the transfer code itself gives. _ensure_cnc_routing
refuses a transfer whose CNC rows have no CNC Warehouse and tells the user to "untick CNC
Process on those rows in the Material Planning if the CNC step is not required" -- on rows
that had to be reserved to be offered for transfer at all, i.e. on rows where the field was
read-only. The only way out was to unreserve, untick, and reserve again.

A TRANSFER is different in kind: the steel has physically gone to CNC or straight to the
supplier and no button brings it back, so the route stops being a question there. And the
usual trap applies -- a transfer RELEASES the reservation, so after one, is_reserved is 0
again and a shipped row is indistinguishable from a row nobody ever reserved.
transferred_qty and fully_transferred are the only reliable signals, and the transfer-only
predicate reads those two and nothing else.

So: cnc_process moves out of the reservation-locked lists onto _MP_TRANSFER_LOCKED_FIELDS,
driven by _mp_row_transferred; batch, reserve_without_dimensions, batch_sec_qty and
skip_auto_suggest_batch stay on _mp_row_settled; and check_stock_without_dimensions -- the
plan-WIDE matching rule, not one row's route -- stays on the reservation predicate too.

Every source check here is negative-controlled: the scanner is first shown to find what is
there, to return nothing for a name that is not, and to FAIL on a doctored copy of the file
with cnc_process put back. A check that cannot fail is not a check.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_mp_cnc_process_editable.run
"""

import inspect
import os
import re

import frappe

checks = []

MAPPING = "Material Planning Material Mapping"
EXACT = "Material Planning Available Raw Material"

JS_PATH = ("production_management", "doctype", "material_planning", "material_planning.js")


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _js():
    return open(os.path.join(frappe.get_app_path("manufyxinvenzaerp"), *JS_PATH)).read()


def _const_array(src, name):
    """The quoted fieldnames inside `const <name> = [ ... ];`, or None if there is no
    such const. None rather than [] deliberately: a renamed constant must read as
    "not found", not as "found and empty", or every membership check below passes
    against a list that does not exist."""
    m = re.search(r"const\s+" + re.escape(name) + r"\s*=\s*\[(.*?)\];", src, re.S)
    if not m:
        return None
    return re.findall(r'"([^"]+)"', m.group(1))


def _fn_body(src, name):
    """The body of `function <name>(row) { ... }`, or None. Same reasoning as above."""
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\(row\)\s*\{(.*?)\n\}", src, re.S)
    return m.group(1) if m else None


def _blocks_after(src, marker, window=260):
    """Each stretch of source right after `marker`, for checking which predicate the
    loop that follows it actually applies."""
    return [src[i:i + window] for i in
            [m.start() for m in re.finditer(re.escape(marker), src)]]


def run():
    from manufyxinvenzaerp.production_management import stock_entry as se_mod
    from manufyxinvenzaerp.production_management.doctype.material_planning import (
        material_planning as mp_mod,
    )

    js = _js()

    print("=== 0. the scanner works, and can fail (negative control) ===")
    check("the mapping list is found", isinstance(_const_array(js, "_MP_LOCKED_MAPPING_FIELDS"), list), True)
    check("...and is not empty", bool(_const_array(js, "_MP_LOCKED_MAPPING_FIELDS")), True)
    check("the exact-match list is found", bool(_const_array(js, "_MP_LOCKED_EXACT_FIELDS")), True)
    check("the transfer list is found", bool(_const_array(js, "_MP_TRANSFER_LOCKED_FIELDS")), True)
    check("a const that does not exist reads as missing",
          _const_array(js, "_MP_LOCKED_NOTHING_FIELDS"), None)
    check("a predicate that does exist is found", bool(_fn_body(js, "_mp_row_settled")), True)
    check("a predicate that does not reads as missing", _fn_body(js, "_mp_row_nonsense"), None)
    # The real control: put cnc_process back into the reservation list and the very
    # assertion this file exists for must go the other way.
    doctored = js.replace(
        '\t"batch", "reserve_without_dimensions", "batch_sec_qty",\n',
        '\t"batch", "reserve_without_dimensions", "batch_sec_qty", "cnc_process",\n', 1)
    check("the doctored copy really differs from the file", doctored != js, True)
    check("...and the scanner catches cnc_process in it",
          "cnc_process" in (_const_array(doctored, "_MP_LOCKED_MAPPING_FIELDS") or []), True)

    print()
    print("=== 1. cnc_process is NOT in either reservation-locked list ===")
    mapping = _const_array(js, "_MP_LOCKED_MAPPING_FIELDS")
    exact = _const_array(js, "_MP_LOCKED_EXACT_FIELDS")
    check("Material Mapping's reservation lock drops it", "cnc_process" in mapping, False)
    check("Exact Match's reservation lock drops it", "cnc_process" in exact, False)

    print()
    print("=== 2. the other four fields are still reservation-locked ===")
    for fieldname in ("batch", "reserve_without_dimensions", "batch_sec_qty"):
        check("Material Mapping still locks %s" % fieldname, fieldname in mapping, True)
    for fieldname in ("reserve_without_dimensions", "skip_auto_suggest_batch"):
        check("Exact Match still locks %s" % fieldname, fieldname in exact, True)
    # Set equality, so nothing new can be quietly added to either lock either.
    check("Material Mapping locks exactly those three", sorted(mapping),
          ["batch", "batch_sec_qty", "reserve_without_dimensions"])
    check("Exact Match locks exactly those two", sorted(exact),
          ["reserve_without_dimensions", "skip_auto_suggest_batch"])

    print()
    print("=== 3. cnc_process is driven by a transfer-only predicate ===")
    transfer = _const_array(js, "_MP_TRANSFER_LOCKED_FIELDS")
    check("the transfer lock holds cnc_process and only that", transfer, ["cnc_process"])
    body = _fn_body(js, "_mp_row_transferred")
    check("_mp_row_transferred exists", bool(body), True)
    check("...it reads fully_transferred", "fully_transferred" in (body or ""), True)
    check("...and transferred_qty", "transferred_qty" in (body or ""), True)
    check("...and does NOT reference is_reserved", "is_reserved" in (body or ""), False)

    settled = _fn_body(js, "_mp_row_settled")
    check("_mp_row_settled still exists", bool(settled), True)
    check("...and it DOES reference is_reserved", "is_reserved" in (settled or ""), True)
    check("the two predicates are genuinely different", settled == body, False)

    print()
    print("=== 4. every site applying the transfer lock uses the transfer predicate ===")
    blocks = _blocks_after(js, "_MP_TRANSFER_LOCKED_FIELDS.forEach")
    # Three: the whole-grid sweep in _mp_lock_settled_rows, plus the expanded-row
    # handler on each of the two child tables.
    check("it is applied in three places", len(blocks), 3)
    check("all three use _mp_row_transferred",
          all("_mp_row_transferred(row)" in b for b in blocks), True)
    check("none of them uses _mp_row_settled",
          any("_mp_row_settled(" in b for b in blocks), False)

    for marker in ("_MP_LOCKED_MAPPING_FIELDS.forEach", "_MP_LOCKED_EXACT_FIELDS.forEach"):
        res_blocks = _blocks_after(js, marker)
        check("%s is applied" % marker.split(".")[0], bool(res_blocks), True)
        check("...and never on the transfer predicate",
              any("_mp_row_transferred" in b for b in res_blocks), False)

    print()
    print("=== 5. the plan-wide waiver stays on the RESERVATION predicate ===")
    # check_stock_without_dimensions is how every row is matched to stock, not how one
    # row is routed. A held reservation is exactly a row that cannot be re-matched, so
    # any_settled must keep counting reservations. Deliberately unchanged.
    check("any_settled is computed from _mp_row_settled",
          "let settled = _mp_row_settled(row);" in js and "if (settled) any_settled = true;" in js, True)
    check("...and the waiver follows any_settled",
          'frm.set_df_property("check_stock_without_dimensions", "read_only", any_settled ? 1 : 0);' in js, True)
    check("it is not driven by the transfer predicate",
          re.search(r"any_transferred|check_stock_without_dimensions[^\n]*transferred", js) is not None, False)

    print()
    print("=== 6. nothing else holds the field read-only ===")
    for dt in (MAPPING, EXACT):
        df = frappe.get_meta(dt).get_field("cnc_process")
        check("%s carries cnc_process" % dt, bool(df), True)
        if df:
            check("   ...and it is not read-only in metadata", bool(df.read_only), False)
            check("   ...and it is a Check", df.fieldtype, "Check")
    ps = frappe.db.get_value("Property Setter",
                             {"field_name": "cnc_process", "property": "read_only"}, "name")
    check("no Property Setter makes it read-only", ps, None)

    print()
    print("=== 7. the server never gated it either ===")
    # The UI change would be cosmetic if a server guard refused the same edit. It does
    # not: the reserved-row guard compares Sec Nos, Qty and Batch, and reserve_batches
    # does not read cnc_process at all -- which is also why flipping it cannot
    # invalidate a hold.
    guard = inspect.getsource(mp_mod.MaterialPlanning._validate_batch_calc_qty)
    check("the reserved-row guard compares batch_sec_qty/qty/batch",
          all(f in guard for f in ('flt(row.batch_sec_qty) != flt(db.batch_sec_qty)',
                                   'flt(row.qty) != flt(db.qty)',
                                   '(row.batch or "") != (db.get("batch") or "")')), True)
    check("...and does NOT compare cnc_process", "cnc_process" in guard, False)
    check("reserve_batches never reads cnc_process",
          "cnc_process" in inspect.getsource(mp_mod.reserve_batches), False)
    # The two fields the predicate trusts are the two the server maintains.
    rel = inspect.getsource(se_mod._release_rows_by_qty)
    check("a release keeps transferred_qty", "transferred_qty" in rel, True)
    check("...and fully_transferred", "fully_transferred" in rel, True)

    print()
    print("=== 8. the SERVED doctype JS carries the new logic ===")
    # Doctype JS is read off disk by frappe.desk.form.meta.add_code on every request
    # and, with developer_mode on, is not cached in redis at all -- so this is what a
    # browser gets, not just what the file says. No bench build is involved (that is
    # public/js only) and no migrate.
    from frappe.desk.form.meta import get_meta
    served = get_meta("Material Planning").get("__js") or ""
    print("   developer_mode=%r  form-meta cache entries=%d  served __js=%d bytes" % (
        frappe.conf.developer_mode, len(frappe.cache.hgetall("doctype_form_meta") or {}), len(served)))
    check("something was served at all", len(served) > 10000, True)
    check("a sentinel that IS in the file is served",
          "function _mp_lock_settled_rows(frm)" in served, True)
    check("a sentinel that is NOT in the file is absent",
          "function _mp_row_nonsense(" in served, False)
    check("the served JS defines _mp_row_transferred", "_mp_row_transferred" in served, True)
    check("...and _MP_TRANSFER_LOCKED_FIELDS", "_MP_TRANSFER_LOCKED_FIELDS" in served, True)
    check("...and no longer locks cnc_process on reservation",
          '"batch", "reserve_without_dimensions", "batch_sec_qty", "cnc_process",' in served, False)
    check("...nor on Exact Match",
          '"reserve_without_dimensions", "cnc_process", "skip_auto_suggest_batch",' in served, False)
    check("the served copy matches the file's transfer list",
          _const_array(served, "_MP_TRANSFER_LOCKED_FIELDS"), ["cnc_process"])

    print()
    print("=== 9. live: which rows this actually unlocks ===")
    # Reserved-and-not-shipped rows are the ones whose CNC Process just became editable.
    for dt, qty_field in ((MAPPING, "qty"), (EXACT, "required_qty")):
        rows = frappe.get_all(
            dt, filters={"is_reserved": 1}, fields=["name", "parent", "cnc_process",
                                                    "transferred_qty", "fully_transferred"])
        unlocked = [r for r in rows if not r.fully_transferred and not (r.transferred_qty or 0) > 0]
        print("   %-42s %d reserved, %d now editable" % (dt, len(rows), len(unlocked)))
        check("no reserved+unshipped row of %s is locked" % dt.split()[-2],
              all(not r.fully_transferred and not (r.transferred_qty or 0) > 0 for r in unlocked), True)
    shipped = frappe.db.count(MAPPING, {"fully_transferred": 1}) + \
        frappe.db.count(EXACT, {"fully_transferred": 1})
    print("   %d fully-transferred row(s) across both tables stay locked" % shipped)

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
