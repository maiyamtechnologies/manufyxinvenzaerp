"""Clear every transaction off a test site, keeping the opening stock receipt.

Written for the rebuild loop: wipe the site back to masters plus one Material Receipt,
then walk Sales Order -> Drawing -> BOM -> Material Planning -> Production Plan -> Job
Work Order -> transfer -> operations again from a known starting point.

What survives: all masters (Items, Customers, Suppliers, Warehouses, Rate Schedules,
Operations, Routing, Manufyxinvenza Settings), the one Stock Entry named in KEEP_STOCK
_ENTRY, and everything that entry owns -- its ledger, its batches, its bundles.

What goes: every other transaction, in dependency order; every batch left holding no
stock once they are gone; every ledger and bundle row orphaned by the deletions; and the
_Test companies ERPNext's own fixtures leave behind, which is what makes a test pick the
wrong company and fail with "Warehouse X does not belong to company _Test ...".

NOT reversible. Take a backup first:

    bench --site <site> backup

Dry run (counts only, changes nothing):

    bench --site <site> execute manufyxinvenzaerp.tests.reset_transactions.run

For real -- the confirm string is the site name, so a copy-pasted command cannot fire on
the wrong site:

    bench --site <site> execute manufyxinvenzaerp.tests.reset_transactions.run \\
        --kwargs "{'confirm': '<site>'}"
"""

import frappe
from frappe.utils import flt

KEEP_STOCK_ENTRY = "MAT-STE-00001"

# Dependents before the things they depend on: a document whose children are already
# gone deletes quietly, and Frappe's link checks stop objecting.
DELETE_ORDER = [
	"Manufyx Decision Log",
	"Inspection Entry",
	"Supplier Operation Entry",
	"Job Card",
	"Work Order",
	"Material Issue Plan",
	"Subcontracting Order",
	"Cut Sheet",
	"Production Plan",
	"Material Planning",
	"Sales Invoice",
	"Delivery Note",
	"Purchase Invoice",
	"Payment Entry",
	"Journal Entry",
	"Purchase Receipt",
	"Purchase Order",
	"Supplier Quotation",
	"Request for Quotation",
	"Material Request",
	"Stock Entry",
	"BOM",
	"Drawing",
	"Sales Order",
]

TEST_COMPANY_PREFIX = "_Test"


def run(confirm=None):
	site = frappe.local.site
	dry = confirm != site
	if dry:
		print("DRY RUN -- nothing will be deleted.")
		print("To go ahead:  bench --site %s execute "
			  "manufyxinvenzaerp.tests.reset_transactions.run --kwargs \"{'confirm': '%s'}\"\n"
			  % (site, site))
	else:
		print("DELETING on site %s. Not reversible.\n" % site)

	if not frappe.db.exists("Stock Entry", KEEP_STOCK_ENTRY):
		frappe.throw("The entry to keep, %s, is not on this site. Refusing to run."
					 % KEEP_STOCK_ENTRY)

	keep = _things_to_keep()
	print("Keeping %s: %d ledger entries, %d bundles, %d batches.\n" % (
		KEEP_STOCK_ENTRY, len(keep["sles"]), len(keep["bundles"]), len(keep["batches"])))

	total = 0
	for doctype in DELETE_ORDER:
		if not frappe.db.exists("DocType", doctype):
			continue
		names = frappe.get_all(doctype, pluck="name")
		if doctype == "Stock Entry":
			names = [n for n in names if n != KEEP_STOCK_ENTRY]
		if not names:
			continue
		total += len(names)
		print("  %-26s %4d" % (doctype, len(names)))
		if not dry:
			_delete_all(doctype, names)

	print("\n  %-26s %4d documents\n" % ("TOTAL", total))

	if not dry:
		_delete_orphans(keep)
		_delete_empty_batches(keep)
		_rebuild_bins()
		_delete_test_companies()
		# The companies are only part of the set -- see _delete_test_fixtures for why
		# removing them alone leaves `bench run-tests` unable to rebuild.
		_delete_test_fixtures()
		frappe.db.commit()
		print("\nDone. Masters and %s are all that is left." % KEEP_STOCK_ENTRY)
	else:
		_report_orphans(keep)
		companies = _test_companies()
		print("  %-26s %4d  %s" % ("_Test companies", len(companies), companies))
		print("  %-26s %4d" % ("test fixtures", len(_test_fixtures())))


def _things_to_keep():
	"""Everything the surviving Stock Entry owns, so the wipe does not take its stock
	with it. Batches are reached through the bundles as well as through batch_no: a
	batched receipt writes its batch into a Serial and Batch Bundle and leaves the row's
	own batch_no empty."""
	se = frappe.get_doc("Stock Entry", KEEP_STOCK_ENTRY)
	bundles, batches = set(), set()
	for row in se.items:
		if row.batch_no:
			batches.add(row.batch_no)
		if row.serial_and_batch_bundle:
			bundles.add(row.serial_and_batch_bundle)
	for b in frappe.get_all("Stock Ledger Entry",
							filters={"voucher_no": KEEP_STOCK_ENTRY, "is_cancelled": 0},
							fields=["serial_and_batch_bundle", "batch_no"]):
		if b.serial_and_batch_bundle:
			bundles.add(b.serial_and_batch_bundle)
		if b.batch_no:
			batches.add(b.batch_no)
	if bundles:
		for e in frappe.get_all("Serial and Batch Entry",
								filters={"parent": ["in", list(bundles)]}, pluck="batch_no"):
			if e:
				batches.add(e)
	sles = frappe.get_all("Stock Ledger Entry", filters={"voucher_no": KEEP_STOCK_ENTRY},
						  pluck="name")
	return {"sles": set(sles), "bundles": bundles, "batches": batches}


def _delete_all(doctype, names):
	"""Delete, and if a controller objects, take the row out from under it.

	The fallback is not a shortcut past a real check -- it is the point of a reset. A
	cut sheet refuses deletion while its plan exists, a drawing releases its Sales Order
	row on the way out; on a site being wiped wholesale those guards are protecting
	documents that are themselves about to go."""
	failed = 0
	for name in names:
		# A savepoint, not a plain rollback. A failed delete_doc can leave half its
		# child rows gone, so the attempt has to be undone before the direct delete --
		# but rolling the whole transaction back undoes every document deleted before
		# it too, which silently turns a wipe of 669 documents into a wipe of two.
		frappe.db.savepoint("mfx_reset")
		try:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True,
							  ignore_on_trash=True, delete_permanently=True)
		except Exception:
			frappe.db.rollback(save_point="mfx_reset")
			_sql_delete(doctype, name)
			failed += 1
	if failed:
		print("      (%d needed a direct delete)" % failed)


def _sql_delete(doctype, name):
	for child in frappe.get_all("DocField", filters={"parent": doctype,
													 "fieldtype": ["in", ["Table", "Table MultiSelect"]]},
								pluck="options"):
		if child and frappe.db.exists("DocType", child):
			frappe.db.delete(child, {"parent": name, "parenttype": doctype})
	frappe.db.delete(doctype, {"name": name})


def _orphans(keep):
	"""Ledger rows, bundles and postings whose voucher no longer exists."""
	out = {}
	for doctype in ("Stock Ledger Entry", "GL Entry", "Serial and Batch Bundle"):
		gone = []
		for r in frappe.get_all(doctype, fields=["name", "voucher_type", "voucher_no"]):
			if r.name in keep["sles"] or r.name in keep["bundles"]:
				continue
			if not r.voucher_no or not r.voucher_type:
				gone.append(r.name)
			elif not frappe.db.exists(r.voucher_type, r.voucher_no):
				gone.append(r.name)
		out[doctype] = gone
	return out


def _report_orphans(keep):
	for doctype, gone in _orphans(keep).items():
		print("  %-26s %4d  (orphaned)" % (doctype, len(gone)))


def _delete_orphans(keep):
	for doctype, gone in _orphans(keep).items():
		print("  %-26s %4d orphans removed" % (doctype, len(gone)))
		for name in gone:
			if doctype == "Serial and Batch Bundle":
				frappe.db.delete("Serial and Batch Entry", {"parent": name})
			frappe.db.delete(doctype, {"name": name})


def _batch_quantities():
	"""What each batch actually holds, counting both ways stock is recorded: the ledger's
	own batch_no, and the Serial and Batch Entry rows a bundled voucher writes instead."""
	qty = {}
	for r in frappe.db.sql("""SELECT batch_no, SUM(actual_qty) q FROM `tabStock Ledger Entry`
							  WHERE is_cancelled = 0 AND IFNULL(batch_no, '') != ''
							  GROUP BY batch_no""", as_dict=True):
		qty[r.batch_no] = qty.get(r.batch_no, 0) + flt(r.q)
	for r in frappe.db.sql("""SELECT sbe.batch_no, SUM(sbe.qty) q
							  FROM `tabSerial and Batch Entry` sbe
							  JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
							  WHERE sbb.docstatus = 1 AND IFNULL(sbe.batch_no, '') != ''
							  GROUP BY sbe.batch_no""", as_dict=True):
		qty[r.batch_no] = qty.get(r.batch_no, 0) + flt(r.q)
	return qty


def _delete_empty_batches(keep):
	qty = _batch_quantities()
	empty = [b for b in frappe.get_all("Batch", pluck="name")
			 if flt(qty.get(b)) <= 0 and b not in keep["batches"]]
	print("  %-26s %4d removed (held no stock)" % ("Batch", len(empty)))
	for name in empty:
		frappe.db.delete("Serial and Batch Entry", {"batch_no": name})
		frappe.db.delete("Batch", {"name": name})


def _rebuild_bins():
	"""Bins are a cache of the ledger. With most of the ledger gone they have to be told,
	or every item reads a quantity nothing backs."""
	rows = frappe.db.sql("""SELECT item_code, warehouse, SUM(actual_qty) q
							FROM `tabStock Ledger Entry` WHERE is_cancelled = 0
							GROUP BY item_code, warehouse""", as_dict=True)
	live = {(r.item_code, r.warehouse): flt(r.q) for r in rows}
	fixed = removed = 0
	for b in frappe.get_all("Bin", fields=["name", "item_code", "warehouse", "actual_qty"]):
		want = live.get((b.item_code, b.warehouse), 0.0)
		if not want:
			frappe.db.delete("Bin", {"name": b.name})
			removed += 1
		elif flt(b.actual_qty, 6) != flt(want, 6):
			frappe.db.set_value("Bin", b.name, {
				"actual_qty": want, "projected_qty": want, "reserved_qty": 0,
				"indented_qty": 0, "ordered_qty": 0, "planned_qty": 0,
			}, update_modified=False)
			fixed += 1
	print("  %-26s %4d corrected, %d removed" % ("Bin", fixed, removed))


def _test_fixtures():
	"""Every india_compliance test record still on the site, named from its own
	test_records.json rather than guessed by pattern."""
	try:
		recs = frappe.get_file_json(
			frappe.get_app_path("india_compliance", "tests", "test_records.json"))
	except Exception:
		return []
	out = []
	for doctype, rows in recs.items():
		for r in rows:
			name = (r.get("name") or r.get("%s_name" % frappe.scrub(doctype))
					or r.get("company_name"))
			if name and frappe.db.exists(doctype, name):
				out.append((doctype, name))
	return out


def _delete_test_fixtures():
	"""Clear the WHOLE india_compliance fixture set, not just its companies.

	frappe's make_test_objects calls frappe.db.rollback() the moment it meets a fixture
	that already exists, which throws away the companies it created earlier in the same
	run. So a half-present set can never rebuild: `bench run-tests` fails on every
	attempt with "Could not find Warehouse: Stores - _TIRC" and rolls back again.
	Present in full, or absent in full, both work -- it is the mixture that does not, and
	deleting the companies alone is what creates it.

	Addresses first: they link to the customers and suppliers."""
	order = {"Address": 0, "POS Profile": 1, "Customer": 2, "Supplier": 3, "Item": 4, "Company": 5}
	rows = sorted(_test_fixtures(), key=lambda x: order.get(x[0], 9))
	for doctype, name in rows:
		try:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True,
							  delete_permanently=True, ignore_missing=True)
		except Exception as e:
			print("  %-26s %s kept -- %s" % (doctype, name, str(e)[:70]))
	if rows:
		print("  %-26s %4d removed" % ("test fixtures", len(rows)))


def _test_companies():
	return [c for c in frappe.get_all("Company", pluck="name")
			if c.startswith(TEST_COMPANY_PREFIX)]


def _delete_test_companies():
	for name in _test_companies():
		try:
			frappe.delete_doc("Company", name, force=True, ignore_permissions=True,
							  ignore_on_trash=False, delete_permanently=True)
			print("  %-26s %s removed" % ("Company", name))
		except Exception as e:
			print("  %-26s %s kept -- %s: %s" % ("Company", name, type(e).__name__,
												 str(e)[:120]))
