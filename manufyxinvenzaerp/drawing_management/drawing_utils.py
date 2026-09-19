import frappe
from frappe import _
from frappe.utils import flt
from manufyxinvenzaerp.utils.dimension_formula import calculate_qty




@frappe.whitelist()
def mark_as_final_revision(drawing_name):
    """Set Drawing status to Final Revision. Only valid for submitted Working drawings."""
    doc = frappe.get_doc("Drawing", drawing_name)
    if doc.docstatus != 1:
        frappe.throw(_("Drawing must be submitted to mark as Final Revision."))
    if doc.status != "Working":
        frappe.throw(
            _("Cannot mark as Final Revision — current status is '{0}'.").format(doc.status)
        )
    frappe.db.set_value("Drawing", drawing_name, "status", "Final Revision")
    return "Final Revision"


@frappe.whitelist()
def create_revision(drawing_name):
    """Cancel a submitted drawing and open its next revision as a draft.

    Revising a drawing is cancel-then-amend, and doing it by hand is where it comes
    apart. Frappe sees the Sales Order pointing at the drawing, walks on to everything
    else that order points at, and offers to "Cancel All Documents" -- which on an order
    with twenty-one drawings means cancelling twenty-one drawings to revise one. Anybody
    who reads that dialog quickly has just lost the whole order.

    So the cancel is done here with the link check turned off, which is safe for the one
    reason that matters: the link the check is objecting to is the Sales Order DUNO row,
    and this drawing's own on_cancel releases that row itself (_release_sales_order_row).
    Nothing is left pointing at a cancelled drawing.

    The draft that comes back carries amended_from, so before_insert gives it the next
    rev_no and Working status. Its Sales Order row stays empty until it is submitted --
    a draft should not stand in for a submitted drawing -- and submitting it re-attaches
    the row (_link_to_sales_order_row takes over a row whose drawing is the one it was
    amended from).

    A BOM already built against the old revision is left alone. It belongs to that
    revision, and the new one starts without one -- so Create BOM offers itself again
    once the revision is marked Final."""
    doc = frappe.get_doc("Drawing", drawing_name)
    doc.check_permission("cancel")

    if doc.docstatus == 2:
        # Almost always because somebody pressed the button twice. Say where the
        # revision went rather than just refusing -- the second press is a person
        # looking for the draft the first press made.
        existing = frappe.db.get_value(
            "Drawing", {"amended_from": drawing_name, "docstatus": ["<", 2]}, "name"
        )
        if existing:
            frappe.throw(
                _("Drawing {0} has already been revised. Its revision is {1}.").format(
                    drawing_name, frappe.utils.get_link_to_form("Drawing", existing)),
                title=_("Already Revised"),
            )
        frappe.throw(
            _("Drawing {0} is cancelled. Amend it to carry on.").format(drawing_name))
    if doc.docstatus != 1:
        frappe.throw(_("Only a submitted drawing can be revised. This one is still a draft."))

    doc.flags.ignore_links = True
    doc.cancel()

    revision = frappe.copy_doc(doc)
    revision.amended_from = doc.name
    revision.docstatus = 0
    revision.insert(ignore_permissions=True)

    return revision.name


@frappe.whitelist()
def get_batches_for_drawing_item(doctype, txt, searchfield, start, page_len, filters):
    """Return batches with available stock qty for a given item_code."""
    item_code = (
        filters if isinstance(filters, dict) else frappe.parse_json(filters)
    ).get("item_code")
    if not item_code:
        return []
    return frappe.db.sql(
        """
        SELECT
            b.name,
            COALESCE(SUM(sle.actual_qty), 0) AS available_qty,
            b.custom_thickness,
            b.custom_length,
            b.custom_width
        FROM `tabBatch` b
        LEFT JOIN `tabStock Ledger Entry` sle
            ON sle.batch_no = b.name
            AND sle.item_code = %s
            AND sle.is_cancelled = 0
        WHERE b.item = %s
            AND (b.name LIKE %s OR b.batch_id LIKE %s)
            AND COALESCE(b.disabled, 0) = 0
        GROUP BY b.name
        ORDER BY b.name
        LIMIT %s OFFSET %s
        """,
        (item_code, item_code, f"%{txt}%", f"%{txt}%", int(page_len), int(start)),
    )


@frappe.whitelist()
def create_bom_from_drawing(drawing_name):
    drawing = frappe.get_doc("Drawing", drawing_name)
    if drawing.docstatus != 1 or drawing.status != "Final Revision":
        frappe.throw(_("BOM can only be created from a submitted Final Revision drawing."))

    existing_bom = frappe.db.get_value(
        "BOM", {"custom_drawing": drawing_name, "docstatus": ["!=", 2]}, "name"
    )
    if existing_bom:
        frappe.msgprint(
            _("A BOM already exists for this Drawing: {0}. Creating another one.").format(existing_bom),
            indicator="orange",
        )

    company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )

    # The BOM is in Kg like every other finished-goods document (sep14 FG plan, D12):
    # its quantity is the drawing's Cust Weight (Total), and the piece count rides
    # along as Qty (Nos). Every consumer scales by a ratio against this quantity, so
    # raw material per Kg planned stays right; the ones that plan in pieces
    # (Material Planning) scale against Qty (Nos) instead.
    cust_total = flt(drawing.customer_provided_wt, 3)
    drawing_nos = flt(drawing.no_of_qty_to_manufacture)
    if not cust_total or not drawing_nos:
        frappe.throw(
            _("Drawing {0} has no {1}. Set it with Update Customer Weight before creating the BOM, "
              "because the BOM quantity is the Cust Weight (Total) in Kg.").format(
                drawing_name,
                _("Cust Weight (Total)") if not cust_total else _("No of Qty to Manufacture")),
            title=_("Customer Weight Missing"),
        )

    bom = frappe.new_doc("BOM")
    bom.item = drawing.fg_item_code
    bom.item_name = drawing.fg_item_name
    bom.quantity = cust_total
    bom.custom_sec_qty = drawing_nos
    bom.custom_sec_uom = "Nos"
    bom.custom_cust_weight_total = cust_total
    bom.custom_cust_weight_per_nos = flt(drawing.get("weight_per_pcs"), 3) or flt(cust_total / drawing_nos, 3)
    bom.custom_drawing = drawing_name
    bom.custom_duno_mark_no = drawing.duno_mark_no or 0
    bom.custom_customer_drawing_number = drawing.customer_drawing_number or ""
    # Seeded from the drawing rather than left blank and synced later. The sync in
    # rate_schedule_sync.py only fires on an actual EDIT, so a BOM born blank would
    # stay blank until somebody typed the schedule it already implicitly has. The
    # fetch_from fields (custom_rs_*) fill themselves in on insert.
    bom.custom_rate_schedule = drawing.rate_schedule or ""
    bom.project = drawing.project or ""
    bom.company = company
    bom.currency = (
        frappe.db.get_value("Company", company, "default_currency") if company else "INR"
    )
    bom.rm_cost_as_per = "Valuation Rate"

    for d_item in drawing.items:
        bom.append(
            "items",
            {
                "item_code": d_item.material_code,
                "item_name": d_item.material_name,
                "qty": flt(d_item.total_qty) or 0,
                "uom": d_item.uom,
                "custom_item_number": d_item.item_number,
                "custom_sales_order": drawing.sales_order or "",
                "custom_material_spec": d_item.material_spec,
                "custom_unit_weight": d_item.unit_weight,
                "custom_thickness": d_item.thickness,
                "custom_length": d_item.length,
                "custom_width": d_item.width,
                "custom_sec_qty": flt(d_item.total_sec_qty),
                "custom_sec_uom": d_item.sec_uom,
                "custom_parent_item_group": d_item.parent_item_group or "",
            },
        )

    bom.insert(ignore_permissions=True)
    return bom.name


def validate_bom_from_drawing(doc, method):
    if not doc.get("custom_drawing"):
        return

    drawing = frappe.get_doc("Drawing", doc.custom_drawing)
    drawing_map = {d.item_number: d for d in drawing.items if d.item_number}
    drawing_list = list(drawing.items)

    # Guard against actual row deletion (not item_number mismatch from type migrations)
    if len(doc.items) < len(drawing.items):
        frappe.throw(
            _("Not allowed to remove items from BOM. Please maintain all items as per Drawing.")
        )

    qty_warnings = []
    for i, bom_item in enumerate(doc.items):
        d_item = drawing_map.get(bom_item.get("custom_item_number")) or (
            drawing_list[i] if i < len(drawing_list) else None
        )
        if not d_item:
            continue

        bom_item.uom = d_item.uom
        bom_item.custom_item_number = d_item.item_number
        bom_item.custom_sales_order = drawing.sales_order or ""
        bom_item.custom_parent_item_group = d_item.parent_item_group or ""
        bom_item.custom_thickness = flt(d_item.thickness)
        bom_item.custom_length = flt(d_item.length)
        bom_item.custom_width = flt(d_item.width)
        bom_item.custom_unit_weight = flt(d_item.unit_weight)
        bom_item.custom_sec_qty = flt(d_item.total_sec_qty)
        bom_item.custom_sec_uom = d_item.sec_uom or ""

        drawing_qty = flt(d_item.total_qty)
        if drawing_qty and flt(bom_item.qty) != drawing_qty:
            qty_warnings.append(
                _("Row {0}: Quantity changed from {1} to {2} — restored from Drawing.").format(
                    bom_item.idx, flt(bom_item.qty), drawing_qty
                )
            )
            bom_item.qty = drawing_qty

    if qty_warnings:
        frappe.msgprint(
            _(
                "Not allowed to edit item details in BOM level. "
                "Kindly make corrections in Drawing master.<br><br>"
            )
            + "<br>".join(qty_warnings),
            title=_("BOM Items Restored from Drawing"),
            indicator="orange",
        )


@frappe.whitelist()
def create_production_plan_from_bom(bom_name):
    bom = frappe.get_doc("BOM", bom_name)
    if bom.docstatus != 1:
        frappe.throw(_("BOM must be submitted to create a Production Plan."))
    if not bom.get("custom_drawing"):
        frappe.throw(_("Production Plan creation is only available for BOMs linked to a Drawing."))

    stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or ""

    # Planned in pieces: the plan starts with every piece of the drawing no other
    # plan has claimed yet (D16), and its own validate (apply_fg_nos) turns the Nos
    # into Planned Qty (Kg) -- this sets Qty (Nos) only (D26).
    from manufyxinvenzaerp.production_plan_management.production_plan import (
        fg_nos_remaining,
    )

    nos_left = fg_nos_remaining(bom.custom_drawing)
    if nos_left <= 0:
        frappe.throw(
            _("Every piece of drawing {0} is already on a Production Plan. Reduce the Qty (Nos) "
              "on one of those plans, or cancel it, to plan pieces here.").format(bom.custom_drawing),
            title=_("Nothing Left to Plan"),
        )

    pp = frappe.new_doc("Production Plan")
    pp.custom_type = "Internal Job"
    pp.company = bom.company
    pp.posting_date = frappe.utils.today()
    pp.get_items_from = ""

    pp.append(
        "po_items",
        {
            "item_code": bom.item,
            "bom_no": bom_name,
            "custom_sec_qty": nos_left,
            "custom_sec_uom": "Nos",
            "planned_start_date": frappe.utils.now_datetime(),
            "stock_uom": stock_uom,
            "custom_drawing": bom.get("custom_drawing") or "",
            "custom_duno_mark_no": bom.get("custom_duno_mark_no") or 0,
        },
    )

    # Auto-populate Process Planning from BOM routing or BOM operations
    operations = []
    if bom.routing:
        operations = frappe.get_all(
            "BOM Operation",
            filters={"parent": bom.routing, "parenttype": "Routing"},
            fields=["operation", "sequence_id"],
            order_by="sequence_id asc",
        )
    elif bom.with_operations and bom.operations:
        operations = [
            {"operation": op.operation, "sequence_id": op.sequence_id}
            for op in sorted(bom.operations, key=lambda o: o.sequence_id or 0)
        ]

    for op in operations:
        pp.append("custom_process_planning", {
            "operation_name": op.get("operation"),
            "work_type": "Internal Jobcard",
        })

    pp.insert(ignore_permissions=True)
    return pp.name


@frappe.whitelist()
def parse_drawing_items_csv(csv_content):
	"""Parse CSV text and return processed Drawing Item rows.

	Expected columns (order-independent, case-insensitive):
	  item_number, material_code, sec_qty, thickness, length, width

	Fetches item master data and calculates qty server-side so the client
	only needs to set_value on each child row.
	"""
	import csv as csv_module
	import io

	if not csv_content or not csv_content.strip():
		frappe.throw(_("The uploaded CSV file is empty."))

	# Strip BOM character that Excel sometimes adds
	csv_content = csv_content.lstrip("﻿")

	reader = csv_module.DictReader(io.StringIO(csv_content))

	# Normalise headers: lowercase + strip whitespace so both "material_code"
	# and "Material Code" (or "item_code" from PO-style CSVs) are accepted.
	if not reader.fieldnames:
		frappe.throw(_("CSV file has no header row."))

	normalised_headers = {h.strip().lower(): h for h in reader.fieldnames}

	def _col(row, *candidates):
		"""Return value of first matching column (case-insensitive)."""
		for c in candidates:
			orig = normalised_headers.get(c.lower())
			if orig and orig in row:
				val = (row[orig] or "").strip()
				if val:
					return val
		return ""

	rows = []
	errors = []
	auto_number = 1

	for line_no, row in enumerate(reader, start=2):
		material_code = _col(row, "material_code", "item_code")
		if not material_code:
			continue  # blank rows are silently skipped

		if not frappe.db.exists("Item", material_code):
			errors.append(_("Row {0}: Item <b>{1}</b> not found.").format(line_no, material_code))
			continue

		item_data = frappe.db.get_value(
			"Item",
			material_code,
			[
				"item_name", "item_group", "description",
				"custom_material_spec", "custom_unit_weight",
				"custom_secondary_uom", "custom_parent_item_group", "stock_uom",
			],
			as_dict=True,
		) or {}

		def _flt(val):
			try:
				return flt(str(val).strip().replace(",", ""))
			except Exception:
				return 0.0

		raw_item_number = _col(row, "item_number", "item no", "item no.")
		item_number = str(raw_item_number).strip() if raw_item_number else str(auto_number)
		sec_qty   = _flt(_col(row, "sec_qty",   "sec qty",   "custom_sec_qty"))
		thickness = _flt(_col(row, "thickness",  "thickness (mm)", "custom_thickness"))
		length    = _flt(_col(row, "length",     "length (mm)",    "custom_length"))
		width     = _flt(_col(row, "width",      "width (mm)",     "custom_width"))

		unit_weight        = flt(item_data.get("custom_unit_weight"))
		parent_item_group  = (item_data.get("custom_parent_item_group") or "").strip()

		# Calculate primary qty using the same formula as drawing.py
		qty = 0.0
		if parent_item_group in ("Structurals", "Plates"):
			calc = calculate_qty(parent_item_group, length, width, thickness, unit_weight, sec_qty)
			if calc is not None:
				qty = calc

		rows.append({
			"item_number":           item_number,
			"material_code":         material_code,
			"material_name":         item_data.get("item_name") or "",
			"item_group":            item_data.get("item_group") or "",
			"parent_item_group":     parent_item_group,
			"raw_material_description": item_data.get("description") or "",
			"material_spec":         item_data.get("custom_material_spec") or "",
			"unit_weight":           unit_weight,
			"thickness":             thickness,
			"length":                length,
			"width":                 width,
			"sec_qty":               sec_qty,
			"sec_uom":               item_data.get("custom_secondary_uom") or "",
			"qty":                   flt(qty, 3),
			"uom":                   item_data.get("stock_uom") or "",
		})
		auto_number += 1

	if errors:
		frappe.throw("<br>".join(errors), title=_("CSV Upload Errors"))

	if not rows:
		frappe.throw(_("No valid item rows found in the CSV file."))

	return rows


def get_so_dashboard_data(data):
    """Extend Sales Order dashboard to include Drawing connections."""
    from frappe import _

    data["transactions"].append({"label": _("Drawing"), "items": ["Drawing"]})
    return data


@frappe.whitelist()
def update_customer_provided_weight(drawing_name, new_weight_per_nos):
    """Change a drawing's customer weight from the Drawing's popup (sep14 FG plan, D15).

    The popup takes the weight of ONE piece, because that is the figure the customer
    states; Cust Weight (Total) = per Nos x No of Qty to Manufacture is worked out
    here. Both are written to the Drawing and to its Sales Order Drawing List row --
    the only way either changes once the row has a drawing (D24) -- and the Total,
    with per Nos alongside, is cascaded into every document already made from it.

    The Sales Order row is written directly rather than by saving the order: nothing
    the order recalculates on save depends on the customer weight, and the Drawing
    List lock refuses a changed weight on a row that already has a drawing -- this
    function is the one sanctioned way past it.

    The change log keeps the old and new Total, which is what every other document
    carries. Batch reallocation/unreserve stays a manual step -- this only updates
    the numbers."""
    per_nos = flt(new_weight_per_nos, 3)
    if per_nos <= 0:
        frappe.throw(_("Enter the weight of one piece, in Kg."))

    doc = frappe.get_doc("Drawing", drawing_name)
    if doc.docstatus == 2:
        frappe.throw(_("Drawing {0} is cancelled. Update the weight on its current revision.").format(drawing_name))
    nos = flt(doc.no_of_qty_to_manufacture)
    if not nos:
        frappe.throw(_("Drawing {0} has no No of Qty to Manufacture, so there is no Total to work out.").format(drawing_name))

    old_per_nos = flt(doc.get("weight_per_pcs"), 3)
    old_total = flt(doc.customer_provided_wt, 3)
    new_total = flt(per_nos * nos, 3)
    if per_nos == old_per_nos and new_total == old_total:
        frappe.throw(_("New weight is the same as the current value ({0} Kg per Nos).").format(old_per_nos))

    doc.append("weight_change_log", {
        "old_weight": old_total,
        "new_weight": new_total,
        "changed_by": frappe.session.user,
        "changed_on": frappe.utils.now_datetime(),
    })
    doc.weight_per_pcs = per_nos
    doc.customer_provided_wt = new_total
    doc.save(ignore_permissions=True)

    from manufyxinvenzaerp.drawing_management.doctype.drawing.drawing import _touch_sales_order
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        _update_so_difference_kg_for_pair,
    )

    duno_rows = frappe.get_all(
        "Sales Order DUNO Item",
        filters={"drawing": drawing_name},
        fields=["name", "parent", "duno_mark_no"],
    )
    sales_orders = []
    for row in duno_rows:
        frappe.db.set_value(
            "Sales Order DUNO Item", row.name,
            {"weight_per_pcs": per_nos, "total_weight": new_total},
            update_modified=False,
        )
        _update_so_difference_kg_for_pair(row.parent, row.duno_mark_no)
        if row.parent not in sales_orders:
            sales_orders.append(row.parent)
    for so in sales_orders:
        _touch_sales_order(so)

    cascade = _cascade_customer_weight(drawing_name, new_total, per_nos)
    frappe.db.commit()

    return {
        "old_weight_per_nos": old_per_nos,
        "new_weight_per_nos": per_nos,
        "old_weight": old_total,
        "new_weight": new_total,
        "nos": nos,
        "sales_order_updated": bool(duno_rows),
        "sales_order_lines": _so_line_differences(sales_orders, doc.fg_item_code),
        **cascade,
    }


def _so_line_differences(sales_orders, fg_item):
    """Ordered vs drawings for the finished-goods line a changed drawing belongs to.

    A new customer weight moves the Drawing List total away from what the line was
    ordered at. That is expected -- the order was taken on an estimate -- so it is
    reported, not blocked (D15); the popup shows it in orange."""
    out = []
    for so in sales_orders:
        ordered = frappe.db.sql(
            """SELECT COALESCE(SUM(qty), 0), COALESCE(SUM(custom_sec_qty), 0)
               FROM `tabSales Order Item` WHERE parent = %s AND item_code = %s""",
            (so, fg_item),
        )[0]
        drawn = frappe.db.sql(
            """SELECT COALESCE(SUM(total_weight), 0), COALESCE(SUM(total_quantity), 0)
               FROM `tabSales Order DUNO Item` WHERE parent = %s AND item = %s""",
            (so, fg_item),
        )[0]
        out.append({
            "sales_order": so,
            "item_code": fg_item,
            "ordered_kg": flt(ordered[0], 3),
            "drawings_kg": flt(drawn[0], 3),
            "difference_kg": flt(flt(drawn[0]) - flt(ordered[0]), 3),
            "ordered_nos": flt(ordered[1], 3),
            "drawings_nos": flt(drawn[1], 3),
            "difference_nos": flt(flt(drawn[1]) - flt(ordered[1]), 3),
        })
    return out


def _cascade_customer_weight(drawing_name, new_total, per_nos=None):
    """Push the drawing's new customer weight into every document already made from it.

    What travels is the Total -- all pieces of the drawing (D2, D30) -- with per Nos
    alongside, to Production Plan Items, SCO Drawing Items (Job Work Order and
    Material Issue Plan), Operation Entry drawing rows and the BOM. Work Order is
    intentionally not included (D19).

    The Kg that depends on it moves too, where the document is still a draft:
      - a draft Production Plan's Planned Qty (Kg) = Total x its Nos / drawing Nos;
      - a draft Job Work Order recomputes its Kg, job work amount and rate (R5);
      - the BOM's quantity IS the Total (D12), and every raw-material explosion is a
        ratio against it -- left at the old Total, a plan for 4 of 10 pieces would
        draw 4 x 31 / 300 of the material instead of 4/10.
    A submitted Job Work Order keeps its qty and amount and is listed in the result,
    so the user can decide whether to amend it.

    Operation Entry rows on submitted and cancelled entries are updated too,
    deliberately: the weight there is descriptive -- it drives no stock movement or
    costing -- and leaving a correction out would freeze the wrong number into the
    sheet the shop floor reads."""
    from manufyxinvenzaerp.production_plan_management.production_plan import (
        drawing_fg_weights, fg_kg_for_nos,
    )

    new_total = flt(new_total, 3)
    info = drawing_fg_weights(drawing_name)
    drawing_nos = flt(info.nos) if info else 0
    if per_nos is None:
        per_nos = info.per_nos if info else 0
    per_nos = flt(per_nos, 3)

    # ── Production Plan Items ──────────────────────────────────────────────
    pp_item_rows = frappe.db.sql(
        """SELECT ppi.name, ppi.parent, ppi.custom_sec_qty, pp.docstatus
           FROM `tabProduction Plan Item` ppi
           JOIN `tabProduction Plan` pp ON pp.name = ppi.parent
           WHERE ppi.custom_drawing = %s""",
        (drawing_name,), as_dict=True,
    )
    draft_pps = set()
    for row in pp_item_rows:
        values = {"custom_customer_weight_kg": new_total, "custom_cust_weight_per_nos": per_nos}
        if row.docstatus == 0 and flt(row.custom_sec_qty) > 0:
            kg = fg_kg_for_nos(new_total, row.custom_sec_qty, drawing_nos)
            values.update({"planned_qty": kg, "pending_qty": kg})
            draft_pps.add(row.parent)
        frappe.db.set_value("Production Plan Item", row.name, values, update_modified=False)
    for pp in draft_pps:
        total_planned = frappe.db.sql(
            "SELECT COALESCE(SUM(planned_qty), 0) FROM `tabProduction Plan Item` WHERE parent = %s", (pp,)
        )[0][0]
        frappe.db.set_value("Production Plan", pp, "total_planned_qty", flt(total_planned, 3), update_modified=False)

    # ── SCO Drawing Items: Job Work Order and Material Issue Plan ──────────
    drawing_item_rows = frappe.get_all(
        "SCO Drawing Item",
        filters={"drawing": drawing_name, "parenttype": ["in", ["Subcontracting Order", "Material Issue Plan"]]},
        fields=["name", "parent", "parenttype"],
    )
    for row in drawing_item_rows:
        frappe.db.set_value(
            "SCO Drawing Item", row.name,
            {"customer_weight_kg": new_total, "cust_weight_per_nos": per_nos},
            update_modified=False,
        )

    touched = {(r.parenttype, r.parent) for r in drawing_item_rows}
    mip_names, draft_jwos, submitted_jwos = [], [], []
    for parenttype, parent in sorted(touched):
        if parenttype == "Subcontracting Order":
            total = frappe.db.sql(
                "select sum(customer_weight_kg) from `tabSCO Drawing Item` "
                "where parenttype='Subcontracting Order' and parent=%s",
                (parent,),
            )[0][0]
            frappe.db.set_value("Subcontracting Order", parent, "custom_customer_weight_kg", flt(total, 3))
            docstatus = frappe.db.get_value("Subcontracting Order", parent, "docstatus")
            if docstatus == 0:
                if _recompute_draft_jwo_job_work(parent):
                    draft_jwos.append(parent)
            elif docstatus == 1:
                submitted_jwos.append(parent)
        elif parenttype == "Material Issue Plan":
            mip_names.append(parent)

    if mip_names:
        from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
            refresh_weight_summary,
        )
        for mip_name in mip_names:
            refresh_weight_summary(mip_name)

    # ── Operation Entry drawing rows ───────────────────────────────────────
    # Used to receive the per-piece figure while every other copy got the Total.
    soe_detail_rows = frappe.get_all(
        "SOE Drawing Detail",
        filters={"drawing": drawing_name, "parenttype": "Supplier Operation Entry"},
        fields=["name"],
    )
    for row in soe_detail_rows:
        frappe.db.set_value(
            "SOE Drawing Detail", row.name, "customer_provided_weight_kg", new_total,
            update_modified=False,
        )

    # ── BOM ────────────────────────────────────────────────────────────────
    boms = frappe.get_all(
        "BOM", filters={"custom_drawing": drawing_name, "docstatus": ["<", 2]},
        fields=["name", "quantity", "custom_sec_qty"],
    )
    for bom in boms:
        values = {"custom_cust_weight_total": new_total, "custom_cust_weight_per_nos": per_nos}
        # Only a BOM built in Kg (it carries Qty (Nos)) has the Total as its quantity.
        # One made before the change is in pieces and keeps them.
        if flt(bom.custom_sec_qty) and new_total:
            values["quantity"] = new_total
            # Per-unit consumption is stock_qty / quantity; keep it in step so nothing
            # reading it scales by the old Total.
            for child in ("BOM Item", "BOM Explosion Item"):
                frappe.db.sql(
                    f"UPDATE `tab{child}` SET qty_consumed_per_unit = stock_qty / %s "
                    "WHERE parent = %s AND parenttype = 'BOM'",
                    (new_total, bom.name),
                )
        frappe.db.set_value("BOM", bom.name, values, update_modified=False)

    return {
        "production_plan_items_updated": len(pp_item_rows),
        "draft_production_plans_recalculated": len(draft_pps),
        "drawing_rows_updated": len(drawing_item_rows),
        "subcontracting_orders_updated": len([1 for t, _p in touched if t == "Subcontracting Order"]),
        "draft_job_work_orders_recalculated": draft_jwos,
        "submitted_job_work_orders": submitted_jwos,
        "material_issue_plans_updated": len(mip_names),
        "operation_entry_rows_updated": len(soe_detail_rows),
        "boms_updated": len(boms),
    }


def _recompute_draft_jwo_job_work(sco_name):
    """A draft Job Work Order follows a new customer weight (R5).

    Each drawing row's Kg on the order is Total x its Nos / drawing Nos, its job work
    amount is that Kg x Rate / Kg, and the one item line carries the Kg, the amount
    and the weighted rate (D31, R3) -- the same sums the builder does. Only an order
    built in Kg (its item carries Qty (Nos)) is recomputed; an older one has pieces
    in qty and is left alone. Returns True when the order was recomputed."""
    from manufyxinvenzaerp.subcontracting_management.subcontracting import _job_work_figures

    items = frappe.get_all(
        "Subcontracting Order Item", filters={"parent": sco_name},
        fields=["name", "custom_sec_qty"],
    )
    if len(items) != 1 or not flt(items[0].custom_sec_qty):
        return False

    rows = frappe.get_all(
        "SCO Drawing Item",
        filters={"parent": sco_name, "parenttype": "Subcontracting Order"},
        fields=["name", "drawing", "qty_to_manufacture", "rate_per_kg"],
    )
    figures = _job_work_figures([
        frappe._dict(drawing=r.drawing, nos=r.qty_to_manufacture, rate_per_kg=r.rate_per_kg, name=r.name)
        for r in rows
    ])
    for r in figures.rows:
        frappe.db.set_value(
            "SCO Drawing Item", r.name,
            {"rate_per_kg": r.rate_per_kg, "job_work_amount": r.amount,
             "qty_to_manufacture_kg": r.kg},
            update_modified=False,
        )
    frappe.db.set_value(
        "Subcontracting Order Item", items[0].name,
        {"qty": figures.kg, "rate": figures.rate, "amount": figures.amount},
        update_modified=False,
    )
    frappe.db.set_value(
        "Subcontracting Order", sco_name, {"total_qty": figures.kg, "total": figures.amount},
        update_modified=False,
    )
    return True



#####################
