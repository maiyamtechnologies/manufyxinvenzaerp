"""Finished goods are delivered by the piece, from their drawing batch (sep14 FG plan, A5).

The worked example of section 6: one drawing batch of a 300 Kg / 10 Nos Sales Order line.

  1. Sales Order -> Delivery Note maps the FG line with its pending Nos (10), no batch;
     the non-FG line loses the Nos UOM the mapper copied. An FG row without a batch
     cannot be saved or submitted.
  2. Get FG Batches lists the order's batches with pieces in the row's warehouse (not
     another order's), with a Nos proposal capped by what is pending.
  3. Refused: 5 Nos from a batch holding 4, a batch of another Sales Order, part pieces,
     more Nos on one Sales Order line than it has pending (R4).
  4. DN 1: 3 Nos -> 91.5 Kg (batch 4 Nos / 122 Kg). The typed Kg is replaced.
  5. The second Final Stock Entry's 6 Nos / 181 Kg arrive (a receipt here): 7 / 211.5.
     DN 2: 7 Nos -> the exact 211.5 Kg left. ERPNext refuses its 303 Kg against 300
     ordered while the item's over-delivery allowance is 0; the test sets 5% on its
     own item for DN 2 and puts 0 back. Sales Order Delivered (Nos) = 10.
  6. Return 2 Nos against DN 2 -> -60.429 Kg back into the same batch; Delivered
     (Nos) = 8; the next DN proposes 2 Nos; the DN -> SI path (A6) sees 5 Nos left
     on DN 2. Returning more than is still out, or into another batch, is refused;
     the last 5 would take the exact 151.071 Kg.
  7. Every cancel puts Delivered (Nos) and the batch back. (The 5% allowance stays
     on until then: cancelling the return brings ERPNext's delivered Kg back to 303.)
  8. Pieces heavier than ordered (10 Nos weigh 340 Kg against 300 ordered): once 9
     Nos / 306 Kg have gone ERPNext no longer maps the line, but the override still
     offers its last Nos; Get FG Batches works from it; R4 still caps the Nos, and
     only ERPNext's over-delivery allowance limits the Kg (refused at 0%, fine at
     20%).
  A batch tied to no Sales Order (made by hand) is refused on a Delivery Note row.

EVERYTHING runs inside one transaction that is rolled back at the end, and
frappe.db.commit is disabled for the run, so a stray commit fails the test instead
of saving anything. Every document is also named outright (ZZFG-A5-...), so no
live naming series is touched even inside the transaction.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_fg_delivery_note.run
"""

import frappe
from frappe.utils import add_days, flt, nowdate

from manufyxinvenzaerp.production_management import fg_stock

checks = []

COMPANY = "Manufyx Invenza Private Limited"
WAREHOUSE = "Finished Goods - MIPL"
CUSTOMER = "ZZFG-A5 Customer"
FG_ITEM = "ZZFG-A5-FG"
NON_FG_ITEM = "Bolt-M16X85"  # borrowed read-only: only put on a Sales Order


def check(label, got, want):
	ok = got == want
	checks.append(ok)
	print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def raises(label, fn, text):
	"""fn must throw a message containing `text`; whatever it wrote is rolled back."""
	frappe.db.savepoint("zzfg_a5_try")
	try:
		fn()
	except Exception as e:
		frappe.db.rollback(save_point="zzfg_a5_try")
		msg = str(e)
		frappe.clear_messages()
		check(label, text.lower() in msg.lower(), True)
		if text.lower() not in msg.lower():
			print("       message was: %s" % msg[:300])
		return
	frappe.db.rollback(save_point="zzfg_a5_try")
	check(label, "no error", "refused")


def _name(kind=""):
	return "ZZFG-A5-" + kind + frappe.generate_hash(length=8 - len(kind)).upper()


def _ins(doc, kind=""):
	doc.insert(ignore_permissions=True, set_name=_name(kind))
	return doc


# ── masters and stock (all inside the transaction) ────────────────────────────


def _masters():
	frappe.get_doc({
		"doctype": "Customer", "customer_name": CUSTOMER,
		"customer_type": "Company", "gst_category": "Unregistered",
	}).insert(ignore_permissions=True, set_name=CUSTOMER)
	frappe.get_doc({
		"doctype": "Item", "item_code": FG_ITEM, "item_name": "ZZFG A5 Finished Good",
		"item_group": "Fin Goods Item", "custom_parent_item_group": "Finished Goods",
		"stock_uom": "Kg", "custom_secondary_uom": "Nos", "gst_hsn_code": "730890",
		"is_stock_item": 1, "is_sales_item": 1, "is_purchase_item": 0,
		"has_batch_no": 1, "create_new_batch": 0, "valuation_rate": 50,
	}).insert(ignore_permissions=True)


def _make_so(lines):
	so = frappe.get_doc({
		"doctype": "Sales Order", "company": COMPANY, "customer": CUSTOMER,
		"transaction_date": nowdate(), "delivery_date": add_days(nowdate(), 10),
		"items": [
			dict(line, delivery_date=add_days(nowdate(), 10), warehouse=WAREHOUSE)
			for line in lines
		],
	})
	_ins(so, "SO")
	so.submit()
	return so


def _batch(so, duno):
	"""An FG batch as the Final Stock Entry makes it, tied to the Sales Order
	(so=None: a batch made by hand, tied to no order)."""
	b = frappe.get_doc({
		"doctype": "Batch", "batch_id": _name("B" + duno), "item": FG_ITEM,
		"custom_sales_order": so.name if so else None, "custom_customer": so.customer if so else None,
		"custom_duno_mark_no": duno, "custom_cust_weight_per_nos": 30,
		"custom_sec_uom": "Nos", "custom_sec_qty": 0,
	})
	b.insert(ignore_permissions=True)
	return b.name


def _receive(batch, nos, kg):
	"""Material Receipt of FG pieces into a batch (stands in for the Final Stock Entry)."""
	se = frappe.get_doc({
		"doctype": "Stock Entry", "company": COMPANY,
		"stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
		"items": [{
			"item_code": FG_ITEM, "qty": kg, "uom": "Kg", "conversion_factor": 1,
			"t_warehouse": WAREHOUSE, "basic_rate": 50, "batch_no": batch,
			"use_serial_batch_fields": 1, "custom_sec_qty": nos, "custom_sec_uom": "Nos",
		}],
	})
	_ins(se, "SE")
	se.submit()
	return se


def _state(batch):
	"""(batch Nos, Actual Kg per Nos, Nos in the warehouse, Kg in the warehouse)."""
	b = frappe.db.get_value("Batch", batch, ["custom_sec_qty", "custom_weight_per_piece"], as_dict=True)
	avail = fg_stock.fg_batch_available(batch, WAREHOUSE)
	return (flt(b.custom_sec_qty, 3), flt(b.custom_weight_per_piece, 3), avail["nos"], avail["kg"])


def _delivered(so_detail):
	return flt(frappe.db.get_value("Sales Order Item", so_detail, "custom_delivered_sec_qty"), 3)


def _fg_rows(doc):
	return [r for r in doc.items if r.item_code == FG_ITEM]


def _dn_from_so(so, rows):
	"""Sales Order -> Delivery Note, the FG line replaced by `rows` [(batch, nos, kg typed)]."""
	from manufyxinvenzaerp.selling_management.mapping import make_delivery_note

	dn = make_delivery_note(so.name)
	template = _fg_rows(dn)[0].as_dict()
	dn.items = []
	for batch, nos, kg in rows:
		row = {k: v for k, v in template.items() if k not in ("name", "idx", "parent", "doctype")}
		row.update({"batch_no": batch, "custom_sec_qty": nos, "qty": kg, "use_serial_batch_fields": 1})
		dn.append("items", row)
	return dn


# ── run ───────────────────────────────────────────────────────────────────────


def run():
	real_commit = frappe.db.commit

	def _no_commit(*a, **k):
		raise RuntimeError("verify_fg_delivery_note must not commit")

	frappe.set_user("Administrator")
	frappe.db.commit = _no_commit
	try:
		_run()
	except Exception as e:
		checks.append(False)
		import traceback

		traceback.print_exc()
		print("  FAIL the run raised %s: %s" % (type(e).__name__, e))
	finally:
		frappe.db.rollback()
		frappe.db.commit = real_commit
		frappe.clear_cache(doctype="Item")

	print()
	print("=== after rollback ===")
	check("the test item is gone", bool(frappe.db.exists("Item", FG_ITEM)), False)
	check("no Delivery Note of it is left",
		frappe.db.count("Delivery Note Item", {"item_code": FG_ITEM}), 0)
	print()
	print("=== SUMMARY ===")
	if all(checks):
		print("ALL %d CHECKS PASSED" % len(checks))
	else:
		print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))


def _run():
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return

	from manufyxinvenzaerp.selling_management import delivery_note as dnmod
	from manufyxinvenzaerp.selling_management import sales_invoice as si
	from manufyxinvenzaerp.selling_management.mapping import (
		make_delivery_note,
		make_sales_invoice_from_dn,
	)

	_masters()
	so = _make_so([
		{"item_code": FG_ITEM, "qty": 300, "rate": 100, "custom_sec_qty": 10},
		{"item_code": NON_FG_ITEM, "qty": 4, "rate": 5},
	])
	other_so = _make_so([{"item_code": FG_ITEM, "qty": 50, "rate": 100, "custom_sec_qty": 1}])
	line = so.items[0].name
	b1, b2, b_other = _batch(so, "D1"), _batch(so, "D2"), _batch(other_so, "D1")
	_receive(b1, 4, 122)       # Final Stock Entry 1: 4 Nos weighed 122 Kg
	_receive(b2, 1, 30)        # a second drawing of the same line
	_receive(b_other, 1, 50)   # another order's piece: never offered here
	b_loose = _batch(None, "D9")
	_receive(b_loose, 1, 30)   # a batch made by hand, tied to no order
	print("=== Sales Order %s (line %s), batches %s / %s ===" % (so.name, line, b1, b2))
	check("batch 1 before: 4 Nos, 30.5 per Nos, 4 / 122 in the warehouse", _state(b1), (4.0, 30.5, 4.0, 122.0))

	# ── 1. mapping ──
	print()
	print("=== 1. Sales Order -> Delivery Note ===")
	dn = make_delivery_note(so.name)
	fg = _fg_rows(dn)
	bolt = [r for r in dn.items if r.item_code == NON_FG_ITEM]
	check("one FG row, Nos = pending 10, Sec UOM Nos, no batch (not auto-picked)",
		(len(fg), flt(fg[0].custom_sec_qty), fg[0].custom_sec_uom, fg[0].batch_no or None,
		 fg[0].use_serial_batch_fields), (1, 10.0, "Nos", None, 0))
	check("FG row linked to its Sales Order line", (fg[0].against_sales_order, fg[0].so_detail), (so.name, line))
	check("non-FG row: Sec UOM cleared (Kg stays editable)", (bolt[0].custom_sec_uom or None, flt(bolt[0].custom_sec_qty)), (None, 0.0))
	check("non-FG row: qty untouched", flt(bolt[0].qty), 4.0)
	raises("an FG row without a batch cannot be saved or submitted", lambda: _ins(dn), "Batch No is mandatory")

	# ── 2. Get FG Batches ──
	print()
	print("=== 2. Get FG Batches ===")
	dn = make_delivery_note(so.name)
	found = {b["batch_no"]: b for b in dnmod.get_fg_batches(dn.as_dict())}
	check("lists this order's two batches, not another order's or a loose one", sorted(found), sorted([b1, b2]))
	check("batch 1: 4 Nos / 122 Kg / 30.5 per Nos, proposal 4 Nos = 122 Kg",
		tuple(found[b1][k] for k in ("available_nos", "available_kg", "kg_per_nos", "nos", "kg")),
		(4.0, 122.0, 30.5, 4.0, 122.0))
	check("batch rows point at the Sales Order line and the row they replace",
		(found[b1]["so_detail"], found[b1]["sales_order"], found[b1]["template_row"]),
		(line, so.name, _fg_rows(dn)[0].name))
	check("batch 2: 1 Nos, DUNO D2", (found[b2]["available_nos"], found[b2]["duno"]), (1.0, "D2"))

	probe = _dn_from_so(so, [(b1, 1, 0)])
	res = dnmod.get_fg_rows_kg(probe.as_dict())
	check("form helper: 1 Nos of batch 1 = 30.5 Kg", flt(res[probe.items[0].name]["kg"], 3), 30.5)

	# ── 3. refusals ──
	print()
	print("=== 3. refusals ===")
	raises("5 Nos from a batch holding 4 is refused", lambda: _ins(_dn_from_so(so, [(b1, 5, 1)])), "holds 4")
	raises("a batch of another Sales Order is refused",
		lambda: _ins(_dn_from_so(so, [(b_other, 1, 1)])), "made for Sales Order")
	raises("a batch tied to no Sales Order is refused",
		lambda: _ins(_dn_from_so(so, [(b_loose, 1, 1)])), "not tied to any Sales Order")
	raises("2.5 Nos is refused", lambda: _ins(_dn_from_so(so, [(b1, 2.5, 1)])), "whole number")
	raises("0 Nos is refused", lambda: _ins(_dn_from_so(so, [(b1, 0, 1)])), "whole number")
	raises("two rows of one batch cannot share its last piece",
		lambda: _ins(_dn_from_so(so, [(b1, 3, 1), (b1, 2, 1)])), "holds 1")

	# ── 4. DN 1 ──
	print()
	print("=== 4. DN 1: 3 Nos ===")
	dn1 = _ins(_dn_from_so(so, [(b1, 3, 1)]))
	r = _fg_rows(dn1)[0]
	check("3 Nos -> 91.5 Kg (the typed 1 Kg replaced)", flt(r.qty, 3), 91.5)
	check("row: batch field used, DUNO from the batch", (r.use_serial_batch_fields, r.custom_duno_mark_no), (1, "D1"))
	check("amount priced on the Kg", flt(r.amount, 2), 9150.0)
	dn1.submit()
	check("batch 1: 1 Nos / 30.5 Kg left", _state(b1), (1.0, 30.5, 1.0, 30.5))
	check("Sales Order Delivered (Nos) = 3", _delivered(line), 3.0)
	check("ERPNext delivered Kg = 91.5", flt(frappe.db.get_value("Sales Order Item", line, "delivered_qty"), 3), 91.5)
	nxt = make_delivery_note(so.name)
	check("the next DN proposes the 7 Nos pending", flt(_fg_rows(nxt)[0].custom_sec_qty), 7.0)
	si_probe = make_sales_invoice_from_dn(dn1.name)
	check("DN -> SI (A6) takes DN 1's 3 Nos / 91.5 Kg",
		(flt(si_probe.items[0].custom_sec_qty), flt(si_probe.items[0].qty, 3)), (3.0, 91.5))

	# ── 5. DN 2 ──
	print()
	print("=== 5. Final Stock Entry 2 arrives; DN 2: 7 Nos ===")
	_receive(b1, 6, 181)
	check("batch 1: 7 Nos / 211.5 Kg", _state(b1), (7.0, 30.214, 7.0, 211.5))
	raises("7 Nos of batch 1 + 1 of batch 2 is over the 7 pending (R4)",
		lambda: _ins(_dn_from_so(so, [(b1, 7, 1), (b2, 1, 1)])), "more than is still to deliver")

	dn2 = _ins(_dn_from_so(so, [(b1, 7, 1)]))
	check("7 Nos -> the exact 211.5 Kg left", flt(_fg_rows(dn2)[0].qty, 3), 211.5)
	allowance = flt(frappe.db.get_value("Item", FG_ITEM, "over_delivery_receipt_allowance"))
	raises("ERPNext refuses 303 Kg against 300 ordered at 0% allowance",
		lambda: frappe.get_doc("Delivery Note", dn2.name).submit(), "over limit")
	frappe.db.set_value("Item", FG_ITEM, "over_delivery_receipt_allowance", 5)
	frappe.clear_cache(doctype="Item")
	dn2 = frappe.get_doc("Delivery Note", dn2.name)
	dn2.submit()
	check("batch 1 empty", _state(b1)[0::2], (0.0, 0.0))
	check("Sales Order Delivered (Nos) = 10", _delivered(line), 10.0)
	nxt = make_delivery_note(so.name)
	check("the next DN has no FG row (all 10 Nos delivered)", len(_fg_rows(nxt)), 0)
	raises("1 more Nos from batch 2 is over the 0 pending (R4)",
		lambda: _ins(_dn_from_so_line(so, line, b2, 1)), "more than is still to deliver")

	# ── 6. return ──
	print()
	print("=== 6. return 2 Nos against DN 2 ===")
	dn2_row = _fg_rows(dn2)[0].name
	ret = make_sales_return(dn2.name)
	fitted = dnmod.get_fg_rows_kg(ret.as_dict(), fit_returns=1)[_fg_rows(ret)[0].name]
	check("form: a new return proposes all 7 Nos / 211.5 Kg", (fitted["nos"], fitted["kg"]), (-7.0, -211.5))
	_fg_rows(ret)[0].custom_sec_qty = 2  # typed positive: stored negative
	_ins(ret)
	rr = _fg_rows(ret)[0]
	check("return: -2 Nos / -60.429 Kg", (flt(rr.custom_sec_qty), flt(rr.qty, 3)), (-2.0, -60.429))
	check("return: same batch, linked to the DN 2 row", (rr.batch_no, rr.dn_detail), (b1, dn2_row))
	ret.submit()
	check("batch 1: 2 Nos / 60.429 Kg back", _state(b1), (2.0, flt(60.429 / 2, 3), 2.0, 60.429))
	check("Sales Order Delivered (Nos) = 8", _delivered(line), 8.0)
	nxt = make_delivery_note(so.name)
	check("the next DN proposes the 2 Nos pending again", flt(_fg_rows(nxt)[0].custom_sec_qty), 2.0)
	check("A6 sees 5 Nos / 151.071 Kg still out on the DN 2 row",
		(flt(si._source_row("Delivery Note Item", dn2_row).total_nos),
		 flt(si._source_row("Delivery Note Item", dn2_row).total_kg, 3)), (5.0, 151.071))

	ret2 = make_sales_return(dn2.name)
	fitted = dnmod.get_fg_rows_kg(ret2.as_dict(), fit_returns=1)[_fg_rows(ret2)[0].name]
	check("form: the next return is cut to the 5 still out, exact 151.071 Kg", (fitted["nos"], fitted["kg"]), (-5.0, -151.071))
	_fg_rows(ret2)[0].custom_sec_qty = -6
	raises("returning 6 Nos when 5 are out is refused", lambda: _ins(ret2), "cannot come back")
	ret2 = make_sales_return(dn2.name)
	_fg_rows(ret2)[0].custom_sec_qty = -1
	_fg_rows(ret2)[0].batch_no = b2
	raises("returning into another batch is refused", lambda: _ins(ret2), "go back into the batch")
	ret2 = make_sales_return(dn2.name)
	_fg_rows(ret2)[0].custom_sec_qty = -5
	_ins(ret2)
	check("the last 5 Nos would take the exact 151.071 Kg (draft only)", flt(_fg_rows(ret2)[0].qty, 3), -151.071)
	nob = frappe.get_doc({
		"doctype": "Delivery Note", "company": COMPANY, "customer": so.customer, "is_return": 1,
		"items": [{"item_code": FG_ITEM, "qty": -30, "rate": 100, "warehouse": WAREHOUSE,
		           "batch_no": b1, "custom_sec_qty": -1, "against_sales_order": so.name, "so_detail": line}],
	})
	raises("a return not made from its Delivery Note is refused", lambda: _ins(nob), "must be made from its Delivery Note")

	# ── 7. cancels ──
	print()
	print("=== 7. cancelling in reverse ===")
	ret.reload()
	ret.cancel()
	check("return cancelled: batch empty, Delivered 10", (_state(b1)[0::2], _delivered(line)), ((0.0, 0.0), 10.0))
	dn2.reload()
	dn2.cancel()
	check("DN 2 cancelled: batch 7 / 211.5, Delivered 3", (_state(b1), _delivered(line)), ((7.0, 30.214, 7.0, 211.5), 3.0))
	dn1.reload()
	dn1.cancel()
	check("DN 1 cancelled: batch 10 / 303, Delivered 0", (_state(b1), _delivered(line)), ((10.0, 30.3, 10.0, 303.0), 0.0))
	# Kept at 5% until here: cancelling the return puts ERPNext's delivered Kg back
	# to 303 against 300 ordered, which it checks against the allowance again.
	frappe.db.set_value("Item", FG_ITEM, "over_delivery_receipt_allowance", allowance)
	frappe.clear_cache(doctype="Item")
	check("item allowance put back", flt(frappe.db.get_value("Item", FG_ITEM, "over_delivery_receipt_allowance")), allowance)

	_heavier_pieces(make_delivery_note, dnmod, allowance)


def _heavier_pieces(make_delivery_note, dnmod, allowance):
	"""Pieces heavier than ordered: the Kg runs out before the Nos do.

	300 Kg / 10 Nos ordered; the batch holds 10 Nos weighing 340 Kg. 9 Nos = 306 Kg
	already exceed the 300 Kg ordered, so ERPNext no longer maps the line -- the
	override must still offer its last piece, and only ERPNext's over-delivery
	allowance may limit the Kg (D10)."""
	print()
	print("=== 8. heavier pieces: Kg delivered in full, 1 Nos still pending ===")
	so = _make_so([
		{"item_code": FG_ITEM, "qty": 300, "rate": 100, "custom_sec_qty": 10},
		{"item_code": NON_FG_ITEM, "qty": 4, "rate": 5},
	])
	line, bolt_line = so.items[0].name, so.items[1].name
	b = _batch(so, "H1")
	_receive(b, 10, 340)
	frappe.db.set_value("Item", FG_ITEM, "over_delivery_receipt_allowance", 20)
	frappe.clear_cache(doctype="Item")
	dn1 = _ins(_dn_from_so(so, [(b, 9, 1)]))
	check("9 Nos -> 306 Kg", flt(_fg_rows(dn1)[0].qty, 3), 306.0)
	dn1.submit()
	check("ERPNext: the line's Kg is delivered in full (306 of 300)",
		flt(frappe.db.get_value("Sales Order Item", line, "delivered_qty"), 3), 306.0)
	check("Delivered (Nos) = 9", _delivered(line), 9.0)

	nxt = make_delivery_note(so.name)
	fg = _fg_rows(nxt)
	check("the next DN still has the FG line, with its 1 pending Nos",
		[(r.so_detail, flt(r.custom_sec_qty), r.custom_sec_uom) for r in fg], [(line, 1.0, "Nos")])
	check("... unbatched (batch fields off), placeholder Kg = 1 x 30 ordered",
		(fg[0].batch_no or None, fg[0].use_serial_batch_fields, flt(fg[0].qty, 3)), (None, 0, 30.0))
	check("... in Sales Order line order, next to ERPNext's non-FG row",
		[r.so_detail for r in nxt.items], [line, bolt_line])
	check("... with ERPNext's row details filled (cost center, expense account, rate, warehouse)",
		(bool(fg[0].cost_center), bool(fg[0].expense_account), flt(fg[0].rate), fg[0].warehouse),
		(True, True, 100.0, WAREHOUSE))
	only_bolt = make_delivery_note(so.name, kwargs={"filtered_children": [bolt_line]})
	check("rows picked in the select dialog still filter it out",
		[r.so_detail for r in only_bolt.items], [bolt_line])
	offered = {x["batch_no"]: x for x in dnmod.get_fg_batches(nxt.as_dict())}
	check("Get FG Batches works from that row: 1 Nos / 34 Kg proposed",
		(offered[b]["nos"], offered[b]["kg"], offered[b]["so_detail"]), (1.0, 34.0, line))

	raises("2 Nos on the line with 1 pending is refused (R4)",
		lambda: _ins(_dn_from_so(so, [(b, 2, 1)])), "more than is still to deliver")
	dn2 = _ins(_dn_from_so(so, [(b, 1, 1)]))
	check("the last Nos takes the batch's exact 34 Kg", flt(_fg_rows(dn2)[0].qty, 3), 34.0)
	frappe.db.set_value("Item", FG_ITEM, "over_delivery_receipt_allowance", 0)
	frappe.clear_cache(doctype="Item")
	raises("at 0% allowance ERPNext refuses the extra Kg (its check is the only Kg limit)",
		lambda: frappe.get_doc("Delivery Note", dn2.name).submit(), "over limit")
	frappe.db.set_value("Item", FG_ITEM, "over_delivery_receipt_allowance", 20)
	frappe.clear_cache(doctype="Item")
	dn2 = frappe.get_doc("Delivery Note", dn2.name)
	dn2.submit()
	check("at 20% it goes: Delivered (Nos) = 10, ERPNext Kg = 340",
		(_delivered(line), flt(frappe.db.get_value("Sales Order Item", line, "delivered_qty"), 3)), (10.0, 340.0))
	check("batch empty", _state(b)[0::2], (0.0, 0.0))
	check("now nothing FG is left to map", len(_fg_rows(make_delivery_note(so.name))), 0)
	dn2.reload()
	dn2.cancel()
	check("cancel DN 2: Delivered (Nos) = 9, the batch holds 1 Nos / 34 Kg",
		(_delivered(line), _state(b)[2:]), (9.0, (1.0, 34.0)))
	dn1.reload()
	dn1.cancel()
	frappe.db.set_value("Item", FG_ITEM, "over_delivery_receipt_allowance", allowance)
	frappe.clear_cache(doctype="Item")
	check("cancel DN 1: Delivered (Nos) = 0; allowance put back",
		(_delivered(line), flt(frappe.db.get_value("Item", FG_ITEM, "over_delivery_receipt_allowance"))),
		(0.0, allowance))


def _dn_from_so_line(so, line, batch, nos):
	"""A Delivery Note row made by hand against a Sales Order line (no mapper)."""
	return frappe.get_doc({
		"doctype": "Delivery Note", "company": COMPANY, "customer": so.customer,
		"items": [{
			"item_code": FG_ITEM, "qty": 1, "rate": 100, "uom": "Kg", "conversion_factor": 1,
			"warehouse": WAREHOUSE, "batch_no": batch, "use_serial_batch_fields": 1,
			"custom_sec_qty": nos, "against_sales_order": so.name, "so_detail": line,
		}],
	})
