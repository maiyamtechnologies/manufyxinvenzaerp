"""Data Works: reset a site's data for go-live, from the Data Works page.

One step, safe to run twice:
  transactions    delete every transaction and test master; keep the item master and other masters

What is deleted comes from data/setup.json. The warehouse and rate-schedule steps were removed on
23 Oct 2026 (client): those masters are now set up by hand on the live site. Only a System Manager
can open the page, and every button asks for the site name. This is a one-time tool: remove the
page once the live reset is done.
"""

import json
import os
import traceback
from contextlib import contextmanager

import frappe
from frappe.model.delete_doc import delete_dynamic_links
from frappe.utils import now_datetime

STEPS = ("transactions",)
LABELS = {
	"transactions": "Delete transactions and test data",
}


# ---------------------------------------------------------------- data and guards

def _data(name):
	with open(os.path.join(os.path.dirname(__file__), "data", name)) as f:
		return json.load(f)


def _guard():
	frappe.only_for("System Manager")


def _status_path():
	return frappe.get_site_path("private", "data_works_status.json")


def _log_path():
	return frappe.get_site_path("private", "data_works.log")


def _log(msg):
	line = f"{now_datetime():%H:%M:%S}  {msg}"
	with open(_log_path(), "a") as f:
		f.write(line + "\n")
	print(line)


def _set_status(state, step=None):
	with open(_status_path(), "w") as f:
		json.dump({"state": state, "step": step, "at": str(now_datetime())}, f)


def _get_status():
	try:
		with open(_status_path()) as f:
			return json.load(f)
	except (OSError, ValueError):
		return {"state": "idle", "step": None}


# ---------------------------------------------------------------- whitelisted API

@frappe.whitelist()
def get_state():
	frappe.only_for("System Manager")
	return {
		"site": frappe.local.site,
		"status": _get_status(),
		"steps": [{"step": s, "label": LABELS[s]} for s in STEPS],
	}


@frappe.whitelist()
def preview(step):
	"""What a step would do, as {"title", "lines"} for the confirmation dialog."""
	_guard()
	if step == "all":
		lines = ["A database backup is taken first, then the step below runs."]
		for s in STEPS:
			lines.append(f"-- {LABELS[s]} --")
			lines += _preview_step(s)
		return {"title": "Run everything", "lines": lines}
	if step not in STEPS:
		frappe.throw("Unknown step.")
	return {"title": LABELS[step], "lines": _preview_step(step)}


@frappe.whitelist()
def run(step, confirm_site):
	_guard()
	if confirm_site != frappe.local.site:
		frappe.throw("The site name you typed does not match this site.")
	if step not in STEPS and step not in ("all", "backup"):
		frappe.throw("Unknown step.")
	if _get_status()["state"] == "running":
		frappe.throw("A Data Works step is already running. Watch the log below.")
	_set_status("running", step)
	with open(_log_path(), "w") as f:
		f.write("")
	frappe.enqueue(
		"manufyxinvenzaerp.data_works.engine.run_job",
		queue="long", timeout=7200, step=step, user=frappe.session.user,
	)
	return "queued"


@frappe.whitelist()
def get_log(offset=0):
	frappe.only_for("System Manager")
	try:
		with open(_log_path()) as f:
			lines = f.read().splitlines()
	except OSError:
		lines = []
	offset = int(offset)
	return {"lines": lines[offset:], "next": len(lines), "status": _get_status()}


# ---------------------------------------------------------------- job

def run_job(step, user=None):
	"""Background job (also callable from bench execute). Stops at the first failure."""
	frappe.set_user(user or "Administrator")
	try:
		if step in ("all", "backup"):
			_backup()
		for s in (STEPS if step == "all" else [step] if step in STEPS else []):
			_log(f"=== {LABELS[s]} ===")
			globals()[f"_do_{s}"]()
			frappe.db.commit()
		_log("DONE")
		_set_status("done", step)
	except Exception:
		frappe.db.rollback()
		_log("FAILED\n" + traceback.format_exc())
		_set_status("failed", step)


def _backup():
	from frappe.utils.backups import new_backup

	odb = new_backup(ignore_files=True, force=True)
	_log(f"Backup taken: {odb.backup_path_db}")


# ---------------------------------------------------------------- step 1: transactions

def _table(doctype):
	return frappe.db.exists("DocType", doctype) and frappe.db.table_exists(doctype)


def _test_names():
	"""(doctype, name) of every master whose name starts with a test prefix."""
	prefixes = _data("setup.json")["test_name_prefixes"]
	found = []
	for doctype, field in (("Item", "name"), ("Supplier", "name"), ("Customer", "name"), ("Project", "project_name")):
		if not _table(doctype):
			continue
		for p in prefixes:
			found += [(doctype, n) for n in frappe.get_all(doctype, filters={field: ["like", f"{p}%"]}, pluck="name")]
	return sorted(set(found))


def _preview_step(step):
	cfg = _data("setup.json")
	lines = []
	for dt in cfg["ledger_doctypes"] + cfg["transaction_doctypes"]:
		if _table(dt) and (n := frappe.db.count(dt)):
			lines.append(f"{dt}: {n} to delete")
	lines += [f"Test {dt}: {n}" for dt, n in _test_names()]
	return lines or ["Nothing to delete."]


def _series_file():
	return frappe.get_site_path("private", "data_works_series.json")


def _note_series(names):
	"""Remember the naming-series key of every document about to go. A step that fails half way and
	is run again has lost those documents, so the keys are kept on disk until the reset is done."""
	keys = set()
	try:
		with open(_series_file()) as f:
			keys = set(json.load(f))
	except (OSError, ValueError):
		pass
	keys |= {n.rstrip("0123456789") for n in names if n}
	with open(_series_file(), "w") as f:
		json.dump(sorted(keys), f)


def _reset_series():
	"""Naming series restart at 1 once every document of that series is gone."""
	try:
		with open(_series_file()) as f:
			keys = json.load(f)
	except (OSError, ValueError):
		return
	for key in keys:
		if key:
			frappe.db.sql("update `tabSeries` set current = 0 where name = %s", key)
	os.remove(_series_file())


@contextmanager
def _inline_cleanup():
	"""delete_doc queues one background job per document to tidy its comments, versions and
	shares. Hundreds of them overload the queue, so queue nothing here and run the same tidy-up
	inline after each delete."""
	real = frappe.enqueue
	frappe.enqueue = lambda *a, **k: None
	try:
		yield
	finally:
		frappe.enqueue = real


def _delete(dt, name, force=False):
	frappe.delete_doc(
		dt, name, force=force, ignore_permissions=True, ignore_on_trash=force, delete_permanently=force
	)
	delete_dynamic_links(dt, name)


def _do_transactions():
	cfg = _data("setup.json")
	with _inline_cleanup():
		for dt in cfg["ledger_doctypes"]:
			if _table(dt):
				_note_series(frappe.get_all(dt, pluck="name"))
				frappe.db.delete(dt)
				_log(f"{dt}: cleared")
		frappe.db.commit()
		for dt in cfg["transaction_doctypes"]:
			if not _table(dt):
				continue
			docs = frappe.get_all(dt, pluck="name")
			_note_series(docs)
			for n in docs:
				# Frappe will not delete a submitted document; the ledgers are already gone, so
				# marking it cancelled first is all that stands in the way.
				frappe.db.set_value(dt, n, "docstatus", 2, update_modified=False)
				_delete(dt, n, force=True)
			if docs:
				_log(f"{dt}: {len(docs)} deleted")
			# every document of this doctype is gone, so its old 'Deleted' comments and versions are too
			frappe.db.delete("Comment", {"reference_doctype": dt})
			frappe.db.delete("Version", {"ref_doctype": dt})
			frappe.db.commit()

		tests = _test_names()
		_note_series([n for d, n in tests if d == "Project"])
		items = [n for dt, n in tests if dt == "Item"]
		for ip in frappe.get_all("Item Price", filters={"item_code": ["in", items]}, pluck="name"):
			_delete("Item Price", ip)
		for dt in ("Project", "Item", "Supplier", "Customer"):
			for d, n in tests:
				if d == dt:
					_delete(dt, n)
					_log(f"Test {dt} deleted: {n}")
	_reset_series()
