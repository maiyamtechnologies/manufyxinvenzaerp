import re
import frappe
from frappe import _
from frappe.utils import flt, now
from manufyxinvenzaerp.production_management.doctype.material_planning.material_planning import (
    _get_batch_reserved_by_others,
    _get_batch_total_stock,
)
from manufyxinvenzaerp.utils.dimension_formula import calculate_qty, calculate_sec_qty_from_qty, check_missing_fields
from manufyxinvenzaerp.utils.reference_copy import copy_reference_fields_if_blank

REFERENCE_FIELDS = ["custom_drawing", "custom_duno_mark_no", "custom_customer_drawing_number", "custom_sales_order"]


@frappe.whitelist()
def get_pr_item_uom(doctype, txt, searchfield, start, page_len, filters):
    item_code = (filters if isinstance(filters, dict) else frappe.parse_json(filters)).get("item_code")
    if not item_code:
        return []
    return frappe.db.sql(
        """
        SELECT uom FROM `tabUOM Conversion Detail`
        WHERE parent = %s AND uom LIKE %s
        UNION
        SELECT stock_uom FROM `tabItem` WHERE name = %s AND stock_uom LIKE %s
        LIMIT %s
        """,
        (item_code, f"%{txt}%", item_code, f"%{txt}%", int(page_len)),
    )


def validate_purchase_receipt(doc, method):
    for row in doc.items:
        _copy_from_po_item(row)
        _recalculate_qty(row)
        _check_missing_fields(row, throw=False)
    doc.custom_total_weight = sum(
        row.qty for row in doc.items
        if row.custom_parent_item_group in ("Structurals", "Plates")
    )


def before_submit_purchase_receipt(doc, method):
    for row in doc.items:
        _check_missing_fields(row, throw=True)


def before_insert_batch(doc, method):
    """Set custom batch name and store dimensions when batch is auto-created."""
    if doc.reference_doctype == "Purchase Receipt" and doc.reference_name:
        _setup_batch_from_purchase_receipt(doc)
    elif doc.reference_doctype == "Stock Entry" and doc.reference_name:
        _setup_batch_from_stock_entry(doc)


def _row_awaiting_batch(rows):
    """The document row the batch being created right now belongs to.

    ERPNext makes one batch per stock ledger entry and only then writes the Serial
    and Batch Bundle back onto the row it came from, one row at a time. So while a
    batch is being inserted, every row already dealt with carries a bundle and the
    one being dealt with does not -- which makes "the first row of this item with no
    bundle yet" an exact answer.

    It replaces counting how many batches already exist for this document and using
    the count as an index. That was only ever a guess, and it guessed wrong whenever
    the batches were not created in row order or a row already had a batch of its
    own: the batch then took another line's Length and Width, and nothing said so.
    A row that has been dealt with can never be picked here, however the batches
    were ordered.

    Falls back to the first row when every row already has a bundle, so a batch
    created outside that sequence still gets this item's dimensions rather than
    none at all."""
    if not rows:
        return None
    for row in rows:
        if not row.get("serial_and_batch_bundle"):
            return row
    return rows[0]


def _setup_batch_from_purchase_receipt(doc):
    pr_items = frappe.db.get_all(
        "Purchase Receipt Item",
        filters={"parent": doc.reference_name, "item_code": doc.item},
        fields=[
            "name", "serial_and_batch_bundle",
            "custom_thickness", "custom_length", "custom_width", "custom_sec_qty",
            "custom_sec_uom", "custom_parent_item_group",
        ],
        order_by="idx asc",
    )
    pr_item = _row_awaiting_batch(pr_items)
    if not pr_item:
        return

    batch_prefix = frappe.db.get_value("Item", doc.item, "custom_batch_prefix")
    if not batch_prefix:
        return

    receipt_suffix = _get_receipt_suffix(doc.reference_name)
    parts = [batch_prefix]
    if pr_item.custom_thickness:
        parts.append(f"T{int(pr_item.custom_thickness)}")
    if pr_item.custom_length:
        parts.append(f"L{int(pr_item.custom_length)}")
    if pr_item.custom_width:
        parts.append(f"W{int(pr_item.custom_width)}")
    parts.append(f"R{receipt_suffix}")

    batch_id = "-".join(parts)
    counter = 1
    base_id = batch_id
    while frappe.db.exists("Batch", batch_id):
        counter += 1
        batch_id = f"{base_id}-{counter}"

    doc.batch_id = batch_id
    doc.custom_thickness = pr_item.custom_thickness
    doc.custom_length = pr_item.custom_length
    doc.custom_width = pr_item.custom_width
    doc.custom_sec_qty = pr_item.custom_sec_qty
    doc.custom_sec_uom = pr_item.custom_sec_uom

    # Guard: Structurals/Plates batches are always Nos-tracked. A batch silently
    # created with Sec Qty 0 breaks Kg -> Nos allocation in Material Planning
    # (_alloc_sec_qty) with no visible error until someone notices downstream.
    # before_submit_purchase_receipt already requires Sec Qty > 0 on the PR line
    # itself, so landing here means _row_awaiting_batch matched a line that has no
    # piece count -- which should not be reachable. Fail loudly rather than silently
    # persist a corrupt batch.
    if pr_item.custom_parent_item_group in ("Structurals", "Plates") and not flt(pr_item.custom_sec_qty):
        frappe.throw(
            _(
                "Cannot create batch {0} for item {1}: Sec Qty (Nos) resolved to 0 while "
                "matching Purchase Receipt {2}. This usually means two or more rows for this "
                "item share identical Length/Width/Thickness — give them distinct dimensions "
                "(or split the receipt) so each batch can be matched to the correct row."
            ).format(batch_id, doc.item, doc.reference_name)
        )


def _setup_batch_from_stock_entry(doc):
    """Set batch name and dimensions for batches created from Repack or Material Receipt SE."""
    se_type = frappe.db.get_value("Stock Entry", doc.reference_name, "stock_entry_type")
    if se_type not in ("Repack", "Material Receipt"):
        return

    # Read from the database rather than the Stock Entry document: the bundle that
    # says a row has been dealt with is written straight to the row with db_set,
    # which a document already in memory would not show.
    rows = frappe.db.get_all(
        "Stock Entry Detail",
        filters={"parent": doc.reference_name, "item_code": doc.item},
        fields=[
            "name", "serial_and_batch_bundle", "is_finished_item",
            "custom_thickness", "custom_length", "custom_width", "custom_sec_qty",
            "custom_sec_uom", "custom_parent_item_group", "custom_source_mip_excess_row",
            "custom_existing_supplier_invoice_no", "custom_existing_invoice_wt",
            "custom_existing_inward_date",
        ],
        order_by="idx asc",
    )
    matching_rows = [
        r for r in rows
        if se_type == "Material Receipt" or r.is_finished_item
    ]
    target_row = _row_awaiting_batch(matching_rows)
    if not target_row:
        return

    batch_prefix = frappe.db.get_value("Item", doc.item, "custom_batch_prefix")
    if not batch_prefix:
        return

    t = int(flt(target_row.custom_thickness)) if target_row.custom_thickness else None
    l = int(flt(target_row.custom_length)) if target_row.custom_length else None
    w = int(flt(target_row.custom_width)) if target_row.custom_width else None
    suffix = _get_se_suffix(doc.reference_name)

    parts = [batch_prefix]
    if t:
        parts.append(f"P{t}")
    if l:
        parts.append(f"L{l}")
    if w:
        parts.append(f"W{w}")
    parts.append(f"SR{suffix}")

    batch_id = "-".join(parts)
    counter = 1
    base_id = batch_id
    while frappe.db.exists("Batch", batch_id):
        counter += 1
        batch_id = f"{base_id}-{counter}"

    doc.batch_id = batch_id
    doc.custom_thickness = flt(target_row.custom_thickness)
    doc.custom_length = flt(target_row.custom_length)
    doc.custom_width = flt(target_row.custom_width)
    doc.custom_sec_qty = flt(target_row.custom_sec_qty)
    doc.custom_sec_uom = target_row.custom_sec_uom
    # Excess-material-return Stock Entries (create_mip_excess_return_entry) tag
    # each item with the SCO Excess Material Item row it came from, so Excess
    # Material Mapping can trace a reservation back to it -- carry that onto
    # the batch the same way every other custom_* dimension field is copied.
    doc.custom_source_mip_excess_row = target_row.get("custom_source_mip_excess_row") or ""

    group = (target_row.get("custom_parent_item_group") or "").strip()
    if group in {"Structurals", "Plates"}:
        doc.custom_existing_supplier_invoice_no = target_row.get("custom_existing_supplier_invoice_no") or ""
        doc.custom_existing_invoice_wt = flt(target_row.get("custom_existing_invoice_wt"))
        doc.custom_existing_inward_date = target_row.get("custom_existing_inward_date")


def _get_receipt_suffix(pr_name):
    """Extract last 3 digits from the numeric part of a receipt name (e.g. MAT-PRE-2024-00010 → '010')."""
    match = re.search(r"(\d+)$", pr_name)
    if match:
        return match.group(1)[-3:].zfill(3)
    return pr_name[-3:] if pr_name else "000"


def _get_se_suffix(se_name):
    """Extract last 3 digits from the numeric part of a Stock Entry name."""
    match = re.search(r"(\d+)$", se_name)
    if match:
        return match.group(1)[-3:].zfill(3)
    return se_name[-3:] if se_name else "001"


def _copy_from_po_item(row):
    """Copy dimension + reference fields from the linked PO Item when a PR is created from a PO."""
    fields = ["custom_length", "custom_width", "custom_thickness", "custom_sec_qty", *REFERENCE_FIELDS]
    copy_reference_fields_if_blank(row, "Purchase Order Item", "purchase_order_item", fields)


def _recalculate_qty(row):
    group = row.custom_parent_item_group
    if group in ("Structurals", "Plates"):
        qty = calculate_qty(
            group, row.custom_length, row.custom_width, row.custom_thickness,
            row.custom_unit_weight, row.custom_sec_qty,
        )
        if qty is not None:
            row.qty = qty
    elif group == "Nuts and Bolts":
        sec_qty = calculate_sec_qty_from_qty(row.custom_unit_weight, row.qty)
        if sec_qty is not None:
            row.custom_sec_qty = sec_qty


def _check_missing_fields(row, throw):
    check_missing_fields(row, throw)


# ── Material Planning auto-allocation ────────────────────────────────────────

def _resolve_pr_batch_no(pr_item):
    """Purchase Receipt Items in this instance don't reliably carry batch_no
    directly (items are set to auto-create a new batch on receipt, and this
    environment leaves batch_no blank on the row) — the actual batch lives on
    the row's Serial and Batch Bundle. Resolve it from there, falling back to
    batch_no for any PR created the traditional way."""
    if pr_item.batch_no:
        return pr_item.batch_no
    bundle = pr_item.get("serial_and_batch_bundle")
    if not bundle:
        return ""
    return frappe.db.get_value("Serial and Batch Entry", {"parent": bundle}, "batch_no") or ""


@frappe.whitelist()
def get_mp_for_pr(pr_name):
    """Trace PR → PO → MR → Material Planning. Returns list of MP names linked to this PR."""
    if not frappe.has_permission("Material Planning", "read"):
        frappe.throw(_("Not permitted to view Material Planning links"), frappe.PermissionError)
    rows = frappe.db.sql(
        """
        SELECT DISTINCT mr.custom_material_planning
        FROM `tabPurchase Receipt Item`  pri
        JOIN `tabPurchase Order Item`    poi ON poi.name  = pri.purchase_order_item
        JOIN `tabMaterial Request Item`  mri ON mri.name  = poi.material_request_item
        JOIN `tabMaterial Request`       mr  ON mr.name   = mri.parent
        WHERE pri.parent = %(pr)s
          AND mr.custom_material_planning IS NOT NULL
          AND mr.custom_material_planning != ''
        """,
        {"pr": pr_name},
    )
    return [r[0] for r in rows if r[0]]


@frappe.whitelist()
def diagnose_mp_allocation(pr_name):
    """Why a receipt did, or did not, reach a Material Planning.

    Allocation runs off a chain of four links -- receipt line to order line to request
    line to the request's own plan -- and get_mp_for_pr is a single join across all of
    them. When any link is missing the join returns nothing, allocation never runs, and
    nothing anywhere says so: the receipt submits, the popup that would list the
    allocated batches sees an empty list and returns early, and the plan still shows the
    material as unavailable. That silence is the whole difficulty in diagnosing it after
    the fact.

    This walks the same chain one line at a time and reports the first link that breaks,
    so the answer is "the purchase order was not raised from the request" rather than
    "nothing happened"."""
    if not frappe.has_permission("Purchase Receipt", "read", doc=pr_name):
        frappe.throw(_("Not permitted to read this Purchase Receipt"), frappe.PermissionError)

    broken, plans = [], set()
    for row in frappe.get_all(
        "Purchase Receipt Item", filters={"parent": pr_name},
        fields=["item_code", "purchase_order_item"], order_by="idx",
    ):
        if not row.purchase_order_item:
            broken.append((row.item_code, _("this line was not raised from a Purchase Order")))
            continue
        mr_item = frappe.db.get_value("Purchase Order Item", row.purchase_order_item,
                                      "material_request_item")
        if not mr_item:
            broken.append((row.item_code, _("its Purchase Order line was not raised from a Material Request")))
            continue
        mr = frappe.db.get_value("Material Request Item", mr_item, "parent")
        plan = frappe.db.get_value("Material Request", mr, "custom_material_planning") if mr else None
        if not plan:
            broken.append((row.item_code, _("Material Request {0} is not linked to a Material Planning").format(mr or "?")))
            continue
        plans.add(plan)

    return {"plans": sorted(plans), "broken": broken}


@frappe.whitelist()
def retry_mp_allocation(pr_name):
    """Run the allocation again for a receipt that is already submitted.

    The message shown when allocation fails has always told people to "retry the
    allocation manually from the Material Planning document", and there was nowhere to
    do it: the only caller of allocate_pr_stock_to_mp was the submit hook. Recovering
    meant cancelling and re-receiving stock that had physically arrived.

    Safe to run more than once. allocate_pr_stock_to_mp rebuilds its candidates from
    unavailable_items as that table currently stands, and a row already covered is gone
    from it -- so a second run over the same receipt has nothing left to match."""
    if not frappe.has_permission("Material Planning", "write"):
        frappe.throw(_("Not permitted to update Material Planning"), frappe.PermissionError)
    if frappe.db.get_value("Purchase Receipt", pr_name, "docstatus") != 1:
        frappe.throw(_("Only a submitted Purchase Receipt can be allocated."))

    report = diagnose_mp_allocation(pr_name)
    results = []
    for mp_name in report["plans"]:
        try:
            added = allocate_pr_stock_to_mp(pr_name, mp_name) or {}
            failed_items = []
        except Exception:
            # Same rule as the submit hook: a line the plan refuses costs
            # that line only. Retrying used to re-raise the first refusal and
            # allocate nothing at all, which made the recovery button useless
            # in exactly the case it exists for.
            frappe.log_error(
                title=f"Retry allocation failed for {pr_name} -> {mp_name}",
                message=frappe.get_traceback(),
            )
            added, failed_items = _allocate_pr_items_individually(pr_name, mp_name)
        results.append(dict(added, material_planning=mp_name, failed_items=failed_items))
    frappe.db.commit()
    report["results"] = results
    return report


def _pr_dimensions_match(pr_item, mp_row):
    """True when a purchased line arrived in exactly the size the requirement
    row asks for -- the same strict all-three-dimensions rule
    production_plan.get_sbb_available_qty applies when matching batches on the
    manual "check stock" path (material_planning.move_to_exact_match).

    Only such a receipt is a genuine Exact Match. Available Raw Materials
    carries a single Length/Width/Thickness precisely because the requirement
    and the batch are the same size there; a receipt in any other size has no
    field on that table to record both, so it belongs in Material Mapping.
    """
    return (
        flt(pr_item.custom_length) == flt(mp_row.length)
        and flt(pr_item.custom_width) == flt(mp_row.width)
        and flt(pr_item.custom_thickness) == flt(mp_row.thickness)
    )


def _receivable_qty(pr_item, batch_total_qty, batch_reserved_qty):
    """How much of a received line this plan may actually claim.

    Normally the whole line: the batch was created by this very receipt and
    nothing else has touched it, so free stock and received qty are the same
    number. They come apart when another plan reserved part of the batch
    between the receipt and this allocation, and then claiming the full line
    writes Material Mapping rows adding up to more of the batch than exists --
    which _validate_batch_calc_qty refuses, taking the WHOLE receipt's
    allocation down with it rather than just the surplus.

    Capping here turns that into the ordinary short-delivery outcome the
    caller already handles: the plan takes what is free and the remainder
    stays a blank-batch "Not Mapped" row to purchase or map by hand.

    A batch with no stock in the plan's warehouse is not capped -- there is
    nothing to divide up and _validate_batch_calc_qty skips such rows too
    (already transferred out, or received elsewhere), so a cap of 0 would
    block a legitimate allocation instead of protecting one.
    """
    received_qty = flt(pr_item.qty)
    if flt(batch_total_qty) <= 0:
        return received_qty
    free_qty = flt(max(0.0, flt(batch_total_qty) - flt(batch_reserved_qty)), 3)
    return flt(min(received_qty, free_qty), 3)


def _build_mapping_row(
    mp_row,
    *,
    alloc_qty,
    ratio,
    pr_item,
    pr_name,
    purchased_item_code,
    batch_no,
    purchased_item_data,
    batch_total_qty,
    batch_reserved_qty,
):
    """Build a fully-populated Material Mapping row for a received batch that
    does not dimensionally match the requirement -- either because an alternate
    item was bought, or because the original item was bought at a different
    (typically standard stock) size via a Consolidate Item line.

    The requirement's own Length/Width/Thickness stay on the row's plain
    fields while the batch's go on the batch_* fields, so the size actually
    needed survives alongside the size actually purchased.

    Qty is the part of the requirement THIS batch covers, not the whole
    requirement. When a receipt covers a row only partly the caller splits the
    remainder off into its own blank-batch row, so writing the full figure here
    counted the shortfall twice -- and because a reserve_without_dimensions row
    reserves exactly its Qty, _validate_batch_calc_qty then refused the save
    ("Required Qty 30 Kg, Free stock 10 Kg") and took the entire allocation
    down with it: the receipt submitted, the plan kept every row unmapped, and
    the only trace was an Error Log entry. Any partly-received consolidated
    purchase hit this.
    """
    covered_qty = flt(min(flt(alloc_qty), flt(mp_row.qty)), 3)
    covered_ratio = (covered_qty / flt(mp_row.qty)) if flt(mp_row.qty) else 1.0
    return {
        "item_number":             mp_row.item_number,
        "sales_order":             mp_row.sales_order,
        "item_code":               mp_row.item_code,
        "item_name":               mp_row.item_name,
        "bom_no":                  mp_row.bom_no,
        "drawing":                 mp_row.drawing,
        "duno_mark_no":            mp_row.duno_mark_no,
        "customer_drawing_number": mp_row.customer_drawing_number,
        "qty":                     covered_qty,
        "uom":                     mp_row.uom,
        "sec_qty":                 flt(flt(mp_row.sec_qty) * covered_ratio, 3),
        "sec_uom":                 mp_row.sec_uom,
        "parent_item_group":       mp_row.parent_item_group,
        "length":                  mp_row.length,
        "width":                   mp_row.width,
        "thickness":               mp_row.thickness,
        "unit_weight":             mp_row.unit_weight,
        "batch":                   batch_no,
        "planned_item":            purchased_item_code,
        "batch_mapped":            "Mapped" if batch_no else "Not Mapped",
        "batch_parent_item_group": purchased_item_data.get("custom_parent_item_group") or "",
        "batch_length":            flt(pr_item.custom_length),
        "batch_width":             flt(pr_item.custom_width),
        "batch_thickness":         flt(pr_item.custom_thickness),
        "batch_unit_weight":       flt(purchased_item_data.get("custom_unit_weight")),
        "batch_sec_qty":           flt(flt(pr_item.custom_sec_qty) * ratio, 3),
        "batch_calc_qty":          flt(alloc_qty, 3),
        "batch_total_qty":         flt(batch_total_qty, 3),
        "batch_reserved_qty":      flt(batch_reserved_qty, 3),
        "batch_free_qty":          flt(max(0.0, batch_total_qty - batch_reserved_qty), 3),
        "purchase_receipt":        pr_name,
        # Dimensions differ by definition on this path -- reserve by weight
        # rather than requiring a dimension match, same as picking this batch by
        # hand via "Assign Batch" with that option enabled. Sec Nos is derived
        # from that weight and stays fractional; whole-piece rounding happens at
        # transfer time on the Material Issue Plan.
        "reserve_without_dimensions": 1,
    }


def _fill_mapping_row_from_receipt(
    mp_row,
    *,
    alloc_qty,
    ratio,
    pr_item,
    pr_name,
    purchased_item_code,
    batch_no,
    purchased_item_data,
    batch_total_qty,
    batch_reserved_qty,
):
    """Write a received batch onto a Material Mapping row that was still
    waiting for one: the requirement's own dimensions stay on the row's plain
    fields and the batch's go on the batch_* fields -- the same shape
    _build_mapping_row produces, applied to a row that already exists.

    Qty is the caller's business, not this function's: when the receipt covers
    the row only in part, the caller shrinks it here and adds a second
    blank-batch row for the remainder.
    """
    mp_row.batch                   = batch_no
    mp_row.planned_item            = purchased_item_code
    mp_row.batch_mapped            = "Mapped" if batch_no else "Not Mapped"
    mp_row.batch_parent_item_group = purchased_item_data.get("custom_parent_item_group") or ""
    mp_row.batch_length            = flt(pr_item.custom_length)
    mp_row.batch_width             = flt(pr_item.custom_width)
    mp_row.batch_thickness         = flt(pr_item.custom_thickness)
    mp_row.batch_unit_weight       = flt(purchased_item_data.get("custom_unit_weight"))
    mp_row.batch_sec_qty           = flt(flt(pr_item.custom_sec_qty) * ratio, 3)
    mp_row.batch_calc_qty          = flt(alloc_qty, 3)
    mp_row.batch_total_qty         = flt(batch_total_qty, 3)
    mp_row.batch_reserved_qty      = flt(batch_reserved_qty, 3)
    mp_row.batch_free_qty          = flt(max(0.0, batch_total_qty - batch_reserved_qty), 3)
    mp_row.purchase_receipt        = pr_name
    # Unlike _build_mapping_row's path, a receipt CAN land here in the exact
    # size the row asks for (the row is only in this table because a re-check
    # moved it, not because the size differs) -- so only waive the dimension
    # check when the sizes actually differ.
    mp_row.reserve_without_dimensions = 0 if _pr_dimensions_match(pr_item, mp_row) else 1


@frappe.whitelist()
def allocate_pr_stock_to_mp(pr_name, mp_name, only_items=None):
    """
    Allocate batches received on a PR into the linked Material Planning.
    - Received in the requirement's own dimensions → Available Raw Materials (Exact Match)
    - Received in any other size, or as an alternate item → Material Mapping (Partial Stock)

    Routing is decided per requirement row by actual dimensions
    (_pr_dimensions_match), not by whether the original or an alternate item
    code was bought: buying the right item code at a standard stock size (the
    normal outcome of a Consolidate Item purchase, e.g. ISMB400 ordered in
    4000 mm bars to cover 6936 mm requirements) is NOT an exact match, and
    recording it as one would overwrite the required size with the purchased
    one -- Available Raw Materials has only a single set of dimensions.

    "Alternate item purchased" covers both Unavailable Item's own per-row
    alternate_item AND Material Planning Consolidate Item's alternate_item
    (a bulk substitution decision made once for the whole deduped-by-item_code
    consolidated line) -- either way the purchased batch lands in Material
    Mapping against every original Unavailable Item row it substitutes for.

    The matched Unavailable Items row is removed once fully covered; if the PR
    received less than the row's required qty, the row is kept with its qty
    (and proportional Sec Qty) reduced to just the remaining shortfall.

    No item/batch/duno-keyed dedup is applied when appending Available Raw
    Materials/Material Mapping rows -- a drawing can genuinely need the SAME
    item from the SAME batch more than once (e.g. two different-length pieces
    of ISA100 on one duno), and such a key previously collapsed those into one,
    silently discarding the second Unavailable Item row (still marked
    fulfilled and removed by the reconcile step below, since _consume() runs
    before any such check) with no Available Raw Materials/Material Mapping
    row ever created for it -- a real data-loss bug found on MP-2026-00010
    (18 rows, ~132.9 Kg, across 13 duno+item combinations). Re-running this
    function for the same PR is naturally idempotent without a key anyway:
    each call rebuilds its match candidates from mp.unavailable_items as it
    currently stands, and a fully-fulfilled row is already gone from that
    table by the time any second call could happen.

    only_items limits the pass to the named Purchase Receipt Item rows. The
    whole receipt is allocated in ONE save, so a single row the plan refuses
    discards the allocation of every other item on it as well -- five items
    received, four of them perfectly allocatable, and the plan keeps all five
    unmapped (PR-26-00008). _allocate_pr_items_individually uses this to
    retry the receipt one line at a time under a savepoint each, so the lines
    that can land still do.
    """
    pr = frappe.get_doc("Purchase Receipt", pr_name)
    mp = frappe.get_doc("Material Planning", mp_name)
    only_items = set(only_items or [])

    # Index MP unavailable_items two ways: precise (item_code, duno_mark_no) when the
    # PR item carries a DUNO reference, and a legacy item-code-only fallback for PRs
    # created before this reference chain existed (no custom_duno_mark_no to match on).
    by_alternate, by_alternate_any = {}, {}
    by_original, by_original_any = {}, {}
    unavail_by_item_code = {}
    for row in (mp.unavailable_items or []):
        duno = row.duno_mark_no or ""
        if row.alternate_item:
            by_alternate.setdefault((row.alternate_item, duno), []).append(row)
            by_alternate_any.setdefault(row.alternate_item, []).append(row)
        by_original.setdefault((row.item_code, duno), []).append(row)
        by_original_any.setdefault(row.item_code, []).append(row)
        unavail_by_item_code.setdefault(row.item_code, []).append(row)

    # Consolidate Item's own Alternate Item section (bulk, whole-consolidated-
    # line purchasing decision, set once rather than per original drawing row)
    # -- when set, a purchase of that alternate item must fan out across every
    # Unavailable Item row sharing the Consolidate Item row's own item_code
    # (i.e. everything that got deduped into it), the same way Unavailable
    # Item's own per-row alternate_item already does. Consolidate Item never
    # carries a DUNO (it's deduped across drawings), so this only ever
    # participates in the item-code-only ("_any"/sequential) matching below.
    by_consolidate_alt_any = {}
    for c_row in (mp.consolidate_items or []):
        if c_row.alternate_item:
            by_consolidate_alt_any.setdefault(c_row.alternate_item, []).extend(
                unavail_by_item_code.get(c_row.item_code, [])
            )

    # Fallback candidates: Material Mapping rows still waiting for a batch.
    #
    # Unavailable Items is where a requirement waiting to be purchased is
    # SUPPOSED to sit, but it is not the only place one can be found by the
    # time the goods arrive -- re-running "Check Stock Availability" moves
    # batch-item requirements into Material Mapping (blank batch, "Not
    # Mapped") no matter how far along their purchase already is. Matching
    # only against Unavailable Items meant such a receipt allocated nothing
    # whatsoever, silently: no error, no message, and a plan still showing
    # every row unmapped with the stock sitting in the warehouse
    # (MP-2026-00012 / PR-26-00005).
    #
    # These rows are filled IN PLACE rather than appended to, because unlike
    # an Unavailable Item -- which is consumed and replaced by a new row --
    # the requirement already lives in this table; appending would duplicate
    # it. Rows already carrying a batch, reserved rows, and rows fulfilled by
    # the virtual-excess/excess-material paths are never candidates.
    mm_by_duno, mm_by_any, mm_by_item_code = {}, {}, {}
    for row in (mp.material_mapping or []):
        if row.batch or row.is_reserved or row.is_virtual_excess or row.excess_material:
            continue
        # A blank-batch row this very receipt already stamped is its own
        # shortfall marker -- what it could NOT cover. Running the allocation
        # again (the "Retry Allocation" button does exactly that) must not
        # hand the same batch out a second time: the plan would then claim
        # more of it than was ever received.
        if row.purchase_receipt == pr_name:
            continue
        mm_by_duno.setdefault((row.item_code, row.duno_mark_no or ""), []).append(row)
        mm_by_any.setdefault(row.item_code, []).append(row)
        mm_by_item_code.setdefault(row.item_code, []).append(row)

    # A Consolidate Item's bulk alternate-item decision fans out over Material
    # Mapping rows exactly as it does over Unavailable Items ones above.
    mm_by_consolidate_alt_any = {}
    for c_row in (mp.consolidate_items or []):
        if c_row.alternate_item:
            mm_by_consolidate_alt_any.setdefault(c_row.alternate_item, []).extend(
                mm_by_item_code.get(c_row.item_code, [])
            )

    added_exact   = 0
    added_mapping = 0
    filled_mapping = 0
    fulfilled_row_names  = set()
    remaining_qty_by_row = {}  # row.name -> qty still short after this PR's receipts
    # Material Mapping rows share the two trackers above so _split_allocation
    # sequences across them the same way, but they are NOT Unavailable Items:
    # the reconcile step below must not count them, and never sees them since
    # it only walks mp.unavailable_items.
    mapping_row_names = set()
    QTY_EPSILON = 0.001  # matches the 3-decimal rounding used throughout this table

    def _consume(mp_row, received_qty):
        remaining = flt(remaining_qty_by_row.get(mp_row.name, flt(mp_row.qty)) - received_qty, 3)
        if remaining <= QTY_EPSILON:
            fulfilled_row_names.add(mp_row.name)
            remaining_qty_by_row.pop(mp_row.name, None)
        else:
            remaining_qty_by_row[mp_row.name] = remaining

    def _split_allocation(matched_rows, received_qty, sequential):
        """Client change request Phase 2.5: a consolidated purchase line (no
        DUNO to disambiguate — e.g. one bought via a Material Planning
        Consolidate Item row that summed several drawings' requirements for
        the same item_code) matching MORE THAN ONE Unavailable Item row must
        split its received qty SEQUENTIALLY across those rows — fill the
        first (by original document order/idx) fully, then the next, and so
        on — rather than crediting the full received qty to every matched row
        independently (which double/triple-counts the same physical receipt).
        Any dimension-driven shortfall naturally lands on the last row(s) in
        the sequence, since earlier rows are always filled first. A single
        match, or a precise item+DUNO match, is unaffected — same behavior as
        before (the full received qty applies to that one row).

        Rows already filled by an EARLIER line of the same receipt are skipped.
        A supplier substituting sizes delivers one item across several PR lines
        (7000 mm unavailable, so 2 x 4000 mm plus a 6900 mm), and each line runs
        this function again over the same match list; without that skip, a row
        _consume() already completed is absent from remaining_qty_by_row and so
        falls back to its FULL original qty, silently getting a second helping
        while later rows receive nothing."""
        if not sequential or len(matched_rows) <= 1:
            return [(mp_row, flt(received_qty)) for mp_row in matched_rows]

        allocations = []
        remaining_receipt = flt(received_qty)
        for mp_row in sorted(matched_rows, key=lambda r: r.idx):
            if remaining_receipt <= QTY_EPSILON:
                break
            if mp_row.name in fulfilled_row_names:
                continue
            row_requirement = flt(remaining_qty_by_row.get(mp_row.name, mp_row.qty))
            alloc_qty = flt(min(remaining_receipt, row_requirement), 3)
            if alloc_qty <= 0:
                continue
            allocations.append((mp_row, alloc_qty))
            remaining_receipt = flt(remaining_receipt - alloc_qty, 3)
        return allocations

    # Batch-resolve the PO Item -> MR Item -> MR chain for every PR row up
    # front (3 queries total) instead of 3 frappe.db.get_value calls per row
    # (Report 4 Finding D-04) -- the loop below does the same lookups as
    # before, just against these pre-fetched dicts.
    poi_names = list({pr_item.purchase_order_item for pr_item in pr.items if pr_item.purchase_order_item})
    poi_to_mri = {}
    if poi_names:
        for rec in frappe.get_all(
            "Purchase Order Item", filters={"name": ["in", poi_names]}, fields=["name", "material_request_item"]
        ):
            poi_to_mri[rec.name] = rec.material_request_item

    mri_names = list({v for v in poi_to_mri.values() if v})
    mri_to_mr = {}
    if mri_names:
        for rec in frappe.get_all(
            "Material Request Item", filters={"name": ["in", mri_names]}, fields=["name", "parent"]
        ):
            mri_to_mr[rec.name] = rec.parent

    mr_names = list({v for v in mri_to_mr.values() if v})
    mr_to_mp = {}
    if mr_names:
        for rec in frappe.get_all(
            "Material Request", filters={"name": ["in", mr_names]}, fields=["name", "custom_material_planning"]
        ):
            mr_to_mp[rec.name] = rec.custom_material_planning

    for pr_item in pr.items:
        if only_items and pr_item.name not in only_items:
            continue
        if not pr_item.purchase_order_item:
            continue

        # Confirm this PR item traces back to our MP
        mr_item_name = poi_to_mri.get(pr_item.purchase_order_item)
        if not mr_item_name:
            continue
        mr_name = mri_to_mr.get(mr_item_name)
        if not mr_name:
            continue
        item_mp = mr_to_mp.get(mr_name)
        if item_mp != mp_name:
            continue

        item_code = pr_item.item_code
        batch_no  = _resolve_pr_batch_no(pr_item)
        pr_duno   = pr_item.get("custom_duno_mark_no") or ""

        # When the PR item knows its DUNO, only allocate against that exact drawing's
        # row — no fallback fan-out (a miss here should surface as unallocated, not
        # mis-allocated to a different drawing's shortage). Only fall back to matching
        # by item_code alone when the PR item has no DUNO reference at all -- either an
        # in-flight PR created before this field existed, or (client change request
        # Phase 2.5) a consolidated purchase line that intentionally spans several
        # drawings' worth of the same item_code and must split sequentially across them.
        sequential = not pr_duno

        if pr_duno:
            matched_alternate = by_alternate.get((item_code, pr_duno), [])
            matched_original  = by_original.get((item_code, pr_duno), [])
        else:
            matched_alternate = list(by_alternate_any.get(item_code, []))
            matched_original  = by_original_any.get(item_code, [])
            # Merge in rows matched via a Consolidate Item row's own
            # alternate_item -- dedup by row name in case a row is ALSO
            # independently flagged with its own row-level alternate_item
            # equal to the same purchased item_code.
            if item_code in by_consolidate_alt_any:
                seen_names = {r.name for r in matched_alternate}
                for r in by_consolidate_alt_any[item_code]:
                    if r.name not in seen_names:
                        matched_alternate.append(r)
                        seen_names.add(r.name)

        # Only when nothing is waiting in Unavailable Items -- that table stays
        # the primary and preferred match, so a plan following the intended
        # route behaves exactly as before.
        matched_mapping = []
        if not matched_alternate and not matched_original:
            if pr_duno:
                matched_mapping = list(mm_by_duno.get((item_code, pr_duno), []))
            else:
                matched_mapping = list(mm_by_any.get(item_code, []))
                seen_names = {r.name for r in matched_mapping}
                for r in mm_by_consolidate_alt_any.get(item_code, []):
                    if r.name not in seen_names:
                        matched_mapping.append(r)
                        seen_names.add(r.name)

        if matched_alternate:
            # Alternate item purchased → Material Mapping, fully populated as
            # if the user had picked this batch by hand (batch dimensions,
            # Sec Qty/Calc Qty, Status), not left blank for a later manual fix.
            alt_item_data = frappe.db.get_value(
                "Item", item_code,
                ["custom_parent_item_group", "custom_unit_weight"],
                as_dict=True,
            ) or {}
            batch_total_qty    = _get_batch_total_stock(batch_no, mp.for_warehouse) if batch_no else 0.0
            batch_reserved_qty = _get_batch_reserved_by_others(batch_no, mp_name) if batch_no else 0.0
            received_qty = _receivable_qty(pr_item, batch_total_qty, batch_reserved_qty)

            for mp_row, alloc_qty in _split_allocation(matched_alternate, received_qty, sequential):
                _consume(mp_row, alloc_qty)
                ratio = (alloc_qty / received_qty) if received_qty else 0.0
                mp.append("material_mapping", _build_mapping_row(
                    mp_row,
                    alloc_qty=alloc_qty,
                    ratio=ratio,
                    pr_item=pr_item,
                    pr_name=pr_name,
                    purchased_item_code=item_code,
                    batch_no=batch_no,
                    purchased_item_data=alt_item_data,
                    batch_total_qty=batch_total_qty,
                    batch_reserved_qty=batch_reserved_qty,
                ))
                added_mapping += 1

        elif matched_original:
            # Original item purchased -- Exact Match only for the rows whose own
            # dimensions this receipt actually matches. A Consolidate Item line
            # bought at a standard stock size matches none of them and goes to
            # Material Mapping instead, keeping the required size on the row and
            # the purchased size on batch_* (see _pr_dimensions_match).
            item_data = frappe.db.get_value(
                "Item", item_code,
                ["stock_uom", "custom_secondary_uom",
                 "custom_parent_item_group", "custom_unit_weight"],
                as_dict=True,
            ) or {}
            batch_total_qty    = _get_batch_total_stock(batch_no, mp.for_warehouse) if batch_no else 0.0
            batch_reserved_qty = _get_batch_reserved_by_others(batch_no, mp_name) if batch_no else 0.0
            received_qty = _receivable_qty(pr_item, batch_total_qty, batch_reserved_qty)

            splits = list(_split_allocation(matched_original, received_qty, sequential))

            # ONE batch, ONE table -- decided here for the whole receipt line rather
            # than per requirement row.
            #
            # A single received batch is routinely split across several requirements,
            # and its dimensions can match some of them exactly while missing others.
            # Deciding row by row put the same batch into Material Mapping AND Exact
            # Match, which _validate_no_cross_table_batch_duplicate then refuses --
            # the plan could not be saved at all after such a receipt, and the batch
            # would have been double-counted at transfer time if it had been.
            #
            # Any mismatch sends the whole batch to Material Mapping: that table
            # carries the required size on the row and the purchased size on batch_*,
            # so it represents a matching row perfectly well, while Exact Match
            # assumes the two are the same and cannot represent a mismatch at all.
            all_dimensions_match = all(
                _pr_dimensions_match(pr_item, mp_row) for mp_row, _ in splits
            )

            for mp_row, alloc_qty in splits:
                _consume(mp_row, alloc_qty)
                ratio = (alloc_qty / received_qty) if received_qty else 0.0

                if not all_dimensions_match:
                    mp.append("material_mapping", _build_mapping_row(
                        mp_row,
                        alloc_qty=alloc_qty,
                        ratio=ratio,
                        pr_item=pr_item,
                        pr_name=pr_name,
                        purchased_item_code=item_code,
                        batch_no=batch_no,
                        purchased_item_data=item_data,
                        batch_total_qty=batch_total_qty,
                        batch_reserved_qty=batch_reserved_qty,
                    ))
                    added_mapping += 1
                    continue

                mp.append("available_raw_materials", {
                    "item_number":            mp_row.item_number,
                    "sales_order":            mp_row.sales_order,
                    "item_code":              item_code,
                    "item_name":              pr_item.item_name or mp_row.item_name,
                    "duno_mark_no":           mp_row.duno_mark_no,
                    "customer_drawing_number": mp_row.customer_drawing_number,
                    "batch_no":               batch_no,
                    "parent_item_group":      mp_row.parent_item_group,
                    "length":                 flt(pr_item.custom_length)    or mp_row.length,
                    "width":                  flt(pr_item.custom_width)     or mp_row.width,
                    "thickness":              flt(pr_item.custom_thickness) or mp_row.thickness,
                    "overall_required_qty":   flt(mp_row.qty, 3),
                    "required_qty":           flt(min(alloc_qty, flt(mp_row.qty)), 3),
                    "available_qty":          flt(alloc_qty, 3),
                    "sec_qty":                flt(flt(pr_item.custom_sec_qty) * ratio, 3) or mp_row.sec_qty,
                    "sec_uom":                item_data.get("custom_secondary_uom") or mp_row.sec_uom,
                    "uom":                    item_data.get("stock_uom")    or mp_row.uom,
                    "warehouse":              pr_item.warehouse or mp.for_warehouse,
                    "purchase_receipt":       pr_name,
                })
                added_exact += 1

        elif matched_mapping:
            # Nothing left in Unavailable Items, but Material Mapping rows for
            # this item are still waiting for a batch -- fill them in place.
            map_item_data = frappe.db.get_value(
                "Item", item_code,
                ["custom_parent_item_group", "custom_unit_weight"],
                as_dict=True,
            ) or {}
            batch_total_qty    = _get_batch_total_stock(batch_no, mp.for_warehouse) if batch_no else 0.0
            batch_reserved_qty = _get_batch_reserved_by_others(batch_no, mp_name) if batch_no else 0.0
            received_qty = _receivable_qty(pr_item, batch_total_qty, batch_reserved_qty)

            for mp_row, alloc_qty in _split_allocation(matched_mapping, received_qty, sequential):
                # _split_allocation hands a lone matched row the WHOLE receipt
                # line (its sequential capping only kicks in for two or more
                # rows). On this path the row's own requirement is the cap:
                # batch_calc_qty records what this row takes FROM the batch,
                # so claiming more than it needs both overstates the plan's
                # mapped weight and would reserve the surplus away from every
                # other requirement that batch could still serve.
                outstanding = flt(remaining_qty_by_row.get(mp_row.name, mp_row.qty))
                alloc_qty = flt(min(flt(alloc_qty), outstanding), 3)
                if alloc_qty <= 0:
                    continue

                row_sec_qty = flt(mp_row.sec_qty)
                covered_ratio = (alloc_qty / outstanding) if outstanding else 1.0
                shortfall_qty = flt(outstanding - alloc_qty, 3)

                _consume(mp_row, alloc_qty)
                mapping_row_names.add(mp_row.name)
                ratio = (alloc_qty / received_qty) if received_qty else 0.0
                _fill_mapping_row_from_receipt(
                    mp_row,
                    alloc_qty=alloc_qty,
                    ratio=ratio,
                    pr_item=pr_item,
                    pr_name=pr_name,
                    purchased_item_code=item_code,
                    batch_no=batch_no,
                    purchased_item_data=map_item_data,
                    batch_total_qty=batch_total_qty,
                    batch_reserved_qty=batch_reserved_qty,
                )
                filled_mapping += 1

                # A row this receipt could only cover in part is split, exactly
                # as the Unavailable Items route splits one: this row shrinks to
                # what the batch actually supplies and the rest becomes its own
                # blank-batch row to assign by hand. Leaving the full
                # requirement on a reserve_without_dimensions row would have it
                # reserve more of the batch than arrived, which
                # _validate_batch_calc_qty refuses -- taking the whole
                # allocation down with it.
                covered_sec_qty = flt(row_sec_qty * covered_ratio, 3)
                mp_row.qty = alloc_qty
                mp_row.sec_qty = covered_sec_qty
                if shortfall_qty > QTY_EPSILON:
                    mp.append("material_mapping", {
                        "item_number":            mp_row.item_number,
                        "sales_order":            mp_row.sales_order,
                        "item_code":              mp_row.item_code,
                        "item_name":              mp_row.item_name,
                        "bom_no":                 mp_row.bom_no,
                        "drawing":                mp_row.drawing,
                        "duno_mark_no":           mp_row.duno_mark_no,
                        "customer_drawing_number": mp_row.customer_drawing_number,
                        "qty":                    shortfall_qty,
                        "uom":                    mp_row.uom,
                        "sec_qty":                flt(row_sec_qty - covered_sec_qty, 3),
                        "sec_uom":                mp_row.sec_uom,
                        "parent_item_group":      mp_row.parent_item_group,
                        "length":                 mp_row.length,
                        "width":                  mp_row.width,
                        "thickness":              mp_row.thickness,
                        "unit_weight":            mp_row.unit_weight,
                        "batch":                  "",
                        "batch_mapped":           "Not Mapped",
                        "purchase_receipt":       pr_name,
                    })
                    added_mapping += 1

    # Reconcile Unavailable Items. A row this receipt covered in full simply
    # goes; a row it covered only partly leaves behind its shortfall as a
    # Material Mapping row with NO batch, for someone to assign by hand.
    #
    # A short delivery means the material was ordered and arrived undersized --
    # not that nobody has tried to buy it yet. Leaving the remainder in
    # Unavailable Items would send it round the purchase loop a second time; the
    # blank-batch Mapping row instead puts it where every other "assign this
    # yourself" case already lives (move_to_exact_match uses exactly the same
    # convention when it finds no dimension match).
    if fulfilled_row_names or remaining_qty_by_row:
        kept = []
        for row in (mp.unavailable_items or []):
            if row.name in fulfilled_row_names:
                continue
            new_qty = remaining_qty_by_row.get(row.name)
            if new_qty is None:
                kept.append(row)
                continue

            old_qty = flt(row.qty)
            ratio = (new_qty / old_qty) if old_qty else 0.0
            mp.append("material_mapping", {
                "item_number":            row.item_number,
                "sales_order":            row.sales_order,
                "item_code":              row.item_code,
                "item_name":              row.item_name,
                "bom_no":                 row.bom_no,
                "drawing":                row.drawing,
                "duno_mark_no":           row.duno_mark_no,
                "customer_drawing_number": row.customer_drawing_number,
                "qty":                    flt(new_qty, 3),
                "uom":                    row.uom,
                "sec_qty":                flt(flt(row.sec_qty) * ratio, 3),
                "sec_uom":                row.sec_uom,
                "parent_item_group":      row.parent_item_group,
                "length":                 row.length,
                "width":                  row.width,
                "thickness":              row.thickness,
                "unit_weight":            row.unit_weight,
                "batch":                  "",
                "batch_mapped":           "Not Mapped",
                "purchase_receipt":       pr_name,
            })
            added_mapping += 1
        mp.unavailable_items = kept

    if added_exact or added_mapping or filled_mapping or fulfilled_row_names or remaining_qty_by_row:
        # The receipt is saving the plan, not a person editing it -- see
        # _warn_undersized_purchase_dimensions.
        mp.flags.mfx_saved_by_another_document = True
        mp.save(ignore_permissions=True)

    # What the plan is still waiting for, by item: every Material Mapping row
    # left without a batch, whether this receipt shrank it to a shortfall or
    # never covered it at all (the item was dropped at the Purchase Order, or
    # cut back at the receipt). The caller shows this on submit so the
    # shortfall is visible then and there -- to purchase the balance, or to
    # map another batch against it -- rather than only to whoever next opens
    # the plan and reads the table.
    pending_by_item = {}
    for row in (mp.material_mapping or []):
        if row.batch:
            continue
        pending_by_item[row.item_code] = flt(
            pending_by_item.get(row.item_code, 0.0) + flt(row.qty), 3
        )

    return {
        "added_exact": added_exact,
        "added_mapping": added_mapping,
        "filled_mapping": filled_mapping,
        "fulfilled": len(fulfilled_row_names - mapping_row_names),
        "partial": len([n for n in remaining_qty_by_row if n not in mapping_row_names]),
        "pending_by_item": pending_by_item,
    }


def _archive_consolidate_items(mp_name, pr_name):
    """Once a receipt has landed, the Consolidate Item table has done its job:
    write it out to a comment on the Material Planning -- every row plus the
    Material Request / Purchase Order / Purchase Receipt it turned into -- and
    empty the table.

    Keeping the purchasing lines around after they have been bought invites
    someone to raise a second Material Request for material that is already in
    the warehouse. The comment preserves exactly what was ordered, so the
    history survives even though the table no longer offers it for purchase.
    """
    mp = frappe.get_doc("Material Planning", mp_name)
    if not mp.consolidate_items:
        return 0

    # Trace this receipt back to the PO and MR it came from, for the record.
    po_names, mr_names = set(), set()
    pr = frappe.get_doc("Purchase Receipt", pr_name)
    for pr_item in pr.items:
        if pr_item.purchase_order:
            po_names.add(pr_item.purchase_order)
        if pr_item.purchase_order_item:
            mri = frappe.db.get_value(
                "Purchase Order Item", pr_item.purchase_order_item, "material_request_item")
            if mri:
                mr = frappe.db.get_value("Material Request Item", mri, "parent")
                if mr:
                    mr_names.add(mr)

    header = "".join("<th style='padding:4px 8px'>%s</th>" % h for h in (
        _("Item"), _("Alternate Item"), _("Required Kg"), _("Length"), _("Width"),
        _("Thickness"), _("Sec Qty"), _("Purchase Kg"), _("Difference Kg")))
    body = ""
    for c in mp.consolidate_items:
        body += "<tr>" + "".join("<td style='padding:4px 8px'>%s</td>" % v for v in (
            frappe.utils.escape_html(c.item_code or ""),
            frappe.utils.escape_html(c.alternate_item or "-"),
            flt(c.required_kg, 3), flt(c.length, 3), flt(c.width, 3),
            flt(c.thickness, 3), flt(c.sec_qty, 3), flt(c.purchase_kg, 3),
            flt(c.difference_kg, 3),
        )) + "</tr>"

    comment = _("<b>Consolidate Items purchased and archived</b><br>") + "{0}: {1}<br>{2}: {3}<br>{4}: {5}<br><br>".format(
        _("Material Request"), ", ".join(sorted(mr_names)) or "-",
        _("Purchase Order"), ", ".join(sorted(po_names)) or "-",
        _("Purchase Receipt"), pr_name,
    ) + (
        "<table border='1' style='border-collapse:collapse;font-size:12px'>"
        "<thead><tr>" + header + "</tr></thead><tbody>" + body + "</tbody></table>"
    )

    archived = len(mp.consolidate_items)
    mp.add_comment("Comment", comment)

    # Clear the table, and release the rows that fed it so a later requirement
    # for the same item consolidates cleanly instead of being treated as already
    # folded in (_consolidate_unavailable_items keys off consolidated_into).
    mp.consolidate_items = []
    for row in (mp.unavailable_items or []):
        row.consolidated_into = ""
    mp.flags.mfx_saved_by_another_document = True
    mp.save(ignore_permissions=True)
    return archived


def _allocate_pr_items_individually(pr_name, mp_name):
    """Allocate a receipt one line at a time, each under its own savepoint.

    The fallback for a whole-receipt pass the plan refused. Allocation writes
    every item in a single save, so one row the plan will not accept discards
    the allocation of every other item on the receipt: PR-26-00008 delivered
    five plate sizes, four of them allocatable without argument, and all five
    stayed unmapped because the PLATE8 rows filled their batch to the last
    kilo and tripped a rounding check.

    A receipt is not an all-or-nothing document -- items get dropped at the
    Purchase Order, dropped again at the receipt, and re-cut to whatever the
    supplier actually sent -- so what CAN be matched must land, and only the
    line that genuinely cannot must be left for someone to look at. Each line
    is rolled back to its own savepoint, so a refusal costs that item and
    nothing else.

    Returns (combined result, list of item_codes that failed).
    """
    combined = {
        "added_exact": 0, "added_mapping": 0, "filled_mapping": 0,
        "fulfilled": 0, "partial": 0, "pending_by_item": {},
    }
    failed_items = []

    pr_rows = frappe.get_all(
        "Purchase Receipt Item",
        filters={"parent": pr_name},
        fields=["name", "item_code"],
        order_by="idx",
    )
    for seq, pr_row in enumerate(pr_rows):
        savepoint = "mfx_pr_alloc_%d" % seq
        frappe.db.savepoint(savepoint)
        try:
            result = allocate_pr_stock_to_mp(pr_name, mp_name, only_items=[pr_row.name]) or {}
        except Exception:
            # Back to this line's own savepoint, not the start of the submit.
            frappe.db.rollback(save_point=savepoint)
            failed_items.append(pr_row.item_code)
            frappe.log_error(
                title=f"Allocation failed for {pr_row.item_code} on {pr_name} -> {mp_name}",
                message=frappe.get_traceback(),
            )
            continue

        for key in ("added_exact", "added_mapping", "filled_mapping", "fulfilled", "partial"):
            combined[key] += result.get(key) or 0
        # A whole-plan snapshot taken after each save, so the most recent one
        # is the current state -- not something to add up across lines.
        combined["pending_by_item"] = result.get("pending_by_item") or {}

    return combined, failed_items


def _msgprint_pending_mapping(mp_name, pending_by_item):
    """Say what the plan is still short of, at the moment of receipt.

    A short delivery is the normal case, not an error: the plan keeps a
    blank-batch "Not Mapped" row for the balance. But nothing announced it,
    so the shortfall was only discovered by opening the plan and reading the
    table -- and a receipt that allocated most of what was needed looked
    exactly like one that allocated all of it.
    """
    if not pending_by_item:
        return
    lines = ", ".join(
        "<b>{0}</b> {1} Kg".format(item_code, flt(qty, 3))
        for item_code, qty in sorted(pending_by_item.items())
    )
    frappe.msgprint(
        _(
            "Material Planning {0} still has unmapped requirements after this receipt — {1}. "
            "Purchase the balance, or map another batch against those rows in Material Mapping."
        ).format(mp_name, lines),
        indicator="orange",
        title=_("Material Mapping Pending"),
    )


def on_submit_purchase_receipt(doc, method):
    """Auto-allocate received batches back to every Material Planning this PR traces to,
    then refresh any Material Issue Plans that link to those MPs so their raw-material
    snapshot stays current for the transfer popup."""
    from manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan import (
        refresh_mip_raw_materials,
    )

    affected_mps = get_mp_for_pr(doc.name)
    for mp_name in affected_mps:
        result, failed_items = {}, []
        try:
            result = allocate_pr_stock_to_mp(doc.name, mp_name) or {}
        except Exception:
            frappe.log_error(
                title=f"Material Planning auto-allocation failed for {doc.name} -> {mp_name}",
                message=frappe.get_traceback(),
            )
            # One refused line used to cost the whole receipt its allocation.
            # Retry line by line so everything that can be matched still is,
            # and only the line that cannot is reported.
            result, failed_items = _allocate_pr_items_individually(doc.name, mp_name)

        allocated_anything = bool(
            result.get("added_exact")
            or result.get("added_mapping")
            or result.get("filled_mapping")
        )

        if failed_items and not allocated_anything:
            # Report 3 Finding H-01 / Phase 1 HP-04: this failure previously
            # had zero user-visible signal -- the PR submit still succeeds
            # (intentionally, so a downstream planning-sync problem never
            # blocks the stock-affecting document), but the submitting user
            # now sees that the automatic allocation into mp_name did not
            # happen, instead of only discovering it much later when
            # Material Planning still shows the item as unavailable.
            frappe.msgprint(
                _(
                    "Automatic batch allocation into Material Planning {0} failed for this "
                    "receipt. The Purchase Receipt has still been submitted; a Manufacturing "
                    "Manager will need to check the Error Log and, if appropriate, retry the "
                    "allocation manually from the Material Planning document."
                ).format(mp_name),
                indicator="orange",
                title=_("Material Planning Allocation Failed"),
            )
        elif failed_items:
            frappe.msgprint(
                _(
                    "Material Planning {0} was allocated from this receipt, except for "
                    "<b>{1}</b> — that item was refused and left unmapped. The rest has been "
                    "allocated; check the Error Log for why that one did not."
                ).format(mp_name, ", ".join(sorted(set(failed_items)))),
                indicator="orange",
                title=_("Partly Allocated"),
            )
        elif not allocated_anything:
            # Tracing to a plan but allocating nothing into it is not a
            # normal outcome -- it means every requirement this receipt
            # could have covered has already been mapped, or none of them
            # could be matched at all. Both used to look identical to a
            # successful allocation from the outside: the receipt
            # submitted, no error was raised, and the plan quietly stayed
            # unmapped.
            frappe.msgprint(
                _(
                    "Nothing was allocated into Material Planning {0} from this receipt — "
                    "no requirement row was left waiting for these items. Check the plan's "
                    "Material Mapping and Unavailable Items tables before treating the "
                    "material as planned."
                ).format(mp_name),
                indicator="orange",
                title=_("No Material Planning Rows Matched"),
            )

        if allocated_anything:
            _msgprint_pending_mapping(mp_name, result.get("pending_by_item") or {})

        try:
            _archive_consolidate_items(mp_name, doc.name)
        except Exception:
            frappe.log_error(
                title=f"Consolidate Item archive failed for {doc.name} -> {mp_name}",
                message=frappe.get_traceback(),
            )

    # Refresh MIP raw-material snapshots for any MIPs linked to affected MPs
    if affected_mps:
        mip_rows = frappe.db.get_all(
            "SCO Drawing Item",
            filters={"material_planning": ("in", affected_mps)},
            fields=["parent"],
            distinct=True,
        )
        for row in mip_rows:
            try:
                refresh_mip_raw_materials(row.parent)
            except Exception:
                frappe.log_error(
                    title=f"MIP raw-material refresh failed for {row.parent} after {doc.name}",
                    message=frappe.get_traceback(),
                )
                # Report 3 Finding H-01 / Phase 1 HP-04: same "surface it, don't
                # just log it" treatment as the allocation failure above.
                frappe.msgprint(
                    _(
                        "Refreshing the raw-material snapshot for Material Issue Plan {0} failed "
                        "after this receipt. Its displayed transferred/allocated weight may be "
                        "stale until it is manually refreshed."
                    ).format(row.parent),
                    indicator="orange",
                    title=_("Material Issue Plan Refresh Failed"),
                )


def _get_batch_from_bundle(sbb_name):
    """Resolve a Serial and Batch Bundle to its batch_no -- Frappe v15 items using
    use_serial_batch_fields can end up with the PR item's own batch_no blank and
    the batch reference living only in its serial_and_batch_bundle instead. Was
    previously called here but never defined (a latent NameError -- this crashed
    get_pr_mp_allocations for any PR whose items went through the bundle path)."""
    if not sbb_name:
        return None
    return frappe.db.get_value("Serial and Batch Entry", {"parent": sbb_name}, "batch_no")


@frappe.whitelist()
def get_pr_mp_allocations(pr_name):
    """Return which Material Planning documents have batches from this PR allocated,
    so the client can show a post-submit popup pointing the user at them.

    Deliberately NOT filtered to is_reserved=1: allocate_pr_stock_to_mp only places
    the received batch into Available Raw Materials / Material Mapping -- it never
    sets is_reserved itself, that's still a separate, manual Reserve step on the
    Material Planning. Filtering by is_reserved here would make this popup fire
    almost never (nothing is reserved yet right after a normal receipt) and, worse,
    would let a stale "already reserved" message go out even though a reserve step
    still needs to happen before the batch can be transferred via a Material Issue
    Plan (client change request: no transfer for anything not purchased AND
    reserved -- see _get_mp_reserved_batches's is_reserved=1 filter, which is what
    actually enforces that)."""
    if not frappe.has_permission("Material Planning", "read"):
        frappe.throw(_("Not permitted to view Material Planning allocations"), frappe.PermissionError)
    pr = frappe.get_doc("Purchase Receipt", pr_name)
    pr_batches = {}
    for item in (pr.items or []):
        batch_no = item.batch_no
        if not batch_no:
            # Try to get batch from serial_and_batch_bundle
            batch_no = _get_batch_from_bundle(item.serial_and_batch_bundle or "")
        if batch_no:
            pr_batches.setdefault(batch_no, []).append({
                "item_code": item.item_code,
                "qty": flt(item.qty, 3),
            })

    if not pr_batches:
        return []

    batch_list = list(pr_batches.keys())
    ph = ", ".join(["%s"] * len(batch_list))

    mm_rows = frappe.db.sql(
        f"SELECT parent AS mp, batch AS batch_no, item_code, is_reserved, "
        f"       SUM(CASE WHEN is_reserved = 1 THEN reserved_qty ELSE qty END) AS qty "
        f"FROM `tabMaterial Planning Material Mapping` "
        f"WHERE batch IN ({ph}) "
        f"GROUP BY parent, batch, item_code, is_reserved",
        batch_list, as_dict=True,
    )

    arm_rows = frappe.db.sql(
        f"SELECT parent AS mp, batch_no, item_code, is_reserved, "
        f"       SUM(CASE WHEN is_reserved = 1 THEN reserved_qty ELSE required_qty END) AS qty "
        f"FROM `tabMaterial Planning Available Raw Material` "
        f"WHERE batch_no IN ({ph}) "
        f"GROUP BY parent, batch_no, item_code, is_reserved",
        batch_list, as_dict=True,
    )

    result = []
    for r in (list(mm_rows) + list(arm_rows)):
        result.append({
            "material_planning": r.mp,
            "batch_no": r.batch_no,
            "item_code": r.item_code,
            "qty": flt(r.qty, 3),
            "is_reserved": bool(r.is_reserved),
        })

    return result
