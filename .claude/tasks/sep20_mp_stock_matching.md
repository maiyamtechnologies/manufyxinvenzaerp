# SEP 20 — Material Planning: stock matching after a purchase

> Status: approved 20 Sep 2026, in development.

## Why

MP-2026-00129 (deleted; evidence in backup `20260920_014602-manufact-database.sql.gz`):
- 7 Exact Match rows reserved, then **PR-26-00037** received and its allocation reserved 93
  rows in Material Mapping (16,074.889 Kg).
- The user unreserved all 100 rows and ran Check Stock Availability again. **76
  requirements went to Unavailable Items** (to purchase): PLATE10 44, ISA100 24, ISMB250 6,
  ISMB400 2.

Two causes:
1. **Bug.** `_ordered_item_codes` protects every item on a Material Request that isn't
   Cancelled or Stopped. MAT-MR-2026-00031 stayed "Partially Ordered" after the receipt,
   so the re-check passed those Unavailable rows through untouched and never tried the
   received stock.
2. **Dimensions.** The purchase came in consolidated sizes: PLATE10 731 × 311 for 20 plate
   sizes, ISA100 390 mm for 190/320/340/390, ISMB250 7,479 mm for 879/979/3,186/7,479.
   Exact Match only takes equal sizes.

## Decisions (user)

| # | Decision |
|---|---|
| 1 | Re-check: **match received stock first**. Only what stock can't cover stays protected as "being purchased", and only while the MR still has quantity not yet received. |
| 2 | New checkbox **Check stock without dimensions** next to Raw Materials Warehouse. For Plates and Structurals: same item only, any size. Exact-size batches first, then other sizes, largest free first. Exact Kg with no whole-piece rounding. Rows get Reserve Without Dimensions ticked, with fractional Nos (Kg ÷ the batch's piece weight). No excess row. Uncovered requirements go to Material Mapping. Rows already reserved are kept on a re-check. Unticked = today's behaviour. |
| 3 | New action on Available Raw Materials: **Allocate from Purchase Receipt**. Pick a submitted receipt, and its batches are matched to this plan's uncovered requirements with the same rules as #2 (rows added to Exact Match with Reserve Without Dimensions). Batches reserved anywhere, or already on a row of this plan, are never reused. |

## Design

- `_pending_purchase_items(mp_name)` replaces `_ordered_item_codes` for the re-check: an
  item counts only while its MR line has `received_qty < stock_qty` on an active MR.
- Re-check: a protected requirement is matched to stock like any other. Its protected
  Unavailable row is kept only for the part stock can't cover, with qty reduced to the
  shortfall, or dropped if covered.
- One allocator, `_allocate_without_dimensions(req_kg, candidates, batch_free, ...)`, is
  used by both #2 and #3. `candidates` are same-item batches, exact size first.
- ARM rows made this way carry the **batch's** dimensions (the table has one set: what is
  transferred), `reserve_without_dimensions = 1`, `required_qty` = exact Kg, and `sec_qty`
  via `_sec_nos_for_weight_arm`.
- Re-check with reservations (checkbox only): reserved ARM / Material Mapping rows are
  returned unchanged. Their Kg counts against the requirement (coverage key: item, DUNO,
  item no) and against the batch's free Kg. The JS guard is lifted only when the box is
  ticked.
- #3 `allocate_receipt_to_plan(mp_name, pr_name)`:
  - receipt batches come from its Serial and Batch Bundles;
  - free Kg in the plan's warehouse = stock − reserved by any plan − already on this
    plan's rows;
  - uncovered requirements = raw materials − Kg already on ARM / batch-mapped Material
    Mapping rows;
  - covered Kg is taken off "Not Mapped" Material Mapping rows and Unavailable rows for
    the same requirement.

## Tests

- `verify_mp_stock_without_dimensions`, with stand-in batch stock through the real
  `check_stock_availability`: checkbox on/off, exact first, fractional Nos, the MR
  protection with and without receipt, reservations kept.
- `verify_mp_allocate_from_receipt`: receipt batches only, reserved and used batches
  skipped, Material Mapping / Unavailable reduced.
