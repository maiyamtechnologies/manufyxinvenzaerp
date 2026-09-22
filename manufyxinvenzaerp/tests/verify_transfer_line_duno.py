"""A transfer line carries the drawing it actually belongs to, or none at all.

get_mip_pending_items stamps duno_mark_no / drawing / sales_order / customer_drawing_number
onto each line by looking them up from the plan's raw-material rows. That lookup was a
dict comprehension keyed (item, batch), so it had two faults at once:

  * no CNC leg in the key, though the lines themselves are keyed by leg -- one batch
    feeding a CNC drawing and a direct one makes TWO lines and both got one answer;
  * the LAST row won, so a batch serving several drawings stamped whichever DUNO
    happened to be read last.

Together they put the wrong drawing on a real Stock Entry: MAT-STE-00354 moved 1B1's
CNC material to the CNC warehouse carrying 1B3 (ISMB400) and 1B5 (ISA100, PLATE10),
because those batches also feed 1B2..1B5 on the direct leg.

It is not only cosmetic. create_mip_cnc_partial_forward reads these values straight back
off the transfer's own rows to build the CNC-to-supplier leg, so a wrong DUNO is copied
onward rather than corrected.

The rule now: the leg is part of the key, and where the contributing rows disagree the
line is stamped BLANK -- a merged line covers several drawings and belongs to none of them.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_transfer_line_duno.run
"""

import inspect

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-60s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as mipt

    src = inspect.getsource(mipt.get_mip_pending_items)

    print("=== the lookup is keyed by the CNC leg, like the lines are ===")
    check("the key carries the leg",
          '1 if (r.cnc_process and cnc_warehouse) else 0)' in src, True)
    check("DUNO is read with the leg",
          'duno_by_key.get((item_code, batch_no, 1 if is_cnc else 0)' in src, True)
    check("sales order too",
          'so_by_key.get((item_code, batch_no, 1 if is_cnc else 0)' in src, True)
    check("customer drawing number too",
          'cdn_by_key.get((item_code, batch_no, 1 if is_cnc else 0)' in src, True)
    check("the leg-blind reads are gone",
          'duno_by_key.get((item_code, batch_no), "")' in src, False)

    print()
    print("=== rows that disagree produce a blank, not a guess ===")
    check("the dict comprehension is gone (last row no longer wins)",
          "((r.planned_item or r.item_code), r.batch_no or \"\"): r.get(fieldname)" in src, False)
    check("disagreement blanks the value", 'out[key] = ""' in src, True)

    print()
    print("=== live: every line's DUNO is one its own rows agree on ===")
    mip = frappe.db.get_value("Material Issue Plan", {"docstatus": ["<", 2]},
                              "name", order_by="creation desc")
    if not mip:
        print("  SKIP no Material Issue Plan on this site")
    else:
        m = frappe.get_doc("Material Issue Plan", mip)
        cnc_wh = m.cnc_warehouse or ""
        # what each (item, batch, leg) is really made of
        rows_by_key = {}
        for r in (m.raw_materials or []):
            key = ((r.planned_item or r.item_code), r.batch_no or "",
                   1 if (r.cnc_process and cnc_wh) else 0)
            rows_by_key.setdefault(key, set()).add(r.duno_mark_no or "")

        try:
            pending = mipt.get_mip_pending_items(mip)
        except Exception as e:
            print("  SKIP %s could not be read: %s" % (mip, frappe.utils.strip_html(str(e))[:60]))
            pending = []

        print("  %s: %d line(s)" % (mip, len(pending)))
        for p in pending:
            key = (p["item_code"], p["batch_no"] or "", 1 if p["cnc_process"] else 0)
            contributors = rows_by_key.get(key, set())
            stamped = p["duno_mark_no"] or ""
            leg = "CNC" if p["cnc_process"] else "direct"
            if len(contributors) == 1:
                want = list(contributors)[0]
                check("%s %s -> the one drawing it covers" % (p["item_code"], leg), stamped, want)
            else:
                check("%s %s -> blank (%d drawings merged)" % (p["item_code"], leg, len(contributors)),
                      stamped, "")

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
