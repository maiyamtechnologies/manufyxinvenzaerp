"""The 2026-09-24 change request: spec/grade checks, grid columns, per-operation party, MIP NOS.

1. The Sales Order BOM sheet gains a Material Spec column, and Verify Raw Materials
   refuses a row whose sheet spec or grade is not the one on that Material Code's
   Item. Spec and grade travel from the Item onto every document downstream by
   fetch_from, so a sheet asking for E350 against an E250 Item would otherwise plan,
   buy and receive E250 without anyone having decided that. The row's material_spec
   stopped being fetched from the Item for the same reason -- a fetch would overwrite
   the very value the check compares.
2. An Item's spec and grade lock once it has transactions (item._LOCKED_FIELDS).
3. Spec and Grade are shown in the Material Planning Raw Material and Consolidate
   grids -- and both still fit the 11-column budget, which silently drops columns.
4. Target Storage Location (the bin) is shown in the Purchase Receipt grid.
5. Each Process Planning row names who does the operation -- a Supplier for a
   Subcontractor row, a new Contractor master for an Internal Jobcard row --
   mandatory at SUBMIT (drafts are created from the BOM routing before anyone could
   know), carried onto that operation's Supplier Operation Entry, and shown on the
   Job Work Order's Operations table.
7. The MIP transfer popups show Available NOS beside In Stock (Kg), at the same piece
   weight the popup already converts NOS with.
(6, Stock UOM in the Stock Entry grid, is covered by verify_nos_labels.)

Everything is rolled back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_change_request_2026_09_24.run
"""

import inspect

import frappe
from frappe.utils import flt

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


def _grid(doctype):
    shown, total = [], 1
    for f in frappe.get_meta(doctype).fields:
        if f.hidden or not f.in_list_view or f.fieldtype in ("Section Break", "Column Break", "Tab Break"):
            continue
        # grid.js update_default_colsize: 2, Text/Small Text 3, Check 1.
        total += f.columns or (3 if f.fieldtype in ("Text", "Small Text") else (1 if f.fieldtype == "Check" else 2))
        if total <= 11:
            shown.append(f.fieldname)
    return shown, total


def run():
    try:
        _run()
    finally:
        frappe.db.rollback()
        print()
        print("  (rolled back -- this check leaves no trace)")
    _summary()


def _so(rows):
    """A stand-in Sales Order holding only raw-material rows, as the checks read them."""
    return frappe._dict(custom_so_raw_materials=[
        frappe._dict(dict(r, idx=i, is_locked=0, customer_drawing_number="CDN-T"))
        for i, r in enumerate(rows, 1)])


def _run():
    from manufyxinvenzaerp.drawing_management import so_drawing_import as imp

    print("=== 1. Sheet Material Spec, and the spec/grade check ===")
    tpl = inspect.getsource(imp.download_bom_template)
    check("the template has a Material Spec column beside Grade",
          '"Material Code", "Material Spec", "Grade"' in tpl, True)
    f = frappe.get_meta("Sales Order Drawing Raw Material").get_field("material_spec")
    check("the row's spec is the sheet's own (a Link, not fetched)",
          (f.fieldtype, f.options, bool(f.fetch_from)), ("Link", "Material Spec", False))
    verify_src = inspect.getsource(imp.verify_raw_materials)
    check("Verify runs both new checks",
          "_check_raw_material_specs(so)" in verify_src and "_check_item_spec_grade(so)" in verify_src, True)

    item = frappe.db.get_value(
        "Item", {"custom_material_spec": ["is", "set"], "custom_material_grade": ["is", "set"]},
        ["name", "custom_material_spec", "custom_material_grade"], as_dict=True)
    if not item:
        print("    (no Item carries both a spec and a grade -- match/mismatch not exercised)")
    else:
        same = _so([{"material_code": item.name, "material_spec": item.custom_material_spec,
                     "grade": item.custom_material_grade}])
        check("  a row matching its Item passes", imp._check_item_spec_grade(same), [])
        other_grade = frappe.db.get_value("Material Grade", {"name": ["!=", item.custom_material_grade]}, "name")
        if other_grade:
            bad = _so([{"material_code": item.name, "material_spec": "", "grade": other_grade}])
            issues = imp._check_item_spec_grade(bad)
            check("  a row asking for another grade is blocked", len(issues), 1)
            check("  and the message says it is not in the Item master",
                  "not in the item master" in frappe.utils.strip_html(str(issues)).lower(), True)
        blank = _so([{"material_code": item.name, "material_spec": "", "grade": ""}])
        check("  a blank sheet spec/grade is not checked", imp._check_item_spec_grade(blank), [])
    check("  a Material Code that is no Item is left to the master check",
          imp._check_item_spec_grade(_so([{"material_code": "ZZ-NO-ITEM", "grade": "X"}])), [])
    check("  a spec not in the Material Spec master is refused",
          len(imp._check_raw_material_specs(_so([{"material_code": "X", "material_spec": "ZZ-NO-SPEC"}]))), 1)
    real_spec = frappe.db.get_value("Material Spec", {}, "name")
    if real_spec:
        check("  a spec in the master passes",
              imp._check_raw_material_specs(_so([{"material_code": "X", "material_spec": real_spec}])), [])

    print()
    print("=== 2. Item spec/grade lock after transactions ===")
    from manufyxinvenzaerp.item_management import item as item_mod
    # Locked once SET, not outright: every Item in use had neither set when the lock
    # arrived, so filling a blank one in has to stay possible (item._LOCK_ONCE_SET).
    check("both lock once set",
          {"custom_material_spec", "custom_material_grade"} <= set(item_mod._LOCK_ONCE_SET), True)
    check("  and the existing locked fields are unchanged (still locked outright)",
          set(item_mod._LOCKED_FIELDS), {"custom_parent_item_group", "stock_uom", "custom_unit_weight",
                                         "custom_secondary_uom", "custom_batch_prefix"})
    js = open(frappe.get_app_path("manufyxinvenzaerp", "public", "js", "item.js")).read()
    check("  the form greys them out only once they hold a value",
          "LOCK_ONCE_SET_FIELDS" in js and "if (frm.doc[field])" in js, True)
    used = frappe.db.sql_list("""
        SELECT i.name FROM `tabItem` i
        WHERE EXISTS (SELECT 1 FROM `tabStock Ledger Entry` s WHERE s.item_code = i.name) LIMIT 1""")
    specs = frappe.get_all("Material Spec", pluck="name", limit=2)
    if used and len(specs) == 2:
        name = used[0]
        frappe.db.set_value("Item", name, "custom_material_spec", None, update_modified=False)
        doc = frappe.get_doc("Item", name)
        doc.custom_material_spec = specs[0]
        check("  an Item in use can have a BLANK spec filled in",
              not _throws(lambda: item_mod.validate_locked_fields(doc), "transactions already exist"), True)
        frappe.db.set_value("Item", name, "custom_material_spec", specs[0], update_modified=False)
        doc = frappe.get_doc("Item", name)
        doc.custom_material_spec = specs[1]
        check("  but a spec once set cannot be changed",
              _throws(lambda: item_mod.validate_locked_fields(doc), "transactions already exist"), True)
        doc = frappe.get_doc("Item", name)
        doc.stock_uom = "Nos" if doc.stock_uom != "Nos" else "Kg"
        check("  and a strictly locked field is still refused as before",
              _throws(lambda: item_mod.validate_locked_fields(doc), "transactions already exist"), True)
    else:
        print("    (no Item in use, or fewer than two specs -- lock not exercised)")

    print()
    print("=== 3. Spec and Grade in the Material Planning grids ===")
    for dt, must in (("Material Planning Raw Material", ["material_spec", "material_grade", "qty"]),
                     ("Material Planning Consolidate Item", ["material_spec", "material_grade", "item_code"])):
        frappe.clear_cache(doctype=dt)
        shown, total = _grid(dt)
        check("%s fits the budget" % dt, total <= 11, True)
        check("  and shows %s" % ", ".join(must), all(m in shown for m in must), True)
    # The values in MR/PO/PR are the Item's own, by the same fetch, so they cannot drift.
    for dt in ("Material Request Item", "Purchase Order Item", "Purchase Receipt Item"):
        m = frappe.get_meta(dt)
        check("%s spec/grade come from the Item" % dt,
              (m.get_field("custom_material_spec").fetch_from, m.get_field("custom_material_grade").fetch_from),
              ("item_code.custom_material_spec", "item_code.custom_material_grade"))

    print()
    print("=== 4. Purchase Receipt grid shows the bin ===")
    frappe.clear_cache(doctype="Purchase Receipt Item")
    shown, total = _grid("Purchase Receipt Item")
    check("Target Storage Location and Warehouse are shown",
          ("storage_location" in shown, "warehouse" in shown), (True, True))
    check("  within the budget", total <= 11, True)

    print()
    print("=== 5. Supplier/Contractor per operation ===")
    c = frappe.get_meta("Contractor")
    check("Contractor master has name, address, contact, remarks",
          all(c.get_field(fn) for fn in ("contractor_name", "address", "contact_number", "remarks")), True)
    pp_meta = frappe.get_meta("Process Planning")
    party = pp_meta.get_field("party")
    check("Process Planning has a Supplier/Contractor Dynamic Link in the grid",
          (party.fieldtype, party.options, bool(party.in_list_view), party.label),
          ("Dynamic Link", "party_type", True, "Supplier/Contractor"))
    order = [f.fieldname for f in pp_meta.fields]
    check("  placed right after Work Type", order.index("party") == order.index("work_type") + 2, True)
    check("  not a field-level reqd (drafts are made from the routing)", bool(party.reqd), False)

    from manufyxinvenzaerp.production_plan_management.production_plan import (
        _check_row_party, before_submit_process_planning,
    )
    r = frappe._dict(idx=1, operation_name="Fit-up", work_type="Internal Jobcard", party="", party_type="")
    _check_row_party(r)
    check("  an Internal Jobcard row takes party type Contractor", r.party_type, "Contractor")
    r = frappe._dict(idx=1, operation_name="Fit-up", work_type="Subcontractor", party="", party_type="")
    _check_row_party(r)
    check("  a Subcontractor row takes party type Supplier", r.party_type, "Supplier")
    wrong = frappe._dict(idx=1, operation_name="Fit-up", work_type="Internal Jobcard",
                         party="Some Supplier", party_type="Supplier")
    check("  a Supplier left on an Internal Jobcard row is refused",
          _throws(lambda: _check_row_party(wrong), "does not match") or
          _throws(lambda: _check_row_party(wrong), "needs a contractor"), True)
    pp = frappe._dict(custom_process_planning=[
        frappe._dict(idx=1, operation_name="Fit-up", work_type="Internal Jobcard", party="")])
    check("  submitting with a row missing its party is refused",
          _throws(lambda: before_submit_process_planning(pp), "supplier/contractor"), True)
    pp.custom_process_planning[0].party = "Anyone"
    check("  and allowed once every row has one",
          not _throws(lambda: before_submit_process_planning(pp), "supplier/contractor"), True)
    hooks = frappe.get_hooks("doc_events").get("Production Plan", {})
    check("  the submit check is wired in",
          any("before_submit_process_planning" in h for h in (hooks.get("before_submit") or [])), True)

    soe = frappe.get_meta("Supplier Operation Entry").get_field("contractor")
    check("Operation Entry has a Contractor field", (soe.fieldtype, soe.options), ("Link", "Contractor"))
    from manufyxinvenzaerp.subcontracting_management import subcontracting as sub
    src = inspect.getsource(sub._create_soes_for_sco)
    check("  each entry takes its own row's party",
          'op_row.get("party")' in src and '"contractor": contractor' in src, True)
    check("  a subcontracted row with no party keeps the Job Work Order's supplier",
          "else sco.supplier" in src, True)
    check("  the Operations summary sends supplier and contractor",
          '"supplier", "contractor"' in inspect.getsource(sub.get_soe_summary), True)
    from manufyxinvenzaerp.setup import SCO_OPS_SCRIPT
    check("  and the Job Work Order's Operations table shows the column",
          "Supplier/Contractor" in SCO_OPS_SCRIPT and "d.supplier || d.contractor" in SCO_OPS_SCRIPT, True)

    print()
    print("=== 7. MIP transfer popup: Available NOS ===")
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _available_nos, get_mip_pending_items,
    )
    check("no piece weight gives a dash, not an invented number",
          _available_nos({"available_qty": 100}, 0), None)
    check("a remnant is shown as it is, not rounded to whole pieces",
          _available_nos({"available_qty": 90}, 25), 3.6)
    mip = frappe.db.get_value("Material Issue Plan", {}, "name", order_by="creation desc")
    rows = []
    if mip:
        try:
            rows = get_mip_pending_items(mip)
        except Exception:
            rows = []
    if rows:
        r = rows[0]
        check("  a live row carries available_nos", "available_nos" in r, True)
        if flt(r.get("kg_per_piece")) > 0:
            check("  = In Stock Kg / the popup's own piece weight",
                  flt(r["available_nos"], 3), flt(flt(r["available_qty"]) / flt(r["kg_per_piece"]), 3))
    else:
        print("    (no MIP with pending rows on this site -- live row not exercised)")
    mip_js = open(frappe.get_app_path(
        "manufyxinvenzaerp", "subcontracting_management", "doctype",
        "material_issue_plan", "material_issue_plan.js")).read()
    check("  the popup has the Available NOS column", '__("Available NOS")' in mip_js, True)
    tsrc = inspect.getsource(
        __import__("manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer",
                   fromlist=["x"]).get_mip_cnc_pending_items)
    check("  CNC-forward rows priced WITHOUT gaining a kg_per_piece key",
          'row["available_nos"]' in tsrc and 'row["kg_per_piece"]' not in tsrc, True)


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
