# api — manufyxinvenzaerp

_Generated: 2026-09-21 21:29:50_

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
| `@frappe.validate_and_sanitize_search_inputs` | 1003 |
| `get_bom_info` | 1029 |
| `get_so_drawings_for_bom_picker` | 1095 |
| `get_raw_materials` | 1219 |
| `check_stock_availability` | 1421 |
| `allocate_receipt_to_plan` | 1890 |
| `move_to_exact_match` | 2173 |
| `update_exact_match_from_consolidate` | 2339 |
| `finalize_mapping` | 2566 |
| `verify_raw_materials` | 2825 |
| `get_batch_reservation_summary` | 2841 |
| `get_batch_item` | 2877 |
| `get_batch_stock_summary` | 2885 |
| `get_batch_cross_table_usage` | 3123 |
| `validate_planned_stock` | 3266 |
| `reserve_batches` | 3432 |
| `get_available_excess_batches` | 3604 |
| `add_excess_material_mapping` | 3670 |
| `get_available_virtual_excess_items` | 3765 |
| `claim_virtual_excess_mapping` | 3878 |
| `reserve_exact_match_batches` | 4091 |
| `unreserve_exact_match_batches` | 4238 |
| `check_mapping_batch_availability` | 4289 |
| `unreserve_batches` | 4350 |
| `reassign_batch` | 4574 |
| `make_production_plan` | 4893 |
| `make_material_request` | 4969 |
| `make_material_request_from_consolidate` | 5123 |
| `update_so_difference_kg` | 5261 |
| `auto_suggest_consolidate_dimensions` | 5291 |
| `auto_purchase_from_mp` | 5379 |
| `complete_batch_mapping` | 5585 |
| `@frappe.validate_and_sanitize_search_inputs` | 949 |
## production_management/fg_stock.py

| Method | Line |
|--------|------|
| `get_fg_settings` | 537 |
| `get_fg_kg_for_nos` | 546 |
| `get_fg_planned_kg` | 555 |
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
| `get_production_plans_for_sales_order` | 1376 |
| `@frappe.validate_and_sanitize_search_inputs` | 1401 |
| `get_job_work_order_for_production_plan` | 1435 |
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
| `unlink_excess_claim` | 1085 |
| `refresh_weight_summary` | 1285 |
| `get_mip_batch_plan_html` | 1461 |
| `download_mip_batch_plan_pdf` | 1467 |
| `get_mip_consolidate_plan_html` | 1606 |
| `download_mip_consolidate_plan_pdf` | 1612 |
| `check_mip_batch_change_allowed` | 237 |
| `check_mip_raw_materials_refreshable` | 245 |
| `refresh_mip_raw_materials_manual` | 259 |
| `refresh_mip_raw_materials` | 279 |
| `create_from_subcontracting_order` | 50 |
| `save_transfer_draft` | 555 |
| `get_transfer_draft` | 614 |
| `` | 69 |
| `populate_from_production_plan` | 72 |
## subcontracting_management/material_issue_plan_batch_update.py

| Method | Line |
|--------|------|
| `apply_consolidate_batch_update` | 1109 |
| `get_batch_capacity` | 196 |
| `preview_consolidate_batch_update` | 745 |
| `get_consolidate_line_context` | 847 |
| `get_candidate_batches` | 878 |
## subcontracting_management/material_issue_plan_transfer.py

| Method | Line |
|--------|------|
| `has_cnc_stock` | 1473 |
| `get_mip_cnc_button_state` | 1493 |
| `get_mip_readiness_check` | 1567 |
| `create_mip_transfer_entry` | 1725 |
| `create_mip_partial_transfer` | 1777 |
| `get_mip_cnc_pending_items` | 1855 |
| `create_mip_cnc_partial_forward` | 1912 |
| `create_mip_cnc_forward_entry` | 2045 |
| `create_mip_excess_return_entry` | 2153 |
| `submit_mip_transfer_entry` | 249 |
| `get_mip_process_loss_state` | 301 |
| `create_mip_process_loss_entry` | 374 |
| `get_mip_pending_items` | 600 |
| `update_transfer_sec_qty` | 823 |
## subcontracting_management/subcontracting.py

| Method | Line |
|--------|------|
| `` | 2263 |
| `` | 2266 |
| `` | 2269 |
| `` | 2272 |
| `` | 2275 |
| `create_sco_from_production_plan` | 26 |
| `create_sco_and_mip_from_production_plan` | 264 |
| `delete_sco_and_mip_for_production_plan` | 289 |
| `` | 369 |
| `create_supplier_operation_entries` | 372 |
| `get_soe_summary` | 394 |
| `get_final_stock_entry_preview` | 648 |
| `create_finished_goods_entry` | 714 |
| `check_soe_completion_before_confirm` | 963 |
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

_161 whitelisted methods_
