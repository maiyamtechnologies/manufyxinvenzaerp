# app_map — manufyxinvenzaerp

_Generated: 2026-09-04 00:52:54_

## Modules

- accounts_management
- config
- drawing_management
- item_management
- manufyxinvenzaerp
- material_request_management
- patches
- production_management
- production_plan_management
- public
- purchase_order_management
- purchase_receipt_management
- rfq_management
- sq_management
- subcontracting_management
- templates
- tests
- utils

## Python files

_Total: 288_

- accounts_management/__init__.py
- accounts_management/payment_entry.py
- accounts_management/payment_request.py
- accounts_management/report/customer_fund_usage/customer_fund_usage.py
- accounts_management/report/customer_fund_usage/__init__.py
- accounts_management/report/__init__.py
- config/__init__.py
- drawing_management/bom_class_override.py
- drawing_management/doctype/drawing/drawing.py
- drawing_management/doctype/drawing/__init__.py
- drawing_management/doctype/drawing_item/drawing_item.py
- drawing_management/doctype/drawing_item/__init__.py
- drawing_management/doctype/drawing_weight_change_log/drawing_weight_change_log.py
- drawing_management/doctype/drawing_weight_change_log/__init__.py
- drawing_management/doctype/__init__.py
- drawing_management/doctype/job_nature/__init__.py
- drawing_management/doctype/job_nature/job_nature.py
- drawing_management/doctype/nature_of_work/__init__.py
- drawing_management/doctype/nature_of_work/nature_of_work.py
- drawing_management/doctype/production_plan_bom_raw_material/__init__.py
- drawing_management/doctype/production_plan_bom_raw_material/production_plan_bom_raw_material.py
- drawing_management/doctype/rate_schedule/__init__.py
- drawing_management/doctype/rate_schedule_price_log/__init__.py
- drawing_management/doctype/rate_schedule_price_log/rate_schedule_price_log.py
- drawing_management/doctype/rate_schedule/rate_schedule.py
- drawing_management/doctype/sales_order_drawing_raw_material/__init__.py
- drawing_management/doctype/sales_order_drawing_raw_material/sales_order_drawing_raw_material.py
- drawing_management/doctype/sales_order_duno_item/__init__.py
- drawing_management/doctype/sales_order_duno_item/sales_order_duno_item.py
- drawing_management/drawing_utils.py
- drawing_management/__init__.py
- drawing_management/sales_order.py
- drawing_management/so_drawing_import.py
- hooks.py
- __init__.py
- item_management/__init__.py
- item_management/item.py
- manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py
- manufyxinvenzaerp/doctype/delivery_challan/__init__.py
- manufyxinvenzaerp/doctype/delivery_challan_item/delivery_challan_item.py
- manufyxinvenzaerp/doctype/delivery_challan_item/__init__.py
- manufyxinvenzaerp/doctype/gate_pass_purpose/gate_pass_purpose.py
- manufyxinvenzaerp/doctype/gate_pass_purpose/__init__.py
- manufyxinvenzaerp/doctype/__init__.py
- manufyxinvenzaerp/doctype/manufyxinvenza_settings/__init__.py
- manufyxinvenzaerp/doctype/manufyxinvenza_settings/manufyxinvenza_settings.py
- manufyxinvenzaerp/__init__.py
- manufyxinvenzaerp/page/bulk_permissions/__init__.py
- manufyxinvenzaerp/page/__init__.py
- material_request_management/__init__.py
- material_request_management/material_request.py
- patches/__init__.py
- patches/v1/backfill_drawing_rate_schedule_type.py
- patches/v1/backfill_duno_calculated_weight.py
- patches/v1/backfill_payment_entry_created_flag.py
- patches/v1/backfill_production_plan_status.py
- patches/v1/backfill_sco_status.py
- patches/v1/fix_bom_item_number_field_type.py
- patches/v1/__init__.py
- patches/v1/remove_sco_transfer_fields.py
- patches/v1/remove_wo_transfer_fields.py
- patches/v1/rename_excess_batch_mapped_statuses.py
- patches/v1/scale_customer_weight_by_qty.py
- permissions_bulk.py
- production_management/doctype/cut_sheet_allocation/cut_sheet_allocation.py
- production_management/doctype/cut_sheet_allocation/__init__.py
- production_management/doctype/cut_sheet/cut_sheet.py
- production_management/doctype/cut_sheet/__init__.py
- production_management/doctype/__init__.py
- production_management/doctype/inspection_call_log/__init__.py
- production_management/doctype/inspection_call_log/inspection_call_log.py
- production_management/doctype/inspection_entry/__init__.py
- production_management/doctype/inspection_entry/inspection_entry.py
- production_management/doctype/inspection_entry_item/__init__.py
- production_management/doctype/inspection_entry_item/inspection_entry_item.py
- production_management/doctype/job_card_raw_material/__init__.py
- production_management/doctype/job_card_raw_material/job_card_raw_material.py
- production_management/doctype/manufyx_decision_log/__init__.py
- production_management/doctype/manufyx_decision_log/manufyx_decision_log.py
- production_management/doctype/material_planning_available_raw_material/__init__.py
- production_management/doctype/material_planning_available_raw_material/material_planning_available_raw_material.py
- production_management/doctype/material_planning_batch_change_log/__init__.py
- production_management/doctype/material_planning_batch_change_log/material_planning_batch_change_log.py
- production_management/doctype/material_planning_bom_item/__init__.py
- production_management/doctype/material_planning_bom_item/material_planning_bom_item.py
- production_management/doctype/material_planning_consolidate_item/__init__.py
- production_management/doctype/material_planning_consolidate_item/material_planning_consolidate_item.py
- production_management/doctype/material_planning/__init__.py
- production_management/doctype/material_planning_material_mapping/__init__.py
- production_management/doctype/material_planning_material_mapping/material_planning_material_mapping.py
- production_management/doctype/material_planning/material_planning.py
- production_management/doctype/material_planning_raw_material/__init__.py
- production_management/doctype/material_planning_raw_material/material_planning_raw_material.py
- production_management/doctype/material_planning/test_material_planning.py
- production_management/doctype/material_planning_unavailable_item/__init__.py
- production_management/doctype/material_planning_unavailable_item/material_planning_unavailable_item.py
- production_management/doctype/process_planning/__init__.py
- production_management/doctype/process_planning/process_planning.py
- production_management/doctype/production_plan_available_raw_material/__init__.py
- production_management/doctype/production_plan_available_raw_material/production_plan_available_raw_material.py
- production_management/doctype/storage_location/__init__.py
- production_management/doctype/storage_location/storage_location.py
- production_management/doctype/store_location/__init__.py
- production_management/doctype/store_location/store_location.py
- production_management/__init__.py
- production_management/inspection.py
- production_management/manual_release_check.py
- production_management/page/erp_manual/__init__.py
- production_management/production_utils.py
- production_management/report/cut_sheet_report/cut_sheet_report.py
- production_management/report/cut_sheet_report/__init__.py
- production_management/report/__init__.py
- production_management/report/inspection_status_report/__init__.py
- production_management/report/inspection_status_report/inspection_status_report.py
- production_management/report/inventory_report/__init__.py
- production_management/report/inventory_report/inventory_report.py
- production_management/report/manufyxinvenza_stock_balance/__init__.py
- production_management/report/manufyxinvenza_stock_balance/manufyxinvenza_stock_balance.py
- production_management/report/production_report/__init__.py
- production_management/report/production_report/production_report.py
- production_management/stock_entry.py
- production_plan_management/production_plan.py
- pull_live.py
- purchase_order_management/__init__.py
- purchase_order_management/purchase_order.py
- purchase_receipt_management/__init__.py
- purchase_receipt_management/purchase_receipt.py
- rfq_management/__init__.py
- rfq_management/request_for_quotation.py
- sample_data.py
- setup.py
- sq_management/__init__.py
- sq_management/supplier_quotation.py
- subcontracting_management/doctype/__init__.py
- subcontracting_management/doctype/job_card_consumption_log/__init__.py
- subcontracting_management/doctype/job_card_consumption_log/job_card_consumption_log.py
- subcontracting_management/doctype/material_issue_plan_consolidate_item/__init__.py
- subcontracting_management/doctype/material_issue_plan_consolidate_item/material_issue_plan_consolidate_item.py
- subcontracting_management/doctype/material_issue_plan/__init__.py
- subcontracting_management/doctype/material_issue_plan/material_issue_plan.py
- subcontracting_management/doctype/material_issue_plan_raw_material/__init__.py
- subcontracting_management/doctype/material_issue_plan_raw_material/material_issue_plan_raw_material.py
- subcontracting_management/doctype/sco_drawing_item/__init__.py
- subcontracting_management/doctype/sco_drawing_item/sco_drawing_item.py
- subcontracting_management/doctype/sco_excess_material_item/__init__.py
- subcontracting_management/doctype/sco_excess_material_item/sco_excess_material_item.py
- subcontracting_management/doctype/soe_consumption_log/__init__.py
- subcontracting_management/doctype/soe_consumption_log/soe_consumption_log.py
- subcontracting_management/doctype/soe_drawing_detail/__init__.py
- subcontracting_management/doctype/soe_drawing_detail/soe_drawing_detail.py
- subcontracting_management/doctype/soe_inspection_item/__init__.py
- subcontracting_management/doctype/soe_inspection_item/soe_inspection_item.py
- subcontracting_management/doctype/supplier_operation_entry/__init__.py
- subcontracting_management/doctype/supplier_operation_entry/supplier_operation_entry.py
- subcontracting_management/doctype/supplier_operation_item/__init__.py
- subcontracting_management/doctype/supplier_operation_item/supplier_operation_item.py
- subcontracting_management/__init__.py
- subcontracting_management/material_issue_plan_transfer.py
- subcontracting_management/overrides.py
- subcontracting_management/report/excess_material_return_report/excess_material_return_report.py
- subcontracting_management/report/excess_material_return_report/__init__.py
- subcontracting_management/report/__init__.py
- subcontracting_management/subcontracting.py
- templates/__init__.py
- templates/pages/__init__.py
- tests/_chk_tmp.py
- tests/create_full_test_entry.py
- tests/create_test_data.py
- tests/find_cascade_fixture.py
- tests/find_clean_mp.py
- tests/_find_mip_excess.py
- tests/__init__.py
- tests/move_fixtures_to_custom_json.py
- tests/_probe_ab.py
- tests/_probe_tmp.py
- tests/_render_challan.py
- tests/reset_transactions.py
- tests/revert_wo_jc_cleanup.py
- tests/_t_close.py
- tests/_t_cs.py
- tests/test_alternate_item.py
- tests/test_classification_logic.py
- tests/test_e2e_material_planning.py
- tests/test_material_planning.py
- tests/test_po_edge_cases.py
- tests/test_purchase_order_creation.py
- tests/test_unavailable_actions.py
- tests/test_whitelist_coverage.py
- tests/_t_loss.py
- tests/_t_sample.py
- tests/verify_auto_purchase_gated.py
- tests/verify_batch_receipt_line_match.py
- tests/verify_batch_remark_isolation.py
- tests/verify_batch_remarks.py
- tests/verify_batch_sec_qty_atomic.py
- tests/verify_billed_to_consume.py
- tests/verify_bom_nature_of_work_rate_schedule.py
- tests/verify_bom_routing_new_bom.py
- tests/verify_bom_routing_trim.py
- tests/verify_bulk_permissions.py
- tests/verify_cancelled_drawing_link.py
- tests/verify_cnc_consumption_and_kg_chain.py
- tests/verify_consolidate_alternate_item.py
- tests/verify_consolidate_finalize.py
- tests/verify_consolidate_item2.py
- tests/verify_consolidate_item.py
- tests/verify_consolidate_sec_qty_editable.py
- tests/verify_consumable_entry.py
- tests/verify_consumption_log_hard_cap.py
- tests/verify_create_operation_and_inspection_gate.py
- tests/verify_customer_weight_scaled.py
- tests/verify_cut_sheet_delete_guards.py
- tests/verify_cut_sheet_doctype.py
- tests/verify_cut_sheet_excess_visibility.py
- tests/verify_cut_sheet_fields_consistent.py
- tests/verify_cut_sheet_new_batch.py
- tests/verify_cutsheet_status_and_load_fixes.py
- tests/verify_cut_sheet_w2_derived.py
- tests/verify_decision_log.py
- tests/verify_delivery_challan.py
- tests/verify_drawing_create_revision.py
- tests/verify_drawing_import_savepoint.py
- tests/verify_drawing_weight_cascade2.py
- tests/verify_drawing_weight_cascade.py
- tests/verify_excess_claim_lifecycle.py
- tests/verify_excess_material_mapping.py
- tests/verify_excess_material_mapping_row_btn.py
- tests/verify_excess_partial_and_flags.py
- tests/verify_excess_return_and_process_loss.py
- tests/verify_excess_weight_or_pieces.py
- tests/verify_internal_job_sco.py
- tests/verify_manual_mr_multi_supplier.py
- tests/verify_mapped_status_lists_match.py
- tests/verify_mapping_batch_warehouse.py
- tests/verify_material_planning_health.py
- tests/verify_mip_consolidated_allocation.py
- tests/verify_mip_consolidate_items.py
- tests/verify_mip_excess_plan_tab.py
- tests/verify_mip_post_purchase_refresh.py
- tests/verify_mip_raw_material_slimmed.py
- tests/verify_mixed_sco_regression.py
- tests/verify_mp_inspection_gate.py
- tests/verify_mp_multi_mr_guard_message.py
- tests/verify_mp_view_all_filters.py
- tests/verify_no_create_production_plan_button.py
- tests/verify_no_item_default_bom.py
- tests/verify_no_zero_qty_exact_match.py
- tests/verify_operation_close_and_sco_status.py
- tests/verify_partial_final_stock_entry.py
- tests/verify_partial_transfer_reservation.py
- tests/verify_per_row_unreserve.py
- tests/verify_planning_status_follows_reservations.py
- tests/verify_pp_naming.py
- tests/verify_pr_allocation_recovery.py
- tests/verify_pr_allocation_single_table.py
- tests/verify_pr_inspection.py
- tests/verify_process_planning_fields.py
- tests/verify_production_report.py
- tests/verify_pr_partial_receipt_allocation.py
- tests/verify_pr_sequential_allocation.py
- tests/verify_purchase_size_warning.py
- tests/verify_reassign_batch_exact_match2.py
- tests/verify_reassign_batch_exact_match.py
- tests/verify_reassign_batch_inspection_blocked.py
- tests/verify_receipt_allocates_after_recheck.py
- tests/verify_reservation_permission_guard.py
- tests/verify_reservation_release_on_transfer.py
- tests/verify_return_excess_dialog.py
- tests/verify_rm_issue_row_numbers.py
- tests/verify_rwd_two_way.py
- tests/verify_se_duno_propagation.py
- tests/verify_so_calculated_weight.py
- tests/verify_so_drawing_buttons.py
- tests/verify_soe_consumption_weight_kg.py
- tests/verify_soe_summary_available.py
- tests/verify_so_raw_material_checks.py
- tests/verify_status_mirror.py
- tests/verify_testing_button_gated.py
- tests/verify_transfer_draft.py
- tests/verify_unreserve_after_transfer.py
- tests/verify_unreserve_btn_meta.py
- tests/verify_weight_cascade_reaches_soe.py
- tests/verify_wo_jc_standard2.py
- tests/verify_wo_jc_standard.py
- utils/decision_log.py
- utils/dimension_formula.py
- utils/__init__.py
- utils/reference_copy.py

## JavaScript files

_Total: 26_

- accounts_management/report/customer_fund_usage/customer_fund_usage.js
- drawing_management/doctype/drawing/drawing.js
- manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.js
- manufyxinvenzaerp/doctype/delivery_challan/delivery_challan_list.js
- manufyxinvenzaerp/page/bulk_permissions/bulk_permissions.js
- production_management/doctype/cut_sheet/cut_sheet.js
- production_management/doctype/material_planning/material_planning.js
- production_management/page/erp_manual/erp_manual.js
- production_management/report/cut_sheet_report/cut_sheet_report.js
- production_management/report/inspection_status_report/inspection_status_report.js
- production_management/report/inventory_report/inventory_report.js
- production_management/report/manufyxinvenza_stock_balance/manufyxinvenza_stock_balance.js
- production_management/report/production_report/production_report.js
- public/js/batch.js
- public/js/bom.js
- public/js/inspection_entry.js
- public/js/item.js
- public/js/manual_renderer.js
- public/js/manufyxinvenzaerp.bundle.js
- public/js/payment_request.js
- public/js/production_plan.js
- public/js/purchase_order.js
- public/js/purchase_receipt.js
- public/js/supplier_operation_entry.js
- subcontracting_management/doctype/material_issue_plan/material_issue_plan.js
- subcontracting_management/report/excess_material_return_report/excess_material_return_report.js

## JSON files

_Total: 166_

- accounts_management/custom/payment_entry.json
- accounts_management/custom/payment_request.json
- accounts_management/report/customer_fund_usage/customer_fund_usage.json
- drawing_management/custom/bom_explosion_item.json
- drawing_management/custom/bom_item.json
- drawing_management/custom/bom.json
- drawing_management/custom/drawing_item.json
- drawing_management/custom/drawing.json
- drawing_management/custom/sales_order_item.json
- drawing_management/custom/sales_order.json
- drawing_management/doctype/drawing/drawing.json
- drawing_management/doctype/drawing_item/drawing_item.json
- drawing_management/doctype/drawing_weight_change_log/drawing_weight_change_log.json
- drawing_management/doctype/job_nature/job_nature.json
- drawing_management/doctype/nature_of_work/nature_of_work.json
- drawing_management/doctype/production_plan_bom_raw_material/production_plan_bom_raw_material.json
- drawing_management/doctype/rate_schedule_price_log/rate_schedule_price_log.json
- drawing_management/doctype/rate_schedule/rate_schedule.json
- drawing_management/doctype/sales_order_drawing_raw_material/sales_order_drawing_raw_material.json
- drawing_management/doctype/sales_order_duno_item/sales_order_duno_item.json
- manufyxinvenzaerp/custom/accounts_settings.json
- manufyxinvenzaerp/custom/address.json
- manufyxinvenzaerp/custom/advance_taxes_and_charges.json
- manufyxinvenzaerp/custom/asset_capitalization.json
- manufyxinvenzaerp/custom/asset_capitalization_stock_item.json
- manufyxinvenzaerp/custom/asset.json
- manufyxinvenzaerp/custom/asset_repair.json
- manufyxinvenzaerp/custom/batch.json
- manufyxinvenzaerp/custom/bill_of_entry.json
- manufyxinvenzaerp/custom/communication.json
- manufyxinvenzaerp/custom/company.json
- manufyxinvenzaerp/custom/contact.json
- manufyxinvenzaerp/custom/customer.json
- manufyxinvenzaerp/custom/delivery_note_item.json
- manufyxinvenzaerp/custom/delivery_note.json
- manufyxinvenzaerp/custom/department.json
- manufyxinvenzaerp/custom/designation.json
- manufyxinvenzaerp/custom/dunning.json
- manufyxinvenzaerp/custom/email_account.json
- manufyxinvenzaerp/custom/employee.json
- manufyxinvenzaerp/custom/employee_tax_exemption_declaration.json
- manufyxinvenzaerp/custom/employee_tax_exemption_proof_submission.json
- manufyxinvenzaerp/custom/e_waybill_log.json
- manufyxinvenzaerp/custom/expense_claim.json
- manufyxinvenzaerp/custom/finance_book.json
- manufyxinvenzaerp/custom/gl_entry.json
- manufyxinvenzaerp/custom/income_tax_slab.json
- manufyxinvenzaerp/custom/invoice_discounting.json
- manufyxinvenzaerp/custom/item_barcode.json
- manufyxinvenzaerp/custom/item_group.json
- manufyxinvenzaerp/custom/item.json
- manufyxinvenzaerp/custom/item_tax_template.json
- manufyxinvenzaerp/custom/journal_entry_account.json
- manufyxinvenzaerp/custom/journal_entry.json
- manufyxinvenzaerp/custom/landed_cost_voucher.json
- manufyxinvenzaerp/custom/material_request_item.json
- manufyxinvenzaerp/custom/material_request.json
- manufyxinvenzaerp/custom/material_request_plan_item.json
- manufyxinvenzaerp/custom/packed_item.json
- manufyxinvenzaerp/custom/packing_slip_item.json
- manufyxinvenzaerp/custom/period_closing_voucher.json
- manufyxinvenzaerp/custom/pick_list.json
- manufyxinvenzaerp/custom/pos_invoice_item.json
- manufyxinvenzaerp/custom/pos_invoice.json
- manufyxinvenzaerp/custom/print_settings.json
- manufyxinvenzaerp/custom/process_deferred_accounting.json
- manufyxinvenzaerp/custom/project.json
- manufyxinvenzaerp/custom/purchase_invoice_item.json
- manufyxinvenzaerp/custom/purchase_invoice.json
- manufyxinvenzaerp/custom/purchase_order_item.json
- manufyxinvenzaerp/custom/purchase_order.json
- manufyxinvenzaerp/custom/purchase_receipt_item.json
- manufyxinvenzaerp/custom/purchase_receipt_item_supplied.json
- manufyxinvenzaerp/custom/purchase_receipt.json
- manufyxinvenzaerp/custom/purchase_reconciliation_tool.json
- manufyxinvenzaerp/custom/purchase_taxes_and_charges.json
- manufyxinvenzaerp/custom/putaway_rule.json
- manufyxinvenzaerp/custom/quality_inspection.json
- manufyxinvenzaerp/custom/quotation_item.json
- manufyxinvenzaerp/custom/quotation.json
- manufyxinvenzaerp/custom/request_for_quotation_item.json
- manufyxinvenzaerp/custom/salary_component.json
- manufyxinvenzaerp/custom/salary_slip.json
- manufyxinvenzaerp/custom/sales_invoice_item.json
- manufyxinvenzaerp/custom/sales_invoice.json
- manufyxinvenzaerp/custom/sales_taxes_and_charges.json
- manufyxinvenzaerp/custom/serial_and_batch_bundle.json
- manufyxinvenzaerp/custom/stock_ledger_entry.json
- manufyxinvenzaerp/custom/stock_reconciliation_item.json
- manufyxinvenzaerp/custom/stock_reconciliation.json
- manufyxinvenzaerp/custom/supplier.json
- manufyxinvenzaerp/custom/supplier_quotation_item.json
- manufyxinvenzaerp/custom/supplier_quotation.json
- manufyxinvenzaerp/custom/task.json
- manufyxinvenzaerp/custom/tax_category.json
- manufyxinvenzaerp/custom/tax_withholding_category.json
- manufyxinvenzaerp/custom/terms_and_conditions.json
- manufyxinvenzaerp/custom/timesheet.json
- manufyxinvenzaerp/custom/user.json
- manufyxinvenzaerp/custom/warranty_claim.json
- manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.json
- manufyxinvenzaerp/doctype/delivery_challan_item/delivery_challan_item.json
- manufyxinvenzaerp/doctype/gate_pass_purpose/gate_pass_purpose.json
- manufyxinvenzaerp/doctype/manufyxinvenza_settings/manufyxinvenza_settings.json
- manufyxinvenzaerp/page/bulk_permissions/bulk_permissions.json
- manufyxinvenzaerp/workspace/manufyx/manufyx.json
- production_management/custom/inspection_entry.json
- production_management/custom/job_card.json
- production_management/custom/manufacturing_settings.json
- production_management/custom/material_planning_available_raw_material.json
- production_management/custom/material_planning_consolidate_item.json
- production_management/custom/material_planning.json
- production_management/custom/material_planning_material_mapping.json
- production_management/custom/production_plan_available_raw_material.json
- production_management/custom/production_plan_bom_raw_material.json
- production_management/custom/production_plan_item.json
- production_management/custom/production_plan.json
- production_management/custom/stock_entry_detail.json
- production_management/custom/stock_entry.json
- production_management/custom/work_order.json
- production_management/doctype/cut_sheet_allocation/cut_sheet_allocation.json
- production_management/doctype/cut_sheet/cut_sheet.json
- production_management/doctype/inspection_call_log/inspection_call_log.json
- production_management/doctype/inspection_entry/inspection_entry.json
- production_management/doctype/inspection_entry_item/inspection_entry_item.json
- production_management/doctype/job_card_raw_material/job_card_raw_material.json
- production_management/doctype/manufyx_decision_log/manufyx_decision_log.json
- production_management/doctype/material_planning_available_raw_material/material_planning_available_raw_material.json
- production_management/doctype/material_planning_batch_change_log/material_planning_batch_change_log.json
- production_management/doctype/material_planning_bom_item/material_planning_bom_item.json
- production_management/doctype/material_planning_consolidate_item/material_planning_consolidate_item.json
- production_management/doctype/material_planning_material_mapping/material_planning_material_mapping.json
- production_management/doctype/material_planning/material_planning.json
- production_management/doctype/material_planning_raw_material/material_planning_raw_material.json
- production_management/doctype/material_planning_unavailable_item/material_planning_unavailable_item.json
- production_management/doctype/process_planning/process_planning.json
- production_management/doctype/production_plan_available_raw_material/production_plan_available_raw_material.json
- production_management/doctype/storage_location/storage_location.json
- production_management/doctype/store_location/store_location.json
- production_management/page/erp_manual/erp_manual.json
- production_management/report/cut_sheet_report/cut_sheet_report.json
- production_management/report/inspection_status_report/inspection_status_report.json
- production_management/report/inventory_report/inventory_report.json
- production_management/report/manufyxinvenza_stock_balance/manufyxinvenza_stock_balance.json
- production_management/report/production_report/production_report.json
- subcontracting_management/custom/material_issue_plan.json
- subcontracting_management/custom/soe_drawing_detail.json
- subcontracting_management/custom/subcontracting_order_item.json
- subcontracting_management/custom/subcontracting_order.json
- subcontracting_management/custom/subcontracting_receipt_item.json
- subcontracting_management/custom/subcontracting_receipt.json
- subcontracting_management/custom/subcontracting_receipt_supplied_item.json
- subcontracting_management/custom/supplier_operation_entry.json
- subcontracting_management/custom/supplier_operation_item.json
- subcontracting_management/doctype/job_card_consumption_log/job_card_consumption_log.json
- subcontracting_management/doctype/material_issue_plan_consolidate_item/material_issue_plan_consolidate_item.json
- subcontracting_management/doctype/material_issue_plan/material_issue_plan.json
- subcontracting_management/doctype/material_issue_plan_raw_material/material_issue_plan_raw_material.json
- subcontracting_management/doctype/sco_drawing_item/sco_drawing_item.json
- subcontracting_management/doctype/sco_excess_material_item/sco_excess_material_item.json
- subcontracting_management/doctype/soe_consumption_log/soe_consumption_log.json
- subcontracting_management/doctype/soe_drawing_detail/soe_drawing_detail.json
- subcontracting_management/doctype/soe_inspection_item/soe_inspection_item.json
- subcontracting_management/doctype/supplier_operation_entry/supplier_operation_entry.json
- subcontracting_management/doctype/supplier_operation_item/supplier_operation_item.json
- subcontracting_management/report/excess_material_return_report/excess_material_return_report.json

## Doctypes

### drawing
- Path: `drawing_management/doctype/drawing`
- Controller: `drawing_management/doctype/drawing/drawing.py`
- Client script: `drawing_management/doctype/drawing/drawing.js`
- Methods:
  - before_insert:
  - validate:
  - before_submit:
  - on_submit:
  - on_cancel:
  - _recalculate_all:
  - _check_missing_fields:
  - _calculate_totals:
  - _sales_order_row:
  - _touch_sales_order:
  - _release_sales_order_row:
  - _link_to_sales_order_row:
  - _recalculate_row_qty:
  - _recalculate_row_totals:
  - _check_row_missing_fields:
  - check_existing_bom:

### drawing_item
- Path: `drawing_management/doctype/drawing_item`
- Controller: `drawing_management/doctype/drawing_item/drawing_item.py`
- Client script: none

### drawing_weight_change_log
- Path: `drawing_management/doctype/drawing_weight_change_log`
- Controller: `drawing_management/doctype/drawing_weight_change_log/drawing_weight_change_log.py`
- Client script: none

### job_nature
- Path: `drawing_management/doctype/job_nature`
- Controller: `drawing_management/doctype/job_nature/job_nature.py`
- Client script: none

### nature_of_work
- Path: `drawing_management/doctype/nature_of_work`
- Controller: `drawing_management/doctype/nature_of_work/nature_of_work.py`
- Client script: none

### production_plan_bom_raw_material
- Path: `drawing_management/doctype/production_plan_bom_raw_material`
- Controller: `drawing_management/doctype/production_plan_bom_raw_material/production_plan_bom_raw_material.py`
- Client script: none

### rate_schedule_price_log
- Path: `drawing_management/doctype/rate_schedule_price_log`
- Controller: `drawing_management/doctype/rate_schedule_price_log/rate_schedule_price_log.py`
- Client script: none

### rate_schedule
- Path: `drawing_management/doctype/rate_schedule`
- Controller: `drawing_management/doctype/rate_schedule/rate_schedule.py`
- Client script: none
- Methods:
  - before_insert:
  - validate:
  - _track_rate_change:

### sales_order_drawing_raw_material
- Path: `drawing_management/doctype/sales_order_drawing_raw_material`
- Controller: `drawing_management/doctype/sales_order_drawing_raw_material/sales_order_drawing_raw_material.py`
- Client script: none

### sales_order_duno_item
- Path: `drawing_management/doctype/sales_order_duno_item`
- Controller: `drawing_management/doctype/sales_order_duno_item/sales_order_duno_item.py`
- Client script: none

### delivery_challan
- Path: `manufyxinvenzaerp/doctype/delivery_challan`
- Controller: `manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py`
- Client script: `manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.js`
- Methods:
  - validate:
  - on_submit:
  - on_cancel:
  - _set_defaults:
  - _validate_type_rules:
  - _validate_against_gate_pass:
  - _validate_items:
  - _calculate_totals:
  - _validate_return_quantities:
  - _set_status:
  - _compute_status:
  - _status_for_returnable:
  - _returned_by_row:
  - _refresh_source_gate_pass:
  - refresh_overdue_gate_passes:
  - make_return_entry:
  - postprocess:
  - update_item:
  - _pending_by_row:
  - gate_pass_return_query:
  - _default_address:
  - _party_display_name:
  - _party_address:
  - _html_to_lines:
  - get_delivery_challan_html:
  - download_delivery_challan_pdf:
  - _esc:
  - _date:
  - _num:
  - _company_header:
  - _title_bar:
  - _render_delivery_challan_html:
  - sign_cell:

### delivery_challan_item
- Path: `manufyxinvenzaerp/doctype/delivery_challan_item`
- Controller: `manufyxinvenzaerp/doctype/delivery_challan_item/delivery_challan_item.py`
- Client script: none

### gate_pass_purpose
- Path: `manufyxinvenzaerp/doctype/gate_pass_purpose`
- Controller: `manufyxinvenzaerp/doctype/gate_pass_purpose/gate_pass_purpose.py`
- Client script: none

### manufyxinvenza_settings
- Path: `manufyxinvenzaerp/doctype/manufyxinvenza_settings`
- Controller: `manufyxinvenzaerp/doctype/manufyxinvenza_settings/manufyxinvenza_settings.py`
- Client script: none

### cut_sheet_allocation
- Path: `production_management/doctype/cut_sheet_allocation`
- Controller: `production_management/doctype/cut_sheet_allocation/cut_sheet_allocation.py`
- Client script: none

### cut_sheet
- Path: `production_management/doctype/cut_sheet`
- Controller: `production_management/doctype/cut_sheet/cut_sheet.py`
- Client script: `production_management/doctype/cut_sheet/cut_sheet.js`
- Methods:
  - validate:
  - _sync_allocations_from_rows:
  - on_trash:
  - _block_identity_changes:
  - claiming_rows:
  - _block_cut_changes_while_claimed:
  - _block_if_claimed:
  - _block_if_transferred:
  - _fetch_batch_dimensions:
  - _calculate:
  - _validate_allocations_fit:
  - _set_status:
  - suggest_w1_sec_qty:
  - get_available_cut_sheets:
  - get_cut_sheet_for_batch:
  - allocate_cut_sheet:
  - refresh_cut_sheet_allocations:
  - cut_sheet_warehouse_query:
  - mark_cut_sheet_inactive:
  - release_all_cut_sheet_allocations:
  - release_cut_sheet_allocation:
  - apply_w2_to_batch:
  - revert_w2_from_batch:

### inspection_call_log
- Path: `production_management/doctype/inspection_call_log`
- Controller: `production_management/doctype/inspection_call_log/inspection_call_log.py`
- Client script: none

### inspection_entry
- Path: `production_management/doctype/inspection_entry`
- Controller: `production_management/doctype/inspection_entry/inspection_entry.py`
- Client script: none
- Methods:
  - validate:
  - _autofill_total_qty_to_check:
  - _set_inspection_complete_date:
  - before_submit:
  - _validate_scalar_result:
  - _validate_soe_items:
  - _validate_pr_items:

### inspection_entry_item
- Path: `production_management/doctype/inspection_entry_item`
- Controller: `production_management/doctype/inspection_entry_item/inspection_entry_item.py`
- Client script: none

### job_card_raw_material
- Path: `production_management/doctype/job_card_raw_material`
- Controller: `production_management/doctype/job_card_raw_material/job_card_raw_material.py`
- Client script: none

### manufyx_decision_log
- Path: `production_management/doctype/manufyx_decision_log`
- Controller: `production_management/doctype/manufyx_decision_log/manufyx_decision_log.py`
- Client script: none
- Methods:
  - on_trash:

### material_planning_available_raw_material
- Path: `production_management/doctype/material_planning_available_raw_material`
- Controller: `production_management/doctype/material_planning_available_raw_material/material_planning_available_raw_material.py`
- Client script: none

### material_planning_batch_change_log
- Path: `production_management/doctype/material_planning_batch_change_log`
- Controller: `production_management/doctype/material_planning_batch_change_log/material_planning_batch_change_log.py`
- Client script: none

### material_planning_bom_item
- Path: `production_management/doctype/material_planning_bom_item`
- Controller: `production_management/doctype/material_planning_bom_item/material_planning_bom_item.py`
- Client script: none

### material_planning_consolidate_item
- Path: `production_management/doctype/material_planning_consolidate_item`
- Controller: `production_management/doctype/material_planning_consolidate_item/material_planning_consolidate_item.py`
- Client script: none
- Methods:
  - recalculate:

### material_planning_material_mapping
- Path: `production_management/doctype/material_planning_material_mapping`
- Controller: `production_management/doctype/material_planning_material_mapping/material_planning_material_mapping.py`
- Client script: none

### material_planning
- Path: `production_management/doctype/material_planning`
- Controller: `production_management/doctype/material_planning/material_planning.py`
- Client script: `production_management/doctype/material_planning/material_planning.js`
- Methods:
  - excess_row_availability:
  - _release_row_pool_claims:
  - _cut_sheet_thickness:
  - excess_aware_mapped_status:
  - validate:
  - _consolidate_rows_touched:
  - _warn_undersized_purchase_dimensions:
  - _sync_cut_sheet_flag:
  - _sync_cut_sheet_calc:
  - _sync_batch_remarks:
  - _consolidate_unavailable_items:
  - _recalculate_consolidate_items:
  - _auto_update_planning_status:
  - _validate_no_cross_table_batch_duplicate:
  - _set_row_excess:
  - _update_weight_summary:
  - _apply_rwd_fractional_nos:
  - _move_skipped_arm_to_mapping:
  - _validate_batch_calc_qty:
  - _validate_alternate_item_qty:
  - material_mapping_batch_query:
  - search_bom:
  - get_bom_info:
  - get_so_drawings_for_bom_picker:
  - _nos_from_weight:
  - _reconcile_sec_qty_with_sales_order:
  - get_raw_materials:
  - _requirement_key:
  - _ordered_item_codes:
  - check_stock_availability:
  - _alloc_sec_qty:
  - _get_non_batch_stock:
  - _get_non_batch_stock_bulk:
  - move_to_exact_match:
  - update_exact_match_from_consolidate:
  - finalize_mapping:
  - _verify_nos_vs_qty:
  - verify_raw_materials:
  - get_batch_reservation_summary:
  - get_batch_item:
  - get_batch_stock_summary:
  - _get_batch_inspection_block_reason:
  - _get_batch_total_stock:
  - _get_batch_reserved_by_others:
  - _get_batch_reserved_by_others_bulk:
  - _get_non_batch_reserved_by_others:
  - _get_non_batch_reserved_by_others_bulk:
  - get_batch_cross_table_usage:
  - _update_bom_item_weights:
  - _calc_kg_per_nos:
  - _calc_usable_nos_split:
  - _row_get:
  - validate_planned_stock:
  - _add:
  - _sec_nos_for_weight:
  - _refresh_touched_cut_sheets:
  - _require_write:
  - reserve_batches:
  - _get_batch_reserved_by_self:
  - get_available_excess_batches:
  - add_excess_material_mapping:
  - get_available_virtual_excess_items:
  - _release_virtual_excess_source:
  - claim_virtual_excess_mapping:
  - materialize_virtual_excess_claim:
  - reserve_exact_match_batches:
  - unreserve_exact_match_batches:
  - check_mapping_batch_availability:
  - unreserve_batches:
  - _get_batch_dims:
  - _calc_batch_qty:
  - _precheck_batch_reassignment:
  - _mark_excess_item_mapped:
  - _batch_change_remarks:
  - reassign_batch:
  - _apply_batch_to_mapping_row:
  - make_production_plan:
  - make_material_request:
  - make_material_request_from_consolidate:
  - _update_so_difference_kg_for_pair:
  - update_so_difference_kg:
  - unlink_material_request_on_cancel:
  - auto_suggest_consolidate_dimensions:
  - auto_purchase_from_mp:
  - _collect_batch_mapping_issues:
  - complete_batch_mapping:

### material_planning_raw_material
- Path: `production_management/doctype/material_planning_raw_material`
- Controller: `production_management/doctype/material_planning_raw_material/material_planning_raw_material.py`
- Client script: none

### material_planning_unavailable_item
- Path: `production_management/doctype/material_planning_unavailable_item`
- Controller: `production_management/doctype/material_planning_unavailable_item/material_planning_unavailable_item.py`
- Client script: none

### process_planning
- Path: `production_management/doctype/process_planning`
- Controller: `production_management/doctype/process_planning/process_planning.py`
- Client script: none

### production_plan_available_raw_material
- Path: `production_management/doctype/production_plan_available_raw_material`
- Controller: `production_management/doctype/production_plan_available_raw_material/production_plan_available_raw_material.py`
- Client script: none

### storage_location
- Path: `production_management/doctype/storage_location`
- Controller: `production_management/doctype/storage_location/storage_location.py`
- Client script: none

### store_location
- Path: `production_management/doctype/store_location`
- Controller: `production_management/doctype/store_location/store_location.py`
- Client script: none

### job_card_consumption_log
- Path: `subcontracting_management/doctype/job_card_consumption_log`
- Controller: `subcontracting_management/doctype/job_card_consumption_log/job_card_consumption_log.py`
- Client script: none

### material_issue_plan_consolidate_item
- Path: `subcontracting_management/doctype/material_issue_plan_consolidate_item`
- Controller: `subcontracting_management/doctype/material_issue_plan_consolidate_item/material_issue_plan_consolidate_item.py`
- Client script: none

### material_issue_plan
- Path: `subcontracting_management/doctype/material_issue_plan`
- Controller: `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py`
- Client script: `subcontracting_management/doctype/material_issue_plan/material_issue_plan.js`
- Methods:
  - after_insert:
  - validate:
  - on_trash:
  - create_from_subcontracting_order:
  - populate_from_production_plan:
  - _mip_refresh_blocked_message:
  - check_mip_raw_materials_refreshable:
  - refresh_mip_raw_materials_manual:
  - refresh_mip_raw_materials:
  - _sync_excess_availability:
  - _sync_transferred_qty:
  - key:
  - save_transfer_draft:
  - get_transfer_draft:
  - _clear_transfer_draft:
  - _sync_consolidate_items:
  - _batch_stock_in:
  - _cut_sheet_reference:
  - _lookup_drawing_planned_weight:
  - _drawing_planned_weights:
  - _throw_claimed_excess_locked:
  - _assert_claimed_excess_unchanged:
  - unlink_excess_claim:
  - _sync_excess_return_totals:
  - _used_in_fg_weight:
  - _sync_batch_remarks:
  - _maybe_mark_completed:
  - _unaccounted_weight:
  - recheck_mip_completion:
  - refresh_weight_summary:
  - get_target_context:
  - get_mip_batch_plan_html:
  - download_mip_batch_plan_pdf:
  - _render_mip_batch_plan_html:

### material_issue_plan_raw_material
- Path: `subcontracting_management/doctype/material_issue_plan_raw_material`
- Controller: `subcontracting_management/doctype/material_issue_plan_raw_material/material_issue_plan_raw_material.py`
- Client script: none

### sco_drawing_item
- Path: `subcontracting_management/doctype/sco_drawing_item`
- Controller: `subcontracting_management/doctype/sco_drawing_item/sco_drawing_item.py`
- Client script: none

### sco_excess_material_item
- Path: `subcontracting_management/doctype/sco_excess_material_item`
- Controller: `subcontracting_management/doctype/sco_excess_material_item/sco_excess_material_item.py`
- Client script: none

### soe_consumption_log
- Path: `subcontracting_management/doctype/soe_consumption_log`
- Controller: `subcontracting_management/doctype/soe_consumption_log/soe_consumption_log.py`
- Client script: none

### soe_drawing_detail
- Path: `subcontracting_management/doctype/soe_drawing_detail`
- Controller: `subcontracting_management/doctype/soe_drawing_detail/soe_drawing_detail.py`
- Client script: none

### soe_inspection_item
- Path: `subcontracting_management/doctype/soe_inspection_item`
- Controller: `subcontracting_management/doctype/soe_inspection_item/soe_inspection_item.py`
- Client script: none

### supplier_operation_entry
- Path: `subcontracting_management/doctype/supplier_operation_entry`
- Controller: `subcontracting_management/doctype/supplier_operation_entry/supplier_operation_entry.py`
- Client script: none

### supplier_operation_item
- Path: `subcontracting_management/doctype/supplier_operation_item`
- Controller: `subcontracting_management/doctype/supplier_operation_item/supplier_operation_item.py`
- Client script: none

## Module-level controllers

### accounts_management/payment_entry.py
Functions:
  - 4:on_submit_payment_entry:
  - 8:on_cancel_payment_entry:
  - 12:_sync_payment_entry_created_flag:

### accounts_management/payment_request.py
Functions:
  - 5:validate_payment_request:
  - 29:payment_entry_query:
  - 56:get_fund_usage:

### drawing_management/bom_class_override.py
Functions:
  - 1061:get_bom_item_rate:
  - 1096:get_valuation_rate:
  - 1152:get_list_context:
  - 1157:get_bom_items_as_dict:
  - 1256:get_bom_items:
  - 1263:validate_bom_no:
  - 1289:get_children:
  - 1330:add_additional_cost:
  - 1347:add_non_stock_items_cost:
  - 1380:add_operations_cost:
  - 1468:get_bom_diff:
  - 1524:item_query:
  - 1575:make_variant_bom:
  - 1613:get_op_cost_from_sub_assemblies:
  - 1631:get_scrap_items_from_sub_assemblies:

### drawing_management/drawing_utils.py
Functions:
  - 10:mark_as_final_revision:
  - 24:create_revision:
  - 80:get_batches_for_drawing_item:
  - 112:create_bom_from_drawing:
  - 169:validate_bom_from_drawing:
  - 224:create_production_plan_from_bom:
  - 278:parse_drawing_items_csv:
  - 390:get_so_dashboard_data:
  - 399:update_customer_provided_weight:
  - 451:_cascade_customer_weight:

### drawing_management/sales_order.py
Functions:
  - 7:drawing_calculated_weight:
  - 23:recalculate_raw_material_qty:

### drawing_management/so_drawing_import.py
Functions:
  - 11:_calc_qty:
  - 19:_get_file_path:
  - 28:_parse_excel:
  - 127:parse_bom_excel:
  - 365:_bulk_insert:
  - 385:create_drawings_from_import:
  - 566:process_drawings:
  - 695:_at:
  - 715:_check_drawing_masters:
  - 777:_check_row_required:
  - 797:_check_unused_dimensions:
  - 818:_check_drawing_headers:
  - 856:verify_raw_materials:
  - 975:download_bom_template:
  - 1030:clear_drawing_import:
  - 1065:get_cancelled_drawing_links:

### hooks.py

### item_management/item.py
Functions:
  - 15:validate_item:
  - 24:validate_parent_item_group:
  - 29:set_calculation_type:
  - 36:validate_uom_configuration:
  - 77:validate_batch_configuration:
  - 92:validate_batch_prefix:
  - 104:_has_transactions:
  - 112:validate_locked_fields:
  - 125:has_item_transactions:

### material_request_management/material_request.py
Functions:
  - 11:get_mr_item_uom:
  - 27:validate_material_request:
  - 33:before_submit_material_request:
  - 38:_recalculate_qty:
  - 53:_check_missing_fields:

### permissions_bulk.py
Functions:
  - 55:_app_modules:
  - 60:_guard:
  - 67:get_targets:
  - 92:get_role_state:
  - 144:apply_permissions:

### production_management/inspection.py
Functions:
  - 40:_inspection_applicable:
  - 53:validate_soe_inspection:
  - 57:validate_purchase_receipt_inspection:
  - 61:_validate_inspection_call_log:
  - 69:before_submit_soe_inspection_gate:
  - 73:_before_submit_inspection_gate:
  - 96:add_inspection_call:
  - 143:update_inspection_call_date:
  - 163:create_inspection_entry:
  - 247:on_submit_inspection_entry:
  - 332:_apply_soe_inspection_results:
  - 386:_resolve_pr_item_batch_nos:
  - 410:_get_source_doc:
  - 425:_resolve_traceability:

### production_management/manual_release_check.py

### production_management/production_utils.py
Functions:
  - 37:create_operations_workstations_routing:
  - 45:_create_operations:
  - 55:_create_workstations:
  - 70:_create_routing:
  - 103:get_routing_operations_for_bom:
  - 132:_get_previous_operation_consumed:
  - 177:_get_prev_soe_consumed_for_jc:
  - 221:validate_final_operation_consumption:

### production_management/stock_entry.py
Functions:
  - 12:validate_stock_entry:
  - 51:_sync_batch_remarks:
  - 69:_copy_from_material_request_item:
  - 81:_refresh_sco_status_for_final_entry:
  - 100:on_submit_stock_entry:
  - 213:_reduce_batch_sec_qty:
  - 242:_apply_cut_sheet_w2:
  - 291:_apply_cut_sheet_w2_as_new_batch:
  - 365:_cut_sheet_creates_new_batch:
  - 378:_batch_stock_by_warehouse:
  - 398:_repack_remnant_to_new_batch:
  - 515:_repoint_reservations:
  - 532:_cancel_cut_sheet_repack:
  - 571:_batch_total_kg_all_wh:
  - 584:_populate_manufacture_sec_qty:
  - 621:_linked_material_plannings:
  - 667:_consumed_qty_by_batch:
  - 705:_reservation_rows:
  - 720:_release_rows_by_qty:
  - 758:_restore_rows_by_qty:
  - 799:_release_material_planning_reservations:
  - 866:_refresh_linked_mip_weight:
  - 897:on_cancel_stock_entry:
  - 926:_cancelled_row_batch_no:
  - 965:_restore_batch_sec_qty:
  - 985:_restore_material_planning_reservations:
  - 1018:_update_sco_transferred_weight:
  - 1129:_update_sco_cnc_weight:
  - 1177:_update_wo_transferred_weight:
  - 1220:_update_wo_cnc_weight:
  - 1267:_calc_qty:
  - 1290:get_production_plans_for_sales_order:
  - 1316:production_plan_query:
  - 1349:get_job_work_order_for_production_plan:
  - 1367:validate_consumable_entry:

### production_plan_management/production_plan.py
Functions:
  - 22:get_sbb_available_qty:
  - 149:get_sbb_batches_bulk:
  - 266:match_batches_by_dimension:
  - 284:get_items_for_material_requests:
  - 477:get_exploded_items:
  - 484:get_bom_items_direct:
  - 550:get_uom_conversion_factor:
  - 556:get_warehouse_list:
  - 572:get_material_request_items:
  - 661:get_mp_planned_weights:
  - 676:_calc_mp_drawing_weight:
  - 693:_calc_mp_weight:
  - 713:get_pp_drawings_for_picker:
  - 727:_picker_rows_from_mp:
  - 774:_picker_rows_from_so:
  - 829:_mark_already_in_pp:
  - 860:get_operations_from_routing:
  - 873:get_standard_routing_operations:
  - 886:make_material_request:
  - 964:autoname_production_plan:
  - 974:after_save_production_plan:
  - 979:refresh_production_plan_status:
  - 1041:_plan_material_transferred:
  - 1068:validate_process_planning_contiguity:
  - 1105:unlink_production_plan_on_trash:
  - 1118:_recalculate_sec_qty:

### pull_live.py
Functions:
  - 29:get_session:
  - 37:fetch_list:
  - 57:fetch_doc:
  - 63:upsert:
  - 89:sync_singles:
  - 105:sync_doctype:
  - 127:run:

### purchase_order_management/purchase_order.py
Functions:
  - 10:get_po_item_uom:
  - 26:validate_purchase_order:
  - 37:_copy_from_mr_item:
  - 42:before_submit_purchase_order:
  - 47:_recalculate_qty:
  - 62:_check_missing_fields:

### purchase_receipt_management/purchase_receipt.py
Functions:
  - 16:get_pr_item_uom:
  - 32:validate_purchase_receipt:
  - 43:before_submit_purchase_receipt:
  - 48:before_insert_batch:
  - 56:_row_awaiting_batch:
  - 83:_setup_batch_from_purchase_receipt:
  - 144:_setup_batch_from_stock_entry:
  - 217:_get_receipt_suffix:
  - 225:_get_se_suffix:
  - 233:_copy_from_po_item:
  - 239:_recalculate_qty:
  - 254:_check_missing_fields:
  - 260:_resolve_pr_batch_no:
  - 275:get_mp_for_pr:
  - 296:diagnose_mp_allocation:
  - 337:retry_mp_allocation:
  - 375:_pr_dimensions_match:
  - 393:_receivable_qty:
  - 420:_build_mapping_row:
  - 495:_fill_mapping_row_from_receipt:
  - 539:allocate_pr_stock_to_mp:
  - 1078:_archive_consolidate_items:
  - 1143:_allocate_pr_items_individually:
  - 1198:_msgprint_pending_mapping:
  - 1223:on_submit_purchase_receipt:
  - 1339:_get_batch_from_bundle:
  - 1351:get_pr_mp_allocations:

### rfq_management/request_for_quotation.py
Functions:
  - 16:validate_rfq:
  - 21:_copy_from_mr_item:

### sample_data.py
Functions:
  - 4:run:

### setup.py
Functions:
  - 1424:create_default_warehouse_types:
  - 1438:after_install:
  - 1484:after_migrate:
  - 1535:clear_item_default_boms:
  - 1561:setup_storage_location:
  - 1583:create_item_client_script:
  - 1599:create_item_custom_fields:
  - 1684:create_purchase_order_custom_fields:
  - 1790:hide_purchase_order_weight_fields:
  - 1804:create_purchase_order_client_script:
  - 1820:create_purchase_receipt_custom_fields:
  - 1999:create_batch_custom_fields:
  - 2084:create_purchase_receipt_client_script:
  - 2100:create_material_request_custom_fields:
  - 2225:create_material_request_client_script:
  - 2241:create_rfq_custom_fields:
  - 2317:create_rfq_client_script:
  - 2333:create_sq_custom_fields:
  - 2412:create_sq_client_script:
  - 2428:create_bom_custom_fields:
  - 2535:create_so_custom_fields:
  - 2626:create_so_client_script:
  - 2642:create_bom_client_script:
  - 2662:create_production_plan_custom_fields:
  - 2904:create_production_plan_client_script:
  - 3177:create_stock_entry_custom_fields:
  - 3403:hide_duplicate_sco_field:
  - 3430:create_stock_entry_client_script:
  - 3467:create_doctype_label_translations:
  - 3490:remove_sco_purchase_order_mandatory:
  - 3501:add_sco_working_status:
  - 3539:hide_sco_job_worker_warehouse:
  - 3568:make_sco_job_worker_conditional:
  - 3603:create_sco_custom_fields:
  - 4137:create_sco_client_script:
  - 4153:create_sco_ops_client_script:
  - 4169:create_soe_client_script:
  - 4185:create_manufacturing_settings_custom_fields:
  - 4224:create_material_planning_auto_purchase_fields:
  - 4287:create_payment_request_custom_fields:

### sq_management/supplier_quotation.py
Functions:
  - 19:get_sq_item_uom:
  - 35:validate_supplier_quotation:
  - 42:before_submit_supplier_quotation:
  - 47:_copy_from_rfq_item_if_blank:
  - 65:_has_custom_data:
  - 70:_recalculate_qty:
  - 85:_check_missing_fields:

### subcontracting_management/material_issue_plan_transfer.py
Functions:
  - 32:_ensure_mip_editable:
  - 42:_cnc_rows_missing_warehouse:
  - 49:_ensure_cnc_routing:
  - 87:_validate_selected_against_stock:
  - 176:_linked_mp_names:
  - 180:_linked_mp_names_and_duno_scope:
  - 215:_tag_stock_entry:
  - 222:_cut_sheet_caps:
  - 258:get_mip_process_loss_state:
  - 316:_final_manufacture_entry:
  - 331:create_mip_process_loss_entry:
  - 438:_job_stock_at_supplier:
  - 470:_excess_return_source_rows:
  - 522:_cut_sheet_w1_totals:
  - 544:_available_for_transfer:
  - 554:get_mip_pending_items:
  - 762:update_transfer_sec_qty:
  - 808:_batch_free_qty:
  - 817:_apply_transfer_excess_to_raw_materials:
  - 860:_log_round_up_excess:
  - 981:_log_consolidated_excess:
  - 1089:has_cnc_stock:
  - 1109:get_mip_cnc_button_state:
  - 1150:_get_mip_transfer_stock_entry_names:
  - 1167:_get_already_transferred_batches:
  - 1183:get_mip_readiness_check:
  - 1341:create_mip_transfer_entry:
  - 1391:create_mip_partial_transfer:
  - 1469:get_mip_cnc_pending_items:
  - 1526:create_mip_cnc_partial_forward:
  - 1597:_cnc_sent_and_forwarded:
  - 1648:create_mip_cnc_forward_entry:
  - 1709:_override_changes_dimensions:
  - 1721:create_mip_excess_return_entry:

### subcontracting_management/overrides.py
Functions:
  - 11:_is_pp_flow_sco:
  - 18:resolve_supplier_warehouse:
  - 38:_any_operation_started:
  - 59:_final_stock_entry_submitted:
  - 69:refresh_sco_status:

### subcontracting_management/subcontracting.py
Functions:
  - 12:get_sco_dashboard_data:
  - 26:create_sco_from_production_plan:
  - 189:create_sco_and_mip_from_production_plan:
  - 214:delete_sco_and_mip_for_production_plan:
  - 297:create_supplier_operation_entries:
  - 319:get_soe_summary:
  - 385:_final_operation:
  - 401:_fg_already_booked:
  - 424:_rm_already_consumed:
  - 442:_consumption_for_completed:
  - 526:get_final_stock_entry_preview:
  - 585:create_finished_goods_entry:
  - 728:_soe_consumed_kg:
  - 771:validate_supplier_operation_entry:
  - 943:_soe_drawing_target_nos:
  - 954:_validate_completed_status:
  - 1036:before_cancel_supplier_operation_entry:
  - 1064:_sync_soe_inspection_items:
  - 1102:before_submit_supplier_operation_entry:
  - 1136:_propagate_available_to_next:
  - 1158:_propagate_drawing_nos_to_next:
  - 1198:_update_sco_drawing_item_completion:
  - 1222:on_update_supplier_operation_entry:
  - 1234:_push_sco_completion_to_wo:
  - 1274:on_submit_supplier_operation_entry:
  - 1308:before_delete_supplier_operation_entry:
  - 1330:on_cancel_subcontracting_order:
  - 1354:_build_soe_drawing_rows:
  - 1401:_create_soes_for_sco:
  - 1477:_get_mp_total_weight:
  - 1505:_get_mp_actual_transferred_weight:
  - 1551:_refresh_wo_drawing_transferred_weights:
  - 1594:_get_sco_transfer_warehouses:
  - 1606:_get_sco_supplier_warehouse:
  - 1623:_get_wo_transfer_warehouses:
  - 1637:_refresh_sco_drawing_transferred_weights:
  - 1679:_get_mp_drawing_weight:
  - 1696:_get_mp_drawing_weights_by_duno:
  - 1722:_get_mp_mapped_weight_by_duno:
  - 1804:_get_mp_excess_by_duno:
  - 1827:_sec_qty_for_reserved:
  - 1841:_get_mp_reserved_batches:
  - 1951:_get_pp_planned_qty:
  - 1967:_get_supplier_wh_consumption_items:
  - 2048:_build_jc_drawing_rows:
  - 2081:_populate_jcs_for_wo:

### tests/_chk_tmp.py
Functions:
  - 2:run:

### tests/create_full_test_entry.py
Functions:
  - 32:get_ctx:
  - 61:ensure_item:
  - 80:ensure_fg_item:
  - 100:ensure_batch:
  - 119:make_receipt:
  - 142:make_bom:
  - 181:make_material_planning:
  - 200:run:

### tests/create_test_data.py
Functions:
  - 19:get_context:
  - 52:make_item:
  - 73:make_fg_item:
  - 93:make_batch:
  - 112:make_stock_entry:
  - 135:make_bom:
  - 171:run:

### tests/find_cascade_fixture.py
Functions:
  - 4:run:

### tests/find_clean_mp.py
Functions:
  - 3:run:

### tests/_find_mip_excess.py
Functions:
  - 4:run:

### tests/move_fixtures_to_custom_json.py
Functions:
  - 64:_all_target_doctypes:
  - 70:run:

### tests/_probe_ab.py
Functions:
  - 5:run:

### tests/_probe_tmp.py
Functions:
  - 2:run:

### tests/_render_challan.py
Functions:
  - 7:run:

### tests/reset_transactions.py
Functions:
  - 68:run:
  - 116:_things_to_keep:
  - 145:_delete_all:
  - 170:_sql_delete:
  - 179:_orphans:
  - 195:_report_orphans:
  - 200:_delete_orphans:
  - 209:_batch_quantities:
  - 226:_delete_empty_batches:
  - 236:_rebuild_bins:
  - 258:_test_companies:
  - 263:_delete_test_companies:

### tests/revert_wo_jc_cleanup.py
Functions:
  - 106:run:

### tests/_t_close.py
Functions:
  - 5:run:

### tests/_t_cs.py
Functions:
  - 4:run:

### tests/test_alternate_item.py
Functions:
  - 15:_get_unavailable_rows:
  - 23:_clear_mr_links:

### tests/test_classification_logic.py
Functions:
  - 24:_mock_sbb_batches_bulk:
  - 41:_ensure_batch_items:

### tests/test_e2e_material_planning.py
Functions:
  - 28:_get_context:
  - 46:_make_mp:
  - 61:test_flow_1_get_raw_materials:
  - 80:test_flow_2_check_stock_availability:
  - 136:test_flow_3_get_batch_item:
  - 152:test_flow_4_make_production_plan:
  - 168:test_ec1_submit_without_bom:
  - 184:test_ec2_get_raw_materials_no_company:
  - 201:test_ec3_check_stock_no_warehouse:
  - 217:test_ec4_get_batch_item_invalid:
  - 227:test_ec5_empty_bom_items:
  - 242:test_ec6_make_pp_on_draft:
  - 259:run:

### tests/test_material_planning.py
Functions:
  - 25:_make_item:
  - 45:_make_batch:
  - 62:_raw_material_row:
  - 88:test_uc1_exact_match_goes_to_available:
  - 125:test_uc2_partial_stock_goes_to_mapping:
  - 161:test_uc3_no_stock_goes_to_unavailable:
  - 196:test_uc4_get_batch_item:
  - 211:test_uc5_mixed_items_all_three_buckets:
  - 263:run:

### tests/test_po_edge_cases.py
Functions:
  - 15:_find_or_create_mr:
  - 43:_cancel_all_mrs:

### tests/test_purchase_order_creation.py
Functions:
  - 23:get_ctx:
  - 33:_make_test_mp:
  - 64:test_v1_po_created_with_correct_supplier:
  - 78:test_v2_po_items_match_unavailable_rows:
  - 98:test_v3_po_linked_back_on_rows:
  - 113:test_v4_partial_selection_only_links_selected:
  - 130:test_v5_error_when_no_items_selected:
  - 142:test_v6_error_when_no_unavailable_items:
  - 161:test_v7_po_is_draft:
  - 172:test_v8_multiple_pos_for_same_mp:
  - 191:run:

### tests/test_unavailable_actions.py
Functions:
  - 29:_mock_sbb:
  - 38:_ensure_batch_items:

### tests/test_whitelist_coverage.py
Functions:
  - 34:_app_root:
  - 38:_whitelisted_methods:
  - 67:_front_end_calls:

### tests/_t_loss.py
Functions:
  - 5:run:

### tests/_t_sample.py
Functions:
  - 17:_wh:
  - 25:run:

### tests/verify_auto_purchase_gated.py
Functions:
  - 30:check:
  - 36:_set_flag:
  - 41:_call:
  - 50:run:

### tests/verify_batch_receipt_line_match.py
Functions:
  - 39:check:
  - 45:_warehouse:
  - 52:_receipt:
  - 67:_batches_of:
  - 76:run:

### tests/verify_batch_remark_isolation.py
Functions:
  - 27:check:
  - 33:run:

### tests/verify_batch_remarks.py
Functions:
  - 34:run:

### tests/verify_batch_sec_qty_atomic.py
Functions:
  - 31:check:
  - 37:_sec_qty:
  - 41:run:
  - 164:_make_fixtures:
  - 183:_cleanup:

### tests/verify_billed_to_consume.py
Functions:
  - 33:check:
  - 39:_src:
  - 43:run:
  - 96:_summary:

### tests/verify_bom_nature_of_work_rate_schedule.py
Functions:
  - 22:check:
  - 28:_template_headers:
  - 40:_parse_sheet:
  - 56:run:

### tests/verify_bom_routing_new_bom.py
Functions:
  - 17:run:

### tests/verify_bom_routing_trim.py
Functions:
  - 23:run:

### tests/verify_bulk_permissions.py
Functions:
  - 24:check:
  - 30:run:

### tests/verify_cancelled_drawing_link.py
Functions:
  - 35:check:
  - 41:_src:
  - 45:run:

### tests/verify_cnc_consumption_and_kg_chain.py
Functions:
  - 25:check:
  - 31:_fake_soe:
  - 41:run:

### tests/verify_consolidate_alternate_item.py
Functions:
  - 41:run:

### tests/verify_consolidate_finalize.py
Functions:
  - 22:run:

### tests/verify_consolidate_item2.py
Functions:
  - 4:run:

### tests/verify_consolidate_item.py
Functions:
  - 10:run:

### tests/verify_consolidate_sec_qty_editable.py
Functions:
  - 16:run:

### tests/verify_consumable_entry.py
Functions:
  - 42:check:
  - 48:_refusal:
  - 61:_client_script:
  - 67:run:

### tests/verify_consumption_log_hard_cap.py
Functions:
  - 24:check:
  - 30:_doc:
  - 54:_blocked:
  - 71:_validate:
  - 87:run:

### tests/verify_create_operation_and_inspection_gate.py
Functions:
  - 20:run:

### tests/verify_customer_weight_scaled.py
Functions:
  - 31:check:
  - 37:run:

### tests/verify_cut_sheet_delete_guards.py
Functions:
  - 36:check:
  - 42:_batch_dims:
  - 46:_make_item:
  - 60:_make_batch:
  - 67:_warehouse:
  - 71:_make_sheet:
  - 83:run:

### tests/verify_cut_sheet_doctype.py
Functions:
  - 33:check:
  - 38:_throws:
  - 46:plate_kg:
  - 50:run:

### tests/verify_cut_sheet_excess_visibility.py
Functions:
  - 39:check:
  - 45:_throws:
  - 54:_cut_sheet_with_allocations:
  - 68:run:
  - 331:_summary:

### tests/verify_cut_sheet_fields_consistent.py
Functions:
  - 47:check:
  - 53:run:

### tests/verify_cut_sheet_new_batch.py
Functions:
  - 50:check:
  - 56:_company:
  - 70:_warehouse:
  - 80:_ensure_item:
  - 105:_stock:
  - 109:_dims:
  - 116:_make_entry:
  - 126:run:

### tests/verify_cutsheet_status_and_load_fixes.py
Functions:
  - 46:check:
  - 52:run:
  - 172:_plans_with_sco:
  - 180:_existing_plan_expectations:
  - 206:_summary:

### tests/verify_cut_sheet_w2_derived.py
Functions:
  - 24:check:
  - 30:run:

### tests/verify_decision_log.py
Functions:
  - 33:check:
  - 39:_source:
  - 43:run:

### tests/verify_delivery_challan.py
Functions:
  - 35:check:
  - 41:_throws:
  - 55:_company:
  - 59:_supplier:
  - 70:_challan:
  - 91:_status:
  - 95:_pending:
  - 99:run:

### tests/verify_drawing_create_revision.py
Functions:
  - 31:check:
  - 37:run:
  - 112:_check_the_wiring:
  - 138:_summary:

### tests/verify_drawing_import_savepoint.py
Functions:
  - 26:check:
  - 32:run:
  - 105:_build_sales_order:
  - 155:_cleanup:

### tests/verify_drawing_weight_cascade2.py
Functions:
  - 4:run:

### tests/verify_drawing_weight_cascade.py
Functions:
  - 16:run:

### tests/verify_excess_claim_lifecycle.py
Functions:
  - 52:check:
  - 57:_throws:
  - 66:run:

### tests/verify_excess_material_mapping.py
Functions:
  - 21:run:

### tests/verify_excess_material_mapping_row_btn.py
Functions:
  - 48:run:

### tests/verify_excess_partial_and_flags.py
Functions:
  - 34:check:
  - 39:_throws:
  - 47:run:

### tests/verify_excess_return_and_process_loss.py
Functions:
  - 42:check:
  - 48:_throws:
  - 56:_src:
  - 60:run:
  - 157:_summary:

### tests/verify_excess_weight_or_pieces.py
Functions:
  - 35:check:
  - 41:_js:
  - 47:run:

### tests/verify_internal_job_sco.py
Functions:
  - 13:run:

### tests/verify_manual_mr_multi_supplier.py
Functions:
  - 25:run:

### tests/verify_mapped_status_lists_match.py
Functions:
  - 33:check:
  - 39:_js_statuses:
  - 52:run:
  - 123:_summary:

### tests/verify_mapping_batch_warehouse.py
Functions:
  - 38:check:
  - 44:_offered:
  - 49:run:
  - 122:_wiring:
  - 136:_summary:

### tests/verify_material_planning_health.py
Functions:
  - 34:_note:
  - 38:_stock_in:
  - 51:_reserved_elsewhere:
  - 66:_check_reservations:
  - 105:_check_purchase_sizes:
  - 162:run:

### tests/verify_mip_consolidated_allocation.py
Functions:
  - 33:run:

### tests/verify_mip_consolidate_items.py
Functions:
  - 21:check:
  - 27:run:

### tests/verify_mip_excess_plan_tab.py
Functions:
  - 31:check:
  - 37:_js:
  - 46:run:

### tests/verify_mip_post_purchase_refresh.py
Functions:
  - 27:run:

### tests/verify_mip_raw_material_slimmed.py
Functions:
  - 49:check:
  - 55:_source:
  - 59:_row_queries:
  - 73:run:

### tests/verify_mixed_sco_regression.py
Functions:
  - 14:run:

### tests/verify_mp_inspection_gate.py
Functions:
  - 39:_make_inspected_item_and_pr:
  - 70:run:

### tests/verify_mp_multi_mr_guard_message.py
Functions:
  - 20:run:

### tests/verify_mp_view_all_filters.py
Functions:
  - 36:check:
  - 42:_js:
  - 51:run:

### tests/verify_no_create_production_plan_button.py
Functions:
  - 24:check:
  - 30:run:

### tests/verify_no_item_default_bom.py
Functions:
  - 30:check:
  - 36:run:
  - 110:_item_with_a_bom:

### tests/verify_no_zero_qty_exact_match.py
Functions:
  - 26:check:
  - 32:run:

### tests/verify_operation_close_and_sco_status.py
Functions:
  - 39:check:
  - 45:_throws:
  - 54:run:
  - 180:_summary:

### tests/verify_partial_final_stock_entry.py
Functions:
  - 41:check:
  - 47:run:
  - 157:_wiring:
  - 181:_summary:

### tests/verify_partial_transfer_reservation.py
Functions:
  - 37:check:
  - 43:_warehouse:
  - 50:_entry:
  - 60:_held:
  - 65:run:

### tests/verify_per_row_unreserve.py
Functions:
  - 15:run:

### tests/verify_planning_status_follows_reservations.py
Functions:
  - 43:check:
  - 49:_status:
  - 53:_save:
  - 60:run:
  - 142:_summary:

### tests/verify_pp_naming.py
Functions:
  - 6:run:

### tests/verify_pr_allocation_recovery.py
Functions:
  - 38:check:
  - 44:_receipt_with_an_intact_chain:
  - 59:run:
  - 135:_wiring:
  - 150:_summary:

### tests/verify_pr_allocation_single_table.py
Functions:
  - 31:check:
  - 37:_routes_to_mapping:
  - 46:_pr:
  - 50:_req:
  - 54:run:

### tests/verify_pr_inspection.py
Functions:
  - 19:run:

### tests/verify_process_planning_fields.py
Functions:
  - 11:run:

### tests/verify_production_report.py
Functions:
  - 32:check:
  - 38:_labels:
  - 42:run:
  - 295:_old_shape:
  - 303:_excess_rows:
  - 312:_summary:

### tests/verify_pr_partial_receipt_allocation.py
Functions:
  - 39:check:
  - 45:_pr_item:
  - 51:_validate_boundary:
  - 64:run:

### tests/verify_pr_sequential_allocation.py
Functions:
  - 24:run:

### tests/verify_purchase_size_warning.py
Functions:
  - 26:check:
  - 32:_warned:
  - 47:_find_plan:
  - 61:_touch_purchase_line:
  - 69:_touch_other_table:
  - 78:run:
  - 125:_summary:
  - 134:_check_the_rules:

### tests/verify_reassign_batch_exact_match2.py
Functions:
  - 16:run:

### tests/verify_reassign_batch_exact_match.py
Functions:
  - 13:run:

### tests/verify_reassign_batch_inspection_blocked.py
Functions:
  - 22:run:

### tests/verify_receipt_allocates_after_recheck.py
Functions:
  - 53:check:
  - 59:_ctx:
  - 76:run:
  - 162:_make_plan:
  - 178:_make_material_request:
  - 197:_make_receipt:
  - 239:_keys:
  - 246:_summary:

### tests/verify_reservation_permission_guard.py
Functions:
  - 32:check:
  - 38:run:

### tests/verify_reservation_release_on_transfer.py
Functions:
  - 26:check:
  - 32:_reserved:
  - 36:run:

### tests/verify_return_excess_dialog.py
Functions:
  - 29:check:
  - 35:_dialog_source:
  - 47:run:

### tests/verify_rm_issue_row_numbers.py
Functions:
  - 39:check:
  - 45:_plain:
  - 49:run:
  - 108:_summary:

### tests/verify_rwd_two_way.py
Functions:
  - 31:check:
  - 37:_js:
  - 43:run:

### tests/verify_se_duno_propagation.py
Functions:
  - 21:run:

### tests/verify_so_calculated_weight.py
Functions:
  - 23:check:
  - 29:run:

### tests/verify_so_drawing_buttons.py
Functions:
  - 26:check:
  - 32:_script_from_source:
  - 38:run:

### tests/verify_soe_consumption_weight_kg.py
Functions:
  - 13:run:

### tests/verify_soe_summary_available.py
Functions:
  - 33:check:
  - 39:run:
  - 97:_check_the_wiring:
  - 115:_summary:

### tests/verify_so_raw_material_checks.py
Functions:
  - 29:check:
  - 35:_row:
  - 41:run:

### tests/verify_status_mirror.py
Functions:
  - 10:run:

### tests/verify_testing_button_gated.py
Functions:
  - 24:check:
  - 30:_soe_script:
  - 37:run:

### tests/verify_transfer_draft.py
Functions:
  - 23:check:
  - 29:run:

### tests/verify_unreserve_after_transfer.py
Functions:
  - 24:check:
  - 30:_row:
  - 34:run:

### tests/verify_unreserve_btn_meta.py
Functions:
  - 3:run:

### tests/verify_weight_cascade_reaches_soe.py
Functions:
  - 25:check:
  - 31:run:

### tests/verify_wo_jc_standard2.py
Functions:
  - 4:run:

### tests/verify_wo_jc_standard.py
Functions:
  - 4:run:

### utils/decision_log.py
Functions:
  - 31:log_decision:

### utils/dimension_formula.py
Functions:
  - 36:calculate_qty:
  - 58:calculate_sec_qty_from_qty:
  - 69:check_missing_fields:

### utils/reference_copy.py
Functions:
  - 18:fetch_fields:
  - 27:copy_reference_fields_if_blank:

## Whitelisted API methods

- `item_management/item.py:125` — `has_item_transactions`
- `accounts_management/payment_request.py:28` — `@frappe.validate_and_sanitize_search_inputs`
- `accounts_management/payment_request.py:56` — `get_fund_usage`
- `tests/test_whitelist_coverage.py:4` — ``reserve_batches` was swallowed when a helper was inserted directly above it, and`
- `tests/test_whitelist_coverage.py:40` — `    found = set`
- `tests/test_whitelist_coverage.py:111` — `            "so pressing the button that calls them answers 'Method Not Allowed':\n    "`
- `tests/verify_drawing_create_revision.py:126` — `    # The link check is skipped for one reason only: the link it objects to is the`
- `tests/verify_pr_partial_receipt_allocation.py:97` — `    import inspect`
- `purchase_order_management/purchase_order.py:10` — `get_po_item_uom`
- `sq_management/supplier_quotation.py:19` — `get_sq_item_uom`
- `drawing_management/drawing_utils.py:10` — `mark_as_final_revision`
- `drawing_management/drawing_utils.py:24` — `create_revision`
- `drawing_management/drawing_utils.py:80` — `get_batches_for_drawing_item`
- `drawing_management/drawing_utils.py:112` — `create_bom_from_drawing`
- `drawing_management/drawing_utils.py:224` — `create_production_plan_from_bom`
- `drawing_management/drawing_utils.py:278` — `parse_drawing_items_csv`
- `drawing_management/drawing_utils.py:399` — `update_customer_provided_weight`
- `drawing_management/bom_class_override.py:353` — `get_routing`
- `drawing_management/bom_class_override.py:424` — `get_bom_material_detail`
- `drawing_management/bom_class_override.py:509` — `update_cost`
- `drawing_management/bom_class_override.py:1256` — `get_bom_items`
- `drawing_management/bom_class_override.py:1289` — `get_children`
- `drawing_management/bom_class_override.py:1468` — `get_bom_diff`
- `drawing_management/bom_class_override.py:1523` — `@frappe.validate_and_sanitize_search_inputs`
- `drawing_management/bom_class_override.py:1575` — `make_variant_bom`
- `drawing_management/so_drawing_import.py:127` — `parse_bom_excel`
- `drawing_management/so_drawing_import.py:385` — `create_drawings_from_import`
- `drawing_management/so_drawing_import.py:566` — `process_drawings`
- `drawing_management/so_drawing_import.py:856` — `verify_raw_materials`
- `drawing_management/so_drawing_import.py:975` — `download_bom_template`
- `drawing_management/so_drawing_import.py:1030` — `clear_drawing_import`
- `drawing_management/so_drawing_import.py:1065` — `get_cancelled_drawing_links`
- `drawing_management/doctype/drawing/drawing.py:189` — `check_existing_bom`
- `production_plan_management/production_plan.py:284` — `get_items_for_material_requests`
- `production_plan_management/production_plan.py:661` — `get_mp_planned_weights`
- `production_plan_management/production_plan.py:713` — `get_pp_drawings_for_picker`
- `production_plan_management/production_plan.py:860` — `get_operations_from_routing`
- `production_plan_management/production_plan.py:873` — `get_standard_routing_operations`
- `production_plan_management/production_plan.py:886` — `make_material_request`
- `material_request_management/material_request.py:11` — `get_mr_item_uom`
- `subcontracting_management/material_issue_plan_transfer.py:258` — `get_mip_process_loss_state`
- `subcontracting_management/material_issue_plan_transfer.py:331` — `create_mip_process_loss_entry`
- `subcontracting_management/material_issue_plan_transfer.py:554` — `get_mip_pending_items`
- `subcontracting_management/material_issue_plan_transfer.py:762` — `update_transfer_sec_qty`
- `subcontracting_management/material_issue_plan_transfer.py:1089` — `has_cnc_stock`
- `subcontracting_management/material_issue_plan_transfer.py:1109` — `get_mip_cnc_button_state`
- `subcontracting_management/material_issue_plan_transfer.py:1183` — `get_mip_readiness_check`
- `subcontracting_management/material_issue_plan_transfer.py:1341` — `create_mip_transfer_entry`
- `subcontracting_management/material_issue_plan_transfer.py:1391` — `create_mip_partial_transfer`
- `subcontracting_management/material_issue_plan_transfer.py:1469` — `get_mip_cnc_pending_items`
- `subcontracting_management/material_issue_plan_transfer.py:1526` — `create_mip_cnc_partial_forward`
- `subcontracting_management/material_issue_plan_transfer.py:1648` — `create_mip_cnc_forward_entry`
- `subcontracting_management/material_issue_plan_transfer.py:1721` — `create_mip_excess_return_entry`
- `subcontracting_management/subcontracting.py:26` — `create_sco_from_production_plan`
- `subcontracting_management/subcontracting.py:189` — `create_sco_and_mip_from_production_plan`
- `subcontracting_management/subcontracting.py:214` — `delete_sco_and_mip_for_production_plan`
- `subcontracting_management/subcontracting.py:294` — ``
- `subcontracting_management/subcontracting.py:297` — `create_supplier_operation_entries`
- `subcontracting_management/subcontracting.py:319` — `get_soe_summary`
- `subcontracting_management/subcontracting.py:526` — `get_final_stock_entry_preview`
- `subcontracting_management/subcontracting.py:585` — `create_finished_goods_entry`
- `subcontracting_management/subcontracting.py:2032` — ``
- `subcontracting_management/subcontracting.py:2035` — ``
- `subcontracting_management/subcontracting.py:2038` — ``
- `subcontracting_management/subcontracting.py:2041` — ``
- `subcontracting_management/subcontracting.py:2044` — ``
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:50` — `create_from_subcontracting_order`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:69` — ``
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:72` — `populate_from_production_plan`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:175` — `check_mip_raw_materials_refreshable`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:189` — `refresh_mip_raw_materials_manual`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:209` — `refresh_mip_raw_materials`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:457` — `save_transfer_draft`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:506` — `get_transfer_draft`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:830` — `unlink_excess_claim`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:1030` — `refresh_weight_summary`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:1206` — `get_mip_batch_plan_html`
- `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py:1212` — `download_mip_batch_plan_pdf`
- `permissions_bulk.py:67` — `get_targets`
- `permissions_bulk.py:92` — `get_role_state`
- `permissions_bulk.py:144` — `apply_permissions`
- `production_management/inspection.py:96` — `add_inspection_call`
- `production_management/inspection.py:143` — `update_inspection_call_date`
- `production_management/inspection.py:163` — `create_inspection_entry`
- `production_management/stock_entry.py:1290` — `get_production_plans_for_sales_order`
- `production_management/stock_entry.py:1315` — `@frappe.validate_and_sanitize_search_inputs`
- `production_management/stock_entry.py:1349` — `get_job_work_order_for_production_plan`
- `production_management/production_utils.py:103` — `get_routing_operations_for_bom`
- `production_management/production_utils.py:128` — ``
- `production_management/doctype/material_planning/material_planning.py:872` — `@frappe.validate_and_sanitize_search_inputs`
- `production_management/doctype/material_planning/material_planning.py:926` — `@frappe.validate_and_sanitize_search_inputs`
- `production_management/doctype/material_planning/material_planning.py:952` — `get_bom_info`
- `production_management/doctype/material_planning/material_planning.py:1004` — `get_so_drawings_for_bom_picker`
- `production_management/doctype/material_planning/material_planning.py:1111` — `get_raw_materials`
- `production_management/doctype/material_planning/material_planning.py:1252` — `check_stock_availability`
- `production_management/doctype/material_planning/material_planning.py:1646` — `move_to_exact_match`
- `production_management/doctype/material_planning/material_planning.py:1809` — `update_exact_match_from_consolidate`
- `production_management/doctype/material_planning/material_planning.py:2033` — `finalize_mapping`
- `production_management/doctype/material_planning/material_planning.py:2292` — `verify_raw_materials`
- `production_management/doctype/material_planning/material_planning.py:2308` — `get_batch_reservation_summary`
- `production_management/doctype/material_planning/material_planning.py:2344` — `get_batch_item`
- `production_management/doctype/material_planning/material_planning.py:2352` — `get_batch_stock_summary`
- `production_management/doctype/material_planning/material_planning.py:2590` — `get_batch_cross_table_usage`
- `production_management/doctype/material_planning/material_planning.py:2722` — `validate_planned_stock`
- `production_management/doctype/material_planning/material_planning.py:2849` — `reserve_batches`
- `production_management/doctype/material_planning/material_planning.py:3021` — `get_available_excess_batches`
- `production_management/doctype/material_planning/material_planning.py:3087` — `add_excess_material_mapping`
- `production_management/doctype/material_planning/material_planning.py:3182` — `get_available_virtual_excess_items`
- `production_management/doctype/material_planning/material_planning.py:3295` — `claim_virtual_excess_mapping`
- `production_management/doctype/material_planning/material_planning.py:3508` — `reserve_exact_match_batches`
- `production_management/doctype/material_planning/material_planning.py:3655` — `unreserve_exact_match_batches`
- `production_management/doctype/material_planning/material_planning.py:3706` — `check_mapping_batch_availability`
- `production_management/doctype/material_planning/material_planning.py:3767` — `unreserve_batches`
- `production_management/doctype/material_planning/material_planning.py:3932` — `reassign_batch`
- `production_management/doctype/material_planning/material_planning.py:4194` — `make_production_plan`
- `production_management/doctype/material_planning/material_planning.py:4265` — `make_material_request`
- `production_management/doctype/material_planning/material_planning.py:4419` — `make_material_request_from_consolidate`
- `production_management/doctype/material_planning/material_planning.py:4557` — `update_so_difference_kg`
- `production_management/doctype/material_planning/material_planning.py:4587` — `auto_suggest_consolidate_dimensions`
- `production_management/doctype/material_planning/material_planning.py:4675` — `auto_purchase_from_mp`
- `production_management/doctype/material_planning/material_planning.py:4864` — `complete_batch_mapping`
- `production_management/doctype/cut_sheet/cut_sheet.py:390` — `suggest_w1_sec_qty`
- `production_management/doctype/cut_sheet/cut_sheet.py:431` — `get_available_cut_sheets`
- `production_management/doctype/cut_sheet/cut_sheet.py:457` — `get_cut_sheet_for_batch`
- `production_management/doctype/cut_sheet/cut_sheet.py:491` — `allocate_cut_sheet`
- `production_management/doctype/cut_sheet/cut_sheet.py:634` — `@frappe.validate_and_sanitize_search_inputs`
- `production_management/doctype/cut_sheet/cut_sheet.py:675` — `mark_cut_sheet_inactive`
- `production_management/doctype/cut_sheet/cut_sheet.py:737` — `release_all_cut_sheet_allocations`
- `manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py:367` — `refresh_overdue_gate_passes`
- `manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py:402` — `make_return_entry`
- `manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py:496` — `@frappe.validate_and_sanitize_search_inputs`
- `manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py:603` — `get_delivery_challan_html`
- `manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py:610` — `download_delivery_challan_pdf`
- `purchase_receipt_management/purchase_receipt.py:16` — `get_pr_item_uom`
- `purchase_receipt_management/purchase_receipt.py:275` — `get_mp_for_pr`
- `purchase_receipt_management/purchase_receipt.py:296` — `diagnose_mp_allocation`
- `purchase_receipt_management/purchase_receipt.py:337` — `retry_mp_allocation`
- `purchase_receipt_management/purchase_receipt.py:539` — `allocate_pr_stock_to_mp`
- `purchase_receipt_management/purchase_receipt.py:1351` — `get_pr_mp_allocations`

## hooks.py — doc_events

doc_events = {
	"Item": {
		"validate": "manufyxinvenzaerp.item_management.item.validate_item",
	},
	"Sales Order": {
		"validate": "manufyxinvenzaerp.drawing_management.sales_order.recalculate_raw_material_qty",
	},
	"Purchase Order": {
		"validate": "manufyxinvenzaerp.purchase_order_management.purchase_order.validate_purchase_order",
		"before_submit": "manufyxinvenzaerp.purchase_order_management.purchase_order.before_submit_purchase_order",
	},
	"Purchase Receipt": {
		"validate": [
			"manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.validate_purchase_receipt",
			"manufyxinvenzaerp.production_management.inspection.validate_purchase_receipt_inspection",
		],
		"before_submit": "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.before_submit_purchase_receipt",
		"on_submit": "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.on_submit_purchase_receipt",
	},
	"Batch": {
		"before_insert": "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.before_insert_batch",
	},
	"BOM": {
		"validate": "manufyxinvenzaerp.drawing_management.drawing_utils.validate_bom_from_drawing",
	},
	"Material Request": {
		"validate": "manufyxinvenzaerp.material_request_management.material_request.validate_material_request",
		"before_submit": "manufyxinvenzaerp.material_request_management.material_request.before_submit_material_request",
		"on_cancel": "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.unlink_material_request_on_cancel",
		"on_trash": "manufyxinvenzaerp.production_management.doctype.material_planning.material_planning.unlink_material_request_on_cancel",
	},
	"Request for Quotation": {
		"validate": "manufyxinvenzaerp.rfq_management.request_for_quotation.validate_rfq",
	},
	"Supplier Quotation": {
		"validate": "manufyxinvenzaerp.sq_management.supplier_quotation.validate_supplier_quotation",
		"before_submit": "manufyxinvenzaerp.sq_management.supplier_quotation.before_submit_supplier_quotation",
	},
	# Work Order and Job Card carry no hooks from this app: they were reverted to
	# standard ERPNext under the client's Phase 0.4 change request, and
	# Subcontracting Order / Operation Entry do that work instead.
	"Stock Entry": {
		"validate": "manufyxinvenzaerp.production_management.stock_entry.validate_stock_entry",
		"on_submit": "manufyxinvenzaerp.production_management.stock_entry.on_submit_stock_entry",
		"on_cancel": "manufyxinvenzaerp.production_management.stock_entry.on_cancel_stock_entry",
	},
	"Supplier Operation Entry": {
		"validate": [
			"manufyxinvenzaerp.subcontracting_management.subcontracting.validate_supplier_operation_entry",
			"manufyxinvenzaerp.production_management.inspection.validate_soe_inspection",
		],
		"before_submit": [
			"manufyxinvenzaerp.subcontracting_management.subcontracting.before_submit_supplier_operation_entry",
			"manufyxinvenzaerp.production_management.inspection.before_submit_soe_inspection_gate",
		],
		"on_update": "manufyxinvenzaerp.subcontracting_management.subcontracting.on_update_supplier_operation_entry",
		"on_submit": "manufyxinvenzaerp.subcontracting_management.subcontracting.on_submit_supplier_operation_entry",
		"before_cancel": "manufyxinvenzaerp.subcontracting_management.subcontracting.before_cancel_supplier_operation_entry",
		"before_delete": "manufyxinvenzaerp.subcontracting_management.subcontracting.before_delete_supplier_operation_entry",
	},
	"Subcontracting Order": {
		"on_cancel": "manufyxinvenzaerp.subcontracting_management.subcontracting.on_cancel_subcontracting_order",
	},
	"Production Plan": {
		"autoname": "manufyxinvenzaerp.production_plan_management.production_plan.autoname_production_plan",
		"validate": [
			"manufyxinvenzaerp.production_plan_management.production_plan.after_save_production_plan",
			"manufyxinvenzaerp.production_plan_management.production_plan.validate_process_planning_contiguity",
		],
		"on_trash": "manufyxinvenzaerp.production_plan_management.production_plan.unlink_production_plan_on_trash",
		"on_cancel": "manufyxinvenzaerp.production_plan_management.production_plan.unlink_production_plan_on_trash",
	},
	"Inspection Entry": {
		"on_submit": "manufyxinvenzaerp.production_management.inspection.on_submit_inspection_entry",
	},
	"Payment Request": {
		"validate": "manufyxinvenzaerp.accounts_management.payment_request.validate_payment_request",
	},
	"Payment Entry": {
		"on_submit": "manufyxinvenzaerp.accounts_management.payment_entry.on_submit_payment_entry",
		"on_cancel": "manufyxinvenzaerp.accounts_management.payment_entry.on_cancel_payment_entry",
	},
}

## hooks.py — overrides

override_doctype_class = {
    "BOM": "manufyxinvenzaerp.drawing_management.bom_class_override.BOM",
    "Subcontracting Order": "manufyxinvenzaerp.subcontracting_management.overrides.CustomSubcontractingOrder",
    "Stock Entry": "manufyxinvenzaerp.subcontracting_management.overrides.CustomStockEntry",
}


override_doctype_dashboards = {
	"Sales Order": "manufyxinvenzaerp.drawing_management.drawing_utils.get_so_dashboard_data",
	"Subcontracting Order": "manufyxinvenzaerp.subcontracting_management.subcontracting.get_sco_dashboard_data",
}


## hooks.py — fixtures & lifecycle

after_install = "manufyxinvenzaerp.setup.after_install"
after_migrate = "manufyxinvenzaerp.setup.after_migrate"

