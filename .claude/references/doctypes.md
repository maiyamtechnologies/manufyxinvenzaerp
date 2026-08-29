# doctypes — manufyxinvenzaerp

_Generated: 2026-08-29 23:53:06_

## drawing

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/drawing` |
| Controller | `drawing_management/doctype/drawing/drawing.py` |
| Client script | `drawing_management/doctype/drawing/drawing.js` |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` before_insert` | no |
| ` validate` | no |
| ` before_submit` | no |
| ` on_submit` | no |
| ` on_cancel` | no |
| ` _recalculate_all` | no |
| ` _check_missing_fields` | no |
| ` _calculate_totals` | no |
| ` _sales_order_row` | no |
| ` _touch_sales_order` | no |
| ` _release_sales_order_row` | no |
| ` _link_to_sales_order_row` | no |
| ` _recalculate_row_qty` | no |
| ` _recalculate_row_totals` | no |
| ` _check_row_missing_fields` | no |
| ` check_existing_bom` | no |

---

## drawing_item

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/drawing_item` |
| Controller | `drawing_management/doctype/drawing_item/drawing_item.py` |
| Client script | none |

---

## drawing_weight_change_log

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/drawing_weight_change_log` |
| Controller | `drawing_management/doctype/drawing_weight_change_log/drawing_weight_change_log.py` |
| Client script | none |

---

## job_nature

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/job_nature` |
| Controller | `drawing_management/doctype/job_nature/job_nature.py` |
| Client script | none |

---

## nature_of_work

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/nature_of_work` |
| Controller | `drawing_management/doctype/nature_of_work/nature_of_work.py` |
| Client script | none |

---

## production_plan_bom_raw_material

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/production_plan_bom_raw_material` |
| Controller | `drawing_management/doctype/production_plan_bom_raw_material/production_plan_bom_raw_material.py` |
| Client script | none |

---

## rate_schedule_price_log

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/rate_schedule_price_log` |
| Controller | `drawing_management/doctype/rate_schedule_price_log/rate_schedule_price_log.py` |
| Client script | none |

---

## rate_schedule

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/rate_schedule` |
| Controller | `drawing_management/doctype/rate_schedule/rate_schedule.py` |
| Client script | none |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` before_insert` | no |
| ` validate` | no |
| ` _track_rate_change` | no |

---

## sales_order_drawing_raw_material

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/sales_order_drawing_raw_material` |
| Controller | `drawing_management/doctype/sales_order_drawing_raw_material/sales_order_drawing_raw_material.py` |
| Client script | none |

---

## sales_order_duno_item

| Key | Value |
|-----|-------|
| Module | drawing_management |
| Path | `drawing_management/doctype/sales_order_duno_item` |
| Controller | `drawing_management/doctype/sales_order_duno_item/sales_order_duno_item.py` |
| Client script | none |

---

## manufyxinvenza_settings

| Key | Value |
|-----|-------|
| Module | manufyxinvenzaerp |
| Path | `manufyxinvenzaerp/doctype/manufyxinvenza_settings` |
| Controller | `manufyxinvenzaerp/doctype/manufyxinvenza_settings/manufyxinvenza_settings.py` |
| Client script | none |

---

## cut_sheet_allocation

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/cut_sheet_allocation` |
| Controller | `production_management/doctype/cut_sheet_allocation/cut_sheet_allocation.py` |
| Client script | none |

---

## cut_sheet

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/cut_sheet` |
| Controller | `production_management/doctype/cut_sheet/cut_sheet.py` |
| Client script | `production_management/doctype/cut_sheet/cut_sheet.js` |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` validate` | no |
| ` _sync_allocations_from_rows` | no |
| ` on_trash` | no |
| ` _block_identity_changes` | no |
| ` claiming_rows` | no |
| ` _block_cut_changes_while_claimed` | no |
| ` _block_if_claimed` | no |
| ` _block_if_transferred` | no |
| ` _fetch_batch_dimensions` | no |
| ` _calculate` | no |
| ` _validate_allocations_fit` | no |
| ` _set_status` | no |
| ` suggest_w1_sec_qty` | no |
| ` get_available_cut_sheets` | no |
| ` get_cut_sheet_for_batch` | no |
| ` allocate_cut_sheet` | no |
| ` refresh_cut_sheet_allocations` | no |
| ` cut_sheet_warehouse_query` | no |
| ` mark_cut_sheet_inactive` | no |
| ` release_all_cut_sheet_allocations` | no |
| ` release_cut_sheet_allocation` | no |
| ` apply_w2_to_batch` | no |
| ` revert_w2_from_batch` | no |

---

## inspection_call_log

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/inspection_call_log` |
| Controller | `production_management/doctype/inspection_call_log/inspection_call_log.py` |
| Client script | none |

---

## inspection_entry

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/inspection_entry` |
| Controller | `production_management/doctype/inspection_entry/inspection_entry.py` |
| Client script | none |
| doc_events | see hooks.md |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` validate` | no |
| ` _autofill_total_qty_to_check` | no |
| ` _set_inspection_complete_date` | no |
| ` before_submit` | no |
| ` _validate_scalar_result` | no |
| ` _validate_soe_items` | no |
| ` _validate_pr_items` | no |

---

## inspection_entry_item

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/inspection_entry_item` |
| Controller | `production_management/doctype/inspection_entry_item/inspection_entry_item.py` |
| Client script | none |

---

## job_card_raw_material

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/job_card_raw_material` |
| Controller | `production_management/doctype/job_card_raw_material/job_card_raw_material.py` |
| Client script | none |

---

## manufyx_decision_log

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/manufyx_decision_log` |
| Controller | `production_management/doctype/manufyx_decision_log/manufyx_decision_log.py` |
| Client script | none |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` on_trash` | no |

---

## material_planning_available_raw_material

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/material_planning_available_raw_material` |
| Controller | `production_management/doctype/material_planning_available_raw_material/material_planning_available_raw_material.py` |
| Client script | none |

---

## material_planning_batch_change_log

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/material_planning_batch_change_log` |
| Controller | `production_management/doctype/material_planning_batch_change_log/material_planning_batch_change_log.py` |
| Client script | none |

---

## material_planning_bom_item

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/material_planning_bom_item` |
| Controller | `production_management/doctype/material_planning_bom_item/material_planning_bom_item.py` |
| Client script | none |

---

## material_planning_consolidate_item

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/material_planning_consolidate_item` |
| Controller | `production_management/doctype/material_planning_consolidate_item/material_planning_consolidate_item.py` |
| Client script | none |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` recalculate` | no |

---

## material_planning_material_mapping

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/material_planning_material_mapping` |
| Controller | `production_management/doctype/material_planning_material_mapping/material_planning_material_mapping.py` |
| Client script | none |

---

## material_planning

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/material_planning` |
| Controller | `production_management/doctype/material_planning/material_planning.py` |
| Client script | `production_management/doctype/material_planning/material_planning.js` |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` excess_row_availability` | no |
| ` _release_row_pool_claims` | no |
| ` _cut_sheet_thickness` | no |
| ` excess_aware_mapped_status` | no |
| ` validate` | no |
| ` _consolidate_rows_touched` | no |
| ` _warn_undersized_purchase_dimensions` | no |
| ` _sync_cut_sheet_flag` | no |
| ` _sync_cut_sheet_calc` | no |
| ` _sync_batch_remarks` | no |
| ` _consolidate_unavailable_items` | no |
| ` _recalculate_consolidate_items` | no |
| ` _auto_update_planning_status` | no |
| ` _validate_no_cross_table_batch_duplicate` | no |
| ` _set_row_excess` | no |
| ` _update_weight_summary` | no |
| ` _apply_rwd_fractional_nos` | no |
| ` _move_skipped_arm_to_mapping` | no |
| ` _validate_batch_calc_qty` | no |
| ` _validate_alternate_item_qty` | no |
| ` material_mapping_batch_query` | no |
| ` search_bom` | no |
| ` get_bom_info` | no |
| ` get_so_drawings_for_bom_picker` | no |
| ` _nos_from_weight` | no |
| ` _reconcile_sec_qty_with_sales_order` | no |
| ` get_raw_materials` | no |
| ` _requirement_key` | no |
| ` _ordered_item_codes` | no |
| ` check_stock_availability` | no |
| ` _alloc_sec_qty` | no |
| ` _get_non_batch_stock` | no |
| ` _get_non_batch_stock_bulk` | no |
| ` move_to_exact_match` | no |
| ` update_exact_match_from_consolidate` | no |
| ` finalize_mapping` | no |
| ` _verify_nos_vs_qty` | no |
| ` verify_raw_materials` | no |
| ` get_batch_reservation_summary` | no |
| ` get_batch_item` | no |
| ` get_batch_stock_summary` | no |
| ` _get_batch_inspection_block_reason` | no |
| ` _get_batch_total_stock` | no |
| ` _get_batch_reserved_by_others` | no |
| ` _get_batch_reserved_by_others_bulk` | no |
| ` _get_non_batch_reserved_by_others` | no |
| ` _get_non_batch_reserved_by_others_bulk` | no |
| ` get_batch_cross_table_usage` | no |
| ` _update_bom_item_weights` | no |
| ` _calc_kg_per_nos` | no |
| ` _calc_usable_nos_split` | no |
| ` _row_get` | no |
| ` validate_planned_stock` | no |
| ` _add` | no |
| ` _sec_nos_for_weight` | no |
| ` _refresh_touched_cut_sheets` | no |
| ` _require_write` | no |
| ` reserve_batches` | no |
| ` _get_batch_reserved_by_self` | no |
| ` get_available_excess_batches` | no |
| ` add_excess_material_mapping` | no |
| ` get_available_virtual_excess_items` | no |
| ` _release_virtual_excess_source` | no |
| ` claim_virtual_excess_mapping` | no |
| ` materialize_virtual_excess_claim` | no |
| ` reserve_exact_match_batches` | no |
| ` unreserve_exact_match_batches` | no |
| ` check_mapping_batch_availability` | no |
| ` unreserve_batches` | no |
| ` _get_batch_dims` | no |
| ` _calc_batch_qty` | no |
| ` _precheck_batch_reassignment` | no |
| ` _mark_excess_item_mapped` | no |
| ` _batch_change_remarks` | no |
| ` reassign_batch` | no |
| ` _apply_batch_to_mapping_row` | no |
| ` make_production_plan` | no |
| ` make_material_request` | no |
| ` make_material_request_from_consolidate` | no |
| ` _update_so_difference_kg_for_pair` | no |
| ` update_so_difference_kg` | no |
| ` unlink_material_request_on_cancel` | no |
| ` auto_suggest_consolidate_dimensions` | no |
| ` auto_purchase_from_mp` | no |
| ` _collect_batch_mapping_issues` | no |
| ` complete_batch_mapping` | no |

---

## material_planning_raw_material

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/material_planning_raw_material` |
| Controller | `production_management/doctype/material_planning_raw_material/material_planning_raw_material.py` |
| Client script | none |

---

## material_planning_unavailable_item

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/material_planning_unavailable_item` |
| Controller | `production_management/doctype/material_planning_unavailable_item/material_planning_unavailable_item.py` |
| Client script | none |

---

## process_planning

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/process_planning` |
| Controller | `production_management/doctype/process_planning/process_planning.py` |
| Client script | none |

---

## production_plan_available_raw_material

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/production_plan_available_raw_material` |
| Controller | `production_management/doctype/production_plan_available_raw_material/production_plan_available_raw_material.py` |
| Client script | none |

---

## storage_location

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/storage_location` |
| Controller | `production_management/doctype/storage_location/storage_location.py` |
| Client script | none |

---

## store_location

| Key | Value |
|-----|-------|
| Module | production_management |
| Path | `production_management/doctype/store_location` |
| Controller | `production_management/doctype/store_location/store_location.py` |
| Client script | none |

---

## job_card_consumption_log

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/job_card_consumption_log` |
| Controller | `subcontracting_management/doctype/job_card_consumption_log/job_card_consumption_log.py` |
| Client script | none |

---

## material_issue_plan_consolidate_item

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/material_issue_plan_consolidate_item` |
| Controller | `subcontracting_management/doctype/material_issue_plan_consolidate_item/material_issue_plan_consolidate_item.py` |
| Client script | none |

---

## material_issue_plan

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/material_issue_plan` |
| Controller | `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py` |
| Client script | `subcontracting_management/doctype/material_issue_plan/material_issue_plan.js` |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` after_insert` | no |
| ` validate` | no |
| ` on_trash` | no |
| ` create_from_subcontracting_order` | no |
| ` populate_from_production_plan` | no |
| ` _mip_refresh_blocked_message` | no |
| ` check_mip_raw_materials_refreshable` | no |
| ` refresh_mip_raw_materials_manual` | no |
| ` refresh_mip_raw_materials` | no |
| ` _sync_excess_availability` | no |
| ` _sync_transferred_qty` | no |
| ` key` | no |
| ` save_transfer_draft` | no |
| ` get_transfer_draft` | no |
| ` _clear_transfer_draft` | no |
| ` _sync_consolidate_items` | no |
| ` _batch_stock_in` | no |
| ` _cut_sheet_reference` | no |
| ` _lookup_drawing_planned_weight` | no |
| ` _drawing_planned_weights` | no |
| ` _throw_claimed_excess_locked` | no |
| ` _assert_claimed_excess_unchanged` | no |
| ` unlink_excess_claim` | no |
| ` _sync_excess_return_totals` | no |
| ` _used_in_fg_weight` | no |
| ` _sync_batch_remarks` | no |
| ` _maybe_mark_completed` | no |
| ` _unaccounted_weight` | no |
| ` recheck_mip_completion` | no |
| ` refresh_weight_summary` | no |
| ` get_target_context` | no |
| ` get_mip_batch_plan_html` | no |
| ` download_mip_batch_plan_pdf` | no |
| ` _render_mip_batch_plan_html` | no |

---

## material_issue_plan_raw_material

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/material_issue_plan_raw_material` |
| Controller | `subcontracting_management/doctype/material_issue_plan_raw_material/material_issue_plan_raw_material.py` |
| Client script | none |

---

## sco_drawing_item

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/sco_drawing_item` |
| Controller | `subcontracting_management/doctype/sco_drawing_item/sco_drawing_item.py` |
| Client script | none |

---

## sco_excess_material_item

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/sco_excess_material_item` |
| Controller | `subcontracting_management/doctype/sco_excess_material_item/sco_excess_material_item.py` |
| Client script | none |

---

## soe_consumption_log

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/soe_consumption_log` |
| Controller | `subcontracting_management/doctype/soe_consumption_log/soe_consumption_log.py` |
| Client script | none |

---

## soe_drawing_detail

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/soe_drawing_detail` |
| Controller | `subcontracting_management/doctype/soe_drawing_detail/soe_drawing_detail.py` |
| Client script | none |

---

## soe_inspection_item

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/soe_inspection_item` |
| Controller | `subcontracting_management/doctype/soe_inspection_item/soe_inspection_item.py` |
| Client script | none |

---

## supplier_operation_entry

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/supplier_operation_entry` |
| Controller | `subcontracting_management/doctype/supplier_operation_entry/supplier_operation_entry.py` |
| Client script | none |
| doc_events | see hooks.md |

---

## supplier_operation_item

| Key | Value |
|-----|-------|
| Module | subcontracting_management |
| Path | `subcontracting_management/doctype/supplier_operation_item` |
| Controller | `subcontracting_management/doctype/supplier_operation_item/supplier_operation_item.py` |
| Client script | none |

---

