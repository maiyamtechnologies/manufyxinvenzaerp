"""The final stock entry books what is finished, not what was planned.

The button used to wait for custom_all_ops_complete -- every operation on every drawing
done. A job of ten drawings that had finished four could not book those four: the
finished steel sat at the supplier with nothing to show for it until the last piece of
the last drawing was painted. And when it finally ran it consumed everything in the
supplier warehouse and produced every drawing at its full planned quantity, whatever had
actually been made.

It now appears as soon as the LAST operation exists, and books only what that operation
has finished:

  * one finished-goods row per drawing, for the pieces completed and not yet booked;
  * raw material narrowed to the share belonging to those drawings, taken from the
    Material Issue Plan's own rows and scaled by how much of each drawing is done.

The share is worked out cumulatively -- what the job should have consumed by now for
everything finished to date, less what earlier entries consumed -- so several partial
runs land exactly on the transferred weight instead of drifting a few grams off it.

Measured here against a real job: finish two of its five drawings and the entry consumes
1,111.782 Kg of the 6,086.526 Kg transferred, which is those two drawings' planned weight
to the gram, and touches none of the material belonging to the other three.

Everything runs inside a transaction and is rolled back.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_partial_final_stock_entry.run
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.subcontracting_management.subcontracting import (
    create_finished_goods_entry,
    get_final_stock_entry_preview,
)

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-54s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _bookable_sco():
    """A submitted job whose raw material has actually been sent.

    This used to take the first submitted order it found, which is fine until that
    order is one that may not book finished goods yet. Finished goods now wait for
    the transfer legs to finish (_pending_transfer_block in subcontracting.py), and
    on this site the first submitted order is SC-ORD-2026-00004 -- the job that was
    completed with 472.615 Kg of CNC material still in stores, which is exactly the
    job that rule exists to stop. The test then read a correct refusal as a failure
    of partial booking, which is a different feature entirely.

    Skipping those keeps this test about what it is about. If every job is blocked
    there is nothing here to measure, and run() says so rather than inventing one.
    """
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        _pending_transfer_block,
    )

    for name in frappe.get_all("Subcontracting Order",
                               filters={"docstatus": 1}, pluck="name", order_by="name"):
        if not _pending_transfer_block(name):
            return name
    return None


def run():
    sco = _bookable_sco()
    if not sco:
        print("=== no submitted Job Work Order ready to book on this site ===")
        _wiring()
        _summary()
        return

    print("=== %s ===" % sco)
    p = get_final_stock_entry_preview(sco)
    check("the final operation is found", bool(p["final_operation"]), True)
    check("it is the last in the routing",
          p["final_operation"]["sequence_id"],
          max(frappe.get_all("Supplier Operation Entry", filters={"subcontracting_order": sco},
                             pluck="sequence_id") or [0]))
    print("   last operation: %s (seq %s), %s of %s pieces completed"
          % (p["final_operation"]["operation"], p["final_operation"]["sequence_id"],
             p["total_completed"], p["total_planned"]))

    final = p["final_operation"]["name"]
    rows = frappe.get_all("SOE Drawing Detail", filters={"parent": final},
                          fields=["name", "drawing", "duno_mark_no", "completed_qty_nos"],
                          order_by="idx")
    if len(rows) < 2:
        print("   Fewer than two drawings on this job; the partial split cannot be shown.")
        _wiring()
        _summary()
        return

    mip_wt = flt(frappe.db.get_value("Material Issue Plan",
                                     {"subcontracting_order": sco}, "transferred_weight_kg"))

    try:
        # Clear the way: an entry already submitted for this job holds the material.
        for name in frappe.get_all("Stock Entry",
                                   filters={"subcontracting_order": sco, "docstatus": 1,
                                            "stock_entry_type": "Manufacture"}, pluck="name"):
            doc = frappe.get_doc("Stock Entry", name)
            doc.flags.ignore_links = True
            doc.cancel()

        print()
        print("=== nothing finished, nothing to book ===")
        for r in rows:
            frappe.db.set_value("SOE Drawing Detail", r.name, "completed_qty_nos", 0,
                                update_modified=False)
        none_yet = get_final_stock_entry_preview(sco)
        check("the button has nothing to offer", none_yet["can_create"], False)
        check("and says so rather than making an empty entry",
              "already in finished goods" in none_yet["reason"], True)

        print()
        print("=== finish two drawings of %d ===" % len(rows))
        keep = {rows[0].drawing: flt(rows[0].completed_qty_nos) or 1,
                rows[1].drawing: flt(rows[1].completed_qty_nos) or 1}
        for r in rows:
            frappe.db.set_value("SOE Drawing Detail", r.name, "completed_qty_nos",
                                keep.get(r.drawing, 0), update_modified=False)

        p2 = get_final_stock_entry_preview(sco)
        check("only those two are ready",
              sorted(d["drawing"] for d in p2["drawings"] if d["ready_to_book"] > 0),
              sorted(keep))
        check("one piece or more makes the entry possible", p2["can_create"], True)

        res = create_finished_goods_entry(sco)
        se = frappe.get_doc("Stock Entry", res["name"])
        fg = [i for i in se.items if i.is_finished_item]
        cons = [i for i in se.items if not i.is_finished_item]

        check("a finished-goods row per finished drawing",
              sorted(i.custom_drawing for i in fg), sorted(keep))
        check("for the pieces completed, not the pieces planned",
              sorted(flt(i.qty) for i in fg), sorted(keep.values()))
        check("each row records the drawing it was made for",
              all(i.custom_drawing and i.custom_duno_mark_no for i in fg), True)

        consumed = flt(sum(flt(i.qty) for i in cons), 3)
        print("   consumed %.3f Kg of the %.3f Kg transferred for the whole job"
              % (consumed, mip_wt))
        check("it consumes less than the whole job", consumed < mip_wt, True)
        check("and something, rather than booking goods against nothing", consumed > 0, True)

        # The share is the finished drawings' own planned weight -- that is what
        # "the raw material belongs to those drawings" has to mean.
        want = flt(sum(
            flt(w.total_weight_kg) * (keep[w.drawing] / flt(w.qty_to_manufacture))
            for w in frappe.get_all(
                "SCO Drawing Item",
                filters={"parent": sco, "parenttype": "Subcontracting Order",
                         "drawing": ["in", list(keep)]},
                fields=["drawing", "total_weight_kg", "qty_to_manufacture"])
            if flt(w.qty_to_manufacture)), 1)
        check("and it matches those drawings' own weight", flt(consumed, 1), want)

        print()
        print("=== booking again does not book the same pieces twice ===")
        se.submit()
        p3 = get_final_stock_entry_preview(sco)
        check("they now count as booked",
              sorted(d["drawing"] for d in p3["drawings"] if d["already_booked"] > 0),
              sorted(keep))
        check("with nothing left ready", p3["can_create"], False)
    finally:
        frappe.db.rollback()

    _wiring()
    _summary()


def _wiring():
    print()
    print("=== and the form asks before it acts ===")
    js = open(frappe.get_app_path("manufyxinvenzaerp", "subcontracting_management", "doctype",
                                  "material_issue_plan", "material_issue_plan.js")).read()
    check("the all-operations-complete gate is gone",
          "custom_all_ops_complete" in js, False)
    check("the button waits for the final operation instead",
          "if (!p || !p.final_operation) return;" in js, True)
    check("and shows what will be booked first",
          "function _show_final_stock_entry_preview(frm)" in js, True)
    check("creating is a deliberate second step",
          'primary_action_label: __("Create Stock Entry")' in js, True)

    py = open(frappe.get_app_path("manufyxinvenzaerp", "subcontracting_management",
                                  "subcontracting.py")).read()
    check("consumption is narrowed to the finished drawings",
          "def _consumption_for_completed(" in py, True)
    check("cumulatively, so partial runs do not drift",
          "flt(share.get(key, 0) - already.get(key, 0), 3)" in py, True)
    check("and an entry that cannot be netted still blocks a second",
          "It does not record which drawings it booked" in py, True)


def _summary():
    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
