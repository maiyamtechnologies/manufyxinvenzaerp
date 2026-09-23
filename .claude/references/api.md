# api — manufyxinvenzaerp

_Generated: 2026-09-23 13:39:24_

All `@frappe.whitelist()` methods. Call from JS:
`frappe.call({ method: 'manufyxinvenzaerp.<dotted.path>', args: {...} })`

## accounts_management/payment_request.py

| Method | Line |
|--------|------|
| `@frappe.validate_and_sanitize_search_inputs` | 28 |
| `get_fund_usage` | 56 |
## drawing_management/bom_class_override.py

| Method | Line |
|--------|------|
| `get_bom_items` | 1256 |
| `get_children` | 1289 |
| `get_bom_diff` | 1468 |
| `@frappe.validate_and_sanitize_search_inputs` | 1523 |
| `make_variant_bom` | 1575 |
| `get_routing` | 353 |
| `get_bom_material_detail` | 424 |
| `update_cost` | 509 |
## drawing_management/doctype/drawing/drawing.py

| Method | Line |
|--------|------|
| `check_existing_bom` | 239 |
## drawing_management/drawing_utils.py

| Method | Line |
|--------|------|
| `create_bom_from_drawing` | 112 |
| `create_revision` | 24 |
| `create_production_plan_from_bom` | 249 |
| `parse_drawing_items_csv` | 319 |
| `update_customer_provided_weight` | 440 |
| `get_batches_for_drawing_item` | 80 |
| `mark_as_final_revision` | 10 |
## drawing_management/rate_schedule_sync.py

| Method | Line |
|--------|------|
| `get_rate_schedule_conflict` | 153 |
## drawing_management/so_drawing_import.py

| Method | Line |
|--------|------|
| `verify_raw_materials` | 1019 |
| `download_bom_template` | 1146 |
| `clear_drawing_import` | 1210 |
| `get_cancelled_drawing_links` | 1245 |
| `parse_bom_excel` | 137 |
| `create_drawings_from_import` | 401 |
| `process_drawings` | 601 |
## item_management/item.py

| Method | Line |
|--------|------|
| `has_item_transactions` | 204 |
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
| `@frappe.validate_and_sanitize_search_inputs` | 1038 |
| `get_bom_info` | 1064 |
| `get_so_drawings_for_bom_picker` | 1130 |
| `get_raw_materials` | 1254 |
| `check_stock_availability` | 1456 |
| `allocate_receipt_to_plan` | 1928 |
| `move_to_exact_match` | 2211 |
| `update_exact_match_from_consolidate` | 2377 |
| `finalize_mapping` | 2604 |
| `verify_raw_materials` | 2863 |
| `get_batch_reservation_summary` | 2879 |
| `get_batch_item` | 2915 |
| `get_batch_stock_summary` | 2923 |
| `get_batch_cross_table_usage` | 3161 |
| `validate_planned_stock` | 3304 |
| `reserve_batches` | 3500 |
| `get_available_excess_batches` | 3675 |
| `add_excess_material_mapping` | 3741 |
| `get_available_virtual_excess_items` | 3836 |
| `claim_virtual_excess_mapping` | 3949 |
| `reserve_exact_match_batches` | 4162 |
| `unreserve_exact_match_batches` | 4313 |
| `check_mapping_batch_availability` | 4364 |
| `unreserve_batches` | 4425 |
| `reassign_batch` | 4649 |
| `make_production_plan` | 4978 |
| `make_material_request` | 5054 |
| `make_material_request_from_consolidate` | 5208 |
| `update_so_difference_kg` | 5346 |
| `auto_suggest_consolidate_dimensions` | 5376 |
| `auto_purchase_from_mp` | 5464 |
| `complete_batch_mapping` | 5722 |
| `@frappe.validate_and_sanitize_search_inputs` | 984 |
## production_management/fg_stock.py

| Method | Line |
|--------|------|
| `get_fg_settings` | 575 |
| `get_fg_kg_for_nos` | 584 |
| `get_fg_planned_kg` | 593 |
## production_management/inspection.py

| Method | Line |
|--------|------|
| `update_inspection_call_date` | 143 |
| `create_inspection_entry` | 163 |
| `add_inspection_call` | 96 |
## production_management/production_utils.py

| Method | Line |
|--------|------|
| `get_routing_operations_for_bom` | 103 |
| `` | 128 |
## production_management/stock_entry.py

| Method | Line |
|--------|------|
| `get_production_plans_for_sales_order` | 1481 |
| `@frappe.validate_and_sanitize_search_inputs` | 1506 |
| `get_job_work_order_for_production_plan` | 1540 |
## production_plan_management/production_plan.py

| Method | Line |
|--------|------|
| `get_items_for_material_requests` | 284 |
| `get_mp_planned_weights` | 679 |
| `get_pp_drawings_for_picker` | 731 |
| `get_operations_from_routing` | 936 |
| `get_standard_routing_operations` | 949 |
| `make_material_request` | 962 |
## purchase_order_management/purchase_order.py

| Method | Line |
|--------|------|
| `get_po_item_uom` | 10 |
## purchase_receipt_management/purchase_receipt.py

| Method | Line |
|--------|------|
| `get_pr_mp_allocations` | 1351 |
| `get_pr_item_uom` | 16 |
| `get_mp_for_pr` | 275 |
| `diagnose_mp_allocation` | 296 |
| `retry_mp_allocation` | 337 |
| `allocate_pr_stock_to_mp` | 539 |
## selling_management/delivery_note.py

| Method | Line |
|--------|------|
| `get_fg_rows_kg` | 415 |
| `get_fg_batches` | 429 |
## selling_management/mapping.py

| Method | Line |
|--------|------|
| `make_sales_invoice_from_so` | 182 |
| `make_sales_invoice_from_dn` | 201 |
| `make_delivery_note` | 22 |
## selling_management/sales_invoice.py

| Method | Line |
|--------|------|
| `get_fg_row_kg` | 351 |
## sq_management/supplier_quotation.py

| Method | Line |
|--------|------|
| `get_sq_item_uom` | 19 |
## subcontracting_management/doctype/material_issue_plan/material_issue_plan.py

| Method | Line |
|--------|------|
| `unlink_excess_claim` | 1129 |
| `refresh_weight_summary` | 1372 |
| `get_mip_batch_plan_html` | 1548 |
| `download_mip_batch_plan_pdf` | 1554 |
| `get_mip_consolidate_plan_html` | 1693 |
| `download_mip_consolidate_plan_pdf` | 1699 |
| `check_mip_batch_change_allowed` | 237 |
| `check_mip_raw_materials_refreshable` | 245 |
| `refresh_mip_raw_materials_manual` | 259 |
| `refresh_mip_raw_materials` | 279 |
| `create_from_subcontracting_order` | 50 |
| `save_transfer_draft` | 584 |
| `get_transfer_draft` | 643 |
| `` | 69 |
| `populate_from_production_plan` | 72 |
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
| `has_cnc_stock` | 1495 |
| `get_mip_cnc_button_state` | 1515 |
| `get_mip_readiness_check` | 1589 |
| `create_mip_transfer_entry` | 1747 |
| `create_mip_partial_transfer` | 1799 |
| `get_mip_cnc_pending_items` | 1882 |
| `create_mip_cnc_partial_forward` | 1939 |
| `create_mip_cnc_forward_entry` | 2072 |
| `create_mip_excess_return_entry` | 2180 |
| `submit_mip_transfer_entry` | 249 |
| `get_mip_process_loss_state` | 301 |
| `create_mip_process_loss_entry` | 374 |
| `get_mip_pending_items` | 600 |
| `update_transfer_sec_qty` | 845 |
## subcontracting_management/subcontracting.py

| Method | Line |
|--------|------|
| `check_soe_completion_before_confirm` | 1242 |
| `` | 2552 |
| `` | 2555 |
| `` | 2558 |
| `` | 2561 |
| `` | 2564 |
| `create_sco_from_production_plan` | 27 |
| `create_sco_and_mip_from_production_plan` | 271 |
| `delete_sco_and_mip_for_production_plan` | 296 |
| `` | 376 |
| `create_supplier_operation_entries` | 379 |
| `get_soe_summary` | 401 |
| `get_final_stock_entry_preview` | 839 |
| `create_finished_goods_entry` | 937 |
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
| `    # registered. Checking membership there is the only thing that proves the` | 105 |
## tests/verify_pr_partial_receipt_allocation.py

| Method | Line |
|--------|------|
| `    import inspect` | 97 |

## Total

_162 whitelisted methods_
