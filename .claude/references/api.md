# api — manufyxinvenzaerp

_Generated: 2026-10-20 03:36:32_

All `@frappe.whitelist()` methods. Call from JS:
`frappe.call({ method: 'manufyxinvenzaerp.<dotted.path>', args: {...} })`

## accounts_management/doctype/payment_approval/payment_approval.py

| Method | Purpose |
|--------|---------|
| `approve(name, remarks, approved_amount)` | Director approves (remarks mandatory) |
| `reject(name, remarks)` | Director rejects (remarks mandatory) |
| `reset_approvals(name)` | Clear all approvals on a rejected/pending draft |
| `make_payment_entry(name)` | Unsaved Pay entry for the approved amount |
| `get_fund_usage(payment_entry, payment_approval)` | Source of Funds total / used / balance |
| `payment_entry_query`, `director_query` | Link searches |
## data_works/engine.py

| Method | Line |
|--------|------|
| `run` | 109 |
| `get_log` | 128 |
| `get_state` | 85 |
| `preview` | 96 |
## drawing_management/doctype/drawing/drawing.py

| Method | Line |
|--------|------|
| `check_existing_bom` | 239 |
## drawing_management/drawing_utils.py

| Method | Line |
|--------|------|
| `create_bom_from_drawing` | 112 |
| `create_revision` | 24 |
| `create_production_plan_from_bom` | 250 |
| `parse_drawing_items_csv` | 320 |
| `update_customer_provided_weight` | 441 |
| `get_batches_for_drawing_item` | 80 |
| `mark_as_final_revision` | 10 |
## drawing_management/rate_schedule_sync.py

| Method | Line |
|--------|------|
| `get_rate_schedule_conflict` | 200 |
## drawing_management/so_drawing_import.py

| Method | Line |
|--------|------|
| `verify_raw_materials` | 1148 |
| `download_bom_template` | 1277 |
| `clear_drawing_import` | 1351 |
| `get_cancelled_drawing_links` | 1386 |
| `parse_bom_excel` | 146 |
| `create_drawings_from_import` | 414 |
| `process_drawings` | 616 |
## item_management/item.py

| Method | Line |
|--------|------|
| `has_item_transactions` | 251 |
## manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py

| Method | Line |
|--------|------|
| `refresh_overdue_gate_passes` | 367 |
| `make_return_entry` | 402 |
| `@frappe.validate_and_sanitize_search_inputs` | 496 |
| `get_delivery_challan_html` | 603 |
| `download_delivery_challan_pdf` | 610 |
## material_request_management/material_request.py

| Method | Line |
|--------|------|
| `get_mr_item_uom` | 11 |
## permissions_bulk.py

| Method | Line |
|--------|------|
| `apply_permissions` | 144 |
| `get_targets` | 67 |
| `get_role_state` | 92 |
## production_management/doctype/cut_sheet/cut_sheet.py

| Method | Line |
|--------|------|
| `suggest_w1_sec_qty` | 390 |
| `get_available_cut_sheets` | 431 |
| `get_cut_sheet_for_batch` | 457 |
| `allocate_cut_sheet` | 491 |
| `@frappe.validate_and_sanitize_search_inputs` | 634 |
| `mark_cut_sheet_inactive` | 675 |
| `release_all_cut_sheet_allocations` | 737 |
## production_management/doctype/material_planning/material_planning.py

| Method | Line |
|--------|------|
| `@frappe.validate_and_sanitize_search_inputs` | 1036 |
| `@frappe.validate_and_sanitize_search_inputs` | 1090 |
| `get_bom_info` | 1116 |
| `get_so_drawings_for_bom_picker` | 1182 |
| `get_raw_materials` | 1306 |
| `check_stock_availability` | 1508 |
| `allocate_receipt_to_plan` | 1980 |
| `move_to_exact_match` | 2270 |
| `update_exact_match_from_consolidate` | 2436 |
| `finalize_mapping` | 2663 |
| `verify_raw_materials` | 2922 |
| `get_batch_reservation_summary` | 2938 |
| `get_batch_item` | 2974 |
| `get_batch_stock_summary` | 2982 |
| `get_batch_cross_table_usage` | 3220 |
| `validate_planned_stock` | 3363 |
| `reserve_batches` | 3559 |
| `get_available_excess_batches` | 3742 |
| `add_excess_material_mapping` | 3808 |
| `get_available_virtual_excess_items` | 3903 |
| `claim_virtual_excess_mapping` | 4016 |
| `reserve_exact_match_batches` | 4229 |
| `unreserve_exact_match_batches` | 4389 |
| `check_mapping_batch_availability` | 4440 |
| `unreserve_batches` | 4507 |
| `reassign_batch` | 4731 |
| `make_production_plan` | 5060 |
| `make_material_request` | 5136 |
| `make_material_request_from_consolidate` | 5290 |
| `update_so_difference_kg` | 5428 |
| `auto_suggest_consolidate_dimensions` | 5458 |
| `auto_purchase_from_mp` | 5546 |
| `complete_batch_mapping` | 5832 |
## production_management/fg_stock.py

| Method | Line |
|--------|------|
| `get_fg_settings` | 581 |
| `get_fg_kg_for_nos` | 590 |
| `get_fg_planned_kg` | 599 |
## production_management/inspection.py

| Method | Line |
|--------|------|
| `update_inspection_call_date` | 143 |
| `create_inspection_entry` | 163 |
| `create_soe_inspection` | 251 |
| `add_inspection_call` | 96 |
## production_management/production_utils.py

| Method | Line |
|--------|------|
| `get_routing_operations_for_bom` | 103 |
| `` | 128 |
## production_management/stock_entry.py

| Method | Line |
|--------|------|
| `get_production_plans_for_sales_order` | 1539 |
| `@frappe.validate_and_sanitize_search_inputs` | 1564 |
| `get_job_work_order_for_production_plan` | 1598 |
## production_plan_management/production_plan.py

| Method | Line |
|--------|------|
| `get_items_for_material_requests` | 295 |
| `get_mp_planned_weights` | 690 |
| `get_pp_drawings_for_picker` | 742 |
| `get_operations_from_routing` | 947 |
| `get_standard_routing_operations` | 960 |
| `make_material_request` | 973 |
## purchase_order_management/purchase_order.py

| Method | Line |
|--------|------|
| `get_po_item_uom` | 10 |
## purchase_receipt_management/purchase_receipt.py

| Method | Line |
|--------|------|
| `get_pr_mp_allocations` | 1357 |
| `get_pr_item_uom` | 16 |
| `get_mp_for_pr` | 275 |
| `diagnose_mp_allocation` | 296 |
| `retry_mp_allocation` | 337 |
| `allocate_pr_stock_to_mp` | 539 |
## selling_management/delivery_note.py

| Method | Line |
|--------|------|
| `get_fg_rows_kg` | 421 |
| `get_fg_batches` | 435 |
## selling_management/delivery_plan.py

| Method | Line |
|--------|------|
| `refresh_delivery_plan` | 208 |
| `create_delivery_from_plan` | 272 |
## selling_management/mapping.py

| Method | Line |
|--------|------|
| `make_sales_invoice_from_so` | 182 |
| `make_sales_invoice_from_dn` | 201 |
| `make_delivery_note` | 22 |
## selling_management/packing_slip.py

| Method | Line |
|--------|------|
| `make_packing_slip` | 71 |
## selling_management/sales_invoice.py

| Method | Line |
|--------|------|
| `get_fg_row_kg` | 351 |
## sq_management/supplier_quotation.py

| Method | Line |
|--------|------|
| `get_sq_item_uom` | 19 |
## stock_management/storage_location.py

| Method | Line |
|--------|------|
| `@frappe.validate_and_sanitize_search_inputs` | 547 |
| `@frappe.validate_and_sanitize_search_inputs` | 565 |
| `get_default_location` | 589 |
| `get_location_settings` | 597 |
## subcontracting_management/doctype/material_issue_plan/material_issue_plan.py

| Method | Line |
|--------|------|
| `unlink_excess_claim` | 1177 |
| `refresh_weight_summary` | 1421 |
| `get_mip_batch_plan_html` | 1606 |
| `download_mip_batch_plan_pdf` | 1612 |
| `get_mip_consolidate_plan_html` | 1768 |
| `download_mip_consolidate_plan_pdf` | 1774 |
| `check_mip_batch_change_allowed` | 253 |
| `check_mip_raw_materials_refreshable` | 261 |
| `refresh_mip_raw_materials_manual` | 275 |
| `refresh_mip_raw_materials` | 295 |
| `create_from_subcontracting_order` | 57 |
| `save_transfer_draft` | 618 |
| `get_transfer_draft` | 680 |
| `` | 76 |
| `populate_from_production_plan` | 79 |
## subcontracting_management/material_issue_plan_batch_update.py

| Method | Line |
|--------|------|
| `apply_consolidate_batch_update` | 1205 |
| `get_batch_capacity` | 212 |
| `preview_consolidate_batch_update` | 766 |
| `get_consolidate_line_context` | 868 |
| `@frappe.validate_and_sanitize_search_inputs` | 899 |
| `get_candidate_batches` | 948 |
## subcontracting_management/material_issue_plan_transfer.py

| Method | Line |
|--------|------|
| `has_cnc_stock` | 1726 |
| `get_mip_cnc_button_state` | 1746 |
| `get_mip_readiness_check` | 1820 |
| `create_mip_transfer_entry` | 1978 |
| `create_mip_partial_transfer` | 2031 |
| `get_mip_cnc_pending_items` | 2120 |
| `create_mip_cnc_partial_forward` | 2184 |
| `create_mip_cnc_forward_entry` | 2319 |
| `create_mip_excess_return_entry` | 2503 |
| `submit_mip_transfer_entry` | 259 |
| `get_mip_process_loss_state` | 311 |
| `create_mip_process_loss_entry` | 397 |
| `get_mip_pending_items` | 625 |
| `update_transfer_sec_qty` | 920 |
## subcontracting_management/subcontracting.py

| Method | Line |
|--------|------|
| `check_soe_completion_before_confirm` | 1260 |
| `` | 2655 |
| `` | 2658 |
| `` | 2661 |
| `` | 2664 |
| `` | 2667 |
| `create_sco_from_production_plan` | 27 |
| `create_sco_and_mip_from_production_plan` | 281 |
| `delete_sco_and_mip_for_production_plan` | 306 |
| `` | 386 |
| `create_supplier_operation_entries` | 389 |
| `get_soe_summary` | 411 |
| `get_final_stock_entry_preview` | 853 |
| `create_finished_goods_entry` | 951 |
## tests/test_whitelist_coverage.py

| Method | Line |
|--------|------|
| `            "so pressing the button that calls them answers 'Method Not Allowed':\n    "` | 111 |
| `    found = set` | 40 |
| ``reserve_batches` was swallowed when a helper was inserted directly above it, and` | 4 |
## tests/verify_drawing_create_revision.py

| Method | Line |
|--------|------|
| `    # The link check is skipped for one reason only: the link it objects to is the` | 126 |
## tests/verify_mip_download_and_grid.py

| Method | Line |
|--------|------|
| `    # registered. Checking membership there is the only thing that proves the` | 107 |
## tests/verify_pr_partial_receipt_allocation.py

| Method | Line |
|--------|------|
| `    import inspect` | 97 |

## Total

_166 whitelisted methods_
