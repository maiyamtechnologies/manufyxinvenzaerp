# api — manufyxinvenzaerp

_Generated: 2026-09-19 15:10:14_

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
| `download_bom_template` | 1110 |
| `clear_drawing_import` | 1168 |
| `get_cancelled_drawing_links` | 1203 |
| `parse_bom_excel` | 137 |
| `create_drawings_from_import` | 396 |
| `process_drawings` | 596 |
| `verify_raw_materials` | 984 |
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
| `get_bom_info` | 1024 |
| `get_so_drawings_for_bom_picker` | 1081 |
| `get_raw_materials` | 1205 |
| `check_stock_availability` | 1348 |
| `move_to_exact_match` | 1742 |
| `update_exact_match_from_consolidate` | 1905 |
| `finalize_mapping` | 2129 |
| `verify_raw_materials` | 2388 |
| `get_batch_reservation_summary` | 2404 |
| `get_batch_item` | 2440 |
| `get_batch_stock_summary` | 2448 |
| `get_batch_cross_table_usage` | 2686 |
| `validate_planned_stock` | 2818 |
| `reserve_batches` | 2984 |
| `get_available_excess_batches` | 3156 |
| `add_excess_material_mapping` | 3222 |
| `get_available_virtual_excess_items` | 3317 |
| `claim_virtual_excess_mapping` | 3430 |
| `reserve_exact_match_batches` | 3643 |
| `unreserve_exact_match_batches` | 3790 |
| `check_mapping_batch_availability` | 3841 |
| `unreserve_batches` | 3902 |
| `reassign_batch` | 4126 |
| `make_production_plan` | 4445 |
| `make_material_request` | 4521 |
| `make_material_request_from_consolidate` | 4675 |
| `update_so_difference_kg` | 4813 |
| `auto_suggest_consolidate_dimensions` | 4843 |
| `auto_purchase_from_mp` | 4931 |
| `complete_batch_mapping` | 5137 |
| `@frappe.validate_and_sanitize_search_inputs` | 944 |
| `@frappe.validate_and_sanitize_search_inputs` | 998 |
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
| `get_operations_from_routing` | 916 |
| `get_standard_routing_operations` | 929 |
| `make_material_request` | 942 |
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
| `refresh_weight_summary` | 1120 |
| `get_mip_batch_plan_html` | 1296 |
| `download_mip_batch_plan_pdf` | 1302 |
| `get_mip_consolidate_plan_html` | 1441 |
| `download_mip_consolidate_plan_pdf` | 1447 |
| `check_mip_batch_change_allowed` | 234 |
| `check_mip_raw_materials_refreshable` | 242 |
| `refresh_mip_raw_materials_manual` | 256 |
| `refresh_mip_raw_materials` | 276 |
| `create_from_subcontracting_order` | 50 |
| `save_transfer_draft` | 538 |
| `get_transfer_draft` | 587 |
| `` | 69 |
| `populate_from_production_plan` | 72 |
| `unlink_excess_claim` | 920 |
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
| `has_cnc_stock` | 1462 |
| `get_mip_cnc_button_state` | 1482 |
| `get_mip_readiness_check` | 1556 |
| `create_mip_transfer_entry` | 1714 |
| `create_mip_partial_transfer` | 1764 |
| `get_mip_cnc_pending_items` | 1842 |
| `create_mip_cnc_partial_forward` | 1899 |
| `create_mip_cnc_forward_entry` | 2025 |
| `create_mip_excess_return_entry` | 2098 |
| `get_mip_process_loss_state` | 283 |
| `create_mip_process_loss_entry` | 356 |
| `get_mip_pending_items` | 579 |
| `update_transfer_sec_qty` | 812 |
## subcontracting_management/subcontracting.py

| Method | Line |
|--------|------|
| `` | 2179 |
| `` | 2182 |
| `` | 2185 |
| `` | 2188 |
| `` | 2191 |
| `create_sco_from_production_plan` | 26 |
| `create_sco_and_mip_from_production_plan` | 261 |
| `delete_sco_and_mip_for_production_plan` | 286 |
| `` | 366 |
| `create_supplier_operation_entries` | 369 |
| `get_soe_summary` | 391 |
| `get_final_stock_entry_preview` | 604 |
| `create_finished_goods_entry` | 670 |
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

_158 whitelisted methods_
