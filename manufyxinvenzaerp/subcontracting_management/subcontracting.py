from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, today


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard override
# ─────────────────────────────────────────────────────────────────────────────

def get_sco_dashboard_data(data):
    """Add Supplier Operation Entry to the Subcontracting Order dashboard."""
    data["transactions"].append({
        "label": _("Operations"),
        "items": ["Supplier Operation Entry"],
    })
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Whitelisted API functions
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def create_sco_from_production_plan(pp_name):
    """Create a Draft Subcontracting Order from a submitted Production Plan.
    Populates drawing items and total weight from Material Planning reservations.

    Subcontracting Order is the single production-execution doctype for all three
    Production Plan Types (Internal Job / Supplier Job / Supplier with Material) --
    Work Order is no longer created from Production Plan at all (client change
    request Phase 0.4/4.1). Process Planning rows can be Subcontractor and/or
    Internal Jobcard in any mix; Supplier Operation Entry is the universal
    one-row-per-operation execution document regardless of who performs it.
    """
    if not frappe.has_permission("Subcontracting Order", "create"):
        frappe.throw(_("Not permitted to create Subcontracting Orders"), frappe.PermissionError)

    existing = frappe.db.get_value(
        "Subcontracting Order", {"custom_production_plan": pp_name, "docstatus": ["!=", 2]}, "name"
    )
    if existing:
        frappe.throw(
            _(
                "A Subcontracting Order ({0}) already exists for this Production Plan. "
                "Open the existing Subcontracting Order from the connections panel."
            ).format(existing)
        )

    pp = frappe.get_doc("Production Plan", pp_name)

    all_ops = pp.custom_process_planning or []
    if not all_ops:
        frappe.throw(_("No operations found in the Process Planning table."))
    has_sub = any(r.work_type == "Subcontractor" for r in all_ops)
    if has_sub and not pp.custom_vendor_contractor:
        frappe.throw(_("Please set the Vendor/Contractor on the Production Plan before creating a Subcontracting Order."))

    wo_list = frappe.get_all("Work Order", filters={"production_plan": pp_name}, limit=1, pluck="name")
    wo_name = wo_list[0] if wo_list else None

    if wo_name:
        wo = frappe.get_doc("Work Order", wo_name)
        fg_item = wo.production_item
        fg_qty = wo.qty
        fg_warehouse = wo.fg_warehouse
        bom_no = wo.bom_no
    else:
        if not pp.po_items:
            frappe.throw(_("No items found in the Production Plan. Please add items to manufacture first."))
        pp_item = pp.po_items[0]
        fg_item = pp_item.item_code
        fg_qty = pp_item.planned_qty
        fg_warehouse = pp_item.warehouse or ""
        bom_no = pp_item.bom_no

    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )
    currency = (
        frappe.db.get_value("Company", company, "default_currency")
        or frappe.db.get_single_value("Global Defaults", "default_currency")
        or "INR"
    )
    uom = frappe.db.get_value("Item", fg_item, "stock_uom") or "Nos"

    # Build drawing items + weight summary from Material Planning reservations.
    # Per drawing: customer-provided weight, planned RM weight, mapped (actual
    # reserved batch) weight, and the over-mapped excess to be returned by the supplier.
    drawing_rows = []
    total_customer = total_planned = total_mapped = total_excess = 0.0
    _mapped_cache = {}   # mp_name -> {duno_mark_no: mapped_kg}
    _excess_cache = {}   # mp_name -> {duno_mark_no: excess_kg}
    _drawing_weight_cache = {}  # mp_name -> {duno_mark_no: planned_kg}
    for pi in pp.po_items:
        mp_name = pi.get("custom_material_planning")
        duno    = pi.get("custom_duno_mark_no") or ""

        if mp_name not in _mapped_cache:
            _mapped_cache[mp_name] = _get_mp_mapped_weight_by_duno(mp_name)
            _excess_cache[mp_name] = _get_mp_excess_by_duno(mp_name)
        if mp_name not in _drawing_weight_cache:
            _drawing_weight_cache[mp_name] = _get_mp_drawing_weights_by_duno(mp_name)

        if duno:
            planned = _drawing_weight_cache[mp_name].get(duno, 0.0)
            mapped = _mapped_cache[mp_name].get(duno, 0.0)
            excess = _excess_cache[mp_name].get(duno, 0.0)
        else:
            # No DUNO on the PP item — take the whole Material Planning's totals.
            planned = _get_mp_total_weight(mp_name)
            mapped = _get_mp_total_weight(mp_name)
            excess = sum(_excess_cache[mp_name].values())

        customer = flt(pi.get("custom_customer_weight_kg"), 3)
        total_customer += customer
        total_planned  += planned
        total_mapped   += mapped
        total_excess   += excess

        drawing_rows.append({
            "drawing": pi.get("custom_drawing"),
            "item_code": pi.item_code,
            "item_name": pi.get("item_name") or frappe.db.get_value("Item", pi.item_code, "item_name") or pi.item_code,
            "duno_mark_no": duno,
            "customer_drawing_number": pi.get("custom_customer_drawing_number"),
            "material_planning": mp_name,
            "customer_weight_kg": customer,
            "total_weight_kg": flt(planned, 3),
            "mapped_weight_kg": flt(mapped, 3),
            "excess_weight_kg": flt(excess, 3),
            "qty_to_manufacture": flt(pi.get("planned_qty"), 3),
        })

    sco = frappe.get_doc({
        "doctype": "Subcontracting Order",
        "company": company,
        "currency": currency,
        "conversion_rate": 1,
        "supplier": pp.custom_vendor_contractor or "",
        "schedule_date": today(),
        "items": [{
            "item_code": fg_item,
            "qty": flt(fg_qty) or 1,
            "uom": uom,
            "warehouse": fg_warehouse or "",
            "bom": bom_no,
            "rate": 0,
            "subcontracting_conversion_factor": 1,
        }],
        "custom_production_plan": pp_name,
        "custom_work_order": wo_name or "",
        "custom_customer_weight_kg": flt(total_customer, 3),
        "custom_total_weight_kg": flt(total_planned, 3),
        "custom_mapped_weight_kg": flt(total_mapped, 3),
        "custom_excess_weight_kg": flt(total_excess, 3),
    })
    # Run the app's own BOM-active check explicitly rather than letting the
    # blanket ignore_validate below skip it — this is the one check from
    # CustomSubcontractingOrder.validate() that must still fire at creation
    # time, so an inactive/missing BOM is caught here, not deferred to the
    # next unrelated-looking save (see IMM-03 / Report 3 Finding C-02).
    sco._pp_validate_items()
    # Same reason as _pp_validate_items above: ignore_validate skips validate()
    # wholesale, and this is the other piece of it that has to happen AT creation.
    # The Material Issue Plan is built in the same click and copies this field
    # across -- left until the next save, the MIP starts with a blank Supplier
    # Warehouse and every transfer from it fails.
    sco._auto_set_supplier_warehouse()
    sco.flags.ignore_validate = True
    sco.insert(ignore_permissions=True, ignore_mandatory=True)

    # Insert drawing item rows directly after SCO creation
    for row_data in drawing_rows:
        row_data.update({
            "doctype": "SCO Drawing Item",
            "parent": sco.name,
            "parenttype": "Subcontracting Order",
            "parentfield": "custom_drawing_items",
        })
        frappe.get_doc(row_data).insert(ignore_permissions=True)

    return sco.name


@frappe.whitelist()
def create_sco_and_mip_from_production_plan(pp_name):
    """Create the Job work order (Subcontracting Order) and its Material Issue
    Plan together in one step -- client request: MIP is always created
    immediately alongside the SCO now, not as a separate later step. Both
    directions of the reference are kept: MIP.subcontracting_order points back
    to the SCO (create_from_subcontracting_order already does this), and
    Production Plan.custom_material_issue_plan is set here to the new MIP.
    Idempotent -- safe to call again once both already exist."""
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        create_from_subcontracting_order,
    )

    existing_sco = frappe.db.get_value(
        "Subcontracting Order", {"custom_production_plan": pp_name, "docstatus": ["!=", 2]}, "name"
    )
    already_existed = bool(existing_sco)
    sco_name = existing_sco or create_sco_from_production_plan(pp_name)

    mip_name = create_from_subcontracting_order(sco_name)
    frappe.db.set_value("Production Plan", pp_name, "custom_material_issue_plan", mip_name)

    return {"sco": sco_name, "mip": mip_name, "already_existed": already_existed}


@frappe.whitelist()
def delete_sco_and_mip_for_production_plan(pp_name):
    """Delete the Job work order (Subcontracting Order) and Material Issue Plan
    created from this Production Plan, cleanly, in the order that avoids
    "linked document" errors: the Material Issue Plan is deleted FIRST (it is
    what links to the SCO via its own subcontracting_order field -- deleting it
    first removes that reference before the SCO is touched), then the SCO is
    cancelled (its own on_cancel_subcontracting_order hook already cleanly
    cancels + deletes every linked Supplier Operation Entry in the correct
    reverse-sequence order) and deleted.

    Refuses outright, with one clear message, rather than cascading through
    any REAL stock movement: if a Stock Entry has already been submitted
    against the Material Issue Plan, or any Supplier Operation Entry under the
    Subcontracting Order already has recorded production/transfer, nothing is
    deleted."""
    if not (frappe.has_permission("Subcontracting Order", "delete") and frappe.has_permission("Material Issue Plan", "delete")):
        frappe.throw(_("Not permitted to delete Job work orders / Material Issue Plans"), frappe.PermissionError)

    sco_name = frappe.db.get_value(
        "Subcontracting Order", {"custom_production_plan": pp_name, "docstatus": ["!=", 2]}, "name"
    )
    mip_name = frappe.db.get_value("Material Issue Plan", {"production_plan": pp_name}, "name")

    if not sco_name and not mip_name:
        frappe.throw(_("Nothing to delete -- no Job work order or Material Issue Plan exists for this Production Plan."))

    if mip_name:
        # custom_mip_ref lives on Stock Entry itself (header), not a child table.
        transferred = frappe.db.count("Stock Entry", {"custom_mip_ref": mip_name, "docstatus": 1})
        if transferred:
            frappe.throw(_(
                "Cannot delete: {0} submitted Stock Entry(ies) already exist against Material Issue Plan {1} "
                "(material has actually been transferred). Reverse/cancel those first if this really needs to be removed."
            ).format(transferred, mip_name))

    if sco_name:
        # completed_qty_nos / transferred_weight_kg live on the SOE Drawing Detail
        # child table, not on Supplier Operation Entry itself -- join through it.
        worked = frappe.db.sql(
            """
            select distinct sdd.parent
            from `tabSOE Drawing Detail` sdd
            inner join `tabSupplier Operation Entry` soe on soe.name = sdd.parent
            where soe.subcontracting_order = %s and soe.docstatus != 2
              and (sdd.completed_qty_nos > 0 or sdd.transferred_weight_kg > 0)
            """,
            sco_name,
            as_dict=True,
        )
        if worked:
            frappe.throw(_(
                "Cannot delete: {0} already has recorded production/transfer against it ({1}). "
                "Reverse/cancel that first if this really needs to be removed."
            ).format(sco_name, ", ".join(w.parent for w in worked)))

    # Clear the Production Plan's own reference to the MIP FIRST -- otherwise
    # Frappe's link-checker sees the Production Plan itself still pointing at
    # the Material Issue Plan (via custom_material_issue_plan) and refuses to
    # delete it, exactly the kind of "connection/link issue" this needs to avoid.
    frappe.db.set_value("Production Plan", pp_name, "custom_material_issue_plan", "")

    try:
        if mip_name:
            frappe.delete_doc("Material Issue Plan", mip_name, ignore_permissions=True)

        if sco_name:
            sco = frappe.get_doc("Subcontracting Order", sco_name)
            if sco.docstatus == 1:
                sco.cancel()
            frappe.delete_doc("Subcontracting Order", sco_name, ignore_permissions=True)
    except frappe.LinkExistsError:
        frappe.throw(_(
            "Cannot delete: something else in the system still links to this Job work order or "
            "Material Issue Plan. Remove that link first, then try again."
        ))

    return {"sco": sco_name, "mip": mip_name}


@frappe.whitelist()


@frappe.whitelist()
def create_supplier_operation_entries(sco_name):
    """Create one SOE per subcontractor operation (idempotent).
    Op 1 available_to_consume = SCO's transferred weight (0 if not yet transferred).
    Op 2+ available_to_consume = previous SOE's total_consumed_kg.
    """
    if not frappe.has_permission("Supplier Operation Entry", "create"):
        frappe.throw(_("Not permitted to create Supplier Operation Entries"), frappe.PermissionError)

    sco = frappe.get_doc("Subcontracting Order", sco_name)
    if sco.docstatus != 1:
        frappe.throw(_("Subcontracting Order must be submitted before creating Supplier Operation Entries."))

    pp_name = sco.custom_production_plan
    if not pp_name:
        frappe.throw(_("Subcontracting Order is not linked to a Production Plan."))

    return _create_soes_for_sco(sco)




@frappe.whitelist()
def get_soe_summary(sco_name):
    """Operation-wise summary for a SCO's Supplier Operation Entries."""
    from frappe.utils import flt

    soes = frappe.get_all(
        "Supplier Operation Entry",
        filters={"subcontracting_order": sco_name, "docstatus": ["!=", 2]},
        fields=[
            "name", "sequence_id", "operation", "status", "docstatus",
            "available_to_consume_kg", "total_consumed_kg",
        ],
        order_by="sequence_id asc",
    )
    if not soes:
        return soes

    drawing_rows = frappe.get_all(
        "SOE Drawing Detail",
        filters={"parent": ["in", [d.name for d in soes]]},
        fields=["parent", "drawing", "customer_drawing_number", "duno_mark_no",
                "qty_to_manufacture", "completed_qty_nos",
                "available_to_consume_nos", "transferred_weight_kg"],
        order_by="idx asc",
    )

    details_map = {}
    for dr in drawing_rows:
        details_map.setdefault(dr.parent, []).append(dr)

    # Available is what is LEFT to consume, not what arrived. An operation that has
    # consumed all eight of its pieces read "Available 8, Consumed 8" -- the same 8 in
    # two columns, one of which had already been used up. Read down the Available column
    # of a finished job and every row still offered its full quantity.
    #
    # The figure the drawing rows hold (available_to_consume_nos) is what the previous
    # operation handed over and does not move as this one works, so the consumption is
    # taken off here. The gross is kept alongside it -- "0.000 of 8.000" -- because
    # "nothing left" and "nothing ever arrived" are different problems.
    #
    # Difference is measured from Overall Qty on every row, including Op-1. It used to
    # be measured from Available on Op-2+, which is now the Available column itself; a
    # column that agrees with its neighbour by construction tells you nothing. Against
    # Overall Qty it answers the question the row is really asked -- how many of this
    # job's pieces does this operation still owe -- and answers it the same way on every
    # row.
    for soe in soes:
        details = details_map.get(soe.name, [])
        soe["drawing_details"] = details
        soe["total_qty_to_mfg"] = sum(flt(d.qty_to_manufacture) for d in details)
        soe["total_completed_nos"] = sum(flt(d.completed_qty_nos) for d in details)
        seq = soe.get("sequence_id") or 1
        if seq == 1:
            # Op-1 is measured in Kg -- it consumes weight off the rack, not pieces --
            # so there is nothing in Nos to take off it.
            soe["avail_gross_nos"] = sum(flt(d.transferred_weight_kg) for d in details)
            soe["avail_nos"] = soe["avail_gross_nos"]
        else:
            soe["avail_gross_nos"] = sum(flt(d.available_to_consume_nos) for d in details)
            soe["avail_nos"] = flt(soe["avail_gross_nos"]) - flt(soe["total_completed_nos"])
        soe["diff_nos"] = flt(soe["total_qty_to_mfg"]) - flt(soe["total_completed_nos"])

    return soes




def _final_operation(sco_name):
    """The last operation in the routing, whether or not anything is finished on it.

    The button used to wait for custom_all_ops_complete -- every operation on every
    drawing done. A job of ten drawings that had finished four could not book those
    four, so finished steel sat at the supplier with nothing to show for it until the
    last piece of the last drawing was painted."""
    rows = frappe.get_all(
        "Supplier Operation Entry",
        filters={"subcontracting_order": sco_name, "docstatus": ["<", 2]},
        fields=["name", "operation", "sequence_id", "status"],
        order_by="sequence_id desc", limit=1,
    )
    return rows[0] if rows else None


def _fg_already_booked(sco_name):
    """Pieces already turned into finished goods, per drawing.

    Read off the finished-goods rows of submitted Manufacture entries, which carry the
    drawing they were made for. Without it a second run would re-book pieces the first
    run had already produced."""
    booked = {}
    for r in frappe.db.sql(
        """
        SELECT sed.custom_drawing AS drawing, SUM(sed.qty) AS qty
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.subcontracting_order = %(sco)s AND se.stock_entry_type = 'Manufacture'
          AND se.docstatus = 1 AND sed.is_finished_item = 1
          AND IFNULL(sed.custom_drawing, '') != ''
        GROUP BY sed.custom_drawing
        """,
        {"sco": sco_name}, as_dict=True,
    ):
        booked[r.drawing] = flt(r.qty)
    return booked


def _rm_already_consumed(sco_name, supplier_warehouse):
    """Raw material already consumed by submitted Manufacture entries, per item and batch."""
    out = {}
    for r in frappe.db.sql(
        """
        SELECT sed.item_code, sed.batch_no, SUM(sed.qty) AS qty
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.subcontracting_order = %(sco)s AND se.stock_entry_type = 'Manufacture'
          AND se.docstatus = 1 AND sed.s_warehouse = %(wh)s
        GROUP BY sed.item_code, sed.batch_no
        """,
        {"sco": sco_name, "wh": supplier_warehouse}, as_dict=True,
    ):
        out[(r.item_code, r.batch_no or "")] = flt(r.qty)
    return out


def _consumption_for_completed(sco, supplier_warehouse, preview, available):
    """Narrow the supplier's stock to the share belonging to the finished drawings.

    Booking four drawings out of ten must consume four drawings' worth of steel, not
    everything sitting at the supplier -- the other six have not been made yet and their
    material has to stay where it is.

    Each drawing's share comes from the Material Issue Plan's own raw-material rows,
    which record what was transferred for that DUNO, scaled by how much of the drawing is
    finished: a drawing of two pieces with one finished consumes half of its rows.

    The figure is worked out CUMULATIVELY -- what the job should have consumed by now for
    everything finished to date, less what earlier entries already consumed -- rather
    than incrementally. That is what makes the last entry land exactly on the transferred
    weight instead of a few grams away from it after several partial runs.

    A drawing whose share cannot be traced (no Material Issue Plan, or rows carrying no
    DUNO) falls back to the whole of what is available, which is the old behaviour: the
    alternative is booking finished goods against no material at all."""
    mip_name = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": sco.name}, "name")
    if not mip_name:
        return available

    rows = frappe.get_all(
        "Material Issue Plan Raw Material", filters={"parent": mip_name},
        fields=["item_code", "planned_item", "batch_no", "duno_mark_no", "transferred_qty",
                "drawing_planned_weight", "reqd_kg"],
    )
    if not rows or not any(r.duno_mark_no for r in rows):
        return available

    # How much of each drawing is finished, cumulatively, as a fraction of its plan.
    finished_fraction = {}
    for d in preview["drawings"]:
        planned = flt(d["qty_to_manufacture"])
        if planned:
            finished_fraction[d["duno_mark_no"] or ""] = min(
                1.0, flt(d["completed_qty_nos"]) / planned)

    # The batch's own item is what the transfer line carries, not the requirement's --
    # they differ wherever an alternate was issued against a requirement.
    share = {}
    for r in rows:
        fraction = finished_fraction.get(r.duno_mark_no or "")
        if not fraction:
            continue
        key = (r.planned_item or r.item_code, r.batch_no or "")

        # Capped at what the drawing actually NEEDS, not at what was sent.
        #
        # Whole pieces go to the supplier -- you cannot send 2.039 of a cut piece,
        # and a 5 m length is issued to make a 340 mm part. Consuming the whole
        # transfer would charge the job for every kilo that went out and leave
        # nothing behind to return, so the off-cut could only ever be received as
        # new stock while the same steel was also booked into finished goods. The
        # job's real consumption is the drawing's own weight; whatever is over
        # stays at the supplier, to come back as an excess return or be written
        # off as process loss with a reason.
        wanted = flt(r.drawing_planned_weight) or flt(r.reqd_kg)
        contribution = flt(r.transferred_qty) * fraction
        if wanted:
            contribution = min(contribution, wanted * fraction)
        share[key] = flt(share.get(key, 0)) + contribution

    if not share:
        return []

    already = _rm_already_consumed(sco.name, supplier_warehouse)
    out = []
    for row in available:
        key = (row["item_code"], row.get("batch_no") or "")
        due = flt(share.get(key, 0) - already.get(key, 0), 3)
        if due <= 0:
            continue
        # Never more than is actually there: an off-cut returned to stores, or material
        # already consumed some other way, has to reduce what this can take.
        qty = min(due, flt(row["qty"], 3))
        if qty <= 0:
            continue
        out.append(dict(row, qty=flt(qty, 3)))
    return out


@frappe.whitelist()
def get_final_stock_entry_preview(sco_name):
    """What the final stock entry would book right now, without booking it.

    One row per drawing: how many pieces the last operation has finished, how many of
    those are already in finished goods, and how many are left to book. The popup shows
    this before anything is created, because "four of ten" is a fact somebody should see
    and agree with rather than discover in a draft."""
    if not frappe.has_permission("Subcontracting Order", "read", doc=sco_name):
        frappe.throw(_("Not permitted to read this Job Work Order"), frappe.PermissionError)

    final = _final_operation(sco_name)
    if not final:
        return {"final_operation": None, "drawings": [], "can_create": False,
                "reason": _("No operations have been created for this Job Work Order yet.")}

    booked = _fg_already_booked(sco_name)
    completed = {
        d.drawing: d
        for d in frappe.get_all(
            "SOE Drawing Detail", filters={"parent": final["name"]},
            fields=["drawing", "customer_drawing_number", "duno_mark_no",
                    "qty_to_manufacture", "completed_qty_nos"], order_by="idx",
        )
        if d.drawing
    }

    drawings, total_ready = [], 0.0
    for drawing, d in completed.items():
        done = flt(d.completed_qty_nos, 3)
        already = flt(booked.get(drawing), 3)
        ready = flt(done - already, 3)
        total_ready += max(ready, 0.0)
        drawings.append({
            "drawing": drawing,
            "duno_mark_no": d.duno_mark_no or "",
            "customer_drawing_number": d.customer_drawing_number or "",
            "qty_to_manufacture": flt(d.qty_to_manufacture, 3),
            "completed_qty_nos": done,
            "already_booked": already,
            "ready_to_book": max(ready, 0.0),
        })

    total_ready = flt(total_ready, 3)
    return {
        "final_operation": final,
        "drawings": drawings,
        "total_ready": total_ready,
        "total_planned": flt(sum(d["qty_to_manufacture"] for d in drawings), 3),
        "total_completed": flt(sum(d["completed_qty_nos"] for d in drawings), 3),
        "can_create": total_ready > 0,
        "reason": "" if total_ready > 0 else _(
            "Nothing is waiting to be booked. The last operation ({0}) has completed "
            "{1} of {2} pieces, and all of them are already in finished goods."
        ).format(final["operation"], flt(sum(d["completed_qty_nos"] for d in drawings), 3),
                 flt(sum(d["qty_to_manufacture"] for d in drawings), 3)),
    }


@frappe.whitelist()
def create_finished_goods_entry(sco_name):
    """Create a draft 'Manufacture' Stock Entry that consumes the raw materials currently
    in the supplier warehouse and produces the finished good into the FG warehouse.

    Exposed via the 'Make Final Stock Entry' button, which appears once raw materials
    have been transferred to the supplier. The user reviews and submits the draft; on
    submission the consumed RM leaves stock and the finished good is added to inventory.

    Idempotent -- the button has no way to know a Stock Entry already exists for this
    SCO without asking, and previously called through unconditionally every click,
    creating a fresh duplicate draft (or throwing 'already returned' further down) each
    time. Now: a SUBMITTED entry means the work is already done, so refuse outright
    rather than create a second one; a DRAFT one already sitting there is handed back
    as-is instead of piling up another. Returns {"name": ..., "already_existed": bool}
    so the caller can phrase its message correctly either way.
    """
    sco = frappe.get_doc("Subcontracting Order", sco_name)
    if sco.docstatus != 1:
        frappe.throw(_("Subcontracting Order must be submitted first."))

    # A submitted entry no longer ends the matter -- booking four drawings now and six
    # later is the point. What it must not do is double-book, and that is only safe
    # where the earlier entry says which drawings it was for.
    #
    # Entries written before finished-goods rows carried custom_drawing say nothing of
    # the sort, so their pieces cannot be netted off and a second entry would book them
    # again. Those still stop here, exactly as they always did.
    unattributed = frappe.db.sql(
        """
        SELECT se.name FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.subcontracting_order = %(sco)s AND se.stock_entry_type = 'Manufacture'
          AND se.docstatus = 1 AND sed.is_finished_item = 1
          AND IFNULL(sed.custom_drawing, '') = ''
        LIMIT 1
        """,
        {"sco": sco_name},
    )
    if unattributed:
        frappe.throw(
            _("A Final Stock Entry has already been created and submitted for this "
              "Job Work Order: {0}. It does not record which drawings it booked, so a "
              "second entry cannot tell what is left and might book the same pieces "
              "again.").format(unattributed[0][0]),
            title=_("Already Booked"),
        )

    existing_draft = frappe.db.get_value(
        "Stock Entry", {"subcontracting_order": sco_name, "stock_entry_type": "Manufacture", "docstatus": 0}, "name"
    )
    if existing_draft:
        return {"name": existing_draft, "already_existed": True}

    mip_status = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": sco_name}, "status")
    if mip_status == "Completed":
        frappe.throw(_("The linked Material Issue Plan is already Completed and locked for further changes."))
    supplier_warehouse = _get_sco_supplier_warehouse(sco)
    if not supplier_warehouse:
        frappe.throw(_("Please set the Supplier / WIP Warehouse on the Material Issue Plan "
                       "(or the Job Worker Warehouse on the Subcontracting Order) first."))
    if not flt(sco.get("custom_transferred_weight_kg")):
        frappe.throw(_("No raw material has been transferred to the supplier yet. "
                       "Transfer raw materials before making the finished-goods entry."))

    # Determine FG warehouse from SCO items or the linked Material Issue Plan's
    # excess/return warehouse (custom_return_warehouse moved there).
    fg_warehouse = ""
    if sco.items:
        fg_warehouse = sco.items[0].warehouse or ""
    if not fg_warehouse:
        mip_name = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": sco.name})
        if mip_name:
            fg_warehouse = frappe.db.get_value("Material Issue Plan", mip_name, "excess_return_warehouse") or ""
    if not fg_warehouse:
        frappe.throw(_("No finished-good warehouse set. Set the warehouse on the "
                       "Subcontracting Order item (or the Finished Goods Warehouse on the "
                       "linked Material Issue Plan) first."))

    # What the last operation has actually finished decides what this entry books.
    preview = get_final_stock_entry_preview(sco_name)
    if not preview["final_operation"]:
        frappe.throw(_("The final operation has not been created for this Job Work Order yet."))
    if not preview["can_create"]:
        frappe.throw(preview["reason"], title=_("Nothing to Book"))

    consumed = _get_supplier_wh_consumption_items(sco, supplier_warehouse)
    if not consumed:
        frappe.throw(_("No raw-material stock found in the supplier warehouse to consume. "
                       "Ensure the raw materials have been transferred to the supplier."))

    consumed = _consumption_for_completed(sco, supplier_warehouse, preview, consumed)
    if not consumed:
        frappe.throw(_("The drawings finished so far have no raw material left to consume "
                       "against them."), title=_("Nothing to Consume"))

    # One finished-goods row per drawing, for the pieces the last operation has
    # finished and not yet booked -- not for the whole job. Four drawings out of ten
    # produce four rows; the other six wait for their own entry.
    #
    # Each row carries the drawing it was made for, which is what _fg_already_booked
    # reads on the next run so the same piece is never booked twice.
    item_by_drawing = {
        d.drawing: d for d in (sco.get("custom_drawing_items") or []) if d.get("drawing")
    }
    fg_rows = []
    for row in preview["drawings"]:
        if flt(row["ready_to_book"]) <= 0:
            continue
        d = item_by_drawing.get(row["drawing"])
        item_code = (d.item_code if d else None) or (sco.items[0].item_code if sco.items else None)
        if not item_code:
            continue
        fg_rows.append({
            "item_code": item_code,
            "qty": flt(row["ready_to_book"], 3),
            "uom": frappe.db.get_value("Item", item_code, "stock_uom") or "Nos",
            "t_warehouse": fg_warehouse,
            "is_finished_item": 1,
            "custom_drawing": row["drawing"],
            "custom_duno_mark_no": row["duno_mark_no"],
            "custom_customer_drawing_number": row["customer_drawing_number"],
            "description": row["duno_mark_no"] or row["customer_drawing_number"] or "",
        })
    if not fg_rows:
        frappe.throw(_("No finished-good item found for the drawings that are complete."))

    items = list(consumed) + fg_rows

    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Manufacture",
        "company": sco.company,
        "subcontracting_order": sco_name,
        "items": items,
    })
    se.insert(ignore_permissions=True)
    return {"name": se.name, "already_existed": False}


# ─────────────────────────────────────────────────────────────────────────────
# Doc event handlers
# ─────────────────────────────────────────────────────────────────────────────

def _soe_consumed_kg(doc):
    """Weight this operation actually passed on to the next one.

    Not simply SUM(consumption_log.weight_kg): on an operation with Inspection
    Mandatory, only ACCEPTED pieces move on, so each drawing contributes its logged Kg
    in the same proportion that its accepted Nos bears to its logged Nos. Weight that
    is still awaiting inspection, or was rejected, has not been passed to the next
    operation and must not be counted as though it had.

    For a non-mandatory operation completed_qty_nos IS the raw log total, so the
    scale factor is 1 and this returns the plain sum.

    The scaling also absorbs historical records logged while mandatory operations were
    exempt from the Nos ceiling (step 6 of validate_supplier_operation_entry), where the
    same piece was deliberately re-logged after rework and a plain sum would count its
    weight twice. New records can no longer be over-logged, but old ones exist.

    Log rows carrying weight but no drawing (or no Nos) can't be apportioned, so
    they are passed through at face value rather than silently dropped."""
    done_by_drawing = {
        r.drawing: flt(r.completed_qty_nos)
        for r in (doc.drawing_details or []) if r.drawing
    }
    logged_nos = defaultdict(float)
    logged_kg = defaultdict(float)
    unattributed_kg = 0.0
    for r in (doc.consumption_log or []):
        if r.drawing and flt(r.qty_nos) > 0:
            logged_nos[r.drawing] += flt(r.qty_nos)
            logged_kg[r.drawing] += flt(r.weight_kg)
        else:
            unattributed_kg += flt(r.weight_kg)

    total = unattributed_kg
    for drawing, nos in logged_nos.items():
        kg = logged_kg[drawing]
        # A drawing with no completed_qty_nos yet (mandatory op awaiting its first
        # Inspection Entry) contributes nothing -- nothing has been accepted to pass on.
        done = done_by_drawing.get(drawing, nos)
        total += kg * (done / nos) if nos else kg
    return flt(total, 3)


def validate_supplier_operation_entry(doc, method):
    """Per-drawing Nos tracking + validation.

    For all operations:
      - Sum qty_nos per drawing from consumption_log.
      - If Inspection Mandatory is OFF: that sum is pushed straight into
        drawing_details.completed_qty_nos, same as before.
      - If Inspection Mandatory is ON: completed_qty_nos is left untouched here — it only
        ever grows via Accepted Qty from a submitted Inspection Entry (see
        inspection.on_submit_inspection_entry / _apply_soe_inspection_results). The gap
        between what's been logged and what Inspection has actually accepted is instead
        surfaced in inspection_items (see _sync_soe_inspection_items) for QC to review.
      - Auto-advance status from Open → In Progress when any Nos are logged.

      - Recompute total_consumed_kg (see _soe_consumed_kg) on EVERY operation — this is
        what the next operation's available_to_consume_kg is seeded from.

    For Op-1 (sequence_id == 1):
      - Check the Manufacturing Settings trigger: if "Fully Transferred", block logging
        for a drawing whose transferred_weight_kg is 0.
      - Keep existing Kg over-consume guard (available_to_consume_kg from SCO transfer).

    For Op-2+ (sequence_id > 1):
      - Validate that total qty_nos per drawing does not exceed available_to_consume_nos.
    """
    seq = doc.sequence_id or 1

    # --- 1. Sum qty_nos per drawing ---
    log_nos_by_drawing = defaultdict(float)
    for r in (doc.consumption_log or []):
        if r.drawing and flt(r.qty_nos) > 0:
            log_nos_by_drawing[r.drawing] += flt(r.qty_nos)

    # --- 2. Push completed_qty_nos into drawing_details rows (non-mandatory only —
    #         see _sync_soe_inspection_items for the mandatory path) ---
    if not doc.custom_inspection_mandatory:
        for row in (doc.drawing_details or []):
            row.completed_qty_nos = flt(log_nos_by_drawing.get(row.drawing or "", 0.0), 3)

    _sync_soe_inspection_items(doc, log_nos_by_drawing)

    # --- 2a. Op-1: auto-set available_to_consume_nos = qty_to_manufacture when material
    #         has been transferred for that drawing (transferred_weight_kg > 0) ---
    if seq == 1:
        for row in (doc.drawing_details or []):
            if flt(row.transferred_weight_kg) > 0:
                row.available_to_consume_nos = flt(row.qty_to_manufacture, 3)

    # --- 2c. Update SOE-level Nos summary fields ---
    doc.total_available_nos = flt(
        sum(flt(r.available_to_consume_nos) for r in (doc.drawing_details or [])), 3
    )
    doc.total_completed_nos = flt(
        sum(flt(r.completed_qty_nos) for r in (doc.drawing_details or [])), 3
    )

    # --- 2b. Validate completed_qty_nos does not exceed qty_to_manufacture ---
    for row in (doc.drawing_details or []):
        qty_to_mfg = flt(row.qty_to_manufacture)
        completed = flt(row.completed_qty_nos)
        if qty_to_mfg > 0 and completed > qty_to_mfg:
            frappe.throw(
                _("Drawing {0}: Completed ({1} Nos) exceeds Qty to Manufacture ({2} Nos). "
                  "Reduce the logged quantity.")
                .format(row.customer_drawing_number or row.drawing, completed, qty_to_mfg),
                title=_("Completed Qty Exceeds Limit"),
            )

    # --- 3. Status ---
    if log_nos_by_drawing and doc.status == "Open":
        doc.status = "In Progress"

    # An amendment starts the operation over. The cancelled document's Completed
    # status copies across but its finished quantities do not, so leaving it set
    # would both describe the new draft wrongly and make it unsaveable -- the
    # check below would refuse an amendment nobody could get past.
    # __islocal rather than is_new(): same flag is_new() reads, but reached
    # through get() because this validator is also driven directly with plain
    # dicts in the tests, which carry no Document methods. (creation is no use
    # here -- insert() stamps it before validate runs.)
    if doc.get("amended_from") and doc.get("__islocal") and (doc.status or "") == "Completed":
        doc.status = "In Progress" if log_nos_by_drawing else "Open"

    _validate_completed_status(doc, seq)

    # --- 4. Op-1: check log trigger setting ---
    if seq == 1 and log_nos_by_drawing:
        trigger = (
            frappe.db.get_single_value("Manufacturing Settings", "custom_soe_log_trigger")
            or "Fully Transferred"
        )
        if trigger == "Fully Transferred":
            detail_map = {r.drawing: r for r in (doc.drawing_details or []) if r.drawing}
            for drawing, nos in log_nos_by_drawing.items():
                row = detail_map.get(drawing)
                if row and flt(row.transferred_weight_kg) <= 0:
                    frappe.throw(
                        _("Drawing {0}: no material has been transferred to the supplier warehouse yet. "
                          "Transfer raw materials first, or change 'SOE Log Entry Allowed When' in "
                          "Manufacturing Settings to allow partial entries.")
                        .format(row.customer_drawing_number or drawing),
                        title=_("Material Not Yet Transferred"),
                    )

    # --- 5. Kg consumed, for EVERY operation (this feeds the next one's
    #        available_to_consume_kg via _propagate_available_to_next). Computing it
    #        only for seq == 1, as this did originally, left Op-2 reporting 0 Kg
    #        consumed and every operation from Op-3 on showing 0 Kg available -- the
    #        weight chain died one hop in. ---
    doc.total_consumed_kg = _soe_consumed_kg(doc)

    # The over-consume guard stays on the RAW log total, unscaled: it is a data-entry
    # check ("you typed more Kg than you were given"), so rework re-logs must still
    # count against it even though they don't add to the weight carried forward.
    if seq == 1:
        total_kg = sum(flt(r.weight_kg) for r in (doc.consumption_log or []))
        available_kg = flt(doc.available_to_consume_kg)
        if available_kg > 0 and total_kg > available_kg:
            frappe.throw(
                _("You have entered {0} Kg, but only {1} Kg is available to consume.")
                .format(flt(total_kg, 3), flt(available_kg, 3)),
                title=_("Exceeds Available to Consume"),
            )

    # --- 6. Per-drawing Nos ceiling on the Consumption Log, for EVERY operation.
    #
    #        The log records what was produced, once. If the drawing is 4 Nos, the log
    #        can never total more than 4 -- on any operation, mandatory inspection or
    #        not. The ceiling is the previous operation's completed Nos from Op-2 on,
    #        and the drawing's own quantity at Op-1.
    #
    #        Mandatory operations were previously exempt so that a rejected piece could
    #        be logged a SECOND time after rework, deliberately pushing the total past
    #        the real quantity (4 made, 1 rejected, re-logged: total 5). That is no
    #        longer wanted -- inspection can run many rounds, but the log is written
    #        once. Nothing is lost by removing it: _sync_soe_inspection_items derives
    #        pending work as (logged - accepted), so a rejected piece stays pending on
    #        its own and the next inspection round picks it up without a second log
    #        entry. See tests/verify_consumption_log_hard_cap.py. ---
    detail_map = {r.drawing: r for r in (doc.drawing_details or []) if r.drawing}
    for drawing, nos in log_nos_by_drawing.items():
        row = detail_map.get(drawing)
        label = (row.customer_drawing_number if row else None) or drawing

        if seq > 1:
            available = flt(row.available_to_consume_nos) if row else 0.0
            if available <= 0:
                frappe.throw(
                    _("Drawing {0}: the previous operation has not completed any quantity "
                      "for this drawing. Consumption cannot be logged until the previous "
                      "operation is completed.")
                    .format(label),
                    title=_("Previous Operation Not Completed"),
                )
            ceiling, source = available, _("available from the previous operation")
        else:
            ceiling = flt(row.qty_to_manufacture) if row else 0.0
            if ceiling <= 0:
                continue
            source = _("to manufacture for this drawing")

        if nos > ceiling:
            frappe.throw(
                _("Drawing {0}: entered {1} Nos in total but only {2} Nos are {3}. "
                  "The Consumption Log records what was produced once -- a piece sent "
                  "back for rework is not logged again, it stays pending for the next "
                  "inspection round on its own.")
                .format(label, flt(nos, 3), flt(ceiling, 3), source),
                title=_("Exceeds Available Qty"),
            )


def _soe_drawing_target_nos(row, seq):
    """How many Nos this operation is expected to finish for one drawing.

    Op-1 works to the drawing's own quantity; every later operation works to
    what the previous one handed it. Same pair the Consumption Log ceiling in
    validate_supplier_operation_entry uses, so "fully done" and "you have
    entered too much" are measured against one number, not two.
    """
    return flt(row.available_to_consume_nos) if (seq or 1) > 1 else flt(row.qty_to_manufacture)


def _validate_completed_status(doc, seq):
    """Status may only reach Completed when the operation really is finished.

    Completed is not a label -- before_submit_supplier_operation_entry requires
    it, submitting hands this operation's quantity to the next one, and the Job
    Work Order's Operations tab reports from it. Setting it early passes a
    quantity forward that was never made.

    Two things must hold, and neither was checked before:

      * every drawing is done -- completed Nos have reached the quantity this
        operation was given. (On an Inspection-Mandatory operation completed Nos
        only ever comes from an accepted Inspection Entry, so this is the same
        check expressed once: logged for ordinary operations, accepted for
        inspected ones.)
      * no inspection round is still open. An operation whose last call is
        Pending has pieces sitting with QC; closing it would submit a quantity
        inspection has not passed yet.
    """
    if (doc.status or "") != "Completed":
        return

    short, starved = [], []
    for row in (doc.drawing_details or []):
        label = row.customer_drawing_number or row.drawing
        # Nothing to make, or no drawing to make it against. The Consumption Log
        # requires a drawing and its picker is filtered to these rows, so a row
        # with no drawing can never be logged against -- gating Completed on one
        # would be a condition nobody could ever satisfy.
        if not row.drawing or flt(row.qty_to_manufacture) <= 0:
            continue

        target = _soe_drawing_target_nos(row, seq)
        if target <= 0:
            # Only reachable from Op-2 onwards: the operation before this one
            # passed nothing across, so there is nothing here to have finished.
            starved.append(label)
            continue

        done = flt(row.completed_qty_nos)
        if done + 0.001 < target:
            short.append(
                _("{0} — {1} of {2} Nos").format(label, flt(done, 3), flt(target, 3))
            )

    if short or starved:
        parts = []
        if short:
            parts.append(
                _("These drawings are not finished yet:<br>{0}").format("<br>".join(short))
            )
        if starved:
            parts.append(
                _("These drawings received nothing from the previous operation, so there is "
                  "nothing to complete:<br>{0}").format("<br>".join(starved))
            )
        frappe.throw(
            _("Status cannot be set to <b>Completed</b>.<br><br>{0}<br><br>"
              "Enter the remaining quantity in the Consumption Log first.{1}")
            .format(
                "<br><br>".join(parts),
                _(" On this operation the quantity is counted from Accepted Qty on a submitted "
                  "Inspection Entry, not from the log alone.")
                if doc.custom_inspection_mandatory else "",
            ),
            title=_("Operation Not Finished"),
        )

    if doc.custom_inspection_mandatory:
        pending = [
            r for r in (doc.custom_inspection_call_log or [])
            if (r.round_status or "") == "Pending"
        ]
        if pending:
            frappe.throw(
                _("Status cannot be set to <b>Completed</b> — inspection round {0} is still "
                  "Pending. Complete the inspection before closing this operation.")
                .format(pending[-1].round_no or len(pending)),
                title=_("Inspection Still Open"),
            )


def before_cancel_supplier_operation_entry(doc, method):
    """A Supplier Operation Entry is not cancellable on its own.

    The Job Work Order's Operations tab, the next operation's available
    quantity and the SCO Drawing Items' completion all read from SUBMITTED
    operation entries. Cancelling one leaves the order reporting a quantity
    nothing accounts for any more, and the chain behind it intact but pointing
    at a document that no longer counts -- which is exactly what happened to
    SCO-SOE-0005: cancelled, then not even amendable (the doctype had no
    amended_from field, so Frappe refused the amendment outright).

    Cancelling the Job Work Order itself still cascades through here, which is
    the supported way to undo a whole chain -- it cancels and removes every
    operation together, in reverse sequence, so nothing is left half-referenced.
    """
    if doc.flags.get("mfx_cancelled_by_sco"):
        return

    frappe.throw(
        _("A Supplier Operation Entry cannot be cancelled on its own — the Job Work Order "
          "reports its quantity, and the operations after it were given work based on it.<br><br>"
          "To undo this operation, cancel Job Work Order <b>{0}</b>: that removes the whole "
          "operation chain together and leaves nothing pointing at a cancelled document.")
        .format(doc.subcontracting_order or "—"),
        title=_("Cannot Cancel This Operation"),
    )


def _sync_soe_inspection_items(doc, log_nos_by_drawing):
    """Rebuild inspection_items fresh on every save, one row per drawing in
    drawing_details: pending Nos = everything ever logged in Consumption Log for that
    drawing, minus whatever Inspection has already accepted (completed_qty_nos). This is
    derived, not incrementally tracked, so it self-corrects across any number of rework
    rounds with no manual bookkeeping: a rejected Nos simply isn't subtracted from the log
    total, so it reappears here on its own the moment it's logged again.

    This is what makes rework work without re-logging: 4 logged, 3 accepted in round 1
    leaves 1 pending, so the rejected piece comes back for round 2 by itself.

    The raw log total is still capped at qty_to_manufacture before subtracting
    completed_qty_nos. That cap is now belt-and-braces -- step 6 of
    validate_supplier_operation_entry stops the log exceeding the drawing's quantity in
    the first place -- but it is kept as a guard for records logged before that ceiling
    applied to mandatory operations, so "pending" can never promise more Nos than
    physically exist and an Inspection Entry can never accept more than were made.

    Empty (cleared) when Inspection Mandatory is off -- there is nothing pending review."""
    doc.set("inspection_items", [])
    if not doc.custom_inspection_mandatory:
        return

    for row in (doc.drawing_details or []):
        if not row.drawing:
            continue
        logged = flt(log_nos_by_drawing.get(row.drawing, 0.0), 3)
        qty_to_mfg = flt(row.qty_to_manufacture)
        if qty_to_mfg > 0:
            logged = min(logged, qty_to_mfg)
        pending = flt(logged - flt(row.completed_qty_nos), 3)
        doc.append("inspection_items", {
            "drawing": row.drawing,
            "customer_drawing_number": row.customer_drawing_number or "",
            "qty_nos": pending if pending > 0 else 0.0,
        })


def before_submit_supplier_operation_entry(doc, method):
    """Enforce sequential, status-gated submission:
      - Status must be 'Completed' before submit.
      - Every earlier-sequence operation for the same SCO must already be submitted.
    """
    if (doc.status or "") != "Completed":
        frappe.throw(
            _("Set Status to <b>Completed</b> before submitting this Supplier Operation Entry."),
            title=_("Operation Not Completed"),
        )

    seq = doc.sequence_id or 0
    if seq > 1:
        pending = frappe.get_all(
            "Supplier Operation Entry",
            filters={
                "subcontracting_order": doc.subcontracting_order,
                "sequence_id": ["<", seq],
                "docstatus": ["!=", 1],
            },
            fields=["sequence_id", "operation"],
            order_by="sequence_id asc",
        )
        if pending:
            first = pending[0]
            frappe.throw(
                _("Operation sequence {0} (<b>{1}</b>) is not completed yet. "
                  "Operations must be completed and submitted in sequence — "
                  "finish it before submitting sequence {2}.")
                .format(first.sequence_id, first.operation, seq),
                title=_("Complete Previous Operation First"),
            )


def _propagate_available_to_next(doc):
    """Push Op-1's total_consumed_kg into Op-2's available_to_consume_kg (Kg chain).
    Kept for backwards-compatibility with Op-1 Kg tracking."""
    next_soe = frappe.db.get_value(
        "Supplier Operation Entry",
        {
            "subcontracting_order": doc.subcontracting_order,
            "sequence_id": (doc.sequence_id or 0) + 1,
            "docstatus": 0,
        },
        "name",
    )
    if next_soe:
        frappe.db.set_value(
            "Supplier Operation Entry",
            next_soe,
            "available_to_consume_kg",
            flt(doc.total_consumed_kg, 3),
            update_modified=False,
        )


def _propagate_drawing_nos_to_next(doc):
    """Push per-drawing completed_qty_nos from this SOE's drawing_details into
    the next SOE's drawing_details.available_to_consume_nos.
    Only updates the next operation while it is still a draft."""
    next_soe_name = frappe.db.get_value(
        "Supplier Operation Entry",
        {
            "subcontracting_order": doc.subcontracting_order,
            "sequence_id": (doc.sequence_id or 0) + 1,
            "docstatus": 0,
        },
        "name",
    )
    if not next_soe_name:
        return

    drawing_nos = {
        r.drawing: flt(r.completed_qty_nos, 3)
        for r in (doc.drawing_details or [])
        if r.drawing
    }
    if not drawing_nos:
        return

    next_doc = frappe.get_doc("Supplier Operation Entry", next_soe_name)
    changed = False
    for row in (next_doc.drawing_details or []):
        new_val = drawing_nos.get(row.drawing or "", 0.0)
        if flt(row.available_to_consume_nos, 3) != flt(new_val, 3):
            row.available_to_consume_nos = flt(new_val, 3)
            changed = True

    if changed:
        next_doc.total_available_nos = flt(
            sum(flt(r.available_to_consume_nos) for r in (next_doc.drawing_details or [])), 3
        )
        next_doc.flags.ignore_validate = True
        next_doc.save(ignore_permissions=True)


def _update_sco_drawing_item_completion(doc):
    """Update SCO Drawing Items' completed_qty_nos from the submitted SOE's
    drawing_details so the SCO shows consolidated drawing completion."""
    drawing_nos = {
        r.drawing: flt(r.completed_qty_nos, 3)
        for r in (doc.drawing_details or [])
        if r.drawing
    }
    if not drawing_nos:
        return

    for row in frappe.get_all(
        "SCO Drawing Item",
        filters={"parent": doc.subcontracting_order},
        fields=["name", "drawing"],
    ):
        if row.drawing in drawing_nos:
            frappe.db.set_value(
                "SCO Drawing Item", row.name,
                "completed_qty_nos", drawing_nos[row.drawing],
                update_modified=False,
            )


def on_update_supplier_operation_entry(doc, method):
    """Live propagation on save: push Kg chain and per-drawing Nos to next operation."""
    from manufyxinvenzaerp.subcontracting_management.overrides import refresh_sco_status

    if doc.docstatus == 0:
        _propagate_available_to_next(doc)
        _propagate_drawing_nos_to_next(doc)

    # First quantity logged anywhere on the order moves it Open -> Working.
    refresh_sco_status(doc.subcontracting_order)


def _push_sco_completion_to_wo(pp_name, last_soe):
    """Cross-chain counterpart of _propagate_available_to_next / _propagate_drawing_nos_to_next:
    when the SCO's final operation completes, hand its finished qty/weight off to the sibling
    Work Order's first Internal-Jobcard Job Card(s) (mixed-plan chain — some ops Subcontractor,
    the rest Internal Jobcard). No-op if there's no sibling WO yet, or no still-draft Op-1
    Job Card to push into (it will be handled by _populate_jcs_for_wo's reverse-order path
    instead, once that WO/JC is created).
    # SHARED_SCO_JC: cross-chain — no SOE-side mirror, this only runs on the SCO side
    """
    wo_name = frappe.db.get_value(
        "Work Order", {"production_plan": pp_name, "docstatus": ["!=", 2]}, "name"
    )
    if not wo_name:
        return

    nos_by_drawing = {
        r.drawing: flt(r.completed_qty_nos, 3)
        for r in (last_soe.drawing_details or []) if r.drawing
    }

    # Loop (not get_value) — a WO can in principle have more than one sequence_id=1 JC
    # if ERPNext's own batch-size splitting ever kicks in; push to all of them.
    for jc_name in frappe.get_all(
        "Job Card",
        filters={"work_order": wo_name, "sequence_id": 1, "docstatus": 0},
        pluck="name",
    ):
        jc_doc = frappe.get_doc("Job Card", jc_name)
        if not jc_doc.get("custom_drawing_details"):
            continue
        jc_doc.custom_available_to_consume_kg = flt(last_soe.total_consumed_kg, 3)
        for row in jc_doc.custom_drawing_details:
            row.available_to_consume_nos = flt(nos_by_drawing.get(row.drawing or "", 0.0), 3)
        jc_doc.custom_total_available_nos = flt(
            sum(flt(r.available_to_consume_nos) for r in jc_doc.custom_drawing_details), 3
        )
        jc_doc.flags.ignore_validate = True
        jc_doc.save(ignore_permissions=True)


def on_submit_supplier_operation_entry(doc, method):
    """On submit: propagate Kg + Nos to next operation; update SCO drawing completion;
    mark SCO all_ops_complete if this is the last operation.
    """
    _propagate_available_to_next(doc)
    _propagate_drawing_nos_to_next(doc)
    _update_sco_drawing_item_completion(doc)

    # Check if all operations are complete
    remaining = frappe.db.count(
        "Supplier Operation Entry",
        filters={
            "subcontracting_order": doc.subcontracting_order,
            "sequence_id": [">", doc.sequence_id or 0],
            "docstatus": ["!=", 2],
        },
    )
    if remaining == 0:
        frappe.db.set_value(
            "Subcontracting Order", doc.subcontracting_order, "custom_all_ops_complete", 1
        )
        pp_name = frappe.db.get_value(
            "Subcontracting Order", doc.subcontracting_order, "custom_production_plan"
        )
        if pp_name:
            _push_sco_completion_to_wo(pp_name, doc)

    # All operations done is only half of Completed -- the final Stock Entry has
    # still to be submitted -- so re-derive rather than assume either way.
    from manufyxinvenzaerp.subcontracting_management.overrides import refresh_sco_status

    refresh_sco_status(doc.subcontracting_order)


def before_delete_supplier_operation_entry(doc, method):
    """Block deletion of an SOE if other SOEs exist for the same SCO.
    The operation chain must not be broken; cancel the SCO to delete all SOEs together.
    """
    others = frappe.db.count(
        "Supplier Operation Entry",
        {
            "subcontracting_order": doc.subcontracting_order,
            "name": ["!=", doc.name],
            "docstatus": ["!=", 2],
        },
    )
    if others:
        frappe.throw(
            _("This Supplier Operation Entry is part of an operation chain for SCO <b>{0}</b>. "
              "You cannot delete it individually — cancel the Subcontracting Order first to "
              "remove all linked Supplier Operation Entries together.")
            .format(doc.subcontracting_order),
            title=_("Cannot Delete — Linked Operations Exist"),
        )


def on_cancel_subcontracting_order(doc, method):
    """On SCO cancel: cancel submitted SOEs in reverse sequence order, then delete all.
    Ensures the sequential-submit guard in before_submit does not block cascading cancels.
    """
    soes = frappe.get_all(
        "Supplier Operation Entry",
        filters={"subcontracting_order": doc.name, "docstatus": ["!=", 2]},
        fields=["name", "docstatus", "sequence_id"],
        order_by="sequence_id desc",
    )
    for soe_info in soes:
        soe_doc = frappe.get_doc("Supplier Operation Entry", soe_info.name)
        if soe_doc.docstatus == 1:
            # Cascade from the order is the only cancel an operation entry accepts
            # -- see before_cancel_supplier_operation_entry.
            soe_doc.flags.mfx_cancelled_by_sco = True
            soe_doc.cancel()
        soe_doc.delete(ignore_permissions=True)


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_soe_drawing_rows(sco, seq_idx):
    """Build drawing_details rows for a new SOE from the SCO's drawing items.

    Customer Weight / Planned Weight are static per-drawing reference figures from the
    SCO Drawing Items -- populated on every operation's SOE, not just Op-1, so whoever
    opens Op-3/Op-4/etc. can still see what the drawing was supposed to weigh.

    Op-1 (seq_idx == 1) additionally seeds transferred_weight_kg from whatever has
    ALREADY been transferred at SOE-creation time -- material can legitimately be
    transferred to the supplier before "Create Supplier Operation Entries" is ever
    clicked, and in that case there is no future transfer SE submit left to trigger
    _refresh_sco_drawing_transferred_weights(), so a hardcoded 0 here would permanently
    under-report "Available to Consume" on Op-1 even though the SCO header
    (custom_transferred_weight_kg) is correct. Uses the same proportional scaling
    (mapped_weight_kg share of the SCO total) as that refresh function, so both stay
    consistent whichever one runs first. It is still kept live afterwards by
    _refresh_sco_drawing_transferred_weights() on every subsequent transfer SE submit/cancel.
    Op-2+ : transferred_weight_kg stays 0 (not meaningful after the first transfer
    operation); available_to_consume_nos is filled later by
    _propagate_drawing_nos_to_next when Op-1 saves/submits.
    """
    total_mapped = 0.0
    ratio = 0.0
    if seq_idx == 1:
        total_mapped = sum(flt(d.mapped_weight_kg) for d in (sco.get("custom_drawing_items") or []))
        transferred_weight = flt(sco.get("custom_transferred_weight_kg") or 0)
        ratio = min(transferred_weight / total_mapped, 1.0) if total_mapped else 0.0

    rows = []
    for d in (sco.get("custom_drawing_items") or []):
        row = {
            "doctype": "SOE Drawing Detail",
            "drawing": d.drawing,
            "customer_drawing_number": d.customer_drawing_number or "",
            "duno_mark_no": d.duno_mark_no or "",
            "sales_order": d.get("sales_order") or "",
            "qty_to_manufacture": flt(d.qty_to_manufacture, 3),
            "available_to_consume_nos": 0.0,
            "completed_qty_nos": 0.0,
            "transferred_weight_kg": flt(flt(d.mapped_weight_kg) * ratio, 3) if seq_idx == 1 else 0.0,
            "customer_provided_weight_kg": flt(d.customer_weight_kg, 3),
            "planned_weight_kg": flt(d.total_weight_kg, 3),
        }
        rows.append(row)
    return rows


def _create_soes_for_sco(sco):
    """Create one SOE per operation (Subcontractor or Internal Jobcard) in the linked
    Production Plan -- Supplier Operation Entry is the universal one-row-per-operation
    execution document regardless of who performs it (client change request Phase
    0.4/4.1: Work Order/Job Card no longer used for internal operations at all).
    Idempotent — skips any sequence_id that already has a live SOE.
    Op-1 gets available_to_consume_kg from custom_transferred_weight_kg (0 if not yet
    transferred). Each SOE is populated with drawing_details rows so drawing-level
    Nos tracking is available from the start. Internal Jobcard rows get no
    supplier/supplier_warehouse (executed by the internal team, not a supplier).

    Process Planning rows with Create Operation unchecked (client change request
    Phase 4.2) are dropped entirely before numbering -- they never get an SOE and
    are treated as if they don't exist for sequencing purposes, so the
    available-to-consume chain correctly skips straight from the operation before
    to the operation after. Create Operation defaults to enabled; only an explicit
    uncheck (0) disables a row -- unset/None is treated as enabled.
    """
    pp_name = sco.custom_production_plan if hasattr(sco, "custom_production_plan") else sco.get("custom_production_plan")
    if not pp_name:
        return []

    pp = frappe.get_doc("Production Plan", pp_name)
    all_ops = [
        r for r in sorted(pp.custom_process_planning or [], key=lambda r: r.idx)
        if r.get("create_operation") is None or cint(r.get("create_operation"))
    ]
    if not all_ops:
        return []

    transferred_weight = flt(sco.get("custom_transferred_weight_kg") or 0)
    created_soes = []
    prev_soe_name = None

    for seq_idx, op_row in enumerate(all_ops, start=1):
        existing = frappe.db.get_value(
            "Supplier Operation Entry",
            {"subcontracting_order": sco.name, "sequence_id": seq_idx, "docstatus": ["!=", 2]},
            "name",
        )
        if existing:
            prev_soe_name = existing
            continue

        if seq_idx == 1:
            available_to_consume = transferred_weight
        else:
            prev_consumed = flt(
                frappe.db.get_value("Supplier Operation Entry", prev_soe_name, "total_consumed_kg")
            ) if prev_soe_name else 0
            available_to_consume = prev_consumed

        drawing_rows = _build_soe_drawing_rows(sco, seq_idx)
        is_subcontractor = op_row.work_type == "Subcontractor"

        soe = frappe.get_doc({
            "doctype": "Supplier Operation Entry",
            "subcontracting_order": sco.name,
            "production_plan": pp_name,
            "operation": op_row.operation_name,
            "custom_inspection_mandatory": 1 if cint(op_row.inspection_mandatory) else 0,
            "sequence_id": seq_idx,
            "supplier": sco.supplier if is_subcontractor else "",
            "supplier_warehouse": (sco.supplier_warehouse or "") if is_subcontractor else "",
            "status": "Open",
            "available_to_consume_kg": flt(available_to_consume, 3),
            "total_consumed_kg": 0,
            "drawing_details": drawing_rows,
        })
        soe.insert(ignore_permissions=True)
        prev_soe_name = soe.name
        created_soes.append(soe.name)

    return created_soes


def _get_mp_total_weight(mp_name):
    """Sum of calculated batch weights for all reserved rows in a Material Planning document."""
    if not mp_name:
        return 0.0

    # material_mapping: batch_calc_qty (Kg) for reserved rows with a batch assigned
    mapping_weight = frappe.db.sql(
        """
        SELECT COALESCE(SUM(batch_calc_qty), 0)
        FROM `tabMaterial Planning Material Mapping`
        WHERE parent = %s AND is_reserved = 1 AND batch IS NOT NULL AND batch != ''
        """,
        mp_name,
    )[0][0] or 0

    # available_raw_material: reserved_qty (Kg) for reserved rows
    available_weight = frappe.db.sql(
        """
        SELECT COALESCE(SUM(reserved_qty), 0)
        FROM `tabMaterial Planning Available Raw Material`
        WHERE parent = %s AND is_reserved = 1
        """,
        mp_name,
    )[0][0] or 0

    return flt(mapping_weight) + flt(available_weight)


def _get_mp_actual_transferred_weight(mp_name, source_warehouse, target_warehouses):
    """Sum of ACTUALLY-transferred (submitted Stock Entry) weight for a Material
    Planning document's reserved batches — as opposed to _get_mp_total_weight,
    which is the reserved/mapped weight regardless of whether it has moved yet.

    Capped per item+batch at the reserved qty, so a batch used elsewhere can't
    inflate this MP's figure. target_warehouses may be a warehouse or list of
    warehouses (e.g. WIP + CNC) the material may have moved into.
    """
    if not mp_name or not source_warehouse:
        return 0.0
    if isinstance(target_warehouses, str):
        target_warehouses = [target_warehouses]
    target_warehouses = [w for w in (target_warehouses or []) if w]
    if not target_warehouses:
        return 0.0

    reserved = _get_mp_reserved_batches(mp_name, source_warehouse, None)
    if not reserved:
        return 0.0

    placeholders = ", ".join(["%s"] * len(target_warehouses))
    moved = {}
    for r in frappe.db.sql(
        f"""
        SELECT sed.item_code, sed.batch_no, SUM(sed.qty) AS qty
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.stock_entry_type IN ('Material Transfer', 'Send to Subcontractor')
          AND se.docstatus = 1
          AND sed.s_warehouse = %s
          AND sed.t_warehouse IN ({placeholders})
        GROUP BY sed.item_code, sed.batch_no
        """,
        [source_warehouse] + target_warehouses,
        as_dict=True,
    ):
        moved[(r.item_code, r.batch_no or "")] = flt(r.qty)

    total = 0.0
    for item in reserved:
        key = (item["item_code"], item.get("batch_no") or "")
        total += min(flt(item["qty"]), moved.get(key, 0.0))
    return flt(total, 3)


def _refresh_wo_drawing_transferred_weights(wo):
    """Update Op-1 JC's custom_drawing_details.transferred_weight_kg rows to reflect
    ACTUAL Stock Entry transfers so far.

    Uses wo.custom_transferred_weight_kg (already correctly computed by
    _update_wo_transferred_weight) and scales each drawing's transferred weight
    proportionally to its mapped_weight_kg share of the WO total. This works
    regardless of whether MP row reservations have been cleared by SE submission.
    # SHARED_SCO_JC: mirrors _refresh_sco_drawing_transferred_weights
    """
    jc_op1 = frappe.db.get_value(
        "Job Card",
        {"work_order": wo.name, "sequence_id": 1, "docstatus": ["!=", 2]},
        "name",
    )
    if not jc_op1:
        return

    jc_doc = frappe.get_doc("Job Card", jc_op1)
    if not jc_doc.get("custom_drawing_details"):
        return

    wo_rows = {d.drawing: d for d in (wo.get("custom_drawing_items") or [])}
    total_wo_mapped = sum(flt(d.mapped_weight_kg) for d in (wo.get("custom_drawing_items") or []))
    transferred_weight = flt(wo.get("custom_transferred_weight_kg") or 0)
    ratio = min(transferred_weight / total_wo_mapped, 1.0) if total_wo_mapped else 0.0

    for row in jc_doc.custom_drawing_details:
        wo_row = wo_rows.get(row.drawing)
        new_val = flt(flt(wo_row.mapped_weight_kg) * ratio, 3) if wo_row else 0.0
        if flt(row.transferred_weight_kg) != new_val:
            # Per-row write, not jc_doc.save() -- see the matching note in
            # _refresh_sco_drawing_transferred_weights: Op-1 is often already
            # submitted when a later partial transfer runs this from the Stock Entry
            # submit hook, and save() would then abort that submission outright.
            frappe.db.set_value(
                row.doctype, row.name,
                "transferred_weight_kg", new_val,
                update_modified=False,
            )
            row.transferred_weight_kg = new_val


def _get_sco_transfer_warehouses(sco_name):
    """Source/CNC warehouse for an SCO, resolved via its Material Issue Plan —
    these no longer live on the SCO itself (moved to Material Issue Plan)."""
    mip_name = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": sco_name})
    if not mip_name:
        return None, None
    mip = frappe.db.get_value(
        "Material Issue Plan", mip_name, ["source_warehouse", "cnc_warehouse"], as_dict=True
    )
    return (mip.source_warehouse, mip.cnc_warehouse) if mip else (None, None)


def _get_sco_supplier_warehouse(sco):
    """Resolve the warehouse raw material was actually transferred into for this SCO.

    sco.supplier_warehouse (core field) only auto-sets when a Job Worker is set
    (_auto_set_supplier_warehouse) -- an Internal Job SCO has no Job Worker, so it stays
    blank forever even after real transfers happen. The Material Issue Plan's own
    Supplier / WIP Warehouse field is the actual source of truth the transfer itself was
    resolved against (see get_target_context in material_issue_plan.py
    and _update_sco_transferred_weight in stock_entry.py, which already use this same
    fallback) -- check it first, then fall back to the SCO's own field for a Supplier
    Job/Supplier with Material flow."""
    mip_warehouse = frappe.db.get_value(
        "Material Issue Plan", {"subcontracting_order": sco.name}, "supplier_warehouse"
    )
    return mip_warehouse or sco.supplier_warehouse


def _get_wo_transfer_warehouses(wo_name):
    """Source/CNC warehouse for a Work Order, resolved via its Material Issue Plan —
    these no longer live on the Work Order itself (moved to Material Issue Plan).
    # SHARED_SCO_JC: mirrors _get_sco_transfer_warehouses
    """
    mip_name = frappe.db.get_value("Material Issue Plan", {"work_order": wo_name})
    if not mip_name:
        return None, None
    mip = frappe.db.get_value(
        "Material Issue Plan", mip_name, ["source_warehouse", "cnc_warehouse"], as_dict=True
    )
    return (mip.source_warehouse, mip.cnc_warehouse) if mip else (None, None)


def _refresh_sco_drawing_transferred_weights(sco):
    """SOE equivalent of _refresh_wo_drawing_transferred_weights.
    Uses sco.custom_transferred_weight_kg (already correctly computed) and scales
    each drawing proportionally to its mapped_weight_kg share of the SCO total.
    # SHARED_SCO_JC: mirrors _refresh_wo_drawing_transferred_weights
    """
    soe_op1 = frappe.db.get_value(
        "Supplier Operation Entry",
        {"subcontracting_order": sco.name, "sequence_id": 1, "docstatus": ["!=", 2]},
        "name",
    )
    if not soe_op1:
        return

    soe_doc = frappe.get_doc("Supplier Operation Entry", soe_op1)
    if not soe_doc.get("drawing_details"):
        return

    sco_rows = {d.drawing: d for d in (sco.get("custom_drawing_items") or [])}
    total_sco_mapped = sum(flt(d.mapped_weight_kg) for d in (sco.get("custom_drawing_items") or []))
    transferred_weight = flt(sco.get("custom_transferred_weight_kg") or 0)
    ratio = min(transferred_weight / total_sco_mapped, 1.0) if total_sco_mapped else 0.0

    for row in soe_doc.drawing_details:
        sco_row = sco_rows.get(row.drawing)
        new_val = flt(flt(sco_row.mapped_weight_kg) * ratio, 3) if sco_row else 0.0
        if flt(row.transferred_weight_kg) != new_val:
            # Written per-row rather than via soe_doc.save(): this runs from the
            # Stock Entry submit hook, and Op-1 is routinely already SUBMITTED by the
            # time a later partial transfer lands -- a save() there dies with
            # "Not allowed to change Transferred (Kg) after submission" and takes the
            # whole Stock Entry submission down with it. Only this one Float changes
            # and it is a derived display figure, so a direct write is both safe and
            # cheaper than the full save this used to do.
            frappe.db.set_value(
                row.doctype, row.name,
                "transferred_weight_kg", new_val,
                update_modified=False,
            )
            row.transferred_weight_kg = new_val


def _get_mp_drawing_weight(mp_name, duno_mark_no):
    """Per-drawing planned RM weight — sum of qty from raw_materials sub-table."""
    if not mp_name:
        return 0.0
    if duno_mark_no:
        wt = frappe.db.sql(
            """
            SELECT COALESCE(SUM(qty), 0)
            FROM `tabMaterial Planning Raw Material`
            WHERE parent = %s AND duno_mark_no = %s
            """,
            (mp_name, duno_mark_no),
        )[0][0] or 0
        return flt(wt)
    return _get_mp_total_weight(mp_name)


def _get_mp_drawing_weights_by_duno(mp_name):
    """Batched variant of _get_mp_drawing_weight's duno_mark_no branch -- one grouped
    query per Material Planning instead of one query per drawing row sharing that MP
    (the same N+1 shape already fixed elsewhere in this app; this one was found while
    investigating slow Stock Entry submission via refresh_weight_summary).

    Returns {duno_mark_no: planned_qty}. Callers still fall back to
    _get_mp_total_weight(mp_name) for a blank/falsy duno_mark_no, exactly as
    _get_mp_drawing_weight itself does -- this only replaces the per-duno lookup."""
    weights = defaultdict(float)
    if not mp_name:
        return weights
    for r in frappe.db.sql(
        """
        SELECT duno_mark_no, COALESCE(SUM(qty), 0) AS qty
        FROM `tabMaterial Planning Raw Material`
        WHERE parent = %s
        GROUP BY duno_mark_no
        """,
        mp_name,
        as_dict=True,
    ):
        weights[r.duno_mark_no or ""] += flt(r.qty)
    return weights


def _get_mp_mapped_weight_by_duno(mp_name):
    """Return {duno_mark_no: mapped_weight_kg} for a Material Planning document.

    Mapped weight = the batch weight allocated to each drawing — cross-mapped rows
    (Material Mapping batch_calc_qty) plus exact-match rows (Available Raw Material
    reserved_qty or required_qty). BOTH tables carry duno_mark_no, so both are
    attributed directly to the drawing that actually reserved the batch.

    Exact-match rows used to be spread across every drawing in the Material Planning
    in proportion to that item's planned qty, on the assumption they carried no DUNO.
    They do carry one, and the spreading was badly wrong whenever a Material Planning
    covered more drawings than the job being costed: weight reserved for a drawing in
    THIS job leaked onto drawings that weren't in it and was then discarded with them.
    On the plan that surfaced this, drawing 1B1 reported 501.422 Kg mapped against
    1,876.436 Kg actually reserved, and the Job Work Order's per-drawing rows summed
    to barely half its own (correct) header weight. The proportional split survives
    only as a fallback for rows that genuinely have no DUNO.

    Includes all batch-assigned rows regardless of is_reserved, so the figure stays
    accurate after SE submission clears the reservation flag.
    """
    mapped = defaultdict(float)
    if not mp_name:
        return mapped

    # Cross-mapped — already carries the DUNO/Mark No; include whether reserved or not
    for r in frappe.db.sql(
        """
        SELECT duno_mark_no, batch_calc_qty
        FROM `tabMaterial Planning Material Mapping`
        WHERE parent = %s AND batch IS NOT NULL AND batch != '' AND batch_calc_qty > 0
        """,
        mp_name,
        as_dict=True,
    ):
        mapped[r.duno_mark_no or ""] += flt(r.batch_calc_qty)

    # Exact-match — attributed by its own DUNO; only rows missing one need splitting
    exact_rows = frappe.db.sql(
        """
        SELECT item_code, duno_mark_no,
               COALESCE(NULLIF(reserved_qty, 0), required_qty) AS qty
        FROM `tabMaterial Planning Available Raw Material`
        WHERE parent = %s AND batch_no IS NOT NULL AND batch_no != ''
          AND COALESCE(NULLIF(reserved_qty, 0), required_qty) > 0
        """,
        mp_name,
        as_dict=True,
    )
    exact_rows = [frappe._dict(r) for r in exact_rows]

    for er in list(exact_rows):
        if er.duno_mark_no:
            mapped[er.duno_mark_no] += flt(er.qty)
            exact_rows.remove(er)

    if exact_rows:
        item_duno_qty = defaultdict(lambda: defaultdict(float))  # item -> duno -> planned qty
        item_total = defaultdict(float)                          # item -> total planned qty
        for p in frappe.get_all(
            "Material Planning Raw Material",
            filters={"parent": mp_name},
            fields=["item_code", "duno_mark_no", "qty"],
        ):
            item_duno_qty[p.item_code][p.duno_mark_no or ""] += flt(p.qty)
            item_total[p.item_code] += flt(p.qty)

        for er in exact_rows:
            qty = flt(er.qty)
            if qty <= 0:
                continue
            shares = item_duno_qty.get(er.item_code)
            total = item_total.get(er.item_code, 0)
            if shares and total > 0:
                for duno, planned_qty in shares.items():
                    mapped[duno] += qty * (planned_qty / total)
            else:
                mapped[""] += qty  # exact item with no planned match → unattributed

    return mapped


def _get_mp_excess_by_duno(mp_name):
    """Return {duno_mark_no: excess_kg} per drawing for a Material Planning document.

    Excess = SUM(batch_calc_qty - qty) over Mapped Material Mapping rows — the same
    'Difference in Kg' the Material Planning screen shows: weight mapped beyond what
    was planned (cross-item over-mapping) that the supplier must return.
    """
    from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
        MAPPED_BATCH_STATUSES,
    )

    excess = defaultdict(float)
    if not mp_name:
        return excess
    for r in frappe.get_all(
        "Material Planning Material Mapping",
        filters={"parent": mp_name, "batch_mapped": ["in", MAPPED_BATCH_STATUSES]},
        fields=["duno_mark_no", "batch_calc_qty", "qty"],
    ):
        excess[r.duno_mark_no or ""] += flt(r.batch_calc_qty) - flt(r.qty)
    return excess


def _sec_qty_for_reserved(full_sec_qty, reserved_qty, full_qty):
    """The piece count that goes with the weight still reserved.

    A row that has been partly transferred keeps the remainder of its reservation,
    so the transfer list must offer the piece count that goes with THAT weight --
    not the row's original count, which would offer four pieces against half a
    row's worth of steel. Where nothing has been taken the two are the same and
    this changes nothing."""
    full_sec_qty, reserved_qty, full_qty = flt(full_sec_qty), flt(reserved_qty), flt(full_qty)
    if full_qty <= 0 or full_sec_qty <= 0 or reserved_qty >= full_qty:
        return flt(full_sec_qty, 3)
    return flt(full_sec_qty * (reserved_qty / full_qty), 3)


def _get_mp_reserved_batches(mp_name, source_warehouse, supplier_warehouse, duno_filter=None):
    """Return SE item dicts for reserved batches in a Material Planning document.
    Includes sec_qty, dimensions, and unit_weight for each SE line.

    duno_filter: an optional iterable of DUNO/Mark Nos to restrict results to. A
    single Material Planning document can be shared across several Production
    Plans/Material Issue Plans (only some of its drawings pulled into any one of
    them at a time) -- without this, every reserved batch in the WHOLE Material
    Planning gets offered for transfer by every caller, including batches
    reserved for drawings that belong to a completely different, not-yet-planned
    job. Pass None (the default) for the old unfiltered whole-MP behaviour.
    """
    items = []
    duno_filter = set(duno_filter) if duno_filter else None

    # Cache item stock_uom and unit_weight to avoid N queries
    _uom_cache = {}
    _uwt_cache = {}

    def _stock_uom(item_code):
        if item_code not in _uom_cache:
            _uom_cache[item_code] = frappe.db.get_value("Item", item_code, "stock_uom") or "Kg"
        return _uom_cache[item_code]

    def _unit_weight(item_code):
        if item_code not in _uwt_cache:
            _uwt_cache[item_code] = flt(frappe.db.get_value("Item", item_code, "custom_unit_weight") or 0)
        return _uwt_cache[item_code]

    # From material_mapping: batch-assigned reserved rows
    mm_filters = {"parent": mp_name, "is_reserved": 1}
    if duno_filter:
        mm_filters["duno_mark_no"] = ["in", list(duno_filter)]
    rows = frappe.get_all(
        "Material Planning Material Mapping",
        filters=mm_filters,
        fields=[
            "item_code", "planned_item", "batch", "batch_calc_qty", "batch_sec_qty",
            "batch_length", "batch_width", "batch_thickness", "batch_unit_weight",
            "batch_parent_item_group", "parent_item_group", "sec_uom", "cnc_process",
            "reserve_without_dimensions", "reserved_qty",
        ],
    )
    for r in rows:
        if not r.batch:
            continue
        # Always use reserved_qty — it's the actual stock held back for this row.
        # batch_calc_qty is the full requirement which may exceed what's available (shortfall).
        qty = flt(r.reserved_qty)
        if qty <= 0:
            continue
        # When the batch belongs to a different item (cross-item mapping), planned_item
        # holds the batch's actual item — use it so ERPNext batch validation passes.
        se_item_code = r.planned_item or r.item_code
        items.append({
            "item_code": se_item_code,
            "batch_no": r.batch,
            # v15: use the batch_no field directly; Frappe creates the SBB on submit.
            "use_serial_batch_fields": 1,
            "qty": flt(qty, 3),
            "uom": _stock_uom(se_item_code),
            "s_warehouse": source_warehouse,
            "t_warehouse": supplier_warehouse,
            "custom_sec_qty": _sec_qty_for_reserved(r.batch_sec_qty, qty, r.batch_calc_qty),
            "custom_sec_uom": r.sec_uom or "",
            "custom_length": flt(r.batch_length, 3),
            "custom_width": flt(r.batch_width, 3),
            "custom_thickness": flt(r.batch_thickness, 3),
            "custom_unit_weight": flt(r.batch_unit_weight, 4),
            "custom_parent_item_group": r.batch_parent_item_group or r.parent_item_group or "",
            "cnc_process": 1 if r.cnc_process else 0,
        })

    # From available_raw_material: exact-match reserved rows
    arm_filters = {"parent": mp_name, "is_reserved": 1}
    if duno_filter:
        arm_filters["duno_mark_no"] = ["in", list(duno_filter)]
    rows2 = frappe.get_all(
        "Material Planning Available Raw Material",
        filters=arm_filters,
        fields=[
            "item_code", "batch_no", "reserved_qty", "available_qty", "required_qty",
            "sec_qty", "sec_uom", "length", "width", "thickness", "parent_item_group", "cnc_process",
        ],
    )
    for r in rows2:
        qty = flt(r.reserved_qty)   # available_qty is pre-reservation stock, not what's actually reserved
        if r.batch_no and qty > 0:
            items.append({
                "item_code": r.item_code,
                "batch_no": r.batch_no,
                # v15: use the batch_no field directly; Frappe creates the SBB on submit.
                "use_serial_batch_fields": 1,
                "qty": flt(qty, 3),
                "uom": _stock_uom(r.item_code),
                "s_warehouse": source_warehouse,
                "t_warehouse": supplier_warehouse,
                "custom_sec_qty": _sec_qty_for_reserved(r.sec_qty, qty, r.required_qty),
                "custom_sec_uom": r.sec_uom or "",
                "custom_length": flt(r.length, 3),
                "custom_width": flt(r.width, 3),
                "custom_thickness": flt(r.thickness, 3),
                "custom_unit_weight": _unit_weight(r.item_code),
                "custom_parent_item_group": r.parent_item_group or "",
                "cnc_process": 1 if r.cnc_process else 0,
            })

    return items


def _get_pp_planned_qty(pp_name, customer_drawing_number, duno_mark_no):
    """Return planned_qty from the Production Plan Item matching the given
    customer_drawing_number + duno_mark_no. Returns 0 when no match is found."""
    if not pp_name:
        return 0
    filters = {"parent": pp_name}
    if customer_drawing_number:
        filters["custom_customer_drawing_number"] = customer_drawing_number
    if duno_mark_no:
        filters["custom_duno_mark_no"] = duno_mark_no
    result = frappe.db.get_value("Production Plan Item", filters, "planned_qty")
    return flt(result)




def _get_supplier_wh_consumption_items(sco, supplier_warehouse=None):
    """Return SE consumption rows (issued FROM the supplier/WIP warehouse, no target) for
    all raw material still sitting at the supplier for this SCO.

    Counts the NET movement across the supplier warehouse boundary -- every submitted SE
    linked to this SCO (via custom_sco_ref or subcontracting_order) that puts stock INTO
    that warehouse adds, and every one that takes stock OUT subtracts. Filtering on
    stock_entry_type = 'Send to Subcontractor' instead (as this did originally) silently
    lost every batch routed through CNC: that material reaches the supplier on the second
    leg of a Stores -> CNC -> supplier hop, which is a 'Material Transfer', so it was
    never offered for consumption and stayed stranded at the supplier after the finished
    goods were booked. Netting also means an excess return (supplier -> stores) correctly
    reduces what is left to consume, and a partial re-run cannot double-count material an
    earlier Manufacture entry already consumed.

    Querying the SE Detail rows is reliable in Frappe v15 because SLE rows store batch
    tracking in Serial and Batch Bundles rather than in the batch_no column, making SLE
    batch_no lookups unreliable. Reading the warehouse's live stock instead would be
    simpler but wrong -- a supplier warehouse is shared across every order placed with
    that supplier, so it would pull in other jobs' material.

    supplier_warehouse defaults to sco.supplier_warehouse for backward compatibility, but
    callers should pass _get_sco_supplier_warehouse(sco) instead -- an Internal Job SCO's
    own field is never set (see that helper's docstring)."""
    supplier_warehouse = supplier_warehouse or sco.supplier_warehouse
    rows = frappe.db.sql(
        """
        SELECT sed.item_code, sed.batch_no,
               SUM(CASE WHEN sed.t_warehouse = %(wh)s THEN sed.qty
                        WHEN sed.s_warehouse = %(wh)s THEN -sed.qty
                        ELSE 0 END) AS qty
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE (se.custom_sco_ref = %(sco)s OR se.subcontracting_order = %(sco)s)
          AND se.docstatus = 1
          AND (sed.t_warehouse = %(wh)s OR sed.s_warehouse = %(wh)s)
        GROUP BY sed.item_code, sed.batch_no
        HAVING SUM(CASE WHEN sed.t_warehouse = %(wh)s THEN sed.qty
                        WHEN sed.s_warehouse = %(wh)s THEN -sed.qty
                        ELSE 0 END) > 0
        """,
        {"wh": supplier_warehouse, "sco": sco.name},
        as_dict=True,
    )
    return [
        {
            "item_code": r.item_code,
            "batch_no": r.batch_no,
            # v15: use the batch_no field directly; Frappe creates the SBB on submit.
            "use_serial_batch_fields": 1,
            "qty": flt(r.qty, 3),
            "uom": frappe.db.get_value("Item", r.item_code, "stock_uom") or "Kg",
            "s_warehouse": supplier_warehouse,
        }
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Work Order / Job Card mirror (SHARED_SCO_JC)
# All functions below are direct mirrors of the SCO/SOE equivalents above.
# Comment marker: SHARED_SCO_JC — grep this to find all paired functions.
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()


@frappe.whitelist()


@frappe.whitelist()


@frappe.whitelist()


@frappe.whitelist()


# ─── Private helpers (WO/JC) ─────────────────────────────────────────────────

def _build_jc_drawing_rows(wo, seq_idx):
    """Build custom_drawing_details rows for a new JC from the WO's drawing items.
    transferred_weight_kg starts at 0 — it is not yet backed by any Stock Entry —
    and is kept live afterwards by _refresh_wo_drawing_transferred_weights() on
    every transfer SE submit/cancel.
    # SHARED_SCO_JC: mirrors _build_soe_drawing_rows
    """
    rows = []
    for d in (wo.get("custom_drawing_items") or []):
        row = {
            "drawing":               d.drawing,
            "customer_drawing_number": d.customer_drawing_number or "",
            "duno_mark_no":          d.duno_mark_no or "",
            "sales_order":           d.get("sales_order") or "",
            "qty_to_manufacture":    flt(d.qty_to_manufacture, 3),
            "available_to_consume_nos": 0.0,
            "completed_qty_nos":     0.0,
            "transferred_weight_kg": 0.0,
        }
        if seq_idx == 1:
            row.update({
                "customer_provided_weight_kg": flt(d.customer_weight_kg, 3),
                "planned_weight_kg":           flt(d.total_weight_kg, 3),
            })
        else:
            row.update({
                "customer_provided_weight_kg": 0.0,
                "planned_weight_kg":           0.0,
            })
        rows.append(row)
    return rows


def _populate_jcs_for_wo(wo):
    """Populate custom_drawing_details on the Job Cards ERPNext created on WO submit.
    Idempotent — skips JCs that already have drawing detail rows.
    # SHARED_SCO_JC: mirrors _create_soes_for_sco
    """
    if not wo.get("custom_drawing_items"):
        return  # This WO was not created via the PP drawing flow — skip

    # Build operation → sequence_id map from WO operations
    wo_op_seq = {}
    for op in frappe.get_all(
        "Work Order Operation",
        filters={"parent": wo.name},
        fields=["operation", "sequence_id"],
    ):
        wo_op_seq[op.operation] = flt(op.sequence_id) or 0

    jcs = frappe.get_all(
        "Job Card",
        filters={"work_order": wo.name, "docstatus": 0},
        fields=["name", "operation", "sequence_id"],
    )
    if not jcs:
        return

    jcs_sorted = sorted(jcs, key=lambda x: (wo_op_seq.get(x.operation, 0), x.name))
    transferred_weight = flt(wo.get("custom_transferred_weight_kg") or 0)
    nos_by_drawing_from_sco = {}

    # Mixed-plan chain, reverse ordering: if a sibling SCO already finished its
    # subcontract portion before this WO's Job Cards were created, seed Op-1 from
    # ITS completion instead of this WO's own (irrelevant, likely-zero) raw-material
    # transfer. The forward ordering (SCO finishes AFTER these JCs already exist) is
    # handled live by _push_sco_completion_to_wo on the SCO's last SOE submit.
    sco_row = frappe.db.get_value(
        "Subcontracting Order",
        {"custom_production_plan": wo.production_plan, "docstatus": ["!=", 2]},
        ["name", "custom_all_ops_complete"],
        as_dict=True,
    )
    if sco_row and sco_row.custom_all_ops_complete:
        last_soe_name = frappe.db.get_value(
            "Supplier Operation Entry",
            {"subcontracting_order": sco_row.name, "docstatus": 1},
            "name", order_by="sequence_id desc",
        )
        if last_soe_name:
            last_soe = frappe.get_doc("Supplier Operation Entry", last_soe_name)
            transferred_weight = flt(last_soe.total_consumed_kg, 3)
            nos_by_drawing_from_sco = {
                r.drawing: flt(r.completed_qty_nos, 3)
                for r in (last_soe.drawing_details or []) if r.drawing
            }

    for seq_idx, jc_info in enumerate(jcs_sorted, start=1):
        jc_doc = frappe.get_doc("Job Card", jc_info.name)

        # Idempotent check
        if frappe.db.exists(
            "SOE Drawing Detail",
            {"parent": jc_info.name, "parentfield": "custom_drawing_details"},
        ):
            continue

        drawing_rows = _build_jc_drawing_rows(wo, seq_idx)
        for row in drawing_rows:
            jc_doc.append("custom_drawing_details", row)

        if seq_idx == 1:
            jc_doc.custom_available_to_consume_kg = flt(transferred_weight, 3)
            if nos_by_drawing_from_sco:
                for row in jc_doc.custom_drawing_details:
                    row.available_to_consume_nos = flt(
                        nos_by_drawing_from_sco.get(row.drawing or "", 0.0), 3
                    )

        jc_doc.custom_total_available_nos  = flt(
            sum(flt(r.available_to_consume_nos) for r in jc_doc.custom_drawing_details), 3
        )
        jc_doc.custom_total_completed_nos  = 0.0
        jc_doc.flags.ignore_validate = True
        jc_doc.save(ignore_permissions=True)
