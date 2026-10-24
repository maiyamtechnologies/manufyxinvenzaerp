"""Every movement in a Storage-Location warehouse names a location that fits it.

Storage Location is the ERPNext Inventory Dimension of that name. ERPNext records it on
every ledger entry but cannot make it mandatory per warehouse, and its own negative-stock
check works at item level, so a batch could leave a location it is not in. The rules
added by stock_management/storage_location.py, checked here end to end:

  * a warehouse with Mandatory Storage Location ticked, and locations of its own, refuses
    a submit without a location; any other warehouse does not care;
  * inward, with the Item's Validate Storage Location on, the location must be one the
    item lists for that warehouse (none listed, none allowed); with it off (the default
    since 22 Oct 2026) any location of the warehouse; the item's default is filled in;
  * outward, the location must hold the batch -- the message says where it is;
  * a batch spread over two locations is split into one row per location;
  * a Repack back into the same warehouse (cut-sheet remnant) keeps the source location;
  * moving a batch between locations of ONE warehouse is not stock leaving it, so it
    does not count towards releasing a Material Planning reservation (the bug this
    guards against: a same-warehouse Material Transfer was released batch-wide);
  * a Material Issue Plan cannot send stock into such a warehouse without naming the
    location, and a Material Planning row shows where its batch is.

Fixtures are created once and left in place (ZZTEST names, nothing deleted); the test
entries are cancelled at the end, and the ZZTEST warehouse is unticked again so no
other check's entries need a location.

Run: bench --site manufactv16 execute manufyxinvenzaerp.tests.verify_storage_location.run
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.production_management.stock_entry import _consumed_qty_by_batch
from manufyxinvenzaerp.stock_management import storage_location as sl

checks = []

ITEM = "ZZTEST-CS-REPACK"
WH_TYPE = "ZZTEST Storage Location"
L1, L2 = "ZZTEST-SL-1", "ZZTEST-SL-2"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-60s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, needle=None):
    try:
        fn()
    except frappe.ValidationError as e:
        frappe.clear_last_message()
        return needle in str(e) if needle else True
    return False


def _fixtures(company):
    if not frappe.db.exists("Warehouse Type", WH_TYPE):
        frappe.get_doc({"doctype": "Warehouse Type", "name": WH_TYPE}).insert(ignore_permissions=True)
    frappe.db.set_value("Warehouse Type", WH_TYPE, "custom_storage_location_applicable", 1)

    abbr = frappe.get_cached_value("Company", company, "abbr")
    wh = "ZZTEST SL Store - %s" % abbr
    if not frappe.db.exists("Warehouse", wh):
        frappe.get_doc({
            "doctype": "Warehouse", "warehouse_name": "ZZTEST SL Store", "company": company,
            "warehouse_type": WH_TYPE,
        }).insert(ignore_permissions=True)
    frappe.db.set_value("Warehouse", wh, {"warehouse_type": WH_TYPE, "custom_mandatory_storage_location": 1})

    for loc in (L1, L2):
        if not frappe.db.exists("Storage Location", loc):
            frappe.get_doc({"doctype": "Storage Location", "name": loc, "warehouse": wh}).insert(
                ignore_permissions=True
            )
        frappe.db.set_value("Storage Location", loc, "warehouse", wh)
    frappe.db.commit()
    return wh


def _set_item_locations(rows, validate=1):
    item = frappe.get_doc("Item", ITEM)
    item.custom_validate_storage_location = validate
    item.set("custom_storage_locations", rows)
    item.save(ignore_permissions=True)
    frappe.db.commit()


def _se(company, se_type, rows, submit=True):
    se = frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": se_type, "company": company,
        "items": [dict({
            "item_code": ITEM, "basic_rate": 50, "custom_parent_item_group": "Structurals",
            "custom_unit_weight": 10, "custom_sec_qty": 1, "custom_length": 3000,
        }, **r) for r in rows],
    })
    se.insert(ignore_permissions=True)
    if submit:
        se.submit()
    return se


def run():
    company = frappe.get_all("Company", pluck="name")[0]
    wh = _fixtures(company)
    made = []

    print("=== which warehouses need a location ===")
    check("the ZZTEST warehouse needs one", sl.location_applicable(wh), True)
    untyped = frappe.db.get_value("Warehouse", {"is_group": 0, "warehouse_type": ["is", "not set"]}, "name")
    check("a warehouse with no type does not", sl.location_applicable(untyped) if untyped else False, False)
    check("its locations", sl.warehouse_locations(wh), [L1, L2])

    try:
        print()
        print("=== inward: missing, defaulted, not allowed ===")
        _set_item_locations([])
        draft = _se(company, "Material Receipt", [{"qty": 30, "t_warehouse": wh}], submit=False)
        made.append(draft)
        check("two locations, no default: left blank on save", draft.items[0].to_storage_location, None)
        check("submit refused without a location", _throws(draft.submit, "mandatory"), True)
        # Only what the Item lists (Oct 2026): nothing listed, nothing offered or allowed.
        check("item lists none: nothing allowed", sl.allowed_locations(ITEM, wh), [])
        check("item lists none: picker is empty",
              sl.inward_location_query("Storage Location", "", "name", 0, 20,
                                       {"item_code": ITEM, "warehouse": wh}), [])
        check("item lists none: a keyed-in location is refused on save", _throws(lambda: _se(
            company, "Material Receipt", [{"qty": 5, "t_warehouse": wh, "to_storage_location": L1}],
            submit=False), "Storage Locations table"), True)

        # Validate Storage Location off: the item's own list is ignored.
        _set_item_locations([{"warehouse": wh, "storage_location": L1, "is_default": 1}], validate=0)
        check("validation off: every location of the warehouse allowed", sl.allowed_locations(ITEM, wh), [L1, L2])
        _set_item_locations([{"warehouse": wh, "storage_location": L1, "is_default": 1}])
        first = _se(company, "Material Receipt", [{"qty": 30, "t_warehouse": wh}])
        made.append(first)
        check("item default filled in", first.items[0].to_storage_location, L1)
        check("picker offers only what the item lists",
              [r[0] for r in sl.inward_location_query("Storage Location", "", "name", 0, 20,
                                                      {"item_code": ITEM, "warehouse": wh})], [L1])
        sle_loc = frappe.db.get_value("Stock Ledger Entry",
                                      {"voucher_no": first.name, "is_cancelled": 0}, "storage_location")
        check("ledger entry carries it", sle_loc, L1)
        batch = frappe.db.get_value("Stock Entry Detail", first.items[0].name, "batch_no") or \
            sl.row_batches(frappe.get_doc("Stock Entry", first.name).items[0], 30).popitem()[0]

        # Checked on SAVE since Oct 2026 (check_locations), not only on submit.
        check("a location the item does not list is refused on save", _throws(lambda: _se(
            company, "Material Receipt", [{"qty": 5, "t_warehouse": wh, "to_storage_location": L2}],
            submit=False), "cannot hold"), True)

        print()
        print("=== move between locations of one warehouse ===")
        move = _se(company, "Material Transfer", [{
            "qty": 30, "s_warehouse": wh, "t_warehouse": wh, "batch_no": batch,
            "use_serial_batch_fields": 1, "to_storage_location": L1,
        }], submit=False)
        made.append(move)
        check("source filled from where the batch is", move.items[0].storage_location, L1)
        move.items[0].to_storage_location = L1
        _set_item_locations([{"warehouse": wh, "storage_location": L1, "is_default": 1},
                             {"warehouse": wh, "storage_location": L2}])
        move.reload()
        move.items[0].to_storage_location = L2
        move.save()
        move.submit()
        check("batch now in L2", sl.location_stock(ITEM, wh, batch), {L2: 30.0})
        check("a location move is not stock leaving (reservations kept)",
              _consumed_qty_by_batch(frappe.get_doc("Stock Entry", move.name)), {})

        print()
        print("=== outward from the wrong location ===")
        check("refused on save, naming where it is", _throws(lambda: _se(company, "Material Issue", [{
            "qty": 5, "s_warehouse": wh, "batch_no": batch, "use_serial_batch_fields": 1,
            "storage_location": L1,
        }], submit=False), L2), True)
        blank = _se(company, "Material Issue", [{
            "qty": 5, "s_warehouse": wh, "batch_no": batch, "use_serial_batch_fields": 1,
        }], submit=False)
        made.append(blank)
        check("a blank location still saves (filled from where the batch is)", blank.items[0].storage_location, L2)

        print()
        print("=== a batch spread over two locations is split ===")
        back = _se(company, "Material Transfer", [{
            "qty": 10, "s_warehouse": wh, "t_warehouse": wh, "batch_no": batch,
            "use_serial_batch_fields": 1, "storage_location": L2, "to_storage_location": L1,
        }])
        made.append(back)
        check("now L1 10 / L2 20", sl.location_stock(ITEM, wh, batch), {L1: 10.0, L2: 20.0})
        issue = _se(company, "Material Issue", [{
            # One 3 m piece of this item is 30 Kg; the app derives Kg from the pieces.
            "qty": 30, "s_warehouse": wh, "batch_no": batch, "use_serial_batch_fields": 1,
            "custom_sec_qty": 1,
        }], submit=False)
        made.append(issue)
        got = sorted((r.storage_location, flt(r.qty, 2), flt(r.custom_sec_qty, 3)) for r in issue.items)
        check("two rows, by location, Nos in proportion", got, [(L1, 10.0, 0.333), (L2, 20.0, 0.667)])
        issue.submit()
        check("submitted; the batch is gone from both", sl.location_stock(ITEM, wh, batch), {})

        print()
        print("=== same-warehouse Repack keeps the source location ===")
        stock = _se(company, "Material Receipt", [{"qty": 20, "t_warehouse": wh, "to_storage_location": L2}])
        made.append(stock)
        b2 = sl.row_batches(frappe.get_doc("Stock Entry", stock.name).items[0], 20).popitem()[0]
        repack = frappe.get_doc({
            "doctype": "Stock Entry", "stock_entry_type": "Repack", "company": company,
            "items": [
                {"item_code": ITEM, "qty": 20, "s_warehouse": wh, "batch_no": b2, "use_serial_batch_fields": 1},
                {"item_code": ITEM, "qty": 20, "t_warehouse": wh},
            ],
        })
        sl.fill_locations(repack)
        check("consumed row from L2", repack.items[0].storage_location, L2)
        check("remnant back into L2, not the default", repack.items[1].to_storage_location, L2)

        print()
        print("=== Material Issue Plan ===")
        mip_name = frappe.get_all("Material Issue Plan", pluck="name", limit=1)
        if mip_name:
            mip = frappe.get_doc("Material Issue Plan", mip_name[0])
            mip.excess_return_warehouse = wh
            mip.fg_storage_location = None
            check("a saved plan needs the FG location",
                  _throws(lambda: sl.validate_mip_locations(mip), "mandatory"), True)
            check("and no entry is made into the warehouse without it",
                  _throws(lambda: sl.require_mip_location(mip, wh), "Storage Location"), True)
            mip.fg_storage_location = L1
            check("with it, both pass",
                  not _throws(lambda: sl.validate_mip_locations(mip))
                  and not _throws(lambda: sl.require_mip_location(mip, wh)), True)
            mip.fg_storage_location = "ZZTEST-NOT-HERE"
            check("a location of another warehouse is refused",
                  _throws(lambda: sl.validate_mip_locations(mip)), True)

        print()
        print("=== Material Planning shows where a batch is ===")
        mp_name = frappe.get_all("Material Planning", pluck="name", limit=1)
        if mp_name:
            mp = frappe.get_doc("Material Planning", mp_name[0])
            mp.for_warehouse = wh
            row = mp.append("material_mapping", {"item_code": ITEM, "batch": b2})
            sl.stamp_reserved_locations(mp)
            check("row stamped with the batch's location", row.storage_location, L2)

    finally:
        for se in reversed(made):
            try:
                if frappe.db.get_value("Stock Entry", se.name, "docstatus") == 1:
                    frappe.get_doc("Stock Entry", se.name).cancel()
            except Exception as e:
                print("   (could not cancel %s: %s)" % (se.name, e))
        _set_item_locations([])
        # Untick it again: other checks pick "any leaf warehouse" for their own
        # entries, and must not land in one that suddenly needs a Storage Location.
        frappe.db.set_value("Warehouse", wh, "custom_mandatory_storage_location", 0)
        frappe.db.commit()
        print()
        print("   test entries cancelled, nothing deleted")

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
