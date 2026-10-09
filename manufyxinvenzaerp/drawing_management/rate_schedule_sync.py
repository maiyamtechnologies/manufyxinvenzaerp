"""Keep one drawing's Rate Schedule the same on the Drawing, its BOM and every
Production Plan row that quotes it.

The rate a job is charged at belongs to the DRAWING. Three documents display it --
Drawing, BOM (one BOM is one drawing, via custom_drawing) and Production Plan Item
rows (one plan holds many drawings, so it sits on the row) -- and all three can now
edit it, because in practice the person who notices the rate is wrong is whichever
one of the three they happen to have open.

So the drawing is the key, not the document: change the schedule anywhere, and the
other two follow. Concretely, for drawing D the targets are

    the Drawing D itself
    every BOM with custom_drawing = D          (not cancelled)
    every Production Plan Item with custom_drawing = D   (parent not cancelled)

Three things are worth knowing before changing anything here.

**Only the LINK propagates, plus the display copies that follow it.** The Rate
Schedule master -- its rate, its price log -- is edited on the Rate Schedule
doctype and nowhere else. What travels is *which schedule this drawing uses*.

**Writes go through db_set / db.set_value, never doc.save().** Two reasons, and
both matter. A Drawing or BOM is normally SUBMITTED by the time anyone revisits a
rate, so an ordinary save is not available; and a BOM save re-runs costing, so
propagating through one would silently recalculate every rate and amount on a
submitted BOM as a side effect of correcting a label. db_set writes the column and
nothing else.

**That is also what stops this recursing.** db_set fires no hooks, so a Drawing
save that writes to its BOM does not trigger the BOM's own on_update, which would
write back to the Drawing, and so on. If you ever replace a db_set here with a
doc.save(), you will get an infinite loop.
"""

import frappe
from frappe import _

# What gets copied alongside the link, per target doctype. Keyed by the target's
# own fieldname, valued by the field on the Rate Schedule it comes from.
#
# These same fields carry `fetch_from` in their definitions (setup.py), so an
# ordinary save re-derives them anyway. They are written explicitly here because
# db_set does not run fetch_from -- and because a submitted document may never see
# an ordinary save again.
_DRAWING_DETAIL_MAP = {
    "rs_job_nature": "job_nature",
    "rs_details": "details",
    "rs_work_content": "work_content",
    "rs_job_reference": "job_reference",
    "rs_rate_per_kg": "rate_per_kg",
}
_BOM_DETAIL_MAP = {
    "custom_rs_type": "type",
    "custom_rs_job_nature": "job_nature",
    "custom_rs_details": "details",
    "custom_rs_work_content": "work_content",
    "custom_rs_job_reference": "job_reference",
    "custom_rs_rate_per_kg": "rate_per_kg",
}
_PP_ITEM_DETAIL_MAP = {
    "custom_rs_job_nature": "job_nature",
    "custom_rs_rate_per_kg": "rate_per_kg",
}

# The field holding the link, per doctype.
_LINK_FIELD = {
    "Drawing": "rate_schedule",
    "BOM": "custom_rate_schedule",
    "Production Plan Item": "custom_rate_schedule",
}
_DETAIL_MAP = {
    "Drawing": _DRAWING_DETAIL_MAP,
    "BOM": _BOM_DETAIL_MAP,
    "Production Plan Item": _PP_ITEM_DETAIL_MAP,
}


def _schedule_details(schedule):
    """Every field of a Rate Schedule the three documents mirror, in one read."""
    if not schedule:
        return {}
    return frappe.db.get_value(
        "Rate Schedule",
        schedule,
        ["type", "job_nature", "details", "work_content", "job_reference", "rate_per_kg"],
        as_dict=True,
    ) or {}


_NUMERIC_FIELDTYPES = ("Currency", "Float", "Int", "Percent", "Check")


def _empty_value(doctype, fieldname):
    """The right kind of blank for this column.

    None is not it. Frappe's numeric columns are NOT NULL with a 0 default, so
    clearing a schedule by writing None into rs_rate_per_kg fails outright --
    "Column 'rs_rate_per_kg' cannot be null" -- and takes the whole propagation
    down with it, mid-way through the documents it was updating.
    """
    df = frappe.get_meta(doctype).get_field(fieldname)
    return 0 if df and df.fieldtype in _NUMERIC_FIELDTYPES else ""


def _values_for(doctype, schedule, details):
    """The full set of column writes for one target: the link plus its display copies."""
    values = {_LINK_FIELD[doctype]: schedule or ""}
    for fieldname, source in _DETAIL_MAP[doctype].items():
        if schedule:
            values[fieldname] = details.get(source) or _empty_value(doctype, fieldname)
        else:
            values[fieldname] = _empty_value(doctype, fieldname)
    return values


def _targets(drawing, exclude=None):
    """Every document quoting this drawing, as (doctype, name, current_schedule).

    Cancelled documents are left out: they are a historical record of what was
    agreed at the time, and rewriting a rate onto one would falsify it.

    `exclude` is the (doctype, name) that triggered the change -- it is being saved
    right now and writing to it underneath its own save is how you lose the value
    the user just typed.
    """
    rows = []
    if drawing:
        rows.append(("Drawing", drawing, frappe.db.get_value("Drawing", drawing, "rate_schedule")))

    for bom in frappe.get_all(
        "BOM",
        filters={"custom_drawing": drawing, "docstatus": ["!=", 2]},
        fields=["name", "custom_rate_schedule"],
    ):
        rows.append(("BOM", bom.name, bom.custom_rate_schedule))

    # Child rows are queried directly: going through the parent Production Plan
    # would mean loading whole plans (up to 500 rows each) to reach one row.
    for row in frappe.get_all(
        "Production Plan Item",
        filters={"custom_drawing": drawing, "docstatus": ["!=", 2]},
        fields=["name", "parent", "custom_rate_schedule"],
    ):
        rows.append(("Production Plan Item", row.name, row.custom_rate_schedule))

    if exclude:
        rows = [r for r in rows if (r[0], r[1]) != tuple(exclude)]
    return rows


@frappe.whitelist()
def get_rate_schedule_conflict(drawing, new_schedule, source_doctype=None, source_name=None):
    """Does this change overwrite a schedule the drawing already had?

    Called from the form BEFORE the change is accepted, so the user is asked the
    question while they can still back out -- rather than being told afterwards
    that four other documents were rewritten.

    Returns the drawing's current schedule, whether it genuinely differs, and how
    many other documents would be rewritten.
    """
    if not drawing:
        return {"conflict": False, "current": None, "target_count": 0}

    current = frappe.db.get_value("Drawing", drawing, "rate_schedule")
    targets = _targets(drawing, exclude=(source_doctype, source_name) if source_doctype else None)
    return {
        "conflict": bool(current) and current != (new_schedule or ""),
        "current": current,
        "drawing": drawing,
        "target_count": len(targets),
        "targets": [{"doctype": d, "name": n} for d, n, _cur in targets],
    }


def propagate(drawing, schedule, source_doctype=None, source_name=None):
    """Write `schedule` onto every document quoting `drawing`, skipping the source.

    Returns {"updated": [...], "unchanged": n} -- `updated` names the documents that
    actually changed, which is what the confirmation popup lists. Documents already
    on this schedule are counted, not named: telling someone a document was
    "updated" when nothing about it changed makes the whole message untrustworthy.
    """
    if not drawing:
        return {"updated": [], "unchanged": 0}

    schedule = schedule or ""
    details = _schedule_details(schedule)
    updated, unchanged = [], 0

    for doctype, name, current in _targets(drawing, exclude=(source_doctype, source_name)):
        if (current or "") == schedule:
            unchanged += 1
            continue
        frappe.db.set_value(
            doctype, name, _values_for(doctype, schedule, details), update_modified=False
        )
        label = name
        if doctype == "Production Plan Item":
            # A child row's name is a hash nobody can act on. Name the plan instead.
            parent = frappe.db.get_value("Production Plan Item", name, "parent")
            label = parent or name
        updated.append({"doctype": doctype, "name": name, "label": label})

    # A Production Plan holding two rows for the same drawing would otherwise be
    # listed twice under the same name, reading as two separate documents.
    seen, deduped = set(), []
    for u in updated:
        key = (u["doctype"], u["label"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(u)

    return {"updated": deduped, "unchanged": unchanged}


def _route(doctype, name):
    """Desk URL for a document.

    A Production Plan Item is a child row and has no form of its own, so it is
    routed to its PARENT plan -- linking to the row's own route opens nothing.
    The route itself comes from Frappe (/desk/... on v16), never hard-coded.
    """
    if doctype == "Production Plan Item":
        doctype = "Production Plan"
    return frappe.utils.get_absolute_url(doctype, name)


def announce(result, schedule):
    """Tell the user which documents were rewritten -- or that none needed to be.

    Deliberately a msgprint rather than a silent success: this is the one action in
    the app that edits documents the user is not looking at, and doing that quietly
    is how people stop trusting a number they did not type.
    """
    updated = result.get("updated") or []
    if not updated:
        return

    items = "".join(
        '<li><a href="{route}" target="_blank">{label}</a> '
        '<span style="color:#888">({doctype})</span></li>'.format(
            # label is already the parent's name for a Production Plan Item, which
            # is both what to show and what to route to.
            route=_route(u["doctype"], u["label"]),
            label=frappe.utils.escape_html(u["label"]),
            doctype=_("Production Plan") if u["doctype"] == "Production Plan Item" else u["doctype"],
        )
        for u in updated
    )

    frappe.msgprint(
        _("Rate Schedule set to <b>{0}</b>. Updated in these documents:").format(
            frappe.utils.escape_html(schedule or _("(none)"))
        )
        + '<ul style="margin:8px 0 0 18px">{0}</ul>'.format(items),
        title=_("Rate Schedule Updated"),
        indicator="green",
    )


# ── Document hooks ───────────────────────────────────────────────────────────
#
# Every hook propagates only when the field was ACTUALLY EDITED in this save --
# has_value_changed against the pre-save copy -- never when the document merely
# disagrees with its drawing.
#
# That distinction is the whole safety of this feature. Reconciling on
# disagreement sounds tidier and is destructive: every BOM and Production Plan
# created before these fields existed carries a blank Rate Schedule, so the first
# time anyone saved one of them for an unrelated reason, the blank would win and
# wipe the rate off the Drawing and off every other document quoting it. Nobody
# would connect the loss to the save that caused it.
#
# The cost of the safe rule is that pre-existing documents stay blank until
# someone sets them. That is the right trade: blank is visibly missing, whereas a
# silently cleared rate looks like a decision.


def seed_production_plan_rows(doc, method=None):
    """Fill a blank Rate Schedule on any Production Plan row that names a drawing.

    Rows reach a plan by several routes -- make_production_plan from a Material
    Planning, the "Add Drawings" picker, and by hand -- and threading the schedule
    through each of them separately is how one of them ends up forgotten. Seeding
    once here, on validate, catches all of them.

    Only ever fills a BLANK. A row already carrying a schedule is left exactly as
    it is, including one deliberately cleared: overwriting that would make the
    field impossible to empty.

    Seeded rows are recorded on doc.flags so on_update_production_plan can tell
    them apart from rows a person edited. Without that, seeding a row would look
    like an edit and would broadcast the drawing's own schedule back out at it --
    harmless in the common case, but on a legacy BOM still sitting blank it would
    silently write a rate onto a submitted document as a side effect of saving an
    unrelated plan.
    """
    seeded = set()
    for row in (doc.get("po_items") or []):
        drawing = row.get("custom_drawing")
        if not drawing or row.get("custom_rate_schedule"):
            continue
        schedule = frappe.db.get_value("Drawing", drawing, "rate_schedule")
        if not schedule:
            continue
        details = _schedule_details(schedule)
        for fieldname, value in _values_for("Production Plan Item", schedule, details).items():
            row.set(fieldname, value)
        seeded.add(row.name)

    doc.flags.rate_schedule_seeded_rows = seeded


def _is_insert(doc):
    """No pre-save copy means this is the first save of a brand-new document.

    Worth short-circuiting rather than letting it fall through: has_value_changed
    returns True for EVERY field on an insert (there is nothing to compare against),
    so without this a drawing import creating 500 drawings would run the full
    propagation 500 times. It would find nothing to do each time -- a brand-new
    drawing has no BOM and no plan quoting it yet, and a BOM created by
    create_bom_from_drawing is seeded from the drawing it was just built from -- but
    it would spend three queries per document proving it.
    """
    return doc.get_doc_before_save() is None


def _sync_if_edited(doc, drawing, source_doctype):
    if _is_insert(doc):
        return
    if not drawing or not doc.has_value_changed(_LINK_FIELD[source_doctype]):
        return
    schedule = doc.get(_LINK_FIELD[source_doctype]) or ""
    result = propagate(drawing, schedule, source_doctype, doc.name)
    announce(result, schedule)


def on_update_drawing(doc, method=None):
    """Drawing → its BOM and every Production Plan row quoting it."""
    _sync_if_edited(doc, doc.name, "Drawing")


def on_update_bom(doc, method=None):
    """BOM → Drawing and Production Plan rows. One BOM is one drawing."""
    _sync_if_edited(doc, doc.get("custom_drawing"), "BOM")


def on_update_production_plan(doc, method=None):
    """Production Plan rows → their Drawings and BOMs.

    Row-level rather than document-level: a plan holds many drawings, each with its
    own schedule, so "did this document change" is not a useful question. The
    pre-save copy is indexed by row name to find the rows a user actually touched.

    Announcements are merged into one popup -- one message per changed row would be
    unusable on a plan where somebody re-rated a batch of drawings.
    """
    # Same reasoning as _is_insert: on a first save every row looks changed, and a
    # plan can arrive with 500 of them. Its rows were just seeded from their own
    # drawings anyway, so there is nothing to send back.
    before = doc.get_doc_before_save()
    if before is None:
        return
    previous = {
        r.name: (r.get("custom_rate_schedule") or "")
        for r in (before.get("po_items") or [])
    }

    seeded = doc.flags.get("rate_schedule_seeded_rows") or set()

    merged, schedules = [], set()
    for row in (doc.get("po_items") or []):
        drawing = row.get("custom_drawing")
        if not drawing:
            continue
        # Filled in by seed_production_plan_rows from the drawing's own schedule --
        # copying it straight back out again is not an edit.
        if row.name in seeded:
            continue
        schedule = row.get("custom_rate_schedule") or ""
        # A row absent from the pre-save copy is newly added and was not seeded,
        # which means somebody typed a schedule into it -- that should travel.
        if previous.get(row.name, "") == schedule:
            continue
        result = propagate(drawing, schedule, "Production Plan Item", row.name)
        merged.extend(result.get("updated") or [])
        schedules.add(schedule)

    if merged:
        # Several drawings re-rated in one save can legitimately point at different
        # schedules; naming one of them in the header would be a lie.
        label = schedules.pop() if len(schedules) == 1 else _("the selected schedules")
        announce({"updated": merged}, label)
