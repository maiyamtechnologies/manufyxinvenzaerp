import frappe
from frappe import _

FORMULA_GROUPS = {"Structurals", "Plates"}

_LOCKED_FIELDS = {
    "custom_parent_item_group": "Parent Item Group",
    "stock_uom": "Default Unit of Measure",
    "custom_unit_weight": "Unit Weight",
    "custom_secondary_uom": "Secondary UOM",
    "custom_batch_prefix": "Custom Batch Abbreviation",
}

# Locked once SET, rather than outright. Spec and grade are mirrored onto 25 child
# tables by fetch_from and matched against the Sales Order sheet by Verify Raw
# Materials, so changing one on an Item already in use would leave rows fetched before
# the change describing a different material from rows fetched after it -- a different
# spec or grade is a different Item.
#
# But filling a BLANK one in is not a change of material, and it has to stay possible:
# when this lock arrived, every one of the 37 Items with transactions had neither set.
# Locking those outright would have left them unable ever to carry a spec or grade, and
# every sheet row naming one would have been refused by Verify with no fix short of a
# new Item for every material in stock.
_LOCK_ONCE_SET = {
    "custom_material_spec": "Material Spec",
    "custom_material_grade": "Material Grade",
}


def validate_item(doc, method):
    validate_parent_item_group(doc)
    set_calculation_type(doc)
    validate_uom_configuration(doc)
    validate_batch_configuration(doc)
    validate_fg_configuration(doc)
    validate_batch_prefix_not_fg(doc)
    validate_batch_prefix(doc)
    validate_locked_fields(doc)


def validate_parent_item_group(doc):
    if not doc.custom_parent_item_group:
        frappe.throw(_("Parent Item Group is mandatory"))


def set_calculation_type(doc):
    if doc.custom_parent_item_group in FORMULA_GROUPS:
        doc.custom_item_calculation_type = "Formula Weight Calculation"
    elif doc.custom_parent_item_group == "Nuts and Bolts":
        doc.custom_item_calculation_type = "Normal Weight Calculation"


def validate_uom_configuration(doc):
    parent_group = doc.custom_parent_item_group
    if not parent_group:
        return

    if parent_group in FORMULA_GROUPS:
        if doc.stock_uom and doc.stock_uom != "Kg":
            frappe.throw(
                _(
                    "System is configured for Primary UOM as KG for {0}. "
                    "Select Default UOM as Kg for Structurals Item Group"
                ).format(parent_group),
                title=_("UOM Configuration Warning"),
            )
        if doc.custom_secondary_uom and doc.custom_secondary_uom != "Nos":
            frappe.throw(
                _(
                    "System is configured for Secondary UOM as Nos for {0}. "
                    "Select Default UOM as Nos for Structurals Item Group"
                ).format(parent_group),
                title=_("Secondary UOM Warning"),
            )
    elif parent_group == "Nuts and Bolts":
        if doc.stock_uom and doc.stock_uom != "Nos":
            frappe.throw(
                _(
                    "System is configured for Primary UOM as NOS for {0}. "
                    "Select Default UOM as Nos for Nuts and Bolts Item Group"
                ).format(parent_group),
                title=_("UOM Configuration Warning"),
            )
        if doc.custom_secondary_uom and doc.custom_secondary_uom != "Kg":
            frappe.throw(
                _(
                    "System is configured for Secondary UOM as KG for {0}. "
                    "Select Default UOM as Kg for Nuts and Bolts Item Group"
                ).format(parent_group),
                title=_("Secondary UOM Warning"),
            )


def validate_batch_configuration(doc):
    if not doc.has_batch_no:
        return

    if doc.custom_parent_item_group in FORMULA_GROUPS:
        doc.create_new_batch = 1
        if not doc.custom_batch_prefix:
            frappe.throw(
                _("Custom Batch Abbreviation is required for {0} when Has Batch No is enabled").format(
                    doc.custom_parent_item_group
                )
            )


def validate_fg_configuration(doc):
    """Finished goods are stocked in Kg with the piece count as Sec Qty in Nos, in
    one batch per drawing that our code creates (sep14 FG plan, rule in one line).

    - Kg / Nos: every FG figure downstream (Final Stock Entry, Delivery Note,
      invoice) is Kg on the ledger and Nos alongside it; an item stocked in Nos
      books pieces as Kg, which is the live bug this plan fixes.
    - Has Batch No: the batch is what holds a drawing's Nos and its Kg per piece.
    - Create New Batch off, no prefix: fg_stock.get_or_create_fg_batch names and
      fills the batch itself (FG-<Sales Order>-<DUNO>). ERPNext's auto batch, or a
      prefix picked up by before_insert_batch, would make a second, empty-handed
      batch per entry instead.

    An item that already has transactions cannot change these safely (ERPNext
    refuses Has Batch No once stock exists, and _LOCKED_FIELDS refuses the UOMs),
    so it only gets an orange note. FINGOODS001 stays on its old set-up (D13).
    """
    from manufyxinvenzaerp.production_management.fg_stock import FG_PARENT_ITEM_GROUP

    # Read off the document, not is_fg_item(): a new item is not in the database yet.
    if doc.custom_parent_item_group != FG_PARENT_ITEM_GROUP:
        return

    problems = []
    if doc.stock_uom != "Kg":
        problems.append(_("Default Unit of Measure must be Kg (it is {0})").format(doc.stock_uom or "-"))
    if doc.custom_secondary_uom != "Nos":
        problems.append(
            _("Secondary UOM must be Nos (it is {0})").format(doc.custom_secondary_uom or "-")
        )
    if not doc.has_batch_no:
        problems.append(_("Has Batch No must be ticked"))
    if doc.custom_batch_prefix:
        problems.append(_("Custom Batch Abbreviation must be blank"))

    if doc.is_new() or not _has_transactions(doc.name):
        # Nothing to decide for the user: the batch is always created by our code.
        doc.create_new_batch = 0
        if problems:
            frappe.throw(
                _("Finished-goods item {0} is set up wrongly:").format(frappe.bold(doc.name or doc.item_code))
                + "<ul><li>" + "</li><li>".join(problems) + "</li></ul>"
                + _("Finished goods are stocked in Kg, carry their piece count in Nos, "
                    "and get one batch per drawing created by the system."),
                title=_("Finished Goods Set-up"),
            )
        return

    if doc.create_new_batch:
        problems.append(_("Automatically Create New Batch should be unticked"))
    if problems:
        frappe.msgprint(
            _("Finished-goods item {0} does not follow the Kg / Nos set-up, but it already "
              "has transactions, so it is left as it is:").format(frappe.bold(doc.name))
            + "<ul><li>" + "</li><li>".join(problems) + "</li></ul>",
            title=_("Finished Goods Set-up"),
            indicator="orange",
        )


def validate_batch_prefix_not_fg(doc):
    """The prefix FG is reserved for finished-goods batches (FG-<Sales Order>-<DUNO>).

    A raw-material prefix of FG would name its batches FG-..., and every place
    that recognises a finished-goods batch by its name, or searches batches for a
    Delivery Note, would then pick up steel. "FG-something" is refused for the
    same reason: it still starts with "FG-".
    """
    prefix = (doc.custom_batch_prefix or "").strip().upper()
    if prefix == "FG" or prefix.startswith("FG-"):
        frappe.throw(
            _("Custom Batch Abbreviation {0} is reserved for finished-goods batches. "
              "Choose a different abbreviation.").format(frappe.bold(doc.custom_batch_prefix)),
            title=_("Reserved Batch Abbreviation"),
        )


## This validation is required to prevent changing batch prefix when batches are already created with the old prefix, which can lead to data inconsistency.
def validate_batch_prefix(doc):
    if not doc.is_new():
        old_prefix = frappe.db.get_value("Item", doc.name, "custom_batch_prefix")
        if old_prefix and old_prefix != doc.custom_batch_prefix:
            batch_exists = frappe.db.exists("Batch", {"item": doc.name})

            if batch_exists:
                frappe.throw(
                    _("Cannot change the Custom Batch Abbreviation for Item {0} because existing transactions are linked to it.").format(doc.name)
                )


def _has_transactions(item_code):
    return bool(
        frappe.db.exists("Stock Ledger Entry", {"item_code": item_code})
        or frappe.db.exists("Purchase Order Item", {"item_code": item_code, "docstatus": 1})
        or frappe.db.exists("Sales Order Item", {"item_code": item_code, "docstatus": 1})
    )


def validate_locked_fields(doc):
    if doc.is_new() or not _has_transactions(doc.name):
        return
    for field, label in _LOCKED_FIELDS.items():
        if frappe.db.get_value("Item", doc.name, field) != doc.get(field):
            frappe.throw(
                _("Cannot change {0} for Item {1} because transactions already exist.").format(
                    label, doc.name
                )
            )
    for field, label in _LOCK_ONCE_SET.items():
        stored = frappe.db.get_value("Item", doc.name, field)
        if stored and stored != doc.get(field):
            frappe.throw(
                _("Cannot change {0} for Item {1} because transactions already exist. "
                  "A different {0} is a different material -- create a new Item for it.")
                .format(label, doc.name)
            )


@frappe.whitelist()
def has_item_transactions(item_code):
    return _has_transactions(item_code)