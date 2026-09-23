"""Several sizes for one off-cut; Create Inspection from the Operation Entry; per-row
inspection results.

  1. Return Excess Entry: a Structurals/Plates row can carry extra dimension lines.
     Each becomes its own excess row, cloned under the original, so it is priced,
     received and batched like any other row. Claimed and weight-only rows refuse.
  2. Operation Entry: Create Inspection is a form button with a date popup; one call
     logs the round and creates the entry. Weight Summary in two columns, status and
     call date hidden, Inspection Entry under Connections.
  3. Inspection Entry: Feedback on every row (both tables), Rework Remarks on drawing
     rows, mandatory with a rejection. The header values are derived from the rows.
     Header in three columns, Contractor beside Supplier.

Everything runs inside ONE transaction that is rolled back (frappe.db.commit is a
no-op for the run), and tabSeries is compared before and after.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_inspection_rows_and_return_split.run
"""

import frappe
from frappe.utils import flt, nowdate, add_days

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, fragment):
    try:
        fn()
    except Exception as e:
        return fragment.lower() in frappe.utils.strip_html(str(e)).lower()
    return False


def _meta_fields(doctype):
    return {f.fieldname: f for f in frappe.get_meta(doctype).fields}


def _split():
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _split_extra_dimensions,
    )

    print("\n=== 1. Return Excess Entry: several sizes for one item ===")
    mip = frappe.new_doc("Material Issue Plan")
    base = {"item_code": "X-PLATE", "parent_item_group": "Plates", "thickness": 10,
            "unit_weight": 7.85, "return_reason": "Off-cut", "qty": 50, "sec_qty": 1}
    for name, extra in (("row-plate", {}), ("row-nuts", {"parent_item_group": "Nuts and Bolts"})):
        r = mip.append("excess_return_items", dict(base, **extra))
        r.name = name
    overrides = {
        "row-plate": {"name": "row-plate", "length": 1000, "width": 500, "sec_qty": 1, "return_reason": "Off-cut",
                      "extra_dimensions": [{"length": 600, "width": 400, "sec_qty": 2},
                                           {"length": 300, "width": 200, "sec_qty": 1}]},
    }
    _split_extra_dimensions(mip, overrides)
    rows = mip.excess_return_items
    check("two extra sizes -> two more rows", len(rows), 4)
    check("placed right under the original, before the next item",
          [r.parent_item_group for r in rows], ["Plates", "Plates", "Plates", "Nuts and Bolts"])
    check("rows renumbered", [r.idx for r in rows], [1, 2, 3, 4])
    clone = rows[1]
    check("clone keeps item, thickness, unit weight and reason",
          (clone.item_code, flt(clone.thickness), flt(clone.unit_weight), clone.return_reason),
          ("X-PLATE", 10.0, 7.85, "Off-cut"))
    check("clone is a NEW row (inserted on save, not lost)", bool(clone.get("__islocal")), True)
    check("clone has its own name, carrying its own dimensions",
          (overrides[clone.name]["length"], overrides[clone.name]["width"], overrides[clone.name]["sec_qty"]),
          (600, 400, 2))
    check("every row its own name (one batch each, traced to its row)",
          len({r.name for r in rows}), 4)

    def claimed():
        m = frappe.new_doc("Material Issue Plan")
        r = m.append("excess_return_items", dict(base, mapped_material_planning="MP-X"))
        r.name = "row-c"
        _split_extra_dimensions(m, {"row-c": {"extra_dimensions": [{"length": 1, "width": 1, "sec_qty": 1}]}})
    check("a claimed row refuses extra sizes", _throws(claimed, "claimed"), True)

    def weight_only():
        m = frappe.new_doc("Material Issue Plan")
        r = m.append("excess_return_items", dict(base, enter_weight_instead_of_pieces=1))
        r.name = "row-w"
        _split_extra_dimensions(m, {"row-w": {"extra_dimensions": [{"length": 1, "width": 1, "sec_qty": 1}]}})
    check("a weight-only row refuses extra sizes", _throws(weight_only, "weight"), True)

    js = open(frappe.get_app_path(
        "manufyxinvenzaerp", "subcontracting_management", "doctype", "material_issue_plan",
        "material_issue_plan.js")).read()
    check("dialog: duplicate icon, extra lines, planned/returning/difference",
          all(k in js for k in ("_rex_dup", "_rex_extra", "extra_dimensions", "Returning", "Difference")), True)


def _soe_layout():
    print("\n=== 2. Operation Entry layout ===")
    meta = frappe.get_meta("Supplier Operation Entry")
    order = [f.fieldname for f in meta.fields]
    i = order.index("total_completed_nos")
    check("column break between the NOS pair and the Kg pair",
          order[i + 1: i + 3], ["column_break_summary_kg", "available_to_consume_kg"])
    j = order.index("create_inspection_btn")
    check("Create Inspection button directly above the Consumption Log",
          (order[j - 1], order[j + 1]), ("section_break_log", "consumption_log"))
    f = _meta_fields("Supplier Operation Entry")
    check("Inspection Status and Call Date hidden",
          (f["custom_inspection_status"].hidden, f["custom_inspection_call_date"].hidden), (1, 1))
    check("Inspection Entry under Connections",
          [(l.link_doctype, l.link_fieldname) for l in meta.links],
          [("Inspection Entry", "supplier_operation_entry")])
    js = open(frappe.get_app_path("manufyxinvenzaerp", "public", "js", "supplier_operation_entry.js")).read()
    check("toolbar Create Inspection removed (View stays)",
          ('add_custom_button(__("Create Inspection")' in js, "View Inspection Entry" in js), (False, True))


def _soe_create_inspection():
    from manufyxinvenzaerp.production_management.inspection import create_soe_inspection

    print("\n=== 2b. Create Inspection: one call, round + entry ===")
    check("no date -> refused", _throws(lambda: create_soe_inspection("x", None), "call date"), True)

    sub = frappe.db.get_value("Supplier Operation Entry", {"docstatus": 1, "custom_inspection_mandatory": 1}, "name")
    if sub:
        check("a submitted Operation Entry refuses", _throws(lambda: create_soe_inspection(sub, nowdate()), "draft"), True)

    soe = frappe.db.get_value(
        "Supplier Operation Entry", {"docstatus": 0, "custom_inspection_mandatory": 1}, "name")
    if not soe:
        print("  SKIP no draft Operation Entry with inspection")
        return
    items = frappe.get_all("SOE Inspection Item", filters={"parent": soe, "parenttype": "Supplier Operation Entry"},
                           fields=["name", "drawing"])
    log = frappe.get_all("Inspection Call Log", filters={"parent": soe, "parenttype": "Supplier Operation Entry"},
                         fields=["name", "round_status", "inspection_entry"])
    if not items or not log:
        print("  SKIP %s has no inspection items or call log to borrow" % soe)
        return

    # A round still open with its entry refuses a new one.
    frappe.db.set_value("Inspection Call Log", log[-1].name, {"round_status": "Pending"})
    check("an open round with its entry refuses", _throws(lambda: create_soe_inspection(soe, nowdate()), "still open"), True)

    # A round logged without an entry is reused, with the date picked in the popup.
    frappe.db.set_value("Inspection Call Log", log[-1].name, {"inspection_entry": None})
    for it in items:
        frappe.db.set_value("SOE Inspection Item", it.name, "qty_nos", 2)
    frappe.db.set_value("Supplier Operation Entry", soe, "contractor", None)
    when = add_days(nowdate(), 1)
    name = create_soe_inspection(soe, when)
    entry = frappe.get_doc("Inspection Entry", name)
    check("entry created for the pending drawings", sorted(r.drawing for r in entry.soe_items),
          sorted(i.drawing for i in items))
    check("entry and round carry the popup's date",
          (str(entry.call_date), str(frappe.db.get_value("Inspection Call Log", log[-1].name, "call_date"))),
          (str(when), str(when)))
    check("round linked to the new entry",
          frappe.db.get_value("Inspection Call Log", log[-1].name, "inspection_entry"), name)
    return entry


def _entry_rules(entry):
    print("\n=== 3. Inspection Entry: per-row results ===")
    f = _meta_fields("SOE Inspection Item")
    check("drawing rows: Feedback + Rework Remarks in the grid",
          (f["feedback"].in_list_view, f["rework_remarks"].in_list_view), (1, 1))
    check("Rework Remarks mandatory with a rejection", f["rework_remarks"].mandatory_depends_on, "eval:doc.reject_qty>0")
    g = _meta_fields("Inspection Entry Item")
    check("item rows: Feedback in the grid", g["feedback"].in_list_view, 1)
    for dt in ("SOE Inspection Item", "Inspection Entry Item"):
        width = sum(flt(x.columns) or 2 for x in frappe.get_meta(dt).fields if x.in_list_view and not x.hidden)
        check("%s grid fits 11 columns" % dt, width <= 11, True)

    h = _meta_fields("Inspection Entry")
    check("header: Contractor added", h["contractor"].options, "Contractor")
    order = [x.fieldname for x in frappe.get_meta("Inspection Entry").fields]
    top = order[: order.index("section_break_status")]
    check("header in three columns", sum(1 for x in top if h[x].fieldtype == "Column Break"), 2)
    check("header Feedback / Rework Remarks only for a Job Card",
          (h["feedback"].depends_on, h["section_break_remarks"].depends_on),
          ('eval:doc.source_doctype=="Job Card"', 'eval:doc.source_doctype=="Job Card"'))

    if not entry:
        print("  SKIP live row rules (no entry created above)")
        return
    entry.__dict__.pop("__islocal", None)
    r0 = entry.soe_items[0]

    r0.accept_qty, r0.feedback = 1, "Ok"          # 1 of 2 rejected, yet Ok
    check("row Ok with a rejection -> refused", _throws(entry.validate, "cannot be ok"), True)
    for r in entry.soe_items:
        r.accept_qty, r.feedback, r.rework_remarks = 2, "Not Ok", ""
    check("row Not Ok with nothing rejected -> refused", _throws(entry.validate, "cannot be not ok"), True)
    r0.accept_qty, r0.feedback = 1, "Not Ok"
    for r in entry.soe_items[1:]:
        r.feedback = "Ok"
    check("rejection without Rework Remarks -> refused", _throws(entry.validate, "rework remarks"), True)
    r0.rework_remarks = "weld bead uneven"
    entry.validate()
    check("header Feedback derived: Not Ok when a row is Not Ok", entry.feedback, "Not Ok")
    check("header Rework Remarks derived from the rows",
          entry.rework_remarks, "%s: weld bead uneven" % (r0.customer_drawing_number or r0.drawing))

    entry.status = "Completed"
    entry.soe_items[-1].feedback = ""
    check("submit refused while a row has no Feedback", _throws(entry.before_submit, "feedback"), True)
    r0.accept_qty, r0.feedback = 2, ""
    for r in entry.soe_items:
        r.accept_qty = 2
    entry.soe_items[0].feedback = "Ok"
    entry.validate()
    check("header blank until every row has Feedback",
          entry.feedback if len(entry.soe_items) > 1 else "", "")
    for r in entry.soe_items:
        r.feedback = "Ok"
    entry.validate()
    check("header Ok once every row is Ok", entry.feedback, "Ok")
    check("and no Rework Remarks without a rejection", entry.rework_remarks, "")


def _patch():
    from manufyxinvenzaerp.patches.v1.inspection_feedback_to_rows import execute

    print("\n=== patch ===")
    q = "select name, feedback, rework_remarks from `tabSOE Inspection Item` order by name"
    before = frappe.db.sql(q)
    execute()
    check("running the patch again changes nothing", frappe.db.sql(q) == before, True)
    left = frappe.db.sql("""select count(*) from `tabSOE Inspection Item` c join `tabInspection Entry` p
        on p.name = c.parent where p.docstatus = 1 and ifnull(p.feedback,'') != '' and ifnull(c.feedback,'') = ''""")[0][0]
    check("every submitted entry's rows have Feedback", left, 0)
    wrong = frappe.db.sql("""select count(*) from `tabSOE Inspection Item` c join `tabInspection Entry` p
        on p.name = c.parent where p.docstatus = 1 and c.feedback = 'Not Ok' and ifnull(c.reject_qty, 0) <= 0""")[0][0]
    check("no row Not Ok with nothing rejected", wrong, 0)


def run():
    print("=== verify_inspection_rows_and_return_split ===")
    series_before = frappe.db.sql("select name, current from tabSeries order by name")
    real_commit = frappe.db.commit
    frappe.db.commit = lambda *a, **k: None
    try:
        _split()
        _soe_layout()
        entry = _soe_create_inspection()
        _entry_rules(entry)
        _patch()
    finally:
        frappe.db.rollback()
        frappe.db.commit = real_commit
    series_after = frappe.db.sql("select name, current from tabSeries order by name")
    check("no naming-series number used", series_before == series_after, True)

    print()
    failed = checks.count(False)
    if failed:
        print("%d of %d CHECKS FAILED" % (failed, len(checks)))
    else:
        print("ALL %d CHECKS PASSED" % len(checks))
