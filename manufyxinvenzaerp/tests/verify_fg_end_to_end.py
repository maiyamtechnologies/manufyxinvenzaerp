"""Finished goods in Kg and Nos, end to end: the worked example of the sep14 plan (§6).

sep14 FG plan (.claude/tasks/sep14_fg_uom_plan.md), package A8. One drawing of 10 Nos at
Cust Weight (per Nos) 30 / Cust Weight (Total) 300, on a Sales Order line of 300 Kg /
10 Nos, at a Rate Schedule of 20 per Kg, taken through every document with the app's
own functions:

  Sales Order      upload sheet (real parser) -> Verify Raw Materials -> Create Drawing
  Drawing / BOM    submit, Final Revision, BOM 300 Kg / 10 Nos
  PP 1             4 Nos -> 120 Kg                         JWO 1: 120 Kg / 4 Nos, 20 / Kg, 2,400
  Final SE 1       4 Nos weighed 122 Kg                    batch FG-<SO>-D1: 4 / 122 / 30.5
  DN 1             3 Nos -> 91.5 Kg                        batch 1 / 30.5
  PP 2             6 Nos -> 180 Kg (7 refused)             JWO 2: 180 Kg / 6 Nos, 3,600
  Final SE 2       6 Nos weighed 181 Kg                    batch 7 / 211.5 / 30.214
  DN 2             7 Nos -> the exact 211.5 Kg left        batch 0
  Return           2 Nos against DN 2 -> -60.429 Kg        batch 2 / 60.429
  SI from DN 1     3 Nos -> 91.5 Kg (the DN's actual Kg per Nos)
  SI from SO       5 Nos -> 150 Kg (300 / 10 x 5, the ordered Kg per Nos); the last 2
                   Nos then take the exact 58.5 Kg still unbilled (300 - 91.5 - 150)
  Production Report  Job Work Amount 2,400 + 3,600 for the drawing

SHORTCUTS (steps of the real chain that are stood in for, and why):
  1. Operations. Each Job Work Order's operation entries are created by the app
     (_create_soes_for_sco), but the pieces the LAST operation has finished are written
     straight onto its SOE Drawing Detail (completed_qty_nos) instead of logging them
     through every operation and its inspection -- the same shortcut
     verify_fg_final_stock_entry.py uses. The Final Stock Entry reads exactly that figure.
  2. Raw material at the supplier. The job's material is a ZZFG- consumable received into
     Stores and moved to the supplier warehouse by a Material Transfer tagged with the
     Job Work Order (custom_sco_ref), instead of the Material Planning -> reservation ->
     Material Issue Plan transfer popup. The Final Stock Entry consumes it as it would
     the real material; the finished-goods rows under test do not depend on it. The
     Material Issue Plan's Supplier / WIP and Finished Goods warehouses, which the user
     fills on the form, are written onto it when blank (Work In Progress / Finished
     Goods - MIPL), and so is the Job Work Order's Transferred Weight, which the app
     rolls up only from "Send to Subcontractor" entries and CNC -> supplier transfers
     (stock_entry._update_sco_transferred_weight), not from this Stores -> WIP transfer.
  3. Drawing buttons. The Sales Order's Submit Drawing / Mark as Final Revision / Create
     and Submit BOM steps are called directly (Drawing.submit, mark_as_final_revision,
     create_bom_from_drawing + submit) rather than through process_drawings, whose error
     path rolls back the whole transaction.
  4. Over-delivery. Final SE 2 weighs 303 Kg against the 300 Kg ordered, so ERPNext's
     over-delivery allowance (0% on the site, D10) would refuse DN 2. The test's own
     item carries a 5% allowance.

EVERYTHING runs inside ONE database transaction that is rolled back at the end:
frappe.db.commit is a no-op for the run (Verify Raw Materials and Create Drawing commit
on purpose). Every document is named ZZFG-A8-...: those this test inserts are named
outright, and those the app's own functions insert (Drawing, Production Plan, Job Work
Order, Material Issue Plan, operation entries, Stock Entries, ledger entries ...) get a
ZZFG-A8- name from a naming guard that refuses every naming-series counter for the
duration -- so no live series number is consumed even inside the transaction. After
the rollback the test checks that nothing is left and that tabSeries is unchanged.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_end_to_end.run
"""

import os
import tempfile

import frappe
from frappe.utils import add_days, flt, nowdate

checks = []

PREFIX = "ZZFG-A8-"
COMPANY = "Manufyx Invenza Private Limited"
FG_WH = "Finished Goods - MIPL"
STORES = "Stores - MIPL"
CUSTOMER = "ZZFG-A8 Customer"
FG_ITEM = "ZZFG-A8-FG"
CONSUMABLE = "ZZFG-A8-NUT"
RATE_SCHEDULE = "ZZFG-A8-RS20"
RM_ITEM = "FLAT"  # borrowed read-only: named on the drawing's raw-material row only
DUNO = "D1"

series_refused = []  # (doctype, series key) the naming guard turned into ZZFG-A8- names


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-68s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def refused(fn):
    """The message of the exception fn raises (its writes rolled back), or None."""
    frappe.db.savepoint("zzfg_a8_try")
    try:
        fn()
    except Exception as e:  # noqa: BLE001 -- any refusal counts, the text is checked
        frappe.db.rollback(save_point="zzfg_a8_try")
        frappe.clear_messages()
        return frappe.utils.strip_html(str(e)) or "refused"
    frappe.db.rollback(save_point="zzfg_a8_try")
    return None


def _name(kind=""):
    """ZZFG-A8- + 8 characters = 16: India Compliance refuses longer invoice names."""
    return PREFIX + kind + frappe.generate_hash(length=8 - len(kind)).upper()


def _ins(doc, kind=""):
    doc.insert(ignore_permissions=True, set_name=_name(kind))
    return doc


# ── the transaction and the naming guard ──────────────────────────────────────


class _SeriesUsed(Exception):
    pass


class one_transaction:
    """Hold commits off, refuse naming-series counters, roll everything back on exit."""

    def __enter__(self):
        import frappe.model.base_document as base_document
        import frappe.model.document as document
        import frappe.model.naming as naming

        self._mods = (naming, document, base_document)
        self._getseries = naming.getseries
        self._set_new_name = naming.set_new_name
        self._commit = frappe.db.commit

        def getseries(key, digits):
            raise _SeriesUsed(key)

        real_set_new_name = self._set_new_name

        def set_new_name(doc):
            try:
                real_set_new_name(doc)
            except _SeriesUsed as e:
                doc.name = _name()
                series_refused.append((doc.doctype, e.args[0]))

        naming.getseries = getseries
        for mod in self._mods:
            mod.set_new_name = set_new_name
        frappe.db.commit = lambda *a, **k: None
        return self

    def __exit__(self, *exc):
        naming = self._mods[0]
        frappe.db.rollback()
        naming.getseries = self._getseries
        for mod in self._mods:
            mod.set_new_name = self._set_new_name
        frappe.db.commit = self._commit
        frappe.local.message_log = []
        frappe.clear_cache(doctype="Item")
        return False


# ── masters (all inside the transaction) ──────────────────────────────────────


def _masters():
    frappe.get_doc({
        "doctype": "Customer", "customer_name": CUSTOMER,
        "customer_type": "Company", "gst_category": "Unregistered",
    }).insert(ignore_permissions=True, set_name=CUSTOMER)
    frappe.get_doc({
        "doctype": "Item", "item_code": FG_ITEM, "item_name": "ZZFG A8 Finished Good",
        "item_group": "Fin Goods Item", "custom_parent_item_group": "Finished Goods",
        "stock_uom": "Kg", "custom_secondary_uom": "Nos", "gst_hsn_code": "730890",
        "is_stock_item": 1, "is_sales_item": 1, "is_purchase_item": 0,
        "include_item_in_manufacturing": 1, "has_batch_no": 1, "create_new_batch": 0,
        "valuation_rate": 50, "over_delivery_receipt_allowance": 5,
    }).insert(ignore_permissions=True)
    group, hsn = frappe.db.get_value("Item", "Nut-M20", ["item_group", "gst_hsn_code"])
    frappe.get_doc({
        "doctype": "Item", "item_code": CONSUMABLE, "item_name": CONSUMABLE,
        "item_group": group, "gst_hsn_code": hsn, "custom_parent_item_group": "Nuts and Bolts",
        "stock_uom": "Nos", "custom_secondary_uom": "Kg", "custom_unit_weight": 0.5,
        "is_stock_item": 1, "include_item_in_manufacturing": 1, "has_batch_no": 0,
        "valuation_rate": 40,
    }).insert(ignore_permissions=True)
    frappe.get_doc({
        "doctype": "Rate Schedule", "rs_no": RATE_SCHEDULE, "type": "Inhouse",
        "job_nature": frappe.db.get_value("Job Nature", {}, "name"), "rate_per_kg": 20,
    }).insert(ignore_permissions=True)


def _sheet():
    """The upload sheet with the template's own headers: one drawing, one material."""
    import io

    import openpyxl

    from manufyxinvenzaerp.drawing_management.so_drawing_import import download_bom_template

    frappe.response.clear()
    download_bom_template()
    wb = openpyxl.load_workbook(io.BytesIO(frappe.response["filecontent"]), read_only=True)
    header = list(next(wb.active.iter_rows(values_only=True)))
    wb.close()
    frappe.response.clear()

    values = {
        "Assembly Group": "ZZFG", "Customer Drawing Number": PREFIX + "CDN-1",
        "DUNO/Mark No": DUNO, "FG Item": FG_ITEM, "Total Qty": 10,
        "Cust Weight (per Nos)": 30, "Cust Weight (Total)": 300,
        "Nature of Work": "", "Rate Schedule": RATE_SCHEDULE,
        "Item No": "1", "Material Code": RM_ITEM, "Grade": "", "Thickness": 0, "Width": 0,
        "Length": 1000, "Reqd Raw Material Qty": 2,
    }
    out = openpyxl.Workbook()
    out.active.append(header)
    out.active.append([values.get(h, "") for h in header])
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    out.save(path)
    return header, path


# ── readers ───────────────────────────────────────────────────────────────────


def _batch_state(batch):
    """(batch Nos, Actual Kg per Nos, Nos in the FG warehouse, Kg in the FG warehouse)."""
    from manufyxinvenzaerp.production_management import fg_stock

    b = frappe.db.get_value("Batch", batch, ["custom_sec_qty", "custom_weight_per_piece"], as_dict=True)
    avail = fg_stock.fg_batch_available(batch, FG_WH)
    return (flt(b.custom_sec_qty, 3), flt(b.custom_weight_per_piece, 3), avail["nos"], avail["kg"])


def _so_line(line, field):
    return flt(frappe.db.get_value("Sales Order Item", line, field), 3)


def _fg_rows(doc):
    return [r for r in doc.items if r.item_code == FG_ITEM]


# ── steps ─────────────────────────────────────────────────────────────────────


def _sales_order_to_bom():
    from manufyxinvenzaerp.drawing_management import so_drawing_import as imp
    from manufyxinvenzaerp.drawing_management.drawing_utils import (
        create_bom_from_drawing, mark_as_final_revision,
    )

    print("=== 1. Sales Order: upload sheet, Verify, Create Drawing ===")
    so = frappe.get_doc({
        "doctype": "Sales Order", "company": COMPANY, "customer": CUSTOMER,
        "transaction_date": nowdate(), "delivery_date": add_days(nowdate(), 30),
        "po_no": PREFIX + "PO",
        "items": [{
            "item_code": FG_ITEM, "qty": 300, "uom": "Kg", "rate": 100, "warehouse": FG_WH,
            "custom_sec_qty": 10, "delivery_date": add_days(nowdate(), 30),
        }],
    })
    _ins(so, "SO")
    header, path = _sheet()
    check("template headers carry both customer weights",
          [h for h in header if h.startswith("Cust Weight")],
          ["Cust Weight (per Nos)", "Cust Weight (Total)"])
    frappe.db.set_value("Sales Order", so.name, "custom_bom_excel_file",
                        "/private/files/zzfg-a8.xlsx", update_modified=False)
    real_get_path = imp._get_file_path
    imp._get_file_path = lambda url: path
    try:
        imp.parse_bom_excel(so.name)
    finally:
        imp._get_file_path = real_get_path
        os.unlink(path)
    staged = frappe.db.get_value("Sales Order DUNO Item", {"parent": so.name},
                                 ["name", "weight_per_pcs", "total_weight", "total_quantity"], as_dict=True)
    check("Drawing List row: 30 per Nos x 10 Nos = 300 Total",
          (flt(staged.weight_per_pcs, 3), flt(staged.total_quantity, 3), flt(staged.total_weight, 3)),
          (30.0, 10.0, 300.0))

    err = refused(lambda: imp.create_drawings_from_import(so.name, 0, 30))
    check("Create Drawing before Verify is refused on the server",
          bool(err) and "not verified" in err, True)
    res = imp.verify_raw_materials(so.name)
    for i in res["issues"]:
        print("       issue:", frappe.utils.strip_html(i)[:160])
    check("Verify Raw Materials passes (300 Kg / 10 Nos line, 30 x 10 = 300)", res["verified"], True)
    made = [r for r in imp.create_drawings_from_import(so.name, 0, 30)["results"] if r["status"] == "success"]
    check("one Drawing created", len(made), 1)
    drawing = made[0]["drawing"]
    d = frappe.db.get_value("Drawing", drawing, ["weight_per_pcs", "customer_provided_wt",
                                                 "no_of_qty_to_manufacture", "rs_rate_per_kg",
                                                 "duno_mark_no"], as_dict=True)
    check("Drawing: per Nos 30, Total 300, 10 Nos, 20 / Kg, DUNO D1",
          (flt(d.weight_per_pcs, 3), flt(d.customer_provided_wt, 3),
           flt(d.no_of_qty_to_manufacture, 3), flt(d.rs_rate_per_kg, 2), d.duno_mark_no),
          (30.0, 300.0, 10.0, 20.0, DUNO))

    so = frappe.get_doc("Sales Order", so.name)
    so.submit()
    so = frappe.get_doc("Sales Order", so.name)
    so.custom_duno_items[0].total_weight = 310
    err = refused(lambda: so.save(ignore_permissions=True))
    check("the drawn Drawing List row is locked (Update Customer Weight only)",
          bool(err) and "Update Customer Weight" in err, True)

    frappe.get_doc("Drawing", drawing).submit()
    mark_as_final_revision(drawing)
    bom_name = create_bom_from_drawing(drawing)
    frappe.get_doc("BOM", bom_name).submit()
    bom = frappe.db.get_value("BOM", bom_name, ["quantity", "custom_sec_qty",
                                                "custom_cust_weight_per_nos", "custom_cust_weight_total"],
                              as_dict=True)
    check("BOM: 300 Kg, Qty (Nos) 10, Cust Weight 30 / 300",
          (flt(bom.quantity, 3), flt(bom.custom_sec_qty, 3),
           flt(bom.custom_cust_weight_per_nos, 3), flt(bom.custom_cust_weight_total, 3)),
          (300.0, 10.0, 30.0, 300.0))
    print("   (Sales Order %s, Drawing %s, BOM %s)" % (so.name, drawing, bom_name))
    return frappe._dict(so=so.name, line=so.items[0].name, drawing=drawing, bom=bom_name)


def _plan(c, nos, label, other_plan=None):
    """Production Plan from the BOM's own button, set to `nos`, submitted."""
    from manufyxinvenzaerp.drawing_management.drawing_utils import create_production_plan_from_bom

    pp = frappe.get_doc("Production Plan", create_production_plan_from_bom(c.bom))
    check("%s: defaults to the %s Nos left" % (label, 10 - (4 if other_plan else 0)),
          flt(pp.po_items[0].custom_sec_qty), 10.0 - (4 if other_plan else 0))
    if other_plan:
        pp.po_items[0].custom_sec_qty = nos + 1
        msg = refused(lambda: pp.save(ignore_permissions=True)) or ""
        check("%s: %s Nos is refused, naming %s" % (label, nos + 1, other_plan), other_plan in msg, True)
        pp.reload()
    pp.po_items[0].custom_sec_qty = nos
    pp.save(ignore_permissions=True)
    pp.submit()
    r = pp.po_items[0]
    check("%s: %s Nos -> %s Kg planned" % (label, nos, nos * 30),
          (flt(r.custom_sec_qty), flt(r.planned_qty, 3)), (float(nos), float(nos * 30)))
    return pp


def _job_work_order(pp, nos, label):
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        create_sco_and_mip_from_production_plan, create_supplier_operation_entries,
    )

    res = create_sco_and_mip_from_production_plan(pp.name)
    sco = frappe.get_doc("Subcontracting Order", res["sco"])
    item, dr = sco.items[0], sco.custom_drawing_items[0]
    kg, amount = float(nos * 30), float(nos * 30 * 20)
    check("%s: %s Kg / %s Nos, rate 20 / Kg, amount %s" % (label, kg, nos, amount),
          (flt(item.qty, 3), flt(item.custom_sec_qty), flt(item.rate, 2), flt(item.amount, 2)),
          (kg, float(nos), 20.0, amount))
    check("%s drawing row: %s Nos, Rate / Kg 20, Job Work Amount %s" % (label, nos, amount),
          (flt(dr.qty_to_manufacture), flt(dr.rate_per_kg, 2), flt(dr.job_work_amount, 2)),
          (float(nos), 20.0, amount))
    sco.submit()
    create_supplier_operation_entries(sco.name)
    return sco.name, res["mip"]


def _material_at_supplier(sco_name, mip_name):
    """SHORTCUT 2: the job's material reaches the supplier warehouse, tagged to the job."""
    from manufyxinvenzaerp.subcontracting_management.subcontracting import _get_sco_supplier_warehouse

    sco = frappe.get_doc("Subcontracting Order", sco_name)
    supplier_wh = _get_sco_supplier_warehouse(sco)
    if not supplier_wh:
        supplier_wh = "Work In Progress - MIPL"
        frappe.db.set_value("Material Issue Plan", mip_name, "supplier_warehouse", supplier_wh,
                            update_modified=False)
        print("   (Material Issue Plan had no Supplier / WIP Warehouse: set to %s)" % supplier_wh)
    # The Finished Goods Warehouse the user picks on the Material Issue Plan; the Final
    # Stock Entry books the pieces into it.
    if not frappe.db.get_value("Material Issue Plan", mip_name, "excess_return_warehouse"):
        frappe.db.set_value("Material Issue Plan", mip_name, "excess_return_warehouse", FG_WH,
                            update_modified=False)
    for se_type, row in (
        ("Material Receipt", {"t_warehouse": STORES, "basic_rate": 40}),
        ("Material Transfer", {"s_warehouse": STORES, "t_warehouse": supplier_wh}),
    ):
        se = frappe.get_doc({
            "doctype": "Stock Entry", "stock_entry_type": se_type, "company": COMPANY,
            "custom_sco_ref": sco_name if se_type == "Material Transfer" else None,
            "items": [dict({"item_code": CONSUMABLE, "qty": 20, "uom": "Nos", "conversion_factor": 1}, **row)],
        })
        _ins(se, "SE")
        se.submit()
    if not flt(frappe.db.get_value("Subcontracting Order", sco_name, "custom_transferred_weight_kg")):
        frappe.db.set_value("Subcontracting Order", sco_name, "custom_transferred_weight_kg", 10,
                            update_modified=False)
        print("   (transferred weight not rolled up from the consumable: set on the Job Work Order)")


def _final_stock_entry(c, sco_name, done_nos, weighed, label):
    """SHORTCUT 1: the last operation has finished `done_nos`; book them."""
    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        _final_operation, create_finished_goods_entry, get_final_stock_entry_preview,
    )

    final = _final_operation(sco_name)
    frappe.db.set_value("SOE Drawing Detail", {"parent": final.name, "drawing": c.drawing},
                        "completed_qty_nos", done_nos, update_modified=False)
    pv = [d for d in get_final_stock_entry_preview(sco_name)["drawings"] if d["drawing"] == c.drawing][0]
    check("%s preview: %s Nos ready, planned %s Kg" % (label, done_nos, done_nos * 30),
          (pv["ready_to_book"], pv["planned_kg"]), (float(done_nos), float(done_nos * 30)))
    se = frappe.get_doc("Stock Entry", create_finished_goods_entry(sco_name)["name"])
    row = _fg_rows(se)[0]
    check("%s FG row: %s Kg = Nos x 30, %s Nos, batch FG-<SO>-D1" % (label, done_nos * 30, done_nos),
          (flt(row.qty, 3), row.uom, flt(row.custom_sec_qty), row.batch_no),
          (float(done_nos * 30), "Kg", float(done_nos), c.batch))
    row.qty = weighed  # the weighed figure (Edit FG Stock Kg is on by default)
    se.save(ignore_permissions=True)
    check("%s: the weighed %s Kg stands" % (label, weighed), flt(_fg_rows(se)[0].qty, 3), float(weighed))
    se.submit()
    return se


def _delivery(c, nos, label):
    from manufyxinvenzaerp.selling_management import delivery_note as dnmod
    from manufyxinvenzaerp.selling_management.mapping import make_delivery_note

    dn = make_delivery_note(c.so)
    fg = _fg_rows(dn)
    pending = 10 - _so_line(c.line, "custom_delivered_sec_qty")
    check("%s: Sales Order -> DN maps the %s Nos pending, no batch yet" % (label, pending),
          (len(fg), flt(fg[0].custom_sec_qty), fg[0].batch_no or None), (1, pending, None))
    offered = [b for b in dnmod.get_fg_batches(dn.as_dict()) if b["batch_no"] == c.batch]
    check("%s: Get FG Batches offers the drawing batch" % label, len(offered), 1)
    # What the form's "Add Rows" does: one row per ticked batch, copied from the
    # unbatched row, which is then removed.
    template = fg[0].as_dict()
    dn.items = []
    r = {k: v for k, v in template.items() if k not in ("name", "idx", "parent", "doctype")}
    r.update({"batch_no": c.batch, "custom_sec_qty": nos, "qty": 1, "use_serial_batch_fields": 1})
    dn.append("items", r)
    _ins(dn, "DN")
    dn.submit()
    return dn, offered[0]


def _run():
    from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return

    from manufyxinvenzaerp.selling_management.mapping import (
        make_sales_invoice_from_dn, make_sales_invoice_from_so,
    )

    frappe.set_user("Administrator")
    _masters()
    c = _sales_order_to_bom()
    c.batch = "FG-%s-%s" % (c.so, DUNO)

    print()
    print("=== 2. PP 1: 4 Nos -> Job Work Order 1 -> Final Stock Entry 1 (122 Kg) ===")
    pp1 = _plan(c, 4, "PP 1")
    sco1, mip1 = _job_work_order(pp1, 4, "JWO 1")
    _material_at_supplier(sco1, mip1)
    _final_stock_entry(c, sco1, 4, 122, "Final SE 1")
    check("batch 4 Nos / 122 Kg -> 30.5 per Nos", _batch_state(c.batch), (4.0, 30.5, 4.0, 122.0))
    b = frappe.db.get_value("Batch", c.batch, ["custom_sales_order", "custom_customer", "custom_drawing",
                                               "custom_duno_mark_no", "custom_job_work_order",
                                               "custom_cust_weight_per_nos"], as_dict=True)
    check("batch carries SO, customer, drawing, DUNO, JWO, planned 30 per Nos",
          (b.custom_sales_order, b.custom_customer, b.custom_drawing, b.custom_duno_mark_no,
           b.custom_job_work_order, flt(b.custom_cust_weight_per_nos, 3)),
          (c.so, CUSTOMER, c.drawing, DUNO, sco1, 30.0))

    print()
    print("=== 3. DN 1: 3 Nos ===")
    dn1, offer = _delivery(c, 3, "DN 1")
    check("DN 1: the batch was offered with 4 Nos / 122 Kg",
          (offer["available_nos"], offer["available_kg"]), (4.0, 122.0))
    check("DN 1: 3 Nos -> 91.5 Kg (the typed 1 Kg replaced)", flt(_fg_rows(dn1)[0].qty, 3), 91.5)
    check("batch 1 Nos / 30.5 Kg", _batch_state(c.batch), (1.0, 30.5, 1.0, 30.5))
    check("Sales Order Delivered (Nos) = 3", _so_line(c.line, "custom_delivered_sec_qty"), 3.0)

    print()
    print("=== 4. PP 2: 6 Nos -> Job Work Order 2 -> Final Stock Entry 2 (181 Kg) ===")
    pp2 = _plan(c, 6, "PP 2", other_plan=pp1.name)
    sco2, mip2 = _job_work_order(pp2, 6, "JWO 2")
    _material_at_supplier(sco2, mip2)
    _final_stock_entry(c, sco2, 6, 181, "Final SE 2")
    check("same batch: 7 Nos / 211.5 Kg -> 30.214 per Nos", _batch_state(c.batch), (7.0, 30.214, 7.0, 211.5))

    print()
    print("=== 5. DN 2: 7 Nos ===")
    dn2, _o = _delivery(c, 7, "DN 2")
    check("DN 2: 7 Nos -> the exact 211.5 Kg left", flt(_fg_rows(dn2)[0].qty, 3), 211.5)
    check("batch empty", _batch_state(c.batch)[2:], (0.0, 0.0))
    check("Sales Order Delivered (Nos) = 10", _so_line(c.line, "custom_delivered_sec_qty"), 10.0)
    check("ERPNext delivered Kg = 303 (91.5 + 211.5)", _so_line(c.line, "delivered_qty"), 303.0)

    print()
    print("=== 6. Return 2 Nos against DN 2 ===")
    ret = make_sales_return(dn2.name)
    _fg_rows(ret)[0].custom_sec_qty = 2
    _ins(ret, "RT")
    rr = _fg_rows(ret)[0]
    check("return: -2 Nos / -60.429 Kg, same batch", (flt(rr.custom_sec_qty), flt(rr.qty, 3), rr.batch_no),
          (-2.0, -60.429, c.batch))
    ret.submit()
    check("batch 2 Nos / 60.429 Kg back (30.214 per Nos)", _batch_state(c.batch),
          (2.0, flt(60.429 / 2, 3), 2.0, 60.429))
    check("Sales Order Delivered (Nos) = 8", _so_line(c.line, "custom_delivered_sec_qty"), 8.0)

    print()
    print("=== 7. Sales Invoice from DN 1, then from the Sales Order ===")
    si1 = make_sales_invoice_from_dn(dn1.name)
    r = _fg_rows(si1)[0]
    check("SI from DN 1: 3 Nos / 91.5 Kg (the DN's actual 30.5 per Nos)",
          (flt(r.custom_sec_qty), flt(r.qty, 3)), (3.0, 91.5))
    _ins(si1)
    si1.submit()
    check("DN 1 row Billed (Nos) = 3",
          flt(frappe.db.get_value("Delivery Note Item", _fg_rows(dn1)[0].name, "custom_billed_sec_qty")), 3.0)
    check("SO line Billed (Nos) = 3", _so_line(c.line, "custom_billed_sec_qty"), 3.0)

    si2 = make_sales_invoice_from_so(c.so)
    r = _fg_rows(si2)[0]
    # All 7 unbilled Nos are the last pending pieces, so they take the exact Kg still
    # unbilled on the line: 300 - the 91.5 DN 1 billed at its actual weight (R2).
    check("SI from SO defaults to the 7 Nos unbilled = the exact 208.5 Kg left",
          (flt(r.custom_sec_qty), flt(r.qty, 3)), (7.0, 208.5))
    r.custom_sec_qty = 5
    _ins(si2)
    check("SI from SO: 5 Nos -> 150 Kg (300 / 10 x 5)", flt(_fg_rows(si2)[0].qty, 3), 150.0)
    check("amount priced on the Kg (150 x 100)", flt(_fg_rows(si2)[0].amount, 2), 15000.0)
    si2.submit()
    check("SO line Billed (Nos) = 8", _so_line(c.line, "custom_billed_sec_qty"), 8.0)
    t = make_sales_invoice_from_so(c.so)
    check("the next SI from SO offers the last 2 Nos at the exact 58.5 Kg left (300 - 91.5 - 150)",
          (flt(_fg_rows(t)[0].custom_sec_qty), flt(_fg_rows(t)[0].qty, 3)), (2.0, 58.5))
    t.update_stock = 1
    for row in t.items:
        row.warehouse = FG_WH
    err = refused(lambda: _ins(t))
    check("Update Stock on an FG invoice is refused", bool(err) and "Update Stock" in err, True)

    print()
    print("=== 8. Production Report: Job Work Amount ===")
    _report(c, sco1, sco2)


def _report(c, sco1, sco2):
    """The report's row for each Job Work Order: the drawing's Rate / Kg and Job Work Amount."""
    from manufyxinvenzaerp.production_management.report.production_report import production_report as pr

    for sco, amount in ((sco1, 2400.0), (sco2, 3600.0)):
        columns, data = pr.execute(frappe._dict(subcontracting_order=sco))[:2]
        keys = [col.get("fieldname") for col in columns if isinstance(col, dict)]
        rows = [r for r in data if isinstance(r, dict) and r.get("drawing") == c.drawing]
        check("%s: Job Work Amount column, one drawing row" % sco,
              ("job_work_amount" in keys, len(rows)), (True, 1))
        if rows:
            check("%s: Rate / Kg 20, Job Work Amount %s" % (sco, amount),
                  (flt(rows[0].get("rate_per_kg"), 2), flt(rows[0].get("job_work_amount"), 2)), (20.0, amount))


# ── run ───────────────────────────────────────────────────────────────────────


def _series_snapshot():
    return dict(frappe.db.sql("SELECT name, current FROM `tabSeries`"))


def run():
    before = _series_snapshot()
    with one_transaction():
        try:
            _run()
        except Exception as e:
            checks.append(False)
            import traceback

            traceback.print_exc()
            print("  FAIL the run raised %s: %s" % (type(e).__name__, str(e)[:400]))

    print()
    print("=== after rollback ===")
    if series_refused:
        kinds = sorted({"%s (%s)" % (dt, key) for dt, key in series_refused})
        print("   naming series refused and replaced by ZZFG-A8- names: %s" % ", ".join(kinds))
    check("naming series counters unchanged", _series_snapshot() == before, True)
    check("test items gone", frappe.db.count("Item", {"name": ["in", [FG_ITEM, CONSUMABLE]]}), 0)
    check("no FG batch of the test item left", frappe.db.count("Batch", {"item": FG_ITEM}), 0)
    for doctype in ("Sales Order", "Drawing", "Production Plan", "Subcontracting Order",
                    "Material Issue Plan", "Supplier Operation Entry", "Stock Entry",
                    "Delivery Note", "Sales Invoice", "Customer", "Rate Schedule"):
        check("no %s named ZZFG-A8-" % doctype, frappe.db.count(doctype, {"name": ["like", PREFIX + "%"]}), 0)
    check("no BOM of the test item", frappe.db.count("BOM", {"item": FG_ITEM}), 0)
    check("no ledger entry named ZZFG-A8-",
          frappe.db.count("Stock Ledger Entry", {"name": ["like", PREFIX + "%"]})
          + frappe.db.count("GL Entry", {"name": ["like", PREFIX + "%"]}), 0)

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
