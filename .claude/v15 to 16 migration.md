# manufyxinvenzaerp — v15 → v16 migration plan

_Written 2026-09-26 on frappe-bench1 (v15). Analysis was done against source code:
ERPNext + India Compliance `version-16` (cloned 2026-09-26, ERPNext HEAD b30aa53) and
Frappe v16.28.0 (frappe-bench11). Nothing was run on a v16 site with this app yet —
every finding below must be re-confirmed on the real v16 bench (Phase 1)._

---

## 0. How to use this file (read first — Claude Code)

The user's workflow is:

1. User builds a **new v16 bench** (Python 3.14, Node 24) and installs frappe, erpnext,
   hrms, india_compliance, payments on their `version-16` branches.
2. User gets **manufyxinvenzaerp on its v15 code** (`devbranch`) into that bench.
3. User asks Claude Code to read the md files — `SKILL.md`, `references/app_map.md`, and
   **this file** — and then start the migration.

When that happens, Claude Code should:

- Work on a **new git branch `v16-migration`** cut from `devbranch`. Never commit v16-only
  changes straight onto `devbranch` — CI deploys `devbranch` → `main` → live (v15), and a
  v16-only change would break live on the next `[autodeploy]`.
- Follow the phases in §4 **in order**, tick the checkboxes in this file as work lands, and
  add dated notes under §9 (Change log).
- Treat §2 as "confirmed from source, still re-verify", and §3 as "verified OK from source".
- Follow every rule in SKILL.md: **never delete without asking** (includes files, DB rows,
  custom fields), and remember bench does not hot-reload (restart `bench start`) and
  `public/js` needs `bench build --app manufyxinvenzaerp`.
- **Do not touch `frappe-benchv16`** — that is the office bench. Do not touch the live server.
- Many things in SKILL.md describe **v15 internals** (§2.3, §2.9). After the migration, update
  SKILL.md so it describes v16 — it is hand-written and the scan script won't do it.

---

## 1. Target environment

| Item | v15 today (bench1) | v16 target | Note |
|---|---|---|---|
| Frappe | 15.120.1 | version-16 (16.28+ at time of writing) | |
| ERPNext | 15.121.2 | version-16 | |
| india_compliance | 15.31.4 | version-16 | branch exists |
| hrms | 15.64.0 | version-16 | branch exists |
| payments | version-15 | version-16 | branch exists |
| frappe_assistant_core | 2.5.0 (`main`, local commit e50c5c3 of 2026-06-23) | latest `main` | **Supports v16** (verified 2026-09-26): README says "Requires Frappe v15 or v16 and Python 3.10+", and upstream CI (`.github/workflows/ci.yml`) has a matrix entry `frappe-branch: version-16`, Python 3.14, Node 24. Install a **fresh `bench get-app`** of upstream `main` — the bench1 copy is 3 months old and predates that. It has no `required_apps`, and our app does not depend on it. Its Chat UI build needs Node 22+ (v16's Node 24 covers that). |
| Python | 3.10.21 | **3.14** | ERPNext v16 `requires-python >=3.14`. Needs a new bench — no in-place upgrade. |
| Node | 20.18 | **≥ 24** | frappe v16 `package.json` engines |
| MariaDB | 10.11.14 | check the v16 install docs | |
| Redis | 7.0.15 | check the v16 install docs | |
| Bootstrap (desk) | 4.6.2 | 4.6.2 | unchanged — good for our HTML (§2.8) |

Our app's `pyproject.toml` says `requires-python = ">=3.10"` and ruff `target-version = "py310"`.
Every .py file in the app compiles under Python 3.14 with SyntaxWarnings as errors (checked).
Optionally bump ruff to `py314` later — that's cosmetic, not required.

**Site data:** migrate a **copy** of a manufact backup (`bench --site manufact backup --with-files`
on bench1, then `bench --site <newsite> restore …` on the v16 bench, then `bench migrate`).
Never point the v16 bench at the live DB.

---

## 2. Things that WILL break or change — must be handled

### 2.1 BOM class override — HARD BREAK (priority 1)

`drawing_management/bom_class_override.py` (1,655 lines) is a **full copy of ERPNext v15's
`bom.py`**, hooked in through `override_doctype_class["BOM"]`. In v16:

- `BOM Scrap Item` was renamed to **`BOM Secondary Item`**. The fields `scrap_items`,
  `scrap_material_cost`, `base_scrap_material_cost`, `scrap_items_section` and others are gone
  (BOM gets 24 new fields: `secondary_items`, `cost_allocation`, `bom_conf_tab`, …).
  The copy imports `erpnext.manufacturing.doctype.bom_scrap_item.bom_scrap_item` →
  **ImportError** → every BOM form, save and submit fails.
- `erpnext.stock.doctype.stock_entry.stock_entry.get_operating_cost_per_unit` was **removed**
  (the copy imports it inside `add_operations_cost`).
- `erpnext.stock.get_item_details.get_price_list_rate(args, …)` → now `get_price_list_rate(ctx: ItemDetailsCtx, …)`.
- v16 `bom.py` grew from 1,697 to 2,138 lines, so the copy would miss a lot of logic even without the break.
- The copy is **already stale against current v15** (its `add_operations_cost` predates ERPNext's per-operation costing).

Only **5 real customisations** live in that file (diff against v15 `bom.py` = 142 changed lines):

| # | Method | What ours does |
|---|---|---|
| 1 | `before_insert` (new) | default `with_operations = 1`, `routing = "Standard Manufacturing Routing"` |
| 2 | `get_rm_rate` / item-detail fill (≈ line 405) | `if r == "bom_no": continue` — never auto-link sub-BOMs; flat BOM only |
| 3 | `manage_default_bom` | never set a default BOM; clear `Item.default_bom` (long docstring explains why) |
| 4 | material cost loop (≈ line 798) | `if not self.bom_creator and d.is_stock_item:` |
| 5 | exploded items (≈ line 913) | copy `custom_thickness`, `custom_length`, `custom_width` into exploded rows |

**Fix:** rewrite as a **thin subclass** — `class BOM(ERPNextBOM)` that overrides only these
5 methods, re-copying each **from v16's `bom.py`** and re-applying our small change. Everything
else is inherited.

- **Module-level functions** in the file (`get_children`, `item_query`, `make_variant_bom`,
  `get_bom_items`, `get_bom_diff`, `get_list_context`, …) are **ERPNext's own**. Check whether
  anything calls them by *our* dotted path (`grep -rn "bom_class_override\." --include=*.js --include=*.py`,
  including setup.py client scripts and `public/js/bom.js`). If nothing does, delete them from
  our file (ask the user first — SKILL rule), because ERPNext's copies are what the BOM form calls.
  If something does, re-export them from v16: `from erpnext.manufacturing.doctype.bom.bom import get_children, …`.
  SKILL.md warns that "a dead-code sweep flags these" — this is the moment to settle it for real.
- `BOMTree` and `BOMRecursionError` are copies too — import them from ERPNext instead.
- Tests: `verify_no_item_default_bom`, `verify_bom_routing_new_bom`, `verify_bom_routing_trim`,
  `verify_bom_nature_of_work_rate_schedule`, `verify_fg_bom_pp_kg`.
- `verify_no_item_default_bom.py:56` calls `erpnext.stock.get_item_details.get_item_details(frappe._dict({...}))`
  — v16 takes `ctx: ItemDetailsCtx`. Update the test to build an `ItemDetailsCtx`.

> Recommended: do the thin-subclass rewrite **on v15 first** (it is valid there and removes the
> stale-copy risk now), ship it through normal CI, then only re-base the 5 methods on v16.
> If the user prefers to keep v15 untouched, do it on `v16-migration` only.

### 2.2 Customization JSON pointing at fields v16 removed

`<module>/custom/*.json` (synced on every migrate). A property setter on a field that no longer
exists is dead data. A custom field whose `insert_after` target is gone gets pushed to the end of the form.

**Property setters on removed fields — drop them (ask first):**

| Doctype | Field | File |
|---|---|---|
| Job Card | `scrap_items`, `scrap_items_section` | production_management/custom/job_card.json |
| Work Order | `materials_and_operations_tab`, `required_items_section` | production_management/custom/work_order.json |
| Purchase Receipt | `provisional_expense_account` | manufyxinvenzaerp/custom/purchase_receipt.json |

**`insert_after` targets missing in v16 — re-anchor:**

| Doctype | Custom field | insert_after (missing) |
|---|---|---|
| Purchase Order / Purchase Receipt / Supplier Quotation | `is_reverse_charge` | `apply_tds` (India Compliance field — check whether IC v16 still creates it) |
| Sales Order | `gst_section` | `gst_vehicle_type` |
| Tax Category | `gst_state` | `company` |
| Subcontracting Receipt Item | `taxable_value` | `scrap_cost_per_qty` |
| Drawing Item | `inventory_dimension` | `amount` |
| Stock Ledger Entry | `storage_location` | `inventory_dimension` |
| Subcontracting Order | `custom_column_break_tpxcf`, `custom_wip_warehouse` | `custom_return_warehouse`, `custom_source_warehouse` (probably created by setup.py → re-check on the live v16 meta; may be a false alarm) |

Many of these (`is_reverse_charge`, `gst_*`, `taxable_value`) are **India Compliance's own
fields exported into our JSON by accident** (Customize Form export takes everything). Decide
per field whether our app should own it at all. If IC v16 creates it, remove it from our JSON
so the two don't fight over it.

Also: `stock_entry_detail.json` and `subcontracting_receipt_item.json` still mention scrap fields — review.

**No fieldname clashes:** none of our custom fields (JSON or setup.py) uses a fieldname that v16
newly added as a standard field (checked).

Remember the two SKILL.md traps still apply: the sync **never deletes**, and **setup.py wins**
(`after_migrate` runs after the sync).

### 2.3 Child-table grid: the 11-column cap is GONE in v16 (visual change everywhere)

SKILL.md says "Frappe's grid has a hard 11-column budget — the first column past 11 is silently
dropped". **That line is removed in v16.** v15 `grid.js setup_visible_columns` had
`if (total_colsize > 11) return false;`. In v16 it is gone, so **every `in_list_view` column renders**.

Consequences:
- Grids that were silently truncated will suddenly show **all** their columns — most of all
  **Production Plan Item** (26 against 11 per SKILL), plus any grid where `setup.py` "spent the
  budget deliberately" (`layout_purchase_receipt_item_grid`, `layout_stock_entry_detail_grid`,
  `layout_production_plan_item_grid`). Expect wide, cramped or horizontally scrolling grids.
- Hidden-by-budget columns such as `planned_qty`, `warehouse` and `planned_start_date` on PP Item will now **appear**.
- Tests that emulate the v15 budget will report wrong results: `verify_grid_and_tab_layout.py`,
  `verify_nos_labels.py`, `verify_fg_schema.py` (`_visible_grid_columns`),
  `verify_change_request_2026_09_24.py`. Update their emulation to v16 rules.
- Action: go grid by grid and decide which columns should really be `in_list_view` — turn off
  the ones that were only "invisible by accident". Take screenshots before (v15) and after (v16).

`cannot_add_rows` is still **not** a DocField property in v16 (checked `docfield.json`). The
runtime-flag approach in `material_issue_plan.js` still applies.

### 2.4 Desk URL moved: `/app/...` → `/desk/...`

v16 frappe `hooks.py` has `website_redirects`: `/app/(.*)` → `/desk/\1`, and `/app` → `/desk`.
Old links still work, but through a redirect (full page reload instead of in-desk routing, and
they break if someone ever removes the redirect).

Our app hard-codes `/app/…` in **15 places** across: `setup.py` (client scripts),
`drawing_management/rate_schedule_sync.py`, `material_issue_plan.js`, `drawing.js`,
`material_planning.js`, `public/js/purchase_receipt.js`.

- Replace them with `frappe.utils.get_form_link()` / `get_url_to_form()` (Python) and
  `frappe.utils.get_form_link()` / `frappe.set_route()` (JS), so the route comes from the framework.
- Check `erp_manual` and `manual_renderer.js` content, and the case_studies docs, for `/app/` links too.

### 2.5 Subcontracting Order — v16 overlaps with our own fields

- v16 SCO has a **standard `production_plan` field** plus **`reserve_stock`** (stock
  reservation against the PP, via `production_plan_sub_assembly_item`). Ours uses
  **`custom_production_plan`**. As long as our code never fills the standard `production_plan`,
  v16's reservation logic stays asleep. **Keep `reserve_stock` = 0** — our reservations live in
  Material Planning, and two reservation systems on one batch will fight.
  (`grep -rn "\"production_plan\"" subcontracting_management/` and check `create_sco_from_production_plan`.)
- New in v16: **Subcontracting Inward Order** (customer-provided material), plus `subcontracting_inward_order`
  and `is_additional_transfer_entry` on Stock Entry, and `is_subcontracted` on Sales Order.
  We don't use them. Hide the new fields on our forms if they add clutter.
- Status options are the same as v15 (`Draft/Open/Partially Received/Completed/Material Transferred/Partial Material Transferred/Cancelled/Closed`).
  `setup.add_sco_working_status` (Property Setter appending "Working") should still apply — verify after migrate.
- `purchase_order` is still `reqd=1` in v16 → `setup.remove_sco_purchase_order_mandatory` is still needed; verify it applies.
- All methods overridden in `overrides.py` (`CustomSubcontractingOrder`: `validate`,
  `update_status(status, update_modified, update_bin)`, `on_submit`, `on_cancel`,
  `validate_purchase_order_for_subcontracting`, `validate_service_items`, `validate_items`,
  `calculate_*`; `CustomStockEntry.validate_subcontract_order`) **still exist in v16 with the
  same signatures**. But the parent bodies changed. Diff each v16 parent method against what
  ours assumes, especially `validate` / `on_submit` / `on_cancel`, which now also go through
  `buying_controller` / `accounts_controller` / `budget_controller`.

### 2.6 Stock Entry Detail — scrap → secondary

v16 removed `is_scrap_item` and added `secondary_item_type`, `bom_secondary_item`, `valuation_type`,
`against_fg`, `scio_detail`, `landed_cost_voucher_amount` and `customer_provided_item_cost`.
Our non-test code does not read `is_scrap_item` (checked); the scrap references are only in the
BOM copy (§2.1) and `tests/revert_wo_jc_cleanup.py`.

Our Final Stock Entry (`create_finished_goods_entry`, `_final_fg_rows`) and repack flows build
rows by hand. Check that v16's new `validate` doesn't require `valuation_type` /
`secondary_item_type` on our Manufacture rows, and that `is_finished_item` still behaves the same.

`use_serial_batch_fields` still exists in v16 (used in `material_issue_plan_transfer.py`,
`delivery_note.py`, `delivery_plan.py`, `fg_stock.py`) — good. Re-verify the SKILL.md rule
"`Stock Ledger Entry.batch_no` is empty for Purchase Receipt batches (Serial and Batch Bundle)"
on v16. `get_batch_qty` has the same parameters in v16.

### 2.7 ERPNext functions whose signature changed

| Function | v15 | v16 | Where we use it |
|---|---|---|---|
| `erpnext.stock.get_item_details.get_item_details` | `(args: dict\|str, doc, …)` | `(ctx: ItemDetailsCtx, doc, …)` | only `tests/verify_no_item_default_bom.py` |
| `erpnext.stock.get_item_details.get_price_list_rate` | `(args, item_doc, out)` | `(ctx: ItemDetailsCtx, item_doc, out: ItemDetails)` | only the BOM copy (§2.1) |
| `erpnext.stock.doctype.item.item.get_item_details` | same | same signature, now **permission-checked** | only the BOM copy |
| `material_request.make_purchase_order` | `args` default `{}` | `args` default `frappe.flags.args or {}` | tests + MP flows — behaviour same unless flags.args is set |

Same signature in v16 (checked): `sales_order.make_delivery_note`, `sales_order.make_sales_invoice`,
`delivery_note.make_sales_invoice` (all three are in our `override_whitelisted_methods` — keep
the signatures matching), `make_purchase_receipt`, both `make_sales_return`, `get_conversion_factor`,
`apply_warehouse_filter`, `add_variant_item`, `get_item_group_defaults`, `get_batch_qty`,
`india_compliance.tests.before_tests`.

Frappe: every `frappe.*` import we use exists in v16 (checked, including `frappe.types.DF`
and `frappe.tests.utils.FrappeTestCase`, which is now a compatibility alias — v16 prefers
`frappe.tests.IntegrationTestCase`/`UnitTestCase`; migrate the 8 unittest modules later, not required).

### 2.8 Custom HTML must not break — what we render and what to check

**Good news (checked):** desk is still **Bootstrap 4.6.2**; every CSS class used in our HTML
(159 distinct) still exists in v16 frappe/bootstrap styles; every frappe CSS variable we use
still exists (`--mpm-*` are our own, and `--white` was never a frappe variable in v15 either);
no DOM selector our JS uses in `.find()` / `$()` / `closest()` targets a class that v16 removed;
every `grid.*` API we touch (`add_custom_button`, `wrapper`, `grid_rows`, `grid_rows_by_docname`,
`update_docfield_property`, `refresh_row`, `reset_grid`, `get_selected_children`, `docfields`,
`df`, `custom_buttons`, `cannot_add_rows`, `cannot_delete_rows`) still exists in v16 `grid*.js`;
`cur_frm` still exists; `frappe.utils.icon` sprite still has every icon we use (`filetype` was
already missing in v15 — see SKILL).

**Risk is in layout, not in APIs** — v16 restyled the desk (new sidebar, spacing, form widths,
dark-mode tokens). Every HTML producer below must be opened and eyeballed in light **and** dark mode:

| File | `<table>/<tr>/<td>/<th>` count | What it renders |
|---|---|---|
| `subcontracting_management/doctype/material_issue_plan/material_issue_plan.js` | 238 | transfer popups (primary / CNC / CNC-forward), excess plan tab, readiness check, process-loss dialog, return-excess dialog |
| `production_management/doctype/material_planning/material_planning.js` | 166 | batch picker, reservation summary, check mapping / validate stock, consolidate dialogs, view-all |
| `subcontracting_management/doctype/material_issue_plan/material_issue_plan.py` | 52 | batch plan HTML/PDF, consolidate plan HTML/PDF (`get_mip_*_plan_html`, `download_mip_*_pdf`) |
| `setup.py` (client scripts) | 44 | SO / PP / Stock Entry / SCO / SOE client-script HTML |
| `manufyxinvenzaerp/doctype/delivery_challan/delivery_challan.py` | 26 | Delivery Challan / Gate Pass HTML + PDF |
| `public/js/purchase_receipt.js` | 15 | MP allocation display |
| `public/js/supplier_operation_entry.js` | 12 | SOE summary |
| `production_management/page/erp_manual/erp_manual.js`, `public/js/manual_renderer.js` | 12 / 6 | ERP manual page |
| `public/js/batch.js` | 9 | batch usage |
| `drawing_management/doctype/drawing/drawing.js` | 6 | |
| `manufyxinvenzaerp/page/bulk_permissions/bulk_permissions.js` | 4 | Bulk Permissions page |
| `purchase_receipt_management/purchase_receipt.py` | 4 | allocation messages |

HTML-type fields: 8 JSON files (Drawing, Material Planning, Material Issue Plan, plus custom
fields on Sales Order, Batch, SCO, Work Order, Material Planning) and 7 in `setup.py`.

**PDFs:** v16 Print Format gains a `pdf_generator` field (default still `wkhtmltopdf`, with a
Chrome option). `frappe.utils.pdf.get_pdf` is still there. Confirm **wkhtmltopdf is installed on
the v16 bench** (patched-Qt build), then compare each PDF side by side with v15: MIP batch plan,
MIP consolidate plan, Delivery Challan. Watch page breaks, table widths and fonts.

Method for each HTML screen: screenshot on v15 (bench1) → the same record on v16 → compare.
Playwright MCP is available and can do this at desktop and narrow widths.

### 2.9 Other v16 framework changes to keep in mind

- **Desk/workspace redesign:** v16 adds `Workspace Sidebar`, `Desktop Icon`, `Desktop Layout`
  and `Sidebar Item Group`. Our `manufyxinvenzaerp/workspace/manufyx/manufyx.json` is a classic
  Workspace. Check that it appears, that the links work, and whether it needs a sidebar or desktop icon entry.
- **Default sort for NEW doctypes** is `creation` (was `modified`). Existing doctypes keep their JSON
  `sort_field`. Any `frappe.get_all(...)` with no `order_by` that then takes `[0]` is order-dependent — review.
- `@frappe.whitelist()` still allows GET/POST/PUT/DELETE by default — no change to our ~140
  whitelisted methods. Keep `tests/test_whitelist_coverage.py` green.
- `fetch_from` on parent and child rows is still filled in `base_document` (`set_fetch_from_value`)
  — the Material Spec / Grade mirror design (25 child tables) should survive. Confirm with one save.
- `frappe.db.sql` raw queries (heavy use) on standard tables: the column renames found are in
  §2.1 and §2.6 — grep `tabBOM Scrap Item`, `scrap_`, `is_scrap_item` once more on the v16 bench.
- `public/js/production_plan.js` hides `section_break_ucc4`, which no longer exists in v16
  (harmless). But v16 adds **new** sections and fields to our heavily customised forms, and they will show:
  Production Plan `reserve_stock`; SCO `production_plan`, `reserve_stock`, `supplier_currency`;
  Stock Entry `is_additional_transfer_entry`, `subcontracting_inward_order`, reference section;
  Purchase Receipt totals sections; Sales Order 18 new (UTM, totals, `is_subcontracted`,
  `transaction_time`); Item 29 new (pricing tab, tax withholding categories, `production_capacity`);
  BOM 24 new. Decide per form what to hide.
- **Scheduler:** our only job is `daily → delivery_challan.refresh_overdue_gate_passes`. Still valid.
- **Stock Reconciliation is blocked site-wide** by `block_stock_reconciliation`. ERPNext v16's
  `item.py` still creates an opening-stock Stock Reconciliation when an Item is saved with
  `opening_stock` — same as v15, so the behaviour is unchanged, but test item creation.
- **Patches:** our `patches.txt` entries have already run on the manufact copy, so they won't
  run again. A **fresh** v16 install runs them all — `remove_wo_transfer_fields`,
  `remove_sco_transfer_fields` and `fix_bom_item_number_field_type` touch standard doctypes, so
  make them idempotent and tolerant of missing fields.
- `override_doctype_dashboards` for Sales Order and SCO: v16 dashboards may have new
  transactions. Our function should take the `data` it is given and extend it, not replace it.
- India Compliance v16 GST overrides: we import from `india_compliance.gst_india.overrides.transaction`
  (still present). Re-test GST on PO/PR/SI/DN, and e-Waybill if it's used.

---

## 3. Verified OK from source (still smoke-test)

- All 64 `from frappe/erpnext/india_compliance … import …` symbols exist in v16, except the
  two BOM ones in §2.1.
- The 3 ERPNext dotted methods our JS calls directly exist in v16:
  `payment_request.make_payment_entry`, `sales_order.make_delivery_note`, `material_request.make_purchase_order`.
- Python 3.14 compiles the whole app.
- No custom fieldname collides with a new v16 standard field.
- Bootstrap, CSS classes, CSS variables, grid APIs and `cur_frm` all still present (§2.8).

---

## 4. Phased plan (work in this order)

### Phase 0 — Before touching v16 (on bench1, optional but recommended)
- [ ] Take a fresh manufact backup with files, for the v16 trial.
- [ ] Record v15 baselines: run the full test suite (`bench --site manufact run-tests --app manufyxinvenzaerp`
      plus every `verify_*.run`) and save the pass/fail list. Some may already fail on v15 — know which.
- [ ] Take v15 screenshots of every screen in §2.8 and every grid in §2.3, and save PDFs of each print.
- [ ] (Recommended) Rewrite the BOM override as a thin subclass on v15 (§2.1). Ship it through normal CI.
- [ ] (Optional) Clean the tests/ scratch files (`_chk_tmp.py`, `_probe_*.py`, `zz_tmp_*.py`, …) —
      **ask the user before deleting anything**.

### Phase 1 — Stand up and re-verify (v16 bench)
- [ ] Confirm versions: `bench version`, `python --version` (3.14), `node --version` (≥24).
- [ ] `git checkout -b v16-migration` in `apps/manufyxinvenzaerp`.
- [ ] Re-run the checks from §8 against the **installed** v16 apps (not the scratch clones) and
      update §2 and §3 with anything new.
- [ ] Restore the manufact backup copy to a new site. Do not migrate yet — first read the migrate log of a dry run on a second copy if possible.

### Phase 2 — Code fixes that must land before `bench migrate` can succeed
- [ ] §2.1 BOM override → thin subclass on v16's `bom.py`.
- [ ] `bench build --app manufyxinvenzaerp` succeeds under Node 24.
- [ ] App imports cleanly: `bench --site <site> console` → `import manufyxinvenzaerp.hooks`, and
      import every module (walk the package and `importlib.import_module` each one).

### Phase 3 — Migrate
- [ ] `bench --site <site> migrate` — save the full log. Every error or traceback must be
      explained. Watch for failures in `after_migrate` / `setup.py`: `create_custom_fields` with a
      missing `insert_after`, property setters on removed fields, client-script installation,
      `add_sco_working_status`, `seed_material_grades`, `layout_*_grid`.
- [ ] `bench --site <site> clear-cache`, `bench build`, restart `bench start`.
- [ ] Check ERPNext's own v16 patches renamed the BOM scrap data (BOMs with scrap rows → secondary items).

### Phase 4 — Clean-ups after migrate
- [ ] §2.2 property setters and anchors (ask before removing anything from JSON).
- [ ] §2.3 grid columns: decide per grid and update the `layout_*_grid` functions in setup.py.
- [ ] §2.4 `/app/` → framework link helpers.
- [ ] §2.5 SCO: make sure the standard `production_plan` stays empty and `reserve_stock` stays off. Hide the new clutter fields.
- [ ] §2.9 hide the new v16 fields/sections the client doesn't use on PP / SCO / SE / PR / SO / Item / BOM.
- [ ] Re-export changed customizations (`export_customizations(..., sync_on_migrate=True)`).
- [ ] Update the tests that emulate v15 internals (§2.3, §2.1 `get_item_details`).

### Phase 5 — Test (see §5), fix, repeat.

### Phase 6 — CI and deployment
- [ ] `.github/workflows/main.yml`: `python-version: "3.11"` → `"3.14"`, `node-version: "18"` → `"24"`,
      and change frappe/erpnext/hrms/india_compliance/payments checkout branches to `version-16`.
      Check the MariaDB/Redis service container versions.
- [ ] The live server needs a v16 stack (new Python/Node). Plan it with the user as a
      **separate cutover** (maintenance window, full backup, migrate, smoke test, rollback plan).
      The deploy script's automatic code rollback will **not** undo a v16 schema migration —
      rollback means restoring the DB backup onto the old v15 stack.
- [ ] Only merge `v16-migration` → `devbranch` once live is ready to move to v16 (otherwise the
      next `[autodeploy]` pushes v16 code onto a v15 server).

### Phase 7 — Docs
- [ ] SKILL.md: Frappe/ERPNext v16 in the Environment table; rewrite the 11-column grid rule
      (§2.3), the BOM override note (§2.1), `/desk` routes, and anything else found.
- [ ] Run `bash apps/manufyxinvenzaerp/.claude/update_skill.sh` to regenerate app_map / doctypes / hooks / api.
- [ ] `references/deployment.md`: new CI versions and server stack.
- [ ] Close out §9 of this file.

---

## 5. Post-migration test plan

### 5.1 Automated
- [ ] `bench --site <site> run-tests --app manufyxinvenzaerp` (8 unittest modules; `test_whitelist_coverage` must be green).
- [ ] Every `tests/verify_*.py`: `bench --site <site> execute manufyxinvenzaerp.tests.<name>.run`.
      Each must end "ALL n CHECKS PASSED". Loop over them and collect the results; compare with the Phase 0 v15 baseline.
      A new failure is either a v16 break or a test that emulates v15 internals — decide which, then fix.
- [ ] `verify_client_scripts_parse` — every setup.py client script parses (`node --check` under Node 24).

### 5.2 Manual end-to-end (the full chain, one real job, from the restored copy)
Use a job that exists in the restored data, **and** make one brand-new job from scratch.

1. **Masters:** Item create/edit (FG item defaults, batch prefix, UOM, Material Spec/Grade link,
   no default BOM), Material Grade/Spec, Rate Schedule.
2. **Sales Order:** BOM-sheet import (`so_drawing_import`: load → verify → create/submit drawings
   → create BOMs), DUNO warnings, calculated weight, delivery plan, FG lines.
3. **Drawing:** create, revision, final revision, Rate Schedule sync Drawing ↔ BOM ↔ PP (all three directions).
4. **BOM:** create from drawing, save, submit, cost update, routing default, BOM tree view,
   exploded items carry L/W/T, no `Item.default_bom` set. (**Most important after §2.1.**)
5. **Material Planning:** get raw materials, check stock, reserve / unreserve (row and bulk),
   exact match, mapping, reassign batch, cut sheet, excess mapping (virtual/real), consolidate
   dialogs, make MR / auto purchase, finalize.
6. **Buying:** MR → RFQ → SQ → PO → PR (UOM fields, dimension copy-forward, batch
   auto-creation, inspection gate, allocation to MP, `diagnose/retry_mp_allocation`).
7. **Production Plan:** naming, drawing picker, Process Planning rows, supplier mandatory on
   submit, FG nos → kg, create SCO + MIP.
8. **Subcontracting Order:** status Open → Working → Completed, dashboard, cancel cascade to SOE,
   standard `production_plan` stays empty, no stock reservation created.
9. **Material Issue Plan:** refresh raw materials, readiness check, transfer drafts (all 3
   popup types), partial transfer, CNC forward, excess return (Repack with out-rows), process loss,
   completion gate, both PDFs.
10. **Supplier Operation Entry:** create, consumption log hard cap, inspection gate, submit,
    propagation to next op, cancel blocked unless via SCO.
11. **Final Stock Entry (Manufacture):** preview, create, partial, FG batch, sec qty; check the
    GL/SLE valuation looks the same as v15 for the same input.
12. **Selling:** Delivery Note from SO (override), FG by the piece, returns, Sales Invoice from SO and DN (overrides), Payment Request / Payment Entry flag, Customer Fund Usage report.
13. **Delivery Challan / Gate Pass:** returnable, return entry, overdue refresh, PDF.
14. **Stock Reconciliation** still blocked; **Consumable entry** validation.
15. **Reports:** Cut Sheet, Inspection Status, Inventory, Manufyxinvenza Stock Balance (a custom
    copy of a stock report — re-check its SQL against v16 SLE/Bin), Production Report, Excess Material Return.
16. **Pages:** Bulk Permissions, ERP Manual. **Workspace:** Manufyx.
17. **Permissions:** non-Administrator users for each role (store, purchase, production) — v16
    permission checks (like `item.get_item_details`) are stricter.

### 5.3 Visual / HTML regression
- [ ] Every screen in §2.8 compared with the Phase 0 screenshots, in light and dark mode, desktop and narrow width.
- [ ] Every grid in §2.3: correct columns, no unintended extra columns, editable where it should be, row buttons working.
- [ ] Buttons: colours from `mfx_buttons.js` (blue / outlined blue / orange / red / grey) still paint
      — v16 may change button markup or class names. Check the group-button painting in particular.
- [ ] All PDFs match v15 (layout, totals, page breaks).
- [ ] No JS console errors on any customised form (Playwright `browser_console_messages`).

### 5.4 Data integrity after migrate (compare the v15 copy with the v16 copy)
- [ ] Stock balance per item / warehouse / batch identical (use `get_batch_qty`, not raw SLE `batch_no`).
- [ ] Batch `sec_qty` values identical.
- [ ] Counts of MP / MIP / SCO / SOE / PP by status identical; SCO statuses not recomputed wrongly.
- [ ] BOM costs unchanged for a sample of submitted BOMs; scrap → secondary data migrated.
- [ ] Custom fields present on each doctype (count by `dt`, compare with v15).

---

## 6. Risk summary

| Risk | Level | Section |
|---|---|---|
| BOM override import failure → BOM unusable | **High / certain** | 2.1 |
| Grids show far more columns (layout, usability) | **Medium / certain** | 2.3 |
| SCO v16 reservation / `production_plan` interacting with our flow | Medium | 2.5 |
| Stock Entry Manufacture rows vs v16 validation (secondary/valuation types) | Medium | 2.6 |
| New v16 fields cluttering customised forms | Low–Medium | 2.9 |
| `/app` links go through a redirect | Low | 2.4 |
| Dead property setters / field anchors | Low | 2.2 |
| HTML visual drift from the desk restyle | Low–Medium | 2.8 |
| frappe_assistant_core v16 compatibility | Low (upstream supports v16; use latest `main`) | 1 |
| Live cutover / rollback | High impact, controllable | Phase 6 |

---

## 7. Do / Don't

- DO work on the `v16-migration` branch; keep `devbranch` deployable to v15 until cutover.
- DO migrate a **copy** of the data; keep the v15 bench1 untouched as the reference.
- DO ask before deleting any file, custom field, property setter or record.
- DO re-verify each §2 item on the installed v16 code before changing anything.
- DON'T touch `frappe-benchv16` (office) or the live server.
- DON'T copy ERPNext files wholesale again (the BOM lesson) — subclass and override single methods.
- DON'T turn on v16 stock reservation (`reserve_stock`) on PP/SCO — Material Planning owns reservations.
- DON'T push with `[autodeploy]` from the migration branch.

---

## 8. Re-check commands (run on the v16 bench, from `apps/manufyxinvenzaerp/manufyxinvenzaerp`)

```bash
# 1. Every frappe/erpnext/IC symbol we import still exists (prints only failures)
../../../env/bin/python - <<'EOF'
import ast, os, importlib
bad = 0
for dp, _, fs in os.walk('.'):
    for f in fs:
        if not f.endswith('.py'): continue
        for n in ast.walk(ast.parse(open(os.path.join(dp, f)).read())):
            if isinstance(n, ast.ImportFrom) and n.module and n.module.split('.')[0] in ('frappe','erpnext','india_compliance','hrms'):
                try:
                    m = importlib.import_module(n.module)
                    for a in n.names:
                        if not hasattr(m, a.name):
                            try: importlib.import_module(f"{n.module}.{a.name}")
                            except Exception: bad += 1; print('MISSING', n.module, a.name, os.path.join(dp, f))
                except Exception as e: bad += 1; print('MODULE', n.module, e, os.path.join(dp, f))
print('problems:', bad)
EOF
# (run inside `bench --site <site> console` if frappe needs a site context for imports)

# 2. Leftover scrap / removed-field references
grep -rnE "scrap_item|scrap_items|BOM Scrap|is_scrap_item|scrap_material_cost|get_operating_cost_per_unit" --include=*.py --include=*.js --include=*.json . | grep -v /tests/

# 3. Hard-coded desk routes
grep -rnE "[\"'\`]/app/" --include=*.py --include=*.js --include=*.html . | grep -v /tests/ | grep -v public/dist

# 4. Grid cap really gone? (expect no output)
grep -n "total_colsize > 11" ../../frappe/frappe/public/js/frappe/form/grid.js

# 5. Property setters / insert_after pointing at fields missing in v16: after migrate, in console:
#    for each <module>/custom/*.json, compare field_name / insert_after with frappe.get_meta(dt).fields
```

---

## 9. Change log

- 2026-09-26 — Plan written on bench1 from a source-level comparison (ERPNext/IC version-16
  clones plus frappe-bench11 Frappe 16.28). No code changed yet.
- 2026-09-26 — frappe_assistant_core confirmed v16-compatible (README + upstream CI matrix
  on version-16 / Py 3.14 / Node 24, commit 99deda4). Install latest upstream `main`.
