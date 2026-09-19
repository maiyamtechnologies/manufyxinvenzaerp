# SEP 14 — Finished goods in Kg, tracked in Nos per drawing (FINAL PLAN)

> **Status: Implemented (waves 0–3), 19 Sep 2026.** Approved for development 19 Sep 2026
> (R1–R5 confirmed). Commits: e2951ab (wave 0), 315d838 (wave 1), 086180e (wave 2); wave 3
> (manual, features doc §22, `tests/verify_fg_end_to_end.py`) is ready for the coordinator's
> commit. See **Implementation notes / known limits** at the end.
> - Decisions came from the chat and from the decision sheet
>   `~/Downloads/FG_Kg_Nos_Plan_Gaps_Decisions.docx` (Q1–Q13, answered by the user).
> - Work is split into agents in waves: see **§7 Agent work split**. Resume with
>   *"start wave 0 of the sep 14 plan"*.
> - Old orders, drawings, BOMs, Production Plans, Job Work Orders and FINGOODS001 are **not
>   migrated**. The user deletes them later. Build and test for **new entries only**.

## The rule in one line

**Finished goods move in Kg everywhere (stock UOM Kg), and every FG row also carries its
piece count as Sec Qty in Nos, per drawing.** One batch per drawing holds both, so Kg per
piece is always *batch Kg ÷ batch Nos*.

---

## 1. Final decisions

### Agreed in chat

| # | Topic | Decision |
|---|---|---|
| D1 | Sales Order unit | Line Qty in **Kg** (Tonne converted to Kg by the user). **Sec Qty = total Nos** of the line. |
| D2 | Customer weight | Two values everywhere: **Cust Weight (per Nos)** and **Cust Weight (Total)** = per Nos × Nos. Total always means all pieces. |
| D3 | Verify Raw Materials | Per drawing: per Nos × Nos = Total. Per FG line: Σ drawing Total = line Kg, and Σ drawing Nos = line Sec Qty. **All block drawing creation.** |
| D4 | Second FG item | A drawing whose FG item isn't on the SO items table fails Verify. |
| D5 | Production Plan | The user enters **Nos**; Kg = Cust Weight (Total) × Nos ÷ drawing Nos (= Nos × per Nos). |
| D6 | Batch | **One per drawing**, `FG-<Sales Order>-<DUNO>`, created by our code. |
| D7 | Final Stock Entry Kg | Defaults to Nos × Cust Weight (per Nos). Setting **Edit FG Stock Kg** (on by default): on = editable, off = read-only and reset by the server. |
| D8 | Delivery Note | The user types **Nos**; Kg = Nos × batch Kg per piece, **read-only**. The last Nos of a batch takes its exact remaining Kg. |
| D9 | Order status | **Not changed** in this task. |
| D10 | Over-delivery Kg % | Configured later by the client. No code. |
| D11 | Invoice UOM | Same UOM (Kg) as the SO / DN. |
| D12 | BOM quantity | **Kg** = Cust Weight (Total). The Nos is carried as BOM Sec Qty. |
| D13 | Old data | Skipped. |
| D14 | Precision | **3 decimals** (`flt(x, 3)`) for every backend Kg calculation and comparison. No other tolerance. |
| D15 | Update Customer Weight | The Drawing popup takes the **per Nos** weight; Total = × Nos is calculated. |
| D16 | Several PPs per drawing | Allowed; Σ Nos over all non-cancelled PPs of a drawing **can never exceed** the drawing's Nos. |
| D17 | FG weight warning | Setting **FG Weight Difference Warning (%)**. |
| D18 | Print formats | Custom formats. **No print work.** |

### From the decision sheet (user's answers)

| # | Sheet | Decision |
|---|---|---|
| D19 | Q1 | **Drop Work Order.** Core Work Order and Job Card are out of the plan. FG is booked only through the Job Work Order's Final Stock Entry. |
| D20 | Q2 | FG **Material Transfer allowed**. The user enters Nos, and Kg is calculated. Nos are tracked per warehouse. **The batch carries full reference details** (§4.1). |
| D21 | Q3 | **Stock Reconciliation blocked for the whole site** (it isn't used: 0 records). The form shows the message in A1 item 3 on open, and the server refuses to save. Corrections are made with Material Issue (remove) + Material Receipt (add back). **RM and FG Material Transfer / Issue / Receipt must work correctly with Kg, Nos and batch updates** (audit task). |
| D22 | Q4 | Returns by **Nos into the same drawing batch**. **Nos is shown in the grid (list view) on the Sales Order and the Delivery Note.** Kg on DN / return rows is read-only. |
| D23 | Q5 | **Update Stock blocked** on invoices with FG lines. **An invoice made directly from the Sales Order works by Nos**: e.g. SO 10 Nos / 1,000 Kg → invoice 5 Nos = 500 Kg. The next invoice defaults to the **pending** Nos (5), not the total. |
| D24 | Q6 | Drawing List weights and Nos are **locked once the row has a Drawing**. They change only through Update Customer Weight on the Drawing. |
| D25 | Q7 | **Server-side check** that Verify passed, before Create Drawing. |
| D26 | Q8 | **One server-side Kg calculation** for every Production Plan entry point. |
| D27 | Q9 | Material Issue Plan drawing rows take **Nos from the Production Plan** (new entries only). |
| D28 | Q10 | Batch mandatory on FG rows, plus a **Get FG Batches** button. The batch carries the **Sales Order reference**, which the DN uses to find and fill batches. |
| D29 | Q11 | Every DN batch row is **linked to its SO line** (`against_sales_order`, `so_detail`). |
| D30 | Q12 | **Total sent downstream everywhere.** Uniform labels **"Cust Weight (per Nos)"** and **"Cust Weight (Total)"** on: the SO Drawing List (and the upload template), Drawing, BOM, Production Plan, Material Issue Plan and Job Work Order. |
| D31 | Q13 | **Job work amount now:** Job Work Order item rate from the drawings' Rate per Kg, amount = Kg × rate. **Production Report shows the rate per Kg and the amount per drawing, plus the overall total.** |

### Readings (confirmed by the user, 19 Sep 2026)

- **R1, D22 read-only:**
  - the SO line **Kg stays editable**, because the user enters it (D1);
  - on the DN, DN return and SI, **Kg is read-only and Nos is the field typed**.
- **R2, D23 Kg per Nos:**
  - an invoice made from the SO uses SO line Kg ÷ SO line Nos (the ordered weight);
  - an invoice made from a DN uses the DN row's actual Kg per Nos;
  - the last pending Nos takes the exact pending Kg.
- **R3, D31 amount basis** = the drawing's Cust Weight (Total) on that Job Work Order ×
  its Rate per Kg. The Job Work Order item rate = Σ amount ÷ Σ Kg, a weighted average,
  because one Job Work Order has one FG item line but several drawings.
- **R4, no Nos overshoot:** DN Nos ≤ pending Nos on the SO line, and SI Nos ≤ pending
  (unbilled) Nos.
- **R5, customer weight updated after the Job Work Order exists:** a draft JWO recomputes
  its rate and amount; a submitted JWO keeps its qty, and the update message lists it.

---

## 2. Facts from the live site (19 Sep 2026)

**Items, batches and settings**
- FG items: `custom_parent_item_group = "Finished Goods"` (item group "Fin Goods Item").
  - "Fabricated Structurs": Kg, Sec UOM Nos, no stock, no batch.
  - FINGOODS001: Nos, 6 in stock (left alone, D13).
- 116 batches, none starting with `FG-`. `before_insert_batch` only renames PR and
  Repack / Material Receipt batches of items that have `custom_batch_prefix`.
- Stock Settings:
  - `use_serial_batch_fields = 1`;
  - `auto_create_serial_and_batch_bundle_for_outward = 1`, FIFO;
  - over-delivery allowance 0.
- **0** Work Orders, Delivery Notes, Sales Invoices, Stock Reconciliations and subcontracted
  Purchase Orders. 6 Job Work Orders (SCO), each with **one** item line.

**Current behaviour to fix**
- BOM quantity holds the piece count (`drawing_utils.create_bom_from_drawing`), and so does
  the PP `planned_qty`.
- Live bug: `create_finished_goods_entry` books Nos as Kg. `_fg_already_booked` sums
  `qty`.
- Customer weight is treated as per piece:
  - DUNO `total_weight` → `Drawing.customer_provided_wt`;
  - the PP picker multiplies it (`public/js/production_plan.js` ~769);
  - `_cascade_customer_weight` multiplies it, except for the SOE branch, which writes the
    per-piece value.

**Where the Nos come from**
- Three PP entry points:
  - the picker (`production_plan.js` `_finish_insert` ~748);
  - BOM (`drawing_utils.create_production_plan_from_bom`);
  - Material Planning (`material_planning.py` `make_production_plan` ~4465).
- `qty_to_manufacture` = `planned_qty` in the SCO builder (`subcontracting.py` ~134) and in
  `material_issue_plan.py` `populate_from_production_plan` (~137).

**Job Work Order rate and report**
- SCO item `rate = 0` at creation (`subcontracting.py` ~150). The amount comes from
  `overrides.py` `_pp_calculate_amounts` (qty × rate).
- The Production Report already has Rate Schedule and Rate / Kg columns (`rate_map`), but
  no amount.

**Other checks**
- Create Drawing's "verified" check is JS-only.
- Drawing List fields lock only on SO submit.
- New custom fields are defined in `setup.py` **and** exported to
  `manufyxinvenzaerp/custom/<doctype>.json` (commit 15faadb). There is no
  `fixtures/custom_field.json` any more.
- Existing Stock Entry hooks skip FG rows (`not row.is_finished_item`).
- Item "Opening Stock" creates a Stock Reconciliation only for items without batches
  (erpnext `item.py` 282).

---

## 3. Conventions for every agent

1. **3 decimals** for every Kg figure: `flt(x, 3)`. Money: 2 decimals.
2. **New fields** are added only by A0 (wave 0). Other agents don't add fields; if one is
   missing, stop and report it.
3. **hooks.py** is edited only by A0. It registers every hook and override up front,
   pointing at stub functions that the other agents fill in.
4. **Three different "total_weight" fields.** Change only the first:

   | Field | Meaning |
   |---|---|
   | `Sales Order DUNO Item.total_weight` | Customer weight → becomes **Cust Weight (Total)** |
   | `Sales Order Drawing Raw Material.total_weight`, `Drawing.total_weight` | Calculated RM weight. **Do not touch.** |
   | `Sales Order DUNO Item.calculated_weight` / `difference_kg` | RM roll-up. **Do not touch.** |

5. **FG row** = a row whose item has `custom_parent_item_group = "Finished Goods"`. Always
   use `fg_stock.is_fg_item(item_code)`.
6. **Last-piece rule:** when Nos equals everything remaining (in a batch in a warehouse,
   pending on an SO line, or unbilled on a DN row), Kg = the exact remaining Kg, never
   Nos × Kg per piece.
7. **Tests:**
   - `tests/verify_fg_*.py`, run with
     `bench --site manufact execute manufyxinvenzaerp.tests.<module>.run`;
   - test documents use the `ZZFG-` prefix, and each test cleans up only what it created;
   - **never delete or change user data**. Snapshot and restore anything borrowed.
8. **No migrate, no bench restart and no commit inside waves 1–3.** Python is tested
   through `bench execute` (a fresh process). The coordinator migrates, restarts, checks
   the browser and commits between waves.
9. Match the surrounding code style: docstrings and comments explain *why*.

---

## 4. Fields and settings (all created by A0)

### 4.1 Field list

| Doctype | Field | Type / label | Notes |
|---|---|---|---|
| Manufyxinvenza Settings | `edit_fg_stock_kg` | Check "Edit FG Stock Kg", default 1 | New section "Finished Goods". Description in §4.3 |
| Manufyxinvenza Settings | `fg_weight_difference_warning_percent` | Percent "FG Weight Difference Warning (%)", default 5 | Description in §4.3 |
| Sales Order DUNO Item (own) | `weight_per_pcs` | Float "Cust Weight (per Nos)" | `read_only_depends_on: eval:doc.drawing \|\| doc.docstatus===1` |
| Sales Order DUNO Item | `total_weight` | relabel "Cust Weight (Total)" | Same read-only rule, also on `total_quantity` |
| Sales Order Item | `custom_sec_qty` | Float "Qty (Nos)", **in_list_view** | Entered by the user |
| Sales Order Item | `custom_sec_uom` | Link UOM, default Nos, read-only | |
| Sales Order Item | `custom_delivered_sec_qty` | Float "Delivered (Nos)", read-only, no_copy | Net of returns |
| Sales Order Item | `custom_billed_sec_qty` | Float "Billed (Nos)", read-only, no_copy | |
| Drawing (own) | `weight_per_pcs` | Float "Cust Weight (per Nos)", read-only | Description: "Change with Update Customer Weight." |
| Drawing | `customer_provided_wt` | relabel "Cust Weight (Total)" | Description: "Cust Weight (per Nos) × No of Qty to Manufacture. Calculated." |
| BOM | `custom_sec_qty`, `custom_sec_uom` | "Qty (Nos)", Nos, read-only | |
| BOM | `custom_cust_weight_per_nos`, `custom_cust_weight_total` | "Cust Weight (per Nos)", "Cust Weight (Total)", read-only | From the Drawing |
| Production Plan Item | `custom_sec_qty` | Float "Qty (Nos)", in_list_view | Entered by the user |
| Production Plan Item | `custom_sec_uom` | Nos, read-only | |
| Production Plan Item | `custom_cust_weight_per_nos` | "Cust Weight (per Nos)", read-only | |
| Production Plan Item | `custom_customer_weight_kg` | relabel "Cust Weight (Total)" | |
| Production Plan Item | `planned_qty` | property setter: label "Planned Qty (Kg)"; `read_only_depends_on: eval:doc.custom_drawing` | |
| Subcontracting Order Item | `custom_sec_qty`, `custom_sec_uom` | "Qty (Nos)", Nos, read-only | |
| Subcontracting Order | `custom_customer_weight_kg` | relabel "Cust Weight (Total)" | |
| SCO Drawing Item (own; used by both the JWO and the MIP) | `cust_weight_per_nos` | new, "Cust Weight (per Nos)" | |
| SCO Drawing Item | `customer_weight_kg` | relabel "Cust Weight (Total)" | |
| SCO Drawing Item | `rate_per_kg`, `job_work_amount` | "Rate / Kg", "Job Work Amount", Currency, read-only | |
| SOE Drawing Detail (own) | `customer_provided_weight_kg` | relabel "Cust Weight (Total)" | |
| Material Planning BOM Item (own) | `customer_provided_weight_kg` | relabel "Cust Weight (Total)" | |
| Batch | `custom_sales_order`, `custom_customer`, `custom_drawing`, `custom_duno_mark_no`, `custom_customer_drawing_number`, `custom_job_work_order` | Links / Data, read-only | "FG Details" section (collapsible), shown only when `custom_sales_order` is set |
| Batch | `custom_cust_weight_per_nos` | Float "Planned Kg per Nos", read-only | |
| Batch | `custom_weight_per_piece` | Float "Actual Kg per Nos", read-only | |
| Stock Entry Detail | *(already has `custom_sec_qty`, `custom_drawing`, `custom_duno_mark_no`)* | | Make `custom_sec_qty` in_list_view if it isn't already |
| Delivery Note Item | `custom_drawing`, `custom_duno_mark_no`, `custom_sec_uom` | read-only | |
| Delivery Note Item | `custom_sec_qty` | Float "Qty (Nos)", **in_list_view** | |
| Delivery Note Item | `custom_billed_sec_qty` | read-only, no_copy | |
| Delivery Note Item | `qty` | property setter: `read_only_depends_on: eval:doc.custom_sec_uom` (FG rows) | |
| Sales Invoice Item | `custom_drawing`, `custom_duno_mark_no`, `custom_sec_qty` (in_list_view), `custom_sec_uom` | | Same names as the DN, so DN → SI maps them automatically |
| Sales Invoice Item | `qty` | property setter: `read_only_depends_on: eval:doc.custom_sec_uom` | |
| Item | `opening_stock` | property setter: hidden | Stock Reconciliation is blocked (D21) |

Grids must stay within Frappe's 11-column budget. When adding Qty (Nos) to a list view,
drop the least useful visible column and note which one.

### 4.2 Upload template headers

```
… FG Item, Total Qty, Cust Weight (per Nos), Cust Weight (Total), Nature of Work …
```

The parser also accepts the old headers: "Weight per Pcs (KG)" as per Nos, and "Total
Weight (KG)" as the Total.

### 4.3 Setting descriptions

- **Edit FG Stock Kg:** "When ticked, the Kg of each finished-goods row on the Final Stock
  Entry can be changed to the weighed figure. When unticked, the Kg is read-only and always
  equals Nos × the drawing's Cust Weight (per Nos)."
- **FG Weight Difference Warning (%):** "On the Final Stock Entry, show a warning when the Kg
  entered for a drawing differs from its planned weight (Nos × Cust Weight (per Nos)) by
  more than this percentage, in either direction. It is only a warning: the entry can still
  be saved. Set 0 to warn on any difference. Applies only when Edit FG Stock Kg is ticked."

---

## 5. Work packages

### A0 — Schema, hooks and stubs (wave 0, one agent)

1. **Fields:** every field, relabel and property setter in §4.1:
   - custom fields in `setup.py` `create_*_custom_fields()` **and** in
     `manufyxinvenzaerp/custom/<doctype>.json`;
   - own doctypes in their JSON files;
   - the Settings JSON.
2. **`production_management/fg_stock.py`**, with stubs and full docstrings. **This is the
   contract** other agents code against:
   - `is_fg_item(item_code) -> bool`: implemented now;
   - `get_or_create_fg_batch(item_code, sales_order, drawing, duno, customer, customer_drawing_number, job_work_order, cust_weight_per_nos, reference_name) -> batch_name`;
   - `refresh_fg_batch(batch_no)`: recompute `custom_sec_qty` and `custom_weight_per_piece`;
   - `fg_batch_nos_by_warehouse(batch_no) -> {warehouse: nos}`;
   - `fg_batch_available(batch_no, warehouse) -> {"nos", "kg", "kg_per_nos"}`;
   - `kg_for_nos(batch_no, warehouse, nos) -> kg`: applies the last-piece rule.
3. **Stub hook functions** (`pass` bodies + docstrings), all registered in `hooks.py`:

   | Hook | Function (file) | Owner |
   |---|---|---|
   | Stock Reconciliation `validate` | `stock_management/stock_reconciliation.py:block_stock_reconciliation` (a new package folder `stock_management` under the app module, not a new Frappe module) | A1 |
   | Production Plan `validate` (append to the list) | `production_plan_management/production_plan.py:apply_fg_nos` | A3 |
   | Stock Entry `validate` (append) | `fg_stock.validate_fg_stock_entry_rows` | A4 |
   | Stock Entry `on_submit` / `on_cancel` (append) | `fg_stock.on_fg_stock_entry_change` | A4 |
   | Delivery Note `validate` / `on_submit` / `on_cancel` | `selling_management/delivery_note.py` | A5 |
   | Sales Invoice `validate` / `on_submit` / `on_cancel` | `selling_management/sales_invoice.py` | A6 |
   | `override_whitelisted_methods`: `erpnext.selling.doctype.sales_order.sales_order.make_delivery_note` | `selling_management/mapping.py:make_delivery_note` | A5 |
   | `override_whitelisted_methods`: `erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice` | `selling_management/mapping.py:make_sales_invoice_from_so` | A6 |
   | `override_whitelisted_methods`: `erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice` | `selling_management/mapping.py:make_sales_invoice_from_dn` | A6 |
   | `doctype_js` | `public/js/delivery_note.js` (A5), `sales_invoice.js` (A6), `stock_reconciliation.js` (A1), `stock_entry_fg.js` (A4) | |

   Every override stub **calls the original ERPNext function and returns its result
   unchanged**, so nothing changes until its owner fills it in.
4. **Migrate and check:** run `bench --site manufact migrate` and restart the bench.
   Confirm that the fields exist and that SO, DN, SI, Batch, PP, SCO, Stock Entry, Stock
   Reconciliation and Drawing all open without JS errors.

*Done when:* the fields are visible with the right labels, migrate is clean, the stubs
change no behaviour, and the full regression is unchanged from its baseline
(72 pass / 28 error / 4 fail).

### A1 — Masters and stock control (wave 1)

**Owns:** `item_management/item.py`, `stock_management/stock_reconciliation.py`,
`public/js/stock_reconciliation.js`, and **RM branches only** of
`production_management/stock_entry.py` (audit fixes).

1. **FG item rule** (`validate_fg_configuration`, called from `validate_item`), for FG
   items with no transactions (`_has_transactions`):
   - stock UOM Kg, Secondary UOM Nos;
   - `has_batch_no = 1`, `create_new_batch = 0`;
   - `custom_batch_prefix` blank.

   Items that already have transactions get an orange note instead.
2. **Prefix guard:** a raw-material `custom_batch_prefix` may not be `FG`
   (case-insensitive).
3. **Stock Reconciliation blocked** (D21). The JS `onload` / `refresh` shows the message
   and disables Save, and the server `validate` throws it for every purpose, including
   Opening Stock:
   > "As the inventory module is completely customized, Stock Reconciliation cannot be
   > used. Instead, use a Stock Entry of type Material Issue to remove the product from
   > inventory, then a Material Receipt to add the updated stock."
4. **Stock movement audit** (D21): `tests/verify_fg_stock_movements.py` checks Material
   Transfer (full and partial), Material Issue and Material Receipt for:
   - an RM Plate/Structural batch;
   - an RM Nuts & Bolts item;
   - an FG batch (skipped, with a clear note, until A4 lands; it's re-run in wave 3).

   For each, assert SE row Kg and Nos, batch `custom_sec_qty` and the batch Kg per
   warehouse, after submit and after cancel. Fix RM defects in the RM branches only, and
   list each one.
5. **"Fabricated Structurs" master:** batch on, auto batch off. **Ask the user before
   changing this record.**

*Done when:*
- a new FG item with Nos UOM or no batch is refused;
- FINGOODS001 still saves;
- prefix "FG" is refused;
- a Stock Reconciliation can't be saved and shows the message;
- the RM movement tests pass.

### A2 — Sales Order, upload sheet, Verify, Drawing List lock (wave 1)

**Owns:** `drawing_management/so_drawing_import.py`, `drawing_management/sales_order.py`,
and **only the Sales Order client-script sections of `setup.py`**. A2 is the only wave-1
agent allowed in `setup.py`.

1. **Template** (`download_bom_template`): headers per §4.2. Sample: 5 Nos × 50 = 250.
2. **Parse and stage:**
   - read the per Nos value (new and old headers) into `weight_per_pcs`, and the Total;
   - add `weight_per_pcs` to the staging insert (~270–283) and to the Drawing List grid
     columns (setup.py ~1364).
3. **Verify Raw Materials** (`verify_raw_materials`) adds to `issues` (these block), for FG
   items only:
   - per pending row: per Nos and Total > 0, and `flt(per_nos × total_quantity, 3) == flt(total, 3)`;
   - per row: its FG `item` is on the SO items table (D4);
   - per FG line, over all its Drawing List rows: Σ Total = line `qty`, and
     Σ `total_quantity` = line `custom_sec_qty`.

   Messages show ordered vs drawings, in Kg and Nos, and the difference.
4. **SO validate** (`sales_order.py`):
   - clear `custom_raw_materials_verified` when an FG line's `qty`, `custom_sec_qty` or
     `item_code` changes;
   - orange warning on save when the line totals don't match;
   - **server-side lock**: on a Drawing List row with `drawing` set, `weight_per_pcs`,
     `total_weight` and `total_quantity` can't change (compare with the saved row).
5. **Create Drawing** (`create_drawings_from_import`):
   - on the first batch (`batch_start == 0`), throw if not verified (D25);
   - write `customer_provided_wt` = Total and `Drawing.weight_per_pcs` = per Nos.

*Done when:*
- a 5 × 50 = 250 sheet on a 250 Kg / 5 Nos line verifies;
- a Total of 245 fails the row;
- a line of 240 Kg or 4 Nos fails;
- a foreign FG item fails;
- calling Create Drawing directly while unverified is refused;
- editing a locked row is refused.

### A3 — Customer weight, Drawing, BOM, Production Plan, Job Work Order, MIP, job work rate (wave 1)

**Owns:**
- `drawing_management/doctype/drawing/drawing.py` and `.js`;
- `drawing_management/drawing_utils.py`;
- `production_plan_management/production_plan.py` and `public/js/production_plan.js`;
- `material_planning.py`: only `make_production_plan`, `get_bom_info` and
  `_update_bom_item_weights`;
- `subcontracting.py`: **only the SCO builder** (`create_sco_from_production_plan` and its
  helpers, above ~line 400);
- `material_issue_plan.py`: only `populate_from_production_plan`;
- `subcontracting_management/overrides.py`: only `_pp_calculate_amounts`, if needed.

1. **Drawing:** validate keeps `customer_provided_wt = flt(weight_per_pcs × no_of_qty_to_manufacture, 3)`
   when `weight_per_pcs` is set.
2. **Update Customer Weight** (D15, D30):
   - The popup field is "New Cust Weight (per Nos)". Description: "Enter the weight of ONE
     piece. Total = this × {Nos} Nos. Current: {per} Kg per Nos, {total} Kg total." Show a
     live "New total" line.
   - The server writes the Drawing (per Nos and Total) and the SO row (both), and logs old
     and new.
   - `_cascade_customer_weight` sends the **Total**, with per Nos alongside, to PP items,
     SCO Drawing Items (JWO and MIP), **SOE Drawing Detail** (fixes the per-piece write)
     and BOM.
   - Draft JWOs recompute rate and amount (R5).
   - The result message shows the new SO line difference in orange, without blocking,
     and lists any submitted JWOs.
3. **BOM** (`create_bom_from_drawing`): `quantity` = Cust Weight (Total). Set Sec Qty = Nos,
   and both Cust Weight fields.
4. **BOM quantity audit**, covered by `tests/verify_fg_bom_pp_kg.py`. It proves that
   Material Planning and MIP RM Kg for a 4-of-10 PP are exactly 4/10 of the drawing's RM.

   | Where | Check |
   |---|---|
   | `production_plan.py` `get_bom_items_direct` | ratio: unchanged |
   | `material_planning.py` `get_bom_info` (1046) | fall back to BOM Sec Qty (Nos) |
   | `bom_class_override.py` 46/49, 945, 986, 1173–1177, 1323, 1366 | ratios: unchanged |
   | `bom_class_override.py` 756–763 `cost_per_unit × quantity` | if operation costs are per piece, use Sec Qty |
   | `production_report.py` `qty_to_manufacture` | Nos again (via item 6) |

5. **Production Plan** (D5, D16, D26):
   - `apply_fg_nos(doc)` is the **only** place that calculates `planned_qty` for drawing
     rows: Total × Sec Qty ÷ drawing Nos, 3 dp. It also sets Cust Weight per Nos and
     Total.
   - It blocks when Σ Sec Qty on non-cancelled PPs for the drawing exceeds the drawing
     Nos, naming the other PPs.
   - The three entry points set only `custom_sec_qty`:
     - the picker defaults to the **remaining** Nos and hides drawings with 0 left;
     - `create_production_plan_from_bom` defaults to the remaining Nos;
     - `make_production_plan` sets Sec Qty from `qty_to_manufacture`.
   - The JS mirrors the Kg for display.
6. **Job Work Order builder:**
   - item `qty` = Σ PP Kg; `custom_sec_qty` = Σ Nos;
   - drawing rows `qty_to_manufacture` = the PP row's **Sec Qty**, plus both Cust Weight
     fields;
   - `rate_per_kg` = Drawing `rs_rate_per_kg`, and `job_work_amount` = flt(Total × rate, 2);
   - item `rate` = Σ amount ÷ Σ Kg, so `amount` = Σ amount (D31, R3).
7. **MIP** `populate_from_production_plan`: `qty_to_manufacture` = PP Sec Qty, plus both
   Cust Weight fields.
8. **Material Planning** `_update_bom_item_weights`: the value copied is now the Total, so
   there is no code change. Assert it in the test.
9. **Rewrite the tests that break:** `verify_customer_weight_scaled.py`,
   `verify_weight_cascade_reaches_soe.py`, `verify_drawing_weight_cascade.py`,
   `verify_drawing_weight_cascade2.py`.

*Done when:* for a new 10 Nos / 300 Kg drawing at 20 / Kg:
- BOM 300 Kg / 10 Nos;
- PP 4 Nos → 120 Kg, and a second PP of 7 Nos is refused (6 left);
- JWO 120 Kg / 4 Nos with the drawing row at 4 Nos, rate 20, amount 2,400;
- MIP row 4 Nos;
- RM Kg is 4/10;
- Update Customer Weight to 31 per Nos → Total 310 everywhere, SOE included;
- the rewritten tests pass.

### A4 — FG batch, Final Stock Entry, FG stock movements (wave 1)

**Owns:**
- `production_management/fg_stock.py` (implement the A0 contract);
- `public/js/stock_entry_fg.js`;
- `subcontracting.py`: **only** `_fg_already_booked`, `get_final_stock_entry_preview` and
  `create_finished_goods_entry`;
- `stock_entry.py`: **only** new calls into `fg_stock.py`. It doesn't change RM branches.

1. **`get_or_create_fg_batch`:**
   - name `FG-<SO>-<DUNO>` (the drawing name if the DUNO is blank);
   - explicit insert, filling every Batch FG field (§4.1); `reference_doctype` /
     `reference_name` = the first Final Stock Entry;
   - reuse the batch on later entries.
2. **`create_finished_goods_entry`:** per drawing:
   - `qty` = flt(Nos × per Nos, 3), `uom` Kg, Sec Qty and Sec UOM Nos;
   - `batch_no`, `use_serial_batch_fields = 1`;
   - drawing, DUNO.

   Get the SO and customer from the drawing.
3. **`_fg_already_booked`:** sum `custom_sec_qty`, falling back to `qty` when it's empty.
4. **`validate_fg_stock_entry_rows`**, for FG rows:
   - **Manufacture:**
     - Edit FG Stock Kg off: reset Kg to planned;
     - on: keep the typed Kg and warn above the % setting (drawing, planned, entered,
       difference Kg and %);
     - whole Nos only.
   - **Material Transfer / Material Issue:**
     - batch and Nos mandatory, whole Nos, Nos ≤ available in the source warehouse;
     - **Kg = `kg_for_nos`**, read-only.
   - **Material Receipt:**
     - an existing FG batch is mandatory (no new FG batch this way); Nos mandatory;
     - **Kg typed** (the re-weigh case in D21).
   - Every FG row needs a batch.
5. **`on_fg_stock_entry_change`:** `refresh_fg_batch` for each FG batch on submit and
   cancel. Nos per warehouse = Σ Sec Qty in − out, from submitted SE and DN rows.
6. **JS `stock_entry_fg.js`:** on FG rows, Nos drives Kg for Transfer and Issue, and Kg is
   read-only when the setting is off.
7. **Test `tests/verify_fg_final_stock_entry.py`:**
   - 4 of 10 Nos at 122 Kg → batch 4 / 122, 30.5 per Nos, with every FG detail filled;
   - 6 more at 181 → 10 / 303;
   - a third run finds nothing to book;
   - setting off → the typed Kg is replaced;
   - transfer 3 Nos → 90.9 Kg moved (3 × 30.3), with Nos per warehouse 7 + 3;
   - issue all → 0; receipt of 10 Nos at 300 Kg into the same batch → 30.0 per Nos;
   - every cancel restores the figures.

### A5 — Delivery Note and returns (wave 2; needs A4)

**Owns:** `selling_management/delivery_note.py`, `public/js/delivery_note.js`, and
`make_delivery_note` in `selling_management/mapping.py`.

1. **SO → DN mapping** (`make_delivery_note`): FG lines are mapped with Nos = pending Nos
   (SO Nos − delivered Nos). The Kg comes from batches. Non-FG lines are unchanged.
2. **Get FG Batches** (button + whitelisted method):
   - lists batches whose `custom_sales_order` is on the DN, with stock in the row's
     warehouse: drawing, DUNO, Nos, Kg and Kg per Nos;
   - the user ticks drawings, and one row per batch is added with `against_sales_order` and
     `so_detail` of the matching FG line (D28, D29);
   - the unbatched FG row is removed.
3. **Validate**, on FG rows:
   - batch mandatory;
   - whole Nos > 0; Nos ≤ batch available in the warehouse; Σ Nos per SO line ≤ pending
     Nos (R4);
   - Kg = `kg_for_nos` (server-side);
   - the batch's SO = the row's SO.
4. **Returns** (`is_return`):
   - Nos negated, Kg = −Nos × the original DN row's Kg per Nos (the last piece returns the
     exact remainder);
   - Nos ≤ delivered − earlier returns;
   - same batch.
5. **On submit / cancel:** SO `custom_delivered_sec_qty` (net of returns) and
   `refresh_fg_batch`.
6. **JS:** Nos drives Kg, which is read-only on FG rows, and Nos shows in the grid.
7. **Test `tests/verify_fg_delivery_note.py`** (the worked example):
   - DN 1 = 3 Nos → 91.5 Kg;
   - DN 2 = 7 Nos → 211.5 Kg (remaining);
   - 5 Nos from a batch holding 4 is refused;
   - SO delivered = 10;
   - a return of 2 Nos puts 2 Nos and their Kg back, and SO delivered = 8;
   - an FG row without a batch can't be submitted.

   ERPNext refuses DN 2 while the Kg allowance is 0%. The test sets it on the item and
   restores it afterwards.

### A6 — Sales Invoice (wave 1)

**Owns:** `selling_management/sales_invoice.py`, `public/js/sales_invoice.js`, and the two
invoice functions in `selling_management/mapping.py`.

1. **Block Update Stock** when any line is an FG item (D23).
2. **SO → SI** (`make_sales_invoice_from_so`):
   - FG rows: Nos = SO Nos − `custom_billed_sec_qty`;
   - Kg = Nos × (SO line Kg ÷ SO line Nos); the last pending Nos = the exact pending Kg
     (R2).
3. **DN → SI** (`make_sales_invoice_from_dn`): Nos = DN row Nos − its
   `custom_billed_sec_qty`; Kg from the DN row's own Kg per Nos, with the same last-piece
   rule.
4. **Validate:**
   - whole Nos; Nos ≤ pending on the source (the SO line or the DN row);
   - Kg recalculated from Nos (server-side), read-only in the JS;
   - an FG row must come from an SO or a DN.
5. **On submit / cancel:** `custom_billed_sec_qty` on the SO line (every invoice) and on
   the DN row (DN-based invoices). Credit notes reduce it.
6. **Test `tests/verify_fg_sales_invoice.py`:**
   - SO 10 Nos / 1,000 Kg → SI 5 Nos = 500 Kg; the next SI defaults to 5 / 500; a third
     is refused;
   - Update Stock with an FG line is refused;
   - cancel restores the pending Nos.

   The DN → SI case uses a DN inserted directly with Nos and batch fields; the full
   DN → SI path is re-run in wave 3.

### A7 — Production Report: job work rate and amount (wave 1)

**Owns:** `production_management/report/production_report/` (py, js, json).

1. Keep "Rate Schedule" and "Rate / Kg". Add **"Job Work Amount"** per drawing row = Cust
   Weight (Total) × Rate / Kg (2 dp), and add it to the total row. Relabel "Customer
   Weight (Kg)" to "Cust Weight (Total)".
2. Read `rate_per_kg` / `job_work_amount` from the SCO Drawing Item when set (new JWOs);
   otherwise calculate from the drawing's rate.
3. Update `tests/verify_production_report.py`.

*Done when:* the rate per Kg and the amount show per drawing, the grand total adds up, and
the report test passes.

### A8 — Docs, manual, end-to-end, regression (wave 3)

1. **Manual** (`production_management/page/erp_manual/erp_manual.js`): a new section,
   "Finished Goods — Kg and Nos", covering:
   - the template columns and the Verify checks;
   - PP in Nos;
   - the Final Stock Entry and the two settings;
   - FG transfer, issue and receipt, and Stock Reconciliation being blocked;
   - DN and returns;
   - invoicing by Nos;
   - the job work amount.

   Use §6.
2. **Features doc:** a new section in `manufyxinvenzaerp_features.md`, then run
   `bash apps/manufyxinvenzaerp/.claude/update_skill.sh`.
3. **`tests/verify_fg_end_to_end.py`:** the full §6 example, SO → Drawing → BOM → PP →
   JWO → Final SE ×2 → DN ×2 → return → SI (from the DN, and from the SO).
4. **Regression:** re-run A1's FG movement cases, the DN → SI cases, every `verify_fg_*`
   test, and the full regression against the baseline.

**Not in this plan (on hold):** the new "FG Stock by Drawing" report (Phase 7 hold list).
Start it only when the user says so.

---

## 6. Worked example (tests and manual)

One drawing: 10 Nos, Cust Weight (per Nos) 30, Cust Weight (Total) 300. SO line 300 Kg /
10 Nos. Rate 20 / Kg.

| Step | Result | Batch `FG-<SO>-D1` after (Nos · Kg · Kg per Nos) |
|---|---|---|
| PP 4 Nos | 120 Kg planned | — |
| JWO | 120 Kg / 4 Nos, amount 2,400 | — |
| Final SE 1: 4 Nos, weighed 122 Kg | | 4 · 122.000 · 30.500 |
| DN 1: 3 Nos | 91.500 Kg | 1 · 30.500 · 30.500 |
| PP 6 Nos → JWO → Final SE 2: 6 Nos, weighed 181 Kg | | 7 · 211.500 · 30.214 |
| DN 2: 7 Nos | 211.500 Kg (remaining) | 0 · 0.000 · — |
| Return 2 Nos (against DN 2) | −60.429 Kg | 2 · 60.429 · 30.214 |
| SI from SO: 5 Nos | 150.000 Kg (300 ÷ 10 × 5) | |

---

## 7. Agent work split

### Waves and dependencies

```
Wave 0   A0  schema + hooks + stubs                     1 agent, must finish first
          │  coordinator: migrate, restart, baseline regression, commit
          ▼
Wave 1   A1  masters + Stock Reconciliation + stock audit  ┐
         A2  Sales Order + sheet + Verify + lock           │
         A3  weight / BOM / PP / JWO / MIP / rate          │ 6 agents in parallel,
         A4  FG batch + Final Stock Entry + FG movements   │ no dependencies
         A6  Sales Invoice                                 │ between them
         A7  Production Report                             ┘
          │  coordinator: migrate if needed, restart, all wave-1 tests, browser check, commit
          ▼
Wave 2   A5  Delivery Note + returns                    needs A4 (fg_stock)
          │  coordinator: tests, browser check, commit
          ▼
Wave 3   A8  manual, features doc, end-to-end, full regression
```

### Why the wave-1 agents don't collide

| Shared thing | Rule |
|---|---|
| `setup.py` | A0 adds all fields in wave 0. In wave 1 only A2 edits it (Sales Order client-script sections). |
| `hooks.py` | Only A0. |
| `subcontracting.py` | A3: the SCO builder (above ~line 400). A4: FG booking functions. Always re-read before editing. |
| `stock_entry.py` | A1: RM-branch fixes. A4: adds calls into `fg_stock.py`. Re-read before editing. |
| `material_planning.py`, `material_issue_plan.py` | Only A3, only the listed functions. |
| `selling_management/mapping.py` | A5: `make_delivery_note` (wave 2). A6: the two invoice functions. |
| Live site `manufact` | No migrate or restart in waves 1–3. Test with `bench execute`. `ZZFG-` test documents are cleaned up. Never delete user data. |
| Git | Agents don't commit. The coordinator commits per wave after tests pass (no autodeploy unless the user asks). |

### Prompt for each agent

> Read `apps/manufyxinvenzaerp/.claude/tasks/sep14_fg_uom_plan.md`: sections 1–4, your
> package **A<n>** in section 5, and section 7. Work only in the files your package owns.
> Follow section 3. Do not add fields, edit hooks.py, migrate, restart, commit or delete
> any data. Build the test named in your package, run it with `bench execute`, and report:
> - what changed (file:function);
> - the test results;
> - anything blocked or outside your ownership.

### Coordinator checklist between waves

1. `bench --site manufact migrate` (wave 0, or when an agent reports a JSON change).
2. Restart: `pkill -f "honcho start"`, then `setsid bench start` in the background.
3. Run every `verify_fg_*` test plus the regression, and compare with the baseline
   (72 / 28 / 4).
4. Browser check of the forms touched in the wave.
5. Commit the wave.

---

## Implementation notes / known limits (wave 3, 19 Sep 2026)

- **End to end:** `tests/verify_fg_end_to_end.py` runs §6 through every document on fresh
  `ZZFG-A8-` masters in one rolled-back transaction (commit held off; a naming guard gives
  every app-created document a `ZZFG-A8-` name instead of a naming-series number, and
  `tabSeries` is compared before and after). Shortcuts, as in the A4 test: the last
  operation's finished Nos are written onto its SOE Drawing Detail, and the job's material
  reaches the supplier warehouse as a ZZFG- consumable (Material Receipt + Material Transfer
  tagged `custom_sco_ref`, with the MIP warehouses and the JWO transferred weight filled in)
  rather than through Material Planning. One reading made concrete by it: after DN 1 is
  billed at its actual 30.5 Kg per Nos, the SO line's remaining 7 Nos are the last pending
  pieces and take the exact 208.5 Kg left (not 210); 5 of them are 150 Kg as in §6, and the
  last 2 then take 58.5 Kg.
- **Fabricated Structurs is not batch-enabled yet:** 100 Kg of it is unbatched stock from
  MAT-STE-00012 / MAT-STE-00014, so switching Has Batch No on is the user's decision (A1
  item 5). Until then it behaves the old way.
- **Old data skipped (D13):** nothing from before the change was migrated.
- **Untested:** the Pick List → Delivery Note path, and a DN return into a different
  warehouse from the one delivered from.
- **Over-delivery / over-billing allowance (D10):** ERPNext's 0% refuses a delivery or
  invoice whose Kg exceeds the ordered Kg (heavier pieces) until the client sets a
  tolerance. The tests set it on their own items.
- **Orphan bundle:** a batch picked through ERPNext's batch selector leaves an orphan draft
  Serial and Batch Bundle behind.
- **Excluded from regression runs:** `verify_pp_naming`, `verify_internal_job_sco`,
  `verify_mixed_sco_regression` and `verify_create_operation_and_inspection_gate` commit real
  documents, so they are not run.
- **Not started (on hold):** the "FG Stock by Drawing" report.
