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
from frappe import _
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




# Stock Entry purposes whose FG rows fg_stock looks after. Anything else only has to
# carry a batch.
_TAKE_OUT_PURPOSES = ("Material Transfer", "Material Issue")


def _is_batch_fg_item(item_code):
	"""An FG item on the new model: finished goods AND batch-tracked.

	Legacy FG items (FINGOODS001: stocked in Nos, no batch) are left alone, as the plan
	says old data is (D13). A1's item rule makes every NEW finished-goods item
	batch-tracked, so this does not let a new one slip past."""
	return is_fg_item(item_code) and bool(
		cint(frappe.get_cached_value("Item", item_code, "has_batch_no"))
	)


def _is_whole(nos):
	return flt(nos, 3) == int(flt(nos, 3))


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
		reference_name           -- the Final Stock Entry creating it. May be None when
		                            the entry has not been saved yet (the Final Stock
		                            Entry builder picks the batch before it inserts the
		                            entry); on_fg_stock_entry_change then fills the
		                            reference in when that entry is submitted.

	Output: the Batch name (str).

	Rules:
		- Name is FG-<sales_order>-<duno>, or FG-<sales_order>-<drawing> when the
		  DUNO is blank. One batch per drawing, never one per entry: a batch that
		  already carries this drawing for this item is returned whatever its name.
		- If FG-<sales_order>-<duno> is taken by ANOTHER drawing (a DUNO repeated on
		  one order), the drawing name is used instead of the DUNO.
		- Created by an explicit insert (not ERPNext's auto batch), filling every
		  Batch "FG Details" field; reference_doctype "Stock Entry".
		- A later entry for the same drawing reuses the existing batch unchanged.
	"""
	if not is_fg_item(item_code):
		frappe.throw(_("{0} is not a finished-goods item, so it has no drawing batch.").format(item_code))
	if not (sales_order and drawing):
		frappe.throw(
			_("A finished-goods batch needs the Sales Order and the Drawing it belongs to "
			  "(item {0}, drawing {1}, order {2}).").format(item_code, drawing or "-", sales_order or "-")
		)

	existing = frappe.db.get_value("Batch", {"item": item_code, "custom_drawing": drawing}, "name")
	if existing:
		return existing

	duno = (duno or "").strip()
	candidates = []
	if duno:
		candidates.append("%s%s-%s" % (FG_BATCH_PREFIX, sales_order, duno))
	candidates.append("%s%s-%s" % (FG_BATCH_PREFIX, sales_order, drawing))

	batch_id = None
	for name in candidates:
		if not frappe.db.exists("Batch", name):
			batch_id = name
			break
	if not batch_id:
		# Both names are held by some other drawing or item. Guessing a third name
		# would hide the collision; the user has to look at those batches.
		frappe.throw(
			_("Cannot create the finished-goods batch for drawing {0}: {1} already "
			  "exist for another drawing or item.").format(drawing, ", ".join(candidates)),
			title=_("FG Batch Name Taken"),
		)

	batch = frappe.get_doc({
		"doctype": "Batch",
		"batch_id": batch_id,
		"item": item_code,
		"custom_sales_order": sales_order,
		"custom_customer": customer or None,
		"custom_drawing": drawing,
		"custom_duno_mark_no": duno,
		"custom_customer_drawing_number": customer_drawing_number or "",
		"custom_job_work_order": job_work_order or None,
		"custom_cust_weight_per_nos": flt(cust_weight_per_nos, 3),
		"custom_sec_uom": "Nos",
		"custom_sec_qty": 0,
	})
	if reference_name and frappe.db.exists("Stock Entry", reference_name):
		batch.reference_doctype = "Stock Entry"
		batch.reference_name = reference_name
	batch.insert(ignore_permissions=True)
	return batch.name


def _batch_row_match(alias):
	"""SQL condition: row `alias` moved batch %(batch)s.

	A row normally names its batch in batch_no (use_serial_batch_fields). A row whose
	batch was picked through a Serial and Batch Bundle instead carries it only in the
	bundle, so that is looked at as well; an FG row always moves exactly one batch."""
	return (
		"({a}.batch_no = %(batch)s OR {a}.serial_and_batch_bundle IN ("
		"SELECT sbe.parent FROM `tabSerial and Batch Entry` sbe WHERE sbe.batch_no = %(batch)s))"
	).format(a=alias)


def _nos_by_warehouse_all(batch_no):
	"""{warehouse: net Nos} for the batch, zero and negative balances included.

	Stock Entry rows: t_warehouse receives, s_warehouse gives (a transfer does both).
	Delivery Note rows: `warehouse` gives. A return row carries a negative Sec Qty,
	so the same subtraction puts its pieces back."""
	rows = frappe.db.sql(
		"""
		SELECT wh, SUM(nos) AS nos FROM (
			SELECT sed.t_warehouse AS wh, IFNULL(sed.custom_sec_qty, 0) AS nos
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.docstatus = 1 AND IFNULL(sed.t_warehouse, '') != '' AND {sed}
			UNION ALL
			SELECT sed.s_warehouse AS wh, -IFNULL(sed.custom_sec_qty, 0) AS nos
			FROM `tabStock Entry Detail` sed
			JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.docstatus = 1 AND IFNULL(sed.s_warehouse, '') != '' AND {sed}
			UNION ALL
			SELECT dni.warehouse AS wh, -IFNULL(dni.custom_sec_qty, 0) AS nos
			FROM `tabDelivery Note Item` dni
			JOIN `tabDelivery Note` dn ON dn.name = dni.parent
			WHERE dn.docstatus = 1 AND IFNULL(dni.warehouse, '') != '' AND {dni}
		) moves
		GROUP BY wh
		""".format(sed=_batch_row_match("sed"), dni=_batch_row_match("dni")),
		{"batch": batch_no},
		as_dict=True,
	)
	return {r.wh: flt(r.nos, 3) for r in rows}


def _kg_by_warehouse(batch_no):
	"""{warehouse: Kg} of the batch from the stock ledger's submitted bundles."""
	rows = frappe.db.sql(
		"""
		SELECT sbe.warehouse AS wh, COALESCE(SUM(sbe.qty), 0) AS kg
		FROM `tabSerial and Batch Entry` sbe
		JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
		WHERE sbe.batch_no = %s AND sbb.docstatus = 1 AND IFNULL(sbb.is_cancelled, 0) = 0
		GROUP BY sbe.warehouse
		""",
		batch_no,
		as_dict=True,
	)
	return {r.wh: flt(r.kg, 3) for r in rows}


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
	scratch, it never adds a delta. It therefore also overrides whatever the older
	Material Issue handler in stock_entry.py subtracted from custom_sec_qty.
	"""
	if not batch_no or not frappe.db.exists("Batch", batch_no):
		return
	nos = flt(sum(_nos_by_warehouse_all(batch_no).values()), 3)
	kg = flt(sum(_kg_by_warehouse(batch_no).values()), 3)
	values = {"custom_sec_qty": nos}
	if not frappe.db.get_value("Batch", batch_no, "custom_sec_uom"):
		values["custom_sec_uom"] = "Nos"
	if nos > 0:
		values["custom_weight_per_piece"] = flt(kg / nos, 3)
	frappe.db.set_value("Batch", batch_no, values, update_modified=False)


def fg_batch_nos_by_warehouse(batch_no):
	"""Nos of a finished-goods batch per warehouse.

	Input:  batch_no (str).
	Output: {warehouse: nos} for every warehouse holding more than 0 Nos, where nos
	        = Sec Qty received into the warehouse minus Sec Qty sent out of it, over
	        submitted Stock Entry rows (t_warehouse in / s_warehouse out) and
	        Delivery Note rows (out; a return comes back in).
	"""
	if not batch_no:
		return {}
	return {wh: nos for wh, nos in _nos_by_warehouse_all(batch_no).items() if nos > 0}


def fg_batch_available(batch_no, warehouse):
	"""What a finished-goods batch holds in one warehouse.

	Inputs: batch_no (str), warehouse (str).
	Output: {"nos": float, "kg": float, "kg_per_nos": float}
		nos        -- from fg_batch_nos_by_warehouse;
		kg         -- flt(batch qty in that warehouse from the stock ledger, 3);
		kg_per_nos -- flt(kg / nos, 3), or 0 when nos is 0. For display: kg_for_nos
		              divides the unrounded figures (see there).
	"""
	nos = flt(fg_batch_nos_by_warehouse(batch_no).get(warehouse), 3) if batch_no and warehouse else 0.0
	kg = flt(_kg_by_warehouse(batch_no).get(warehouse), 3) if batch_no and warehouse else 0.0
	return {"nos": nos, "kg": kg, "kg_per_nos": flt(kg / nos, 3) if nos > 0 else 0.0}


def _price_nos(available_nos, available_kg, nos):
	"""Kg for `nos` out of a stock of available_nos / available_kg (last-piece rule).

	Priced as nos x kg / available_nos on the UNROUNDED ratio and rounded once: taking
	6 of 7 pieces weighing 211.5 Kg is 181.286, not 6 x 30.214 = 181.284. Rounding
	the ratio first would move up to nos x 0.0005 Kg onto the pieces left behind."""
	available_nos, available_kg, nos = flt(available_nos, 3), flt(available_kg, 3), flt(nos, 3)
	if nos <= 0 or available_nos <= 0:
		return 0.0
	if nos == available_nos:
		return available_kg
	return flt(nos * available_kg / available_nos, 3)


def kg_for_nos(batch_no, warehouse, nos):
	"""The Kg that goes with `nos` pieces taken from a batch in a warehouse.

	Inputs: batch_no (str), warehouse (str), nos (whole number > 0).
	Output: Kg (float, 3 dp).

	Rules:
		- nos == everything available in that warehouse -> the exact Kg available
		  there (last-piece rule);
		- otherwise flt(nos * kg / available nos, 3) -- the ratio is NOT rounded to
		  3 dp first (see _price_nos), so kg_per_nos from fg_batch_available is only
		  for display;
		- the caller validates nos <= available and whole Nos; this only prices it.
	"""
	avail = fg_batch_available(batch_no, warehouse)
	return _price_nos(avail["nos"], avail["kg"], nos)


def planned_kg_per_nos(drawing=None, batch_no=None):
	"""Cust Weight (per Nos) for a finished-goods row: the drawing's own figure first
	(Update Customer Weight changes it there), else the one the batch was made with."""
	if not drawing and batch_no:
		drawing = frappe.db.get_value("Batch", batch_no, "custom_drawing")
	per_nos = flt(frappe.db.get_value("Drawing", drawing, "weight_per_pcs")) if drawing else 0.0
	if not per_nos and batch_no:
		per_nos = flt(frappe.db.get_value("Batch", batch_no, "custom_cust_weight_per_nos"))
	return per_nos


# ── Stock Entry hooks ─────────────────────────────────────────────────────────

def validate_fg_stock_entry_rows(doc, method=None):
	"""Stock Entry validate hook for finished-goods rows (registered in hooks.py).

	Runs after ERPNext's own validate and stock_entry.validate_stock_entry, which
	leave FG rows alone. For FG rows only (is_fg_item, batch-tracked):
		- every FG row needs a batch of its own item;
		- Manufacture (the produced row): whole Nos > 0; Edit FG Stock Kg off -> Kg
		  reset to flt(Nos x Cust Weight (per Nos), 3); on -> the typed Kg is kept and
		  an orange warning lists every drawing whose Kg is off its planned Kg by more
		  than FG Weight Difference Warning (%);
		- Material Transfer / Material Issue: batch and Nos mandatory, whole Nos,
		  Nos <= what the batch holds in the source warehouse (less earlier rows of
		  this same entry), Kg = kg_for_nos -- whatever was typed is replaced;
		- Material Receipt: an existing batch of the item is mandatory (ERPNext makes
		  no FG batch: create_new_batch is off), whole Nos > 0, Kg typed (re-weigh).
	When a Kg is changed here, ERPNext's transfer qty and rates -- already worked out
	earlier in validate from the old Kg -- are recomputed, and so are the header
	totals stock_entry.validate_stock_entry wrote.
	"""
	rows = [r for r in doc.items if r.item_code and _is_batch_fg_item(r.item_code)]
	if not rows:
		return

	purpose = doc.purpose or doc.stock_entry_type
	changed = False
	warnings = []
	taken = {}  # (batch, warehouse) -> [nos, kg] already taken by earlier rows

	for row in rows:
		label = _("Row {0} ({1})").format(row.idx, row.item_code)
		if not row.batch_no:
			frappe.throw(
				_("{0}: finished goods are tracked per drawing batch, so a Batch No is "
				  "mandatory.").format(label),
				title=_("FG Batch Missing"),
			)
		if frappe.db.get_value("Batch", row.batch_no, "item") != row.item_code:
			frappe.throw(_("{0}: batch {1} does not belong to this item.").format(label, row.batch_no))

		nos = flt(row.get("custom_sec_qty"), 3)
		row.custom_sec_uom = row.get("custom_sec_uom") or "Nos"

		if purpose == "Manufacture":
			if row.s_warehouse or not row.t_warehouse:
				continue  # an FG item consumed, not produced: only the batch rule applies
			_require_whole_nos(label, nos)
			per_nos = planned_kg_per_nos(row.get("custom_drawing"), row.batch_no)
			planned = flt(nos * per_nos, 3)
			if not edit_fg_stock_kg_enabled():
				if not per_nos:
					frappe.throw(
						_("{0}: the drawing has no Cust Weight (per Nos), so the Kg cannot "
						  "be worked out. Set it with Update Customer Weight on the Drawing.")
						.format(label)
					)
				if flt(row.qty, 3) != planned:
					row.qty = planned
					changed = True
			elif flt(row.qty, 3) <= 0:
				frappe.throw(_("{0}: enter the weighed Kg.").format(label))
			elif planned:
				diff = flt(flt(row.qty, 3) - planned, 3)
				pct = flt(abs(diff) * 100.0 / planned, 2)
				limit = fg_weight_difference_warning_percent()
				if diff and pct > limit:
					warnings.append(_(
						"{0}: planned {1} Kg ({2} Nos x {3}), entered {4} Kg, difference "
						"{5} Kg ({6}%)").format(
							row.get("custom_duno_mark_no") or row.get("custom_drawing") or label,
							planned, nos, per_nos, flt(row.qty, 3), diff, pct))

		elif purpose in _TAKE_OUT_PURPOSES:
			if not row.s_warehouse:
				frappe.throw(_("{0}: the source warehouse is mandatory.").format(label))
			_require_whole_nos(label, nos)
			key = (row.batch_no, row.s_warehouse)
			if key not in taken:
				avail = fg_batch_available(row.batch_no, row.s_warehouse)
				taken[key] = [avail["nos"], avail["kg"]]
			left_nos, left_kg = taken[key]
			if nos > left_nos:
				frappe.throw(
					_("{0}: batch {1} holds {2} Nos in {3}; {4} Nos cannot be taken.").format(
						label, row.batch_no, flt(left_nos, 3), row.s_warehouse, nos),
					title=_("Not Enough Pieces"),
				)
			kg = _price_nos(left_nos, left_kg, nos)
			taken[key] = [flt(left_nos - nos, 3), flt(left_kg - kg, 3)]
			if flt(row.qty, 3) != kg:
				row.qty = kg
				changed = True

		elif purpose == "Material Receipt":
			_require_whole_nos(label, nos)
			if flt(row.qty, 3) <= 0:
				frappe.throw(_("{0}: enter the weighed Kg.").format(label))

	if changed:
		for row in rows:
			# The Kg is the stock UOM; a row in any other UOM would be scaled again.
			if row.uom != row.stock_uom:
				row.uom = row.stock_uom
				row.conversion_factor = 1
		doc.set_transfer_qty()
		doc.calculate_rate_and_amount()
		doc.custom_total_qty = flt(sum(flt(r.qty) for r in doc.items), 3)
		doc.custom_total_sec_qty = flt(sum(flt(r.get("custom_sec_qty")) for r in doc.items), 3)

	if warnings:
		frappe.msgprint(
			_("The Kg entered differs from the planned weight by more than {0}%:").format(
				fg_weight_difference_warning_percent())
			+ "<br>" + "<br>".join(warnings),
			title=_("FG Weight Difference"),
			indicator="orange",
		)


def _require_whole_nos(label, nos):
	if nos <= 0:
		frappe.throw(_("{0}: enter the number of pieces (Qty (Nos)).").format(label), title=_("Nos Missing"))
	if not _is_whole(nos):
		frappe.throw(_("{0}: Qty (Nos) must be a whole number of pieces, not {1}.").format(label, nos))


def on_fg_stock_entry_change(doc, method=None):
	"""Stock Entry on_submit / on_cancel hook (registered in hooks.py).

	refresh_fg_batch() for every distinct FG batch on the entry, on submit and on
	cancel alike (refresh_fg_batch recomputes from the ledger, so the same call
	serves both). On cancel ERPNext has already cleared batch_no off the rows, so the
	batch is read back from the row's bundle (stock_entry._cancelled_row_batch_no).

	On submit of a Manufacture entry, an FG batch still without a reference (the
	Final Stock Entry builder creates it before the entry has a name) is pointed at
	this entry -- the first Final Stock Entry that booked into it.
	"""
	from manufyxinvenzaerp.production_management.stock_entry import _cancelled_row_batch_no

	batches = []
	for row in doc.items:
		if not (row.item_code and _is_batch_fg_item(row.item_code)):
			continue
		batch_no = _cancelled_row_batch_no(row, doc.name)
		if batch_no and batch_no not in batches:
			batches.append(batch_no)

	for batch_no in batches:
		refresh_fg_batch(batch_no)
		if (
			method == "on_submit"
			and (doc.purpose or doc.stock_entry_type) == "Manufacture"
			and not frappe.db.get_value("Batch", batch_no, "reference_name")
		):
			frappe.db.set_value(
				"Batch", batch_no,
				{"reference_doctype": "Stock Entry", "reference_name": doc.name},
				update_modified=False,
			)


# ── Form helpers (public/js/stock_entry_fg.js) ────────────────────────────────

@frappe.whitelist()
def get_fg_settings():
	"""The two finished-goods settings, with their defaults applied."""
	return {
		"edit_fg_stock_kg": edit_fg_stock_kg_enabled(),
		"fg_weight_difference_warning_percent": fg_weight_difference_warning_percent(),
	}


@frappe.whitelist()
def get_fg_kg_for_nos(batch_no, warehouse, nos):
	"""Kg for `nos` pieces out of a batch in a warehouse, plus what is there -- the
	form shows the same figure the server will set on save."""
	frappe.has_permission("Batch", "read", doc=batch_no, throw=True)
	avail = fg_batch_available(batch_no, warehouse)
	return dict(avail, kg=kg_for_nos(batch_no, warehouse, flt(nos)), available_kg=avail["kg"])


@frappe.whitelist()
def get_fg_planned_kg(nos, drawing=None, batch_no=None):
	"""Planned Kg of a Final Stock Entry row: Nos x Cust Weight (per Nos)."""
	if batch_no:
		frappe.has_permission("Batch", "read", doc=batch_no, throw=True)
	per_nos = planned_kg_per_nos(drawing, batch_no)
	return {"kg_per_nos": per_nos, "kg": flt(flt(nos) * per_nos, 3)}
