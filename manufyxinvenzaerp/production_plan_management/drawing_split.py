"""A drawing's pieces split over several Production Plans, and each plan's share of
its raw material.

A drawing of 5 NOS can be planned as 2 on one plan (one supplier) and 3 on another.
Material Planning reserves the drawing's raw material as ONE set of rows for all 5
pieces, and that is left exactly as it is. Each plan takes its share of every row
instead, in proportion to its pieces: 2 of 5 NOS takes 2/5 of every row's Kg and
pieces -- half a bar where a bar serves two halves. Rounding a fraction up to whole
pieces stays the user's call in the transfer popup, as for any other line.

The shares are slices of the drawing laid end to end, in the order the plans were
made: 2 of 5 on the first plan is [0, 2/5], the 3 on the second is [2/5, 1]. A
quantity x is divided as round(x * end) - round(x * start), so the slices of every
plan add back to x exactly -- no gram is lost to rounding or counted twice, however
many plans share the drawing.

Plans are read the same way as the picker's "already planned" count
(production_plan.fg_nos_planned_elsewhere): every Production Plan not cancelled,
by its Qty (Nos). A plan that holds the whole drawing has no slice, and everything
behaves exactly as before.
"""

import frappe
from frappe.utils import flt


def plan_drawing_slices(pp_name):
	"""{(material_planning, duno_mark_no): slice} for this plan's partly-planned drawings.

	A slice is a dict: start and end (fractions of the drawing), nos (this plan's
	pieces), total (the drawing's pieces) and plans (every plan sharing it, in order).
	Only drawings this plan holds PART of are returned; a row without a Material
	Planning, a DUNO or a Qty (Nos) keeps the whole drawing, as before.
	"""
	from manufyxinvenzaerp.production_plan_management.production_plan import drawing_fg_weights

	if not pp_name:
		return {}
	rows = frappe.get_all(
		"Production Plan Item",
		filters={"parent": pp_name, "custom_drawing": ["is", "set"]},
		fields=["custom_drawing", "custom_material_planning", "custom_duno_mark_no", "custom_sec_qty"],
	)
	nos_here = {}
	keys_by_drawing = {}
	for r in rows:
		if not (r.custom_material_planning and r.custom_duno_mark_no and flt(r.custom_sec_qty) > 0):
			continue
		nos_here[r.custom_drawing] = flt(nos_here.get(r.custom_drawing, 0) + flt(r.custom_sec_qty), 3)
		keys_by_drawing.setdefault(r.custom_drawing, set()).add(
			(r.custom_material_planning, r.custom_duno_mark_no))
	if not nos_here:
		return {}

	plans_by_drawing = _plans_in_order(list(nos_here))
	out = {}
	for drawing, nos in nos_here.items():
		info = drawing_fg_weights(drawing)
		total = flt(info.nos) if info else 0.0
		if total <= 0:
			continue
		plans = plans_by_drawing.get(drawing) or [(pp_name, nos)]
		before = 0.0
		for name, n in plans:
			if name == pp_name:
				break
			before += flt(n)
		start = min(flt(before / total, 9), 1.0)
		end = min(flt((before + nos) / total, 9), 1.0)
		if start <= 0 and end >= 1:
			continue  # the whole drawing -- nothing to divide
		sl = {"start": start, "end": end, "nos": nos, "total": total, "drawing": drawing,
		      "plans": [name for name, _n in plans]}
		for key in keys_by_drawing[drawing]:
			out[key] = sl
	return out


def mip_drawing_slices(mip):
	"""plan_drawing_slices for the Production Plan behind a Material Issue Plan."""
	return plan_drawing_slices(mip.get("production_plan")) if mip else {}


def slices_by_duno(slices, mp_name):
	"""{duno: slice} for one Material Planning, the shape the reserved-batch reader takes."""
	return {duno: sl for (mp, duno), sl in (slices or {}).items() if mp == mp_name}


def portion(value, sl):
	"""This plan's part of a whole-drawing quantity. The whole value when sl is None."""
	if not sl:
		return flt(value, 3)
	value = flt(value)
	return flt(flt(value * sl["end"], 3) - flt(value * sl["start"], 3), 3)


def share_label(sl):
	"""'2 of 5 NOS' -- how a plan's share is named in messages."""
	return "{0} of {1} NOS".format(_num(sl["nos"]), _num(sl["total"]))


def _num(value):
	text = ("%.3f" % flt(value, 3)).rstrip("0").rstrip(".")
	return text or "0"


def _plans_in_order(drawings):
	"""{drawing: [(plan, nos), ...]} over every plan not cancelled, oldest first.

	Oldest first is what makes a plan's slice stable: a newer plan is always laid
	after it, so creating one never moves the material of a plan already made."""
	rows = frappe.db.sql(
		"""
		SELECT ppi.custom_drawing AS drawing, pp.name AS pp, pp.creation,
		       SUM(IFNULL(ppi.custom_sec_qty, 0)) AS nos
		FROM `tabProduction Plan Item` ppi
		INNER JOIN `tabProduction Plan` pp ON pp.name = ppi.parent
		WHERE ppi.custom_drawing IN %(drawings)s AND pp.docstatus < 2
		GROUP BY ppi.custom_drawing, pp.name, pp.creation
		HAVING SUM(IFNULL(ppi.custom_sec_qty, 0)) > 0
		ORDER BY pp.creation, pp.name
		""",
		{"drawings": tuple(drawings)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.drawing, []).append((r.pp, flt(r.nos)))
	return out
