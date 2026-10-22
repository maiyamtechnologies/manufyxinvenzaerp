"""Op-1 waits for the whole transfer, item by item (live SC-ORD-2026-00003, 22 Oct 2026).

That job ran all five operations with 193.424 Kg of PLATE16 still in stores. Other items
had been sent over plan, so the job's total transferred weight was above plan and Op-1's
check -- "has this drawing received anything at all" -- passed. Only the Final Stock
Entry, which asks per batch, refused.

Reproduced on a finished local job by taking 193.424 Kg off one row of its transfer:

  * the item-level pending figure sees it, though the job's total Kg is still above plan;
  * Op-1 refuses to log with "Fully Transferred" (and with the setting blank, as on live);
  * "Partially Transferred" lets Op-1 log, and the Final Stock Entry still refuses;
  * the Operations tab banner asks the same question.

Runs inside one transaction that is rolled back at the end.

Run: bench --site manufactv16 execute manufyxinvenzaerp.tests.verify_op1_waits_for_transfer.run
"""

import frappe
from frappe.utils import flt

from manufyxinvenzaerp.subcontracting_management import subcontracting as sc

checks = []
SHORT = 193.424


def check(label, got, want):
	ok = got == want
	checks.append(ok)
	print("  %-4s %-66s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _throws(fn, needle=None):
	frappe.db.savepoint("mfx_throw")
	try:
		fn()
	except frappe.ValidationError as e:
		frappe.db.rollback(save_point="mfx_throw")
		frappe.clear_last_message()
		return needle in str(e) if needle else True
	return False


def _set_trigger(value):
	frappe.db.set_single_value("Manufacturing Settings", "custom_soe_log_trigger", value)


def run():
	real_commit = frappe.db.commit
	frappe.db.commit = lambda *a, **k: None
	try:
		_run()
	finally:
		frappe.db.rollback()
		frappe.db.commit = real_commit
	print("\n%d/%d checks passed" % (sum(checks), len(checks)))


def _run():
	job = None
	for sco in frappe.get_all("Subcontracting Order", {"docstatus": 1}, pluck="name"):
		pending = sc._pending_transfer(sco)
		if pending and pending.kg == 0:
			job = sco
			break
	if not job:
		print("  SKIP no fully transferred job with a Material Issue Plan")
		return
	mip = frappe.db.get_value("Material Issue Plan", {"subcontracting_order": job}, "name")
	print("job %s, plan %s" % (job, mip))
	check("before: nothing pending", sc._pending_transfer(job).kg, 0)

	# Take 193.424 Kg off the biggest line of the job's transfer to the supplier.
	row = frappe.db.sql(
		"""SELECT sed.name, sed.qty, sed.item_code FROM `tabStock Entry Detail` sed
		   JOIN `tabStock Entry` se ON se.name = sed.parent
		   WHERE se.custom_mip_ref = %s AND se.docstatus = 1 AND se.stock_entry_type != 'Manufacture'
		   ORDER BY sed.qty DESC LIMIT 1""", mip, as_dict=True)[0]
	frappe.db.set_value("Stock Entry Detail", row.name, "qty", flt(row.qty) - SHORT)

	pending = sc._pending_transfer(job)
	check("one item short, by the Kg taken off", (pending.item_count, pending.kg), (1, SHORT))
	sco = frappe.get_doc("Subcontracting Order", job)
	print("  (job totals: mapped %s Kg, transferred %s Kg)" % (sco.custom_mapped_weight_kg,
	                                                          sco.custom_transferred_weight_kg))

	op1 = frappe.get_doc("Supplier Operation Entry",
	                     {"subcontracting_order": job, "sequence_id": 1, "docstatus": ["!=", 2]})
	draft = frappe.copy_doc(op1)
	draft.status = "In Progress"
	draft.amended_from = None
	check("the Op-1 copy has quantities logged", bool(draft.consumption_log), True)

	for setting in ("Fully Transferred", None):
		_set_trigger(setting)
		check("Op-1 refuses to log (setting %r)" % setting,
		      _throws(lambda: sc.validate_supplier_operation_entry(draft), "still waiting to be transferred"), True)

	_set_trigger("Partially Transferred")
	check("Partially Transferred: Op-1 may log",
	      _throws(lambda: sc.validate_supplier_operation_entry(draft), "still waiting to be transferred"), False)
	check("  and the Final Stock Entry still refuses",
	      "still waiting to be transferred" in sc._pending_transfer_block(job), True)

	check("Operations tab asks the same question", sc.get_pending_transfer(job).kg, SHORT)
	check("the refusal names the item count",
	      "193.424 Kg across 1 item(s)" in sc._pending_transfer_block(job), True)

	frappe.db.set_value("Stock Entry Detail", row.name, "qty", row.qty)
	_set_trigger("Fully Transferred")
	check("transfer complete again: Op-1 logs",
	      _throws(lambda: sc.validate_supplier_operation_entry(draft), "still waiting to be transferred"), False)
	check("  and the Final Stock Entry has no block", sc._pending_transfer_block(job), "")
	check("a job with no plan is not blocked", sc._pending_transfer(None), None)

	from manufyxinvenzaerp.setup import SCO_OPS_SCRIPT

	check("banner reads the item-level figure",
	      "get_pending_transfer" in SCO_OPS_SCRIPT and "frm.__mfx_pending_transfer" in SCO_OPS_SCRIPT, True)
