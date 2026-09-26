"""The transfer popup's excess tab takes an off-cut in several sizes.

WHY: Return Excess Entry could split a returning off-cut into several sizes (the
duplicate icon, cae8050), but the plan made at transfer time -- the popup's
"Consolidate item for excess return plan" tab -- took one size per item. An off-cut
cut into two lengths had to be planned as one and corrected at return. The tab now
has the same duplicate icon; each size is sent as `extra` on the item's plan entry,
parked with the draft, and booked as its own excess row.

In memory for the booking (the plan's save is stubbed out), and inside a rolled-back
transaction with commits stubbed for the draft round trip.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_excess_plan_sizes.run
"""

import json

import frappe
from frappe.utils import flt

checks = []

MIP = "MIP-2026-00007"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    print("=== verify_excess_plan_sizes ===")
    real_commit = frappe.db.commit
    frappe.db.commit = lambda *a, **k: None
    try:
        _booking()
        _return_na()
        _return_na_limit()
        _draft()
        _client()
    finally:
        frappe.db.commit = real_commit
        frappe.db.rollback()
    print()
    failed = checks.count(False)
    print(("%d of %d CHECKS FAILED" % (failed, len(checks))) if failed else "ALL %d CHECKS PASSED" % len(checks))


def _line(code="ISA100", qty=238.251, drawing=223.798):
    # ISA100: 14.9 Kg per metre, so 1000 mm x 1 Nos = 14.9 Kg.
    return {"item_code": code, "item_name": code, "qty": qty, "drawing_planned_weight": drawing,
            "custom_parent_item_group": "Structurals", "custom_unit_weight": 14.9,
            "custom_thickness": 0, "custom_sec_uom": "Nos", "uom": "Kg"}


def _book(plan):
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _log_consolidated_excess,
    )
    mip = frappe.new_doc("Material Issue Plan")
    mip.source_warehouse = "Stores - MIPL"
    mip.save = lambda *a, **k: None
    _log_consolidated_excess(mip, [_line()], plan)
    return mip.excess_return_items


def _booking():
    print("=== booking at transfer ===")
    rows = _book({"ISA100": {"length": 500, "sec_qty": 1}})
    check("one size: one row, as before", [(r.source_row, flt(r.length), flt(r.qty)) for r in rows],
          [("ISA100", 500.0, 7.45)])

    rows = _book({"ISA100": {"length": 500, "sec_qty": 1,
                             "extra": [{"length": 300, "sec_qty": 2}, {"length": 150, "sec_qty": 1}]}})
    check("three sizes: three rows", len(rows), 3)
    check("...each its own size and Kg",
          [(r.source_row, flt(r.length), flt(r.sec_qty), flt(r.qty)) for r in rows],
          [("ISA100", 500.0, 1.0, 7.45), ("ISA100|size 2", 300.0, 2.0, 8.94),
           ("ISA100|size 3", 150.0, 1.0, 2.235)])
    check("...all of the same item", {r.item_code for r in rows}, {"ISA100"})
    check("...the reason names the total and the sizes",
          all("18.625 Kg was measured" in r.return_reason and "3 sizes" in r.return_reason for r in rows), True)

    rows = _book({"ISA100": {"length": 500, "sec_qty": 1, "extra": [{"length": 300, "sec_qty": 0}]}})
    check("a size with no NOS books nothing for it", [r.source_row for r in rows], ["ISA100"])

    rows = _book({"ISA100": {"length": 500, "sec_qty": 1, "extra": [{"length": 300, "sec_qty": 2}]}})
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _log_consolidated_excess,
    )
    mip = frappe.new_doc("Material Issue Plan")
    mip.save = lambda *a, **k: None
    plan = {"ISA100": {"length": 500, "sec_qty": 1, "extra": [{"length": 300, "sec_qty": 2}]}}
    _log_consolidated_excess(mip, [_line()], plan)
    _log_consolidated_excess(mip, [_line()], plan)
    check("a second transfer accumulates into the same size rows",
          [(r.source_row, flt(r.sec_qty), flt(r.qty)) for r in mip.excess_return_items],
          [("ISA100", 2.0, 14.9), ("ISA100|size 2", 4.0, 17.88)])

    rows = _book({"ISA100": {"length": 500, "sec_qty": 1, "extra": [{"length": 300, "sec_qty": 2}]}})
    none = frappe.new_doc("Material Issue Plan")
    none.save = lambda *a, **k: None
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _log_consolidated_excess as book,
    )
    book(none, [_line(qty=223.798)], {"ISA100": {"length": 500, "sec_qty": 1,
                                                 "extra": [{"length": 300, "sec_qty": 2}]}})
    check("no system excess: nothing booked, sizes or not", len(none.excess_return_items), 0)


def _return_na():
    print()
    print("=== Return NA: not coming back, to Process Loss ===")
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _log_consolidated_excess, _log_round_up_excess, get_mip_process_loss_state,
    )
    if not frappe.db.exists("Material Issue Plan", MIP):
        print("  SKIP %s is not on this site" % MIP)
        return
    mip = frappe.new_doc("Material Issue Plan")
    mip.name = MIP  # the log entry points at a real plan; everything is rolled back
    mip.source_warehouse = "Stores - MIPL"
    mip.save = lambda *a, **k: None
    plan = {"ISA100": {"return_na": 1}}
    before = frappe.db.count("Manufyx Decision Log", {"action": "Return NA at Transfer", "reference_name": MIP})
    _log_consolidated_excess(mip, [_line()], plan)
    check("no excess return row is booked", len(mip.excess_return_items), 0)
    logged = frappe.get_all("Manufyx Decision Log",
                            filters={"action": "Return NA at Transfer", "reference_name": MIP},
                            fields=["item_code", "qty"], order_by="creation desc", limit=1)
    check("the weight is logged as Return NA",
          (frappe.db.count("Manufyx Decision Log", {"action": "Return NA at Transfer", "reference_name": MIP}) - before,
           logged[0].item_code if logged else None, flt(logged[0].qty) if logged else None),
          (1, "ISA100", 14.453))

    rounded = dict(_line(), batch_no="ISA100-L390-R009", round_up_excess_kg=2.5,
                   round_up_excess_pieces=0.43, planned_sec_qty=38.5, custom_sec_qty=39,
                   custom_length=390)
    mip2 = frappe.new_doc("Material Issue Plan")
    mip2.name = MIP
    mip2.save = lambda *a, **k: None
    import manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer as t
    real = t._apply_transfer_excess_to_raw_materials
    t._apply_transfer_excess_to_raw_materials = lambda *a, **k: None
    try:
        _log_round_up_excess(mip2, [rounded], excess_plan=plan)
    finally:
        t._apply_transfer_excess_to_raw_materials = real
    check("a rounding surplus on it is not booked to return either", len(mip2.excess_return_items), 0)

    state = get_mip_process_loss_state(MIP)
    check("Process Loss names the Return NA weight",
          ("ISA100", 14.453) in [(r["item_code"], r["qty"]) for r in state["return_na"]], True)

    none = frappe.new_doc("Material Issue Plan")
    none.name = MIP
    none.save = lambda *a, **k: None
    n0 = frappe.db.count("Manufyx Decision Log", {"action": "Return NA at Transfer", "reference_name": MIP})
    _log_consolidated_excess(none, [_line(qty=223.798)], plan)
    check("no system excess: nothing logged",
          frappe.db.count("Manufyx Decision Log", {"action": "Return NA at Transfer", "reference_name": MIP}) - n0, 0)


def _refused(fn):
    try:
        fn()
    except frappe.ValidationError as e:
        return str(e)
    return None


def _return_na_limit():
    print()
    print("=== Return NA only under the Settings limit ===")
    import inspect
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as t

    frappe.db.set_single_value("Manufyxinvenza Settings", "excess_return_na_below_kg", 1)  # rolled back
    na = {"ISA100": {"return_na": 1}}
    small = [_line(qty=224.298)]          # 0.5 Kg over the drawings
    large = [_line()]                     # 14.453 Kg over
    check("0.5 Kg excess, limit 1 Kg: allowed", _refused(lambda: t._validate_return_na(small, na)), None)
    msg = _refused(lambda: t._validate_return_na(large, na)) or ""
    check("14.453 Kg excess, limit 1 Kg: refused, naming the item and weight",
          "less than 1.0 Kg" in msg and "ISA100" in msg and "14.453" in msg, True)
    check("exactly at the limit is not under it",
          bool(_refused(lambda: t._validate_return_na([_line(qty=224.798)], na))), True)
    check("an item without Return NA is not checked",
          _refused(lambda: t._validate_return_na(large, {"ISA100": {"length": 500, "sec_qty": 1}})), None)
    frappe.db.set_single_value("Manufyxinvenza Settings", "excess_return_na_below_kg", 0)
    check("limit 0: Return NA allowed nowhere", bool(_refused(lambda: t._validate_return_na(small, na))), True)

    src = inspect.getsource(t.create_mip_partial_transfer)
    check("checked before the transfer commits anything",
          0 < src.index("_validate_return_na(") < src.rindex("frappe.db.commit()"), True)  # rindex: the docstring names it too


def _draft():
    print()
    print("=== parked with Save and Close ===")
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        get_transfer_draft, save_transfer_draft,
    )
    if not frappe.db.exists("Material Issue Plan", MIP):
        print("  SKIP %s is not on this site" % MIP)
        return
    row = frappe.get_all("Material Issue Plan Consolidate Item", filters={"parent": MIP},
                         fields=["item_code", "batch_no", "cnc_process"], limit=1)[0]
    extra = [{"length": 300, "width": 0, "sec_qty": 2}]
    save_transfer_draft(MIP, json.dumps([{"item_code": row.item_code, "batch_no": row.batch_no,
                                          "cnc_process": row.cnc_process, "custom_sec_qty": 1}]),
                        json.dumps({row.item_code: {"length": 500, "sec_qty": 1, "extra": extra}}))
    got = get_transfer_draft(MIP)
    saved = got.get("%s|%s|%s" % (row.item_code, row.batch_no or "", 1 if row.cnc_process else 0)) or {}
    check("the first size comes back", (flt(saved.get("draft_excess_length")), flt(saved.get("draft_excess_sec_qty"))),
          (500.0, 1.0))
    check("the extra sizes come back", json.loads(saved.get("draft_excess_extra_sizes") or "[]"), extra)

    save_transfer_draft(MIP, json.dumps([{"item_code": row.item_code, "batch_no": row.batch_no,
                                          "cnc_process": row.cnc_process, "custom_sec_qty": 1}]),
                        json.dumps({row.item_code: {"return_na": 1}}))
    saved = get_transfer_draft(MIP).get("%s|%s|%s" % (row.item_code, row.batch_no or "", 1 if row.cnc_process else 0)) or {}
    check("Return NA comes back ticked", saved.get("draft_excess_return_na"), 1)


def _client():
    print()
    print("=== the popup ===")
    js = open(frappe.get_app_path("manufyxinvenzaerp", "subcontracting_management", "doctype",
                                  "material_issue_plan", "material_issue_plan.js")).read()
    check("the excess tab has the duplicate icon", "mip-xs-dup" in js and '"Add another size for this item"' in js, True)
    check("each extra size can be removed", "mip-xs-remove" in js, True)
    check("the extra sizes are sent to the server", "extra: extra" in js, True)
    check("a half-typed size blocks the transfer", "extra_bad" in js, True)
    check("the draft restores the extra sizes", "draft_excess_extra_sizes" in js, True)
    check("the excess tab has the Return NA box", "mip-xs-na" in js and '__("Return NA")' in js, True)
    check("Return NA needs no dimensions at Transfer", "if (plan.return_na) return;" in js, True)
    check("the Process Loss dialog names it", "of which marked Return NA at transfer" in js, True)
    check("the box opens only under the Settings limit",
          "var na_allowed = !no_excess && na_limit > 0 && sys < na_limit;" in js
          and '"excess_return_na_below_kg"' in js, True)
    check("a draft tick over the limit is dropped", "if (saved.return_na && !na_allowed" in js, True)
