# api — manufyxinvenzaerp

_Generated: 2026-08-29 23:43:53_

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
| `check_existing_bom` | 189 |
## drawing_management/drawing_utils.py

| Method | Line |
|--------|------|
| `create_bom_from_drawing` | 112 |
| `create_production_plan_from_bom` | 224 |
| `create_revision` | 24 |
| `parse_drawing_items_csv` | 278 |
| `update_customer_provided_weight` | 399 |
| `get_batches_for_drawing_item` | 80 |
| `mark_as_final_revision` | 10 |
## drawing_management/so_drawing_import.py

| Method | Line |
|--------|------|
| `clear_drawing_import` | 1030 |
| `get_cancelled_drawing_links` | 1065 |
| `parse_bom_excel` | 127 |
| `create_drawings_from_import` | 385 |
| `process_drawings` | 566 |
| `verify_raw_materials` | 856 |
| `download_bom_template` | 975 |
## item_management/item.py

| Method | Line |
|--------|------|
| `has_item_transactions` | 125 |
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
| `get_raw_materials` | 1103 |
| `check_stock_availability` | 1244 |
| `move_to_exact_match` | 1638 |
| `update_exact_match_from_consolidate` | 1801 |
| `finalize_mapping` | 2025 |
| `verify_raw_materials` | 2284 |
| `get_batch_reservation_summary` | 2300 |
| `get_batch_item` | 2336 |
| `get_batch_stock_summary` | 2344 |
| `get_batch_cross_table_usage` | 2582 |
| `validate_planned_stock` | 2714 |
| `reserve_batches` | 2841 |
| `get_available_excess_batches` | 3013 |
| `add_excess_material_mapping` | 3079 |
| `get_available_virtual_excess_items` | 3174 |
| `claim_virtual_excess_mapping` | 3287 |
| `reserve_exact_match_batches` | 3500 |
| `unreserve_exact_match_batches` | 3647 |
| `check_mapping_batch_availability` | 3698 |
| `unreserve_batches` | 3759 |
| `reassign_batch` | 3924 |
| `make_production_plan` | 4186 |
| `make_material_request` | 4257 |
| `make_material_request_from_consolidate` | 4411 |
| `update_so_difference_kg` | 4549 |
| `auto_suggest_consolidate_dimensions` | 4579 |
| `auto_purchase_from_mp` | 4667 |
| `complete_batch_mapping` | 4856 |
| `@frappe.validate_and_sanitize_search_inputs` | 864 |
| `@frappe.validate_and_sanitize_search_inputs` | 918 |
| `get_bom_info` | 944 |
| `get_so_drawings_for_bom_picker` | 996 |
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
| `get_production_plans_for_sales_order` | 1290 |
| `@frappe.validate_and_sanitize_search_inputs` | 1315 |
| `get_job_work_order_for_production_plan` | 1349 |
## production_plan_management/production_plan.py

| Method | Line |
|--------|------|
| `get_items_for_material_requests` | 284 |
| `get_mp_planned_weights` | 661 |
| `get_pp_drawings_for_picker` | 713 |
| `get_operations_from_routing` | 860 |
| `get_standard_routing_operations` | 873 |
| `make_material_request` | 886 |
## purchase_order_management/purchase_order.py

| Method | Line |
|--------|------|
| `get_po_item_uom` | 10 |
## purchase_receipt_management/purchase_receipt.py

| Method | Line |
|--------|------|
| `get_pr_mp_allocations` | 1177 |
| `get_pr_item_uom` | 16 |
| `get_mp_for_pr` | 275 |
| `diagnose_mp_allocation` | 296 |
| `retry_mp_allocation` | 337 |
| `allocate_pr_stock_to_mp` | 501 |
## sq_management/supplier_quotation.py

| Method | Line |
|--------|------|
| `get_sq_item_uom` | 19 |
## subcontracting_management/doctype/material_issue_plan/material_issue_plan.py

| Method | Line |
|--------|------|
| `refresh_weight_summary` | 1030 |
| `get_mip_batch_plan_html` | 1206 |
| `download_mip_batch_plan_pdf` | 1212 |
| `check_mip_raw_materials_refreshable` | 175 |
| `refresh_mip_raw_materials_manual` | 189 |
| `refresh_mip_raw_materials` | 209 |
| `save_transfer_draft` | 457 |
| `create_from_subcontracting_order` | 50 |
| `get_transfer_draft` | 506 |
| `` | 69 |
| `populate_from_production_plan` | 72 |
| `unlink_excess_claim` | 830 |
## subcontracting_management/material_issue_plan_transfer.py

| Method | Line |
|--------|------|
| `has_cnc_stock` | 1089 |
| `get_mip_cnc_button_state` | 1109 |
| `get_mip_readiness_check` | 1183 |
| `create_mip_transfer_entry` | 1341 |
| `create_mip_partial_transfer` | 1391 |
| `get_mip_cnc_pending_items` | 1469 |
| `create_mip_cnc_partial_forward` | 1526 |
| `create_mip_cnc_forward_entry` | 1648 |
| `create_mip_excess_return_entry` | 1721 |
| `get_mip_process_loss_state` | 258 |
| `create_mip_process_loss_entry` | 331 |
| `get_mip_pending_items` | 554 |
| `update_transfer_sec_qty` | 762 |
## subcontracting_management/subcontracting.py

| Method | Line |
|--------|------|
| `create_sco_and_mip_from_production_plan` | 189 |
| `` | 2032 |
| `` | 2035 |
| `` | 2038 |
| `` | 2041 |
| `` | 2044 |
| `delete_sco_and_mip_for_production_plan` | 214 |
| `create_sco_from_production_plan` | 26 |
| `` | 294 |
| `create_supplier_operation_entries` | 297 |
| `get_soe_summary` | 319 |
| `get_final_stock_entry_preview` | 526 |
| `create_finished_goods_entry` | 585 |
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

## Total

_133 whitelisted methods_
