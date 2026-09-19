// Sales Invoice: finished goods invoiced by the piece (sep14 FG plan).
// Owner: A6. Wave 0 placeholder, deliberately empty.
// A6 adds: Qty (Nos) drives the Kg (read-only on FG rows), and Update Stock is
// refused when any line is a finished-goods item.
frappe.ui.form.on("Sales Invoice", {});
