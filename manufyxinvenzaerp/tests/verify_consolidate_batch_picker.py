"""The Update Batch dialog lists the batches you can actually move a line to.

Two faults, one visible and one behind it.

The picker was an <input list="...">, a datalist. A datalist is not a dropdown: the
browser shows only the entries that match what is already typed. So whenever the box held
a value that no candidate matched, clicking it showed an empty list and the screen simply
said nothing.

What put a stale value there was the second fault. Picking a different line kept the
previous line's target rows -- their batch, their length, their width, their pieces. Since
the batches offered are the SELECTED item's, a plate batch chosen on a PLATE10 line stayed
on the row when an ISMB450 line was picked next, carrying 12,000 x 2,500 and its free
weight onto a line where neither meant anything, and matching none of the ISMB450
candidates.

Now: choosing a line resets its target rows, and the picker is a real <select> that lists
every candidate whatever the box holds. The server was never at fault -- it returns the
right candidates for all five lines of MIP-2026-00060.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_consolidate_batch_picker.run
"""

import os

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _js():
    return open(os.path.join(
        frappe.get_app_path("manufyxinvenzaerp"), "subcontracting_management",
        "doctype", "material_issue_plan", "material_issue_plan.js")).read()


def run():
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_batch_update as bu
    js = _js()

    print("=== the picker is the desk's own searchable Link control ===")
    # It began as an <input list>, a datalist, which shows only what matches what is
    # already typed -- so a stale value made it look empty. A plain <select> fixed that
    # but is no use at 48 batches. This is the control used everywhere else, with a
    # query that narrows on batch name or item code.
    check("the datalist is gone", "_cb_batch_options" in js, False)
    check("...and so is the plain select", '<select class="form-control input-xs _cb_batch"' in js, False)
    check("a real Link control is built per row", "frappe.ui.form.make_control({" in js, True)
    check("...of Batch", 'options: "Batch",' in js, True)
    check("...searching through consolidate_batch_query",
          'query: _MIP_CB + "consolidate_batch_query"' in js, True)
    check("...scoped to the line's warehouse and item",
          "filters: { warehouse: lineWarehouse, item_code: selected.item_code }" in js, True)
    check("its value is seeded from the row", 'ctrl.set_value(targets[i].batch_no || "");' in js, True)
    check("the control never reaches the server payload",
          "map((t) => ({ batch_no: t.batch_no, pieces: t.pieces || 0 }))" in js, True)

    print()
    print("=== and the query itself narrows and ranks ===")
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_batch_update as m
    import inspect as _i
    q = _i.getsource(m.consolidate_batch_query)
    check("it matches on batch name or item",
          "needle not in b.name.lower() and needle not in (b.item or \"\").lower()" in q, True)
    check("the line's own item ranks first",
          "key=lambda r: (0 if r[1] == own_item else 1, -r[2], r[0])" in q, True)
    check("it shows FREE Kg, not what the batch holds", '"%s Kg free"' in q, True)
    check("no warehouse means no list", "if not warehouse:" in q, True)

    print()
    print("=== picking a line clears the last one's rows ===")
    check("targets are reset", "targets = [{}];" in js, True)
    check("...and so are the candidates", "candidates = [];\n\t\t\tcandidatesLoaded = false;" in js, True)
    check("the stale partial reset is gone",
          "targets.forEach((t) => { delete t._info; });" in js, False)

    print()
    print("=== and it does not claim 'nothing to offer' before it has looked ===")
    check("a loaded flag exists", "let candidatesLoaded = false;" in js, True)
    check("the empty note waits for it", "|| !candidatesLoaded ? \"\" :" in js, True)
    # The picker no longer waits on anything: a Link control queries as you type. The
    # loaded flag still gates the NOTES under the table, which do need the candidate
    # list before they can say there is nothing to move to.
    check("the box invites a search", '__("Search batch or item…")' in js, True)

    print()
    print("=== live: the server offers the right batches for every line ===")
    mip = "MIP-2026-00060"
    if not frappe.db.exists("Material Issue Plan", mip):
        print("  SKIP %s not on this site" % mip)
    else:
        m = frappe.get_doc("Material Issue Plan", mip)
        for c in m.consolidate_items:
            ctx = bu.get_consolidate_line_context(mip, c.name)
            wh = ctx.get("warehouse") or ""
            check("%-9s%s resolves a warehouse" % (c.item_code, " CNC" if c.cnc_process else "    "),
                  bool(wh), True)
            if not wh:
                continue
            cands = bu.get_candidate_batches(ctx.get("item_code"), wh)
            check("   ...and is offered %d batch(es), all with free stock" % len(cands),
                  bool(cands) and all(flt(x["free_kg"]) > 0 for x in cands), True)
            # Not item-filtered any more -- any batch of any item can be sent instead.
            # What still holds is that the line's own item sorts to the top, so the
            # ordinary choice is the first one offered.
            check("   ...with a %s batch first" % c.item_code,
                  cands[0]["item_code"] if cands else None, ctx.get("item_code"))

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
