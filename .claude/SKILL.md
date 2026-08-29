---
name: project1-manufyxinvenzaerp
description: >
  Load this skill whenever the user mentions: manufyxinvenzaerp, manufact site,
  drawing_management, item_management, material_request_management,
  production_management, production_plan_management, purchase_order_management,
  purchase_receipt_management, subcontracting_management, rfq_management,
  sq_management, Material Planning, Process Planning, Drawing, BOM override,
  Supplier Operation Entry, or any doctype/module in this app.
---

# Project: manufyxinvenzaerp

## Environment

| Key         | Value                                                    |
|-------------|----------------------------------------------------------|
| Bench       | frappe-bench1                                            |
| Site        | manufact                                                 |
| App         | manufyxinvenzaerp                                        |
| App root    | apps/manufyxinvenzaerp/                                  |
| Python pkg  | apps/manufyxinvenzaerp/manufyxinvenzaerp/                |
| Frappe      | v15                                                      |
| ERPNext     | v15                                                      |

## First thing every session

**Read `.claude/references/app_map.md` before doing anything else.**
It is the single source of truth for file paths, method names, and module layout
and is regenerated automatically on each git commit.

## Safety rule — never delete without asking first

**Never delete any file, database record, or other data — including your own
scratch/debug scripts and stray files you didn't create — without asking the
user for explicit permission first.** This applies even when a permission
mode that bypasses tool-call prompts (e.g. auto-accept) is active; that mode
governs tool-call approval, not this rule. Ask before running `rm`,
`frappe.delete_doc`, dropping/truncating anything, or any other irreversible
removal — no exceptions for "it's just a temp file" or "I made it, so it's
mine to clean up." If a file turns out to be unfamiliar or another party's
in-progress work, leave it alone and flag it instead of deleting it.

(This was violated once: a debug script was deleted via `rm -f` — including,
in one case, another party's uncommitted scratch file — without asking.
Ask first, every time, going forward.)

## Reference files — when to read what

| File                                | Read when …                                                                       |
|-------------------------------------|-----------------------------------------------------------------------------------|
| `.claude/references/app_map.md`     | Any task — always read first; contains full file inventory and method index       |
| `.claude/references/doctypes.md`    | Adding/changing a doctype, controller, or child table                             |
| `.claude/references/hooks.md`       | Touching doc_events, override_doctype_class, or app lifecycle hooks               |
| `.claude/references/api.md`         | Adding or calling a `@frappe.whitelist()` method; checking existing API surface   |
| `.claude/references/deployment.md`  | Running bench commands, migrating, restarting, the CI pipeline and deploy backups |
| `.claude/references/client_change_request_progress.md` | Continuing the in-progress client change request — status of every phase, what's done, what's next |

## App architecture overview

```
manufyxinvenzaerp/
├── drawing_management/       # Drawing → BOM creation; BOM class override
│   ├── bom_class_override.py # Overrides ERPNext BOM with custom logic
│   ├── drawing_utils.py      # Whitelisted helpers: mark_as_final_revision,
│   │                         #   create_bom_from_drawing,
│   │                         #   create_production_plan_from_bom, parse_drawing_items_csv
│   ├── so_drawing_import.py  # The Sales Order BOM-sheet import: load, verify,
│   │                         #   create/submit drawings, create BOMs
│   └── doctype/
│       ├── drawing/          # Drawing doctype (controller + client JS)
│       ├── drawing_item/     # Child table for drawing line items
│       ├── nature_of_work/   # Master for work classification
│       └── production_plan_bom_raw_material/  # Child table
│
├── item_management/          # Item validation (batch config, UOM, item groups)
├── material_request_management/  # Material Request hooks + UOM custom field API
├── purchase_order_management/    # PO hooks + UOM custom field API
├── purchase_receipt_management/  # PR hooks, batch auto-creation on insert
├── rfq_management/           # RFQ validation, copies from MR item
├── sq_management/            # Supplier Quotation hooks + UOM API
│
├── production_management/    # Job Card, Stock Entry hooks; Material Planning doctype
│   ├── job_card.py           # validate_job_card, before_submit_manufacture_stock_entry
│   ├── stock_entry.py        # validate/on_submit/on_cancel; batch reservation release
│   ├── production_utils.py   # routing/workstation helpers; whitelisted: get_routing_operations_for_bom,
│   │                         #   get_raw_materials_for_job_card
│   └── doctype/
│       ├── material_planning/          # Core planning doctype — largest controller
│       ├── cut_sheet/                  # One plate's nesting plan, shared across jobs
│       ├── manufyx_decision_log/       # Append-only: who reserved/reassigned/rounded up
│       ├── inspection_entry/           # QC result; also covers incoming goods
│       ├── process_planning/           # Process routing doctype
│       ├── job_card_raw_material/      # Child table
│       ├── material_planning_*         # Child tables: available_raw_material, bom_item,
│       │                               #   material_mapping, raw_material, unavailable_item
│       ├── production_plan_available_raw_material/
│       ├── storage_location/           # Master
│       └── store_location/             # Master
│
├── production_plan_management/   # Production Plan hooks
│   └── production_plan.py        # after_save_production_plan, make_material_request.
│                                 #   Also holds a dimension-aware rewrite of ERPNext's
│                                 #   get_items_for_material_requests that NOTHING CALLS —
│                                 #   never wired up via override_whitelisted_methods.
│                                 #   Left in place pending a decision.
│
├── subcontracting_management/    # Subcontracting Order override; Supplier Operation Entry
│   ├── overrides.py              # CustomSubcontractingOrder class
│   ├── subcontracting.py         # Whitelisted: create_sco_from_production_plan,
│   │                             #   create_supplier_operation_entries
│   │                             #   (Work Order / Job Card removed 2026-08-20; the
│   │                             #    SCO-keyed transfer functions removed 2026-08-24,
│   │                             #    superseded by material_issue_plan_transfer.py)
│   └── doctype/
│       ├── supplier_operation_entry/   # Custom doctype for subcontracting ops
│       └── supplier_operation_item/    # Child table
│
├── config/                   # Frappe app config (__init__.py only)
├── <module>/custom/          # Custom Field + Property Setter, one file per doctype.
│                             #   112 files, 848 fields, 337 property setters.
│                             #   Replaced fixtures/ on 2026-08-18 — see below.
├── manufyxinvenzaerp/page/   # Desk pages: bulk_permissions
├── public/js/                # Client-side JS injected into core doctypes:
│   │                         #   item.js, bom.js, production_plan.js,
│   │                         #   purchase_order.js, purchase_receipt.js
├── patches/                  # Data migration patches
└── tests/                    # 102 files, two kinds:
    ├── test_*.py             #   8 unittest modules, run by `bench run-tests`
                              #   and by CI. test_whitelist_coverage is the one to
                              #   keep green: it checks every dotted path the front
                              #   end calls is actually whitelisted, after a lost
                              #   decorator shipped a broken Reserve button to live.
    └── verify_*.py           #   86 standalone checks, each with a run() called
                              #   directly: `bench --site manufact execute
                              #   manufyxinvenzaerp.tests.<name>.run`
                              #   They print OK/FAIL per assertion and finish with
                              #   "ALL n CHECKS PASSED". Each one opens with WHY it
                              #   exists — the bug it was written for — so a failure
                              #   is readable without digging up the history.
```

## Coding conventions

- **Hook pattern**: event handlers are top-level functions with signature `(doc, method)`,
  located in `<module>/<doctype_name>.py` or `<module>/<concern>.py`. Never use Document
  subclasses for ERPNext standard doctypes — use `doc_events` in hooks.py instead.
- **Whitelist API**: `@frappe.whitelist()` on standalone functions; called from JS via
  `frappe.call({ method: 'manufyxinvenzaerp.<module>.<file>.<fn>' })`.
- **Private helpers**: prefix with `_` (e.g. `_recalculate_qty`, `_check_missing_fields`).
  Consistent across all modules.
- **Class overrides**: `override_doctype_class` in hooks.py points to a class that extends
  the ERPNext base class (e.g. `BOM(ERPNextBOM)`, `CustomSubcontractingOrder`).
- **Custom UOM fields**: each procurement/supply-chain doctype has a whitelisted
  `get_<X>_item_uom` link-field query (PO, PR, MR, SQ).
- **Custom Field / Property Setter**: NOT fixtures any more (changed 2026-08-18). They live in
  per-doctype `<module>/custom/<doctype>.json` files — 112 files, 848 custom fields, 337 property
  setters — synced on every `bench migrate` by Frappe's own `sync_customizations`. Two things
  follow from that, and both have caught people out:
    - The sync only INSERTS and UPDATES. It never deletes, so removing a field from a JSON file
      does not remove it from a site; it just stops being managed. Delete it in the UI as well.
    - `setup.py` still creates ~140 of these fields through `create_custom_fields`, and it runs on
      `after_migrate`, AFTER the sync. So where the two disagree, **setup.py wins**. If you edit a
      field in Customize Form and re-export it, check `setup.py` does not define it differently or
      your change is overwritten on the next migrate.
  Re-export one doctype with `frappe.modules.utils.export_customizations(module, doctype,
  sync_on_migrate=True)` — the same function Customize Form's "Export Customizations" button calls.
  A file living in a module that is not in `modules.txt` will never sync, so keep them under the
  five registered modules.
- **Batch secondary qty**: several controllers track `sec_qty` on Batch records and
  release/restore on Stock Entry submit/cancel. The adjustment is a single atomic UPDATE
  (`_reduce_batch_sec_qty`) — never read-modify-write, or two entries consuming one batch
  lose a write between them.
- **Every kilo sent to a supplier must land somewhere, and the ledger is the judge.**
  The chain is: transfer → the Final Stock Entry consumes what the DRAWING needed
  (`_consumption_for_completed` caps each share at `drawing_planned_weight`/`reqd_kg`, not
  at what was sent — whole pieces go out, a 5 m length to make a 340 mm part) → the excess
  return is a **Repack** that takes the off-cut OUT of the supplier warehouse and brings it
  home as a new batch → whatever the supplier still cannot account for is **Process Loss**,
  written off by `create_mip_process_loss_entry` with a mandatory reason.
  Three traps live here:
    - The return used to be a `Material Receipt` with **no source warehouse** — it created
      stock while the same kilos stood at the supplier and were then consumed. If you touch
      `create_mip_excess_return_entry`, keep the out rows. It falls back to a plain receipt
      only when the plan has **no supplier warehouse** (excess claimed off another plan's
      table), where no double-count is possible.
    - `_get_supplier_wh_consumption_items` nets on `custom_sco_ref`/`subcontracting_order`.
      Any entry that moves this job's material must carry one, or the netting cannot see it.
    - `_maybe_mark_completed` gates on `_unaccounted_weight`, which reads the **stock ledger**
      (`_job_stock_at_supplier`), not the summary fields — those are derived from the plan's
      own rows and can be wrong. Keep it that way, or the plan closes over stranded stock.
  **"Billed to Consume" was removed on 2026-08-29** and must not come back: material that
  does not return is Process Loss. The cost consequence was accepted — it used to land on
  the job's finished goods, it now lands on the write-off account.
- **A Supplier Operation Entry is not cancellable on its own.** `before_cancel_supplier_operation_entry`
  throws unless `doc.flags.mfx_cancelled_by_sco` is set, which only the two SCO-cancel cascades
  do (`overrides.CustomSubcontractingOrder._cancel_and_delete_soes` and
  `subcontracting.on_cancel_subcontracting_order`). The reason is that the SCO's Operations tab,
  the next operation's `available_to_consume_nos` and the SCO Drawing Items all report from
  SUBMITTED entries — a cancelled one leaves the order quoting a quantity nothing accounts for.
  If you add a third cascade, set that flag or it will be blocked.
- **Subcontracting Order status is derived, not stored, on PP-flow orders.**
  `CustomSubcontractingOrder.update_status` overrides ERPNext's for orders with a
  `custom_production_plan`: Open → Working (any operation has Consumption Log qty) → Completed
  (`custom_all_ops_complete` AND a SUBMITTED `Manufacture` Stock Entry for the SCO). ERPNext's own
  rules are unreachable there — no Subcontracting Receipt, no `supplied_items` — which is why every
  such order sat on "Open" for its whole life before this. It is recomputed by `refresh_sco_status`
  from the SOE `on_update`/`on_submit` hooks and from Stock Entry submit/cancel, so a new event that
  changes either input must call it too. "Working" is not a core option: `setup.add_sco_working_status`
  appends it via Property Setter, and without that the next ordinary save of an order fails Select
  validation.
- **Work Order and Job Card carry NO customizations.** Every field, client script, hook and
  helper this app once added to them was removed — first disabled under the client's Phase 0.4
  change request, then deleted outright on 2026-08-20 (1,827 lines). Subcontracting Order and
  Operation Entry do that work instead. Do not re-add anything to those two doctypes without
  checking why they were reverted.
- **`bom_class_override.py` is a copy of ERPNext's `bom.py`.** Its module-level functions
  (`get_children`, `item_query`, `make_variant_bom`, `get_bom_items`, `get_list_context`) are
  ERPNext's own, called by the BOM form and tree view by dotted path. A dead-code sweep will
  flag them as unreferenced because nothing in THIS app calls them. Removing them breaks the
  BOM form.
- **No scheduler_events** are registered (all commented out in hooks.py).

## This bench does not hot-reload

`bench start` runs the web server with Werkzeug's auto-reloader enabled, and it does
not work here -- touching a file leaves the serving child process untouched. Verified,
not assumed: `touch` on a controller, then watch the child PID stay put.

So **a code change has no effect on the local site until `bench start` is restarted**
(Ctrl+C in that terminal, then `bench start`). `bench restart` is a no-op on this bench
-- it is for supervisor/systemd, and this runs under honcho.

This costs real time when it is forgotten: a fix lands, the screen keeps showing the old
behaviour, and the obvious conclusion is that the fix was wrong. Two separate bugs were
re-reported that way. Check the serving process's start time against the file's mtime
before doubting the code:

```bash
ps -eo pid,lstart,cmd | grep "frappe serve" | grep -v grep
stat -c '%y' <the file you changed>
```

A fresh interpreter -- `bench console`, `bench execute`, `bench run-tests` -- always has
the current code, which is why a verify script can pass while the browser still fails.

**`public/js/` is bundled, so it needs a build as well as a reload.** Anything under
`manufyxinvenzaerp/public/js/` is served from `public/dist/`, and editing the source
changes nothing until:

```bash
bench build --app manufyxinvenzaerp
```

Doctype JS (`.../doctype/<name>/<name>.js`) and Client Scripts installed from `setup.py`
do not need the build -- a `bench migrate` and a browser reload are enough. Getting these
two the wrong way round costs the same hour as forgetting the reloader.

## Batch quantities do not live in the ledger's batch_no

`Stock Ledger Entry.batch_no` is empty for anything received through a Purchase Receipt:
Frappe v15 records the batch in a **Serial and Batch Bundle** instead, and only some
flows (Stock Entry rows written with `use_serial_batch_fields`) fill the column in.

So `SUM(actual_qty) ... GROUP BY batch_no` silently reports **zero for exactly the
batches most likely to be picked**. It has produced two wrong readings here -- once
reporting all 227 batches on the site as empty, once nearly costing a batch picker its
warehouse filter.

Use ERPNext's own helper, which handles both storage models:

```python
from erpnext.stock.doctype.batch.batch import get_batch_qty
get_batch_qty(batch_no=b, warehouse=w, item_code=i)   # -> float
get_batch_qty(batch_no=None, warehouse=w)             # -> [{batch_no, warehouse, qty}]
```

Note the second form: passing `warehouse=None` returns a LIST, not a number, so
`flt(get_batch_qty(batch_no=b, warehouse=None))` is 0.0 for every batch on earth.

## Quick bench commands

```bash
# Run from /home/craft/frappe-bench1/

# Apply DB migrations after code changes
bench --site manufact migrate

# Clear redis + file cache
bench --site manufact clear-cache

# Build JS/CSS assets
bench build --app manufyxinvenzaerp

# Restart workers and web server
bench restart

# Re-export ONE doctype's customizations after changing its fields in the UI.
# There is no export-fixtures step any more — see "Custom Field / Property Setter".
bench --site manufact console
>>> from frappe.modules.utils import export_customizations
>>> export_customizations("Production Management", "Material Planning", sync_on_migrate=True)

# Run app tests
bench --site manufact run-tests --app manufyxinvenzaerp

# Run a single test file
bench --site manufact run-tests --module manufyxinvenzaerp.tests.test_material_planning

# Console / REPL
bench --site manufact console

# Reseed sample data helper
bench --site manufact execute manufyxinvenzaerp.sample_data.create_sample_data
```

## Deployment and CI

> **A commit without `[autodeploy]` in its message ships nowhere.** Pushing `devbranch`
> is not deploying. The tag must be in the message of the commit at the HEAD of the push
> -- `contains(github.event.head_commit.message, '[autodeploy]')` -- so a tagged commit
> carries every untagged one before it along with it, and an untagged one at the head
> leaves the whole branch sitting on the remote doing nothing. Eighteen commits once
> accumulated that way before anybody noticed.

The pipeline is `.github/workflows/main.yml`, triggered by a push to `main`. A push to
`devbranch` whose commit message contains `[autodeploy]` is merged to `main` by
`auto-merge-devbranch.yml`, which is what starts it.

  1. **Test gate** — spins up a throwaway bench with MariaDB and two Redis service
     containers, installs the app, and runs the suite. It must pass before anything is
     deployed. The system-dependency step installs nothing when the runner image already
     has what is needed; it used to hang for six minutes on a stalled apt mirror.
  2. **SSH Deploy** — only runs when the repository variable `LIVE_DEPLOY` is `true`
     (Settings → Secrets and variables → Actions → Variables). Unset it to exercise CI
     without touching the live server.

Every deploy takes a database backup BEFORE anything is touched, checks it with `gzip -t`,
and copies it to `frappe-bench/deploy-backups` — out of Frappe's own backup folder, which
it prunes on its own schedule. Last 10 kept. Any failure rolls the code back to the commit
the server was on and restarts it; uncommitted edits found on the server are stashed, not
discarded. The database is deliberately NOT restored automatically — that would discard
whatever users did since the backup — so the log prints the restore command instead.

## Regenerating this knowledge base

Run `.claude/update_skill.sh` from the app root. It rewrites the four generated files —
`app_map.md`, `doctypes.md`, `hooks.md` and `api.md` — by rescanning the source. It is also
wired to the post-commit git hook, so it runs after every commit.

`SKILL.md` itself is hand-written and is NOT regenerated: anything above that a script
cannot infer — why Work Order carries no customizations, which sweeps produce false
positives, which of two mechanisms wins — has to be edited here by hand.
