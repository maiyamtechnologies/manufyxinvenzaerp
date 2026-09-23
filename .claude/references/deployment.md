# Deployment

## Local (this bench)

```bash
cd /home/craft/frappe-bench1
bench --site manufact migrate          # apply schema + sync custom/*.json
bench --site manufact clear-cache
bench build --app manufyxinvenzaerp
bench restart
```

A migrate takes about 70 seconds and prints one "Updating customizations for <doctype>"
line per file — 112 of them. Anything less means a file is not syncing; check it carries
`"sync_on_migrate": 1` and sits under a module listed in `modules.txt`.

## Custom fields are no longer fixtures

Changed 2026-08-18. There is no `fixtures/` directory and no `export-fixtures` step. Each
doctype's Custom Fields and Property Setters live in `<module>/custom/<doctype>.json` and
are synced by Frappe on every migrate.

To re-export one doctype after changing its fields in the UI:

```bash
bench --site manufact console
>>> from frappe.modules.utils import export_customizations
>>> export_customizations("Production Management", "Material Planning", sync_on_migrate=True)
```

Two traps:

- The sync only inserts and updates. Deleting a field from a JSON file does not remove it
  from any site — it just stops being managed.
- `setup.py` creates ~140 of the same fields on `after_migrate`, which runs AFTER the sync.
  Where the file and `setup.py` disagree, setup.py wins.

## Pipeline

`.github/workflows/main.yml`, on push to `main`. A push to `devbranch` tagged in the commit
message is merged to `main` by `auto-merge-devbranch.yml`, which triggers it.

| Job | What it does | Gate |
|-----|--------------|------|
| Read deploy flags | Looks for `[urgentfix]` in the merge commit and in every commit in the push | always |
| Run App Test Suite | Throwaway bench + MariaDB + 2 Redis containers, installs the app, runs the suite | skipped when `[urgentfix]` |
| SSH Deploy | Backup, pull, build, clear-cache, migrate, restart on the live server | `vars.LIVE_DEPLOY == 'true'` **and** the test job succeeded *or was skipped* |

Set `LIVE_DEPLOY` under Settings → Secrets and variables → Actions → Variables. Unset it to
run CI without touching production.

### Two tags

| Tag | Test suite | Everything else |
|-----|-----------|-----------------|
| `[autodeploy]` | runs, and must pass | backup, pull, build, migrate, restart, rollback on failure |
| `[urgentfix]` | **skipped** | identical |

`[urgentfix]` trades the warning, not the safety net: the backup, the `gzip -t` check and
the rollback all still happen. The Deploy Log record is stamped **Tests Skipped**, so a
deploy that went out untested stays identifiable long after the run has scrolled off.

Three things that look like details and are not:

- The merge commit carries the tag **deliberately**. `gh pr merge` writes GitHub's own
  subject ("Merge pull request #N from …") and would drop `[urgentfix]` on the floor, so
  `auto-merge-devbranch.yml` passes `--subject` with the tag in it. `main.yml` reads
  `github.event.head_commit.message`, which on a merge is that commit.
- The deploy job needs `!cancelled()`. A skipped `needs` job normally skips everything
  downstream, so without it an urgent fix would merge and then deploy **nothing at all** —
  the quietest possible way to fail.
- It still refuses a *failed* test. The condition names the two allowed results
  (`success`, `skipped`) rather than excluding `failure`, which also covers a test job
  that is cancelled or times out.

### Deploy Log in the ERP

The pipeline writes a log per deploy to `$BENCH_PATH/Auto-deploy-logs` and keeps the last
20. That is readable only over SSH — which is exactly the person who cannot read it when a
deploy fails out of hours. `manufyxinvenzaerp/deploy_log.py` copies the same log into a
**Deploy Log** record at the end of every run, on both the success and the rollback path.

- Status is `Completed`, `Rolled Back` or `Failed`; a failure also carries **Failed Step**
  and an **Error Summary** (the last 30 lines), with the whole log underneath.
- Called with `bench execute` from the deploy script — on the server, inside the bench that
  just deployed. No token, no inbound port.
- Commit sha/message/branch are read from git **on the server**, not passed through the
  shell: a commit message with a quote in it would otherwise have to survive two shells.
- It cannot fail a deploy. Everything is caught Python-side and the call ends in `|| true`.
  A deploy that worked being reported as failed because its *logging* failed is the worst
  of both outcomes.
- Records prune to the last 20, matching the server, so a record never outlives the file it
  points at. `_prune()` slices in Python — `limit_start` with `limit_page_length=0` returns
  **everything** in Frappe, and the first version of it deleted the whole table.

## Deploy safety

Before anything is touched:

1. `bench backup`, then the dump is checked with `gzip -t` — not merely checked for
   existence. A truncated dump passes an existence check and fails when it is needed.
2. It is copied to `frappe-bench/deploy-backups`, out of Frappe's own backup folder, which
   Frappe prunes on its own schedule. The site_config.json goes with it. Last 10 kept.
3. Uncommitted changes found in the server's working tree are stashed with a timestamp,
   never discarded.

If any step fails — pull, build, cache, migrate, restart — the code is reset to the commit
the server was on, rebuilt and restarted, so the site returns to the version that worked.

The database is **not** restored automatically. That would discard every transaction made
since the backup minutes earlier. The log and the Telegram message print the command:

```bash
bench --site erp.manufyx.co.in restore <path in deploy-backups>
```

## Live server

- Bench: `/home/manufyxv15/frappe-bench`
- Site: `erp.manufyx.co.in`
- Deploy logs: `frappe-bench/Auto-deploy-logs/` (last 20)
- Pre-deploy backups: `frappe-bench/deploy-backups/` (last 10)
