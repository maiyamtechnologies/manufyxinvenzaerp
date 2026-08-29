"""Every kilo sent to a supplier ends up somewhere, and the books say where.

A job sends 1,000 Kg, uses 500, gets 300 back and cannot account for 200. Before
this, the books could not describe that at all:

  * The excess return was a Material Receipt with NO source warehouse. It created
    the off-cut as new stock in stores while every kilo of it was still standing at
    the supplier -- and the final Stock Entry then consumed it. The same steel was
    received AND consumed, and the job was charged for material it never used.
    Every return entry on the site shows it: `src=(none)`.

  * The final Stock Entry consumed the whole transfer, scaled only by how much of
    each drawing was finished. Whole pieces go to a supplier -- a 5 m length is
    issued to make a 340 mm part -- so "finished" meant "consume all 5 m", leaving
    nothing behind to return.

  * The netting query that decides what is left to consume matches on the job's
    order, and the return entry was tagged only with the plan. Its own docstring
    claimed "an excess return correctly reduces what is left to consume"; it could
    not, because it never saw one.

  * Nothing named the difference. Material the supplier could not account for sat
    in their warehouse under the job's name forever, and the plan could be marked
    Completed straight over the top of it.

Now: the FG entry consumes what the drawing needed, the return is a Repack that
takes the off-cut out of the supplier and brings it home as a new batch, and what
is left over is Process Loss -- declared with a reason, refused while another plan
is claiming it, and issued out by its own entry before the job can close.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_excess_return_and_process_loss.run
"""

import re

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, fragment):
    try:
        fn()
    except Exception as e:
        return fragment.lower() in frappe.utils.strip_html(str(e)).lower()
    return False


def _src(*parts):
    return open(frappe.get_app_path("manufyxinvenzaerp", *parts)).read()


def run():
    from manufyxinvenzaerp.subcontracting_management.material_issue_plan_transfer import (
        _job_stock_at_supplier, _excess_return_source_rows,
        create_mip_process_loss_entry, get_mip_process_loss_state,
    )

    print("=== 1. The return moves material instead of inventing it ===")
    src = _src("subcontracting_management", "material_issue_plan_transfer.py")
    m = re.search(r'def create_mip_excess_return_entry.*?se = frappe\.get_doc\(\{(.*?)\}\)', src, re.S)
    body = m.group(1) if m else ""
    # Repack when there is material at the supplier to take it out of; a plain
    # receipt only where the plan never sent any (excess claimed off another plan's
    # table, say), because there the double-count cannot arise -- the final Stock
    # Entry consumes from a supplier warehouse, and there isn't one.
    check("it repacks out of the supplier when there is stock to take",
          '"Repack" if out_rows else "Material Receipt"' in body, True)
    check("and it is tagged with the job's order, so the netting sees it",
          '"custom_sco_ref"' in body, True)

    # The out rows are chosen from what the job actually has at the supplier.
    fake = frappe._dict(supplier_warehouse="ZZ-NOWHERE", subcontracting_order="ZZ-NOSUCH")
    rows, short = _excess_return_source_rows(fake, [{"item_code": "ZZ-X", "qty": 5, "uom": "Kg"}])
    check("nothing available -> nothing taken, and it says so short",
          (rows, len(short)), ([], 1))

    print()
    print("=== 2. The final entry consumes what the drawing needed ===")
    sub = _src("subcontracting_management", "subcontracting.py")
    check("consumption is capped at the requirement, not the transfer",
          bool(re.search(r"wanted = flt\(r\.drawing_planned_weight\) or flt\(r\.reqd_kg\)", sub))
          and "min(contribution, wanted * fraction)".replace("*", "*") in sub,
          True)

    print()
    print("=== 3. The plan states where every kilo went ===")
    meta = frappe.get_meta("Material Issue Plan")
    for f in ("used_in_fg_weight_kg", "returned_weight_kg",
              "process_loss_weight_kg", "process_loss_reason"):
        check("  %s exists and is read-only" % f,
              (bool(meta.get_field(f)), bool(meta.get_field(f) and meta.get_field(f).read_only)),
              (True, True))

    print()
    print("=== 4. A finished job balances ===")
    done = frappe.db.get_value(
        "Material Issue Plan", {"process_loss_weight_kg": [">", 0]},
        "name", order_by="modified desc",
    )
    if not done:
        print("    (no plan has been written off yet -- skipped)")
    else:
        mip = frappe.get_doc("Material Issue Plan", done)
        left = flt(sum(_job_stock_at_supplier(mip).values()), 3)
        print("    %s: used=%s returned=%s loss=%s  left at supplier=%s"
              % (done, mip.used_in_fg_weight_kg, mip.returned_weight_kg,
                 mip.process_loss_weight_kg, left))
        check("nothing of it is left standing at the supplier", left, 0.0)
        check("and the plan is allowed to close", mip.status, "Completed")

    print()
    print("=== 5. The write-off asks before it acts ===")
    open_mip = frappe.db.get_value(
        "Material Issue Plan",
        {"status": ["!=", "Completed"], "subcontracting_order": ["is", "set"]},
        "name", order_by="creation desc",
    )
    if not open_mip:
        print("    (no open plan -- skipped)")
    else:
        check("a reason is required",
              _throws(lambda: create_mip_process_loss_entry(open_mip, "   "), "enter a reason"),
              True)
        s = get_mip_process_loss_state(open_mip)
        if not s["final_entry_exists"]:
            check("and it refuses before the final Stock Entry exists",
                  _throws(lambda: create_mip_process_loss_entry(open_mip, "cutting loss"),
                          "final stock entry first"), True)

    print()
    print("=== 6. The threshold that says 'this is not process loss' ===")
    fld = frappe.get_meta("Manufyxinvenza Settings").get_field("process_loss_warning_percent")
    check("the setting exists", bool(fld), True)
    check("defaulting to 5%", (fld.default if fld else None), "5")
    mip_js = _src("subcontracting_management", "doctype", "material_issue_plan",
                  "material_issue_plan.js")
    check("and the dialog says to raise a purchase return instead",
          "purchase return" in mip_js.lower(), True)

    print()
    print("=== 7. Claimed material cannot be written off underneath a plan ===")
    check("the check is there, naming the plans",
          bool(re.search(r'if absorb and state\["claimed"\]', src))
          and "unallocate it there first" in src.lower(), True)

    _summary()


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
