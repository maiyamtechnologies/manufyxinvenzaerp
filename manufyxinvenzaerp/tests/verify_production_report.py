"""Production Report: one row per drawing, every operation across the columns.

It used to be one row per drawing *per operation*. A four-operation job with six
drawings filled twenty-four rows with the same six drawings repeated, and answering
"where is 1B1 up to" meant reading four of them and holding them in your head.

Now each drawing gets one row, and every operation the job is routed through
contributes a block of five columns to it -- quantity, status, inspection rounds, last
inspection status, and the gap in days. The operation list is not fixed: it is whatever
the jobs in view are actually routed through, in the order they run.

The two things this checks that a screenshot cannot:

  * the row count really did collapse -- one row per (Job Work Order, Drawing) and no
    more, however many operations sit behind it; and
  * the figures survived the collapse. Every operation's status still appears, in its
    own column, on the row for the drawing it belongs to.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_production_report.run
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.production_management.report.production_report.production_report import (
    execute,
)

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-56s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _labels(columns):
    return [c["label"] for c in columns]


def _drawing_rows(data):
    """The report's rows without its own total row, which the report appends last."""
    return [r for r in data if not r.get("is_total_row")]


def run():
    columns, data = execute({})
    labels = _labels(columns)
    total = data[-1] if data and data[-1].get("is_total_row") else None
    data = _drawing_rows(data)

    print("=== the columns the client asked for, in the order asked for ===")
    lead = labels[:11]
    check("traceability first, sales-order-wise", lead, [
        "Sales Order", "Customer", "Project", "Production Plan (Team)", "Job Type",
        "Job Work Order", "Supplier", "Drawing", "DUNO/Mark No", "Cust Drawing No",
        "Created On",
    ])
    tail = labels[-17:]
    check("weights, costs and completion last", tail, [
        "Cust Weight (Total)", "Planned Weight (Kg)", "Planned NOS", "Waste %",
        "Transferred Weight (Kg)", "Transferred NOS", "Consumed RM Cost",
        "Rate Schedule", "Rate / Kg", "Job Work Amount", "Consumables NOS", "Consumable Cost",
        "Excess Weight (Kg)", "Returned Excess Weight (Kg)", "Difference (Kg)",
        "Completed Drawing Weight (Kg)", "Completed Drawing NOS",
    ])
    check("and the piece count closes it", labels[-1], "Completed Drawing NOS")
    check("Operation and Seq are gone -- they are columns now, not rows",
          [l for l in labels if l in ("Operation", "Seq")], [])

    print()
    print("=== Created On comes from the Job Work Order, not the operation entry ===")
    # Every operation of a job was raised on its own day, so reading the date off the
    # operation made one job look like several.
    created = frappe.get_all("Subcontracting Order",
                             fields=["name", "transaction_date"], as_list=False)
    by_sco = {c.name: c.transaction_date for c in created}
    mismatched = [r["subcontracting_order"] for r in data
                  if r["subcontracting_order"] in by_sco
                  and r["created_on"] != by_sco[r["subcontracting_order"]]]
    check("every row carries its order's own date", mismatched, [])

    if not data:
        print()
        print("   No Supplier Operation Entry on this site, so the shape below cannot be")
        print("   measured against real data. The column contract above still holds.")
        _summary()
        return

    print()
    print("=== one row per drawing, not one per drawing per operation ===")
    keys = [(r["subcontracting_order"], r["drawing"]) for r in data]
    check("no drawing is listed twice on a job", len(keys), len(set(keys)))

    soes = frappe.get_all("Supplier Operation Entry",
                          fields=["name", "subcontracting_order", "operation", "sequence_id", "status"])
    expected = set()
    for d in frappe.get_all("SOE Drawing Detail",
                            filters={"parent": ["in", [s.name for s in soes]]},
                            fields=["parent", "drawing"]):
        parent = next((s for s in soes if s.name == d.parent), None)
        if parent and d.drawing:
            expected.add((parent.subcontracting_order, d.drawing))
    check("every drawing on every job still appears once", set(keys), expected)
    # The collapse is the point: state what it saved, so a regression that quietly
    # re-expands the rows is visible in the output and not only in the assertion.
    print("   %d operation entries over %d drawing rows (was %d rows before)"
          % (len(soes), len(data), sum(1 for _ in _old_shape(soes))))

    print()
    print("=== each operation writes into its own block, on the right row ===")
    # Kg only where the operation is first on EVERY job that has it -- see
    # _operation_columns. Anywhere else the column would carry two different meanings.
    highest = {}
    for s in soes:
        if s.operation:
            highest[s.operation] = max(highest.get(s.operation, 0), s.sequence_id or 0)
    ops = sorted({(s.sequence_id or 0, s.operation) for s in soes if s.operation})
    for seq, operation in ops:
        slug = frappe.scrub(operation)
        unit = "Kg" if highest[operation] <= 1 else "Nos"
        check("%s has its own columns" % operation,
              all("%s %s" % (operation, suffix) in labels
                  for suffix in ("Status", "Inspection Rounds", "Last Inspection Status")),
              True)
        # A pieces operation is headed "Welding NOS", like every other pieces heading;
        # a Kg one keeps "Fit-up (Kg)".
        check("  and a quantity in %s" % unit,
              ("%s (%s)" % (operation, unit) if unit == "Kg" else "%s NOS" % operation) in labels,
              True)
        check("  and a gap of its own", "%s Gap (Days, approx.)" % operation in labels, True)
        # The status a row shows for an operation must be that operation's status on
        # that job -- the check that the pivot put the values where the labels say.
        for s in soes:
            if s.operation != operation:
                continue
            rows = [r for r in data if r["subcontracting_order"] == s.subcontracting_order]
            if not rows:
                continue
            wrong = [r["drawing"] for r in rows if r.get("op_%s_status" % slug) != s.status]
            check("  %s on %s reads %r everywhere" % (operation, s.subcontracting_order, s.status),
                  wrong, [])

    print()
    print("=== a job appears the moment its Job Work Order is submitted ===")
    # Before this, the report was driven by Supplier Operation Entry: a job whose
    # operation entries had not been raised yet was simply absent, with nothing on
    # screen to say it existed. The order is what makes a job real, so the order is
    # what the report is built from now.
    victim = data[0]["subcontracting_order"]
    try:
        frappe.db.delete("Supplier Operation Entry", {"subcontracting_order": victim})
        after_data = _drawing_rows(execute({})[1])
        still = [r for r in after_data if r["subcontracting_order"] == victim]
        check("its drawings are still listed with no operations at all",
              len(still), len([r for r in data if r["subcontracting_order"] == victim]))
        check("and the weights are still on them",
              flt(still[0]["planned_weight_kg"], 3) if still else None,
              flt([r for r in data if r["subcontracting_order"] == victim][0]["planned_weight_kg"], 3))
    finally:
        frappe.db.rollback()

    print()
    print("=== an operation that is first on one job and second on another reads in Nos ===")
    # The routing dropped Material Issue on 2026-08-25, so jobs raised since start at
    # Fit-up while older jobs have Fit-up at sequence 2. A column carries one unit for
    # every row in it, so it cannot be Kg on half of them: it reads in Nos, and the Kg
    # is still on Transferred Weight where it always was.
    # It has to be an operation more than one job runs -- moving one that only ever
    # appears once just moves it, and proves nothing about a mixed column.
    jobs_per_op = {}
    for s in soes:
        if s.operation:
            jobs_per_op.setdefault(s.operation, set()).add(s.subcontracting_order)
    mixed = next(((s.subcontracting_order, s.operation) for s in soes
                  if (s.sequence_id or 0) > 1 and len(jobs_per_op[s.operation]) > 1), None)
    if not mixed:
        print("   No operation on this site is shared by two jobs at sequence 2 or later.")
    else:
        sco_name, operation = mixed
        was_kg = "%s (Kg)" % operation in labels
        try:
            frappe.db.set_value("Supplier Operation Entry",
                                {"subcontracting_order": sco_name, "operation": operation},
                                "sequence_id", 1, update_modified=False)
            after_labels = _labels(execute({})[0])
            check("%s at sequence 1 here and 2 elsewhere" % operation,
                  ("%s (Kg)" % operation in after_labels,
                   "%s NOS" % operation in after_labels),
                  (False, True))
        finally:
            frappe.db.rollback()
        check("and the unit is unchanged once that is rolled back",
              "%s (Kg)" % operation in _labels(execute({})[0]), was_kg)

    print()
    print("=== a draft or cancelled Job Work Order is not a job yet ===")
    drafts = frappe.get_all("Subcontracting Order", filters={"docstatus": ["!=", 1]}, pluck="name")
    check("none of them reach the report",
          [r["subcontracting_order"] for r in data if r["subcontracting_order"] in drafts], [])
    submitted = set(frappe.get_all("Subcontracting Order", filters={"docstatus": 1}, pluck="name"))
    check("and every submitted one that has drawings does",
          sorted(submitted - {r["subcontracting_order"] for r in data}),
          sorted(n for n in submitted
                 if not frappe.db.exists("SCO Drawing Item",
                                         {"parent": n, "parenttype": "Subcontracting Order"})))

    print()
    print("=== Waste % closes the planned block ===")
    # The column that would have caught the per-piece customer weight on sight: 1B1 read
    # 104% while the single-piece drawing beside it read 1.6%, on the same cuts.
    from manufyxinvenzaerp.production_management.report.production_report.production_report import (
        _waste_pct,
    )
    check("it sits between the planned figures and the transferred ones",
          (labels[labels.index("Waste %") - 1], labels[labels.index("Waste %") + 1]),
          ("Planned NOS", "Transferred Weight (Kg)"))
    check("no customer weight leaves it blank, not zero", _waste_pct(0, 1814.089), None)
    check("and it is planned over customer", _waste_pct(1780.16, 1814.089), 1.91)
    check("negative when the plan holds less than the part weighs",
          _waste_pct(100, 90) < 0, True)
    for r in data:
        if not flt(r["customer_weight_kg"]):
            continue
        check("%s: %s%%" % (r["duno_mark_no"], r["waste_pct"]),
              r["waste_pct"],
              _waste_pct(r["customer_weight_kg"], r["planned_weight_kg"]))
        break

    print()
    print("=== raw-material cost follows the requirement, not the stamp ===")
    # A transfer consolidates every requirement for one item and batch into a single
    # line, and that line carries one drawing. On SC-ORD-2026-00003 the whole 285.484 Kg
    # of ISA100 is stamped 1B6, while 1B1 and 1B2 take 81.056 Kg of it each -- costing by
    # that stamp hands one drawing the entire bill and the other four nothing.
    #
    # Sites often run with no rates at all, which hides this behind a column of zeroes,
    # so the transfer is priced here and rolled back.
    entries = frappe.get_all("Stock Entry", filters={"docstatus": 1, "custom_sco_ref": ["!=", ""]},
                             fields=["name", "custom_sco_ref"])
    sco_of_entry = {e.name: e.custom_sco_ref for e in entries}
    transfers = frappe.get_all(
        "Stock Entry Detail", filters={"parent": ["in", list(sco_of_entry) or [""]]},
        fields=["name", "parent", "qty", "t_warehouse"])
    # The finished-goods Manufacture entry names the job too, through
    # subcontracting_order. It is priced at a rate nobody paid for the issue, so if it
    # leaks into the cost the rates below stop coming out at 50.
    manufactured = frappe.get_all(
        "Stock Entry Detail",
        filters={"parent": ["in", frappe.get_all(
            "Stock Entry",
            filters={"docstatus": 1, "purpose": "Manufacture", "subcontracting_order": ["is", "set"]},
            pluck="name") or [""]]},
        fields=["name", "qty"])
    took, supplier_wh = _taken_by_drawing()
    if not transfers:
        print("   No transfer against a Job Work Order on this site.")
    else:
        try:
            for t in transfers:
                frappe.db.set_value("Stock Entry Detail", t.name,
                                    {"basic_rate": 50, "amount": flt(t.qty) * 50},
                                    update_modified=False)
            for t in manufactured:
                frappe.db.set_value("Stock Entry Detail", t.name,
                                    {"basic_rate": 999, "valuation_rate": 999, "amount": flt(t.qty) * 999},
                                    update_modified=False)
            priced = _drawing_rows(execute({})[1])
            # Every drawing should come out at the rate that was paid -- that is what
            # "spread in proportion to what each took" means, checked as a rate rather
            # than as an amount so it does not depend on this site's quantities.
            #
            # "What each took" is the plan's own raw-material rows, which is what the
            # cost is spread over. It is not the Transferred Weight column: that one is
            # the job's transfer shared out by planned weight (refresh_weight_summary), so
            # the two part company wherever a transfer's excess sits on one drawing.
            rates = sorted({round(flt(r["consumed_rm_cost"]) / took[(r["subcontracting_order"], r["drawing"])], 2)
                            for r in priced if flt(took.get((r["subcontracting_order"], r["drawing"])))})
            check("every drawing is costed at the rate paid", rates, [50.0])
            print("   (%d finished-goods Manufacture rows priced at 999 alongside -- none of it may show)"
                  % len(manufactured))
            # The whole transfer is what landed at the job. An issue routed through CNC
            # (Stores -> CNC -> job) moves the same Kg twice and is counted once.
            check("and the parts add up to the whole transfer",
                  round(sum(flt(r["consumed_rm_cost"]) for r in priced), 2),
                  round(sum(flt(t.qty) for t in transfers
                            if t.t_warehouse and t.t_warehouse == supplier_wh.get(sco_of_entry[t.parent]))
                        * 50, 2))
        finally:
            frappe.db.rollback()
    apart = [(r["subcontracting_order"], r["drawing"], flt(r["transferred_weight_kg"], 3),
              flt(took[(r["subcontracting_order"], r["drawing"])], 3))
             for r in data if (r["subcontracting_order"], r["drawing"]) in took
             and flt(r["transferred_weight_kg"], 3) != flt(took[(r["subcontracting_order"], r["drawing"])], 3)]
    for sco_name, drawing, column, rows in apart:
        # Not a failure of this report -- both figures come from the Material Issue
        # Plan -- but worth seeing: the Transferred Weight column and the cost beside it
        # are not spread over the same Kg on these rows.
        print("   NOTE %s %s: Transferred Weight %s Kg, plan rows took %s Kg"
              % (sco_name, drawing, column, rows))

    print()
    print("=== job work: rate per Kg and amount per drawing ===")
    # The amount is the drawing's Cust Weight (Total) on that Job Work Order times its
    # Rate per Kg. An order raised since that pricing went in holds both on its own
    # drawing row; an older one holds neither and is priced from the drawing's Rate
    # Schedule.
    held = {(w.parent, w.drawing): w for w in frappe.get_all(
        "SCO Drawing Item", filters={"parenttype": "Subcontracting Order"},
        fields=["parent", "drawing", "rate_per_kg", "job_work_amount"])}
    schedule = dict(frappe.get_all("Drawing", filters={"name": ["in", [r["drawing"] for r in data]]},
                                   fields=["name", "rs_rate_per_kg"], as_list=True))
    wrong = []
    for r in data:
        w = held.get((r["subcontracting_order"], r["drawing"])) or frappe._dict()
        rate = flt(flt(w.rate_per_kg) or flt(schedule.get(r["drawing"])), 2)
        amount = flt(flt(w.job_work_amount) or flt(r["customer_weight_kg"], 3) * rate, 2)
        if (r["rate_per_kg"], r["job_work_amount"]) != (rate, amount):
            wrong.append((r["subcontracting_order"], r["drawing"], r["rate_per_kg"], r["job_work_amount"]))
    check("every row is Cust Weight (Total) x Rate / Kg", wrong, [])
    example = next((r for r in data if flt(r["rate_per_kg"])), None)
    if example:
        print("   e.g. %s %s: %s Kg x %s = %s"
              % (example["subcontracting_order"], example["duno_mark_no"], example["customer_weight_kg"],
                 example["rate_per_kg"], example["job_work_amount"]))
        check("  worked by hand", example["job_work_amount"],
              flt(flt(example["customer_weight_kg"], 3) * example["rate_per_kg"], 2)
              if not flt((held.get((example["subcontracting_order"], example["drawing"])) or {}).get("job_work_amount"))
              else example["job_work_amount"])

    # What the Job Work Order holds wins over the Rate Schedule. The amount here is
    # deliberately not weight x rate, so reading it back proves it was read, not redone.
    r0 = data[0]
    try:
        frappe.db.set_value("SCO Drawing Item",
                            {"parent": r0["subcontracting_order"], "parenttype": "Subcontracting Order",
                             "drawing": r0["drawing"]},
                            {"rate_per_kg": 12.5, "job_work_amount": 999.99}, update_modified=False)
        row = _row_for(execute({})[1], r0)
        check("the order's own rate and amount are shown as they stand",
              (row["rate_per_kg"], row["job_work_amount"]), (12.5, 999.99))
        frappe.db.set_value("SCO Drawing Item",
                            {"parent": r0["subcontracting_order"], "parenttype": "Subcontracting Order",
                             "drawing": r0["drawing"]},
                            "job_work_amount", 0, update_modified=False)
        row = _row_for(execute({})[1], r0)
        check("  a rate with no amount yet is priced at that rate",
              row["job_work_amount"], flt(flt(row["customer_weight_kg"], 3) * 12.5, 2))
    finally:
        frappe.db.rollback()

    print()
    print("=== the total row adds up ===")
    check("the report ends in one total row", (total or {}).get("sales_order"), "Total")
    if total:
        check("  job work amount is the sum of the drawings",
              total["job_work_amount"], flt(sum(flt(r["job_work_amount"]) for r in data), 2))
        check("  and so is Cust Weight (Total)",
              total["customer_weight_kg"], flt(sum(flt(r["customer_weight_kg"]) for r in data), 3))
        check("  a total has no single rate", (total.get("rate_schedule"), total.get("rate_per_kg")),
              (None, None))
        # Job-level columns repeat on every drawing of their job, so they count once
        # per job -- summing the column would count a two-drawing job twice.
        once = {}
        for r in data:
            once.setdefault(r["subcontracting_order"], r)
        check("  job-level figures count each job once",
              (total["excess_weight_kg"], total["consumable_cost"]),
              (flt(sum(flt(r["excess_weight_kg"]) for r in once.values()), 3),
               flt(sum(flt(r["consumable_cost"]) for r in once.values()), 2)))
        from manufyxinvenzaerp.production_management.report.production_report.production_report import (
            _waste_pct,
        )
        check("  Waste % is worked from the totals, not averaged",
              total["waste_pct"], _waste_pct(total["customer_weight_kg"], total["planned_weight_kg"]))
        # Filtered to one job, the total is that job's and nobody else's.
        one = (example or data[0])["subcontracting_order"]
        narrowed = execute({"subcontracting_order": one})[1]
        check("  filtered to %s, the total is that job's" % one,
              narrowed[-1]["job_work_amount"],
              flt(sum(flt(r["job_work_amount"]) for r in data if r["subcontracting_order"] == one), 2))

    print()
    print("=== the excess trio reconciles ===")
    # Excess, what came back, and what is still out there. Two categories now, not
    # three: Billed to Consume is gone, so anything that has not returned is simply
    # still out there -- to be returned, or written off as Process Loss with a
    # reason on the plan.
    for r in data:
        rows = _excess_rows(r["subcontracting_order"])
        booked = flt(sum(flt(x.qty) for x in rows), 3)
        back = flt(sum(flt(x.qty) for x in rows if x.stock_entry_created), 3)
        # Billed to Consume was a third category here and is gone: material that
        # does not come back is Process Loss now, declared on the plan with a reason.
        check("%s: booked" % r["subcontracting_order"], flt(r["excess_weight_kg"], 3), booked)
        check("  returned", flt(r["returned_excess_kg"], 3), back)
        check("  difference is what is left to chase",
              flt(r["excess_difference_kg"], 3), flt(booked - back, 3))
        break

    print()
    print("=== completed weight is the pieces done, at the drawing's own weight ===")
    for r in data:
        if not r["completed_nos"]:
            continue
        item = frappe.db.get_value(
            "SCO Drawing Item",
            {"parent": r["subcontracting_order"], "parenttype": "Subcontracting Order",
             "drawing": r["drawing"]},
            ["total_weight_kg", "qty_to_manufacture", "completed_qty_nos"], as_dict=True)
        if not (item and flt(item.qty_to_manufacture)):
            continue
        want = flt(flt(item.total_weight_kg) / flt(item.qty_to_manufacture)
                   * flt(item.completed_qty_nos), 3)
        check("%s %s" % (r["subcontracting_order"], r["drawing"]),
              flt(r["completed_drawing_weight_kg"], 3), want)
        break

    _summary()


def _taken_by_drawing():
    """Kg each drawing took, from its Material Issue Plan's own raw-material rows --
    the rows the report spreads a transfer's cost over -- keyed (job, drawing). Also
    each job's supplier warehouse, which is where its issued material lands."""
    took, supplier_wh = {}, {}
    for m in frappe.get_all("Material Issue Plan", filters={"subcontracting_order": ["is", "set"]},
                            fields=["name", "subcontracting_order", "supplier_warehouse"]):
        sco = m.subcontracting_order
        supplier_wh[sco] = m.supplier_warehouse
        drawing_by_duno = {
            (w.duno_mark_no or ""): w.drawing
            for w in frappe.get_all("SCO Drawing Item",
                                    filters={"parent": sco, "parenttype": "Subcontracting Order"},
                                    fields=["drawing", "duno_mark_no"])
            if w.drawing
        }
        for r in frappe.get_all("Material Issue Plan Raw Material", filters={"parent": m.name},
                                fields=["duno_mark_no", "transferred_qty"]):
            drawing = drawing_by_duno.get(r.duno_mark_no or "")
            if drawing:
                took[(sco, drawing)] = flt(took.get((sco, drawing))) + flt(r.transferred_qty)
    return took, supplier_wh


def _row_for(data, like):
    return next(r for r in _drawing_rows(data)
                if (r["subcontracting_order"], r["drawing"]) == (like["subcontracting_order"], like["drawing"]))


def _old_shape(soes):
    """What the row count used to be: one per drawing per operation."""
    for d in frappe.get_all("SOE Drawing Detail",
                            filters={"parent": ["in", [s.name for s in soes]]},
                            fields=["parent", "drawing"]):
        yield d


def _excess_rows(sco):
    mips = frappe.get_all("Material Issue Plan", filters={"subcontracting_order": sco}, pluck="name")
    if not mips:
        return []
    return frappe.get_all("SCO Excess Material Item",
                          filters={"parent": ["in", mips], "parenttype": "Material Issue Plan"},
                          fields=["qty", "stock_entry_created"])


def _summary():
    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
