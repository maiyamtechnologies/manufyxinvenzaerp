"""The CNC-to-supplier leg must not release a reservation a second time.

Material bound for a CNC drawing travels in two hops: Stores -> CNC, then CNC ->
supplier. The reservation is given up on the FIRST hop, which is where the material
left the warehouse it was reserved in. The second hop moves stock that the plan has
already stopped holding.

_release_material_planning_reservations was charging both hops. Because a release walks
the still-reserved rows of a batch in document order and takes weight off them until it
has accounted for what moved, the second charge could not find the rows it had already
cleared -- so it ate into the NEXT drawings in the plan instead, ones with nothing
transferred at all.

Seen on live data. MIP-2026-00059 forwarded 81.056 Kg of ISA100 and 24.003 Kg of
PLATE10 out of CNC on MAT-STE-00359, and MP-2026-00260 lost exactly that much
reservation off 1B6, 1B7, 1B8, 1B9 and part of 1B10:

    ISA100   1B6 11.622 + 1B6 9.536 + 1B7 9.536 + 1B7 11.622
           + 1B8 11.622 + 1B8 9.536 + 1B9 11.324 + 1B10 6.258 = 81.056
    PLATE10  1B6 1.926 + 1B6 2.003 + 1B7 2.640 + 1B7 2.003
           + 1B8 2.003 + 1B8 2.640 + 1B9 6.029 + 1B9 3.404 + 1B9 1.355 = 24.003

The stock was still standing in Stores, so nothing was lost -- but the plan no longer
held it, and those drawings would refuse to transfer until re-reserved.

The rule now: rows leaving the MIP's own CNC warehouse are not consumption. Excluded by
row, not by a whole-entry flag, so an entry mixing CNC and stores rows still releases
correctly for the stores half. Cancel mirrors it through the same helper.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_cnc_forward_double_release.run
"""

import inspect

import frappe
from frappe.utils import flt

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-62s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
    from manufyxinvenzaerp.production_management import stock_entry as se_mod

    print("=== a move out of CNC is not consumption ===")
    src = inspect.getsource(se_mod._consumed_qty_by_batch)
    check("the outward tally skips CNC-sourced rows", "skip_rows = _cnc_sourced_rows(doc)" in src, True)
    check("...in the bundle query", "sbb.voucher_detail_no NOT IN %(skip_rows)s" in src, True)
    check("...and in the no-bundle fallback", "if row.name in skip_rows:" in src, True)

    guard = inspect.getsource(se_mod._cnc_sourced_rows)
    check("the CNC warehouse comes from the entry's own plan",
          'frappe.db.get_value("Material Issue Plan", mip_ref, "cnc_warehouse")' in guard, True)
    check("it matches on the SOURCE warehouse", 'row.get("s_warehouse") == cnc_warehouse' in guard, True)
    check("no MIP link means no exclusion", "if not mip_ref:" in guard, True)

    print()
    print("=== release and cancel both go through it ===")
    for fn in (se_mod._release_material_planning_reservations,
               se_mod._restore_material_planning_reservations):
        check("%s uses the shared tally" % fn.__name__,
              "_consumed_qty_by_batch(doc)" in inspect.getsource(fn), True)

    print()
    print("=== live: what each leg of MIP-2026-00059 now counts as consumed ===")
    legs = [
        ("MAT-STE-00357", "Stores -> CNC", True),
        ("MAT-STE-00358", "Stores -> supplier", True),
        ("MAT-STE-00359", "CNC -> supplier", False),
    ]
    for name, label, should_count in legs:
        if not frappe.db.exists("Stock Entry", name):
            print("  SKIP %s not on this site" % name)
            continue
        doc = frappe.get_doc("Stock Entry", name)
        moved = se_mod._consumed_qty_by_batch(doc)
        total = flt(sum(moved.values()), 3)
        shipped = flt(sum(flt(d.qty) for d in doc.items), 3)
        if should_count:
            check("%s (%s) releases what it moved" % (name, label), total, shipped)
        else:
            check("%s (%s) releases nothing" % (name, label), total, 0.0)

    print()
    print("=== live: the plan holds exactly what it has not yet shipped ===")
    # reserved == required - transferred, per item. ISMB450 has no CNC leg and was
    # always right; ISA100 and PLATE10 are the two the forward robbed.
    mp_name = "MP-2026-00260"
    mip_name = "MIP-2026-00059"
    if not (frappe.db.exists("Material Planning", mp_name)
            and frappe.db.exists("Material Issue Plan", mip_name)):
        print("  SKIP %s / %s not on this site" % (mp_name, mip_name))
    else:
        mp = frappe.get_doc("Material Planning", mp_name)
        mip = frappe.get_doc("Material Issue Plan", mip_name)

        shipped = {}
        for r in mip.raw_materials:
            code = r.planned_item or r.item_code
            shipped[code] = flt(shipped.get(code, 0) + flt(r.transferred_qty), 3)

        required, reserved = {}, {}
        for r in mp.available_raw_materials:
            required[r.item_code] = flt(required.get(r.item_code, 0) + flt(r.required_qty), 3)
            reserved[r.item_code] = flt(reserved.get(r.item_code, 0) + flt(r.reserved_qty), 3)

        for code in sorted(required):
            want = flt(required[code] - flt(shipped.get(code, 0)), 3)
            check("%-9s reserved == required - shipped" % code, reserved[code], want)

    print()
    total, passed = len(checks), sum(1 for c in checks if c)
    if passed == total:
        print("ALL %d CHECKS PASSED" % total)
    else:
        print("%d of %d CHECKS FAILED" % (total - passed, total))
