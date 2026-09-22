"""A consolidate line can be moved to any batch, of any item, before it ships.

The real decision this screen exists for is not "same steel, different bar". It is the
planner deciding, the day before a transfer, to send one ISMB800 instead of four ISMB200
-- or a plate instead of a section. The requirement does not change; what goes does.

The picker used to offer the line's own item only, and the preview refused anything else
outright: "Batch X holds PLATE20, but this line moves ISMB450." So the commonest reason to
open the dialog was the one thing it would not do.

Two things had to change together, and the second is why this was not a one-line edit.

**Exact Match had nowhere to record a substitution.** Material Mapping has carried
planned_item for exactly this -- 65 places across the app read `planned_item or item_code`
to mean "the item the batch actually holds": the consolidate grouping, the transfer line,
the DUNO key, the Cut Sheet caps, the finished-goods split. Available Raw Material had no
such field, so a PLATE20 batch written onto an ISMB450 exact-match row would have shipped
as ISMB450 to every one of them. The field now exists there too, is set when the batch's
item differs and cleared when it does not, and is carried onto the Material Issue Plan.

**Size never needed filtering.** Reserve Without Dimensions reserves a row's required Kg
and states the piece count as a fraction, so a line moves to a batch of any size and only
one number has to reconcile: Kg. Availability is the whole test, which is what was asked
for.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_cross_item_batch_reassign.run
"""

import inspect
import json

import frappe
from frappe.utils import flt

checks = []

MIP = "MIP-2026-00060"
ARM = "Material Planning Available Raw Material"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_batch_update as bu
    from manufyxinvenzaerp.production_management.doctype.material_planning import (
        material_planning as mp_mod,
    )

    print("=== Exact Match can say which item the batch really holds ===")
    df = frappe.get_meta(ARM).get_field("planned_item")
    check("the field exists", bool(df), True)
    if df:
        check("   ...a read-only Item link", (df.fieldtype, df.options, df.read_only),
              ("Link", "Item", 1))
    check("the column is on the table", frappe.db.has_column(ARM, "planned_item"), True)

    print()
    print("=== it is set when the batch differs, and cleared when it does not ===")
    src = inspect.getsource(mp_mod._apply_batch_to_arm_row)
    check("the writer takes the batch's item", "new_item=None" in src, True)
    check("set only when it differs from the requirement",
          'row.planned_item = item if (item and item != row.item_code) else ""' in src, True)
    check("it falls back to the batch's own item",
          "get_batch_item(new_batch_no) if new_batch_no else None" in src, True)
    check("the reassign hands it over", "new_item=w.batch_item," in inspect.getsource(bu._apply_to_one_plan), True)

    # The rule itself, on a stand-in row -- nothing is saved.
    row = frappe._dict(item_code="ISMB450", meta=frappe.get_meta(ARM))
    row.set = lambda f, v: row.__setitem__(f, v)
    row.get = lambda f, default=None: dict.get(row, f, default)
    mp_mod._apply_batch_to_arm_row(row, None, {}, None, 0, new_item="PLATE20")
    check("a substitute item is recorded", row.get("planned_item"), "PLATE20")
    mp_mod._apply_batch_to_arm_row(row, None, {}, None, 0, new_item="ISMB450")
    check("the row's own item is not", row.get("planned_item"), "")

    print()
    print("=== the Material Issue Plan carries it forward ===")
    mip_src = inspect.getsource(
        __import__("manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan"
                   ".material_issue_plan", fromlist=["x"]))
    after_arm = mip_src.split('"source_table": "Material Planning Available Raw Material"')[1][:900]
    check("exact-match rows pass planned_item", '"planned_item": row.get("planned_item")' in after_arm, True)

    print()
    print("=== the picker offers every item, own item first ===")
    q = inspect.getsource(bu.get_candidate_batches)
    check("no item filter on the query", '"item": item_code' in q, False)
    check("each candidate names its item", '"item_code": b.item,' in q, True)
    check("own item sorts first", 'key=lambda b: (-b["same_item"], -b["free_kg"])' in q, True)
    check("zero-stock batches are still left out", "if free <= EPS:" in q, True)

    print()
    print("=== a different item warns, it does not refuse ===")
    plan = inspect.getsource(bu._build_plan) if hasattr(bu, "_build_plan") else inspect.getsource(bu)
    check("the old blocker is gone",
          'blockers.append(\n                _("Batch {0} holds {1}, but this line moves {2}.")' in plan, False)
    check("it is a warning now",
          "The requirement stays {2}; {1} is what " in plan, True)
    check("no free stock is still a blocker",
          '_("Batch {0} has no free stock in {1}.")' in plan, True)

    print()
    print("=== live: the ISMB450 line can reach other items ===")
    if not frappe.db.exists("Material Issue Plan", MIP):
        print("  SKIP %s not on this site" % MIP)
    else:
        m = frappe.get_doc("Material Issue Plan", MIP)
        line = next((c for c in m.consolidate_items if c.item_code == "ISMB450"), None)
        if not line:
            print("  SKIP no ISMB450 line on %s" % MIP)
        else:
            ctx = bu.get_consolidate_line_context(MIP, line.name)
            cands = bu.get_candidate_batches(ctx.get("item_code"), ctx.get("warehouse"))
            items = {c["item_code"] for c in cands}
            check("more than one item is offered", len(items) > 1, True)
            check("its own batch is still first", cands[0]["item_code"], "ISMB450")
            check("every candidate has free stock", all(flt(c["free_kg"]) > 0 for c in cands), True)

            big = next((c for c in cands
                        if c["item_code"] != "ISMB450" and flt(c["free_kg"]) >= flt(line.qty)), None)
            if not big:
                print("  SKIP no other item has enough free stock to preview")
            else:
                pv = bu.preview_consolidate_batch_update(
                    MIP, line.name, json.dumps([{"batch_no": big["batch_no"]}]))
                check("a cross-item move is allowed", pv.get("ok"), True)
                check("   ...with no blockers", len(pv.get("blockers") or []), 0)
                check("   ...and it says what will be sent",
                      any("holds %s, not ISMB450" % big["item_code"] in frappe.utils.strip_html(str(w))
                          for w in (pv.get("warnings") or [])), True)
                check("   ...and covers the line", flt(pv.get("shortfall_kg")), 0.0)

            small = next((c for c in cands
                          if c["item_code"] != "ISMB450" and flt(c["free_kg"]) < flt(line.qty)), None)
            if small:
                pv2 = bu.preview_consolidate_batch_update(
                    MIP, line.name, json.dumps([{"batch_no": small["batch_no"]}]))
                check("a batch too small to cover it is short",
                      flt(pv2.get("shortfall_kg")) > 0 or not pv2.get("ok"), True)

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
