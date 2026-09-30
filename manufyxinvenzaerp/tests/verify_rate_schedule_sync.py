"""The Rate Schedule is decided once, per drawing, and has to read the same on the
Drawing, its BOM and every Production Plan row quoting it.

Three documents can now edit it, which is the whole point and also the whole risk:
the thing being tested is that an edit in ANY of the three reaches the other two,
and -- just as important -- that a save which did NOT touch the field changes
nothing anywhere.

That second half is where the damage would be. Every BOM and Production Plan on
this site was created before these fields existed and carries a blank schedule. A
sync that reconciled "documents that disagree" rather than "the field somebody just
edited" would, on the first unrelated save of any of them, push that blank onto the
Drawing and wipe the rate off every document quoting it -- with nothing on screen
connecting the loss to the save that caused it. Check 4 is that case.

Runs entirely on temporary fixtures and rolls back, so it is safe on live data.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_rate_schedule_sync.run
"""

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _schedule(name, rate, job_nature):
    """A Rate Schedule is autonamed field:rs_no, so rs_no IS the document name."""
    if frappe.db.exists("Rate Schedule", name):
        return name
    frappe.get_doc({
        "doctype": "Rate Schedule",
        "rs_no": name,
        "type": "Outsource",
        "job_nature": job_nature,
        "details": "verify_rate_schedule_sync fixture",
        "rate_per_kg": rate,
    }).insert(ignore_permissions=True)
    return name


def run():
    from manufyxinvenzaerp.drawing_management import rate_schedule_sync as rss

    # A real drawing that already has a BOM -- the sync is keyed on the drawing, so
    # a fixture drawing with nothing pointing at it would prove nothing. A drawing
    # that ALSO has a Production Plan row is preferred, because that is the third
    # leg and the only one whose target is a child row rather than a document.
    pair = frappe.db.sql("""
        SELECT b.custom_drawing AS drawing, b.name AS bom
        FROM `tabBOM` b
        WHERE IFNULL(b.custom_drawing, '') != '' AND b.docstatus != 2
          AND EXISTS (SELECT 1 FROM `tabProduction Plan Item` ppi
                      WHERE ppi.custom_drawing = b.custom_drawing AND ppi.docstatus != 2)
        LIMIT 1
    """, as_dict=True) or frappe.db.sql("""
        SELECT b.custom_drawing AS drawing, b.name AS bom
        FROM `tabBOM` b
        WHERE IFNULL(b.custom_drawing, '') != '' AND b.docstatus != 2
        LIMIT 1
    """, as_dict=True)
    if not pair:
        print("no BOM linked to a Drawing on this site -- skipped")
        return

    drawing, bom = pair[0].drawing, pair[0].bom
    print("drawing %s, bom %s" % (drawing, bom))

    original_drawing_rs = frappe.db.get_value("Drawing", drawing, "rate_schedule")
    original_bom_rs = frappe.db.get_value("BOM", bom, "custom_rate_schedule")
    print("before: drawing=%r bom=%r" % (original_drawing_rs, original_bom_rs))

    # Job Nature is mandatory on a Rate Schedule, so the fixtures borrow whichever
    # one this site has rather than inventing a master that would outlive the test.
    job_nature = frappe.db.get_value("Job Nature", {}, "name")
    if not job_nature:
        print("no Job Nature master on this site -- skipped")
        return

    rs_a = _schedule("VERIFY-RS-A", 61.5, job_nature)
    rs_b = _schedule("VERIFY-RS-B", 88.25, job_nature)

    print()
    print("=== 1. Drawing -> BOM ===")
    frappe.db.set_value("Drawing", drawing, "rate_schedule", rs_a, update_modified=False)
    result = rss.propagate(drawing, rs_a, "Drawing", drawing)
    check("BOM picked up the schedule",
          frappe.db.get_value("BOM", bom, "custom_rate_schedule"), rs_a)
    check("BOM's Rate/KG mirrors the master",
          frappe.db.get_value("BOM", bom, "custom_rs_rate_per_kg"), 61.5)
    check("BOM is named in the popup",
          any(u["doctype"] == "BOM" and u["name"] == bom for u in result["updated"]), True)

    print()
    print("=== 2. BOM -> Drawing (the same edit, from the other end) ===")
    result = rss.propagate(drawing, rs_b, "BOM", bom)
    check("Drawing followed the BOM",
          frappe.db.get_value("Drawing", drawing, "rate_schedule"), rs_b)
    check("Drawing's Rate/KG mirrors the master",
          frappe.db.get_value("Drawing", drawing, "rs_rate_per_kg"), 88.25)
    check("the source document is not listed as updated",
          any(u["name"] == bom for u in result["updated"]), False)

    print()
    print("=== 3. Nothing to do is reported as nothing to do ===")
    # Re-applying the schedule everything already has must not claim it changed
    # anything -- a popup that lists documents it did not touch teaches people to
    # ignore it.
    result = rss.propagate(drawing, rs_b, "BOM", bom)
    check("no documents reported as updated", result["updated"], [])
    check("they are counted as unchanged instead", result["unchanged"] > 0, True)

    print()
    print("=== 4. A save that did not touch the field changes nothing ===")
    # The destructive case. A BOM carrying a blank schedule (every BOM predating
    # this feature) saved for an unrelated reason must NOT push that blank onto
    # the Drawing.
    frappe.db.set_value("BOM", bom, "custom_rate_schedule", "", update_modified=False)
    bom_doc = frappe.get_doc("BOM", bom)
    bom_doc._doc_before_save = frappe.get_doc("BOM", bom)   # nothing changed in this save
    rss.on_update_bom(bom_doc)
    check("Drawing kept its schedule",
          frappe.db.get_value("Drawing", drawing, "rate_schedule"), rs_b)

    print()
    print("=== 5. Clearing the field IS an edit, and does travel ===")
    # Distinct from check 4: here the user really did empty it, so the blank is a
    # decision and must propagate.
    result = rss.propagate(drawing, "", "BOM", bom)
    check("Drawing cleared", frappe.db.get_value("Drawing", drawing, "rate_schedule") or "", "")
    check("its Rate/KG cleared too",
          frappe.db.get_value("Drawing", drawing, "rs_rate_per_kg") or 0, 0)

    print()
    print("=== 6. Cancelled documents are never rewritten ===")
    targets = rss._targets(drawing)
    cancelled = frappe.get_all("BOM", filters={"custom_drawing": drawing, "docstatus": 2},
                               pluck="name")
    check("no cancelled BOM among the targets",
          any(t[1] in cancelled for t in targets), False)

    print()
    print("=== 7. The conflict question is asked only when there is a conflict ===")
    frappe.db.set_value("Drawing", drawing, "rate_schedule", rs_a, update_modified=False)
    same = rss.get_rate_schedule_conflict(drawing, rs_a, "BOM", bom)
    diff = rss.get_rate_schedule_conflict(drawing, rs_b, "BOM", bom)
    check("same schedule -> no question", same["conflict"], False)
    check("different schedule -> question", diff["conflict"], True)
    check("the question names the current schedule", diff["current"], rs_a)

    print()
    print("=== 8. Production Plan rows are the third leg ===")
    pp_rows = frappe.get_all(
        "Production Plan Item",
        filters={"custom_drawing": drawing, "docstatus": ["!=", 2]},
        fields=["name", "parent"],
    )
    if not pp_rows:
        print("  (no Production Plan row quotes this drawing -- leg skipped)")
    else:
        result = rss.propagate(drawing, rs_b, "Drawing", drawing)
        check("the row picked up the schedule",
              frappe.db.get_value("Production Plan Item", pp_rows[0].name,
                                  "custom_rate_schedule"), rs_b)
        check("its Rate/KG mirrors the master",
              frappe.db.get_value("Production Plan Item", pp_rows[0].name,
                                  "custom_rs_rate_per_kg"), 88.25)
        pp_updates = [u for u in result["updated"] if u["doctype"] == "Production Plan Item"]
        check("the popup names the PLAN, not the row hash",
              bool(pp_updates) and pp_updates[0]["label"], pp_rows[0].parent)
        # A child row has no form of its own, so a link to it opens nothing.
        check("and links to the plan's own form",
              rss._route("Production Plan Item", pp_rows[0].parent),
              frappe.utils.get_absolute_url("Production Plan", pp_rows[0].parent))

        print()
        print("=== 9. Seeding a blank row is not treated as an edit ===")
        # The row is filled from its own drawing, so re-broadcasting it would be a
        # no-op at best -- and on a legacy blank BOM it would write a rate onto a
        # submitted document as a side effect of saving an unrelated plan.
        frappe.db.set_value("Production Plan Item", pp_rows[0].name,
                            "custom_rate_schedule", "", update_modified=False)
        # Read it rather than assume: check 7 above left the Drawing on rs_a while
        # the row was pushed to rs_b, and seeding must follow the DRAWING.
        drawing_rs = frappe.db.get_value("Drawing", drawing, "rate_schedule")
        plan = frappe.get_doc("Production Plan", pp_rows[0].parent)
        rss.seed_production_plan_rows(plan)
        seeded_row = next(r for r in plan.po_items if r.name == pp_rows[0].name)
        check("the blank row was seeded from the drawing",
              seeded_row.custom_rate_schedule, drawing_rs)
        check("and was recorded as seeded, not edited",
              pp_rows[0].name in plan.flags.rate_schedule_seeded_rows, True)

    frappe.db.rollback()
    print()
    print("rolled back -- drawing/BOM/plan left exactly as found")

    total, failed = len(checks), checks.count(False)
    print()
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, total))
    else:
        print("ALL %d CHECKS PASSED" % total)
