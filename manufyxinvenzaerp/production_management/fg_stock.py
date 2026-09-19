"""Finished goods stock: Kg on the ledger, Nos per drawing batch.

THE CONTRACT for the sep14 finished-goods plan
(.claude/tasks/sep14_fg_uom_plan.md). Wave 0 (A0) fixed the names, arguments and
return shapes here; A4 fills in the bodies. The Delivery Note (A5), the Sales
Invoice (A6) and the Final Stock Entry code call these and nothing else, so a
signature must not change without telling every one of them.

The model, in one paragraph:
	A finished-goods item is stocked in Kg (stock UOM Kg) and every FG stock row
	also carries its piece count as Sec Qty in Nos. There is exactly ONE batch per
	drawing, named FG-<Sales Order>-<DUNO>, so a batch always holds pieces of one
	shape, and its Kg per piece is simply batch Kg / batch Nos. The Kg side is
	ERPNext's own stock ledger. The Nos side is ours: Batch.custom_sec_qty for the
	batch as a whole, and Sec Qty in minus out of submitted Stock Entry and
	Delivery Note rows for each warehouse.

Rules every function here keeps:
	- 3 decimals for every Kg figure: flt(x, 3), for results and for comparisons.
	  There is no other tolerance.
	- Last-piece rule: when the Nos asked for is everything that is left (in a
	  batch in a warehouse, pending on a Sales Order line, unbilled on a Delivery
	  Note row), the Kg is the exact Kg left, never Nos x Kg per piece. That is what
	  stops a rounding crumb of 0.001 Kg being stranded in a batch with 0 Nos.
	- Nos is tracked per warehouse, because a batch can sit in more than one
	  warehouse after a Material Transfer.
	- An FG row is a row whose item has custom_parent_item_group "Finished Goods".
	  Always ask is_fg_item(); never compare the group by hand.
"""

import frappe
from frappe.utils import cint, flt

FG_PARENT_ITEM_GROUP = "Finished Goods"
FG_BATCH_PREFIX = "FG-"


def is_fg_item(item_code):
	"""True when item_code is a finished-goods item.

	Input:  item_code (str or None).
	Output: bool. False for an empty code or an item that does not exist.

	An item is finished goods when its custom_parent_item_group is "Finished Goods"
	(the Item's own Item Group is "Fin Goods Item"; the parent group is the one this
	app classifies on everywhere). Cached per request through frappe.get_cached_value,
	which is cleared when the Item is saved, so calling this once per row is cheap.
	"""
	if not item_code:
		return False
	return (
		frappe.get_cached_value("Item", item_code, "custom_parent_item_group")
		== FG_PARENT_ITEM_GROUP
	)


def _stored_setting(fieldname):
	"""Raw Manufyxinvenza Settings value, or None when it was never stored.

	frappe.db.get_single_value cannot tell "never set" from "set to 0": it casts a
	missing Check to 0 and a missing Percent to 0.0. setup.set_fg_settings_defaults
	writes the defaults on migrate, and this keeps the default if that ever has
	not run on a site.
	"""
	rows = frappe.db.sql(
		"SELECT value FROM `tabSingles` WHERE doctype=%s AND field=%s",
		("Manufyxinvenza Settings", fieldname),
	)
	return rows[0][0] if rows else None


def edit_fg_stock_kg_enabled():
	"""Manufyxinvenza Settings -> "Edit FG Stock Kg" (default ON).

	Output: bool. True = the Kg of an FG row on the Final Stock Entry may be typed
	(the weighed figure); False = it is read-only and reset to Nos x the drawing's
	Cust Weight (per Nos) by the server.
	"""
	value = _stored_setting("edit_fg_stock_kg")
	return True if value is None else bool(cint(value))


def fg_weight_difference_warning_percent():
	"""Manufyxinvenza Settings -> "FG Weight Difference Warning (%)" (default 5).

	Output: float. Warn on the Final Stock Entry when the Kg entered for a drawing
	differs from its planned Kg by more than this share, either way. 0 means warn on
	any difference. Only consulted when Edit FG Stock Kg is on.
	"""
	value = _stored_setting("fg_weight_difference_warning_percent")
	return 5.0 if value is None else flt(value)


def get_or_create_fg_batch(
	item_code,
	sales_order,
	drawing,
	duno,
	customer,
	customer_drawing_number,
	job_work_order,
	cust_weight_per_nos,
	reference_name,
):
	"""The drawing's finished-goods batch, creating it on first use.

	Inputs:
		item_code                -- the FG item (must pass is_fg_item).
		sales_order              -- the Sales Order the drawing belongs to.
		drawing                  -- Drawing name.
		duno                     -- the drawing's DUNO/Mark No; may be blank.
		customer                 -- Customer of the Sales Order.
		customer_drawing_number  -- the customer's drawing number.
		job_work_order           -- the Subcontracting Order booking it.
		cust_weight_per_nos      -- the drawing's Cust Weight (per Nos), Kg.
		reference_name           -- the Final Stock Entry creating it.

	Output: the Batch name (str).

	Rules (A4):
		- Name is FG-<sales_order>-<duno>, or FG-<sales_order>-<drawing> when the
		  DUNO is blank. One batch per drawing, never one per entry.
		- Created by an explicit insert (not ERPNext's auto batch), filling every
		  Batch "FG Details" field: custom_sales_order, custom_customer,
		  custom_drawing, custom_duno_mark_no, custom_customer_drawing_number,
		  custom_job_work_order, custom_cust_weight_per_nos; custom_sec_uom "Nos";
		  reference_doctype "Stock Entry" / reference_name = the first Final Stock
		  Entry.
		- A later entry for the same drawing reuses the existing batch unchanged.
	"""
	# TODO(A4): implement.
	raise NotImplementedError("fg_stock.get_or_create_fg_batch is filled in by A4")


def refresh_fg_batch(batch_no):
	"""Recompute a finished-goods batch's piece figures from the ledger.

	Input:  batch_no (str), an FG batch.
	Output: None. Writes on the Batch:
		custom_sec_qty          -- total Nos in the batch, all warehouses: Sec Qty in
		                           minus out over submitted Stock Entry and Delivery
		                           Note rows of this batch;
		custom_weight_per_piece -- "Actual Kg per Nos" = flt(batch Kg / batch Nos, 3),
		                           Kg from the stock ledger; left as it was when the
		                           batch holds 0 Nos.

	Called on submit and on cancel of every document that moves an FG batch
	(Stock Entry, Delivery Note), so it must be idempotent: it recomputes from
	scratch, it never adds a delta.
	"""
	# TODO(A4): implement.
	raise NotImplementedError("fg_stock.refresh_fg_batch is filled in by A4")


def fg_batch_nos_by_warehouse(batch_no):
	"""Nos of a finished-goods batch per warehouse.

	Input:  batch_no (str).
	Output: {warehouse: nos} for every warehouse holding more than 0 Nos, where nos
	        = Sec Qty received into the warehouse minus Sec Qty sent out of it, over
	        submitted Stock Entry rows (t_warehouse in / s_warehouse out) and
	        Delivery Note rows (out; a return comes back in).
	"""
	# TODO(A4): implement.
	raise NotImplementedError("fg_stock.fg_batch_nos_by_warehouse is filled in by A4")


def fg_batch_available(batch_no, warehouse):
	"""What a finished-goods batch holds in one warehouse.

	Inputs: batch_no (str), warehouse (str).
	Output: {"nos": float, "kg": float, "kg_per_nos": float}
		nos        -- from fg_batch_nos_by_warehouse;
		kg         -- flt(batch qty in that warehouse from the stock ledger, 3);
		kg_per_nos -- flt(kg / nos, 3), or 0 when nos is 0.
	"""
	# TODO(A4): implement.
	raise NotImplementedError("fg_stock.fg_batch_available is filled in by A4")


def kg_for_nos(batch_no, warehouse, nos):
	"""The Kg that goes with `nos` pieces taken from a batch in a warehouse.

	Inputs: batch_no (str), warehouse (str), nos (whole number > 0).
	Output: Kg (float, 3 dp).

	Rules:
		- nos == everything available in that warehouse -> the exact Kg available
		  there (last-piece rule);
		- otherwise flt(nos * kg_per_nos, 3), kg_per_nos from fg_batch_available;
		- the caller validates nos <= available and whole Nos; this only prices it.
	"""
	# TODO(A4): implement.
	raise NotImplementedError("fg_stock.kg_for_nos is filled in by A4")


def validate_fg_stock_entry_rows(doc, method=None):
	"""Stock Entry validate hook for finished-goods rows (registered in hooks.py).

	Owner: A4. Wave 0 stub: does nothing, so no Stock Entry behaves differently.

	What A4 makes it do, for FG rows only (is_fg_item):
		- every FG row needs a batch;
		- Manufacture: Edit FG Stock Kg off -> reset Kg to Nos x Cust Weight (per
		  Nos); on -> keep the typed Kg and warn above FG Weight Difference Warning
		  (%) (drawing, planned, entered, difference Kg and %); whole Nos only;
		- Material Transfer / Material Issue: batch and Nos mandatory, whole Nos,
		  Nos <= available in the source warehouse, Kg = kg_for_nos (read-only);
		- Material Receipt: an existing FG batch is mandatory (no new FG batch this
		  way), Nos mandatory, Kg typed (the re-weigh case).
	"""
	# TODO(A4): implement. Must stay a no-op until then -- it is wired into hooks.
	pass


def on_fg_stock_entry_change(doc, method=None):
	"""Stock Entry on_submit / on_cancel hook (registered in hooks.py).

	Owner: A4. Wave 0 stub: does nothing.

	What A4 makes it do: refresh_fg_batch() for every distinct FG batch on the
	entry, on submit and on cancel alike (refresh_fg_batch recomputes from the
	ledger, so the same call serves both).
	"""
	# TODO(A4): implement. Must stay a no-op until then -- it is wired into hooks.
	pass
