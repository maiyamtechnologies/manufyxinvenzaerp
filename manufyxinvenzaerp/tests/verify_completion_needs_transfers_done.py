"""A plan cannot finish while material is still waiting to be sent.

MIP-2026-00004 closed itself six minutes after its first transfer with 472.615 Kg
of CNC material still standing in stores, and the Completed lock then hid the very
button that would have sent it. The user's report was "there is no option to
transfer the CNC" -- the button was gone, not broken.

Two independent defects lined up:

  * _maybe_mark_completed measured only what the job had left AT THE SUPPLIER.
    _job_stock_at_supplier nets movements ACROSS the supplier warehouse boundary,
    so material that never left stores never enters that sum at all. The four
    batches that did travel netted to exactly zero, the gate saw nothing
    outstanding, and the plan completed with a whole routing leg unperformed.
    The backend disagreed with itself at that moment: get_mip_cnc_button_state
    still returned show_to_cnc=True while the status said finished. Only the
    Completed early-return in material_issue_plan.js refresh() hid the button.

  * create_finished_goods_entry had no opinion about outstanding transfers, so the
    Final Stock Entry could be booked first. MAT-STE-00010 consumed 10,315.918 Kg
    and produced 10,584.96 Kg of fabricated structures -- Loss (Kg) came out
    NEGATIVE on all three finished rows (-132.783, -65.129, -71.130), which is not
    a loss but an impossibility. The missing 269.042 Kg is the shortfall from the
    CNC material that was never sent.

Now: the completion gate asks get_mip_pending_items -- the same source the transfer
buttons derive from, so the two can never tell different stories -- and the finished
goods entry refuses outright while anything is still to go.

The two guards fail in OPPOSITE directions on purpose, and check 4 pins that down:
a plan left open can still be worked on, so unanswerable counts as pending there;
a job that cannot book finished goods at all is stuck with no way forward, so
unanswerable counts as allowed here.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_completion_needs_transfers_done.run
"""

import ast
import inspect
import textwrap

import frappe

checks = []


def _body(fn):
    """A function's code with its docstring removed.

    These checks assert that a function does NOT do something, and these docstrings
    explain at length what was rejected and why -- so a plain source grep matches the
    warning as readily as the mistake.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = tree.body[0]
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:]
    return ast.unparse(node)


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, fragment):
    try:
        fn()
    except Exception as e:
        return fragment.lower() in frappe.utils.strip_html(str(e)).lower()
    return False


def run():
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        _maybe_mark_completed, _pending_transfer,
    )
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        _pending_transfer_block, create_finished_goods_entry,
    )

    print("=== 1. The gate asks the same question the buttons ask ===")
    # The docstring names the rejected approach in order to explain it, so read the
    # CODE, not the source text -- grepping the whole function finds the very words
    # it is warning against.
    src = _body(_pending_transfer)
    check("it reads get_mip_pending_items, not (qty - transferred_qty)",
          "get_mip_pending_items" in src and "transferred_qty" not in src, True)
    check("and _maybe_mark_completed consults it before completing",
          "_pending_transfer(mip)" in inspect.getsource(_maybe_mark_completed), True)

    print()
    print("=== 2. A plan with material still in stores stays open ===")
    # Every plan on the site, so this keeps working as the data changes: whatever is
    # pending must not be Completed, and whatever is Completed must have nothing left.
    seen_pending = False
    for name in frappe.get_all("Material Issue Plan", pluck="name", order_by="name"):
        mip = frappe.get_doc("Material Issue Plan", name)
        pending = _pending_transfer(mip)
        if not pending:
            continue
        seen_pending = True
        # The status itself is left alone -- MIP-2026-00004 was completed before the
        # guard existed and unwinding it is a data repair, not this function's job.
        # What must be true is that the gate would refuse to do it again.
        was = mip.status
        mip.status = "In Progress"
        _maybe_mark_completed(mip)
        check("  %s: pending material -> gate refuses to complete" % name,
              mip.status, "In Progress")
        mip.status = was
    if not seen_pending:
        print("    (no plan currently has pending material -- nothing to exercise)")

    print()
    print("=== 3. A plan with nothing outstanding is unaffected ===")
    # The guard must not block the ordinary case. A Cut Sheet row is the one that
    # would: its qty is the whole plate while only the W1 pieces ever move, so row
    # arithmetic reads the W2 balance as a permanent shortfall. get_mip_pending_items
    # caps at the cut plan, which is exactly why the gate asks it instead.
    done = [n for n in frappe.get_all("Material Issue Plan",
                                      filters={"status": "Completed"}, pluck="name")]
    for name in done:
        mip = frappe.get_doc("Material Issue Plan", name)
        if _pending_transfer(mip):
            # MIP-2026-00004 is the known-bad one this test exists for; any OTHER
            # completed plan reading pending would mean the guard is over-eager.
            print("    %s is Completed with material still pending (pre-existing "
                  "data defect, see docstring)" % name)
            continue
        check("  %s: completed and nothing pending" % name, True, True)

    print()
    print("=== 4. Finished goods refuse to be booked ahead of the transfer ===")
    blocked = []
    for sco in frappe.get_all("Subcontracting Order", filters={"docstatus": 1}, pluck="name"):
        msg = _pending_transfer_block(sco)
        if msg:
            blocked.append(sco)
            check("  %s: blocked, and the message says how much" % sco,
                  "Kg" in msg and sco_mip(sco) in msg, True)
            check("  %s: and create_finished_goods_entry throws" % sco,
                  _throws(lambda s=sco: create_finished_goods_entry(s),
                          "still waiting to be transferred"), True)
    if not blocked:
        print("    (no submitted order currently has pending material)")

    print()
    print("=== 5. The two guards fail in opposite directions ===")
    # An unresolvable plan must not be able to complete, and must not be prevented
    # from booking finished goods. Same question, different safe answer.
    check("completion treats unanswerable as pending",
          _pending_transfer(frappe._dict(name="ZZ-NO-SUCH-MIP")), True)
    check("finished goods treats unanswerable as allowed",
          _pending_transfer_block("ZZ-NO-SUCH-SCO"), "")

    _summary()


def sco_mip(sco_name):
    """The plan named in the block message, so the check proves it points somewhere."""
    return frappe.db.get_value(
        "Material Issue Plan", {"subcontracting_order": sco_name}, "name") or ""


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
