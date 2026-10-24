"""The client's change list of 22 Oct 2026, checked against a copy of live data.

  1. Item Validate Storage Location: off -> every location of the warehouse is offered;
     on -> only the Item's own Storage Locations.
  2. Job Work Order numbered JWO-YYYY-#####, and each Supplier/Contractor's operations
     carry their own Allocation No. (-1, -2 ... only when the job is split).
  3. Operation Entry Weighment Weight against the Drawing Weight; Delivery Note and
     Packing Slip row Weighment Weight summed into the header total.
  4. Operation Start / End Date and No. of Days, shown in the Production Report.
  5. MRS No. mandatory on the Material Issue Plan transfers to the supplier.
  6. Warehouse -> Mandatory Storage Location (23 Oct): on, and the warehouse has locations,
     a movement in or out must name one; off, or no locations, it need not.

Everything that writes runs inside one transaction that is rolled back at the end.

Run: bench --site manufactv16 execute manufyxinvenzaerp.tests.verify_client_changes_oct22.run
"""

import inspect
from collections import defaultdict

import frappe
from frappe.utils import add_days, getdate, today

checks = []


def check(label, got, want):
	ok = got == want
	checks.append(ok)
	print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, needle=None):
	frappe.db.savepoint("mfx_throw")
	try:
		fn()
	except frappe.ValidationError as e:
		frappe.db.rollback(save_point="mfx_throw")
		frappe.clear_last_message()
		return needle in str(e) if needle else True
	return False


def _fresh():
	"""Forget what this request has already looked up: the tests flip settings mid-request."""
	frappe.local.request_cache = defaultdict(dict)


def run():
	real_commit = frappe.db.commit
	frappe.db.commit = lambda *a, **k: None
	try:
		_storage_location()
		_allocation_numbers()
		_operation_entry()
		_delivery_weighment()
		_production_report()
		_mrs_number()
		_warehouse_mandatory()
	finally:
		frappe.db.rollback()
		frappe.db.commit = real_commit
	print("\n%d/%d checks passed" % (sum(checks), len(checks)))


def _storage_location():
	print("\n1. Validate Storage Location")
	from manufyxinvenzaerp.stock_management import storage_location as sl

	warehouse = frappe.db.sql(
		"""SELECT warehouse FROM `tabStorage Location` GROUP BY warehouse HAVING COUNT(*) > 1 LIMIT 1""")
	if not warehouse:
		print("  SKIP no warehouse with two Storage Locations")
		return
	warehouse = warehouse[0][0]
	locations = sorted(frappe.get_all("Storage Location", {"warehouse": warehouse}, pluck="name"))
	item = frappe.get_all("Item", {"is_stock_item": 1, "disabled": 0, "has_variants": 0}, pluck="name", limit=1)[0]

	doc = frappe.get_doc("Item", item)
	check("new field defaults off", frappe.get_meta("Item").get_field("custom_validate_storage_location").default, "0")
	check("no item has it on after migrate", frappe.db.count("Item", {"custom_validate_storage_location": 1}), 0)
	doc.set("custom_storage_locations", [{"warehouse": warehouse, "storage_location": locations[0], "is_default": 1}])
	doc.custom_validate_storage_location = 0
	doc.save()
	_fresh()
	check("off: every location of the warehouse offered", sorted(sl.allowed_locations(item, warehouse)), locations)
	rows = sl.inward_location_query("Storage Location", "", "name", 0, 50, {"item_code": item, "warehouse": warehouse})
	check("off: the picker lists them all", sorted(r[0] for r in rows), locations)
	check("off: the item's default is still filled in", sl.default_location(item, warehouse), locations[0])

	doc.reload()
	doc.custom_validate_storage_location = 1
	doc.save()
	_fresh()
	check("on: only the item's own locations", sl.allowed_locations(item, warehouse), [locations[0]])


def _allocation_numbers():
	print("\n2. Job Work Order numbering")
	from frappe.model.naming import NamingSeries

	from manufyxinvenzaerp.subcontracting_management.subcontracting import set_jwo_allocation_numbers

	field = frappe.get_meta("Subcontracting Order").get_field("naming_series")
	check("naming series", (field.options, field.default), ("JWO-.YYYY.-", "JWO-.YYYY.-"))
	check("next number looks like JWO-2026-00001",
	      NamingSeries("JWO-.YYYY.-").get_preview()[0].startswith("JWO-%s-" % getdate().year), True)

	# Find a job with two parties and one with one.
	soes = frappe.get_all("Supplier Operation Entry", {"docstatus": ["!=", 2]},
	                      ["name", "subcontracting_order", "sequence_id", "supplier", "contractor"],
	                      order_by="subcontracting_order, sequence_id")
	by_sco = {}
	for s in soes:
		by_sco.setdefault(s.subcontracting_order, []).append(s)
	split = next((k for k, v in by_sco.items() if len({r.supplier or r.contractor for r in v}) > 1), None)
	single = next((k for k, v in by_sco.items() if len({r.supplier or r.contractor for r in v}) == 1), None)

	if single:
		set_jwo_allocation_numbers(single)
		got = {frappe.db.get_value("Supplier Operation Entry", s.name, "jwo_allocation_no") for s in by_sco[single]}
		check("one party: plain order number", got, {single})
	if not split:
		print("  SKIP no job split between parties")
		return
	ops = by_sco[split]
	set_jwo_allocation_numbers(split)
	parties = []
	for s in ops:
		if (s.supplier or s.contractor) not in parties:
			parties.append(s.supplier or s.contractor)
	want = ["%s-%s" % (split, parties.index(s.supplier or s.contractor) + 1) for s in ops]
	got = [frappe.db.get_value("Supplier Operation Entry", s.name, "jwo_allocation_no") for s in ops]
	check("split job: -1, -2 by party in routing order", got, want)

	# A, B, A: the last operation goes back to the first party -- still two numbers.
	first, last = ops[0], ops[-1]
	frappe.db.set_value("Supplier Operation Entry", last.name,
	                    {"supplier": first.supplier, "contractor": first.contractor})
	set_jwo_allocation_numbers(split)
	check("A, B, A is two numbers, the last back on -1",
	      frappe.db.get_value("Supplier Operation Entry", last.name, "jwo_allocation_no"), "%s-1" % split)

	summary = frappe.call("manufyxinvenzaerp.subcontracting_management.subcontracting.get_soe_summary",
	                      sco_name=split)
	check("operations table gets the number", all(r.get("jwo_allocation_no") for r in summary), True)
	from manufyxinvenzaerp.setup import SCO_OPS_SCRIPT

	check("print headed by the Allocation No.", '["Allocation No.", (ops[0] && ops[0].jwo_allocation_no)' in SCO_OPS_SCRIPT, True)
	check("print shows both Rate Schedules and rates",
	      all(x in SCO_OPS_SCRIPT for x in ("Fabrication Rate Schedule No.", "Painting Rate Schedule No.",
	                                        "rs_rate_per_kg", "prs_rate_per_kg")), True)


def _operation_entry():
	print("\n3/4. Operation Entry dates and weighment")
	from manufyxinvenzaerp.subcontracting_management import subcontracting as sc

	d = frappe._dict(status="In Progress", consumption_log=[frappe._dict(date="2026-10-05"),
	                                                         frappe._dict(date="2026-10-03")],
	                 drawing_details=[frappe._dict(customer_provided_weight_kg=100.5),
	                                  frappe._dict(customer_provided_weight_kg=50)],
	                 weighment_weight_kg=148)
	sc._stamp_operation_dates(d)
	check("start = first logged date", str(d.operation_start_date), "2026-10-03")
	check("no end while in progress", d.get("operation_end_date"), None)
	d.status = "Completed"
	sc._stamp_operation_dates(d)
	check("end = the day it is completed", d.operation_end_date, getdate(today()))
	d.operation_end_date = "2026-10-07"
	sc.set_cycle_time_and_weighment(d)
	check("No. of Days counts both ends (3rd to 7th)", d.no_of_days, 5)
	check("drawing weight = the drawings' customer weight", d.drawing_weight_kg, 150.5)
	check("difference = weighment less drawing", d.weight_difference_kg, -2.5)
	d.operation_start_date = "2026-10-01"
	sc._stamp_operation_dates(d)
	check("a start date once set does not move", d.operation_start_date, "2026-10-01")
	d.operation_end_date = "2026-09-30"
	check("end before start refused", _throws(lambda: sc.set_cycle_time_and_weighment(d), "before the Start Date"), True)
	d2 = frappe._dict(status="Open", drawing_details=[], weighment_weight_kg=0)
	sc._stamp_operation_dates(d2)
	sc.set_cycle_time_and_weighment(d2)
	check("open operation: no dates, no difference",
	      (d2.get("operation_start_date"), d2.no_of_days, d2.weight_difference_kg), (None, 0, 0))

	submitted = frappe.get_all("Supplier Operation Entry", {"docstatus": 1}, pluck="name", limit=1)
	if submitted:
		soe = frappe.get_doc("Supplier Operation Entry", submitted[0])
		soe.operation_start_date = add_days(today(), -3)
		soe.operation_end_date = today()
		soe.weighment_weight_kg = 1000
		soe.save()
		check("submitted operation: No. of Days worked out on update", soe.no_of_days, 4)
		check("submitted operation: difference worked out",
		      soe.weight_difference_kg, round(1000 - soe.drawing_weight_kg, 3))


def _delivery_weighment():
	print("\n3. Delivery Note / Packing Slip weighment")
	from manufyxinvenzaerp.selling_management.weighment import set_total_weighment_weight

	d = frappe._dict(items=[frappe._dict(custom_weighment_weight=10.25), frappe._dict(custom_weighment_weight=5)],
	                 custom_total_weighment_weight=99)
	set_total_weighment_weight(d)
	check("rows filled: total is their sum", d.custom_total_weighment_weight, 15.25)
	d = frappe._dict(items=[frappe._dict(custom_weighment_weight=0)], custom_total_weighment_weight=42)
	set_total_weighment_weight(d)
	check("no row filled: typed total kept", d.custom_total_weighment_weight, 42)
	for dt in ("Delivery Note", "Packing Slip"):
		check("%s has the total field" % dt, bool(frappe.get_meta(dt).get_field("custom_total_weighment_weight")), True)
		check("%s Item has the row field" % dt,
		      bool(frappe.get_meta(dt + " Item").get_field("custom_weighment_weight")), True)
	hooks = frappe.get_hooks("doc_events")["Delivery Note"]["validate"]
	check("Delivery Note validate sums it",
	      "manufyxinvenzaerp.selling_management.weighment.set_total_weighment_weight" in hooks, True)
	from manufyxinvenzaerp.selling_management.packing_slip import PackingSlip

	check("Packing Slip validate sums it", "set_total_weighment_weight" in inspect.getsource(PackingSlip.validate), True)


def _production_report():
	print("\n4. Production Report cycle time")
	from manufyxinvenzaerp.production_management.report.production_report import production_report as pr

	soe = frappe.get_all("Supplier Operation Entry", {"docstatus": ["!=", 2]},
	                     ["name", "operation", "subcontracting_order"], limit=1)
	if not soe:
		print("  SKIP no operation entries")
		return
	soe = soe[0]
	frappe.db.set_value("Supplier Operation Entry", soe.name,
	                    {"operation_start_date": "2026-10-01", "operation_end_date": "2026-10-04", "no_of_days": 4})
	columns, data = pr.execute({"subcontracting_order": soe.subcontracting_order})
	labels = {c["label"] for c in columns}
	check("Start / End / No. of Days columns", all("%s %s" % (soe.operation, x) in labels
	                                               for x in ("Start Date", "End Date", "No. of Days")), True)
	check("old approximate gap column gone", any("Gap (Days" in l for l in labels), False)
	slug = frappe.scrub(soe.operation)
	row = next((r for r in data if not r.get("is_total_row")), {})
	check("row carries the operation's dates",
	      (str(row.get("op_%s_start" % slug)), str(row.get("op_%s_end" % slug)), row.get("op_%s_days" % slug)),
	      ("2026-10-01", "2026-10-04", 4))


def _mrs_number():
	print("\n5. MRS No. mandatory")
	from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as t

	check("blank MRS No. refused", _throws(lambda: t._require_mrs_number(" "), "MRS No."), True)
	check("typed MRS No. passes", _throws(lambda: t._require_mrs_number("MRS-1")), False)
	src = inspect.getsource(t.create_mip_partial_transfer)
	check("transfer to the supplier checks it, the CNC leg does not",
	      'if transfer_type != "cnc":\n        _require_mrs_number(mrs_number)' in src, True)
	check("CNC -> supplier checks it", "_require_mrs_number(mrs_number)" in inspect.getsource(t.create_mip_cnc_partial_forward), True)


def _warehouse_mandatory():
	print("\n6. Warehouse Mandatory Storage Location")
	from manufyxinvenzaerp.stock_management import storage_location as sl

	check("Warehouse Type flag hidden",
	      frappe.get_meta("Warehouse Type").get_field("custom_storage_location_applicable").hidden, 1)
	typed = frappe.get_all("Warehouse Type", {"custom_storage_location_applicable": 1}, pluck="name")
	carried = frappe.get_all("Warehouse", {"warehouse_type": ["in", typed or [""]]}, pluck="name")
	check("patch ticked every warehouse whose type had the flag",
	      all(frappe.db.get_value("Warehouse", w, "custom_mandatory_storage_location") for w in carried), True)

	wh = frappe.db.sql("""SELECT warehouse FROM `tabStorage Location` GROUP BY warehouse LIMIT 1""")[0][0]
	company = frappe.db.get_value("Warehouse", wh, "company")
	item = frappe.get_all("Item", {"is_stock_item": 1, "disabled": 0, "has_variants": 0,
	                               "has_batch_no": 0}, pluck="name", limit=1)
	item = item[0] if item else frappe.get_all("Item", {"is_stock_item": 1, "disabled": 0}, pluck="name", limit=1)[0]

	def receipt(warehouse, location=None):
		return frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": company,
		                       "items": [{"item_code": item, "qty": 1, "t_warehouse": warehouse,
		                                  "to_storage_location": location}]})

	for value, want in ((1, True), (0, False)):
		frappe.db.set_value("Warehouse", wh, "custom_mandatory_storage_location", value)
		_fresh()
		check("box %s, warehouse has locations -> mandatory %s" % (value, want), sl.location_applicable(wh), want)
		check("  a receipt with no location %s" % ("refused" if want else "passes"),
		      _throws(lambda: sl.validate_locations(receipt(wh)), "mandatory"), want)
	frappe.db.set_value("Warehouse", wh, "custom_mandatory_storage_location", 1)
	_fresh()
	location = frappe.get_all("Storage Location", {"warehouse": wh}, pluck="name", limit=1)[0]
	check("  a receipt naming one of its locations passes",
	      _throws(lambda: sl.validate_locations(receipt(wh, location)), "mandatory"), False)

	bare = frappe.db.sql("""SELECT name FROM `tabWarehouse` w WHERE is_group = 0 AND NOT EXISTS
	                        (SELECT 1 FROM `tabStorage Location` l WHERE l.warehouse = w.name) LIMIT 1""")
	if bare:
		frappe.db.set_value("Warehouse", bare[0][0], "custom_mandatory_storage_location", 1)
		_fresh()
		check("box on but no locations -> not mandatory", sl.location_applicable(bare[0][0]), False)
		check("  get_location_settings tells the form the same",
		      sl.get_location_settings([bare[0][0], wh]), {bare[0][0]: False, wh: True})
