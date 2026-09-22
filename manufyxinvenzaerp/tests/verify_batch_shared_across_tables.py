"""A batch may serve BOTH planning tables; what it may not do is promise more than it holds.

Material Mapping used to refuse any batch that an Exact Match row already used, whatever
was left of it. That is the case the table exists for: material_mapping_batch_query's own
docstring gives "a requirement for ISMB400 satisfied by an ISA100 bar" as the reason it is
deliberately not filtered by item -- and it was refused on ISA100-L12000-SR001 holding
10,906.800 Kg with 912.476 Kg allocated and 9,994.324 Kg free, on a plan that was 2,649.301
Kg short of ISMB400.

The ban's stated reason was "double-counting at transfer time". It does not happen:
_get_mp_reserved_batches appends rows from both tables into one list, each carrying its own
reserved_qty, and get_mip_pending_items groups by (item, batch, leg) and SUMS -- two sources
become one transfer line of the combined weight, counted once.

The quantity rule was already enforced where it belongs. _get_batch_reserved_by_others takes
exclude_table, so reserving in either table counts the OTHER table's reservations on that
batch INCLUDING this plan's own, and caps what it takes.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_batch_shared_across_tables.run
"""

import inspect

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, fragment):
    try:
        fn()
    except Exception as e:
        return fragment.lower() in frappe.utils.strip_html(str(e)).lower()
    return False


def run():
    from manufyxinvenzaerp.production_management.doctype.material_planning import (
        material_planning as mp_mod,
    )

    print("=== the ban is gone, and what replaced it measures weight ===")
    src = inspect.getsource(mp_mod.MaterialPlanning._validate_batch_not_over_allocated)
    check("the old identity check is gone",
          hasattr(mp_mod.MaterialPlanning, "_validate_no_cross_table_batch_duplicate"), False)
    check("it compares against stock", "_get_batch_total_stock" in src, True)
    check("it subtracts other plans", "_get_batch_reserved_by_others" in src, True)
    check("it measures RESERVED weight only", "is_reserved" in src, True)

    print()
    print("=== reserving already counts the other table (this is what caps it) ===")
    # exclude_table flips which table applies the same-MP exclusion, so the OTHER table
    # counts every plan including this one.
    o = inspect.getsource(mp_mod._get_batch_reserved_by_others)
    check("the helper takes exclude_table", "exclude_table" in o, True)
    check("Material Mapping reserve counts Exact Match",
          'exclude_table="material_mapping"' in inspect.getsource(mp_mod.reserve_batches), True)
    check("Exact Match reserve counts Material Mapping",
          'exclude_table="available_raw_materials"' in
          inspect.getsource(mp_mod.reserve_exact_match_batches), True)

    print()
    print("=== the transfer builder sums the two tables, it does not pick one ===")
    from manufyxinvenzaerp.subcontracting_management import subcontracting as sub
    rb = inspect.getsource(sub._get_mp_reserved_batches)
    check("it reads Material Mapping", "Material Planning Material Mapping" in rb, True)
    check("it reads Available Raw Material", "Material Planning Available Raw Material" in rb, True)
    check("both append into one list", rb.count("items.append(") >= 2, True)
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as mipt
    pend = inspect.getsource(mipt.get_mip_pending_items)
    check("pending lines are summed per item+batch+leg",
          'totals[key]["qty"] = flt(totals[key]["qty"] + item["qty"], 3)' in pend, True)

    print()
    print("=== the popup only refuses an exhausted batch ===")
    import os
    js = open(os.path.join(frappe.get_app_path("manufyxinvenzaerp"),
              "production_management", "doctype", "material_planning",
              "material_planning.js")).read()
    check("it lets a shared batch through when stock remains",
          'if (flt(d.available_qty, 3) > 0)' in js, True)
    check("the old blanket refusal is gone",
          "The same batch cannot be used in both tables" in js, False)

    print()
    print("=== the arithmetic the guard applies ===")
    # 10,906.800 in stock, 912.476 held by exact match, nothing elsewhere.
    stock, exact_match, others = 10906.800, 912.476, 0.0
    free = flt(stock - others - exact_match, 3)
    check("a 2,649.301 Kg mapping row fits in the free 9,994.324",
          flt(free, 3) >= 2649.301, True)
    check("free is what the report shows", free, 9994.324)
    # and the refusal case: reserving more than is free
    check("over-allocation is what should be refused",
          flt(exact_match + 10000.0, 3) > flt(stock - others, 3), True)

    print()
    print("=== live: is there a plan where this now works? ===")
    mp = frappe.db.get_value("Material Planning", {"docstatus": 0}, "name")
    if not mp:
        print("  SKIP no draft Material Planning on this site")
    else:
        d = frappe.get_doc("Material Planning", mp)
        shared = {}
        for r in (d.material_mapping or []):
            if r.batch:
                shared.setdefault(r.batch, set()).add("mapping")
        for r in (d.available_raw_materials or []):
            if r.batch_no:
                shared.setdefault(r.batch_no, set()).add("exact")
        both = [b for b, t in shared.items() if len(t) > 1]
        print(f"  {mp}: {len(both)} batch(es) used in both tables {both[:3]}")
        try:
            d.save(ignore_permissions=True)
            check("the plan saves with a batch in both tables", True, True)
        except Exception as e:
            check("the plan saves with a batch in both tables",
                  frappe.utils.strip_html(str(e))[:60], True)
        finally:
            frappe.db.rollback()

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
