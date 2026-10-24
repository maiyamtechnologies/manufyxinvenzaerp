# Manufyxinvenzaerp — Implemented Features
**App:** manufyxinvenzaerp | **Platform:** Frappe v16 / ERPNext v16 | **Site:** manufactv16
**Date:** 2026-07-16

---

## 1. Item Master Customization

### 1.1 Parent Item Group Enforcement
- `Parent Item Group` is a mandatory custom field on the Item master.
- Drives calculation type automatically:
  - **Structurals / Plates** → Formula Weight Calculation
  - **Nuts and Bolts** → Normal Weight Calculation

### 1.2 UOM Validation per Item Group
- **Structurals / Plates**: Primary UOM must be `Kg`; Secondary UOM must be `Nos`.
- **Nuts and Bolts**: Primary UOM must be `Nos`; Secondary UOM must be `Kg`.
- System throws an error if mismatched UOMs are set.

### 1.3 Batch Configuration Rules
- For Structurals / Plates with `Has Batch No` enabled:
  - `Custom Batch Abbreviation (Prefix)` is mandatory.
  - `Create New Batch` is auto-enabled.
- Batch prefix cannot be changed once batches exist for the item (prevents data inconsistency).

### 1.4 Locked Fields after Transactions
Once stock or order transactions exist for an item, the following fields are locked (cannot be changed):
- Parent Item Group, Default UOM, Unit Weight, Secondary UOM, Custom Batch Abbreviation.

---

## 2. Drawing Management

### 2.1 Drawing Doctype (Custom)
A new central doctype representing the engineering drawing for a Finished Good.

**Key fields:** Sales Order link, Customer, FG Item Code, DUNO/Mark No, Revision Number, Qty to Manufacture, Drawing Items (child table), Total Weight, Status.

### 2.2 Drawing Revision Management
- `Rev No` auto-increments when a Drawing is amended (starts at 0).
- Cancelling a Drawing automatically sets status to `Old Revision`.

### 2.3 Drawing Item Calculation Engine
Formula-based quantity calculation on each line item depending on `Parent Item Group`:
- **Structurals**: `Qty = (Length/1000) × Unit Weight × Sec Qty`
- **Plates**: `Qty = (L/1000) × (W/1000) × Thickness × Unit Weight × Sec Qty`
- **Nuts and Bolts**: `Sec Qty = Qty × Unit Weight`

Total Weight is summed across all items. Missing required dimension fields trigger a warning on save and block submission.

### 2.4 Drawing Lifecycle
`Working` → (submit + mark_as_final_revision) → `Final Revision` → (used for BOM creation)

### 2.5 CSV Import for Drawing Items
- Button on Drawing to upload a CSV file with item rows.
- Server-side parsing: fetches item master data, runs formula calculation, returns ready-to-insert rows.
- Accepts flexible column names (case-insensitive); auto-assigns item numbers if not provided.

### 2.6 Sales Order Integration
- **Create Drawings from SO**: One Drawing created per SO line item; blocked if a Drawing already exists for the SO.
- **Dashboard Link**: Drawings appear in the Sales Order connections dashboard.

### 2.7 BOM Creation from Drawing
- BOM can only be created from a submitted `Final Revision` Drawing.
- All drawing item dimensions (L, W, T, Unit Weight, Sec Qty, Sec UOM, Material Spec, Item Number) are carried into BOM Item custom fields.
- **BOM Validation (via hook)**: Any BOM linked to a Drawing enforces:
  - Drawing items cannot be removed from the BOM.
  - Quantities and dimensions are restored from the Drawing if manually edited in the BOM.

### 2.8 Production Plan Creation from BOM
- BOM must be submitted.
- Auto-populates the Process Planning child table from the BOM's routing operations.

---

## 3. BOM Override

- ERPNext's standard `BOM` doctype is extended via `override_doctype_class`.
- Custom fields added: Drawing reference (`custom_drawing`), DUNO/Mark No (`custom_duno_mark_no`).
- Custom BOM search in Material Planning: searches by BOM name, item code, item name, or DUNO/Mark No.

---

## 4. Material Planning (Custom Doctype)

The largest and most complex module. Drives all raw material identification, stock matching, batch reservation, and downstream MR/PP creation.

### 4.1 BOM Explosion & Raw Materials
- Multiple BOMs (with qty to manufacture) can be added to one Material Planning.
- `Get Raw Materials` explodes each BOM into a flat raw materials list.
- Reverses the formula to compute `Sec Qty (NOS)` from Kg for each Structural/Plate item.
- Cross-validates computed Sec Qty against the stored BOM value and warns on mismatch.

### 4.2 Stock Availability Check — Three-Bucket Classification
`Check Stock Availability` classifies each raw material row into one of three buckets:

| Bucket | Condition |
|---|---|
| **Available Raw Materials** | Batch item: exact dimension batch found with free stock; Non-batch: stock ≥ required |
| **Material Mapping** | Batch item: no exact-dimension batch found (needs alternate/different-dimension batch); also partial-stock shortfall rows |
| **Unavailable Items** | Non-batch item: stock < required (needs purchase) |

- Has a `Store Location` field intended for location-filtered stock queries, but as of this writing this is not a working, populated feature in practice: `Store Location` (a doctype scoped only to the Material Planning child tables) has **zero records** and no Material Planning document has ever set it — the query path it feeds (`get_sbb_available_qty`'s `location` filter) previously raised a hard SQL error whenever a location value *was* supplied, since it queried a `store_location` column that has never existed on Stock Ledger Entry (fixed in Phase 1 HP-05 to query the correct existing column instead, `storage_location`; see the Storage Location / Store Location note in §16 below). Whether Material Planning's location filtering should instead key off `Storage Location` — the separate, real, heavily-used ERPNext Inventory Dimension already wired onto Stock Ledger Entry and 30+ other doctypes across this app — is an open product question, not yet decided.
- Accounts for reservations made by other Material Planning documents (cross-MP awareness).

### 4.3 Batch Dimension Matching (SBB/SBE)
- Batch availability is queried via `Serial and Batch Bundle` / `Serial and Batch Entry` tables.
- Only batches whose `Length`, `Width`, `Thickness` exactly match the required dimensions are considered an exact match.

### 4.4 Material Mapping — Alternate/Different-Dimension Batch Assignment
- User can manually assign a different-dimension batch to Material Mapping rows.
- `Batch Calc Qty` is auto-calculated from the assigned batch's dimensions.
- Save-time validation: blocks if calculated qty exceeds available free stock; warns if below required qty.
- `Reserve Without Dimensions` flag allows bypassing dimension calc and reserving the required qty directly.
- `Finalize Mapping`: unmapped rows (no batch assigned) are moved to Unavailable Items.
- **Weight Summary — Difference in Kg**: The Details tab shows a live HTML summary of `Σ(batch_calc_qty − qty)` for all Mapped rows, coloured green (excess) or red (short).

### 4.4a Update Difference Kg in Sales Order
- Button **"Update Difference Kg in Sales Order"** in the Weight Summary section.
- On click, calls `update_so_difference_kg()` which:
  - Collects unique `(sales_order, duno_mark_no)` pairs from this MP's Material Mapping rows.
  - Queries **all** Material Planning Material Mapping rows (across all MPs) for each pair with `batch_mapped = "Mapped"`.
  - Sums `batch_calc_qty − qty` per pair and writes the result to the `difference_kg` field on the matching `Sales Order DUNO Item` row via `db.set_value` (bypasses SO submitted restriction).
- The `difference_kg` Float field is visible in the Sales Order Drawing List (DUNO Items) child table.

### 4.5 Stock Reservation
- **Reserve Batches** (Material Mapping): reserves qty per batch with partial-stock awareness; tracks intra-document same-batch usage.
- **Reserve Exact Match Batches** (Available Raw Materials): same logic for the exact-match table (supports both batch and non-batch items).
- **Unreserve**: selective unreserve by child row name, for both tables independently.
- **Check Mapping Batch Availability**: pre-flight check that shows shortfall warnings before reserving.
- Reserved rows are locked — qty/batch changes blocked on save until unreserved.

### 4.6 Cross-MP Reservation Integrity
- Reservations from all other Material Planning documents are subtracted when computing available qty.
- When a Stock Entry (Manufacture / Transfer / Issue / Repack) is submitted, reservations for consumed batches are automatically released.
- When the Stock Entry is cancelled, reservations are restored.

### 4.7 Batch Reservation Summary
- Per-batch summary of all active reservations across all MPs (shows MP name, SO, customer, project, reserved qty).

### 4.8 Move to Exact Match
- For selected Unavailable Items, re-checks if exact-dimension batch stock has arrived (e.g. after a Purchase Receipt).
- Matched rows move to Available Raw Materials; still-unavailable remain; batch items with no matching stock move to Material Mapping.

### 4.9 Make Production Plan
- Creates a draft Production Plan from the Material Planning's BOM Items list.
- Auto-links drawing, DUNO/Mark No, Sales Order, Customer, and Material Planning reference on PP items.

### 4.10 Make Material Request
- Creates Material Requests for Unavailable Items.
- Links the Material Request back to the Material Planning for traceability.
- On MR cancel or trash, the MP link is automatically cleared.

### 4.11 PR Stock Auto-Allocation to Material Planning
- After a Purchase Receipt is submitted: `Allocate PR Stock to MP` traces PR → PO → MR → Material Planning.
- Original item purchased → added to Available Raw Materials.
- Alternate item purchased → added to Material Mapping with the received batch and dimensions.

---

## 5. Purchase Order Customization

- **Formula Qty Auto-Calculation**: Qty recalculated from dimensions on save (Structurals / Plates / Nuts and Bolts).
- **Missing Fields Validation**: Warning on save; hard block on submit for Structurals and Plates (Length, Width, Thickness, Unit Weight, Sec Qty).
- **Custom Total Weight**: Sum of all Structural/Plate item quantities on the PO.
- **Custom UOM Link Query**: Link field on PO items returns only UOMs valid for the selected item.

---

## 6. Purchase Receipt Customization

- **Formula Qty Auto-Calculation**: Same formula logic as PO (Structurals / Plates / Nuts and Bolts).
- **Dimension Fields Auto-Copy from PO**: When PR is created from PO, dimension fields (L, W, T, Sec Qty) are copied from the PO item if not already set.
- **Missing Fields Validation**: Warning on save; block on submit.
- **Custom Total Weight** field on PR header.
- **Weighment Weight** (`custom_weighment_weight`): Float field on PR header to record the actual weighment weight.
- **Supplier Invoice Weight** (`custom_supplier_invoice_weight`): Float field on PR header to record the weight as per supplier invoice; placed after Weighment Weight.
- **Custom UOM Link Query** on PR items.
- **Batch Auto-Naming on Receipt**: On Batch `before_insert`, the batch ID is auto-generated as: `{Prefix}-T{Thickness}-L{Length}-W{Width}-R{ReceiptSuffix}` using the item's batch prefix and PR dimensions.
- **Batch Auto-Naming from Stock Entry (Repack / Material Receipt)**: Similar naming with `SR{suffix}`.
- **Batch Master Auto-Populated**: On SE submit for Material Receipt, the batch's `Supplier`, `Supplier Invoice No`, `Invoice Weight`, `Inward Date` custom fields are set from SE item fields.

---

## 7. Material Request Customization

- **Formula Qty Recalculation** on validate.
- **Missing Fields Validation** (warning on save; block on submit).
- **Custom UOM Link Query** on MR items.
- **Material Planning Link Field** (`custom_material_planning`) on Material Request — provides traceability back to the planning document.

---

## 8. RFQ Customization

- **Dimension fields copied from MR item** when RFQ is created from a Material Request.
- Server-side validate hook to enforce custom rules.

---

## 9. Supplier Quotation Customization

- **Custom data copied from RFQ item** if fields are blank on the SQ (dimensions, sec qty, spec).
- **Formula Qty Recalculation** on validate.
- **Missing Fields Validation**.
- **Custom UOM Link Query** on SQ items.

---

## 10. Production Plan Customization

- **Process Planning Child Table** added to Production Plan: each row has an operation name and `Work Type` (`Internal Jobcard` or `Subcontractor`).
- **Vendor/Contractor Field** on Production Plan (used when creating a Subcontracting Order).
- **Override `get_items_for_material_requests`**: custom implementation that accounts for Store Location inventory dimension and SBB-based available qty in the material request calculation.
- **SBB Available Qty Engine** (`get_sbb_available_qty`): core utility that queries Serial and Batch Bundle → Serial and Batch Entry with optional Store Location filtering and exact dimension matching.

---

## 11. Production Operations — Standard Manufacturing Routing

- On install and every migrate, 12 standard operations and matching workstations are auto-created:
  `Material Issue → Cutting Status → Material Matching → Fit-up → Fitup Inspection → Welding → Welding Inspection → Final → Final Inspection → Blasting → Painting → Despatch`
- A single `Standard Manufacturing Routing` combining all 12 in sequence is also auto-created.

---

## 12. Job Card Customization

- **Raw Material Consumption Child Table** (`custom_raw_material_consumption`) added to Job Card.
- Auto-populated from Work Order required items (with WIP stock qty, dimensions, previous operation consumption).
- **Server-side Consumption Validation**:
  - Structurals/Plates: consumed qty cannot exceed transferred qty to WIP.
  - `Current Nos` cannot exceed `Previous Operation Nos` (whenever a previous-operation Nos value exists — see below).
  - Nuts & Bolts: `manual_qty` cannot exceed WIP stock.
- **Previous Operation Data**: fetched from the preceding Job Card; falls back to the last submitted Supplier Operation Entry (Scenario 3 hybrid subcontractor → internal handoff). A Work Order's Job Cards are always locally renumbered starting at `sequence_id = 1`, so a hybrid plan's *first* Work Order Job Card also has `sequence_id = 1` — the fallback now runs for that case too (previously it only ran for `sequence_id > 1`, silently returning 0 available-to-consume for the WO's first operation after a subcontracted block). The matching "Nos can't exceed previous operation" guard, server-side and in the Job Card client script, was ungated the same way so it actually enforces once the sequence_id 1 case carries a real previous-op value.
- **Consumption Log** (`custom_consumption_log`, drawing-level Nos/Kg log with Employee, From Time, To Time) is backed by its own **Job Card Consumption Log** child doctype — kept separate from Supplier Operation Entry's own Consumption Log (see 14.5) so each side can carry different fields.

---

## 13. Stock Entry Customization

- **Formula Qty Auto-Recalculation** on validate for Repack, Material Receipt, Material Issue (Structurals/Plates only).
- **On Submit**: reduces `custom_sec_qty` on the Batch master for consumed batches (Material Issue, Repack source rows, Material Receipt linked batches).
- **Batch Supplier/Invoice fields** copied to Batch master on Material Receipt submit.
- **Automatic Release of Material Planning Reservations** on submit for consumption-type entries.
- **Automatic Restoration of Reservations** on cancel.
- **Final Operation Consumption Validation**: before a Manufacture SE is submitted, checks that all required items in the final Job Card have recorded consumption.

---

## 14. Subcontracting Management

### 14.1 Supplier Operation Entry (Custom Doctype)
A new doctype to track material consumption at each subcontractor operation.

**Key fields:** Work Order, Subcontracting Order, Production Plan, Operation, Sequence ID, Supplier, Supplier Warehouse, Status, Items child table (item code, dimensions, transferred qty, previous op qty, current consumed qty, batch).

### 14.2 Three Production Scenarios
All three scenarios are supported without code branching at the UI level:

| Scenario | Description |
|---|---|
| **Scenario 1** (All Internal) | PP → Work Order → Job Cards per operation |
| **Scenario 2** (All Subcontractor) | PP → SCO directly (no WO) → Supplier Operation Entries |
| **Scenario 3** (Hybrid) | PP → SCO (sub ops) + Work Order (internal ops); subcontractor completes first, then WIP transfer to internal |

### 14.3 Automated Document Creation from Production Plan
All actions are triggered from the Production Plan / SCO via buttons:

- **Create SCO from Production Plan**: creates a draft Subcontracting Order from subcontractor operations in Process Planning; works with or without a Work Order.
- **Create Work Order from PP**: creates a Work Order containing only the Internal Jobcard operations; links filtered routing operations.
- **Create Supplier Operation Entries** (idempotent): one SOE per subcontractor operation in sequence; pre-populates batch from supplier warehouse stock, dimensions from BOM, and previous-operation consumption from prior SOE.

### 14.4 Material Movement Stock Entries from SCO
- **Send to Subcontractor**: draft Stock Entry transferring BOM items from source warehouse to supplier warehouse.
- **WIP Transfer (Scenario 3)**: Material Transfer from supplier warehouse to company WIP warehouse based on last submitted SOE's consumed quantities.
- **Return Unconsumed Stock**: Material Transfer for leftover materials from supplier warehouse back to a specified company warehouse.

### 14.5 SOE Validation & Lifecycle
- On validate: consumed qty vs transferred; cross-operation Nos check (cannot exceed previous operation's Nos); Nuts & Bolts manual qty check.
- On submit: reduces `custom_sec_qty` on batch master for consumed items; marks `custom_all_ops_complete` on the SCO when the last operation is submitted.
- **SCO Dashboard**: Supplier Operation Entries appear in the Subcontracting Order connections dashboard.
- **Consumption Log** (`consumption_log`, drawing-level Nos/Kg log): Date, Drawing, Qty (Nos), Weight (Kg), Remark — kept lean, with no Employee/From Time/To Time fields (those stayed on Job Card's own Consumption Log, see 12).

---

## 15. Custom Fields Summary

Custom fields are exported per-doctype (`<module>/custom/<doctype>.json`, synced on `bench migrate` — see README's "Custom Fields & Property Setters" section; no longer fixture-based as of 2026-08-18) and applied across the following standard doctypes:

| Doctype | Notable Custom Fields |
|---|---|
| Item | Parent Item Group, Calculation Type, Unit Weight, Secondary UOM, Batch Prefix |
| Batch | Sec Qty, Sec UOM, Thickness, Length, Width, Supplier, Invoice No, Invoice Weight, Inward Date |
| BOM / BOM Item | Drawing, DUNO/Mark No, Item Number, Material Spec, Dimensions, Sec Qty, Sec UOM, Sales Order, Parent Item Group |
| Purchase Order / Items | Total Weight, Dimensions, Sec Qty, Parent Item Group, UOM custom link |
| Purchase Receipt / Items | Total Weight, Weighment Weight, Supplier Invoice Weight, Dimensions, Sec Qty, Parent Item Group, Supplier fields, existing invoice fields |
| Material Request / Items | Material Planning link, Dimensions, Sec Qty |
| Supplier Quotation / Items | Dimensions, Sec Qty |
| Production Plan / Items | Drawing, DUNO/Mark No, Customer, Material Planning link; Process Planning table, Vendor/Contractor |
| Job Card | Raw Material Consumption child table, Dimensions per row, Inspection tab (Inspection Status, Inspection Call Date, Inspection Call Log table) |
| Stock Entry / Items | Dimensions, Sec Qty, Parent Item Group, Supplier, Invoice No |
| Subcontracting Order | Production Plan, Work Order, Source Warehouse, WIP Warehouse, All Ops Complete |

---

## 16. New Custom Doctypes

| Doctype | Module | Purpose |
|---|---|---|
| Drawing | drawing_management | Engineering drawing master; drives BOM and production |
| Drawing Item | drawing_management | Child table for drawing line items |
| Nature of Work | drawing_management | Master for work classification |
| Production Plan BOM Raw Material | drawing_management | Child table |
| Sales Order DUNO Item | drawing_management | Child table for SO DUNO mapping |
| Material Planning | production_management | Core raw material planning and batch reservation |
| Material Planning Available Raw Material | production_management | Child table — exact-match stock |
| Material Planning BOM Item | production_management | Child table — BOM list |
| Material Planning Material Mapping | production_management | Child table — alternate/different-dimension batch mapping |
| Material Planning Raw Material | production_management | Child table — exploded raw material list |
| Material Planning Unavailable Item | production_management | Child table — items to purchase |
| Job Card Raw Material | production_management | Child table — per-operation consumption |
| Job Card Consumption Log | subcontracting_management | Child table on Job Card — drawing-level Nos/Kg consumption log, with Employee/From Time/To Time |
| Process Planning | production_management | Child table on Production Plan — operation routing |
| Production Plan Available Raw Material | production_management | Child table |
| Storage Location / Store Location | production_management | See distinction note directly below — these are two separate doctypes, not a naming variant of one |
| Inspection Entry | production_management | Submittable QC sign-off record for Fitup Inspection / Final Inspection rounds |
| Inspection Call Log | production_management | Child table on Job Card/SOE — one row per inspection call round |
| Supplier Operation Entry | subcontracting_management | Per-operation subcontractor material consumption |
| Supplier Operation Item | subcontracting_management | Child table |

**`Storage Location` vs. `Store Location` — these are genuinely two different doctypes, not a typo:**
- **`Storage Location`** is the real, heavily-wired ERPNext Inventory Dimension — registered via `setup.py`'s `setup_storage_location()`, referenced by 32 Link-type custom fields across Stock Ledger Entry, Job Card, Purchase/Sales/Delivery/Subcontracting documents, Drawing Item, Supplier Operation Item, and Production Plan's own child tables. It has active seed data (`A-1`, `A-2`, plus site-specific locations like `B-1`/`B-2`/`B-3`/`B-5`/`CNCSET`/`CNC`).
- **`Store Location`** is a narrower doctype scoped only to the Material Planning family (6 Link fields, all within Material Planning's own child tables). As of this writing it has **zero records** in this site's real data, and no Material Planning document has ever set its `store_location` field — see §4.2 above for the related `get_sbb_available_qty` fix this ambiguity caused (Phase 1 HP-05).

---

## 17. Inspection Call / QC Workflow (Fitup Inspection & Final Inspection)

A QC sign-off workflow layered on top of Job Card and Supplier Operation Entry, scoped to exactly two routing checkpoints: **Fitup Inspection** and **Final Inspection**. Manufacturing logs the inspection call; a separate QC team records the result — matching the real-world split between the manufacturing team (fills quantities as usual, then requests a QC visit) and QC (reviews and signs off on its own page).

### 17.1 Inspection Tab on Job Card / Supplier Operation Entry
- New **Inspection** tab, visible only when `operation` is Fitup Inspection or Final Inspection (`depends_on` gated).
- **Inspection Status** (Open → Working → Completed): starts Open, flips to Working once the first call is logged, becomes Completed only once a round fully clears the checked quantity.
- **Inspection Call Date**: the entry point field the manufacturing team sets before logging a new call.
- **Inspection Call Log** (child table, read-only grid): one row per round — Round No, Inspection Call Date, linked Inspection Entry, Round Status (Pending/Completed), Rework Remarks (denormalized from the entry).

### 17.2 Buttons: Add Inspection Call / Create Inspection Entry
- **"Add Inspection Call"**: validates an Inspection Call Date is set, blocks logging a new round while one is already pending, appends a round, and auto-advances Inspection Status Open → Working.
- **"Create Inspection Entry"**: once a round is pending, creates a draft **Inspection Entry** — prefilled with Operation, Round No, Call Date, and denormalized Work Order/Subcontracting Order/Production Plan/Sales Order/Customer/Supplier traceability — and routes to it as a separate page for QC to fill in.

### 17.3 Inspection Entry (Custom Submittable Doctype)
QC fills in: **Status** (Ok/Not Ok), **Total Checked Qty**, **Cleared Qty**, **Rework Qty** (auto-computed), **Rework Remarks** (mandatory when Rework Qty > 0).

**Server-side rule**: Not Ok always implies Rework Qty > 0, and Ok always implies full clearance — `cleared_qty == total_checked_qty` with Status "Not Ok" is rejected, and partial clearance with Status "Ok" is rejected.

On submit, propagates back to the parent Job Card/SOE: marks that round's call-log row Completed, copies the rework remarks, and sets the parent's overall Inspection Status to **Completed** (fully cleared) or leaves it **Working** (rework remains — manufacturing logs a new call date and the cycle repeats).

### 17.4 Submission Gate
Job Card / Supplier Operation Entry submission is blocked for the Fitup Inspection / Final Inspection operations until Inspection Status is Completed — mirrors the existing "Status must be Completed" gate already used for the drawing-flow consumption fields.

### 17.5 Inspection Status Report
New Script Report showing **one row per inspection round** (full rework history, not just the latest): Production Plan, Sales Order, Customer, Reference Type + Reference (Work Order/Subcontracting Order), Active Doctype + Active Document (Job Card/SOE), Operation, Round No, Inspection Call Date, Inspection Status, Round Status, Total Checked Qty, Cleared Qty, Rework Qty, Rework Remarks. Filterable by Operation, Inspection Status, Production Plan, Sales Order.

### 17.6 Shared Logic Module
`production_management/inspection.py` holds all the logic shared identically by Job Card and SOE (`add_inspection_call`, `create_inspection_entry`, `on_submit_inspection_entry`, the before-submit gate, and `_resolve_traceability` — resolves Sales Order/Customer from the Job Card/SOE's own drawing-detail rows, falling back to the linked Work Order's Sales Order).

### 17.7 Roles
Inspection Entry create/write/submit access: System Manager, Manufacturing Manager, Manufacturing User, and **Quality Manager** (ERPNext's existing QC role — reused rather than creating a new one).

*Design note: ERPNext's standard Quality Inspection doctype was evaluated as an alternative and rejected — it has no accepted/rejected quantity tracking at all (purely parameter/reading-based), mandatory `item_code`/`sample_size` fields that don't map to this use case, only a single Quality Inspection Link per Job Card (no multi-round support), and no support for Supplier Operation Entry as a reference type without patching core ERPNext code.*

---

## 18. Security, Performance & Reliability Remediation (Phase 1 Audit Pass, 2026-07-16)

A ten-report internal audit (functional/BRD, architecture, bugs, performance, code quality, refactoring, dead code, security, testing, action plan) was run against this app and reorganized into a three-phase remediation plan (`PROJ001 CLAUDE FILES/PHASE_1_Critical.md`, `PHASE_2_Medium.md`, `PHASE_3_Low.md`). Most of Phase 1 (the Critical tier) has since been implemented, verified against the live site, and is summarized here. Every fix below was checked for behavior parity before/after (numeric output diffs, test-suite pass/fail signature comparisons via `git stash`, or both) — none of it changes what the app produces, only how fast/safely it gets there, except where explicitly noted as a bug fix.

### 18.1 Security
- **Removed a hardcoded production Administrator credential** from `pull_live.py` — now reads `MANUFYX_LIVE_URL`/`MANUFYX_LIVE_USER`/`MANUFYX_LIVE_PASS` from the environment and refuses to run if unset. **The credential was also found in this repo's git history** (already merged, and this repo has a live GitHub `upstream` remote) — rotating the live password and deciding whether to scrub history is an ops action outside what a code change can fix; not yet done as of this writing.
- **Duplicate-creation guard** added to `create_sco_from_production_plan` / `create_work_order_from_pp` (`subcontracting_management/subcontracting.py`) — a double-click or retry no longer creates a second Subcontracting Order / Work Order against the same Production Plan.
- **BOM-active check now runs at creation time** for the same two functions, instead of being silently skipped by the blanket `ignore_validate` flag used to insert the draft document.
- **Permission checks added** to whitelisted endpoints that previously trusted any authenticated caller:
  - Read: `get_batch_reservation_summary`, `get_batch_cross_table_usage` (`material_planning.py`), `get_mp_for_pr`, `get_pr_mp_allocations` (`purchase_receipt.py`) — now require Material Planning read permission.
  - Write: `reserve_batches`, `finalize_mapping`, `auto_purchase_from_mp` (`material_planning.py`), `create_sco_from_production_plan`, `create_work_order_from_pp`, `create_supplier_operation_entries` (`subcontracting.py`) — now require the relevant create/write permission.
- **Stored XSS fixed**: `drawing_management/doctype/drawing/drawing.js`'s Drawing Items summary table and `public/js/purchase_receipt.js`'s post-submit allocation popup now escape every interpolated Item/Batch/Material-Planning field via `frappe.utils.escape_html`, matching the pattern already used correctly in `batch.js`.

### 18.2 Performance
- **New shared formula module** `manufyxinvenzaerp/utils/dimension_formula.py` (`calculate_qty`, `calculate_sec_qty_from_qty`, `check_missing_fields`) replaces 8 independently-maintained copies of the Structurals/Plates/Nuts-and-Bolts formula across `material_request.py`, `purchase_order.py`, `purchase_receipt.py`, `supplier_quotation.py`, `sales_order.py`, `so_drawing_import.py`, `drawing_utils.py`, and the Drawing controller. Verified numerically identical to the previous per-file implementations across normal values and every edge case (missing dimensions, each item group, blank group).
- **New shared reference-copy module** `manufyxinvenzaerp/utils/reference_copy.py` (`copy_reference_fields_if_blank`, `fetch_fields`) replaces the near-identical copy-from-parent-transaction logic in `purchase_order.py`, `purchase_receipt.py`, and `request_for_quotation.py`.
- **Query batching** (the direct fix for "large document slow to save/submit"):
  - `get_raw_materials` (`material_planning.py`) — the per-row `custom_secondary_uom` Item lookup is now one batched query.
  - `check_stock_availability` (`material_planning.py`) — the whole stock-classification loop now reads from pre-fetched bulk lookups (new `get_sbb_batches_bulk` / `match_batches_by_dimension` in `production_plan.py`; new `_get_batch_reserved_by_others_bulk`, `_get_non_batch_stock_bulk`, `_get_non_batch_reserved_by_others_bulk` in `material_planning.py`) instead of issuing several queries per raw-material row.
  - `allocate_pr_stock_to_mp` (`purchase_receipt.py`) — the Purchase Order Item → Material Request Item → Material Request trace is now 3 batched queries total instead of up to 3 per PR line.
  - Added `search_index` to `item_code`, `batch`/`batch_no`, `is_reserved` on `Material Planning Material Mapping` and `Material Planning Available Raw Material` — confirmed present on the live DB after `bench migrate`.
- **Stock Entry submit-time weight refresh** — `refresh_weight_summary` (Material Issue Plan), `_refresh_wo_drawing_transferred_weights`, and `_refresh_sco_drawing_transferred_weights` (`subcontracting.py`) now set `flags.ignore_links = True` before saving, skipping Frappe's redundant Link-field re-validation on child-table rows the function never touches (none of these narrow numeric-field updates change any Link field's value). Also added `_get_mp_drawing_weights_by_duno`, a batched per-Material-Planning replacement for the old per-drawing-row `_get_mp_drawing_weight` call, now used by `refresh_weight_summary` and both SCO/WO creation functions. Measured on a real 98-row Stock Entry: the two custom submit hooks dropped from ~1.1s to ~0.56s; full end-to-end submission (including ERPNext core's own processing, which this app's code doesn't control) on a comparable 100-row entry was ~13.3s — most of the remaining time sits outside this app's own hooks and hasn't been profiled yet.
- **CI/CD test gate**: `.github/workflows/main.yml` now runs a `test` job (fresh site, full `bench run-tests`) that the `deploy` job depends on — previously the pipeline had no test-execution step at all before pushing to production.

### 18.3 Bug fixes
- **`store_location`/`storage_location` fieldname mismatch, confirmed live**: `get_sbb_available_qty` (and the new `get_sbb_batches_bulk`) filtered Stock Ledger Entry on a `store_location` column that has never existed — confirmed via `DESCRIBE` and a direct call that reproduced `OperationalError: Unknown column 'tabStock Ledger Entry.store_location'`. Fixed to query the column that actually exists, `storage_location`. Also discovered: `Store Location` (the doctype this filter was meant to key off) has **zero records** in this site's data and no Material Planning document has ever set it — this code path had essentially never been exercised.
- **Purchase Receipt submission was crashing on every submit**: `on_submit_purchase_receipt` had a wrong import path for `refresh_mip_raw_materials` (`...subcontracting_management.material_issue_plan` instead of `...subcontracting_management.doctype.material_issue_plan.material_issue_plan`), raising `ModuleNotFoundError` unconditionally, outside any try/except. Fixed and confirmed live (PR-26-00008 submitted successfully afterward, with correct Material Planning allocation across all 100 line items).
- **Silent failures now surfaced to the user**: `on_submit_purchase_receipt`'s Material Planning allocation and `_refresh_linked_mip_weight` (`stock_entry.py`) now show an orange `msgprint` when they fail, in addition to the existing `frappe.log_error` — previously a failure here was invisible until someone noticed stale data much later.
- **Stray script no longer breaks test discovery**: `production_management/test_release.py` (a one-off manual debug script, not a real test, but named so `bench run-tests` tried to import it as one and crashed before any real test could run) renamed to `manual_release_check.py`.

### 18.4 New feature — Material Issue Plan warehouse fields filtered by Company
`source_warehouse`, `supplier_warehouse`, `cnc_warehouse`, `excess_return_warehouse` on Material Issue Plan (`subcontracting_management/doctype/material_issue_plan/material_issue_plan.js`) now filter to the document's own Company via `frm.set_query`, matching the same pattern already used for `subcontracting_order`/`work_order` in this file. Previously showed every warehouse across every company in the system (62 across 10 companies on this site); now shows only the ~7 belonging to the document's own company.

### 18.5 Not yet done (flagged, not silently dropped)
- Rotating the leaked production credential and deciding on a git-history scrub (§18.1) — ops action, not a code change.
- Profiling the *rest* of Stock Entry submission time beyond this app's own two custom hooks (ERPNext core's own Stock Ledger/GL/valuation/Serial-and-Batch-Bundle processing) — the current fix only addresses this app's own custom-code overhead.
- The remaining Phase 1 items requiring business sign-off (Drawing's "All"-role grant, the RFQ/Sales Order missing-dimension gate) or a dedicated design/regression-suite effort first (the batch-matching heuristic redesign, the `bom_class_override.py` fork reduction) — see `PROJ001 CLAUDE FILES/PHASE_1_Critical.md` for the full detail on each.

---

## 19. Custom Field / Property Setter: fixtures → per-doctype custom/*.json (2026-08-18)

`hooks.py`'s `fixtures = ["Custom Field", "Property Setter"]` (unfiltered — exported every record of
those two doctypes site-wide, not just this app's own) replaced with the standard Frappe "Export
Customizations" mechanism: one `<module>/custom/<doctype>.json` file per doctype, each with
`sync_on_migrate: 1`, synced automatically by `frappe.modules.utils.sync_customizations()` on every
`bench migrate` — the exact function Customize Form's own "Export Customizations" button calls, not
a reimplementation. See README's "Custom Fields & Property Setters" section for the mechanism and
regeneration command.

**Scope carried over 1:1, on purpose**: the old fixtures files spanned **112 doctypes**, not just the
~20 this app's own docs describe touching — GST India fields on `GL Entry`/`Journal Entry`, HR fields
on `Employee`/`Salary Slip`/`Timesheet`, and assorted core doctypes (`Task`, `Communication`, `Asset`,
`Putaway Rule`, `Address`, etc.) that happen to carry Custom Field/Property Setter records in this
site's DB but were never created by this app's own code. Per explicit instruction, these were moved
1:1 rather than dropped, so current behavior is unchanged — they now live under a catch-all
`manufyxinvenzaerp/custom/` folder (80 of the 112 files), separate from the ~32 files filed under this
app's own thematic modules (`drawing_management/custom/`, `production_management/custom/`,
`subcontracting_management/custom/`, `accounts_management/custom/`).

**Verified**: live doctype list pulled fresh from `manufact`'s DB (not from the old, possibly-stale
fixture files) — 848 Custom Field + 337 Property Setter records, matching exactly before and after a
real `bench --site manufact migrate` run, which synced all 112 files cleanly with no errors.

**Key files touched**: `hooks.py` (fixtures line removed), new `*/custom/*.json` (112 files across 5
modules), `fixtures/custom_field.json` + `fixtures/property_setter.json` deleted, one-off migration
script kept at `tests/move_fixtures_to_custom_json.py`.

---

## 20. Batch reassignment from Consolidate Items (2026-09-11)

Material Issue Plan's **Raw Materials** grid has long had an *Update Batch* action that
moves one Material Planning row to a different batch. This adds the same action to the
**Consolidate Items** grid, where a line is not a row but a *merge* of N rows pointing
at N Material Planning child rows, possibly across several plans. Reassigning one line
reassigns all of them.

What makes that workable is **Reserve stock without dimensions**: a row in that mode
reserves exactly its required Kg and expresses the piece count as a fraction, so
per-row dimension matching disappears and only one number has to reconcile - total Kg.
A line needing 1,000 Kg across 50 rows can move to a new batch whatever mixture of
dimension-matched and dimensionless rows it started as.

### 20.1 Reserve stock without dimensions, on Exact Match

The waiver existed only on Material Mapping. It is now on **Material Planning Available
Raw Material** too, which fixes the per-row *Update Batch* dialog for exact-match rows:
the dialog always sent the checkbox and the server silently dropped it.

It does **less** here, deliberately. An exact-match row already reserves its Allocated
Qty in Kg verbatim - `reserve_exact_match_batches` does no dimension arithmetic at all -
so that figure is untouched. The waiver's only effect is Sec Qty (NOS), which stops
being a whole-piece allocation and becomes the reserved weight expressed as a fraction
of one piece of the assigned batch. **Allocated Qty in Batch is never rewritten**: it is
this row's share of a requirement that may have been split across several batches.

The flag is set automatically when a batch is reassigned from the Material Issue Plan,
and can be ticked by hand during planning. It is edited in the expanded row (like
Material Mapping's), not as a grid column. Reserved rows cannot be toggled, and it
applies to Structurals and Plates only.

### 20.2 The Update Batch dialog on Consolidate Items

**This is the only place a batch is reassigned on a Material Issue Plan.** Since
14 Sep 2026 the Raw Materials grid's toolbar *Update Batch* is no longer added and its
per-row button is hidden (both kept in code, so they can come back). Consolidate Items
has the button on **every row** — opening the dialog straight onto that line — as well
as above the grid.

The grid is read-only, and Frappe only renders a Button field on a row it can edit, so
the row button is drawn by a cell formatter and its click is caught before the row's
own click handler. A line with anything already transferred shows *Transferred*
instead of a button.

Three steps, because applying cannot be undone in one action:

1. **Preview.** Name one or more target batches and a **piece count** for each.
   Length and Width are shown for reference but are the batch's own size and **cannot
   be edited** — nothing typed there was ever saved or transferred, so they were
   removed as inputs (the server ignores them too). The dialog shows each batch's
   **Weight** (pieces × the batch's piece weight) against its **Total available
   Weight**, then reports what would happen: rows and Kg, every Material Planning
   involved, and **which row lands on which batch**.
2. **Reassign Batch**, available only after a clean preview, opens **Confirm Batch
   Reassignment**: every row with its Material Planning, **current batch, whether it is
   reserved and how many Kg it holds**, and the new batch and Kg it will get. It spells
   out what Yes does — the existing reservations are unreserved, every row is assigned
   to the new batch, and every row is reserved again.
3. **Yes, Unreserve and Reassign** applies it. The result reads *"Unreserved N row(s)
   from OLD and reserved them on NEW (X Kg)."* Any edit before confirming drops back to
   Preview, and the server independently refuses a plan whose figures changed since.

In the result table, **Weight** is what the batch was allowed to give, **Total Batch
Weight** is its free stock (total less every plan's reservations), and **Excess** is
the part of that Weight this line did not use — not material returned.

Only batches with free stock in the plan's source warehouse are offered - a zero-stock
batch is the one case downstream validation does not catch.

### 20.3 Splitting one line across several batches

Rows fill the first batch in table order until its capacity is used, then move to the
next. **A row is never split across two batches**, and once the fill passes a batch it
never comes back to it - the only order an operator can predict by reading the grid top
to bottom. A row too big for what is left closes that batch, and the capacity left
stranded is reported rather than hidden, naming the row that closed it.

If the batches entered cannot cover the whole line, the reassignment is **refused**
rather than partly applied.

Each batch is priced at its **own recorded size**. (Until 14 Sep 2026 a cut size could
be typed here; it steered the split but was never saved, so the Stock Entry carried the
batch's real size regardless. The inputs were made read-only for that reason.)

### 20.4 Nuts and Bolts

No waiver - a bolt's weight is exact and a fractional bolt means nothing. The piece
count is computed explicitly instead, and a count that does not come out whole is
reported rather than rounded, because rounding would change the line's total weight.

### 20.5 What happens when something goes wrong

Everything that can be refused is refused **before** the first write: a line with
anything already transferred, rows holding material claimed from another plan's excess
or from a Cut Sheet, plans the user cannot write to, plans using different warehouses,
a batch already in the other table, a batch with no free stock, and any shortfall.
Uninspected batches and a parked transfer draft raise warnings rather than blocks.

Plans are then written **one at a time**. If one fails, the message names exactly what
was applied, where it stopped and what was untouched. The stopped plan's rows are
released from reservation but **still carry their original batch** - nothing is lost,
and re-running recovers, because members are re-derived from current state each time so
rows that already moved are no longer part of the line.

**A reassign clears that line's unfinished "Select Materials to Transfer" entries**
(the ones parked with *Save and Close*), since they are keyed on the batch. No stock
has moved when this happens. The dialog warns: *"This line has unfinished entries saved
from "Select Materials to Transfer" on … (not yet transferred). Changing the batch
clears them — you will need to re-enter them in the transfer popup."*

### 20.5a Excess after a reassignment

A reassigned row reserves exactly its required Kg, so its planned excess becomes zero.
The excess appears at **transfer**, when fractional Sec Nos are rounded up to whole
pieces: the server books *Kg sent − Kg planned* for each item + batch line, and prices a
piece at the **new batch's own** dimensions. That is the same figure the dialog's
**Excess** column shows. On a split, each batch is booked separately.

**No batch change once stock has moved (14 Sep 2026).** Once any Stock Entry exists
against a Material Issue Plan, no batch on it can be reassigned. That covers a
transfer, a CNC leg, an excess return, process loss or the final entry, and **drafts
count too**. A reassignment ends by rebuilding the Raw Materials table, and that table
must not be rebuilt under documents already created from it. Every Update Batch entry
point checks first and shows *"The batch cannot be reassigned. These actions have
already been performed on MIP-…: [entries]. Because of this the Raw Materials table
cannot be refreshed, so the batch cannot be changed."* The server refuses the same case
on preview, on apply, and on the per-row reassignment when called from the plan.
Material Planning's own grid is not affected.

This rule is wider than the Refresh Raw Materials button's older one, which only counts
submitted entries tagged to the SCO or Work Order.

Two gaps were closed on 14 Sep 2026:

- **"Reused by" pointer on excess-return batches.** When a batch that came from an
  earlier excess return is reserved into a plan, its SCO Excess Material Item records
  which row took it. Moving that row to another batch used to leave the pointer behind,
  so the source plan still showed the off-cut as reused. It is now re-pointed to another
  row still holding the batch, or cleared (`_resync_excess_item_mapping`), for both the
  Consolidate Items and the per-row reassignment.
- **Round-up excess on already-transferred rows.** Every rebuild of Raw Materials, which
  every batch update ends with, used to blank `transfer_excess_kg` on rows transferred
  earlier. Excess Material Items was never affected. The figure is now carried across
  the rebuild while the row keeps the same batch. Checked against the Decision Log's
  "Round Up at Transfer" entries: no plan on the site had lost this figure.

### 20.6 Verified

Against restored live data: a 3-row / 217.344 Kg line moved to another batch and back
with every row returning byte-identical; Sec Nos correctly re-derived against a piece
2.8x larger; the same line split across two batches with 32.903 Kg correctly reported
as stranded; and the whole dialog driven end to end in a browser.

**Key files**: `subcontracting_management/material_issue_plan_batch_update.py` (new),
`material_planning.py` (`_apply_batch_to_arm_row`, `_sec_nos_for_weight_arm`, the
exact-match waiver loop), `material_planning_available_raw_material.json` (new field),
`material_issue_plan.js` (the dialog), `material_planning.js` (the row handler).
Tests: `verify_consolidate_batch_reassign.py`, `verify_arm_reserve_without_dimensions.py`,
`verify_consolidate_batch_apply.py`.

---

## 21. Transfer popup: piece weight and stock available to the plan (2026-09-14)

Reported on MIP-2026-00005. Raising PLATE16 from 0.48 Nos to 1 whole piece was refused
with *"has only 2260.8 Kg free … 1.0 Nos needs 2262.108 Kg"*, on a batch holding exactly
one 2,260.8 Kg plate.

### 21.1 What one piece weighs

The popup worked out a piece as *planned Kg ÷ planned Sec Nos*. Sec Nos is stored to 3
decimals, so for a small fraction that division is wrong: 1,085.812 ÷ 0.480 = 2,262.108
Kg, where the plate weighs 2,260.8. On PLATE12 (6.264 Kg = 0.004433 Nos, stored 0.004)
it priced one piece at **1,566 Kg against a real 1,413**. Rounding up would have shipped
153 Kg too much and booked 153 Kg of excess that never existed. A transfer to the
supplier does not recalculate weight from dimensions, so the wrong figure would have
moved as it was.

A piece is now priced from the line's **own dimensions** (L × W × T × unit weight), the
same formula used everywhere else. They are only trusted when they **agree with the
plan**, meaning the stored Sec Nos is exactly what the planned Kg rounds to at that
piece weight. A line whose dimensions describe something else (a Cut Sheet row, whose
piece is the cut W1, or inconsistent data) keeps the old plan-based figure, so this is
never worse than before. Leaving Sec Nos at the plan still sends the exact planned Kg,
and lowering it can never ask for more than the plan.

The final check at **Verify and Transfer** recalculates the Kg on the server from Sec
Nos × piece weight and ignores the figure sent from the browser. The CNC → Supplier leg
does the same, and there it can only lower a line against what is actually at CNC.

### 21.2 How much of a batch this plan may take

This used to be physical stock only. That correctly included the plan's own
reservation, but it ignored stock reserved by **other drawings or plans**, including
other DUNOs of a shared Material Planning. Now:

> **Available for this plan = stock in the warehouse − what other rows still hold reserved.**

Reservations in a different warehouse, and rows already released by their own transfer,
are not counted. The popup's **In Stock** column still shows physical stock, with a note
such as *"1,965.876 reserved for other drawings or plans"* under it.

Rows elsewhere that are **assigned but not reserved** to the same batch do not reduce
what is available. Taking the stock they were planned against raises a non-blocking
**Stock Also Planned Elsewhere** warning that names them.

### 21.3 The message

> **Not enough stock in batch PLT8-T8-L1250-W12000-R010** (Stores - MIPL)
> You asked for **3 Nos × 942 Kg per piece = 2826 Kg**
> Planned for this line: 1965.876 Kg · In stock: 4710 Kg
> Reserved for other drawings or plans: 1965.876 Kg — *each row, with its DUNO*
> Available for this plan: **2744.124 Kg** · **Short by: 81.876 Kg**
> The most this batch can give is **2 whole piece(s)** (1884 Kg), or up to 2744.124 Kg as a fraction.

### 21.4 The same warning when reassigning a batch

A Consolidate Items reassignment used to check only **reserved** stock, so it could move
a line onto a batch that other rows had assigned but not reserved. That Material
Planning then refused to save. This is how MP-2026-00015 got stuck on 14 Sep 2026: PLATE16 on
MIP-2026-00005 was moved onto the one-piece PLT16-T16-L12000-W1500-R008, which two
unreserved MP-2026-00015 rows (TYPE 1 and TYPE 2) were planned against. The preview and
the confirmation now warn and name those rows. It is a warning, not a block: free stock
is still decided by reservations.

**Key files**: `material_issue_plan_transfer.py` (`_line_kg_per_piece`, `_qty_for_sec`,
`_batch_availability_for_plan`, `_shortage_message`, `update_transfer_sec_qty`,
`_validate_selected_against_stock`, `create_mip_cnc_partial_forward`),
`material_issue_plan.js` (transfer popup). Test: `verify_transfer_piece_weight.py`.

---

## 22. Finished goods in Kg and Nos, per drawing batch (2026-09-19)

Plan: `.claude/tasks/sep14_fg_uom_plan.md` (decisions D1–D31, readings R1–R5). Built in
four waves: e2951ab (fields, hooks, stubs), 315d838 (masters, Sales Order, production
chain, FG batches, invoicing), 086180e (Delivery Note and returns), and wave 3 (manual,
this section, end-to-end test).

**The rule.** Finished goods move in **Kg** everywhere (stock UOM Kg), and every FG row
also carries its piece count as **Sec Qty in Nos**, per drawing. There is exactly one
batch per drawing, `FG-<Sales Order>-<DUNO>`, holding both, so Kg per piece is always
batch Kg ÷ batch Nos. An *FG row* is a row whose item has `custom_parent_item_group =
"Finished Goods"` — always tested with `fg_stock.is_fg_item()`; the Kg/Nos logic applies
to FG items that are also batch-tracked (`fg_stock._is_batch_fg_item`).

Rules that hold everywhere:

- **3 decimals** for every Kg figure and comparison (`flt(x, 3)`), no other tolerance
  (D14). Money 2 dp.
- **Last-piece rule:** when the Nos asked for is everything that remains (in a batch in
  a warehouse, pending on an SO line, unbilled on an SO line or DN row, still out on a
  DN row being returned), the Kg is the exact Kg remaining, never Nos × Kg per piece.
  Pricing divides the *unrounded* ratio (`fg_stock._price_nos`).
- **Nos are recounted, never incremented.** Batch Nos, SO Delivered (Nos), SO / DN
  Billed (Nos) are re-summed from submitted rows on every submit and cancel, so the
  order of notes, returns, credit notes and cancels cannot leave them wrong.
- **Customer weight is two figures (D2):** Cust Weight (per Nos) and Cust Weight
  (Total) = per Nos × drawing Nos. "Total" is what travels downstream everywhere (D30).
  `Drawing.total_weight` and the SO raw-material `total_weight` are the calculated RM
  weight and were not touched.

### 22.1 Where it lives

| Stage | Code | What it does |
|---|---|---|
| Item | `item_management/item.py:validate_fg_configuration`, `validate_batch_prefix_not_fg` | New FG item: stock UOM Kg, Sec UOM Nos, Has Batch No on, Create New Batch forced off, no batch prefix; items with transactions only get an orange note. A raw-material batch prefix may not be `FG`. |
| Upload sheet | `drawing_management/so_drawing_import.py:download_bom_template`, `_parse_excel`, `parse_bom_excel` | Columns *Cust Weight (per Nos)* and *Cust Weight (Total)*; old headers *Weight per Pcs (KG)* / *Total Weight (KG)* still read. `weight_per_pcs` staged on the Drawing List row. |
| Verify | `so_drawing_import.py:_check_fg_weights` (inside `verify_raw_materials`) | Blocking: per Nos and Total present, per Nos × Nos = Total; FG item on the SO items table (D4); per FG line Σ Total = line Kg and Σ Nos = line Qty (Nos). Uses `sales_order.fg_line_totals` / `fg_line_mismatch_text`. |
| Create Drawing | `so_drawing_import.py:create_drawings_from_import` | Refuses on the first batch unless `custom_raw_materials_verified` (D25); writes `customer_provided_wt` = Total and `weight_per_pcs`. |
| Sales Order | `drawing_management/sales_order.py:validate_fg_lines` (from `recalculate_raw_material_qty`), `lock_drawn_rows` (also `before_update_after_submit`), `clear_verified_on_fg_change`, `warn_fg_line_totals` | Drawn Drawing List rows locked (D24); FG line Kg/Nos/item or pending-row weight change clears Verify; orange mismatch warning on save. SO client script `_so_fg_pending_nos_dn_btn` (setup.py `SO_CLIENT_SCRIPT`) adds **Create > Delivery Note (pending Nos)** when `per_delivered` ≥ 100 but Nos are pending. |
| Drawing | `drawing/drawing.py` validate; `drawing_utils.py:update_customer_provided_weight`, `_cascade_customer_weight`, `_recompute_draft_jwo_job_work`, `_so_line_differences` | Total = per Nos × Nos. Update Customer Weight takes the per-Nos figure (D15), writes Drawing + SO row, cascades the Total (per Nos alongside) to PP items, SCO / MIP drawing rows, SOE Drawing Detail and BOM; draft JWOs recompute rate and amount, submitted ones are listed (R5). |
| BOM | `drawing_utils.py:create_bom_from_drawing` | `quantity` = Cust Weight (Total) in Kg; `custom_sec_qty` = drawing Nos; both Cust Weight fields (D12). Material Planning scales against the BOM's Qty (Nos) (`material_planning.py:get_bom_info`). |
| Production Plan | `production_plan_management/production_plan.py:apply_fg_nos` (validate, last), `fg_kg_for_nos`, `drawing_fg_weights`, `fg_nos_planned_elsewhere`, `fg_nos_remaining`, `_mark_fg_nos_left` | The only place `planned_qty` of a drawing row is calculated: Total × Nos ÷ drawing Nos (D5, D26). Σ Nos on non-cancelled PPs ≤ drawing Nos, refusal names the other plans (D16). Entry points set only `custom_sec_qty`: picker (remaining Nos, drawings with 0 left hidden), `drawing_utils.create_production_plan_from_bom`, `material_planning.make_production_plan`. |
| Job Work Order | `subcontracting_management/subcontracting.py:create_sco_from_production_plan`, `_job_work_figures` | Item qty = Σ PP Kg, `custom_sec_qty` = Σ Nos; drawing rows carry Nos, both Cust Weights, `rate_per_kg` (Drawing `rs_rate_per_kg`) and `job_work_amount` = Kg × rate; item rate = Σ amount ÷ Σ Kg (R3). MIP drawing rows take the PP Nos (`material_issue_plan.py:populate_from_production_plan`). |
| FG batch | `production_management/fg_stock.py:get_or_create_fg_batch`, `refresh_fg_batch`, `fg_batch_nos_by_warehouse`, `fg_batch_available`, `kg_for_nos`, `planned_kg_per_nos` | Batch `FG-<SO>-<DUNO>` (drawing name if DUNO blank or taken), explicit insert with the Batch "FG Details" fields; Nos per warehouse = Sec Qty in − out over submitted SE and DN rows (bundle-aware); Kg per warehouse from submitted Serial and Batch Entries; `custom_weight_per_piece` = batch Kg ÷ Nos. |
| Final Stock Entry | `subcontracting.py:create_finished_goods_entry`, `_final_fg_rows`, `_fg_already_booked`, `get_final_stock_entry_preview` | One FG row per drawing ready to book: Kg = Nos × per Nos, Sec Qty Nos, drawing batch with `use_serial_batch_fields`. Already-booked counts Sec Qty (qty for old entries). |
| Stock Entry | `fg_stock.py:validate_fg_stock_entry_rows` (validate), `on_fg_stock_entry_change` (on_submit / on_cancel); `public/js/stock_entry_fg.js` | Batch mandatory. Manufacture: whole Nos; Edit FG Stock Kg off → Kg reset to planned; on → typed Kg kept, warning above the % setting. Transfer / Issue: whole Nos ≤ available in the source warehouse, Kg = `kg_for_nos` (read-only). Receipt: existing batch, Nos, typed Kg. Batch refreshed on submit/cancel; first Manufacture entry becomes the batch reference. |
| Stock Reconciliation | `stock_management/stock_reconciliation.py:block_stock_reconciliation` (validate); `public/js/stock_reconciliation.js` | Always refused, every purpose (D21). Item `opening_stock` hidden (property setter in `setup.py`). |
| Delivery Note | `selling_management/mapping.py:make_delivery_note` (override), `_add_fg_lines_skipped_by_kg`; `selling_management/delivery_note.py:compute_fg_rows`, `validate_delivery_note`, `on_submit_delivery_note`, `on_cancel_delivery_note`, `get_fg_batches`, `get_fg_rows_kg`; `public/js/delivery_note.js` | SO → DN maps FG lines with pending Nos and no batch, including lines ERPNext skips because the Kg is used up. Get FG Batches: one row per batch of the row's SO with stock in the warehouse, linked by `against_sales_order` / `so_detail` (D28, D29). Validate: batch of the row's SO, whole Nos, ≤ batch in the warehouse, Σ per SO line ≤ pending (R4), Kg from the batch. Returns: from the DN (`dn_detail`), same batch, Kg = −Nos × the original row's Kg per Nos, ≤ still out. Submit/cancel recount `custom_delivered_sec_qty` and refresh the batch. |
| Sales Invoice | `mapping.py:make_sales_invoice_from_so`, `make_sales_invoice_from_dn`, `_apply_fg_nos_to_invoice` (overrides); `selling_management/sales_invoice.py:compute_fg_rows`, `validate_sales_invoice`, `on_submit_sales_invoice`, `on_cancel_sales_invoice`, `get_fg_row_kg`; `public/js/sales_invoice.js` | From SO: Kg per Nos = SO line Kg ÷ Nos; from DN: the DN row's own Kg ÷ Nos, net of returns (R2). Whole Nos ≤ unbilled; FG row must come from an SO or DN; Update Stock refused with any FG line (D23). `custom_billed_sec_qty` re-summed on SO line and DN row; credit notes reduce it; debit notes left as typed. |
| Production Report | `production_management/report/production_report/production_report.py:_base_row`, `_job_work_pricing`, `_total_row` | Rate / Kg and Job Work Amount per drawing row, from the SCO Drawing Item when set, else Cust Weight (Total) × the drawing's rate; summed in the total row. Column relabelled Cust Weight (Total). |

### 22.2 Fields and settings

All added in wave 0 (definitions in `setup.py` and `manufyxinvenzaerp/custom/<doctype>.json`;
own doctypes in their JSON). Full list: plan §4.1. The ones to know:

- **Sales Order Item:** `custom_sec_qty` "Qty (Nos)" (typed, in list view), `custom_sec_uom`,
  `custom_delivered_sec_qty`, `custom_billed_sec_qty` (read-only, no_copy).
- **Sales Order DUNO Item:** `weight_per_pcs` "Cust Weight (per Nos)"; `total_weight` relabelled
  "Cust Weight (Total)".
- **Drawing:** `weight_per_pcs` (read-only); `customer_provided_wt` relabelled "Cust Weight (Total)".
- **BOM / Production Plan Item / Subcontracting Order Item:** `custom_sec_qty`, `custom_sec_uom`,
  Cust Weight per Nos / Total; PP `planned_qty` labelled "Planned Qty (Kg)", read-only on drawing rows.
- **SCO Drawing Item:** `cust_weight_per_nos`, `rate_per_kg`, `job_work_amount`.
- **Batch ("FG Details"):** `custom_sales_order`, `custom_customer`, `custom_drawing`,
  `custom_duno_mark_no`, `custom_customer_drawing_number`, `custom_job_work_order`,
  `custom_cust_weight_per_nos` "Planned Kg per Nos", `custom_weight_per_piece` "Actual Kg per Nos".
- **Delivery Note Item / Sales Invoice Item:** `custom_drawing`, `custom_duno_mark_no`,
  `custom_sec_qty` (in list view), `custom_sec_uom`, `custom_billed_sec_qty` (DN); `qty` is
  read-only when `custom_sec_uom` is set (property setter), so non-FG rows have their Sec UOM
  cleared by the hooks.
- **Manufyxinvenza Settings:** `edit_fg_stock_kg` "Edit FG Stock Kg" (default 1) and
  `fg_weight_difference_warning_percent` "FG Weight Difference Warning (%)" (default 5), read
  through `fg_stock.edit_fg_stock_kg_enabled()` / `fg_weight_difference_warning_percent()`,
  which fall back to the defaults when the single was never stored
  (`setup.set_fg_settings_defaults` writes them on migrate).

### 22.3 Hooks and overrides (hooks.py)

- `doc_events`: Stock Entry validate `fg_stock.validate_fg_stock_entry_rows`, on_submit /
  on_cancel `fg_stock.on_fg_stock_entry_change`; Stock Reconciliation validate
  `block_stock_reconciliation`; Delivery Note and Sales Invoice validate / on_submit /
  on_cancel; Production Plan validate `apply_fg_nos` (last in the list); Sales Order
  `before_update_after_submit` `lock_drawn_rows`.
- `override_whitelisted_methods`: ERPNext's `sales_order.make_delivery_note`,
  `sales_order.make_sales_invoice` and `delivery_note.make_sales_invoice` → the three
  functions in `selling_management/mapping.py`. Each calls the ERPNext original and
  post-processes the FG rows, keeping the original signature.
- `doctype_js`: `delivery_note.js`, `sales_invoice.js`, `stock_reconciliation.js`,
  `stock_entry_fg.js`.

### 22.3a Planning rows: Nos with its UOM, and the Kg beside it (2026-09-20)

Material Planning's Selected BOMs rows showed Qty to Manufacture (the drawing's piece
count) beside the finished-goods item's stock UOM, so 2 pieces read "2 Kg". Every
planning row now carries the pair:

| Row | Nos | Kg |
|---|---|---|
| Material Planning BOM Item | `qty_to_manufacture` "Qty to Manufacture (Nos)", `uom` = Nos | `qty_to_manufacture_kg` = drawing Cust Weight (Total) x Nos / drawing Nos |
| Production Plan Item | `custom_sec_qty` | `planned_qty` (unchanged) |
| SCO Drawing Item (Job Work Order, Material Issue Plan) | `qty_to_manufacture` "Qty to Manufacture (Nos)" | `qty_to_manufacture_kg` = the plan's Planned Qty (Kg) |

- `production_plan.drawing_kg_for_nos(drawing, nos, cache)` is the one Kg helper; it
  returns 0 for a drawing without a Cust Weight (per Nos), whose "Total" is one piece.
- Filled by `material_planning.get_bom_info` (and its JS), kept in step on every save by
  `_update_bom_item_weights`, by the Job Work Order builder and
  `populate_from_production_plan`, and by `_recompute_draft_jwo_job_work` after a
  customer-weight change.
- Patch `v1.fg_nos_kg_on_drawing_rows` corrected existing rows; test
  `verify_fg_planning_nos_kg` (13 checks).

### 22.4 Known limits

- **Fabricated Structurs is not batch-enabled yet.** It is the live FG item, but 100 Kg of it
  sits unbatched from MAT-STE-00012 / MAT-STE-00014, so switching Has Batch No on is the
  user's decision. Until then it behaves the old way (no batch, no Nos tracking on SE / DN).
- **Old data is skipped (D13):** orders, drawings, BOMs, plans and Job Work Orders from before
  the change, and FINGOODS001 (Nos, no batch), are not migrated.
- **Untested paths:** Pick List → Delivery Note, and a Delivery Note return into a different
  warehouse from the one delivered from.
- **Over-delivery / over-billing (D10):** ERPNext's allowance is 0%, so a delivery or invoice
  whose Kg exceeds the ordered Kg (heavier pieces) is refused until the client sets a
  tolerance. The Nos are always capped by the app (R4); the Kg limit is ERPNext's alone.
- **Mixed invoicing basis:** billing part of a line from a DN (actual Kg per Nos) and the rest
  from the SO (ordered Kg per Nos) makes the last SO-based pieces absorb the difference, by
  the last-piece rule (in the worked example: 7 Nos left after DN 1 = 208.5 Kg, not 210).
- **Orphan bundle:** a batch picked through ERPNext's batch selector (rather than the batch
  field / Get FG Batches) leaves an orphan draft Serial and Batch Bundle behind.
- **Print formats:** custom formats, not changed here (D18). Order status logic unchanged (D9).

### 22.5 Verified

`tests/verify_fg_end_to_end.py` runs the plan's §6 example through every document in one
rolled-back transaction (every document named `ZZFG-A8-`; a naming guard refuses every
naming-series counter for the run and `tabSeries` is compared before and after). Shortcuts,
documented in the test: the last operation's finished pieces are written onto its SOE Drawing
Detail, and the job's material reaches the supplier warehouse as a ZZFG- consumable (Material
Receipt + Material Transfer tagged `custom_sco_ref`) instead of through Material Planning.
Per-package tests: `verify_fg_schema`, `verify_fg_masters`, `verify_fg_sales_order`,
`verify_fg_bom_pp_kg`, `verify_fg_final_stock_entry`, `verify_fg_stock_movements`,
`verify_fg_delivery_note`, `verify_fg_sales_invoice`, `verify_production_report`. Four older
tests commit real documents and are kept out of regression runs: `verify_pp_naming`,
`verify_internal_job_sco`, `verify_mixed_sco_regression`,
`verify_create_operation_and_inspection_gate`.

**Manual:** ERP Manual → *Finished Goods — Kg and Nos* (`erp_manual.js`
`ERP_MANUAL_FINISHED_GOODS_CHILDREN`).

---

*This document covers all major features implemented in the custom app. Minor utility helpers, internal validation guards, and test scaffolding are not listed.*

---

## 23. Check Stock Availability: rounding dust is not free stock (2026-09-20)

A batch shared across several requirements can be left with a crumb of Kg once its
pieces are all spoken for. Requirement rows carry more decimals than they show, so three
~530.80395 Kg rows on a 3-piece 1,592.413 Kg bar leave 0.00115 Kg -- just above the old
0.001 Kg floor. Check Stock Availability handed that crumb to the next drawing
(MP-2026-00129, 1B8): a 0.001 Kg / 0 Nos Exact Match row, with the rest of the drawing
short by 530.803 Kg instead of one whole piece.

- `material_planning._batch_has_free_stock(remaining_kg, batch_total_kg, batch_total_sec)`:
  free only above `BATCH_FREE_EPSILON` Kg **and**, for a batch that counts its pieces,
  worth at least 0.001 Nos. A genuine part-piece (Reserve Without Dimensions) is still
  offered.
- Used at all three places that pick free batches: `check_stock_availability`,
  `move_to_exact_match`, `update_exact_match_from_consolidate`.
- Test `verify_mp_batch_dust` (17 checks) replays MP-2026-00129 through the real
  `check_stock_availability`, with and without the new bar, and shows the old Kg-only
  rule reproducing the live 0.001 Kg / 0 Nos row. `verify_no_zero_qty_exact_match`
  now checks the three sites use the helper.
- Existing plans are not changed. MP-2026-00129 still has its row 7 (0.001 Kg on R005,
  reserved) and row 8 (530.803 Kg on R037, not reserved).

---

## 24. Material Planning: stock after a purchase (2026-09-20)

Plan: `.claude/tasks/sep20_mp_stock_matching.md`. On MP-2026-00129, a receipt's stock was
reserved, then unreserved, and a re-check sent 76 requirements back to purchase.

1. **Re-check matches received stock first.** `_pending_purchase_items(mp)` replaces
   `_ordered_item_codes` in `check_stock_availability`. An item counts only while its
   Material Request line has `received_qty < stock_qty`. A requirement is matched to
   stock like any other; its protected Unavailable row is kept only for the part stock
   can't cover (`_keep_protected`, qty and Nos scaled), or dropped when covered.
2. **Check stock without dimensions** (`Material Planning.check_stock_without_dimensions`):
   - Plates / Structurals (`DIMENSIONLESS_GROUPS`): any batch of the same item, own size
     first, then largest free.
   - Rows via `_dimensionless_arm_fields`: the batch's dimensions,
     `reserve_without_dimensions = 1`, and `sec_qty` = Kg / the batch piece.
   - A shortfall row's Nos is proportional to the drawing's own pieces.
   - Reserved Exact Match / Material Mapping rows are kept: covered by
     `_coverage_key` (item, DUNO, item no), their batches' Kg is not offered again, and a
     batch held in Material Mapping is not offered to Exact Match.
   - Returns `kept_reserved`; the form keeps reserved rows in place (`_mp_clear_unreserved`),
     because the Material Issue Plan's `source_row` points at them by name. The re-check
     guard is lifted only with the box ticked.
3. **Allocate from Purchase Receipt** (Material Mapping grid button, blue →
   `allocate_receipt_to_plan`):
   - receipt batches (`_receipt_batch_names`: bundles plus `batch_no`), free Kg in the
     plan's warehouse (less every plan's reservations and this plan's rows);
   - batches already in this plan's Exact Match are skipped (a batch serves one table);
   - rows land in **Material Mapping**, where a different-size batch belongs: a row
     already waiting as "Not Mapped" is filled in place (`_mapping_row_from_batch`), the
     part a batch can't cover stays as its own Not Mapped row, and a requirement with no
     row gets one (`_requirement_fields` + the batch fields). The requirement keeps its
     own size; the batch's goes on `batch_*`, with `reserve_without_dimensions = 1`;
   - covered Kg comes off Unavailable Items;
   - nothing is reserved, and running it twice allocates nothing more.
4. Test: `verify_mp_stock_without_dimensions` (29 checks: the real `check_stock_availability`
   with stand-in stock, and `allocate_receipt_to_plan` on a real draft plan in a rolled-back
   transaction).

---

## 25. The Final Stock Entry leaves booked excess behind (2026-09-20)

MIP-2026-00007: the transfer sent more than the drawings called for and the popup's
consolidated excess tab booked the off-cut to return (PLATE8 666.308 Kg, PLATE25 130.467,
FLAT 30.222). The Manufacture entry then consumed every kilo at the supplier, so Return
Excess Entry refused: *"There is not enough of this material left ... PLATE8: 666.308 Kg
short ... It has already been consumed by the final Stock Entry."*

The per-drawing cap in `_consumption_for_completed` could not help: that plan's rows carry
`drawing_planned_weight` equal to `transferred_qty`, so there was nothing to cap.

- `_excess_booked_to_return(mip)` returns Kg per item from Excess Material Items rows that
  are not yet a Stock Entry (`stock_entry_created = 0`) and not claimed
  (`mapped_material_planning` empty).
- `_consumption_for_completed` holds that back per item: what a row would not have
  consumed anyway counts first, then the consumption itself, and any remainder carries to
  the item's other rows.
- Test `verify_fg_entry_leaves_excess` (7 checks) replays MIP-2026-00007 through the real
  function: 3,931.705 Kg at the supplier with 666.201 booked leaves exactly 666.201, and
  nothing changes when nothing is booked.
- Entries already made are not corrected: their material is consumed. Write the difference
  off as Process Loss, or cancel and re-make the entry.

## 26. Cross-item batch reassignment, and the finished-goods loss (2026-09-22)

A day's worth of defects found by walking MIP-2026-00059 and MIP-2026-00060 end to end.
They are separate faults, grouped here because they were found on one job and share a
theme: a figure keyed on the *requirement's* item when it should have been keyed on the
*batch's*.

### 26.1 The transfer line's DUNO

`get_mip_pending_items` stamped each line's DUNO / drawing / customer drawing number from
a dict keyed `(item, batch)` — no CNC leg, and the last row seen won. MAT-STE-00354 moved
1B1's material carrying 1B3 and 1B5. `create_mip_cnc_partial_forward` reads those values
straight back off the transfer's rows, so the wrong drawing was copied onward.

The key now carries the leg, and where the contributing rows disagree the line is stamped
**blank**: a merged line covers several drawings and belongs to none. Test
`verify_transfer_line_duno`.

### 26.2 The CNC forward released the reservation twice

Material bound for a CNC drawing travels Stores → CNC → supplier. The reservation is given
up on the *first* hop. `_release_material_planning_reservations` charged both, and because
a release walks a batch's still-reserved rows in order, the second charge ate into the next
drawings in the plan. MP-2026-00260 lost 81.056 Kg of ISA100 and 24.003 Kg of PLATE10 off
1B6–1B10, none of which had shipped.

`_cnc_sourced_rows` excludes rows leaving the plan's own CNC warehouse from
`_consumed_qty_by_batch`, per row rather than per entry so a mixed entry still releases its
stores half. Cancel mirrors it. Test `verify_cnc_forward_double_release`.

### 26.3 The transfer draft outlived every transfer

`_clear_transfer_draft` was only called from `create_mip_transfer_entry`. The popup's
**Verify and Transfer** runs `create_mip_partial_transfer`, so no transfer made from the
dialog ever cleared its draft. It now clears the **whole popup's** draft, not only the rows
sent: the off-cut is stated once per item and parked on every batch row of that item, so
sending one batch of a two-batch item left an off-cut already booked into
`excess_return_items` sitting there to be booked again. Test `verify_transfer_draft`.

### 26.4 A settled Material Planning row stays settled

Transferring is what *releases* a reservation, so after one a shipped row and a row nobody
ever reserved looked identical — and the row lock let go of batch, waiver, Sec Nos and CNC
Process on rows whose steel had left the building. Check Mapping had the same blind spot
and reported 32 issues on MP-2026-00260, every one settled work.

- `transferred_qty` and `fully_transferred` on both batch tables, kept by
  `_release_rows_by_qty` and unwound by `_restore_rows_by_qty`.
- A row is settled when reserved **or** shipped anything; partial counts.
- `_row_has_shipped` excludes them from `_collect_batch_mapping_issues`.
- The plan-wide *Check stock without dimensions* locks once anything is settled.

Test `verify_transferred_row_locked`.

### 26.5 The requirement shared across two batches

`drawing_planned_weight` is the whole requirement's weight, carried on every row that fills
it. `_consumption_for_completed` measured each row against the whole, so a requirement fed
from two batches held nothing back: 128.456 Kg of PLATE8 was consumed into the job when it
was off-cut standing at the supplier. It now uses `requirement_weight_shares`, the same
split the transfer popup and the per-row Excess Qty already use. Consumption lands exactly
on the plan's own planned weight. Test `verify_fg_consumption_requirement_share`.

### 26.6 Finished goods: the loss, and the weight

The Manufacture entry consumed steel and produced finished goods, and nothing recorded the
difference — it disappeared into the finished item's valuation rate. It **cannot** be a
stock movement: the same entry has already consumed the material.

- `custom_loss_kg` on the finished-goods row, **signed**: positive is weight that went in
  and did not come out; negative means more was booked than consumed, which says the Sales
  Order weight is understated.
- `loss_weight_kg` on the Material Issue Plan, recomputed by summing submitted entries so a
  cancel needs no unwinding. Deliberately separate from `process_loss_weight_kg`, which is
  off-cut written off at the supplier.
- The popup gained **Cust Wt per Nos** (read-only), **FG Wt per Nos** (editable),
  **Consumed RM Wt**, **FG Total wt** and **Loss**, recomputed live, with a confirm when a
  row books more than it consumes. Themed in blue beside the green transfer popup.
- `_consumed_kg_by_drawing` splits the consumption per drawing from the plan — the
  consumption rows are merged across drawings and carry no DUNO — then prorates onto what
  the entry actually consumes.
- The consumption rows carry Sec Nos now, scaled whenever the Kg are narrowed.
- The finished-goods Kg is read-only on the draft: the popup is the only screen that shows
  the consumed steel beside it, and re-opening it rebuilds the existing draft.

Tests `verify_fg_loss_and_edit`, `verify_fg_consumption_sec_nos`.

### 26.7 The Subcontracting Order's FG line said Nos

`Subcontracting Order Item` has no `uom` field, only `stock_uom`, and the builder passed
`"uom"` — a key Frappe drops in silence. With `ignore_validate` the fetch never ran either,
so SC-ORD-2026-00025 read *4,740.12 Nos* of a Kg-stocked item. Test `verify_sco_fg_uom`.

### 26.8 A batch of any item, before the transfer

The real reason to open Update Batch is the planner deciding to send one ISMB800 in place
of four ISMB200. The picker offered the line's own item only, and the preview refused
anything else outright.

- `Material Planning Available Raw Material` gained **`planned_item`**, which Material
  Mapping has always had: 65 places read `planned_item or item_code` as *the item the batch
  holds*. Without it a PLATE20 batch on an ISMB450 row would ship as ISMB450.
- `consolidate_batch_query` is a searchable Link query — batch name or item code, showing
  item, **free** Kg and size, the line's own item first.
- The item is a warning, not a blocker. Availability is the only test; size never needed
  one, because Reserve Without Dimensions makes Kg the only number that reconciles.

Tests `verify_cross_item_batch_reassign`, `verify_consolidate_batch_picker`.

### 26.9 The substituted piece was weighed as the item it replaced

Found the first time a line actually moved across items — ISMB450 onto a PLATE40 sheet.
`_sec_nos_for_weight_arm` took the unit weight and group from the row's own item while the
dimensions were the batch's, so one piece weighed 12 m × 72.4 = 868.8 Kg — a bar — against
a sheet's row. Worse, the three fields agreed with each other and with the stored Sec Nos,
so `_line_kg_per_piece` trusted them. Typing 1 to send a whole sheet then read as *less*
than the plan and was capped: 868.8 Kg against a 1,592.412 Kg requirement.

The batch's item now decides in all three places — `_sec_nos_for_weight_arm`,
`_apply_rwd_fractional_nos` and `refresh_mip_raw_materials`, which carries the batch's
group and unit weight onto the plan rows for both tables. Test
`verify_cross_item_sec_nos_and_partial`.

### 26.10 Two dialogs that misreported

- **The shortfall warning** named the whole plan. Reserving for three rows reported
  MP-2026-00260's three already-shipped ISMB400 rows as 8,870.400 Kg short. Partial rows
  now carry `name` and `_apply_to_one_plan` reports only what it touched.
- **The "Row" column** in the reassignment dialog was the Material Issue Plan's index shown
  beside the plan's name — MIP rows 1/7/11 are MP rows 16/22/26. Both are shown now, with
  the customer drawing. Test `verify_consolidate_row_identity`.

## 27. No hard-coded warehouse names (2026-10-18)

Live renamed Stores to RM Yard, and everything that spelled a warehouse's name broke. Warehouses
are now always read from configuration.

- **Job Worker Warehouse.** Warehouse has a new **Job Worker** field (`custom_job_worker`, Link
  Supplier, `manufyxinvenzaerp/custom/warehouse.json`). `overrides.resolve_supplier_warehouse(supplier,
  company)` returns the company's warehouse linked to that job worker. It used to build the name as
  `"<Job Worker> - <Company Abbr>"`. A Job Work Order whose job worker has no linked warehouse now
  stops with *"No warehouse of … is linked to Job Worker …"*, rather than a mandatory error on a hidden
  field. Patch `v16.link_job_worker_warehouses` links the warehouses made under the old convention
  (INTERNATIONAL STEEL PRO on this site). It syncs the custom field first, because migrate runs
  patches before it syncs `custom/*.json`.
- **Storage Locations are no longer seeded.** `setup.setup_storage_location` used to create A-1 and
  A-2 with no warehouse. Once `warehouse` became mandatory, every migrate failed on them.
- **Tests** read warehouses through `tests/warehouses.py`. That means Stock Settings → Default
  Warehouse, Company → Default WIP / FG Warehouse and the Job Worker link. Each helper fails naming the
  setting when it is blank. This site's Company now has Default WIP = Work In Progress - MIPL and
  Default FG = Finished Goods - MIPL.
- Not changed: `sample_data.py` *creates* its own sample warehouses, so it names them. Labels and
  comments mentioning "Stores" describe the flow, not a warehouse.


## 28. Rate Schedule Category (2026-10-20)

- New Select field **Category** on Rate Schedule (Fabrication / Blasting & Painting / Painting), right
  after Type, with a list-view filter. It is **for reference only**. The client asked that nothing
  filter on it: the Fabrication and Painting Rate Schedule pickers on Drawing, BOM, Production Plan and
  Sales Order still list every schedule. Not mandatory, so older schedules without one still save.
- manufactv16's 48 schedules were filled from their Job Nature: Blasting & Painting → 6,
  Painting → 4, everything else Fabrication → 38. There's no patch, because live gets the same
  load when its data is reset.

## 29. Data Works page — one-time go-live data reset (2026-10-20)

Desk page **Data Works** (`/desk/data-works`, System Manager). It repeats on the live server what was
done by hand on manufactv16 on 18–20 Oct. It is meant to be used once and then removed in a later commit.

- **Guards:** System Manager only, and every button asks for the site name. There is no site_config switch
  (removed on request), so after a deploy the page is live; it must be removed in the next commit.
- **Buttons:** Back up now · Delete transactions and test data · Load RM item master · Run everything
  (backup + delete + load). The warehouse and rate-schedule steps were removed on 23 Oct 2026 (client):
  those masters are set up by hand on live. Each shows a preview of what it will
  do, then asks for the site name. The work runs as a background job on the `long` queue, and the page
  follows `sites/<site>/private/data_works.log`. State is in `data_works_status.json`. One backup is
  taken, by Run everything or the Back up button. There is no maintenance mode.
- **Transactions step:**
  - Ledgers cleared by SQL: Stock Ledger Entry, GL Entry, Payment Ledger Entry, Bin, Repost Item Valuation,
    Stock Reservation Entry.
  - Documents deleted (with children, comments, versions and attachments): Payment Entry, Journal Entry,
    Sales Invoice, Purchase Invoice (added 24 Oct: live kept SINV-26-00002 after the reset), Packing Slip, Delivery Note,
    Delivery Challan, Supplier Operation Entry, Material Issue Plan, Inspection Entry, Cut Sheet, Material
    Planning, Subcontracting Order, Stock Entry, Purchase Receipt, Purchase Order, Material Request,
    Production Plan, BOM, Drawing, Sales Order, Process Deferred Accounting, Process Subscription, Manufyx
    Decision Log, Serial and Batch Bundle, Batch.
  - Test masters deleted: Items, Suppliers, Customers whose name starts with `ZZ` or `Test`, and Projects whose
    project name does (list in `setup.json`). The preview lists them first.
  - Naming series of everything deleted restart at 1.
  - Kept: the item master and every other master.
- **Load RM item master step (24 Oct 2026):** loads `data_works/data/rm_items.json`, the client's
  Code-Spec-Grade master (`RM_Section_Weight_Master_with_Suggested_HSN _ 23-OCT-26.xls`).
  - 282 items: the sheet's 291 rows less duplicates, codes upper case, Chqd codes keep their space
    (`CHQD PLATE5-MS-IS2062-E250`), UOM Kg. Weights confirmed by the client on 24 Oct: ISMBX200X100 24.2,
    ISMCX250X82 34.2, NPBX300X150 42.24.
  - HSN: the sheet's codes, corrected (approved 24 Oct) where the 8-digit code did not fit the size: MS plates
    by thickness 72085410 (<3 mm) / 72085310 (3–4.75) / 72085210 (4.75–10) / 72085110 (>10); SS plates
    72199013 / 72199012 / 72199011; Chqd plates 72084010 (72084000 is not in the GST HSN master); ISA under
    80 mm 72162100; UC and WPB (H sections) 72163300; FLATX25X3 72111910. Review sheet:
    `~/Downloads/RM item master - load plan 24-Oct.xlsx`.
  - Batch prefix (Custom Batch Abbreviation): the item code with the section cut to two letters, e.g.
    `PT8-MS-IS2062-E250`. PLATE PT, FLAT FT, ROD RD, CHQD PLATE CP, ISA IA, ISMB IB, ISMC IC, NPB NB, WPB WB,
    UB UB, UC UC (`abbreviations` in the JSON).
  - A new code is a copy of the live item it replaces (`replaces`), so item defaults, storage locations and
    inspection settings carry over; then spec, grade, group, weight, HSN, prefix, Kg/Nos and batch settings
    are set from the JSON. An item that already exists is updated, so the step can run again.
  - Then deleted, one by one (Item Prices first): every item in *Plates child node* / *Structural child node*
    that is not in the master, except `keep` (SHS100, SHS150), plus `delete_also` (test item E2E-FG-STRUCT).
    An item still linked from a leftover document is kept and named in the log instead of undoing the load.
  - Refuses to start while the Stock Ledger has rows or a linked master (HSN, group, spec, grade) is missing.
  - Tested: `tests/verify_data_works_items.py` (18/18) runs Delete transactions + Load twice on manufactv16
    inside a rollback.
- **Where the data lives:** `manufyxinvenzaerp/data_works/data/setup.json` (test prefixes and the doctype
  lists) and `data/rm_items.json` (the item master).
- **Gotchas found while building it:**
  - Frappe refuses to delete a submitted document even with `force`, so each is marked cancelled first (the
    ledgers are already gone).
  - `delete_doc` queues one cleanup job per document, which overloads the queue (600 jobs, no worker
    locally). The engine queues nothing during the delete loops and runs `delete_dynamic_links` inline.
  - Naming-series keys are saved to `data_works_series.json` before the deletes, so a rerun after a failed
    step still resets them.
  - Each step is safe to run twice.
- **Tested** locally three times: restore of the 18 Oct live dump, migrate, then Run everything through the
  queue with a worker. The result was identical to the hand-made reset: 39 items, 11 warehouses, 40
  locations, 48 schedules, no stock.

## 30. Full-process test with the client's 21 Oct 2026 BOM sheet, and the two fixes it found

Run on manufactv16 (a restore of live dump `20261021_180002`, plus the 279 RM Section items) with `BOM_Import_Template _21-oCT-26.xlsx`: Sales Order `SAL-ORD-2026-00004` (JK Cement, 8,722.75 Kg / 50 Nos of *Fabricated Structurs*) → Verify → 2 Drawings → 2 BOMs → Material Planning `MP-2026-00002` (10,489 Kg of raw material) → Auto Purchase (MR → PO → PR, 8 batches) → reserve → Production Plan `PP-INT-2026-00002` → Job Work Order `SC-ORD-2026-00002` + Material Issue Plan `MIP-2026-00002` → transfer to supplier → 5 operation entries (Final with an Inspection Entry, 50/50 accepted) → Final Stock Entry → Delivery Note `DN-26-00002` → Sales Invoice `SINV-26-00002`. Every document reached its end status.

**Fixed in code**
- **"Make Production Plan" (Material Planning) and "Create Production Plan" (BOM) could not insert a plan.** Both set only *Qty (Nos)* on a drawing row and left Planned Qty to `apply_fg_nos`, but ERPNext v16's `validate_data` refuses Planned Qty 0 *before* that hook runs ("Row #1: Planned Qty must be greater than 0"). Both now also set `planned_qty` from `drawing_kg_for_nos`; `apply_fg_nos` recomputes the same figure. Files: `material_planning.py` (`make_production_plan`), `drawing_utils.py` (`create_production_plan_from_bom`).
- **Finished goods were booked into the raw-material warehouse.** `make_production_plan` copied the Material Planning's *Raw Materials Warehouse* onto the plan item's warehouse, which is where the Job Work Order and the Final Stock Entry book the FINISHED goods. A drawing row now takes the Company's Default Finished Goods Warehouse (the raw-material warehouse stays as the fallback).

**Seen, not changed — for the client / next session**
- Cancelling a submitted Final Stock Entry leaves the Material Issue Plan **Completed and locked**, so the entry cannot be recreated ("already Completed and locked"). The test reset the status by hand.
- The Sales Order line took its warehouse from the FG item's *Item Default* (RM Yard), so the Delivery Note found no finished-goods batch until the row's warehouse was changed to Finished Goods. Set the FG items' default warehouse.
- *Auto-suggest dimensions* proposes fractional pieces (e.g. 219.831 Nos of 191×58×30); the test rounded each up to whole Nos before buying.
- BOM `BOM-Fabricated Structurs-023` (IS2062/SS-304 mix) shows a total cost 2.4× that of the SS-heavier `-024`; items have no price list, so costs are not meaningful yet.
- A Packing Slip can only be made from a **draft** Delivery Note (ERPNext rule); not exercised.
- Every item needs Storage Locations for the receiving warehouse before a Purchase Receipt will submit (PR blocked on PLATE10, whose list named only RM Store). The test added A2 / RM Yard to the 8 items used.

**Sheet corrections** (original kept as `BOM_Import_Template _21-oCT-26 (client original).xlsx`): material code now follows the plate's Thickness and Grade — `PLATE8` with Thickness 6 → `PLATE6` (MS) / `PLATE6-SS304`; `PLATE25` with Thickness 30 → `PLATE30-SS304`; SS-304 rows `PLATE10` → `PLATE10-SS304`; Material Spec `MS` → `SS` on every SS-304 row. 15 rows changed. New local Item `PLATE6` (MS / IS2062) — does not exist on live.

## 31. Client changes of 22 Oct 2026

Verified by `tests/verify_client_changes_oct22.py` (40 checks, rolled back).

- **Item → Validate Storage Location** (`custom_validate_storage_location`, Check, default off, above the Storage Locations table; field in `setup.py: create_oct22_change_fields`).
  - Off (every item after migrate): a transaction offers and accepts every Storage Location of the row's warehouse. The Item's Storage Locations table is ignored, except that its default row is still filled in.
  - On: the old rule — only the locations the Item lists for that warehouse; none listed, none allowed.
  - One switch in `storage_location.py: allowed_locations` (via `validates_item_locations`), so Purchase Receipt, Stock Entry, Delivery Note and the MIP / Material Planning paths all follow it. Not request-cached on purpose: an Item saved and re-read in one request must see the new value.
- **Job Work Order numbering.** Subcontracting Order naming series is `JWO-.YYYY.-` (property setters on `naming_series` options and default). Orders made before keep their `SC-ORD-…` names.
- **JWO Allocation No. per Supplier/Contractor** (`Supplier Operation Entry.jwo_allocation_no`, read-only).
  - `subcontracting.set_jwo_allocation_numbers(sco)` runs after `_create_soes_for_sco`. Parties (`supplier or contractor`, blank counts as its own party) are numbered in the order they first appear in the routing: `JWO-2026-00001-1`, `-2`. A, B, A is two numbers, not three (client). One party → the plain order number.
  - Shown in its own *Allocation No.* table below the Job Work Order's Operations table (Allocation No., Supplier/Contractor, the operations it covers — `allocation_table` in `SCO_OPS_SCRIPT`), and heading the contractor-wise print. Kept out of the operations table so that table keeps its width; the operations table also scrolls inside its own box rather than running under the form's side panel.
  - Patch `v16.set_jwo_allocation_numbers` filled existing jobs.
- **Contractor print shows rates.** Each drawing row now has Fabrication Rate Schedule No. + Rate/Kg and Painting Rate Schedule No. + Rate/Kg, read from the Drawing (`rate_schedule`, `rs_rate_per_kg`, `painting_rate_schedule`, `prs_rate_per_kg`). This replaces the earlier "no rates" choice.
- **Operation Entry — Weighment and Cycle Time** (doctype fields, `allow_on_submit`). Layout (23 Oct): header in 3 columns; *Weighment* (Drawing Weight · Weighment Weight · Difference) one row under Weight Summary; *Cycle Time* (Start · End · No. of Days) one row at the bottom of the Details tab, after the Consumption Log — so the log table is reached without scrolling past them. Start and End Date are read-only (set by the server only):
  - `operation_start_date`: filled when the operation first goes In Progress, from the earliest Consumption Log date (today if no dated row). `operation_end_date`: filled when the status becomes Completed (Mark as Complete). Only blanks are filled. End before start is refused (server-side safety).
  - `no_of_days` = end − start + 1 (both days counted), 0 until both are set.
  - `drawing_weight_kg` = Σ drawing rows' Cust Weight (Total); `weighment_weight_kg` typed (reference only); `weight_difference_kg` = weighment − drawing, 0 when no weighment.
  - `subcontracting.set_cycle_time_and_weighment` runs in validate and on `before_update_after_submit`; `public/js/supplier_operation_entry.js` shows the same live.
- **Production Report:** each operation's block now has *Start Date*, *End Date*, *No. of Days* from the Operation Entry. These replace the old *Gap (Days, approx.)* column, which only guessed from creation times.
- **Delivery Note / Packing Slip weighment.** Row field `custom_weighment_weight` and header `custom_total_weighment_weight` (DN: after Total Net Weight; Packing Slip: after Net Weight UOM). `selling_management/weighment.py`: when any row has a weighment, the total is their sum; when none does, the typed total is kept. Hooked in DN validate and `PackingSlip.validate`; `public/js/weighment.js` does the same live.
- **MRS No. mandatory** on the Material Issue Plan transfer popups that ask for it — RM → supplier/WIP and CNC → supplier. The leg into CNC still asks for no slips. Checked in the dialog (`reqd`, plus a message on Transfer; Save and Close is not blocked) and on the server (`material_issue_plan_transfer._require_mrs_number` in `create_mip_partial_transfer` for non-CNC and `create_mip_cnc_partial_forward`). Cutting Plan No. stays optional.

## 32. Op-1 waits for the whole transfer, item by item (2026-10-23)

Found on live SC-ORD-2026-00003 / MIP-2026-00003: all five operations were logged while 193.424 Kg of PLATE16
was still in RM Store. Other items (PLATE10-G1, PLATE8-G1) had been sent over plan, so the job's total
transferred Kg was above plan. Op-1's check only refused a drawing with 0 Kg transferred, and the Operations tab
banner compared totals, so neither saw it. Only Make Final Stock Entry, which compares per item and batch,
refused ("Nothing to Book"). Checked by `tests/verify_op1_waits_for_transfer.py` (13 checks, rolled back).

- **One answer:** `subcontracting._pending_transfer(sco)` → `{mip, kg, item_count, cnc_kg}` from
  `get_mip_pending_items` (Material Planning held qty per item+batch less the plan's transfer entries). None when
  the job has no plan or it cannot be answered (then nothing is blocked). Not `items` — that is the dict method.
- **Op-1** (`_check_op1_transfer`, in `validate_supplier_operation_entry` step 4): with Manufacturing Settings →
  SOE Log Entry Allowed When = *Fully Transferred* or blank (live is blank), logging on Op-1 is refused while any
  item is pending — "Material Not Yet Transferred", naming the Kg, item count, CNC share and the plan. The old
  per-drawing "0 Kg transferred" check stays after it. *Partially Transferred* skips both.
- **Final Stock Entry** (`_pending_transfer_block`): unchanged rule, now built on the same function. Still the
  last net for Partially Transferred jobs and for operations logged before this check.
- **Operations tab banner** (`SCO_OPS_SCRIPT`): `fetch_pending_transfer` calls `get_pending_transfer` before the
  table is drawn; "Not Yet Transferred" is the item-level Kg plus "N item(s) on MIP-… not yet sent". The planned −
  transferred Kg difference is only the fallback when there is no plan.
- Setting description corrected to say what it does (it promised the per-item rule before the code had it).
- Existing data left as is (client): live SC-ORD-2026-00003 is a test job to be removed.

## 33. Warehouse → Mandatory Storage Location (2026-10-23)

- New Warehouse field `custom_mandatory_storage_location` (Check, after Warehouse Type; `setup.create_warehouse_storage_location_field`).
- `storage_location.location_applicable(warehouse)` is now: the box is on **and** the warehouse has at least one Storage Location. When it holds, every movement in or out of that warehouse must name one of them: refused on submit when blank, and a filled one is checked on save (rules unchanged, see the Storage Location section). A ticked warehouse with no locations asks for nothing.
- Replaces Warehouse Type → *Storage Location Applicable* as the switch. That field is hidden (property setter) and no longer read. Patch `v16.warehouse_mandatory_storage_location` ticked every warehouse whose type had it, so behaviour did not change on the day: RM Store, RM Yard, Consumables Store, Maintenance Store (and the ZZTEST store) locally. The patch creates the field itself, because patches run before customizations sync.
- Forms already ask `get_location_settings`, so the location fields turn mandatory per warehouse without any JS change.
- Checked in `tests/verify_client_changes_oct22.py` §6. `verify_storage_location.py` fixture switched to the warehouse box.
