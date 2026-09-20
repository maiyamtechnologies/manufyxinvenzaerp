from frappe import _


def get_data():
	"""Connections panel: every Stock Entry this plan issued.

	A plan can produce half a dozen of them -- the transfer to the supplier, the leg
	to the CNC warehouse and its forward, the excess return Repack, the process-loss
	write-off and the final Manufacture entry -- and until now the only way to find
	them was to filter the Stock Entry list by Material Issue Plan by hand.

	Keyed on custom_mip_ref, which every entry created from a plan carries (see the
	dual-write in material_issue_plan_transfer)."""
	return {
		"fieldname": "custom_mip_ref",
		"transactions": [
			{"label": _("Stock Movement"), "items": ["Stock Entry"]},
		],
	}
