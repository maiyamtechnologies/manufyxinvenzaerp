"""One cut, described the same way wherever it appears.

Three tables show a batch's cut: Material Planning's Material Mapping and Exact Match,
and the Material Issue Plan's raw materials. They had drifted -- the same figure was
called "To Use Calc Qty (Kg) - W1" in one place and "cs_use_length" in another, one
table showed an empty Cut Sheet panel against every batch whether it had a sheet or
not, and one described a checkbox the user could not actually use.

None of that is a behaviour problem, which is exactly why it was worth fixing: a
person reading two rows should not have to work out whether two differently-labelled
numbers mean the same thing. They now share one set of fieldnames, one set of labels,
one rule for when the panel appears, and are read-only everywhere -- because the
nesting is decided once, on the Cut Sheet itself.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_cut_sheet_fields_consistent.run
"""

import frappe

checks = []

TABLES = [
    ("Material Planning Material Mapping", "Material Mapping"),
    ("Material Planning Available Raw Material", "Exact Match"),
    ("Material Issue Plan Raw Material", "Issue Plan raw materials"),
]

SHARED = [
    "cut_sheet_ref",
    "use_length", "use_width", "use_sec_qty",
    "balance_length", "balance_width", "balance_sec_qty",
]

EXPECTED_LABELS = {
    "cut_sheet_ref":    "Cut Sheet",
    "use_length":       "To Use Length (mm)",
    "use_width":        "To Use Width (mm)",
    "use_sec_qty":      "To Use NOS",
    "use_calc_qty":     "To Use Weight (Kg)",
    "balance_length":   "Balance Length (mm)",
    "balance_width":    "Balance Width (mm)",
    "balance_sec_qty":  "Balance NOS",
    "balance_calc_qty": "Balance Weight (Kg)",
}


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-56s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    metas = {dt: frappe.get_meta(dt) for dt, _ in TABLES}

    print("=== every table calls it by the same name ===")
    for dt, label in TABLES:
        present = {f.fieldname for f in metas[dt].fields}
        check("%s has them all" % label, sorted(f for f in SHARED if f not in present), [])
        check("%s has no cs_ leftovers" % label,
              sorted(f for f in present if f.startswith("cs_")), [])

    print()
    print("=== and by the same label ===")
    for fieldname, want in EXPECTED_LABELS.items():
        seen = {}
        for dt, label in TABLES:
            field = metas[dt].get_field(fieldname)
            if field:
                seen[label] = field.label
        if not seen:
            continue
        check("%s reads the same everywhere" % fieldname,
              sorted(set(seen.values())), [want])

    print()
    print("=== nothing here is typed in ===")
    for dt, label in TABLES:
        editable = sorted(
            f for f in SHARED
            if metas[dt].get_field(f) and not metas[dt].get_field(f).read_only
        )
        check("%s is read-only throughout" % label, editable, [])

    print()
    print("=== the panel appears only where there is a cut ===")
    for dt, label in TABLES:
        section = metas[dt].get_field("section_cut_sheet")
        check("%s hides it otherwise" % label,
              section.depends_on if section else None, "eval:doc.cut_sheet_ref")
        check("%s says where the figures come from" % label,
              bool(section and section.description), True)

    print()
    print("=== the two calculated weights stay where they are calculated ===")
    # Material Planning works them out from the cut plan; the issue plan only ever
    # displayed a copy, so it does not carry them any more.
    for dt, label in TABLES[:2]:
        present = {f.fieldname for f in metas[dt].fields}
        check("%s keeps them" % label,
              sorted(f for f in ("use_calc_qty", "balance_calc_qty") if f not in present), [])
    mip = {f.fieldname for f in metas["Material Issue Plan Raw Material"].fields}
    check("the issue plan does not",
          sorted(f for f in ("use_calc_qty", "balance_calc_qty") if f in mip), [])

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
