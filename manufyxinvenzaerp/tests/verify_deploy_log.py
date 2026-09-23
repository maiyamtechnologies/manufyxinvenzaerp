"""A deploy can be checked from the ERP, and an urgent fix can skip the test gate.

Two things this covers, both of which only ever run on the live server, where they
cannot be tried out by hand without deploying something.

1. Deploy Log. The pipeline writes a full log per deploy to Auto-deploy-logs on the
   server and keeps the last 20. That is readable only over SSH -- which is exactly
   the person who cannot read it when a deploy fails out of hours. record() copies
   the same log into a Deploy Log record with a status on it, and prunes to the same
   count the server keeps, so a record never outlives the file it points at.

   The rule that matters: record() must NEVER raise. It is called from the deploy
   script, and a deploy that worked being reported as failed because its logging
   failed is worse than not logging at all. Checks 2 and 3 push rubbish into it --
   bad status, missing file, no arguments at all -- and require a record each time.

   _prune() is checked properly rather than trusted, because its first version
   deleted every record instead of the old ones: it asked for limit_start=20 with
   limit_page_length=0, and "no limit" in Frappe drops the offset with it, so the
   query returned everything. record() returned a name and the table was empty.

2. [urgentfix]. Same merge, same deploy, same backup and rollback as [autodeploy] --
   the test suite is skipped and nothing else changes. The wiring is easy to get
   subtly wrong: a skipped `needs` job normally skips everything downstream, so
   without !cancelled() on the deploy job an urgent fix would merge and then deploy
   nothing at all, which is the quietest possible way to fail.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_deploy_log.run
"""

import os

import frappe

checks = []
_made = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-60s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _log_file():
    """A small log on disk to read, in the app's own tests directory."""
    path = os.path.join(frappe.get_app_path("manufyxinvenzaerp"), "tests",
                        "_deploy_log_sample.log")
    with open(path, "w") as fh:
        fh.write("AUTO DEPLOY STARTED\n[STEP 4/6] Bench Migrate\n"
                 "ERROR: bench migrate failed with exit code 1\nlast line\n")
    return path


def _workflow(name):
    """Load a workflow file from the repo root.

    get_app_path returns the PYTHON PACKAGE (apps/manufyxinvenzaerp/manufyxinvenzaerp),
    so the repo root is one dirname up -- not two, which lands in apps/ and finds
    nothing.
    """
    import yaml
    repo = os.path.dirname(frappe.get_app_path("manufyxinvenzaerp"))
    path = os.path.join(repo, ".github", "workflows", name)
    with open(path) as fh:
        raw = fh.read()
    return yaml.safe_load(raw), raw


def run():
    # Cleanup in a finally: these records are committed by record() as they are
    # made, so an exception half way through would otherwise leave them behind in
    # a real table on a real site.
    path = _log_file()
    try:
        _run(path)
    finally:
        _cleanup(path)
    _summary()


def _run(path):
    from manufyxinvenzaerp.deploy_log import record, KEEP_RECORDS

    print("=== 1. The record carries the log and a status ===")
    name = record(status="Rolled Back", log_file=path, started="2026-09-23 14:00:00",
                  site="erp.example", failed_step="bench migrate failed",
                  trigger_tag="urgentfix", tests_skipped="1")
    _made.append(name)
    check("a record is created", bool(name), True)
    doc = frappe.get_doc("Deploy Log", name)
    check("  status is kept", doc.status, "Rolled Back")
    check("  the log text is stored", "bench migrate failed" in (doc.log or ""), True)
    check("  the failing step is named", doc.failed_step, "bench migrate failed")
    check("  an urgent fix is marked tests-skipped", doc.tests_skipped, 1)
    # Commit details are read from git on the server rather than passed through two
    # shells, so a commit message with a quote in it cannot break the deploy.
    check("  the commit is read from git, not passed in", bool(doc.commit_sha), True)
    check("  a failure carries a tail summary", bool(doc.error_summary), True)

    print()
    print("=== 2. It cannot fail the deploy that called it ===")
    for label, kwargs in (
        ("an unknown status", {"status": "Banana", "log_file": path}),
        ("a log file that is not there", {"status": "Completed", "log_file": "/no/such.log"}),
        ("no arguments at all", {}),
    ):
        got = record(**kwargs)
        _made.append(got)
        check("  %s still produces a record" % label, bool(got), True)
    bad = frappe.get_doc("Deploy Log", _made[1])
    check("  an unknown status is not stored raw",
          bad.status in ("In Progress", "Completed", "Failed", "Rolled Back"), True)
    missing = frappe.get_doc("Deploy Log", _made[2])
    check("  a missing file is said so in the log field",
          "not found" in (missing.log or ""), True)

    print()
    print("=== 3. Old records are pruned, and only the old ones ===")
    before = frappe.db.count("Deploy Log")
    for _ in range(3):
        _made.append(record(status="Completed", log_file=path, site="erp.example"))
    after = frappe.db.count("Deploy Log")
    # Either it grew by 3, or it was already at the cap and stayed there.
    check("  the table never exceeds the cap", after <= KEEP_RECORDS, True)
    check("  and did not empty itself", after > 0, True)
    if before + 3 <= KEEP_RECORDS:
        check("  grew by exactly the three added", after, before + 3)
    newest = frappe.get_all("Deploy Log", pluck="name", order_by="creation desc", limit=1)
    check("  the newest record survives the prune", newest[0] in _made, True)

    print()
    print("=== 4. The form is a record, not a document to edit ===")
    meta = frappe.get_meta("Deploy Log")
    check("  it can only be created programmatically", bool(meta.in_create), True)
    for fn in ("status", "log", "failed_step", "commit_sha", "tests_skipped"):
        check("  %s is read-only" % fn, bool(meta.get_field(fn).read_only), True)
    perms = [p for p in meta.permissions if p.role == "System Manager"]
    check("  System Manager can read but not write",
          (bool(perms), bool(perms and not perms[0].write), bool(perms and perms[0].delete)),
          (True, True, True))

    print()
    print("=== 5. [urgentfix] skips the gate and still deploys ===")
    main, main_raw = _workflow("main.yml")
    jobs = main["jobs"]
    check("  a prepare job reads the tag once", "prepare" in jobs, True)
    check("  the test job is skipped on urgentfix",
          jobs["test"].get("if"), "needs.prepare.outputs.urgent != 'true'")
    deploy_if = " ".join(str(jobs["deploy"].get("if") or "").split())
    # Each clause matters on its own: without !cancelled() a skipped test skips the
    # deploy; without the result check a FAILED test would deploy anyway.
    check("  the deploy job survives a skipped test", "!cancelled()" in deploy_if, True)
    check("  and still refuses a failed one",
          "needs.test.result == 'success'" in deploy_if
          and "needs.test.result == 'skipped'" in deploy_if, True)
    check("  and still honours LIVE_DEPLOY",
          "vars.LIVE_DEPLOY == 'true'" in deploy_if, True)
    check("  deploy waits for both jobs", jobs["deploy"].get("needs"), ["prepare", "test"])

    # The backup and rollback path is what makes an untested deploy acceptable at
    # all, so assert it is still in the deploy script rather than assuming.
    script = ""
    for step in jobs["deploy"]["steps"]:
        if step.get("id") == "ssh-deploy":
            script = step["with"]["script"]
    check("  the deploy still backs up before touching anything",
          "bench --site \"$SITE\" backup" in script, True)
    check("  still verifies that backup",
          "gzip -t" in script, True)
    check("  still rolls back on failure",
          "rollback \"bench migrate failed\"" in script, True)
    check("  and records the result in the ERP both ways",
          script.count("record_deploy_log") >= 3, True)

    print()
    print("=== 6. The merge carries the tag to main ===")
    merge, merge_raw = _workflow("auto-merge-devbranch.yml")
    cond = " ".join(str(merge["jobs"]["auto-merge"].get("if") or "").split())
    check("  both tags trigger the merge",
          "[autodeploy]" in cond and "[urgentfix]" in cond, True)
    # main.yml reads github.event.head_commit.message, which on a merge is the MERGE
    # commit -- gh's default subject would drop the tag, so it is set explicitly.
    check("  and the tag is written onto the merge commit",
          "--subject" in merge_raw and "DEPLOY_TAG" in merge_raw, True)


def _cleanup(path):
    """Remove only what this run created."""
    for name in _made:
        if name and frappe.db.exists("Deploy Log", name):
            frappe.delete_doc("Deploy Log", name, ignore_permissions=True, force=True)
    frappe.db.commit()
    try:
        os.remove(path)
    except OSError:
        pass
    print()
    print("  (the %d records this check created have been removed)" % len(_made))


def _summary():
    print()
    if not checks:
        print("=== NO CHECKS RUN ===")
    elif all(checks):
        print("=== ALL %d CHECKS PASSED ===" % len(checks))
    else:
        print("=== %d of %d CHECKS FAILED ===" % (checks.count(False), len(checks)))
