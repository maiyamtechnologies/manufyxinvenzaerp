// Stock Entry: finished-goods rows in Kg with Nos per drawing batch (sep14 FG plan).
// Owner: A4. Wave 0 placeholder, deliberately empty.
// A4 adds: on FG rows, Nos drives the Kg for Material Transfer / Issue, and the
// Kg is read-only on the Final Stock Entry when "Edit FG Stock Kg" is off.
// Stock Entry's other client logic lives in the "Stock Entry-dimensional-weight-logic"
// Client Script (setup.py); this file only adds the FG part.
frappe.ui.form.on("Stock Entry", {});
