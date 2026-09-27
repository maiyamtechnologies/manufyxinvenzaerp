"""One-off: put back the batch the user had picked for each Material Mapping row of
MP-2026-00016 (one batch per item), the way the grid does, then Reserve."""
import math

import frappe
from frappe.utils import flt

MP = "MP-2026-00016"
BATCH = {
    "ISA100": "ISA100-L390-R009",
    "ISMB250": "ISMB250-L7479-R009",
    "ISMB400": "ISMB400-L6936-R009",
    "PLATE10": "PLT10-T10-L731-W311-R009",
}


def run():
    from manufyxinvenzaerp.production_management.doctype.material_planning import material_planning as m

    mp = frappe.get_doc("Material Planning", MP)
    for row in mp.material_mapping:
        if row.batch:
            continue
        b = BATCH[row.item_code]
        m._apply_batch_to_mapping_row(row, b, row.item_code, {}, None, 0)
        # As the grid does on picking a batch (material_planning.js): the batch's Nos
        # is the row's Kg in pieces of that batch, fractional.
        # Rounded UP at the 3rd decimal: rounding to nearest can land a gram under the
        # requirement, which the plan's own validation refuses (Row 8: 40.526 < 40.528).
        kg = m._calc_kg_per_nos(row.batch_parent_item_group, row.batch_length, row.batch_width,
                                row.batch_thickness, row.batch_unit_weight)
        row.batch_sec_qty = math.ceil(flt(row.qty) / kg * 1000 - 1e-6) / 1000.0
        row.batch_calc_qty = m._calc_batch_qty(row.batch_parent_item_group, row.batch_length, row.batch_width,
                                               row.batch_thickness, row.batch_sec_qty, row.batch_unit_weight)
    mp.save()
    m.reserve_batches(MP)
    mp = frappe.get_doc("Material Planning", MP)
    rows = list(mp.available_raw_materials) + list(mp.material_mapping)
    print("reserved %d of %d rows, status %s" % (sum(1 for r in rows if r.is_reserved), len(rows), mp.planning_status))
    frappe.db.commit()
