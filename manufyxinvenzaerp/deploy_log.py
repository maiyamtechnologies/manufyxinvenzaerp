"""Bring the server's deploy log into the ERP, so a deploy can be checked from the UI.

The pipeline already writes a full log per deploy to $BENCH_PATH/Auto-deploy-logs and
keeps the last 20. That is only readable over SSH, which is exactly who cannot read it
when something has gone wrong at 9pm. `record()` is called from the deploy script at
the end of every run -- the successful path and the rollback path both -- and copies
that same log into a Deploy Log record with a status on it.

Called through `bench execute`, not over the API, because it runs ON the server inside
the bench that just deployed. No token, no inbound port, and it cannot be invoked by
anything that is not already on the box.

It must never be able to fail a deploy. Everything is wrapped: a bad argument, a log
file that has vanished, a doctype that does not exist yet on a server mid-upgrade --
each returns quietly rather than raising. The deploy script calls it with `|| true` as
well, which is belt and braces, because a deploy that worked being reported as failed
because its *logging* failed is the worst of both outcomes.
"""

import os
import subprocess

import frappe
from frappe.utils import now_datetime

# How many Deploy Log records to keep. Matches the 20 logs the server keeps in
# Auto-deploy-logs, so the two prune in step and a record never points at a log
# file that was cleaned up long ago.
KEEP_RECORDS = 20

# How much of the log to store. A normal deploy log is a few hundred lines; a
# failing `bench migrate` can run to megabytes of traceback. The tail is the part
# that says what happened, so an oversized log is cut from the FRONT and marked.
MAX_LOG_CHARS = 200000

VALID_STATUSES = ("In Progress", "Completed", "Failed", "Rolled Back")


def record(
    status=None,
    log_file=None,
    started=None,
    finished=None,
    commit_sha=None,
    commit_message=None,
    branch=None,
    site=None,
    backup_file=None,
    rollback_commit=None,
    failed_step=None,
    trigger_tag=None,
    tests_skipped=0,
):
    """Create one Deploy Log from a finished deploy. Returns its name, or None.

    Only `status` and `log_file` really matter; everything else is context the
    deploy script happens to know and is cheap to pass along.
    """
    try:
        if status not in VALID_STATUSES:
            # An unrecognised status is still worth a record -- losing the log
            # because the caller mistyped is the wrong trade.
            status = "Failed" if status else "In Progress"

        log_text, tail = _read_log(log_file)

        # Commit details are read from the checkout rather than passed in. A commit
        # message can hold quotes, newlines and backticks, and threading one through
        # a shell heredoc into a --kwargs dict literal is a quoting bug waiting to
        # happen -- one that would break the deploy, not just the log. git already
        # has it, on the same machine, so ask git.
        git = _git_context()
        commit_sha = commit_sha or git.get("sha")
        commit_message = commit_message or git.get("message")
        branch = branch or git.get("branch")

        doc = frappe.new_doc("Deploy Log")
        doc.status = status
        doc.deploy_started = started or None
        doc.deploy_finished = finished or now_datetime()
        doc.commit_sha = (commit_sha or "")[:140]
        doc.commit_message = (commit_message or "")[:1000]
        doc.branch = (branch or "")[:140]
        doc.site = (site or "")[:140]
        doc.log_file = (log_file or "")[:140]
        doc.backup_file = (backup_file or "")[:140]
        doc.rollback_commit = (rollback_commit or "")[:140]
        doc.failed_step = (failed_step or "")[:140]
        doc.trigger_tag = trigger_tag if trigger_tag in ("autodeploy", "urgentfix", "manual") else ""
        doc.tests_skipped = 1 if str(tests_skipped) in ("1", "true", "True", "yes") else 0
        doc.log = log_text
        # Only on a deploy that did not finish clean: on a good one the section is
        # hidden anyway and a summary would just be the last few lines of success.
        doc.error_summary = tail if status != "Completed" else ""
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        _prune()
        return doc.name
    except Exception:
        # Deliberately swallowed. See the module docstring: this must not be able
        # to turn a good deploy into a failed one. Logged so it is still findable.
        try:
            frappe.log_error(frappe.get_traceback(), "Deploy Log: could not record deploy")
            frappe.db.commit()
        except Exception:
            pass
        return None


def _git_context():
    """sha / message / branch of the app checkout this code is running from.

    Best-effort by design: a server whose app directory is not a git checkout, or
    where git is not on PATH, still gets its log recorded -- just without the commit
    on it. Never raises.
    """
    out = {}
    try:
        app_path = frappe.get_app_path("manufyxinvenzaerp")
        repo = os.path.dirname(app_path)
        for key, args in (
            ("sha", ["rev-parse", "HEAD"]),
            ("message", ["log", "-1", "--pretty=%B"]),
            ("branch", ["rev-parse", "--abbrev-ref", "HEAD"]),
        ):
            try:
                out[key] = subprocess.check_output(
                    ["git", "-C", repo] + args,
                    stderr=subprocess.DEVNULL, timeout=15,
                ).decode(errors="replace").strip()
            except Exception:
                out[key] = ""
    except Exception:
        pass
    return out


def _read_log(log_file):
    """(full-ish log, tail) from the server's log file, or a note saying why not.

    The tail is the last 30 non-blank lines, which is what somebody scanning a
    failure wants first, and is what goes in Error Summary.
    """
    if not log_file:
        return "(no log file path was passed by the deploy script)", ""
    if not os.path.isfile(log_file):
        return "(log file not found on the server: %s)" % log_file, ""
    try:
        with open(log_file, "r", errors="replace") as fh:
            text = fh.read()
    except Exception as e:
        return "(log file could not be read: %s)" % e, ""

    if len(text) > MAX_LOG_CHARS:
        cut = len(text) - MAX_LOG_CHARS
        text = ("[... %d characters trimmed from the start of this log; the full "
                "file is on the server at the path in Log File ...]\n\n" % cut
                + text[-MAX_LOG_CHARS:])

    lines = [ln for ln in text.splitlines() if ln.strip()]
    return text, "\n".join(lines[-30:])[:2000]


def _prune():
    """Keep the newest KEEP_RECORDS and delete the rest.

    Ordered by creation, not modified: these are never edited, and `modified`
    would reorder them if anything ever touched one.
    """
    try:
        # Fetched in full and sliced in Python, NOT with limit_start=KEEP_RECORDS.
        # `limit_page_length=0` means "no limit" in Frappe, and an offset with no
        # row count is not valid SQL, so the offset is dropped and the query comes
        # back with EVERY record -- which this function would then delete, wiping
        # the log it exists to trim. Caught the first time it ran: the record had
        # just been created, record() returned its name, and the table was empty.
        names = frappe.get_all("Deploy Log", pluck="name", order_by="creation desc")
        stale = names[KEEP_RECORDS:]
        for name in stale:
            frappe.delete_doc("Deploy Log", name, ignore_permissions=True, force=True)
        if stale:
            frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Deploy Log: could not prune old records")
