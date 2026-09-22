"""The Final Stock Entry records what went in against what came out.

A Manufacture entry consumes steel from the supplier warehouse and produces finished
goods. The two weights are not the same and never will be: the cut list is what the
drawing needs, the customer's figure is what they agreed to pay for, and the difference
is burn, kerf and grinding. Until now nothing recorded it -- the gap simply disappeared
into the finished item's valuation rate, so a job could book a quarter of the steel it
ate and no document said so.

It cannot be a stock movement. The same entry has already consumed the material; issuing
the difference again would take it twice and drive the warehouse negative. So it is a
figure: custom_loss_kg on the finished-goods row, totalled onto the plan as
loss_weight_kg, deliberately separate from process_loss_weight_kg -- that one is off-cut
still standing at the supplier and does need a Material Issue.

Signed on purpose. Positive is weight that went in and did not come out. Negative means
more was booked than consumed, which is not a loss at all: it says the Sales Order was
written for too little, and the popup says so rather than refusing.

The weight is entered in the popup and nowhere else. On the draft it is read-only,
because the popup is the only screen that shows the consumed steel beside it.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_loss_and_edit.run
"""

import inspect
import os

import frappe
from frappe.utils import flt

checks = []

SCO = "SC-ORD-2026-00025"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-60s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _js(*parts):
    return open(os.path.join(frappe.get_app_path("manufyxinvenzaerp"), *parts)).read()


def run():
    from manufyxinvenzaerp.subcontracting_management import subcontracting as sub
    from manufyxinvenzaerp.production_management import fg_stock

    print("=== the fields exist and are not typed into ===")
    sed = frappe.get_meta("Stock Entry Detail").get_field("custom_loss_kg")
    check("Stock Entry Detail.custom_loss_kg", bool(sed), True)
    if sed:
        check("   ...Float and read-only", (sed.fieldtype, sed.read_only), ("Float", 1))
    mip_f = frappe.get_meta("Material Issue Plan").get_field("loss_weight_kg")
    check("Material Issue Plan.loss_weight_kg", bool(mip_f), True)
    if mip_f:
        check("   ...Float and read-only", (mip_f.fieldtype, mip_f.read_only), ("Float", 1))
    check("it is NOT the same field as the supplier write-off",
          bool(frappe.get_meta("Material Issue Plan").get_field("process_loss_weight_kg")), True)

    print()
    print("=== the loss is a figure, not a second stock movement ===")
    src = inspect.getsource(sub._final_fg_rows)
    check("stamped on the finished-goods row", '"custom_loss_kg"' in src, True)
    check("consumed less booked", "- flt(nos * per_nos), 3)" in src, True)
    entry = inspect.getsource(sub.create_finished_goods_entry)
    check("no extra Stock Entry is raised for it", entry.count("frappe.get_doc({") <= 1, True)

    print()
    print("=== the plan totals it from the entries, so a cancel needs no unwinding ===")
    refresh = inspect.getsource(fg_stock._refresh_mip_loss)
    check("summed from submitted entries", "se.docstatus = 1" in refresh, True)
    check("finished-goods rows only", "sed.is_finished_item = 1" in refresh, True)
    check("written to loss_weight_kg", '"loss_weight_kg"' in refresh, True)
    # The name appears in its docstring, saying it is a DIFFERENT figure. What matters
    # is that the supplier write-off's field is never written to from here.
    check("...and never writes the supplier write-off's field",
          '"process_loss_weight_kg"' in refresh, False)
    check("the hook calls it", "_refresh_mip_loss(doc)" in inspect.getsource(
        fg_stock.on_fg_stock_entry_change), True)

    print()
    print("=== the popup is the only place the weight is set ===")
    fgjs = _js("public", "js", "stock_entry_fg.js")
    check("a Final Stock Entry's Kg is locked on the draft",
          "if (_fg_is_produced(frm, row) && frm.doc.subcontracting_order) return true;" in fgjs, True)
    mipjs = _js("subcontracting_management", "doctype", "material_issue_plan", "material_issue_plan.js")
    check("the popup posts the edited figures", "fg_weights_json: JSON.stringify(weights" in mipjs, True)
    check("the builder accepts them",
          "def create_finished_goods_entry(sco_name, fg_weights_json=None):" in inspect.getsource(sub), True)
    check("an existing draft is rebuilt, not handed back unchanged",
          "se.items = []" in entry, True)

    print()
    print("=== the popup's columns, in order, and its footnote ===")
    # Two rates side by side: the customer's, which is read-only, and the one being
    # booked, which starts equal to it and is the only editable cell on the screen.
    order = ["DUNO / Drawing", "To Make", "Completed", "Already Booked", "Booking Now",
             "Cust Wt per Nos", "FG Wt per Nos", "Consumed RM Wt", "FG Total wt", "Loss"]
    at = [mipjs.find('__("%s")' % label) for label in order]
    for label, pos in zip(order, at):
        check("column: %s" % label, pos > 0, True)
    check("they are in that order", at == sorted(at), True)
    check("the editable cell is FG Wt per Nos, not the customer's",
          mipjs.index('__("FG Wt per Nos")') > mipjs.index('__("Cust Wt per Nos")'), True)

    print()
    print("=== themed like the transfer popup, in blue ===")
    check("it has its own theme", "MFX_FG_THEME_CSS" in mipjs, True)
    check("...injected when the popup opens", "_mfx_inject_fg_theme();" in mipjs, True)
    check("...and scoped so no other dialog is touched",
          ".mfx-fg-theme .mfx-fg-pane {" in mipjs, True)
    check("blue, not the transfer popup's green",
          "#0284c7" in mipjs and "#e0f2fe" in mipjs, True)
    check("the green transfer theme is untouched",
          "#65a30d" in mipjs and "#ecfccb" in mipjs, True)
    check("it says what submission does",
          "the raw material is consumed from the supplier warehouse and converted into finished goods" in mipjs, True)
    check("...and where the lower-side difference goes",
          "the difference is recorded as process loss and shown in the report" in mipjs, True)
    check("over-booking is confirmed, not refused", "frappe.confirm(" in mipjs, True)
    check("...with the billing message",
          "Update the weight in the Sales Order for correct billing" in mipjs, True)

    print()
    print("=== the arithmetic, on your worked example ===")
    # 900 Kg/Nos x 2 Nos = 1,800 booked against 2,000 consumed -> 200 lost.
    check("900 x 2 against 2,000 consumed", flt(2000.0 - (900.0 * 2), 3), 200.0)
    # Edited to 1,050/Nos -> 2,100 booked -> 100 over, not a loss.
    check("1,050 x 2 against 2,000 consumed", flt(2000.0 - (1050.0 * 2), 3), -100.0)
    check("exact gives nothing", flt(2000.0 - (1000.0 * 2), 3), 0.0)

    print()
    print("=== live: the split adds up to the entry it describes ===")
    if not frappe.db.exists("Subcontracting Order", SCO):
        print("  SKIP %s not on this site" % SCO)
    else:
        p = sub.get_final_stock_entry_preview(SCO)
        rows = [d for d in p["drawings"] if flt(d["ready_to_book"]) > 0]
        check("every ready drawing knows its consumed steel",
              all(d.get("consumed_rm_kg") is not None for d in rows), True)

        sco_doc = frappe.get_doc("Subcontracting Order", SCO)
        wh = sub._get_sco_supplier_warehouse(sco_doc)
        available = sub._get_supplier_wh_consumption_items(sco_doc, wh)
        consumed = sub._consumption_for_completed(sco_doc, wh, p, available)
        entry_total = flt(sum(flt(r["qty"]) for r in consumed), 3)
        split_total = flt(sum(flt(d["consumed_rm_kg"]) for d in rows), 3)
        check("the per-drawing split equals the entry's own consumption",
              split_total, entry_total)

        mip = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": SCO}, "name")
        check("...and equals the plan's planned weight",
              split_total, flt(frappe.db.get_value(
                  "Material Issue Plan", mip, "total_planned_weight_kg"), 3))

        loss = flt(sum(flt(d["loss_kg"]) for d in rows), 3)
        booked = flt(sum(flt(d["planned_kg"]) for d in rows), 3)
        print("       consumed %.3f, booked %.3f, loss %.3f" % (split_total, booked, loss))
        check("loss is consumed less booked", loss, flt(split_total - booked, 3))

        print()
        print("=== live: editing the weight moves the loss, one for one ===")
        doubled = {d["drawing"]: flt(d["cust_weight_per_nos"]) * 2 for d in rows}
        new_booked = flt(sum(doubled[d["drawing"]] * flt(d["ready_to_book"]) for d in rows), 3)
        check("doubling the rate doubles the booked weight", new_booked, flt(booked * 2, 3))
        check("and the loss falls by exactly that much",
              flt(split_total - new_booked, 3), flt(loss - booked, 3))

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
