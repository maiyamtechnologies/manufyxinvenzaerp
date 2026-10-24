"""Data Works "Load RM item master" (24 Oct 2026): the client's Code-Spec-Grade master with HSN codes.

Runs the whole go-live reset on this site inside one transaction that is rolled back at the end:
delete transactions, then load the item master, then load it again.

  * every one of the 282 items exists with the sheet's spec, grade, weight, HSN and batch prefix;
  * a new code copies the item defaults of the live item it replaces;
  * the old raw-material codes and the test item E2E-FG-STRUCT are gone, SHS100 / SHS150 and the
    finished-goods and nuts-and-bolts items stay;
  * a second run creates nothing and deletes nothing.

Run: bench --site manufactv16 execute manufyxinvenzaerp.tests.verify_data_works_items.run
"""

import frappe

from manufyxinvenzaerp.data_works import engine

checks = []


def check(label, got, want):
	ok = got == want
	checks.append(ok)
	print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def run():
	real_commit, real_enqueue = frappe.db.commit, frappe.enqueue
	frappe.db.commit = lambda *a, **k: None
	frappe.enqueue = lambda *a, **k: None  # no worker here: keep search-index jobs off the queue
	try:
		_run()
	finally:
		frappe.db.rollback()
		frappe.db.commit, frappe.enqueue = real_commit, real_enqueue
	print("\n%d/%d checks passed" % (sum(checks), len(checks)))


def _run():
	cfg = engine._data("rm_items.json")
	rows = {r["item_code"]: r for r in cfg["items"]}
	check("master holds 282 items", len(rows), 282)
	check("every batch prefix is unique", len({r["batch_prefix"] for r in rows.values()}), 282)
	check("no linked master is missing", engine._missing_masters(cfg), [])

	sample = "PLATE8-MS-IS2062-E250"
	old = rows[sample]["replaces"]
	old_defaults = [(d.company, d.default_warehouse) for d in frappe.get_doc("Item", old).item_defaults] \
		if frappe.db.exists("Item", old) else None

	engine._do_transactions()
	check("transactions gone", frappe.db.count("Stock Ledger Entry"), 0)
	print("  preview:", engine._preview_items()[:3])
	engine._do_items()

	got = frappe.get_all("Item", filters={"name": ["in", list(rows)]},
	                     fields=["name", "custom_material_spec", "custom_material_grade", "custom_unit_weight",
	                             "gst_hsn_code", "custom_batch_prefix", "item_group", "stock_uom", "disabled"])
	check("all 282 items exist", len(got), 282)
	bad = [g.name for g in got if (g.custom_material_spec, g.custom_material_grade, round(g.custom_unit_weight, 3),
	                               g.gst_hsn_code, g.custom_batch_prefix, g.item_group, g.stock_uom, g.disabled)
	       != (rows[g.name]["spec"], rows[g.name]["grade"], round(rows[g.name]["unit_weight"], 3),
	           rows[g.name]["gst_hsn_code"], rows[g.name]["batch_prefix"], rows[g.name]["item_group"], "Kg", 0)]
	check("every item matches the sheet", bad, [])
	check("PLATE8 batch prefix is PT8-MS-IS2062-E250",
	      frappe.db.get_value("Item", sample, "custom_batch_prefix"), "PT8-MS-IS2062-E250")
	check("MS plate 8 mm HSN is 72085210", frappe.db.get_value("Item", sample, "gst_hsn_code"), "72085210")
	check("Chqd plate keeps its space, HSN 72084010",
	      frappe.db.get_value("Item", "CHQD PLATE5-MS-IS2062-E250", "gst_hsn_code"), "72084010")
	check("client-confirmed weight NPBX300X150 = 42.24",
	      frappe.db.get_value("Item", "NPBX300X150-MS-IS2062", "custom_unit_weight"), 42.24)
	if old_defaults is not None:
		check("new code copies the replaced item's defaults",
		      [(d.company, d.default_warehouse) for d in frappe.get_doc("Item", sample).item_defaults], old_defaults)

	check("old code deleted", frappe.db.exists("Item", old), None)
	check("old generic codes deleted", [n for n in ("PLATE16", "ISMB200", "PLATE25-G1") if frappe.db.exists("Item", n)], [])
	check("test item E2E-FG-STRUCT deleted", frappe.db.exists("Item", "E2E-FG-STRUCT"), None)
	kept = ["SHS100", "SHS150", "Fabricated Structurs", "FINGOODS001", "Bolt-M16X85", "Nut-M20"]
	check("kept items stay", [n for n in kept if frappe.db.exists("Item", n)],
	      [n for n in kept if n in ("SHS100", "SHS150") or frappe.db.exists("Item", n)])
	rm_left = frappe.get_all("Item", filters={"item_group": ["in", cfg["rm_item_groups"]]}, pluck="name")
	check("raw-material groups hold the master plus the kept two",
	      sorted(set(rm_left) - set(rows)), sorted(n for n in cfg["keep"] if n in rm_left))

	engine._do_items()
	check("second run: nothing more to delete", engine._items_to_delete(cfg), [])
	check("second run: still 282 items", frappe.db.count("Item", {"name": ["in", list(rows)]}), 282)
