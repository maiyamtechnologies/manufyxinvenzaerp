import frappe
from frappe.model.document import Document


class DeployLog(Document):
    """One record per deploy, written by the CI pipeline from the server.

    Every field is read-only and the doctype is in_create: this is a record of
    something that already happened on the server, not a document anyone edits.
    Deleting is allowed -- the pruning in deploy_log.record() relies on it.
    """

    def validate(self):
        self._set_duration()

    def _set_duration(self):
        """A readable elapsed time, so the list view answers 'how long' without
        subtracting two timestamps by eye."""
        from frappe.utils import get_datetime, time_diff_in_seconds

        if not (self.deploy_started and self.deploy_finished):
            self.duration_display = ""
            return
        try:
            seconds = int(time_diff_in_seconds(
                get_datetime(self.deploy_finished), get_datetime(self.deploy_started)))
        except Exception:
            self.duration_display = ""
            return
        if seconds < 0:
            self.duration_display = ""
        elif seconds < 60:
            self.duration_display = "%ds" % seconds
        else:
            self.duration_display = "%dm %02ds" % (seconds // 60, seconds % 60)
