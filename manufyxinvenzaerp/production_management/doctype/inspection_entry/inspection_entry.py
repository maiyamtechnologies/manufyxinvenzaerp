import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class InspectionEntry(Document):
	def validate(self):
		if self.source_doctype == "Purchase Receipt":
			self._validate_pr_items()
		elif self.source_doctype == "Supplier Operation Entry":
			self._validate_soe_items()
		else:
			self._autofill_total_qty_to_check()
			self._validate_scalar_result()

		if self.source_doctype in ("Supplier Operation Entry", "Purchase Receipt"):
			self._derive_header_result()
		self._set_inspection_complete_date()

	def _autofill_total_qty_to_check(self):
		"""Job Card only -- Supplier Operation Entry uses the row-wise soe_items table
		instead (see _validate_soe_items), which already carries its own per-drawing
		Completed Qty copied from the source SOE's inspection_items at creation time."""
		if self.job_card:
			self.total_qty_to_check = flt(frappe.db.get_value("Job Card", self.job_card, "for_quantity"))

	def _set_inspection_complete_date(self):
		"""Set once, the first time Status is saved as Completed -- not re-derived on
		later saves so it reflects when the inspection was actually completed, not
		today's date on every subsequent edit."""
		if self.status == "Completed" and not self.inspection_complete_date:
			self.inspection_complete_date = nowdate()

	def before_submit(self):
		if self.status != "Completed":
			frappe.throw(
				_("Status must be <b>Completed</b> before this Inspection Entry can be submitted."),
				title=_("Inspection Not Completed"),
			)
		missing = [self._row_label(r) for r in self._result_rows() if not r.feedback]
		if missing:
			frappe.throw(
				_("Enter Feedback on every row before completing the inspection:<br>{0}").format("<br>".join(missing)),
				title=_("Feedback Missing"),
			)

	def _result_rows(self):
		"""The rows that carry Feedback: drawings for an Operation Entry, items for a
		Purchase Receipt. A Job Card has none -- its Feedback stays on the header."""
		if self.source_doctype == "Supplier Operation Entry":
			return self.soe_items or []
		if self.source_doctype == "Purchase Receipt":
			return self.items or []
		return []

	def _row_label(self, row):
		if self.source_doctype == "Supplier Operation Entry":
			return _("Row {0} ({1})").format(row.idx, row.customer_drawing_number or row.drawing)
		return _("Row {0} ({1})").format(row.idx, row.item_code)

	def _validate_row_feedback(self):
		"""Ok means nothing rejected on that row, Not Ok means something was. Checked
		once a row has Feedback; that every row has one is checked at submit."""
		for row in self._result_rows():
			if row.feedback == "Ok" and flt(row.reject_qty) > 0:
				frappe.throw(
					_("{0}: Feedback cannot be <b>Ok</b> while {1} is rejected. "
					  "Set it to <b>Not Ok</b> or accept the full quantity.").format(
						self._row_label(row), flt(row.reject_qty))
				)
			if row.feedback == "Not Ok" and flt(row.reject_qty) <= 0:
				frappe.throw(
					_("{0}: Feedback cannot be <b>Not Ok</b> when nothing is rejected. "
					  "Set it to <b>Ok</b>, or reduce the Accepted Qty.").format(self._row_label(row))
				)

	def _derive_header_result(self):
		"""The header Feedback and Rework Remarks are no longer entered: they summarise
		the rows, so the Inspection Status report and the call-log remarks read the
		same fields as before. Not Ok if any row is Not Ok; Ok once every row is Ok."""
		rows = self._result_rows()
		given = [r.feedback for r in rows if r.feedback]
		if "Not Ok" in given:
			self.feedback = "Not Ok"
		elif given and len(given) == len(rows):
			self.feedback = "Ok"
		else:
			self.feedback = ""
		if self.source_doctype == "Supplier Operation Entry":
			self.rework_remarks = "\n".join(
				"%s: %s" % (r.customer_drawing_number or r.drawing, r.rework_remarks.strip())
				for r in rows if flt(r.reject_qty) > 0 and (r.rework_remarks or "").strip()
			)

	def _validate_scalar_result(self):
		self.rework_qty = flt(flt(self.total_checked_qty) - flt(self.cleared_qty), 3)

		if self.is_new():
			# create_inspection_entry() inserts a bare draft prefilled only from the
			# source document (Total Checked Qty defaults from Total Qty to Check,
			# Cleared Qty starts at 0) so the inspector has something to open and edit --
			# it must not fail before that draft even exists. Everything below applies
			# from the inspector's first real save onward instead.
			return

		if flt(self.total_checked_qty) <= 0:
			frappe.throw(_("Total Checked Qty cannot be zero."))

		if self.rework_qty < 0:
			frappe.throw(
				_("Cleared Qty ({0}) cannot exceed Total Checked Qty ({1}).").format(
					self.cleared_qty, self.total_checked_qty
				)
			)

		if self.feedback == "Ok" and self.rework_qty > 0:
			frappe.throw(
				_("Feedback cannot be <b>Ok</b> while Cleared Qty is less than Total Checked Qty. "
				  "Set Feedback to <b>Not Ok</b> or clear the full quantity.")
			)

		if self.feedback == "Not Ok" and self.rework_qty == 0:
			frappe.throw(
				_("Feedback cannot be <b>Not Ok</b> when the full quantity is cleared. "
				  "Set Feedback to <b>Ok</b>, or reduce Cleared Qty to reflect the rework quantity.")
			)

		if self.rework_qty > 1 and not (self.rework_remarks or "").strip():
			frappe.throw(_("Rework Remarks is mandatory when Rework Qty is greater than 1."))

	def _validate_soe_items(self):
		"""Row-wise inspection for a Supplier Operation Entry source -- replaces the
		scalar Total Checked/Cleared Qty fields with per-drawing Accepted/Rejected Qty
		(client change: "instead of entering the Overall checked quantity, user need to
		enter in the item table"). Accepted Qty is what on_submit_inspection_entry /
		_apply_soe_inspection_results later adds onto the source SOE's
		drawing_details.completed_qty_nos; Rejected Qty is not pushed anywhere -- it
		naturally reappears in the SOE's own inspection_items table (see
		_sync_soe_inspection_items) the moment it's logged again in Consumption Log."""
		if not self.soe_items:
			if self.is_new():
				return
			frappe.throw(_("Add at least one drawing to inspect."))

		for row in self.soe_items:
			if flt(row.accept_qty) > flt(row.qty_nos):
				frappe.throw(
					_("Row {0}: Accepted Qty ({1}) cannot exceed Completed Qty ({2}) for drawing {3}.").format(
						row.idx, row.accept_qty, row.qty_nos, row.customer_drawing_number or row.drawing
					)
				)
			row.reject_qty = flt(flt(row.qty_nos) - flt(row.accept_qty), 3)

		# Mirror aggregates onto the header scalar fields -- kept in sync so the
		# Inspection Status Report and any other reader of total_checked_qty /
		# cleared_qty / rework_qty keeps working for an SOE source too, even though the
		# UI shows the item table instead of these fields in that case.
		self.total_checked_qty = flt(sum(flt(r.qty_nos) for r in self.soe_items), 3)
		self.cleared_qty = flt(sum(flt(r.accept_qty) for r in self.soe_items), 3)
		self.rework_qty = flt(sum(flt(r.reject_qty) for r in self.soe_items), 3)

		if self.is_new():
			return

		if self.total_checked_qty <= 0:
			frappe.throw(_("Total Completed Qty cannot be zero."))

		self._validate_row_feedback()

		missing = [self._row_label(r) for r in self.soe_items
		           if flt(r.reject_qty) > 0 and not (r.rework_remarks or "").strip()]
		if missing:
			frappe.throw(
				_("Rework Remarks is mandatory on a row with a Rejected Qty:<br>{0}").format("<br>".join(missing)),
				title=_("Rework Remarks Missing"),
			)

	def _validate_pr_items(self):
		if not self.items:
			frappe.throw(_("Add at least one item to inspect."))

		for row in self.items:
			if flt(row.accept_qty) > flt(row.qty):
				frappe.throw(
					_("Row {0}: Accepted Qty ({1}) cannot exceed Received Qty ({2}) for item {3}.").format(
						row.idx, row.accept_qty, row.qty, row.item_code
					)
				)
			row.reject_qty = flt(flt(row.qty) - flt(row.accept_qty), 3)

		self._validate_row_feedback()
