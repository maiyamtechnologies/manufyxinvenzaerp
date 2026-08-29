"""The form's list of "this row has material against it" statuses must match the
server's, exactly.

material_planning.py holds MAPPED_BATCH_STATUSES and says of it: "Used wherever
mapped rows are totalled -- the Difference in Kg figure on the form and the per-DUNO
excess the Subcontracting Order banner shows -- so adding a status above can never
silently drop rows out of those sums." The form does not read that tuple, though. It
keeps its own hand-written copy, _MP_MAPPED_STATUSES in material_planning.js, and the
two drifted the moment "Cut Sheet Mapped" was added to one and not the other.

What that looked like from the outside (MP-2026-00042): three cut-sheet rows carrying
1,131.822 Kg of excess between them were skipped by the form's own sum, so Material
Planning reported "Difference in Kg +0.000 (17 of 20 mapped)" while the Job Work
Order raised from it showed Excess Weight 1,131.822 Kg -- the same figure, totalled
server-side over all twenty rows. Nothing was wrong with the data; the plan simply
could not see a third of its own rows, and the only place the truth appeared was a
different document.

A comment cannot keep two lists in step. This does: it reads both and fails if they
differ, so the next status added to either side is caught here rather than by
somebody noticing a wrong total months later.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_mapped_status_lists_match.run
"""

import re

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-52s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _js_statuses():
    """The array literal assigned to _MP_MAPPED_STATUSES in the form script."""
    path = frappe.get_app_path(
        "manufyxinvenzaerp", "production_management", "doctype",
        "material_planning", "material_planning.js",
    )
    src = open(path).read()
    m = re.search(r"const _MP_MAPPED_STATUSES = \[(.*?)\];", src, re.S)
    if not m:
        return None
    return [s for s in re.findall(r'"([^"]+)"', m.group(1))]


def run():
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        MAPPED_BATCH_STATUSES,
    )

    js = _js_statuses()
    py = list(MAPPED_BATCH_STATUSES)

    print("=== the two lists ===")
    print("   server: %s" % (py,))
    print("   form  : %s" % (js,))

    check("the form's list was found at all", js is not None, True)
    if js is None:
        _summary()
        return

    check("no status is on the server but missing from the form",
          sorted(set(py) - set(js)), [])
    check("and none is on the form but missing from the server",
          sorted(set(js) - set(py)), [])
    check("the two match exactly", sorted(js), sorted(py))

    # The one that actually went missing, named so a regression is unmistakable.
    check("Cut Sheet Mapped counts as mapped on both sides",
          ("Cut Sheet Mapped" in py, "Cut Sheet Mapped" in js), (True, True))

    print()
    print("=== and the sum it feeds is whole ===")
    # Any plan whose cut-sheet rows carry excess is one the old form under-reported.
    row = frappe.db.sql(
        """
        SELECT parent,
               ROUND(SUM(batch_calc_qty - qty), 3) AS diff,
               COUNT(*) AS rows_
        FROM `tabMaterial Planning Material Mapping`
        WHERE batch_mapped = 'Cut Sheet Mapped'
        GROUP BY parent
        HAVING ABS(SUM(batch_calc_qty - qty)) > 0.001
        ORDER BY ABS(SUM(batch_calc_qty - qty)) DESC
        LIMIT 1
        """,
        as_dict=True,
    )
    if not row:
        print("    (no plan on this site has cut-sheet rows carrying a difference)")
    else:
        r = row[0]
        print("    %s: %d cut-sheet row(s) carrying %.3f Kg" % (r.parent, r.rows_, r.diff))
        included = frappe.db.sql(
            """
            SELECT ROUND(SUM(batch_calc_qty - qty), 3)
            FROM `tabMaterial Planning Material Mapping`
            WHERE parent = %s AND batch_mapped IN %s
            """,
            (r.parent, tuple(py)),
        )[0][0]
        excluded = frappe.db.sql(
            """
            SELECT ROUND(SUM(batch_calc_qty - qty), 3)
            FROM `tabMaterial Planning Material Mapping`
            WHERE parent = %s AND batch_mapped IN %s AND batch_mapped != 'Cut Sheet Mapped'
            """,
            (r.parent, tuple(py)),
        )[0][0]
        check("the difference includes the cut-sheet rows",
              float(included) != float(excluded), True)

    _summary()


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
