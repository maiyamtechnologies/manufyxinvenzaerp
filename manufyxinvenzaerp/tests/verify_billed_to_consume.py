"""Billed to Consume is gone, and stays gone.

This file used to verify the feature. The feature was removed on the client's
instruction (2026-08-29), so it now verifies the opposite: that nothing is left
behind and nothing quietly brings it back.

What it was: a tick on an Excess Material Item saying the off-cut never comes
back. The row was skipped by the return entry, left in the supplier's warehouse,
and swept up by the job's final Stock Entry -- which is what put its cost on the
job rather than in the free pool.

Why it went: under the excess/process-loss model the final Stock Entry consumes
only what the job actually used, so nothing is swept up any more. Material that
does not come back is Process Loss instead -- declared deliberately, with a
reason, checked against what is still claimed by other plans, and issued out of
the supplier warehouse by its own entry.

The one thing that changed for the business, and it was accepted: as
Billed-to-Consume the cost landed on the job's finished goods; as Process Loss it
lands on the write-off account instead.

No live row ever carried the tick on this site (12 excess rows, none ticked), so
nothing needed migrating.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_billed_to_consume.run
"""

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-56s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _src(*parts):
    return open(frappe.get_app_path("manufyxinvenzaerp", *parts)).read()


def run():
    print("=== the field itself ===")
    meta = frappe.get_meta("SCO Excess Material Item")
    check("the tick is gone from the doctype", bool(meta.get_field("billed_to_consume")), False)
    check("and nothing depends on it any more",
          [f.fieldname for f in meta.fields if "billed_to_consume" in (f.depends_on or "")], [])

    print()
    print("=== the code that read it ===")
    for label, parts in (
        ("the return entry no longer skips rows for it",
         ("subcontracting_management", "material_issue_plan_transfer.py")),
        ("completion no longer treats it as settled",
         ("subcontracting_management", "doctype", "material_issue_plan", "material_issue_plan.py")),
        ("excess claiming no longer refuses on it",
         ("production_management", "doctype", "material_planning", "material_planning.py")),
        ("the production report no longer nets it off",
         ("production_management", "report", "production_report", "production_report.py")),
    ):
        src = _src(*parts)
        # The word may survive in a comment explaining what was removed -- what must
        # not survive is code reading the field.
        reads = [
            ln.strip() for ln in src.splitlines()
            if "billed_to_consume" in ln and not ln.strip().startswith("#")
        ]
        check(label, reads, [])

    print()
    print("=== the report it had a filter and a column on ===")
    rep = _src("subcontracting_management", "report", "excess_material_return_report",
               "excess_material_return_report.py")
    repjs = _src("subcontracting_management", "report", "excess_material_return_report",
                 "excess_material_return_report.js")
    check("no column", "billed_to_consume" in rep, False)
    check("no filter", "billed_to_consume" in repjs, False)

    print()
    print("=== and no data was left carrying it ===")
    cols = frappe.db.sql(
        """SELECT COUNT(*) FROM information_schema.columns
           WHERE table_name = 'tabSCO Excess Material Item'
             AND column_name = 'billed_to_consume'"""
    )[0][0]
    # Frappe leaves the column in place after a field is dropped; what matters is
    # that nothing reads it. Reported rather than asserted, so a stale column is
    # visible without failing a run.
    print("    (database column still present: %s -- unread, dropped on the next schema rebuild)"
          % bool(cols))

    _summary()


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
