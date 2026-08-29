# Copyright (c) 2026, Manufyxinvenza and Contributors
# License: GNU General Public License v3. See license.txt

"""Production Report -- one row per drawing, every operation across the columns.

This used to be one row per drawing *per operation*, which meant a four-operation job
with six drawings filled twenty-four rows with the same six drawings repeated, and
answering "where is 1B1 up to" meant reading four rows and holding them in your head.

It is now one row per drawing per Job Work Order, with each operation contributing its
own block of columns -- quantity, status, inspection rounds, last inspection status and
the gap in days. The operations are not a fixed list: they are whichever operations the
jobs in view actually have, in sequence order, so a job routed through Welding and
Blasting shows those and a job routed through Fit-up and Painting shows those.

The first operation is measured in Kg -- it is where raw material is issued -- and every
later one in Nos, since what a fabricator completes downstream is pieces.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

CONSUMPTION_ENTRY_TYPE = "Material Consumption for Manufacture"


def execute(filters=None):
	filters = filters or {}
	data, operations = get_data(filters)
	return get_columns(operations), data


def get_data(filters):
	"""Rows are Job Work Orders, not operation entries.

	A job belongs in this report the moment its Job Work Order is submitted -- before
	anybody has issued a gram of steel against it. Driving the query off Supplier
	Operation Entry meant a submitted job whose operation entries had not been raised
	yet was simply absent, with nothing on screen to say the job existed at all. It
	now starts from the submitted orders themselves and fills the operation blocks in
	from whatever entries exist, so a brand-new job shows its drawings, its weights and
	an empty row of operations waiting to be worked."""
	sco_filters = {"docstatus": 1}
	if filters.get("subcontracting_order"):
		sco_filters["name"] = filters["subcontracting_order"]
	if filters.get("supplier"):
		sco_filters["supplier"] = filters["supplier"]
	if filters.get("production_plan"):
		sco_filters["custom_production_plan"] = filters["production_plan"]
	# The date people mean is the one on screen -- the Job Work Order's own date, which
	# is what the Created On column shows. Filtering operation-entry timestamps instead
	# made a job drop out of its own date range depending on when its later operations
	# happened to be raised.
	if filters.get("from_date"):
		sco_filters["transaction_date"] = [">=", filters["from_date"]]
	if filters.get("to_date"):
		sco_filters["transaction_date"] = (
			["between", [filters["from_date"], filters["to_date"]]]
			if filters.get("from_date") else ["<=", filters["to_date"]]
		)

	scos = frappe.get_all(
		"Subcontracting Order",
		filters=sco_filters,
		fields=["name", "supplier", "custom_production_plan", "transaction_date", "creation"],
	)
	if not scos:
		return [], []

	pp_map = {}
	pp_names = list({s.custom_production_plan for s in scos if s.custom_production_plan})
	if pp_names:
		pp_filters = {"name": ["in", pp_names]}
		if filters.get("job_type"):
			pp_filters["custom_type"] = filters["job_type"]
		for p in frappe.get_all("Production Plan", filters=pp_filters,
								fields=["name", "custom_type", "project", "company"]):
			pp_map[p.name] = p
	if filters.get("job_type"):
		scos = [s for s in scos if s.custom_production_plan in pp_map]
		if not scos:
			return [], []

	sco_names = [s.name for s in scos]
	sco_map = {s.name: s for s in scos}
	created_on = {s.name: (s.transaction_date or getdate(s.creation)) for s in scos}

	soe_filters = {"subcontracting_order": ["in", sco_names]}
	if filters.get("status"):
		soe_filters["status"] = filters["status"]
	if filters.get("operation"):
		soe_filters["operation"] = filters["operation"]
	soes = frappe.get_all(
		"Supplier Operation Entry",
		filters=soe_filters,
		fields=["name", "production_plan", "subcontracting_order", "supplier", "operation",
				"sequence_id", "status", "custom_inspection_status", "custom_inspection_mandatory",
				"total_consumed_kg", "total_completed_nos", "creation"],
	)
	# An Operation or Status filter is a question about operations, so it narrows the
	# jobs too: asking for Open Fit-up should not list every job in the yard with the
	# Fit-up columns blank.
	if filters.get("status") or filters.get("operation"):
		matched = {s.subcontracting_order for s in soes}
		sco_names = [n for n in sco_names if n in matched]
		if not sco_names:
			return [], []

	# "Operation gap in days" has no dedicated start/end field anywhere in
	# this data model (Supplier Operation Entry carries no date fields of its
	# own beyond the inspection-specific custom_inspection_call_date) -- the
	# best available proxy is the creation-timestamp gap between consecutive
	# sequence_id rows of the same Subcontracting Order, since SOEs are
	# created in sequence order as each prior operation's consumption chains
	# into the next (subcontracting.py's _get_soe_creation_loop). Flagged as
	# approximate in the column label/description so it isn't mistaken for a
	# precise measurement.
	by_sco = {}
	for s in soes:
		by_sco.setdefault(s.subcontracting_order, []).append(s)
	gap_days = {}
	for sco, rows in by_sco.items():
		rows_sorted = sorted(rows, key=lambda r: (r.sequence_id or 0))
		prev_creation = None
		for r in rows_sorted:
			if prev_creation:
				gap_days[r.name] = (getdate(r.creation) - getdate(prev_creation)).days
			else:
				gap_days[r.name] = 0
			prev_creation = r.creation

	call_counts = {}
	if soes:
		for c in frappe.get_all(
			"Inspection Call Log",
			filters={"parenttype": "Supplier Operation Entry", "parent": ["in", [s.name for s in soes]]},
			fields=["parent"],
		):
			call_counts[c.parent] = call_counts.get(c.parent, 0) + 1

	# Completed pieces per operation, keyed (operation entry, drawing). This is the one
	# thing only the operation's own drawing table knows.
	completed_by_soe = {}
	for d in frappe.get_all(
		"SOE Drawing Detail",
		filters={"parent": ["in", [s.name for s in soes]]} if soes else {"parent": ["in", []]},
		fields=["parent", "drawing", "completed_qty_nos"],
	):
		completed_by_soe[(d.parent, d.drawing)] = flt(d.completed_qty_nos)

	drawing_rows = _job_drawings(sco_names, soes)
	if not drawing_rows:
		return [], []

	weights, sec_nos, completed = _drawing_figures(sco_names)
	mip_by_sco = _mip_by_sco(sco_names)
	excess = _excess_by_sco(mip_by_sco)
	consumables = _consumables_by_sco(sco_names, {s.custom_production_plan for s in scos})
	rm_cost = _rm_cost_by_drawing(sco_names, mip_by_sco)

	so_names = list({d["sales_order"] for d in drawing_rows if d["sales_order"]})
	so_map = {}
	if so_names:
		for so in frappe.get_all("Sales Order", filters={"name": ["in", so_names]},
								 fields=["name", "customer", "project"]):
			so_map[so.name] = so

	drawing_names = list({d["drawing"] for d in drawing_rows if d["drawing"]})
	rate_map = {}
	if drawing_names:
		for dr in frappe.get_all("Drawing", filters={"name": ["in", drawing_names]},
								 fields=["name", "rate_schedule", "rs_rate_per_kg"]):
			rate_map[dr.name] = dr

	if filters.get("sales_order"):
		drawing_rows = [d for d in drawing_rows if d["sales_order"] == filters["sales_order"]]
		if not drawing_rows:
			return [], []

	# The operation columns are whatever the jobs in view are actually routed through,
	# ordered by the sequence they run in. Sequence decides the unit as well: the first
	# operation is where raw material is issued and is read in Kg, everything after it
	# turns pieces out and is read in Nos.
	op_seq = {}
	for s in soes:
		if not s.operation or s.subcontracting_order not in sco_names:
			continue
		seq = s.sequence_id or 0
		lo, hi = op_seq.get(s.operation, (seq, seq))
		op_seq[s.operation] = (min(lo, seq), max(hi, seq))
	operations = _operation_columns(op_seq)
	slug_by_operation = {op["operation"]: op["slug"] for op in operations}
	kg_operations = {op["operation"] for op in operations if op["unit"] == _("Kg")}

	# One row per drawing per Job Work Order. Each operation writes into its own block
	# of that row rather than adding a row of its own.
	data = []
	rows_by_key = {}
	for d in drawing_rows:
		sco = sco_map[d["subcontracting_order"]]
		pp = pp_map.get(sco.custom_production_plan, frappe._dict())
		row = _base_row(sco, pp, d, so_map, weights, sec_nos, completed, excess,
						consumables, rm_cost, rate_map, created_on)
		rows_by_key[(d["subcontracting_order"], d["drawing"])] = row
		data.append(row)

	for s in soes:
		slug = slug_by_operation.get(s.operation)
		if not slug:
			continue
		is_first = s.operation in kg_operations
		for (sco_name, drawing), row in rows_by_key.items():
			if sco_name != s.subcontracting_order:
				continue
			# The issuing operation reports the drawing's transferred weight -- the same
			# figure the Transferred Weight column carries, deliberately, so the two do
			# not disagree. The operation's own copy of it is the pre-transfer plan and
			# would.
			row["op_%s_qty" % slug] = (
				flt(row["transferred_weight_kg"], 3) if is_first
				else flt(completed_by_soe.get((s.name, drawing)), 3)
			)
			row["op_%s_status" % slug] = s.status or ""
			row["op_%s_rounds" % slug] = call_counts.get(s.name, 0)
			row["op_%s_inspection" % slug] = s.custom_inspection_status or ""
			row["op_%s_gap" % slug] = gap_days.get(s.name, 0)

	data.sort(key=lambda r: (r["sales_order"] or "", r["production_plan"] or "",
							 r["subcontracting_order"] or "", r["drawing"] or ""))
	return data, operations


def _job_drawings(sco_names, soes):
	"""The drawings on each job, from the Job Work Order's own drawing table.

	Read from the order rather than from the operation entries so a job with no
	operation entries yet still has rows -- and so a drawing that is on the order but
	missing from some operation's copy of the table cannot go unreported.

	The operation entries are still used as a fallback for an order whose own table is
	empty, which is how jobs raised before that table was populated still show up."""
	rows = []
	seen = set()
	for w in frappe.get_all(
		"SCO Drawing Item",
		filters={"parent": ["in", sco_names], "parenttype": "Subcontracting Order"},
		fields=["parent", "drawing", "duno_mark_no", "customer_drawing_number", "sales_order"],
	):
		if not w.drawing or (w.parent, w.drawing) in seen:
			continue
		seen.add((w.parent, w.drawing))
		rows.append({"subcontracting_order": w.parent, "drawing": w.drawing,
					 "duno_mark_no": w.duno_mark_no or "", "sales_order": w.sales_order or "",
					 "customer_drawing_number": w.customer_drawing_number or ""})

	covered = {r["subcontracting_order"] for r in rows}
	uncovered = [s.name for s in soes if s.subcontracting_order not in covered]
	if uncovered:
		sco_by_soe = {s.name: s.subcontracting_order for s in soes}
		for d in frappe.get_all(
			"SOE Drawing Detail",
			filters={"parent": ["in", uncovered]},
			fields=["parent", "drawing", "duno_mark_no", "customer_drawing_number", "sales_order"],
		):
			key = (sco_by_soe[d.parent], d.drawing)
			if not d.drawing or key in seen:
				continue
			seen.add(key)
			rows.append({"subcontracting_order": key[0], "drawing": d.drawing,
						 "duno_mark_no": d.duno_mark_no or "", "sales_order": d.sales_order or "",
						 "customer_drawing_number": d.customer_drawing_number or ""})

	# Fall back to the Drawing master for Sales Order. The copy held on the drawing rows
	# is blank in practice -- it is only populated when the Production Plan item carried
	# one -- which left the Sales Order column empty, the Customer column empty (it is
	# looked up FROM the sales order) and the Sales Order filter matching nothing at all,
	# on a report whose whole point is to be readable sales-order-wise.
	missing_so = {r["drawing"] for r in rows if not r["sales_order"]}
	if missing_so:
		so_by_drawing = {
			dr.name: dr.sales_order
			for dr in frappe.get_all("Drawing", filters={"name": ["in", list(missing_so)]},
									 fields=["name", "sales_order"])
			if dr.sales_order
		}
		for r in rows:
			if not r["sales_order"]:
				r["sales_order"] = so_by_drawing.get(r["drawing"]) or ""
	return rows


def _base_row(sco, pp, d, so_map, weights, sec_nos, completed, excess, consumables,
			  rm_cost, rate_map, created_on):
	so = so_map.get(d["sales_order"], frappe._dict())
	name = sco.name
	drawing = d["drawing"]
	w = weights.get((name, drawing), frappe._dict())
	sn = sec_nos.get((name, d["duno_mark_no"]), {})
	done = completed.get((name, drawing), frappe._dict())
	ex = excess.get(name, {})
	cons = consumables.get(name, {})
	rate = rate_map.get(drawing, frappe._dict())

	# Weight of the pieces actually finished, rather than the count on its own: a
	# drawing worth 1814 Kg for two pieces has done 907 Kg when one of them is out.
	qty_to_mfg = flt(done.get("qty_to_manufacture"))
	per_piece = flt(done.get("total_weight_kg")) / qty_to_mfg if qty_to_mfg else 0.0
	completed_nos = flt(done.get("completed_qty_nos"))

	return {
		"sales_order": d["sales_order"],
		"customer": so.get("customer") or "",
		"project": pp.get("project") or so.get("project") or "",
		"production_plan": sco.custom_production_plan or "",
		"job_type": pp.get("custom_type") or "",
		"subcontracting_order": name,
		"supplier": sco.supplier,
		"drawing": drawing,
		"duno_mark_no": d["duno_mark_no"],
		"customer_drawing_number": d["customer_drawing_number"],
		"created_on": created_on.get(name),
		"customer_weight_kg": flt(w.get("customer_weight_kg")),
		"planned_weight_kg": flt(w.get("total_weight_kg")),
		"planned_sec_nos": flt(sn.get("planned"), 3),
		"transferred_weight_kg": flt(w.get("transferred_weight_kg")),
		"transferred_sec_nos": flt(sn.get("issued"), 3),
		"waste_pct": _waste_pct(w.get("customer_weight_kg"), w.get("total_weight_kg")),
		"consumed_rm_cost": flt(rm_cost.get((name, drawing))),
		"rate_schedule": rate.get("rate_schedule") or "",
		"rate_per_kg": flt(rate.get("rs_rate_per_kg")),
		"consumables_nos": flt(cons.get("nos"), 3),
		"consumable_cost": flt(cons.get("cost")),
		"excess_weight_kg": flt(ex.get("excess"), 3),
		"returned_excess_kg": flt(ex.get("returned"), 3),
		"excess_difference_kg": flt(ex.get("difference"), 3),
		"completed_drawing_weight_kg": flt(per_piece * completed_nos, 3),
		"completed_nos": completed_nos,
	}


def _waste_pct(customer_kg, planned_kg):
	"""How much more steel the job plans to buy than the finished part weighs.

	Cutting a member out of a length leaves an off-cut, so a few percent is normal and
	is what this is read for: a line well outside its neighbours is a cutting plan worth
	looking at, not a rounding artefact.

	Blank rather than zero when there is no customer weight to measure against --
	dividing by nothing is not zero waste, and a column of confident 0.00s is worse than
	an honest gap. Negative means the plan holds LESS material than the finished part
	weighs, which cannot be cut and is always an error upstream."""
	customer = flt(customer_kg)
	if not customer:
		return None
	return flt((flt(planned_kg) - customer) / customer * 100, 2)


def _operation_columns(op_seq):
	"""The operation blocks, in the order the operations run.

	`op_seq` maps an operation to the (lowest, highest) sequence it is found at across
	the jobs in view. Both ends matter, because a column carries one unit for every row
	in it: the material issued to a job is reported in Kg against that job's FIRST
	operation, and pieces completed in Nos against the rest.

	An operation that is first on one job and second on another therefore cannot be a Kg
	column -- half its rows would mean something else. That is not hypothetical: the
	routing dropped Material Issue on 2026-08-25, so jobs raised since start at Fit-up
	while older jobs have Fit-up at sequence 2. Such a column reads in Nos, and the Kg
	is still on the Transferred Weight column where it always was.

	Slugs are what the column fieldnames are built from, so two operations that scrub
	to the same slug ("Fit-up" and "Fit Up", say) are separated rather than silently
	writing into each other's columns."""
	seen = set()
	out = []
	for operation, (lo, hi) in sorted(op_seq.items(), key=lambda kv: (kv[1][0], kv[0])):
		slug = frappe.scrub(operation)
		if slug in seen:
			slug = "%s_%s" % (slug, len(out))
		seen.add(slug)
		out.append({"operation": operation, "slug": slug, "sequence_id": lo,
					"unit": _("Kg") if hi <= 1 else _("Nos")})
	return out


def _drawing_figures(sco_names):
	"""Drawing-level weights, piece counts and completion, keyed (job work order, drawing).

	Not read from the SOE Drawing Detail rows: their transferred_weight_kg is only ever
	filled on sequence 1, so every later operation would report 0 Kg transferred for a
	drawing whose material had in fact shipped.

	Preference is the linked Material Issue Plan's own drawing rows -- that is where
	transferred weight is actually maintained (refresh_weight_summary); the
	Subcontracting Order's copy of the same table carries customer/planned/excess but
	leaves transferred at 0. The SCO rows are loaded first as a fallback so a plan with
	no Material Issue Plan yet still reports the three weights it does know.

	Completion goes the other way and is read from the Subcontracting Order's rows only:
	that is the copy the operations write finished pieces back to, and it is a
	job-level figure rather than one operation's share of it."""
	weights, sec_nos, completed = {}, {}, {}
	if not sco_names:
		return weights, sec_nos, completed

	mip_to_sco = {
		m.name: m.subcontracting_order
		for m in frappe.get_all(
			"Material Issue Plan",
			filters={"subcontracting_order": ["in", sco_names]},
			fields=["name", "subcontracting_order"],
		)
	}
	sources = [("Subcontracting Order", {s: s for s in sco_names})]
	if mip_to_sco:
		sources.append(("Material Issue Plan", mip_to_sco))

	for parenttype, parent_to_sco in sources:
		for w in frappe.get_all(
			"SCO Drawing Item",
			filters={"parent": ["in", list(parent_to_sco)], "parenttype": parenttype},
			fields=["parent", "drawing", "customer_weight_kg", "total_weight_kg",
					"transferred_weight_kg", "excess_weight_kg", "qty_to_manufacture",
					"completed_qty_nos"],
		):
			if not w.drawing:
				continue
			key = (parent_to_sco[w.parent], w.drawing)
			weights[key] = w
			if parenttype == "Subcontracting Order":
				completed[key] = w

	# Sec Nos (piece counts) alongside the weights. No drawing-level table holds
	# these -- Sec Qty lives only on the individual raw-material rows -- so they are
	# aggregated per DUNO/Mark No from the Material Issue Plan's own rows.
	#
	# Issued Sec Nos is derived rather than stored, scaling each row's Sec Qty by the
	# share of its Kg that actually shipped. That is what makes fractional rows add
	# up: where two drawings each hold part of one physical piece (0.098 and 0.102 of
	# it), the pieces they were issued come to 0.49 and 0.51 -- one whole piece
	# between them, which is exactly what left the rack. Issued can legitimately
	# exceed planned, since Sec Nos rounded up at transfer is the normal case and the
	# surplus is booked as excess to return.
	for r in frappe.get_all(
		"Material Issue Plan Raw Material",
		filters={"parent": ["in", list(mip_to_sco)]} if mip_to_sco else {"parent": ["in", []]},
		fields=["parent", "duno_mark_no", "sec_qty", "qty", "transferred_qty"],
	):
		key = (mip_to_sco[r.parent], r.duno_mark_no or "")
		agg = sec_nos.setdefault(key, {"planned": 0.0, "issued": 0.0})
		agg["planned"] += flt(r.sec_qty)
		if flt(r.qty):
			agg["issued"] += flt(r.sec_qty) * flt(r.transferred_qty) / flt(r.qty)

	return weights, sec_nos, completed


def _mip_by_sco(sco_names):
	if not sco_names:
		return {}
	out = {}
	for m in frappe.get_all("Material Issue Plan",
							filters={"subcontracting_order": ["in", sco_names]},
							fields=["name", "subcontracting_order"]):
		out.setdefault(m.subcontracting_order, []).append(m.name)
	return out


def _excess_by_sco(mip_by_sco):
	"""Excess booked, excess actually returned, and what is still out there.

	These are job-level rather than drawing-level, and deliberately so: the off-cut a
	transfer leaves over belongs to a batch, not to a drawing, and the excess rows the
	transfer popup writes carry no DUNO to attribute it back with. The same three
	figures therefore repeat on every drawing row of the job -- read them once per job.

	Billed-to-Consume comes off the difference rather than sitting in it forever. That
	material is scrapped by decision, not awaiting collection, which is the same line
	the Excess Material Return Report draws when it builds its chase-list."""
	out = {}
	all_mips = [m for names in mip_by_sco.values() for m in names]
	if not all_mips:
		return out

	rows_by_mip = {}
	for r in frappe.get_all(
		"SCO Excess Material Item",
		filters={"parent": ["in", all_mips], "parenttype": "Material Issue Plan"},
		fields=["parent", "qty", "stock_entry_created"],
	):
		rows_by_mip.setdefault(r.parent, []).append(r)

	for sco, mips in mip_by_sco.items():
		excess = returned = 0.0
		for mip in mips:
			for r in rows_by_mip.get(mip, []):
				excess += flt(r.qty)
				if r.stock_entry_created:
					returned += flt(r.qty)
		out[sco] = {
			"excess": excess,
			"returned": returned,
			# Declared excess that has not come back. Billed-to-Consume used to be
			# subtracted here as a third category; it is gone -- material that does
			# not return is now Process Loss, declared with a reason on the plan.
			"difference": excess - returned,
		}
	return out


def _consumables_by_sco(sco_names, production_plans):
	"""Consumables issued against the job -- welding rods, paint, gas.

	Read from submitted Stock Entries of type "Material Consumption for Manufacture",
	counting only the rows actually marked as consumables. Ticking Consumable Entry on
	such a Stock Entry marks every row for you, so in practice that is all of them; the
	flag matters on an entry somebody built by hand and only partly consumable.

	Job-level, like the excess figures, and repeated on the job's drawing rows: the
	entry names the job through Sales Order and Production Plan and does not say which
	drawing burnt the rod."""
	out = {}
	plans = [p for p in (production_plans or []) if p]
	if not (sco_names or plans):
		return out

	or_filters = []
	if sco_names:
		or_filters.append(["custom_sco_ref", "in", sco_names])
		or_filters.append(["subcontracting_order", "in", sco_names])
	if plans:
		or_filters.append(["custom_consumable_production_plan", "in", plans])

	entries = frappe.get_all(
		"Stock Entry",
		filters={"docstatus": 1, "stock_entry_type": CONSUMPTION_ENTRY_TYPE},
		or_filters=or_filters,
		fields=["name", "custom_sco_ref", "subcontracting_order", "custom_consumable_production_plan"],
	)
	if not entries:
		return out

	sco_by_plan = {}
	if plans and sco_names:
		for m in frappe.get_all("Material Issue Plan",
								filters={"subcontracting_order": ["in", sco_names]},
								fields=["subcontracting_order", "production_plan"]):
			if m.production_plan:
				sco_by_plan[m.production_plan] = m.subcontracting_order

	sco_by_entry = {}
	for e in entries:
		sco = e.custom_sco_ref or e.subcontracting_order or sco_by_plan.get(e.custom_consumable_production_plan)
		if sco:
			sco_by_entry[e.name] = sco
	if not sco_by_entry:
		return out

	for row in frappe.get_all(
		"Stock Entry Detail",
		filters={"parent": ["in", list(sco_by_entry)], "custom_is_consumable": 1},
		fields=["parent", "qty", "amount"],
	):
		agg = out.setdefault(sco_by_entry[row.parent], {"nos": 0.0, "cost": 0.0})
		agg["nos"] += flt(row.qty)
		agg["cost"] += flt(row.amount)
	return out


def _rm_cost_by_drawing(sco_names, mip_by_sco):
	"""What the raw material issued to each drawing was worth, from the Stock Entries
	that issued it -- the valuation the stock ledger itself used, not a recalculation.

	Not attributed by the drawing stamped on the Stock Entry row. A transfer consolidates
	every requirement for one item and batch into a single line, and that line can only
	carry one drawing: on SC-ORD-2026-00003 the whole 285.484 Kg of ISA100 is stamped
	1B6, when 1B1 and 1B2 take 81.056 Kg of it each. Costing by that stamp would hand
	one drawing the entire bill and the other four nothing.

	So the line's value is priced per Kg and spread back over the Material Issue Plan's
	own raw-material rows, in proportion to what each actually took -- the same rows, and
	the same weighting, that _apply_transfer_excess_to_raw_materials uses to split a
	transfer's rounding surplus.

	The stamp is still the fallback, for a Stock Entry raised outside the plan: there is
	nothing else to go on there, and one named drawing beats none."""
	if not sco_names:
		return {}
	entries = frappe.get_all(
		"Stock Entry",
		filters={"docstatus": 1},
		or_filters=[["custom_sco_ref", "in", sco_names], ["subcontracting_order", "in", sco_names]],
		fields=["name", "custom_sco_ref", "subcontracting_order"],
	)
	if not entries:
		return {}
	sco_by_entry = {e.name: (e.custom_sco_ref or e.subcontracting_order) for e in entries}

	rows = frappe.get_all(
		"Stock Entry Detail",
		filters={"parent": ["in", list(sco_by_entry)]},
		fields=["parent", "item_code", "batch_no", "qty", "amount", "basic_rate",
				"valuation_rate", "custom_drawing"],
	)
	if not rows:
		return {}

	# Price per Kg for each item and batch the job moved, so the cost can follow the
	# requirement rather than the consolidated line.
	rate = {}
	stamped = {}
	for r in rows:
		sco = sco_by_entry[r.parent]
		if flt(r.qty):
			key = (sco, r.item_code, r.batch_no or "")
			per_kg = flt(r.amount) / flt(r.qty) if flt(r.amount) else flt(r.basic_rate) or flt(r.valuation_rate)
			if per_kg:
				rate[key] = per_kg
		if r.custom_drawing:
			k = (sco, r.custom_drawing)
			stamped[k] = flt(stamped.get(k, 0)) + flt(r.amount)

	drawing_by_duno = {}
	for w in frappe.get_all("SCO Drawing Item",
							filters={"parent": ["in", sco_names], "parenttype": "Subcontracting Order"},
							fields=["parent", "drawing", "duno_mark_no"]):
		if w.drawing:
			drawing_by_duno[(w.parent, w.duno_mark_no or "")] = w.drawing

	mip_to_sco = {m: sco for sco, mips in (mip_by_sco or {}).items() for m in mips}
	out = {}
	priced = set()
	if mip_to_sco:
		for r in frappe.get_all(
			"Material Issue Plan Raw Material",
			filters={"parent": ["in", list(mip_to_sco)]},
			fields=["parent", "item_code", "planned_item", "batch_no", "duno_mark_no", "transferred_qty"],
		):
			sco = mip_to_sco[r.parent]
			# The batch's own item is what the transfer line carries, which is not the
			# requirement's item wherever an alternate was issued against it.
			item = r.planned_item or r.item_code
			per_kg = rate.get((sco, item, r.batch_no or ""))
			if not per_kg or not flt(r.transferred_qty):
				continue
			drawing = drawing_by_duno.get((sco, r.duno_mark_no or ""))
			if not drawing:
				continue
			out[(sco, drawing)] = flt(out.get((sco, drawing), 0)) + flt(r.transferred_qty) * per_kg
			priced.add((sco, item, r.batch_no or ""))

	# Anything the plan did not account for keeps the stamp it was given.
	for (sco, drawing), amount in stamped.items():
		if (sco, drawing) in out:
			continue
		out[(sco, drawing)] = flt(out.get((sco, drawing), 0)) + amount

	return {k: flt(v, 2) for k, v in out.items()}


def get_columns(operations):
	columns = [
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 130},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 140},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 110},
		{"label": _("Production Plan (Team)"), "fieldname": "production_plan", "fieldtype": "Link", "options": "Production Plan", "width": 150},
		{"label": _("Job Type"), "fieldname": "job_type", "fieldtype": "Data", "width": 110},
		{"label": _("Job Work Order"), "fieldname": "subcontracting_order", "fieldtype": "Link", "options": "Subcontracting Order", "width": 150},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 140},
		{"label": _("Drawing"), "fieldname": "drawing", "fieldtype": "Link", "options": "Drawing", "width": 130},
		{"label": _("DUNO/Mark No"), "fieldname": "duno_mark_no", "fieldtype": "Data", "width": 110},
		{"label": _("Cust Drawing No"), "fieldname": "customer_drawing_number", "fieldtype": "Data", "width": 150},
		# Taken from the Job Work Order rather than from the operation entry: the date
		# people mean by "when was this job raised" is the order's own date, and it is
		# the same on every operation of it.
		{"label": _("Created On"), "fieldname": "created_on", "fieldtype": "Date", "width": 100,
		 "description": _("Date of the Job Work Order this drawing belongs to.")},
	]

	# One block per operation, in sequence order. Everything an operation has to say
	# about a drawing sits together under that operation's name, so reading across the
	# row walks the job forward in the order it actually runs.
	for op in operations:
		label = op["operation"]
		columns += [
			{"label": "%s (%s)" % (label, op["unit"]), "fieldname": "op_%s_qty" % op["slug"],
			 "fieldtype": "Float", "precision": 3, "width": 140,
			 "description": _("Kg issued at this operation.") if op["unit"] == _("Kg")
			 else _("Pieces completed at this operation.")},
			{"label": _("{0} Status").format(label), "fieldname": "op_%s_status" % op["slug"],
			 "fieldtype": "Data", "width": 110},
			{"label": _("{0} Inspection Rounds").format(label), "fieldname": "op_%s_rounds" % op["slug"],
			 "fieldtype": "Int", "width": 130},
			{"label": _("{0} Last Inspection Status").format(label), "fieldname": "op_%s_inspection" % op["slug"],
			 "fieldtype": "Data", "width": 150},
			{"label": _("{0} Gap (Days, approx.)").format(label), "fieldname": "op_%s_gap" % op["slug"],
			 "fieldtype": "Int", "width": 140,
			 "description": _("Days between the previous operation being raised and this one.")},
		]

	columns += [
		# Drawing-level weights. Sec Nos sit beside the weight they belong to -- the two
		# are read together, and a weight without its piece count has repeatedly been the
		# thing that hides a problem (a rounded-up transfer looks identical in Kg terms
		# until you see Nos).
		{"label": _("Customer Weight (Kg)"), "fieldname": "customer_weight_kg", "fieldtype": "Float", "width": 130},
		{"label": _("Planned Weight (Kg)"), "fieldname": "planned_weight_kg", "fieldtype": "Float", "width": 130},
		{"label": _("Planned Sec Nos"), "fieldname": "planned_sec_nos", "fieldtype": "Float", "precision": 3, "width": 120},
		# Closes the planned block: the one number that says whether the plan is sane
		# before anybody looks at what was actually transferred.
		{"label": _("Waste %"), "fieldname": "waste_pct", "fieldtype": "Float", "precision": 2, "width": 90,
		 "description": _("Planned Weight over Customer Weight. A few percent is the off-cut; "
						  "negative means the plan holds less material than the part weighs.")},
		{"label": _("Transferred Weight (Kg)"), "fieldname": "transferred_weight_kg", "fieldtype": "Float", "width": 145},
		{"label": _("Transferred Sec Nos"), "fieldname": "transferred_sec_nos", "fieldtype": "Float", "precision": 3, "width": 140},
		{"label": _("Consumed RM Cost"), "fieldname": "consumed_rm_cost", "fieldtype": "Currency", "width": 140,
		 "description": _("Value of the raw material issued to this drawing, from the Stock Entries that issued it.")},
		{"label": _("Rate Schedule"), "fieldname": "rate_schedule", "fieldtype": "Link", "options": "Rate Schedule", "width": 130},
		{"label": _("Rate / Kg"), "fieldname": "rate_per_kg", "fieldtype": "Currency", "width": 100,
		 "description": _("The job-work rate on this drawing's Rate Schedule.")},
		{"label": _("Consumables (Nos)"), "fieldname": "consumables_nos", "fieldtype": "Float", "precision": 3, "width": 130,
		 "description": _("Job-level. From Material Consumption for Manufacture Stock Entries, repeated on every drawing row of the job.")},
		{"label": _("Consumable Cost"), "fieldname": "consumable_cost", "fieldtype": "Currency", "width": 130,
		 "description": _("Job-level. Value of those same consumable rows.")},
		{"label": _("Excess Weight (Kg)"), "fieldname": "excess_weight_kg", "fieldtype": "Float", "precision": 3, "width": 130,
		 "description": _("Job-level. Excess booked by the Material Issue Plan transfer popup.")},
		{"label": _("Returned Excess Weight (Kg)"), "fieldname": "returned_excess_kg", "fieldtype": "Float", "precision": 3, "width": 160,
		 "description": _("Job-level. The part of it already brought back in by a Return Excess Entry.")},
		{"label": _("Difference (Kg)"), "fieldname": "excess_difference_kg", "fieldtype": "Float", "precision": 3, "width": 120,
		 "description": _("Excess less what has come back -- what is still out there, waiting to return or to be written off as process loss.")},
		{"label": _("Completed Drawing Weight (Kg)"), "fieldname": "completed_drawing_weight_kg", "fieldtype": "Float", "precision": 3, "width": 175,
		 "description": _("Completed pieces valued at the drawing's own weight per piece.")},
		{"label": _("Completed Drawing (Nos)"), "fieldname": "completed_nos", "fieldtype": "Float", "precision": 3, "width": 150},
	]
	return columns
