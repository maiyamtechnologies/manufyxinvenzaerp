"""Verify the follow-up client request on top of Phase 3.2/4.2/4.3:
  - Process Planning's "Skip Operation" checkbox renamed to "Create Operation",
    defaulting to enabled (checked) for every row.
  - _create_soes_for_sco only creates a Supplier Operation Entry for rows with
    Create Operation enabled -- disabled rows are skipped entirely, and the
    remaining SOEs' sequence_id stays contiguous (no gap left behind).
  - Each created SOE's custom_inspection_mandatory mirrors its source Process
    Planning row's Inspection Mandatory checkbox.
  - Submitting an SOE with custom_inspection_mandatory=1 is blocked until at
    least one Inspection Call has been logged -- NOT until custom_inspection_status
    reaches "Completed" (a looser gate than Purchase Receipt's own).

Run via: bench --site manufact execute manufyxinvenzaerp.tests.verify_create_operation_and_inspection_gate.run
"""

import frappe
from manufyxinvenzaerp.tests.create_full_test_entry import fill_process_planning_parties
from frappe.utils import today


def run():
    company = frappe.db.get_value("Company", {}, "name")
    bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_active": 1}, ["name", "item", "quantity"], as_dict=True)
    stock_uom = frappe.db.get_value("Item", bom.item, "stock_uom") or "Nos"
    print("company=", company, "bom=", bom)

    from manufyxinvenzaerp.subcontracting_management.subcontracting import (
        create_sco_from_production_plan,
        _create_soes_for_sco,
    )
    from manufyxinvenzaerp.production_management.inspection import add_inspection_call

    pp = frappe.new_doc("Production Plan")
    pp.custom_type = "Internal Job"
    pp.company = company
    pp.posting_date = today()
    pp.get_items_from = ""
    pp.append("po_items", {"item_code": bom.item, "bom_no": bom.name, "planned_qty": bom.quantity or 1, "stock_uom": stock_uom})
    # Row 1: enabled, no inspection.
    pp.append("custom_process_planning", {
        "operation_name": "Material Issue", "work_type": "Internal Jobcard",
        "create_operation": 1, "inspection_mandatory": 0,
    })
    # Row 2: DISABLED -- should be skipped entirely, no SOE created for it.
    pp.append("custom_process_planning", {
        "operation_name": "Fit-up", "work_type": "Internal Jobcard",
        "create_operation": 0, "inspection_mandatory": 0,
    })
    # Row 3: enabled, inspection mandatory.
    pp.append("custom_process_planning", {
        "operation_name": "Welding", "work_type": "Internal Jobcard",
        "create_operation": 1, "inspection_mandatory": 1,
    })
    pp.insert(ignore_permissions=True)
    fill_process_planning_parties(pp)
    pp.submit()
    print("Created Production Plan:", pp.name)

    sco_name = create_sco_from_production_plan(pp.name)
    sco = frappe.get_doc("Subcontracting Order", sco_name)
    print("Created SCO:", sco_name)

    soe_names = _create_soes_for_sco(sco)
    print("SOEs created:", soe_names)
    assert len(soe_names) == 2, f"Expected 2 SOEs (row 2 disabled), got {len(soe_names)}"

    soes = [frappe.get_doc("Supplier Operation Entry", n) for n in soe_names]
    soes.sort(key=lambda d: d.sequence_id)

    print("SOE 1:", soes[0].operation, "seq=", soes[0].sequence_id, "inspection_mandatory=", soes[0].custom_inspection_mandatory)
    print("SOE 2:", soes[1].operation, "seq=", soes[1].sequence_id, "inspection_mandatory=", soes[1].custom_inspection_mandatory)

    assert soes[0].operation == "Material Issue", "Row 1 (Material Issue) should be the first SOE"
    assert soes[1].operation == "Welding", "Row 3 (Welding) should be the second SOE -- Fit-up (disabled) must be skipped entirely"
    assert soes[0].sequence_id == 1 and soes[1].sequence_id == 2, "sequence_id must be contiguous (1,2), no gap for the skipped row"
    assert not soes[0].custom_inspection_mandatory, "Material Issue row was not inspection-mandatory"
    assert soes[1].custom_inspection_mandatory, "Welding row's custom_inspection_mandatory should mirror the PP row's checkbox"

    # Non-inspection SOE should submit freely once its own (pre-existing, unrelated)
    # Status field is set to Completed.
    soes[0].reload()
    soes[0].status = "Completed"
    soes[0].save(ignore_permissions=True)
    soes[0].reload()
    soes[0].submit()
    print("SOE 1 (Material Issue, no inspection) submitted OK.")

    # Inspection-mandatory SOE must be blocked without any inspection call, even
    # with Status already set to Completed.
    welding_soe = soes[1]
    welding_soe.reload()
    welding_soe.status = "Completed"
    welding_soe.save(ignore_permissions=True)
    welding_soe.reload()
    try:
        welding_soe.submit()
        print("ERROR: should have been blocked -- no inspection call logged yet")
        raise AssertionError("Expected submit to be blocked")
    except frappe.exceptions.ValidationError as e:
        print("OK blocked submit with no inspection call:", str(e)[:150])

    # Log a call (status stays "Pending", NOT "Completed") -- submit should now succeed,
    # since the gate only requires a call to exist, not a completed inspection.
    welding_soe.reload()
    welding_soe.custom_inspection_call_date = today()
    welding_soe.save(ignore_permissions=True)
    add_inspection_call("Supplier Operation Entry", welding_soe.name)

    welding_soe.reload()
    print("Inspection call log rows:", len(welding_soe.custom_inspection_call_log or []))
    print("custom_inspection_status (expect NOT Completed):", welding_soe.custom_inspection_status)
    assert welding_soe.custom_inspection_call_log, "Expected at least one inspection call logged"
    assert welding_soe.custom_inspection_status != "Completed", "Test setup: status should still not be Completed"

    welding_soe.submit()
    print("SOE 2 (Welding, inspection mandatory) submitted OK after just ONE call logged -- gate correctly did not require Completed status.")

    frappe.db.commit()
    print("\nALL CHECKS DONE.")
    print("Test data left in place:", pp.name, sco_name, [s.name for s in soes])
