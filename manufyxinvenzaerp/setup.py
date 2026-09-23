import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CLIENT_SCRIPT_NAME = "Item-parent-item-group-filter"
PO_CLIENT_SCRIPT_NAME = "Purchase Order-custom-po-item-logic"
PR_CLIENT_SCRIPT_NAME = "Purchase Receipt-custom-pr-item-logic"
MR_CLIENT_SCRIPT_NAME = "Material Request-custom-mr-item-logic"
RFQ_CLIENT_SCRIPT_NAME = "Request for Quotation-custom-rfq-item-logic"
SQ_CLIENT_SCRIPT_NAME = "Supplier Quotation-custom-sq-item-logic"
SO_CLIENT_SCRIPT_NAME = "Sales Order-create-drawing-button"

BOM_CLIENT_SCRIPT_NAME = "BOM-create-production-plan-button"
PRODUCTION_PLAN_CLIENT_SCRIPT_NAME = "Production Plan-subcontracting-plan-logic"
STOCK_ENTRY_CLIENT_SCRIPT_NAME = "Stock Entry-dimensional-weight-logic"
SCO_CLIENT_SCRIPT_NAME = "Subcontracting Order-soe-buttons"
SOE_CLIENT_SCRIPT_NAME = "Supplier Operation Entry-consumption-logic"

BOM_CLIENT_SCRIPT = """
frappe.ui.form.on("BOM", {
\trefresh(frm) {
\t\tif (frm.doc.docstatus === 1 && frm.doc.custom_drawing) {
\t\t\tfrm.remove_custom_button(__("Work Order"), __("Create"));
\t\t\tfrm.add_custom_button(__("Production Plan"), function () {
\t\t\t\tfrappe.confirm(
\t\t\t\t\t__("Create a Production Plan for <b>" + (frm.doc.item_name || frm.doc.item) + "</b>?"),
\t\t\t\t\tfunction () {
\t\t\t\t\t\tfrappe.call({
\t\t\t\t\t\t\tmethod: "manufyxinvenzaerp.drawing_management.drawing_utils.create_production_plan_from_bom",
\t\t\t\t\t\t\targs: { bom_name: frm.doc.name },
\t\t\t\t\t\t\tfreeze: true,
\t\t\t\t\t\t\tcallback: function (r) {
\t\t\t\t\t\t\t\tif (r.message) {
\t\t\t\t\t\t\t\t\tfrappe.msgprint({
\t\t\t\t\t\t\t\t\t\ttitle: __("Production Plan Created"),
\t\t\t\t\t\t\t\t\t\tmessage: __("Production Plan created") + ': <a href="/app/production-plan/' + encodeURIComponent(r.message) + '" target="_blank">' + r.message + '</a>',
\t\t\t\t\t\t\t\t\t\tindicator: "green",
\t\t\t\t\t\t\t\t\t});
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t},
\t\t\t\t\t\t});
\t\t\t\t\t}
\t\t\t\t);
\t\t\t}, __("Create"));
\t\t}
\t},
});
""".strip()

CLIENT_SCRIPT = """
frappe.ui.form.on("Item", {
\trefresh(frm) {
\t\t// Null link_filters so apply_link_field_filters() is skipped on dropdown open
\t\tfrm.fields_dict.item_group.df.link_filters = null;
\t\tfrm.set_query("item_group", function() {
\t\t\tvar filters = [["Item Group", "is_group", "=", 0]];
\t\t\tif (frm.doc.custom_parent_item_group) {
\t\t\t\tfilters.push(["Item Group", "parent_item_group", "=", frm.doc.custom_parent_item_group]);
\t\t\t}
\t\t\treturn { filters: filters };
\t\t});
\t\tfrm.set_query("custom_parent_item_group", function() {
\t\t\treturn { filters: { is_group: 1 } };
\t\t});
\t\tfrm.set_df_property("custom_item_calculation_type", "read_only", 1);
\t},
\tcustom_parent_item_group(frm) {
\t\tvar group = frm.doc.custom_parent_item_group;
\t\tif (["Structurals", "Plates"].includes(group)) {
\t\t\tfrm.set_value("custom_item_calculation_type", "Formula Weight Calculation");
\t\t} else if (group) {
\t\t\tfrm.set_value("custom_item_calculation_type", "Normal Weight Calculation");
\t\t}
\t\tfrm.set_value("item_group", "");
\t}
});
""".strip()

PO_CLIENT_SCRIPT = """
frappe.ui.form.on("Purchase Order", {
\trefresh(frm) {
\t\tfrm.set_query("uom", "items", function(doc, cdt, cdn) {
\t\t\tvar row = locals[cdt][cdn];
\t\t\treturn {
\t\t\t\tquery: "manufyxinvenzaerp.purchase_order_management.purchase_order.get_po_item_uom",
\t\t\t\tfilters: { item_code: row.item_code }
\t\t\t};
\t\t});
\t}
});

frappe.ui.form.on("Purchase Order Item", {
\titem_code(frm, cdt, cdn) {
\t\tsetTimeout(function() {
\t\t\tcalculate_qty(frm, cdt, cdn);
\t\t\tpo_toggle_dims(frm, cdt, cdn);
\t\t}, 600);
\t},
\tqty(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (row.custom_parent_item_group === "Nuts and Bolts") {
\t\t\tcalculate_qty(frm, cdt, cdn);
\t\t}
\t},
\tcustom_length(frm, cdt, cdn) { calculate_qty(frm, cdt, cdn); },
\tcustom_width(frm, cdt, cdn) { calculate_qty(frm, cdt, cdn); },
\tcustom_thickness(frm, cdt, cdn) { calculate_qty(frm, cdt, cdn); },
\tcustom_sec_qty(frm, cdt, cdn) { calculate_qty(frm, cdt, cdn); },
\tcustom_unit_weight(frm, cdt, cdn) { calculate_qty(frm, cdt, cdn); },
\tform_render(frm, cdt, cdn) { po_toggle_dims(frm, cdt, cdn); },
\tuom(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (row.uom && row.stock_uom && row.uom !== row.stock_uom) {
\t\t\tfrappe.msgprint({
\t\t\t\tmessage: "Weight is entered for Stock UOM, Kindly update UOM Weight in item master for correct calculation",
\t\t\t\tindicator: "orange",
\t\t\t\ttitle: "UOM Warning"
\t\t\t});
\t\t}
\t}
});

function po_toggle_dims(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;
\tvar show_len   = group === "Structurals" || group === "Plates";
\tvar show_thick = group === "Plates";
\t$.each(frm.fields_dict["items"].grid.grid_rows, function(i, gr) {
\t\tif (gr.doc && gr.doc.name === cdn && gr.grid_form) {
\t\t\tgr.grid_form.toggle_display("custom_length",    show_len);
\t\t\tgr.grid_form.toggle_display("custom_thickness", show_thick);
\t\t\tgr.grid_form.toggle_display("custom_width",     show_thick);
\t\t}
\t});
}

function calculate_qty(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;

\tif (group === "Structurals") {
\t\tif (row.custom_length && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tfrappe.model.set_value(cdt, cdn, "qty", flt((row.custom_length / 1000) * row.custom_unit_weight * row.custom_sec_qty, 3));
\t\t} else {
\t\t\twarn_missing_fields(row, group);
\t\t}
\t} else if (group === "Plates") {
\t\tif (row.custom_length && row.custom_width && row.custom_thickness && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tfrappe.model.set_value(cdt, cdn, "qty", flt((row.custom_length / 1000) * (row.custom_width / 1000) * row.custom_thickness * row.custom_unit_weight * row.custom_sec_qty, 3));
\t\t} else {
\t\t\twarn_missing_fields(row, group);
\t\t}
\t} else if (group === "Nuts and Bolts") {
\t\tif (row.qty && row.custom_unit_weight) {
\t\t\tvar new_sec = flt(row.qty * row.custom_unit_weight, 3);
\t\t\tif (flt(row.custom_sec_qty, 3) !== new_sec) {
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_sec_qty", new_sec);
\t\t\t}
\t\t}
\t}
}

function warn_missing_fields(row, group) {
\tvar missing = [];
\tif (group === "Structurals") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t} else if (group === "Plates") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_width) missing.push("Width");
\t\tif (!row.custom_thickness) missing.push("Thickness");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t}
\tif (missing.length) {
\t\tfrappe.show_alert({
\t\t\tmessage: "Row " + row.idx + ": Missing for " + group + " formula: " + missing.join(", "),
\t\t\tindicator: "orange"
\t\t});
\t}
}
""".strip()

PR_CLIENT_SCRIPT = """
frappe.ui.form.on("Purchase Receipt", {
\trefresh(frm) {
\t\tfrm.set_query("uom", "items", function(doc, cdt, cdn) {
\t\t\tvar row = locals[cdt][cdn];
\t\t\treturn {
\t\t\t\tquery: "manufyxinvenzaerp.purchase_receipt_management.purchase_receipt.get_pr_item_uom",
\t\t\t\tfilters: { item_code: row.item_code }
\t\t\t};
\t\t});
\t}
});

frappe.ui.form.on("Purchase Receipt Item", {
\titem_code(frm, cdt, cdn) {
\t\tsetTimeout(function() {
\t\t\tpr_calculate_qty(frm, cdt, cdn);
\t\t\tpr_toggle_dims(frm, cdt, cdn);
\t\t}, 600);
\t},
\tqty(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (row.custom_parent_item_group === "Nuts and Bolts") {
\t\t\tpr_calculate_qty(frm, cdt, cdn);
\t\t}
\t},
\tcustom_length(frm, cdt, cdn) { pr_calculate_qty(frm, cdt, cdn); },
\tcustom_width(frm, cdt, cdn) { pr_calculate_qty(frm, cdt, cdn); },
\tcustom_thickness(frm, cdt, cdn) { pr_calculate_qty(frm, cdt, cdn); },
\tcustom_sec_qty(frm, cdt, cdn) { pr_calculate_qty(frm, cdt, cdn); },
\tcustom_unit_weight(frm, cdt, cdn) { pr_calculate_qty(frm, cdt, cdn); },
\tform_render(frm, cdt, cdn) { pr_toggle_dims(frm, cdt, cdn); },
\tuom(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (row.uom && row.stock_uom && row.uom !== row.stock_uom) {
\t\t\tfrappe.msgprint({
\t\t\t\tmessage: "Weight is entered for Stock UOM, Kindly update UOM Weight in item master for correct calculation",
\t\t\t\tindicator: "orange",
\t\t\t\ttitle: "UOM Warning"
\t\t\t});
\t\t}
\t}
});

function pr_toggle_dims(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;
\tvar show_len   = group === "Structurals" || group === "Plates";
\tvar show_thick = group === "Plates";
\t$.each(frm.fields_dict["items"].grid.grid_rows, function(i, gr) {
\t\tif (gr.doc && gr.doc.name === cdn && gr.grid_form) {
\t\t\tgr.grid_form.toggle_display("custom_length",    show_len);
\t\t\tgr.grid_form.toggle_display("custom_thickness", show_thick);
\t\t\tgr.grid_form.toggle_display("custom_width",     show_thick);
\t\t}
\t});
}

function pr_calculate_qty(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;

\tif (group === "Structurals") {
\t\tif (row.custom_length && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tfrappe.model.set_value(cdt, cdn, "qty", flt((row.custom_length / 1000) * row.custom_unit_weight * row.custom_sec_qty, 3));
\t\t} else {
\t\t\tpr_warn_missing_fields(row, group);
\t\t}
\t} else if (group === "Plates") {
\t\tif (row.custom_length && row.custom_width && row.custom_thickness && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tfrappe.model.set_value(cdt, cdn, "qty", flt((row.custom_length / 1000) * (row.custom_width / 1000) * row.custom_thickness * row.custom_unit_weight * row.custom_sec_qty, 3));
\t\t} else {
\t\t\tpr_warn_missing_fields(row, group);
\t\t}
\t} else if (group === "Nuts and Bolts") {
\t\tif (row.qty && row.custom_unit_weight) {
\t\t\tvar new_sec = flt(row.qty * row.custom_unit_weight, 3);
\t\t\tif (flt(row.custom_sec_qty, 3) !== new_sec) {
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_sec_qty", new_sec);
\t\t\t}
\t\t}
\t}
}

function pr_warn_missing_fields(row, group) {
\tvar missing = [];
\tif (group === "Structurals") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t} else if (group === "Plates") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_width) missing.push("Width");
\t\tif (!row.custom_thickness) missing.push("Thickness");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t}
\tif (missing.length) {
\t\tfrappe.show_alert({
\t\t\tmessage: "Row " + row.idx + ": Missing for " + group + " formula: " + missing.join(", "),
\t\t\tindicator: "orange"
\t\t});
\t}
}
""".strip()

MR_CLIENT_SCRIPT = """
frappe.ui.form.on("Material Request", {
\trefresh(frm) {
\t\tfrm.set_query("uom", "items", function(doc, cdt, cdn) {
\t\t\tvar row = locals[cdt][cdn];
\t\t\treturn {
\t\t\t\tquery: "manufyxinvenzaerp.material_request_management.material_request.get_mr_item_uom",
\t\t\t\tfilters: { item_code: row.item_code }
\t\t\t};
\t\t});

\t\t// Skip the "Enter Supplier" prompt — go straight to Purchase Order
\t\tfrm.events.make_purchase_order = function(frm) {
\t\t\tfrappe.model.open_mapped_doc({
\t\t\t\tmethod: "erpnext.stock.doctype.material_request.material_request.make_purchase_order",
\t\t\t\tfrm: frm,
\t\t\t\targs: { default_supplier: "" },
\t\t\t\trun_link_triggers: true,
\t\t\t});
\t\t};
\t}
});

frappe.ui.form.on("Material Request Item", {
\titem_code(frm, cdt, cdn) {
\t\tsetTimeout(function() {
\t\t\tmr_calculate_qty(frm, cdt, cdn);
\t\t\tmr_toggle_dims(frm, cdt, cdn);
\t\t}, 600);
\t},
\tqty(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (row.custom_parent_item_group === "Nuts and Bolts") {
\t\t\tmr_calculate_qty(frm, cdt, cdn);
\t\t}
\t},
\tcustom_length(frm, cdt, cdn) { mr_calculate_qty(frm, cdt, cdn); },
\tcustom_width(frm, cdt, cdn) { mr_calculate_qty(frm, cdt, cdn); },
\tcustom_thickness(frm, cdt, cdn) { mr_calculate_qty(frm, cdt, cdn); },
\tcustom_sec_qty(frm, cdt, cdn) { mr_calculate_qty(frm, cdt, cdn); },
\tcustom_unit_weight(frm, cdt, cdn) { mr_calculate_qty(frm, cdt, cdn); },
\tform_render(frm, cdt, cdn) { mr_toggle_dims(frm, cdt, cdn); },
\tuom(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (row.uom && row.stock_uom && row.uom !== row.stock_uom) {
\t\t\tfrappe.msgprint({
\t\t\t\tmessage: "Weight is entered for Stock UOM, Kindly update UOM Weight in item master for correct calculation",
\t\t\t\tindicator: "orange",
\t\t\t\ttitle: "UOM Warning"
\t\t\t});
\t\t}
\t}
});

function mr_toggle_dims(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;
\tvar show_len   = group === "Structurals" || group === "Plates";
\tvar show_thick = group === "Plates";
\t$.each(frm.fields_dict["items"].grid.grid_rows, function(i, gr) {
\t\tif (gr.doc && gr.doc.name === cdn && gr.grid_form) {
\t\t\tgr.grid_form.toggle_display("custom_length",    show_len);
\t\t\tgr.grid_form.toggle_display("custom_thickness", show_thick);
\t\t\tgr.grid_form.toggle_display("custom_width",     show_thick);
\t\t}
\t});
}

function mr_calculate_qty(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;

\tif (group === "Structurals") {
\t\tif (row.custom_length && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tfrappe.model.set_value(cdt, cdn, "qty", flt((row.custom_length / 1000) * row.custom_unit_weight * row.custom_sec_qty, 3));
\t\t} else {
\t\t\tmr_warn_missing_fields(row, group);
\t\t}
\t} else if (group === "Plates") {
\t\tif (row.custom_length && row.custom_width && row.custom_thickness && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tfrappe.model.set_value(cdt, cdn, "qty", flt((row.custom_length / 1000) * (row.custom_width / 1000) * row.custom_thickness * row.custom_unit_weight * row.custom_sec_qty, 3));
\t\t} else {
\t\t\tmr_warn_missing_fields(row, group);
\t\t}
\t} else if (group === "Nuts and Bolts") {
\t\tif (row.qty && row.custom_unit_weight) {
\t\t\tvar new_sec = flt(row.qty * row.custom_unit_weight, 3);
\t\t\tif (flt(row.custom_sec_qty, 3) !== new_sec) {
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_sec_qty", new_sec);
\t\t\t}
\t\t}
\t}
}

function mr_warn_missing_fields(row, group) {
\tvar missing = [];
\tif (group === "Structurals") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t} else if (group === "Plates") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_width) missing.push("Width");
\t\tif (!row.custom_thickness) missing.push("Thickness");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t}
\tif (missing.length) {
\t\tfrappe.show_alert({
\t\t\tmessage: "Row " + row.idx + ": Missing for " + group + " formula: " + missing.join(", "),
\t\t\tindicator: "orange"
\t\t});
\t}
}
""".strip()

RFQ_CLIENT_SCRIPT = """
frappe.ui.form.on("Request for Quotation", {
\trefresh(frm) {
\t\tfrm.set_query("uom", "items", function(doc, cdt, cdn) {
\t\t\tvar row = locals[cdt][cdn];
\t\t\treturn {
\t\t\t\tquery: "manufyxinvenzaerp.sq_management.supplier_quotation.get_sq_item_uom",
\t\t\t\tfilters: { item_code: row.item_code }
\t\t\t};
\t\t});
\t}
});

frappe.ui.form.on("Request for Quotation Item", {
\tform_render(frm, cdt, cdn) { rfq_toggle_dims(frm, cdt, cdn); }
});

function rfq_toggle_dims(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;
\tvar show_len   = group === "Structurals" || group === "Plates";
\tvar show_thick = group === "Plates";
\t$.each(frm.fields_dict["items"].grid.grid_rows, function(i, gr) {
\t\tif (gr.doc && gr.doc.name === cdn && gr.grid_form) {
\t\t\tgr.grid_form.toggle_display("custom_length",    show_len);
\t\t\tgr.grid_form.toggle_display("custom_thickness", show_thick);
\t\t\tgr.grid_form.toggle_display("custom_width",     show_thick);
\t\t}
\t});
}
""".strip()

SQ_CLIENT_SCRIPT = """
frappe.ui.form.on("Supplier Quotation", {
\trefresh(frm) {
\t\tfrm.set_query("uom", "items", function(doc, cdt, cdn) {
\t\t\tvar row = locals[cdt][cdn];
\t\t\treturn {
\t\t\t\tquery: "manufyxinvenzaerp.sq_management.supplier_quotation.get_sq_item_uom",
\t\t\t\tfilters: { item_code: row.item_code }
\t\t\t};
\t\t});
\t}
});

frappe.ui.form.on("Supplier Quotation Item", {
\titem_code(frm, cdt, cdn) {
\t\tsetTimeout(function() {
\t\t\tsq_calculate_qty(frm, cdt, cdn);
\t\t\tsq_toggle_dims(frm, cdt, cdn);
\t\t}, 600);
\t},
\tqty(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (row.custom_parent_item_group === "Nuts and Bolts") {
\t\t\tsq_calculate_qty(frm, cdt, cdn);
\t\t}
\t},
\tcustom_length(frm, cdt, cdn) { sq_calculate_qty(frm, cdt, cdn); },
\tcustom_width(frm, cdt, cdn) { sq_calculate_qty(frm, cdt, cdn); },
\tcustom_thickness(frm, cdt, cdn) { sq_calculate_qty(frm, cdt, cdn); },
\tcustom_sec_qty(frm, cdt, cdn) { sq_calculate_qty(frm, cdt, cdn); },
\tcustom_unit_weight(frm, cdt, cdn) { sq_calculate_qty(frm, cdt, cdn); },
\tform_render(frm, cdt, cdn) { sq_toggle_dims(frm, cdt, cdn); },
\tuom(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (row.uom && row.stock_uom && row.uom !== row.stock_uom) {
\t\t\tfrappe.msgprint({
\t\t\t\tmessage: "Weight is entered for Stock UOM, Kindly update UOM Weight in item master for correct calculation",
\t\t\t\tindicator: "orange",
\t\t\t\ttitle: "UOM Warning"
\t\t\t});
\t\t}
\t}
});

function sq_toggle_dims(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;
\tvar show_len   = group === "Structurals" || group === "Plates";
\tvar show_thick = group === "Plates";
\t$.each(frm.fields_dict["items"].grid.grid_rows, function(i, gr) {
\t\tif (gr.doc && gr.doc.name === cdn && gr.grid_form) {
\t\t\tgr.grid_form.toggle_display("custom_length",    show_len);
\t\t\tgr.grid_form.toggle_display("custom_thickness", show_thick);
\t\t\tgr.grid_form.toggle_display("custom_width",     show_thick);
\t\t}
\t});
}

function sq_calculate_qty(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;

\tif (group === "Structurals") {
\t\tif (row.custom_length && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tfrappe.model.set_value(cdt, cdn, "qty", flt((row.custom_length / 1000) * row.custom_unit_weight * row.custom_sec_qty, 3));
\t\t} else {
\t\t\tsq_warn_missing_fields(row, group);
\t\t}
\t} else if (group === "Plates") {
\t\tif (row.custom_length && row.custom_width && row.custom_thickness && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tfrappe.model.set_value(cdt, cdn, "qty", flt((row.custom_length / 1000) * (row.custom_width / 1000) * row.custom_thickness * row.custom_unit_weight * row.custom_sec_qty, 3));
\t\t} else {
\t\t\tsq_warn_missing_fields(row, group);
\t\t}
\t} else if (group === "Nuts and Bolts") {
\t\tif (row.qty && row.custom_unit_weight) {
\t\t\tvar new_sec = flt(row.qty * row.custom_unit_weight, 3);
\t\t\tif (flt(row.custom_sec_qty, 3) !== new_sec) {
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_sec_qty", new_sec);
\t\t\t}
\t\t}
\t}
}

function sq_warn_missing_fields(row, group) {
\tvar missing = [];
\tif (group === "Structurals") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t} else if (group === "Plates") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_width) missing.push("Width");
\t\tif (!row.custom_thickness) missing.push("Thickness");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t}
\tif (missing.length) {
\t\tfrappe.show_alert({
\t\t\tmessage: "Row " + row.idx + ": Missing for " + group + " formula: " + missing.join(", "),
\t\t\tindicator: "orange"
\t\t});
\t}
}
""".strip()

SO_CLIENT_SCRIPT = """
// ── Sales Order: Drawing Import ────────────────────────────────────────────

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		_so_render_file_buttons(frm);
		_so_render_rm_verify_btn(frm);
		_so_render_drawing_buttons(frm);
		_so_render_duno_view_all_btn(frm);
		_so_render_bom_summary(frm);
		_so_warn_cancelled_drawings(frm);
		_so_fg_pending_nos_dn_btn(frm);
	},
	custom_bom_excel_file(frm) {
		_so_render_file_buttons(frm);
	}
});

// Finished goods are delivered by the piece, but ERPNext decides "fully delivered" by
// Kg -- and weighed pieces are often heavier than ordered, so the Kg can be used up
// with pieces still to go. ERPNext then hides Create > Delivery Note (it only shows
// while per_delivered < 100). This puts the button back while any line still has Nos
// pending; the mapping it calls is the app's override, which offers those lines.
function _so_fg_pending_nos_dn_btn(frm) {
	if (frm.doc.docstatus !== 1 || flt(frm.doc.per_delivered) < 100) return;
	if (["Closed", "On Hold"].includes(frm.doc.status)) return;
	let pending = (frm.doc.items || []).some(function(d) {
		return flt(d.custom_sec_qty) > flt(d.custom_delivered_sec_qty);
	});
	if (!pending) return;
	frm.add_custom_button(__("Delivery Note (pending Nos)"), function() {
		frappe.model.open_mapped_doc({
			method: "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
			frm: frm,
		});
	}, __("Create"));
}

// A drawing that was cancelled leaves its DUNO row pointing at a dead document, and
// Frappe then refuses to save OR submit the order -- reporting it as a row number
// with no hint of which DUNO it means. Cancelling now releases the row by itself, so
// this is for orders that were already in that state: say which DUNO it is, and what
// puts it right, on the form where somebody can act on it.
//
// It has to be said here. Frappe checks links in _validate_links(), which runs before
// every server-side hook, so the same message raised from validate() is never reached.
function _so_warn_cancelled_drawings(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: "manufyxinvenzaerp.drawing_management.so_drawing_import.get_cancelled_drawing_links",
		args: { sales_order: frm.doc.name },
		callback(r) {
			let rows = (r.message || []);
			if (!rows.length) return;
			let lines = rows.map(function(d) {
				return __("Row {0} — DUNO {1} — {2}", [d.idx, d.duno_mark_no || "?", d.drawing]);
			}).join("<br>");
			frm.dashboard.clear_comment();
			frm.dashboard.add_comment(
				"<b>" + __("Cancelled drawing linked") + "</b><br>"
				+ __("This order cannot be saved or submitted while these rows point at a cancelled drawing:")
				+ "<br>" + lines + "<br>"
				+ __("Open each drawing and <b>Amend</b> it, then submit the amendment — the row re-attaches itself to the new revision."),
				"orange", true
			);
		},
	});
}

// ── Qty calculation in Raw Materials child table ───────────────────────────

frappe.ui.form.on("Sales Order Drawing Raw Material", {
	material_code(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (row.is_locked || !row.material_code) return;
		_so_reset_verification(frm);
		frappe.db.get_value("Item", row.material_code,
			["custom_unit_weight", "custom_parent_item_group"],
			function(v) {
				if (v) {
					frappe.model.set_value(cdt, cdn, "unit_weight", v.custom_unit_weight || 0);
					frappe.model.set_value(cdt, cdn, "parent_item_group", v.custom_parent_item_group || "");
				}
				_so_calc_rm_qty(frm, cdt, cdn);
			}
		);
	},
	sec_qty(frm, cdt, cdn)   { _so_reset_verification(frm); _so_calc_rm_qty(frm, cdt, cdn); },
	thickness(frm, cdt, cdn) { _so_reset_verification(frm); _so_calc_rm_qty(frm, cdt, cdn); },
	width(frm, cdt, cdn)     { _so_reset_verification(frm); _so_calc_rm_qty(frm, cdt, cdn); },
	length(frm, cdt, cdn)    { _so_reset_verification(frm); _so_calc_rm_qty(frm, cdt, cdn); }
});

// ── Finished goods: order lines in Kg, drawings in Nos (sep14 plan D1-D3) ────
//
// Verify Raw Materials checks each FG line against its Drawing List rows, so a change
// to either side after a pass means the pass no longer holds. The server clears the
// flag on save (sales_order.clear_verified_on_fg_change); this only shows it straight
// away instead of after the save.
//
// Only lines whose item has Drawing List rows are treated as drawing-built lines:
// the browser does not know which items are finished goods, and clearing the flag
// for an unrelated line would send it to the server as 0 on the next save.

frappe.ui.form.on("Sales Order Item", {
	qty(frm, cdt, cdn)            { _so_fg_line_changed(frm, cdt, cdn); },
	custom_sec_qty(frm, cdt, cdn) { _so_fg_line_changed(frm, cdt, cdn); },
	item_code(frm, cdt, cdn)      { _so_fg_line_changed(frm, cdt, cdn); }
});

function _so_fg_line_changed(frm, cdt, cdn) {
	var line = locals[cdt][cdn];
	var drawn = (frm.doc.custom_duno_items || []);
	if (!drawn.some(function(r) { return !r.drawing; })) return;
	if (!line.item_code || drawn.some(function(r) { return r.item === line.item_code; })) {
		_so_reset_verification(frm);
	}
}

// A pending Drawing List row: its Total is per Nos x Nos (D2), so typing either
// fills the Total, the same product Verify Raw Materials checks. A typed Total is left
// as it is -- Verify reports it if it does not agree. Rows with a Drawing are locked
// (read-only here, refused on the server) and change only through Update Customer
// Weight on the Drawing.
frappe.ui.form.on("Sales Order DUNO Item", {
	weight_per_pcs(frm, cdt, cdn) { _so_duno_weight_changed(frm, cdt, cdn, true); },
	total_quantity(frm, cdt, cdn) { _so_duno_weight_changed(frm, cdt, cdn, true); },
	total_weight(frm, cdt, cdn)   { _so_duno_weight_changed(frm, cdt, cdn, false); },
	item(frm, cdt, cdn)           { _so_duno_weight_changed(frm, cdt, cdn, false); }
});

function _so_duno_weight_changed(frm, cdt, cdn, recalc_total) {
	var row = locals[cdt][cdn];
	if (row.drawing) return;
	_so_reset_verification(frm);
	if (recalc_total && flt(row.weight_per_pcs) > 0 && flt(row.total_quantity) > 0) {
		var total = flt(flt(row.weight_per_pcs) * flt(row.total_quantity), 3);
		if (flt(row.total_weight, 3) !== total) {
			frappe.model.set_value(cdt, cdn, "total_weight", total);
		}
	}
	_so_render_bom_summary(frm);
}

function _so_calc_rm_qty(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	if (row.is_locked) return;
	var pig = row.parent_item_group || "";
	var uw = flt(row.unit_weight), L = flt(row.length),
	    W = flt(row.width), T = flt(row.thickness), sq = flt(row.sec_qty);

	// Look up total_quantity from the Drawing List for this drawing number
	var tq = 1;
	var cdn_val = row.customer_drawing_number;
	if (cdn_val && frm.doc.custom_duno_items) {
		var dr = frm.doc.custom_duno_items.find(function(r) { return r.drawing_number === cdn_val; });
		if (dr && dr.total_quantity) tq = flt(dr.total_quantity);
	}

	var qty = 0;
	if (pig === "Structurals") {
		if (L && uw && sq) qty = (L / 1000) * uw * sq;
	} else if (pig === "Plates") {
		if (L && W && T && uw && sq) qty = (L / 1000) * (W / 1000) * T * uw * sq;
	} else {
		qty = sq;
	}
	frappe.model.set_value(cdt, cdn, "qty", flt(qty, 3));
	frappe.model.set_value(cdt, cdn, "total_sec_qty", flt(sq * tq, 3));
	frappe.model.set_value(cdt, cdn, "total_weight", flt(qty * tq, 3));
	_so_roll_up_drawing_weight(frm, cdn_val);
	_so_render_bom_summary(frm);
}

// Keep the drawing's Calculated Weight in step with its rows as they are edited.
// The server recomputes the same total on save (sales_order.recalculate_raw_material_qty);
// this is only so the grid does not sit showing a figure the rows no longer add up to.
//
// total_weight, not qty -- and it has to stay the same choice the server makes, or
// the figure changes the moment the form is saved. qty is one piece's steel;
// total_weight is that times the drawing's piece count, which is the scale the
// customer weight it gets compared against is on. See drawing_calculated_weight.
function _so_roll_up_drawing_weight(frm, drawing_number) {
	if (!drawing_number) return;
	var dr = (frm.doc.custom_duno_items || []).find(function(r) {
		return r.drawing_number === drawing_number;
	});
	if (!dr) return;
	var total = (frm.doc.custom_so_raw_materials || []).reduce(function(sum, r) {
		return r.customer_drawing_number === drawing_number ? sum + flt(r.total_weight) : sum;
	}, 0);
	frappe.model.set_value(dr.doctype, dr.name, "calculated_weight", flt(total, 3));
}

// ── Summary of the loaded sheet, beside the file ──────────────────────────
//
// Customer weight is typed in from the sheet and describes the FINISHED piece.
// Calculated weight is never typed -- it is what the raw materials listed under
// the drawing add up to. Raw material above finished weight is the normal case
// (stock is cut down to the part); a drawing that comes out UNDER is the one
// worth looking at, so it is called out by name rather than buried in a total.

function _so_render_bom_summary(frm) {
	var fd = frm.fields_dict["custom_bom_summary_html"];
	if (!fd) return;
	var $w = fd.$wrapper;
	$w.empty();
	if (frm.doc.__islocal || frm.doc.docstatus === 2) return;

	var duno = frm.doc.custom_duno_items || [];
	var rows = frm.doc.custom_so_raw_materials || [];
	if (!duno.length && !rows.length) return;

	var created = duno.filter(function(r) { return !!r.drawing; }).length;

	var by_group = {};
	rows.forEach(function(r) {
		var g = (r.parent_item_group || __("Ungrouped")).trim();
		by_group[g] = (by_group[g] || 0) + 1;
	});
	var group_text = Object.keys(by_group).sort().map(function(g) {
		return by_group[g] + " " + g;
	}).join(" · ") || "—";

	var customer = 0, calculated = 0, under = [];
	duno.forEach(function(d) {
		var c = flt(d.total_weight), k = flt(d.calculated_weight);
		customer += c;
		calculated += k;
		if (c > 0 && k > 0 && k < c) under.push(d.duno_mark_no || d.drawing_number);
	});
	var diff = calculated - customer;
	var pct = customer ? (diff / customer) * 100 : 0;

	function row(label, value, color) {
		return '<div style="display:flex;justify-content:space-between;gap:12px;padding:3px 0">' +
			'<span style="color:var(--text-muted)">' + label + '</span>' +
			'<span style="font-weight:600' + (color ? ";color:" + color : "") + '">' + value + '</span></div>';
	}

	var verified = !!frm.doc.custom_raw_materials_verified;
	var html = '<div style="border:1px solid var(--border-color);border-radius:6px;padding:10px 12px;font-size:12px">' +
		'<div style="font-weight:700;margin-bottom:6px">' + __("Loaded Sheet") + '</div>' +
		row(__("Drawings"), duno.length + (created ? " (" + created + " " + __("created") + ")" : "")) +
		row(__("Raw material rows"), rows.length) +
		row(__("By group"), group_text) +
		'<hr style="margin:8px 0;border-top:1px solid var(--border-color)">' +
		row(__("Cust Weight (Total)"), format_number(customer, null, 2) + " Kg") +
		row(__("Calculated weight"), format_number(calculated, null, 2) + " Kg") +
		row(__("Difference"), (diff >= 0 ? "+" : "") + format_number(diff, null, 2) + " Kg (" +
			(pct >= 0 ? "+" : "") + format_number(pct, null, 1) + "%)") +
		row(__("Below customer weight"),
			under.length ? under.join(", ") : __("None"),
			under.length ? "var(--red-500)" : "var(--green-600)") +
		'<hr style="margin:8px 0;border-top:1px solid var(--border-color)">' +
		row(__("Raw materials"), verified ? __("Verified") : __("Not verified"),
			verified ? "var(--green-600)" : "var(--orange-500)") +
		'<div style="color:var(--text-muted);margin-top:8px;line-height:1.5">' +
			__("Cust Weight (Total) is the finished weight of all the pieces, typed in the sheet. Calculated weight is what the raw materials listed under each drawing add up to — normally the heavier of the two, since stock is cut down to the part.") +
		'</div></div>';

	$w.html(html);
}

// ── Verify Raw Materials button above the RM table ────────────────────────

function _so_render_rm_verify_btn(frm) {
	var fd = frm.fields_dict["custom_rm_verify_btn"];
	if (!fd) return;
	var $w = fd.$wrapper;
	$w.empty();
	if (frm.doc.__islocal || frm.doc.docstatus === 2) return;

	var $row = $('<div style="display:flex;align-items:center;gap:10px;padding:4px 0 8px">').appendTo($w);

	var has_unlocked = (frm.doc.custom_so_raw_materials || []).some(function(r) { return !r.is_locked; });
	var verified = !!frm.doc.custom_raw_materials_verified;

	if (has_unlocked) {
		var $verify = $('<button class="btn btn-sm btn-default">')
			.text(__("Verify Raw Materials"))
			.on("click", function() { _so_verify_rm(frm); })
			.appendTo($row);
		// Blue: nothing else on this Sales Order can proceed until it passes.
		// "View All" beside it stays grey -- see public/js/mfx_buttons.js.
		window.mfx_paint_el && window.mfx_paint_el($verify, "primary");
	}

	$('<button class="btn btn-sm btn-default">')
		.html(frappe.utils.icon("view", "sm") + "&nbsp;" + __("View All"))
		.on("click", function() { _so_show_table_popup(frm, "custom_so_raw_materials"); })
		.appendTo($row);

	if (!has_unlocked) return;

	if (verified) {
		$('<span style="color:green;font-weight:bold;font-size:13px;">').html("&#10003; " + __("Verified")).appendTo($row);
	} else {
		$('<span style="color:orange;font-size:12px;">').text(__("Not verified — required before creating drawings")).appendTo($row);
	}
}

function _so_reset_verification(frm) {
	if (frm.doc.custom_raw_materials_verified) {
		frm.doc.custom_raw_materials_verified = 0;
		_so_render_rm_verify_btn(frm);
		_so_render_bom_summary(frm);
	}
}

function _so_verify_rm(frm) {
	function _do_verify() {
		frappe.call({
			method: "manufyxinvenzaerp.drawing_management.so_drawing_import.verify_raw_materials",
			args: { so_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Verifying raw materials…"),
			callback: function(r) {
				if (!r.message) return;
				var res = r.message;
				// Sync modified timestamp so subsequent saves don't get conflict errors
				if (res.modified) { frm.doc.modified = res.modified; }
				frm.doc.custom_raw_materials_verified = res.verified ? 1 : 0;
				_so_render_rm_verify_btn(frm);
				_so_render_bom_summary(frm);
				// Warnings are not issues. They never block verification -- a DUNO
				// reused by an unrelated customer is their paperwork, not a fault in
				// this sheet -- so they are shown alongside a pass as well as a fail,
				// and worded as something to know rather than something to fix.
				var warns = res.warnings || [];
				var warn_html = warns.length
					? '<div style="margin-top:14px;padding:10px 12px;background:#fffbeb;'
						+ 'border-left:3px solid #f59e0b;border-radius:3px;">'
						+ "<b>" + __("{0} warning(s) — verification still passed:", [warns.length]) + "</b><br><br>"
						+ warns.map(function(w) { return "• " + w; }).join("<br><br>")
						+ "</div>"
					: "";

				if (res.verified) {
					if (warns.length) {
						frappe.msgprint({
							title: __("Verified — with warnings"),
							// Single quotes for the HTML attribute on purpose. This string
							// lives inside a Python triple-quoted literal, so a \" here is
							// consumed by Python and reaches the browser as a bare quote --
							// which closes the JS string early and breaks the whole Client
							// Script (SyntaxError, and the Sales Order form stops loading).
							message: "<p style='color:#22863a'>"
								+ __("All raw materials verified. Drawings can be created.")
								+ "</p>" + warn_html,
							indicator: "orange",
						});
					} else {
						frappe.show_alert({ message: __("All raw materials verified!"), indicator: "green" }, 5);
					}
				} else {
					var msg = "<b>" + res.issues.length + " " + __("issue(s) found:") + "</b><br><br>" +
						res.issues.map(function(i) { return "• " + i; }).join("<br>") + warn_html;
					frappe.msgprint({ title: __("Raw Material Issues"), message: msg, indicator: "orange" });
				}
			}
		});
	}
	if (frm.is_dirty()) {
		frm.save(undefined, function() { _do_verify(); });
	} else {
		_do_verify();
	}
}

// ── Inline Load / Clear buttons next to the attach field ──────────────────

function _so_render_file_buttons(frm) {
	var fd = frm.fields_dict["custom_bom_action_btns"];
	if (!fd) return;
	var $w = fd.$wrapper;
	$w.empty();
	if (frm.doc.__islocal || frm.doc.docstatus === 2) return;

	var has_file = !!frm.doc.custom_bom_excel_file;
	var has_drawing_created = (frm.doc.custom_duno_items || []).some(function(r) { return !!r.drawing; });

	// Lock the attach field once any drawing has been created
	frm.set_df_property("custom_bom_excel_file", "read_only", has_drawing_created ? 1 : 0);
	frm.refresh_field("custom_bom_excel_file");

	var $row = $('<div style="display:flex;gap:8px;padding:4px 0 8px">').appendTo($w);

	if (!has_file) {
		// No file yet — show Download Template only
		$('<button class="btn btn-sm btn-default">')
			.text(__("Download Template"))
			.on("click", function() {
				window.open(frappe.urllib.get_full_url(
					"/api/method/manufyxinvenzaerp.drawing_management.so_drawing_import.download_bom_template"
				));
			})
			.appendTo($row);
	} else {
		// File attached — show Load Items and Clear Items
		var $load = $('<button class="btn btn-sm btn-primary">')
			.text(__("Load Items"))
			.appendTo($row);
		if (has_drawing_created) {
			$load.prop("disabled", true)
				.attr("title", __("Drawings have been created — load is disabled"));
		} else {
			$load.on("click", function() { _so_load_excel(frm); });
		}

		var $clear = $('<button class="btn btn-sm btn-default">')
			.text(__("Clear Items"))
			.appendTo($row);
		if (has_drawing_created) {
			$clear.prop("disabled", true)
				.attr("title", __("Drawings have been created — clear is disabled"));
		} else {
			$clear.on("click", function() { _so_clear_import(frm); });
		}
	}
}

// ── Drawing group buttons (top bar) ───────────────────────────────────────

function _so_render_drawing_buttons(frm) {
	if (frm.doc.__islocal || frm.doc.docstatus === 2) return;

	// The Drawing group carries the whole drawing -> BOM sequence, so it is the
	// forward action on this form. Painting is idempotent and the buttons arrive
	// from several async callbacks, so every one of them calls this afterwards.
	function _paint_drawing_group() {
		window.mfx_paint_group && window.mfx_paint_group(frm, "Drawing", "primary");
	}

	var items = frm.doc.custom_duno_items || [];

	// Create Drawing — synchronous: no drawing exists yet
	var has_pending = items.some(function(r) { return r.create_drawing && !r.drawing; });
	if (has_pending) {
		frm.add_custom_button(__("Create Drawing"), function() {
			_so_create_drawings(frm);
		}, __("Drawing"));
			_paint_drawing_group();
	}

	// Remaining 3 buttons depend on live drawing docstatus — fetch async
	var drawing_names = items.filter(function(r) { return !!r.drawing; }).map(function(r) { return r.drawing; });
	if (!drawing_names.length) return;

	frappe.db.get_list("Drawing", {
		filters: [["name", "in", drawing_names]],
		fields: ["name", "docstatus", "status"],
		limit: drawing_names.length
	}).then(function(drawings) {
		var drafts   = new Set(drawings.filter(function(d) { return d.docstatus === 0; }).map(function(d) { return d.name; }));
		var subm_nf  = new Set(drawings.filter(function(d) { return d.docstatus === 1 && d.status !== "Final Revision"; }).map(function(d) { return d.name; }));
		var final    = new Set(drawings.filter(function(d) { return d.status === "Final Revision"; }).map(function(d) { return d.name; }));

		// Submit Drawing — only if drafts exist with checkbox on
		var submit_count = items.filter(function(r) { return r.submit_drawing && drafts.has(r.drawing); }).length;
		if (submit_count) {
			frm.add_custom_button(__("Submit Drawing"), function() {
				_so_run_step(frm, "submit", __("Submit Drawing"), __("Submitting Drawings…"), submit_count, __("Submit"));
			}, __("Drawing"));
			_paint_drawing_group();
		}

		// Mark as Final Revision — only if submitted (non-final) drawings with checkbox on
		var final_count = items.filter(function(r) { return r.mark_final_revision && subm_nf.has(r.drawing); }).length;
		if (final_count) {
			frm.add_custom_button(__("Mark as Final Revision"), function() {
				if (frm.doc.docstatus !== 1) {
					frappe.msgprint({
						title: __("Sales Order Not Submitted"),
						message: __("Please submit the Sales Order before marking drawings as Final Revision."),
						indicator: "orange",
					});
					return;
				}
				_so_run_step(frm, "final_revision", __("Mark as Final Revision"), __("Marking Final Revision…"), final_count, __("Final Revision"));
			}, __("Drawing"));
			_paint_drawing_group();
		}

		// BOM — one button, and only while there is a BOM left to make.
		//
		// A drawing only reaches this stage once it is a Final Revision, so the group
		// reads as a sequence: submit the drawing, mark it final, then make its BOM.
		// Creating a BOM without submitting it was a second way to do the same job that
		// left drafts nobody chased, so there is one button now, not two.
		//
		// Once every final drawing has a submitted BOM there is nothing left to create,
		// and the button used to stay put and answer a click with "already created".
		// It is replaced by View Drawing instead, so the group says what is left to do
		// rather than offering work that is finished.
		// Not while there is still a drawing waiting to be marked final. The two are
		// consecutive steps, not alternatives, and offering both at once invites the
		// BOM to be made for the drawings that happen to be ready while the rest are
		// quietly left behind -- which reads as "the BOMs are done" when they are not.
		var final_names = items.filter(function(r) { return final.has(r.drawing); })
			.map(function(r) { return r.drawing; });
		if (final_names.length && !final_count) {
			var bom_candidates = items.filter(function(r) { return r.create_bom && final.has(r.drawing); });
			frappe.db.get_list("BOM", {
				filters: [["custom_drawing", "in", final_names], ["docstatus", "=", 1]],
				fields: ["custom_drawing"],
				limit: final_names.length,
			}).then(function(existing) {
				var done = new Set(existing.map(function(b) { return b.custom_drawing; }));
				var pending = bom_candidates.filter(function(r) { return !done.has(r.drawing); });

				if (pending.length) {
					frm.add_custom_button(__("Create and Submit BOM"), function() {
						_so_run_step(frm, "create_and_submit_bom", __("Create and Submit BOM"),
							__("Creating and Submitting BOMs…"), pending.length, __("Create BOM"));
					}, __("Drawing"));
			_paint_drawing_group();
				} else if (final_names.every(function(n) { return done.has(n); })) {
					frm.add_custom_button(__("View Drawing"), function() {
						// Says the drawing stage is finished, and where the work goes next.
						// Reaching this button at all means every drawing is final and every
						// one has a submitted BOM, so there is nothing left to do here.
						frappe.msgprint({
							title: __("Drawings and BOMs Ready"),
							message: __("Drawings and BOMs are created — ready to proceed to <b>Material Planning</b>."),
							indicator: "green",
						});
						frappe.set_route("List", "Drawing", { sales_order: frm.doc.name });
					}, __("Drawing"));
			_paint_drawing_group();
				}
			});
		}

		// Submit BOM — only if draft BOMs already exist
		frappe.db.get_list("BOM", {
			filters: [["custom_drawing", "in", drawing_names], ["docstatus", "=", 0]],
			fields: ["name", "custom_drawing"],
			limit: drawing_names.length
		}).then(function(draft_boms) {
			if (draft_boms.length) {
				frm.add_custom_button(__("Submit BOM"), function() {
					_so_run_step(frm, "submit_bom", __("Submit BOM"), __("Submitting BOMs…"), draft_boms.length, null);
				}, __("Drawing"));
			_paint_drawing_group();
			}
		});
	});
}

// ── View All button above the Drawing List grid ───────────────────────────

function _so_render_duno_view_all_btn(frm) {
	var grid = frm.fields_dict["custom_duno_items"] && frm.fields_dict["custom_duno_items"].grid;
	if (!grid) return;
	var $top = grid.wrapper.find(".grid-custom-buttons");
	$top.empty();
	$('<button class="btn btn-default btn-sm">')
		.html(frappe.utils.icon("view", "xs") + " " + __("View All"))
		.on("click", function() { _so_show_table_popup(frm, "custom_duno_items"); })
		.appendTo($top);
}

// ── Action implementations ─────────────────────────────────────────────────

function _so_load_excel(frm) {
	var has_locked = (frm.doc.custom_duno_items || []).some(function(r) { return !!r.drawing; });
	var do_load = function() {
		frappe.call({
			method: "manufyxinvenzaerp.drawing_management.so_drawing_import.parse_bom_excel",
			args: { so_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Parsing Excel file…"),
			callback: function(r) {
				if (!r.message) return;
				var res = r.message;
				frm.reload_doc().then(function() {
					return _so_sync_fg_lines_from_drawings(frm);
				}).then(function(sync) {
					var msg = __("{0} drawing(s) and {1} raw material row(s) loaded.", [res.drawing_count, res.item_count]);
					if (sync.updated) {
						msg += "<br>" + __("Sales Order Kg and Nos updated from the Drawing List for {0} item(s).", [sync.updated]);
					}
					var warnings = (res.warnings || []).concat(sync.warnings);
					if (warnings.length) {
						frappe.msgprint({ title: __("Loaded with Warnings"),
							message: msg + "<br><br><b>" + __("Warnings:") + "</b><br>" + warnings.join("<br>"),
							indicator: "orange" });
					} else {
						frappe.show_alert({ message: $("<div>").html(msg).text(), indicator: "green" }, 5);
					}
				});
			}
		});
	};
	if (has_locked) {
		frappe.confirm(__("Some drawings are already created. Only rows without a drawing will be reloaded. Continue?"), do_load);
	} else {
		do_load();
	}
}

// The Excel loader stages Drawing List rows directly in the database. Copy their
// customer-provided Kg and Total Qty into the matching FG order line, then save
// through the form so ERPNext recalculates amounts and order totals as usual.
function _so_sync_fg_lines_from_drawings(frm) {
	var totals = {};
	(frm.doc.custom_duno_items || []).forEach(function(row) {
		if (!row.item) return;
		var t = totals[row.item] || (totals[row.item] = { kg: 0, nos: 0 });
		t.kg += flt(row.total_weight);
		t.nos += flt(row.total_quantity);
	});
	var warnings = [], changes = [], updated = 0;
	Object.keys(totals).forEach(function(item_code) {
		var lines = (frm.doc.items || []).filter(function(line) { return line.item_code === item_code; });
		// A new order can have one default FG placeholder line before the sheet is
		// loaded. Replace it only when the sheet names exactly one FG item and the
		// line still has the default 1 Kg / 0 Nos; other mismatches need review.
		var placeholder = !lines.length && Object.keys(totals).length === 1
			&& (frm.doc.items || []).length === 1 ? frm.doc.items[0] : null;
		if (placeholder && flt(placeholder.qty, 3) === 1
			&& flt(placeholder.custom_sec_qty, 3) === 0) {
			lines = [placeholder];
		}
		if (lines.length !== 1) {
			warnings.push(__("FG Item {0}: expected one matching Sales Order item line, found {1}. Match its FG item, Kg and Nos to the drawing sheet.",
				[item_code, lines.length]));
			return;
		}
		var line = lines[0], t = totals[item_code];
		var kg = flt(t.kg, 3), nos = flt(t.nos, 3);
		if (line.item_code === item_code && flt(line.qty, 3) === kg
			&& flt(line.custom_sec_qty, 3) === nos) return;
		changes.push({ line: line, item_code: item_code, kg: kg, nos: nos });
	});
	if (!changes.length) return Promise.resolve({ updated: 0, warnings: warnings });
	if (frm.doc.docstatus !== 0) {
		warnings.push(__("Submit-state Sales Order item quantities cannot be updated by Load Items. Set the Kg and Nos through the permitted amendment flow."));
		return Promise.resolve({ updated: 0, warnings: warnings });
	}
	var chain = Promise.resolve();
	changes.forEach(function(change) {
		chain = chain.then(function() {
			if (change.line.item_code !== change.item_code) {
				return frappe.model.set_value(change.line.doctype, change.line.name,
					"item_code", change.item_code);
			}
		}).then(function() {
			return frappe.model.set_value(change.line.doctype, change.line.name, "qty", change.kg);
		}).then(function() {
			return frappe.model.set_value(change.line.doctype, change.line.name, "custom_sec_qty", change.nos);
		}).then(function() { updated += 1; });
	});
	return chain.then(function() {
		return frm.save().then(function() { return { updated: updated, warnings: warnings }; });
	});
}

function _so_create_drawings(frm) {
	if (!frm.doc.custom_raw_materials_verified) {
		frappe.msgprint({
			title: __("Verification Required"),
			message: __("Please click <b>Verify Raw Materials</b> above the Raw Materials table and resolve all issues before creating drawings."),
			indicator: "orange"
		});
		return;
	}
	var items = frm.doc.custom_duno_items || [];
	var count = items.filter(function(r) { return r.create_drawing && !r.drawing; }).length;
	var confirm_msg = __("{0} drawing(s) will be created.", [count]) + "<br><br>" +
		__("To skip any drawing, uncheck <b>Create Drawing</b> in the Drawing List row.");
	frappe.confirm(confirm_msg, function() {
		_so_run_batched(frm, {
			method: "manufyxinvenzaerp.drawing_management.so_drawing_import.create_drawings_from_import",
			title: __("Create Drawing"),
			args: { so_name: frm.doc.name },
			count: count,
		});
	});
}

function _so_run_step(frm, step, label, freeze_msg, count, checkbox_label) {
	var confirm_msg = __("{0} drawing(s) will be processed: <b>{1}</b>.", [count || "", label]);
	if (checkbox_label) {
		confirm_msg += "<br><br>" + __("To skip any drawing, uncheck <b>{0}</b> in the Drawing List row.", [checkbox_label]);
	}
	frappe.confirm(confirm_msg, function() {
		_so_run_batched(frm, {
			method: "manufyxinvenzaerp.drawing_management.so_drawing_import.process_drawings",
			title: label,
			args: { so_name: frm.doc.name, step: step },
			count: count,
		});
	});
}

// ── Batched runner — processes in chunks of 30, shows live progress ───────────

function _so_run_batched(frm, opts) {
	var BATCH_SIZE = 30;
	var all_results = [];
	var batch_start = 0;
	// Counts only move when a batch returns (~4s on BOM creation), but elapsed time
	// and the estimate can tick every second -- so the dialog looks alive between
	// round trips instead of appearing frozen for four seconds at a time.
	var started_at = Date.now();
	var last = { processed: 0, total: opts.count || 1, done: false };
	var ticker = null;

	// Create dialog with a pre-wired Close button (hidden until done)
	var d = new frappe.ui.Dialog({
		title: opts.title,
		size: "small",
		primary_action_label: __("Close & Reload"),
		primary_action: function() { d.hide(); frm.reload_doc(); }
	});
	// Hide Close button and X while running
	d.get_primary_btn().hide();
	d.$wrapper.find(".modal-header .close").hide();
	d.$body.html(_so_progress_html(0, opts.count || 1, [], false, _so_timing(started_at, 0, opts.count || 1, false)));
	d.show();

	// Refresh only the clock/estimate line, not the whole body: re-rendering would
	// reset the scroll position of the error list and restart the bar animation.
	ticker = setInterval(function() {
		if (last.done) { clearInterval(ticker); return; }
		var t = _so_timing(started_at, last.processed, last.total, false);
		var $el = d.$body.find(".so-eta");
		if ($el.length) $el.html(t.html);
	}, 1000);

	function _next() {
		var args = Object.assign({}, opts.args, {
			batch_start: batch_start,
			batch_size: BATCH_SIZE
		});
		frappe.call({
			method: opts.method,
			args: args,
			callback: function(r) {
				var res = (r && r.message) || {};
				var batch_results = res.results || [];
				all_results = all_results.concat(batch_results);
				var processed = res.processed != null ? res.processed : (batch_start + batch_results.length);
				var total = res.total || processed;
				var done = (res.next_start === null || res.next_start === undefined || processed >= total);

				last = { processed: processed, total: total, done: done };
				d.$body.html(_so_progress_html(processed, total, all_results, done,
					_so_timing(started_at, processed, total, done)));

				if (done && ticker) clearInterval(ticker);

				if (!done) {
					batch_start = res.next_start;
					_next();
				} else {
					// Show Close button and X — do NOT reload yet; let the user read the results
					d.get_primary_btn().show();
					d.$wrapper.find(".modal-header .close").show();
				}
			},
			error: function() {
				if (ticker) clearInterval(ticker);
				d.hide();
				frappe.msgprint(__("A server error occurred — check the error log for details."));
				frm.reload_doc();
			}
		});
	}
	_next();
}

// Elapsed / remaining / estimate, measured from this run's own throughput rather
// than a fixed guess -- BOM creation runs at roughly 8 per second on a warm site and
// far slower on a cold one, so a hardcoded rate would be wrong on both.
//
// No estimate is offered until a batch has actually completed: extrapolating from a
// part-finished first batch produces a wild number that then collapses, which reads
// as a bug even though the job is fine.
function _so_timing(started_at, processed, total, done) {
	var elapsed = Math.max(0, (Date.now() - started_at) / 1000);
	var pending = Math.max(0, total - processed);
	var rate = processed > 0 ? processed / elapsed : 0;

	function fmt(sec) {
		sec = Math.round(sec);
		if (sec < 60) return sec + "s";
		var m = Math.floor(sec / 60), r = sec % 60;
		return m + "m " + (r < 10 ? "0" : "") + r + "s";
	}

	var eta_txt;
	if (done) eta_txt = __("finished in {0}", [fmt(elapsed)]);
	else if (processed <= 0 || rate <= 0) eta_txt = __("estimating…");
	else eta_txt = __("about {0} left", [fmt(pending / rate)]);

	var html =
		'<span>' + __("Elapsed") + ' <b>' + fmt(elapsed) + '</b></span>' +
		'<span style="margin:0 10px;color:#cbd5e0">|</span>' +
		'<span>' + eta_txt + '</span>' +
		(rate > 0 && !done
			? '<span style="margin:0 10px;color:#cbd5e0">|</span><span>' +
			  rate.toFixed(1) + ' ' + __("per second") + '</span>'
			: '');

	return { elapsed: elapsed, pending: pending, rate: rate, html: html };
}


function _so_progress_html(processed, total, results, done, timing) {
	var pct  = total ? Math.min(100, Math.round((processed / total) * 100)) : 0;
	var ok   = results.filter(function(x) { return x.status === "success"; }).length;
	var err  = results.filter(function(x) { return x.status === "error"; }).length;
	var skip = results.filter(function(x) {
		return x.status === "skipped" || x.status === "unchecked" || x.status === "already_done";
	}).length;

	var has_err = err > 0;
	var clr_main = has_err ? "#e53e3e" : (done ? "#38a169" : "#5a67d8");

	// Inject keyframe CSS once into the page
	if (!document.getElementById("_so_pg_css")) {
		var _s = document.createElement("style");
		_s.id = "_so_pg_css";
		_s.textContent = "@keyframes _so_shine{0%{background-position:-400px 0}100%{background-position:400px 0}}"
			+ "@keyframes _so_spin{to{transform:rotate(360deg)}}";
		document.head.appendChild(_s);
	}

	// Progress bar style — animated shimmer while running, solid gradient when done
	var bar_style;
	if (done) {
		bar_style = "background:" + (has_err
			? "linear-gradient(90deg,#fc8181,#e53e3e)"
			: "linear-gradient(90deg,#68d391,#38a169)") + ";";
	} else {
		bar_style = "background-image:linear-gradient(90deg,#5a67d8 0%,#9f7aea 50%,#5a67d8 100%);"
			+ "background-size:800px 100%;animation:_so_shine 1.8s linear infinite;";
	}

	// Status icon — spinner while running, circle-check/warn when done
	var icon_html;
	if (done && !has_err) {
		icon_html = '<span style="display:inline-flex;align-items:center;justify-content:center;'
			+ 'width:34px;height:34px;border-radius:50%;background:#c6f6d5;color:#276749;font-size:18px;font-weight:700;">&#10003;</span>';
	} else if (done && has_err) {
		icon_html = '<span style="display:inline-flex;align-items:center;justify-content:center;'
			+ 'width:34px;height:34px;border-radius:50%;background:#fed7d7;color:#c53030;font-size:18px;">&#9888;</span>';
	} else {
		icon_html = '<span style="display:inline-flex;align-items:center;justify-content:center;'
			+ 'width:34px;height:34px;border-radius:50%;background:#ebf4ff;">'
			+ '<span style="width:18px;height:18px;border:3px solid #c3dafe;border-top-color:#5a67d8;'
			+ 'border-radius:50%;animation:_so_spin 0.8s linear infinite;display:inline-block;"></span></span>';
	}

	var lbl = done
		? (has_err ? __("Completed with errors") : __("Complete"))
		: __("Processing…");

	var html = '<div style="padding:20px 16px 14px;">';

	// Header: icon + label on left, large % on right
	html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">';
	html += '<div style="display:flex;align-items:center;gap:12px;">' + icon_html;
	html += '<div><div style="font-size:14px;font-weight:700;color:#1a202c;line-height:1.2;">' + lbl + '</div>';
	html += '<div style="font-size:11px;color:#a0aec0;margin-top:2px;">'
		+ '<b style="color:#4a5568">' + processed + '</b> ' + __("done")
		+ ' &nbsp;·&nbsp; <b style="color:#4a5568">' + Math.max(0, total - processed) + '</b> ' + __("pending")
		+ ' &nbsp;·&nbsp; ' + total + ' ' + __("total") + '</div></div>';
	html += '</div>';
	html += '<span style="font-size:36px;font-weight:800;color:' + clr_main + ';line-height:1;letter-spacing:-1px;">'
		+ pct + '<span style="font-size:16px;font-weight:500;color:#a0aec0;">%</span></span>';
	html += '</div>';

	// Progress bar track
	html += '<div style="background:#e2e8f0;border-radius:999px;height:10px;overflow:hidden;'
		+ 'margin-bottom:16px;box-shadow:inset 0 1px 3px rgba(0,0,0,0.08);">';
	html += '<div style="' + bar_style + 'width:' + pct + '%;height:100%;border-radius:999px;transition:width 0.35s ease;"></div>';
	html += '</div>';

	// Ticks every second between batches -- see the ticker in _so_run_batched.
	html += '<div class="so-eta" style="font-size:11px;color:#718096;margin:-8px 0 14px;display:flex;align-items:center;">'
		+ ((timing && timing.html) || "") + '</div>';

	// Stats pills
	if (results.length) {
		html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:' + (err ? "12" : "0") + 'px;">';
		if (ok)
			html += '<span style="display:inline-flex;align-items:center;gap:5px;background:#f0fff4;color:#276749;'
				+ 'border:1px solid #9ae6b4;border-radius:999px;padding:5px 14px;font-size:12px;font-weight:600;">'
				+ '&#10003;&nbsp;' + ok + '&nbsp;' + __("succeeded") + '</span>';
		if (err)
			html += '<span style="display:inline-flex;align-items:center;gap:5px;background:#fff5f5;color:#c53030;'
				+ 'border:1px solid #fed7d7;border-radius:999px;padding:5px 14px;font-size:12px;font-weight:600;">'
				+ '&#10007;&nbsp;' + err + '&nbsp;' + __("failed") + '</span>';
		if (skip)
			html += '<span style="display:inline-flex;align-items:center;gap:5px;background:#fffaf0;color:#c05621;'
				+ 'border:1px solid #fbd38d;border-radius:999px;padding:5px 14px;font-size:12px;font-weight:600;">'
				+ '&#8677;&nbsp;' + skip + '&nbsp;' + __("skipped") + '</span>';
		html += '</div>';

		// Error detail list
		if (err) {
			var errors = results.filter(function(x) { return x.status === "error"; });
			html += '<div style="max-height:130px;overflow-y:auto;font-size:11px;background:#fff5f5;'
				+ 'border:1px solid #fed7d7;border-radius:8px;padding:10px 12px;margin-top:4px;">';
			errors.forEach(function(e) {
				html += '<div style="display:flex;gap:6px;margin-bottom:5px;align-items:flex-start;">'
					+ '<span style="color:#e53e3e;font-weight:700;flex-shrink:0;margin-top:1px;">&#10007;</span>'
					+ '<span><b style="color:#c53030;">' + frappe.utils.escape_html(e.drawing_number || e.drawing || "") + '</b>'
					+ '<span style="color:#742a2a;">: ' + frappe.utils.escape_html(e.error || "") + '</span></span>'
					+ '</div>';
			});
			html += '</div>';
		}
	}

	html += '</div>';
	return html;
}

function _so_clear_import(frm) {
	var has_locked = (frm.doc.custom_duno_items || []).some(function(r) { return !!r.drawing; });
	var msg = has_locked
		? __("Remove the attached file and all import rows without a created Drawing? Rows with Drawings will be kept.")
		: __("Remove the attached file and all import rows?");
	frappe.confirm(msg, function() {
		frappe.call({
			method: "manufyxinvenzaerp.drawing_management.so_drawing_import.clear_drawing_import",
			args: { so_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Clearing…"),
			callback: function(r) {
				if (!r.message) return;
				var res = r.message;
				frappe.show_alert({ message: __("{0} drawing row(s) and {1} item row(s) cleared.",
					[res.deleted_drawings, res.deleted_items]), indicator: "blue" }, 5);
				frm.reload_doc();
			}
		});
	});
}

// ── Column definitions for each table's View All popup ────────────────────

const _SO_TABLE_VIEW_CONFIG = {
	custom_duno_items: {
		title: "Drawing List",
		filters: [
			{ fieldname: "duno_mark_no",   label: "Filter DUNO/Mark No…" },
			{ fieldname: "drawing_number", label: "Filter Cust Drawing Number…" },
		],
		cols: [
			{ fieldname: "assembly_group",      label: "Assembly Group" },
			{ fieldname: "item",                label: "FG Item" },
			{ fieldname: "item_name",           label: "Item Name" },
			{ fieldname: "duno_mark_no",        label: "DUNO/Mark No" },
			{ fieldname: "drawing_number",      label: "Cust Drawing Number" },
			{ fieldname: "total_quantity",      label: "Total Quantity" },
			// Same labels as the grid and the upload template (sep14 plan D30).
			{ fieldname: "weight_per_pcs",      label: "Cust Weight (per Nos)" },
			{ fieldname: "total_weight",        label: "Cust Weight (Total)" },
			{ fieldname: "calculated_weight",   label: "Calculated Weight (Kg)" },
			{ fieldname: "difference_kg",       label: "Difference Kg" },
			{ fieldname: "drawing",             label: "Drawing" },
			{ fieldname: "create_drawing",      label: "Create Drawing" },
			{ fieldname: "submit_drawing",      label: "Submit" },
			{ fieldname: "mark_final_revision", label: "Final Revision" },
			{ fieldname: "create_bom",          label: "Create BOM" },
		],
	},
	custom_so_raw_materials: {
		title: "Raw Materials",
		filters: [
			{ fieldname: "customer_drawing_number", label: "Filter Drawing No…" },
			{ fieldname: "material_code",           label: "Filter Material Code…" },
		],
		cols: [
			{ fieldname: "customer_drawing_number", label: "Drawing No" },
			{ fieldname: "item_no",                 label: "Item No" },
			{ fieldname: "material_code",           label: "Material Code" },
			{ fieldname: "material_name",           label: "Material Name" },
			{ fieldname: "item_group",               label: "Item Group" },
			{ fieldname: "parent_item_group",         label: "Parent Item Group" },
			{ fieldname: "grade",                   label: "Grade" },
			{ fieldname: "thickness",               label: "Thickness" },
			{ fieldname: "width",                   label: "Width" },
			{ fieldname: "length",                  label: "Length" },
			{ fieldname: "sec_qty",                 label: "Reqd Sec Qty" },
			{ fieldname: "sec_uom",                 label: "Sec UOM" },
			{ fieldname: "total_sec_qty",            label: "Total Sec Qty" },
			{ fieldname: "unit_weight",              label: "Unit Weight" },
			{ fieldname: "qty",                     label: "Weight (Primary UOM)" },
			{ fieldname: "uom",                     label: "UOM" },
			{ fieldname: "total_weight",             label: "Total Weight" },
			{ fieldname: "is_locked",               label: "Locked" },
		],
	},
};

// Generic View All popup — read-only, all configured columns, scrollable
function _so_show_table_popup(frm, fieldname) {
	var cfg = _SO_TABLE_VIEW_CONFIG[fieldname];
	if (!cfg) return;
	var rows = frm.doc[fieldname] || [];
	if (!rows.length) {
		frappe.msgprint(__("No data to display."));
		return;
	}

	var th_style = 'white-space:nowrap;padding:6px 10px;background:#f4f5f7;border-bottom:2px solid #d1d8dd;font-weight:600;font-size:11px;';
	var thead = '<tr>' + cfg.cols.map(function(c) {
		return '<th style="' + th_style + '">' + __(c.label) + '</th>';
	}).join('') + '</tr>';

	function _render_tbody(filtered_rows) {
		return filtered_rows.map(function(row, idx) {
			var cells = cfg.cols.map(function(c) {
				var val = row[c.fieldname];
				if (val === null || val === undefined) val = '';
				return '<td style="padding:5px 10px;white-space:nowrap;border-bottom:1px solid #f0f0f0;">'
					+ frappe.utils.escape_html(String(val)) + '</td>';
			}).join('');
			var bg = idx % 2 !== 0 ? 'background:#fafbfc;' : '';
			return '<tr style="' + bg + '">' + cells + '</tr>';
		}).join('');
	}

	var filter_bar = '<div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;">'
		+ cfg.filters.map(function(f, i) {
			return '<input id="_so_vw_f' + i + '" type="text" placeholder="' + __(f.label) + '"'
				+ ' style="border:1px solid #d1d8dd;border-radius:4px;padding:4px 8px;font-size:12px;width:200px;">';
		}).join('')
		+ '<span id="_so_vw_count" style="font-size:12px;color:#6c757d;"></span></div>';

	var table_html = '<div style="overflow:auto;max-height:65vh;">'
		+ '<table style="font-size:12px;border-collapse:collapse;width:100%;" id="_so_vw_table">'
		+ '<thead style="position:sticky;top:0;z-index:1;">' + thead + '</thead>'
		+ '<tbody id="_so_vw_tbody">' + _render_tbody(rows) + '</tbody>'
		+ '</table></div>';

	var d = new frappe.ui.Dialog({
		title: __(cfg.title + " — {0} item(s)", [rows.length]),
		size: "extra-large",
	});
	d.$body.html(filter_bar + table_html);

	function _apply_filter() {
		var queries = cfg.filters.map(function(f, i) {
			return { fieldname: f.fieldname, q: (d.$body.find("#_so_vw_f" + i).val() || "").toLowerCase() };
		});
		var filtered = rows.filter(function(r) {
			return queries.every(function(qf) {
				return !qf.q || String(r[qf.fieldname] || "").toLowerCase().includes(qf.q);
			});
		});
		d.$body.find("#_so_vw_tbody").html(_render_tbody(filtered));
		d.$body.find("#_so_vw_count").text(filtered.length + " / " + rows.length + " " + __("rows"));
	}
	cfg.filters.forEach(function(f, i) { d.$body.find("#_so_vw_f" + i).on("input", _apply_filter); });
	_apply_filter();
	d.show();
}
""".strip()


def create_default_warehouse_types():
    """Ensure the Warehouse Type master records ERPNext's own
    Company.create_default_warehouses() links to already exist. Core creates a
    "Goods In Transit" warehouse with warehouse_type="Transit" for every new
    company, and Frappe's Link validation fails outright if that Warehouse Type
    record doesn't exist yet -- so this must run before any Company can be
    created, whether that's a real company on a live site or a test-runner
    fixture on a fresh install."""
    for wt in ["Stores", "Work In Progress", "Finished Goods", "Transit"]:
        if not frappe.db.exists("Warehouse Type", wt):
            frappe.get_doc({"doctype": "Warehouse Type", "name": wt}).insert(ignore_permissions=True)
    frappe.db.commit()


def after_install():
    create_default_warehouse_types()
    seed_material_grades()
    create_item_custom_fields()
    create_item_client_script()
    create_purchase_order_custom_fields()
    hide_purchase_order_weight_fields()
    create_purchase_order_client_script()
    create_purchase_receipt_custom_fields()
    layout_purchase_receipt_item_grid()
    create_batch_custom_fields()
    create_purchase_receipt_client_script()
    create_material_request_custom_fields()
    create_material_request_client_script()
    create_rfq_custom_fields()
    create_rfq_client_script()
    create_sq_custom_fields()
    create_sq_client_script()
    create_so_custom_fields()
    create_so_client_script()
    create_bom_custom_fields()
    create_bom_client_script()
    create_production_plan_custom_fields()
    # After both of the above: its BOM fields anchor on custom_customer_drawing_number
    # and its Production Plan Item fields on custom_material_planning, so on a fresh
    # install those anchors have to exist first or the new fields land at the bottom.
    create_rate_schedule_sync_fields()
    layout_production_plan_item_grid()
    create_production_plan_client_script()
    # Work Order and Job Card are deliberately left standard -- every customization
    # this app once added to them was removed under the client's Phase 0.4 change
    # request, and Subcontracting Order / Operation Entry carry that work instead.
    create_stock_entry_custom_fields()
    hide_duplicate_sco_field()
    create_stock_entry_client_script()
    create_doctype_label_translations()
    remove_sco_purchase_order_mandatory()
    hide_sco_job_worker_warehouse()
    hide_sco_unused_tabs()
    hide_sco_amount_fields()
    make_sco_job_worker_conditional()
    add_sco_working_status()
    create_sco_custom_fields()
    create_sco_client_script()
    create_sco_ops_client_script()
    create_soe_client_script()
    create_material_planning_auto_purchase_fields()
    create_manufacturing_settings_custom_fields()
    create_payment_request_custom_fields()
    # Finished goods in Kg, counted in Nos per drawing (sep14 FG plan). After the
    # SO / BOM / PP / SCO / Batch functions above, which add their share of it.
    create_fg_sales_custom_fields()
    create_fg_property_setters()
    set_fg_settings_defaults()
    from manufyxinvenzaerp.production_management.production_utils import (
        create_operations_workstations_routing,
    )
    create_operations_workstations_routing()


def after_migrate():
    from frappe.installer import add_module_defs
    add_module_defs("manufyxinvenzaerp", ignore_if_duplicate=True)

    create_default_warehouse_types()
    # Before the Item fields, which Link to it, and before anything validates a grade
    # already stored on a Sales Order against the master.
    seed_material_grades()
    prepare_material_spec_link()
    create_item_custom_fields()
    create_item_client_script()
    create_purchase_order_custom_fields()
    hide_purchase_order_weight_fields()
    create_purchase_order_client_script()
    create_purchase_receipt_custom_fields()
    layout_purchase_receipt_item_grid()
    create_batch_custom_fields()
    create_purchase_receipt_client_script()
    create_material_request_custom_fields()
    create_material_request_client_script()
    create_rfq_custom_fields()
    create_rfq_client_script()
    create_sq_custom_fields()
    create_sq_client_script()
    create_so_custom_fields()
    create_so_client_script()
    create_bom_custom_fields()
    create_bom_client_script()
    create_production_plan_custom_fields()
    # After both of the above: its BOM fields anchor on custom_customer_drawing_number
    # and its Production Plan Item fields on custom_material_planning, so on a fresh
    # install those anchors have to exist first or the new fields land at the bottom.
    create_rate_schedule_sync_fields()
    layout_production_plan_item_grid()
    create_production_plan_client_script()
    # Work Order and Job Card are deliberately left standard -- every customization
    # this app once added to them was removed under the client's Phase 0.4 change
    # request, and Subcontracting Order / Operation Entry carry that work instead.
    create_stock_entry_custom_fields()
    hide_duplicate_sco_field()
    create_stock_entry_client_script()
    create_doctype_label_translations()
    remove_sco_purchase_order_mandatory()
    hide_sco_job_worker_warehouse()
    hide_sco_unused_tabs()
    hide_sco_amount_fields()
    make_sco_job_worker_conditional()
    add_sco_working_status()
    create_sco_custom_fields()
    create_sco_client_script()
    create_sco_ops_client_script()
    create_soe_client_script()
    create_material_planning_auto_purchase_fields()
    create_manufacturing_settings_custom_fields()
    create_payment_request_custom_fields()
    # Finished goods in Kg, counted in Nos per drawing (sep14 FG plan). After the
    # SO / BOM / PP / SCO / Batch functions above, which add their share of it.
    create_fg_sales_custom_fields()
    create_fg_property_setters()
    set_fg_settings_defaults()
    from manufyxinvenzaerp.production_management.production_utils import (
        create_operations_workstations_routing,
    )
    create_operations_workstations_routing()
    setup_storage_location()
    clear_item_default_boms()


def clear_item_default_boms():
    """No Item carries a default BOM on this app, and none should.

    An item here is a shape of steel, not a product: one finished-goods item has
    hundreds of BOMs, one per drawing, and which one applies is decided by the drawing.
    Stock ERPNext nominates one of them as the item's default and stamps it on the Item
    master, and every Sales Order line for that item then arrives with that arbitrary
    BOM attached -- or refuses to open at all, with "Could not find Row #1: BOM No: ...",
    once the BOM it points at is gone.

    BOM.manage_default_bom is overridden to stop writing the field. This sweeps up
    anything already there, and anything a route outside that override sets later: an
    import, a manual edit on the Item form, or a site restored from a database that
    predates the override."""
    stale = frappe.get_all("Item", filters={"default_bom": ["!=", ""]}, pluck="name")
    if stale:
        frappe.db.set_value("Item", {"name": ["in", stale]}, "default_bom", None,
                            update_modified=False)
        print("Cleared default BOM on %d item(s): %s" % (len(stale), ", ".join(stale[:5])))
    flagged = frappe.get_all("BOM", filters={"is_default": 1}, pluck="name")
    if flagged:
        frappe.db.set_value("BOM", {"name": ["in", flagged]}, "is_default", 0,
                            update_modified=False)
        print("Cleared is_default on %d BOM(s)" % len(flagged))


def setup_storage_location():
    """Create Storage Location records A-1 and A-2, then register as an Inventory Dimension."""
    # 1. Seed master records
    for loc in ["A-1", "A-2"]:
        if not frappe.db.exists("Storage Location", loc):
            frappe.get_doc({
                "doctype": "Storage Location",
                "name": loc,
            }).insert(ignore_permissions=True)

    # 2. Register as an Inventory Dimension (creates custom fields on all stock doctypes)
    if not frappe.db.exists("Inventory Dimension", "Storage Location"):
        frappe.get_doc({
            "doctype": "Inventory Dimension",
            "reference_document": "Storage Location",
            "dimension_name": "Storage Location",
            "apply_to_all_doctypes": 1,
        }).insert(ignore_permissions=True)

    frappe.db.commit()


def seed_material_grades():
    """Every grade already stored on a drawing row becomes a master record, so
    converting Sales Order Drawing Raw Material.grade from free text to a Link does
    not orphan a single existing row.

    Swept from the data, never from a list. This site's three grades are not the live
    site's, and a hard-coded list leaves anything it has not heard of pointing at a
    master that does not exist -- which does not fail at migrate time. It fails the
    next time somebody saves that Sales Order, with a link error naming a grade they
    never typed.

    Values are seeded verbatim, spacing and all. Tidying near-duplicates into one
    grade is a judgement about the steel, not something a migration should make:
    renaming a master here would silently repoint every row quoting it.

    Only ever inserts, so a grade since renamed or disabled is left alone. Runs on
    every migrate rather than once, so a grade that arrives later -- restored from a
    backup, imported by a sheet staged before the conversion -- is picked up too."""
    if not frappe.db.table_exists("Sales Order Drawing Raw Material"):
        return
    if not frappe.db.has_column("Sales Order Drawing Raw Material", "grade"):
        return

    for (grade,) in frappe.db.sql(
        """SELECT DISTINCT grade FROM `tabSales Order Drawing Raw Material`
           WHERE grade IS NOT NULL AND grade != ''"""
    ):
        if not frappe.db.exists("Material Grade", grade):
            frappe.get_doc({
                "doctype": "Material Grade",
                "grade_name": grade,
            }).insert(ignore_permissions=True)
    frappe.db.commit()


def prepare_material_spec_link():
    """Convert the existing Item spec field without discarding stored values.

    Frappe blocks Data -> Link on a Custom Field save even though both use the
    same database column type. Update only this field's metadata before the
    normal create_custom_fields pass, and make every existing value a valid
    Material Spec first. New installations have no field to convert.
    """
    field_name = "Item-custom_material_spec"
    fieldtype = frappe.db.get_value("Custom Field", field_name, "fieldtype")
    if not fieldtype or fieldtype == "Link":
        return
    if fieldtype != "Data":
        frappe.throw("Cannot convert Item Material Spec from {0} to Link".format(fieldtype))

    values = frappe.db.sql(
        """SELECT DISTINCT custom_material_spec FROM `tabItem`
           WHERE custom_material_spec IS NOT NULL AND custom_material_spec != ''""",
        as_list=True,
    )
    for (spec,) in values:
        if not frappe.db.exists("Material Spec", spec):
            frappe.get_doc({"doctype": "Material Spec", "spec_name": spec}).insert(
                ignore_permissions=True
            )

    frappe.db.set_value(
        "Custom Field", field_name,
        {"fieldtype": "Link", "options": "Material Spec"},
        update_modified=False,
    )
    frappe.clear_cache(doctype="Item")


def create_item_client_script():
    if frappe.db.exists("Client Script", CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", CLIENT_SCRIPT_NAME, "script", CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": CLIENT_SCRIPT_NAME,
            "dt": "Item",
            "view": "Form",
            "enabled": 1,
            "script": CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_item_custom_fields():
    custom_fields = {
        "Item": [
            # Material Spec and Material Grade are the two answers to "what steel is
            # this?", and they are masters rather than free text because the free-text
            # version was never filled in: 0 of 85 items carried a spec. They are
            # editable HERE and read-only everywhere else -- every document down the
            # chain mirrors them through fetch_from, for reference only.
            {
                "fieldname": "custom_material_spec",
                "label": "Material Spec",
                "fieldtype": "Link",
                "options": "Material Spec",
                "insert_after": "item_name",
                "description": "Material specification for the item",
            },
            {
                "fieldname": "custom_material_grade",
                "label": "Material Grade",
                "fieldtype": "Link",
                "options": "Material Grade",
                "insert_after": "custom_material_spec",
                "description": "Steel grade for the item, from the Material Grade master",
            },
            {
                "fieldname": "custom_parent_item_group",
                "label": "Parent Item Group",
                "fieldtype": "Link",
                "options": "Item Group",
                # Moved down one so the anchor chain stays linear now that Material
                # Grade sits between them; two fields anchored on the same one leaves
                # their order to chance.
                "insert_after": "custom_material_grade",
                "reqd": 1,
                "default": "All Item Groups",
                "description": "Primary category determining calculation method",
            },
            {
                "fieldname": "custom_unit_weight",
                "label": "Unit Weight",
                "fieldtype": "Float",
                "insert_after": "stock_uom",
                "description": "Default UOM Weight - kg/meter for Structurals, density factor for Plates",
            },
            {
                "fieldname": "custom_secondary_uom",
                "label": "Secondary UOM",
                "fieldtype": "Link",
                "options": "UOM",
                "insert_after": "custom_unit_weight",
                "description": "NOS for Structurals/Plates, KG for Nuts and Bolts",
            },
            {
                "fieldname": "custom_item_calculation_type",
                "label": "Item Calculation Type",
                "fieldtype": "Select",
                "options": "\nNormal Weight Calculation\nFormula Weight Calculation",
                "insert_after": "custom_secondary_uom",
                "read_only": 1,
                "description": "Auto-set based on Parent Item Group",
            },
            {
                "fieldname": "custom_batch_prefix",
                "label": "Custom Batch Abbreviation",
                "fieldtype": "Data",
                "insert_after": "has_batch_no",
                "depends_on": "eval:doc.has_batch_no",
                "description": "Batch prefix for custom naming (e.g., ISMB150)",
            },
            {
                "fieldname": "custom_inspection_required",
                "label": "Inspection Required (Purchase Receipt)",
                "fieldtype": "Check",
                "insert_after": "custom_batch_prefix",
                "description": "If checked, receipts of this item require an Inspection Call "
                "before their batches can be reserved in Material Planning.",
            },
        ],
        "Item Group": [
            {
                "fieldname": "custom_mandatory_thickness",
                "label": "Mandatory Thickness",
                "fieldtype": "Check",
                "depends_on": "eval:doc.is_group==1",
            },
            {
                "fieldname": "custom_mandatory_length",
                "label": "Mandatory Length Value",
                "fieldtype": "Check",
                "depends_on": "eval:doc.is_group==1",
            },
            {
                "fieldname": "custom_mandatory_width",
                "label": "Mandatory Width Value",
                "fieldtype": "Check",
                "depends_on": "eval:doc.is_group==1",
            },
        ],
    }
    create_custom_fields(custom_fields, update=True)


def create_purchase_order_custom_fields():
    custom_fields = {
        "Purchase Order Item": [
            {
                "fieldname": "custom_material_spec",
                "label": "Material Spec",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_spec",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_material_grade",
                "label": "Material Grade",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_grade",
                "read_only": 1,
                "insert_after": "custom_material_spec",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_parent_item_group",
                "label": "Parent Item Group",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_parent_item_group",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_item_calculation_type",
                "label": "Item Calculation Type",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_item_calculation_type",
                "read_only": 1,
                "insert_after": "custom_parent_item_group",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_sec_qty",
                "label": "Sec Qty",
                "fieldtype": "Float",
                "insert_after": "uom",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_sec_uom",
                "label": "Sec UOM",
                "fieldtype": "Link",
                "options": "UOM",
                "fetch_from": "item_code.custom_secondary_uom",
                "read_only": 1,
                "insert_after": "custom_sec_qty",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_unit_weight",
                "label": "Unit Weight",
                "fieldtype": "Float",
                "fetch_from": "item_code.custom_unit_weight",
                "read_only": 1,
                "insert_after": "custom_sec_uom",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_thickness",
                "label": "Thickness",
                "fieldtype": "Float",
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_unit_weight",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_length",
                "label": "Length",
                "fieldtype": "Float",
                "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                "insert_after": "custom_thickness",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_width",
                "label": "Width",
                "fieldtype": "Float",
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_length",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_drawing",
                "label": "Drawing",
                "fieldtype": "Link",
                "options": "Drawing",
                "insert_after": "custom_width",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_duno_mark_no",
                "label": "DUNO/Mark No",
                "fieldtype": "Data",
                "insert_after": "custom_drawing",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_customer_drawing_number",
                "label": "Customer Drawing Number",
                "fieldtype": "Data",
                "insert_after": "custom_duno_mark_no",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_sales_order",
                "label": "Sales Order",
                "fieldtype": "Link",
                "options": "Sales Order",
                "insert_after": "custom_customer_drawing_number",
                "in_list_view": 0,
            },
        ],
    }
    create_custom_fields(custom_fields, update=True)


def hide_purchase_order_weight_fields():
    for fieldname in ["item_weight_details", "weight_per_unit", "total_weight", "weight_uom"]:
        frappe.make_property_setter(
            {
                "doctype": "Purchase Order Item",
                "fieldname": fieldname,
                "property": "hidden",
                "value": 1,
                "property_type": "Check",
            }
        )
    frappe.db.commit()


def create_purchase_order_client_script():
    if frappe.db.exists("Client Script", PO_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", PO_CLIENT_SCRIPT_NAME, "script", PO_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", PO_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": PO_CLIENT_SCRIPT_NAME,
            "dt": "Purchase Order",
            "view": "Form",
            "enabled": 1,
            "script": PO_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_purchase_receipt_custom_fields():
    custom_fields = {
        "Purchase Receipt Item": [
            {
                "fieldname": "custom_material_spec",
                "label": "Material Spec",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_spec",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_material_grade",
                "label": "Material Grade",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_grade",
                "read_only": 1,
                "insert_after": "custom_material_spec",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_parent_item_group",
                "label": "Parent Item Group",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_parent_item_group",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_item_calculation_type",
                "label": "Item Calculation Type",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_item_calculation_type",
                "read_only": 1,
                "insert_after": "custom_parent_item_group",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_sec_qty",
                "label": "Sec Qty",
                "fieldtype": "Float",
                "insert_after": "uom",
                "in_list_view": 1,
                "columns": 1,
            },
            {
                "fieldname": "custom_sec_uom",
                "label": "Sec UOM",
                "fieldtype": "Link",
                "options": "UOM",
                "fetch_from": "item_code.custom_secondary_uom",
                "read_only": 1,
                "insert_after": "custom_sec_qty",
                "in_list_view": 1,
                "columns": 1,
            },
            {
                "fieldname": "custom_unit_weight",
                "label": "Unit Weight",
                "fieldtype": "Float",
                "fetch_from": "item_code.custom_unit_weight",
                "read_only": 1,
                "insert_after": "custom_sec_uom",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_thickness",
                "label": "Thickness",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:doc.custom_parent_item_group==='Plates'",
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_unit_weight",
                "in_list_view": 1,
                "columns": 1,
            },
            {
                "fieldname": "custom_length",
                "label": "Length",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                "insert_after": "custom_thickness",
                "in_list_view": 1,
                "columns": 1,
            },
            {
                "fieldname": "custom_width",
                "label": "Width",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:doc.custom_parent_item_group==='Plates'",
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_length",
                "in_list_view": 1,
                "columns": 1,
            },
            {
                "fieldname": "custom_drawing",
                "label": "Drawing",
                "fieldtype": "Link",
                "options": "Drawing",
                "insert_after": "custom_width",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_duno_mark_no",
                "label": "DUNO/Mark No",
                "fieldtype": "Data",
                "insert_after": "custom_drawing",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_customer_drawing_number",
                "label": "Customer Drawing Number",
                "fieldtype": "Data",
                "insert_after": "custom_duno_mark_no",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_sales_order",
                "label": "Sales Order",
                "fieldtype": "Link",
                "options": "Sales Order",
                "insert_after": "custom_customer_drawing_number",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_inspection_accepted_qty",
                "label": "Inspection Accepted Qty",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "custom_sales_order",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_inspection_rejected_qty",
                "label": "Inspection Rejected Qty",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "custom_inspection_accepted_qty",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_inspection_remarks",
                "label": "Inspection Remarks",
                "fieldtype": "Small Text",
                "read_only": 1,
                "insert_after": "custom_inspection_rejected_qty",
            },
        ],
        "Purchase Receipt": [
            {
                "fieldname": "custom_inspection_tab",
                "label": "Inspection",
                "fieldtype": "Tab Break",
                "insert_after": "amended_from",
            },
            {
                "fieldname": "custom_create_inspection_btn",
                "label": "Create Inspection",
                "fieldtype": "Button",
                "insert_after": "custom_inspection_tab",
            },
            {
                "fieldname": "custom_update_inspection_call_date_btn",
                "label": "Update Inspection Call Date",
                "fieldtype": "Button",
                "depends_on": "eval:doc.custom_inspection_call_log && doc.custom_inspection_call_log.length",
                "insert_after": "custom_create_inspection_btn",
            },
            {
                "fieldname": "custom_inspection_status",
                "label": "Inspection Status",
                "fieldtype": "Select",
                "options": "Open\nWorking\nCompleted",
                "default": "Open",
                "read_only": 1,
                "no_copy": 1,
                "allow_on_submit": 1,
                "insert_after": "custom_update_inspection_call_date_btn",
            },
            {
                "fieldname": "custom_inspection_call_log_section",
                "label": "Inspection Call Log",
                "fieldtype": "Section Break",
                "insert_after": "custom_inspection_status",
            },
            {
                "fieldname": "custom_inspection_call_log",
                "label": "Inspection Call Log",
                "fieldtype": "Table",
                "options": "Inspection Call Log",
                "read_only": 1,
                "allow_on_submit": 1,
                "insert_after": "custom_inspection_call_log_section",
            },
        ],
    }
    create_custom_fields(custom_fields, update=True)


def layout_purchase_receipt_item_grid():
    """Spend the Purchase Receipt Item grid's column budget deliberately.

    Frappe's grid has a hard budget: it walks the fields in order adding up their
    `columns`, and the moment the running total passes 11 it STOPS and drops every
    remaining column (frappe/public/js/frappe/form/grid.js, setup_visible_columns).
    The total starts at 1, so the widths may add up to at most 10.

    This app put six custom columns into that grid, and the budget was being blown
    at Sec UOM — which meant Length, Width, Thickness, Unit Weight, Rate, Amount,
    Net Amount and Accepted Warehouse were ALL invisible, with no error and nothing
    on screen to say why. Accepted Warehouse was reported as "missing" and looked
    like a field that needed enabling; it was already enabled and had simply run off
    the end of the budget.

    The layout below is the client's, and totals exactly 10:

        item_code 2 + qty 1 + custom_sec_qty 1 + custom_sec_uom 1
        + custom_thickness 1 + custom_length 1 + custom_width 1 + warehouse 2

    Rejected Qty, Unit Weight, Rate, Amount and Net Amount come out of the grid to
    pay for it. They are only dropped from the ROW VIEW — every one stays on the
    doctype and stays editable by expanding the row, and Rate/Amount continue to
    drive valuation exactly as before.

    Anything added to this grid later has to come out of this budget. Adding one
    more in_list_view field without taking width back from another does not push a
    column off the right-hand edge — it silently blanks everything after it.
    """
    widths = {"item_code": 2, "qty": 1, "warehouse": 2}
    for fieldname, columns in widths.items():
        frappe.make_property_setter(
            {
                "doctype": "Purchase Receipt Item",
                "fieldname": fieldname,
                "property": "columns",
                "value": columns,
                "property_type": "Int",
            }
        )

    for fieldname in ("rejected_qty", "rate", "amount", "net_amount"):
        frappe.make_property_setter(
            {
                "doctype": "Purchase Receipt Item",
                "fieldname": fieldname,
                "property": "in_list_view",
                "value": 0,
                "property_type": "Check",
            }
        )
    frappe.db.commit()


def create_rate_schedule_sync_fields():
    """Mirror the Drawing's Rate Schedule onto BOM and Production Plan Item.

    The rate a job is charged at is decided once, per drawing, and then has to be
    readable everywhere that drawing is worked on. It lived only on the Drawing,
    so a BOM or a Production Plan gave no idea what the work was being priced at.

    Shape is copied from the Drawing's own section (drawing.json):
      - the Rate Schedule LINK is editable, and allow_on_submit so it can still be
        corrected after the document is submitted -- which is the normal case here,
        since Drawings and BOMs are submitted long before rates get revisited;
      - everything else is read_only with fetch_from, so the schedule's own details
        are shown but never typed. Editing a rate means editing the Rate Schedule
        master, not one of the documents quoting it.

    BOM gets the full section: one BOM is one drawing (custom_drawing), so there is
    room and a reason to show all of it. Production Plan Item gets only the link,
    Job Nature and Rate/KG -- it is a grid row, not a form.

    Keeping the two sides in step is rate_schedule_sync.py; these are just the
    fields it writes to.
    """
    rs_detail_fields = [
        ("custom_rs_job_nature", "Job Nature", "Data", "job_nature"),
        ("custom_rs_details", "Details", "Data", "details"),
        ("custom_rs_work_content", "Work Content", "Data", "work_content"),
        ("custom_rs_job_reference", "Job Reference", "Data", "job_reference"),
        ("custom_rs_rate_per_kg", "Rate/KG", "Currency", "rate_per_kg"),
    ]

    bom_fields = [
        {
            "fieldname": "custom_rate_schedule_section",
            "label": "Rate Schedule",
            "fieldtype": "Section Break",
            "insert_after": "custom_customer_drawing_number",
        },
        {
            "fieldname": "custom_rate_schedule",
            "label": "Rate Schedule",
            "fieldtype": "Link",
            "options": "Rate Schedule",
            "insert_after": "custom_rate_schedule_section",
            "allow_on_submit": 1,
            "description": "Changing this updates the Drawing and every other document that follows it.",
        },
        {
            "fieldname": "custom_rs_type",
            "label": "Type",
            "fieldtype": "Data",
            "fetch_from": "custom_rate_schedule.type",
            "read_only": 1,
            "insert_after": "custom_rate_schedule",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "custom_rate_schedule_col",
            "fieldtype": "Column Break",
            "insert_after": "custom_rs_type",
        },
    ]
    previous = "custom_rate_schedule_col"
    for fieldname, label, fieldtype, source in rs_detail_fields:
        bom_fields.append({
            "fieldname": fieldname,
            "label": label,
            "fieldtype": fieldtype,
            "fetch_from": "custom_rate_schedule.{0}".format(source),
            "read_only": 1,
            "insert_after": previous,
            "allow_on_submit": 1,
        })
        previous = fieldname

    # Production Plan Item is a grid row. Deliberately NOT in_list_view: that grid
    # is already well past Frappe's 11-column budget (see the note in
    # layout_purchase_receipt_item_grid), so an in_list_view field added here would
    # not appear at all -- it would land in the silently-dropped tail. The fields
    # are edited by expanding the row until that grid is re-budgeted.
    pp_item_fields = [
        {
            "fieldname": "custom_rate_schedule",
            "label": "Rate Schedule",
            "fieldtype": "Link",
            "options": "Rate Schedule",
            "insert_after": "custom_material_planning",
            "allow_on_submit": 1,
            "description": "Changing this updates the Drawing and its BOM.",
        },
        {
            "fieldname": "custom_rs_job_nature",
            "label": "Job Nature",
            "fieldtype": "Data",
            "fetch_from": "custom_rate_schedule.job_nature",
            "read_only": 1,
            "insert_after": "custom_rate_schedule",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "custom_rs_rate_per_kg",
            "label": "Rate/KG",
            "fieldtype": "Currency",
            "fetch_from": "custom_rate_schedule.rate_per_kg",
            "read_only": 1,
            "insert_after": "custom_rs_job_nature",
            "allow_on_submit": 1,
        },
    ]

    create_custom_fields(
        {"BOM": bom_fields, "Production Plan Item": pp_item_fields},
        ignore_validate=True,
    )
    frappe.db.commit()


def create_batch_custom_fields():
    custom_fields = {
        "Batch": [
            {
                "fieldname": "custom_material_spec",
                "label": "Material Spec",
                "fieldtype": "Data",
                "fetch_from": "item.custom_material_spec",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_material_grade",
                "label": "Material Grade",
                "fieldtype": "Data",
                "fetch_from": "item.custom_material_grade",
                "read_only": 1,
                "insert_after": "custom_material_spec",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_thickness",
                "label": "Thickness",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "description",
            },
            {
                "fieldname": "custom_length",
                "label": "Length",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "custom_thickness",
            },
            {
                "fieldname": "custom_width",
                "label": "Width",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "custom_length",
            },
            {
                "fieldname": "custom_sec_qty",
                "label": "Sec Qty",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "custom_width",
            },
            {
                "fieldname": "custom_sec_uom",
                "label": "Sec UOM",
                "fieldtype": "Link",
                "options": "UOM",
                "read_only": 1,
                "insert_after": "custom_sec_qty",
            },
            {
                "fieldname": "custom_existing_supplier_invoice_no",
                "label": "Existing Supplier Invoice No",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "custom_sec_uom",
            },
            {
                "fieldname": "custom_existing_invoice_wt",
                "label": "Existing Invoice Wt",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "custom_existing_supplier_invoice_no",
            },
            {
                "fieldname": "custom_existing_inward_date",
                "label": "Existing Inward Date",
                "fieldtype": "Date",
                "read_only": 1,
                "insert_after": "custom_existing_invoice_wt",
            },
            {
                "fieldname": "custom_batch_remarks",
                "label": "Batch Remarks",
                "fieldtype": "Small Text",
                "read_only": 1,
                "insert_after": "custom_existing_inward_date",
                "description": "Populated from the Inspection Call's remarks for this batch's source "
                                "Purchase Receipt item, once inspected (client change request Phase 6.3).",
            },
            {
                "fieldname": "custom_source_mip_excess_row",
                "label": "Source MIP Excess Row",
                "fieldtype": "Data",
                "hidden": 1,
                "read_only": 1,
                "insert_after": "custom_batch_remarks",
                "description": "Row name (SCO Excess Material Item) this batch was returned from, if it "
                                "came from the excess-material-return flow -- lets Excess Material Mapping "
                                "trace a reservation back to the Material Issue Plan it originated from.",
            },
            # Finished goods: one batch per drawing, FG-<Sales Order>-<DUNO>, created
            # by fg_stock.get_or_create_fg_batch (sep14 FG plan, D6/D20/D28). It
            # carries the full order reference so a Delivery Note can find the
            # batches of its Sales Order, and both weights per piece: the planned
            # one from the drawing, and the actual one (batch Kg / batch Nos) that
            # every FG movement uses. Raw-material batches never set
            # custom_sales_order, so the section stays hidden on them.
            {
                "fieldname": "custom_fg_details_section",
                "label": "FG Details",
                "fieldtype": "Section Break",
                "collapsible": 1,
                "depends_on": "eval:doc.custom_sales_order",
                "insert_after": "custom_source_mip_excess_row",
            },
            {
                "fieldname": "custom_sales_order",
                "label": "Sales Order",
                "fieldtype": "Link",
                "options": "Sales Order",
                "read_only": 1,
                "search_index": 1,
                "insert_after": "custom_fg_details_section",
            },
            {
                "fieldname": "custom_customer",
                "label": "Customer",
                "fieldtype": "Link",
                "options": "Customer",
                "read_only": 1,
                "insert_after": "custom_sales_order",
            },
            {
                "fieldname": "custom_drawing",
                "label": "Drawing",
                "fieldtype": "Link",
                "options": "Drawing",
                "read_only": 1,
                "insert_after": "custom_customer",
            },
            {
                "fieldname": "custom_job_work_order",
                "label": "Job Work Order",
                "fieldtype": "Link",
                "options": "Subcontracting Order",
                "read_only": 1,
                "insert_after": "custom_drawing",
                "description": "The Job Work Order whose Final Stock Entry first booked this batch.",
            },
            {
                "fieldname": "custom_fg_details_col",
                "fieldtype": "Column Break",
                "insert_after": "custom_job_work_order",
            },
            {
                "fieldname": "custom_duno_mark_no",
                "label": "DUNO/Mark No",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "custom_fg_details_col",
            },
            {
                "fieldname": "custom_customer_drawing_number",
                "label": "Cust Drawing Number",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "custom_duno_mark_no",
            },
            {
                "fieldname": "custom_cust_weight_per_nos",
                "label": "Planned Kg per Nos",
                "fieldtype": "Float",
                "precision": "3",
                "read_only": 1,
                "insert_after": "custom_customer_drawing_number",
                "description": "The drawing's Cust Weight (per Nos).",
            },
            {
                "fieldname": "custom_weight_per_piece",
                "label": "Actual Kg per Nos",
                "fieldtype": "Float",
                "precision": "3",
                "read_only": 1,
                "insert_after": "custom_cust_weight_per_nos",
                "description": "Batch Kg / batch Nos, recalculated on every finished-goods movement.",
            },
        ],
    }
    create_custom_fields(custom_fields, update=True)


def create_purchase_receipt_client_script():
    if frappe.db.exists("Client Script", PR_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", PR_CLIENT_SCRIPT_NAME, "script", PR_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", PR_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": PR_CLIENT_SCRIPT_NAME,
            "dt": "Purchase Receipt",
            "view": "Form",
            "enabled": 1,
            "script": PR_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_material_request_custom_fields():
    custom_fields = {
        "Material Request": [
            {
                "fieldname": "custom_material_planning",
                "label": "Material Planning",
                "fieldtype": "Link",
                "options": "Material Planning",
                "read_only": 0,
                "insert_after": "amended_from",
                "in_list_view": 1,
                "description": "Set automatically when created via a Material Planning's own Create "
                               "Material Request button; editable here too, so a Material Request "
                               "built manually (e.g. splitting one consolidated requirement across "
                               "several suppliers into separate requests) can still be traced back "
                               "to its source Material Planning for automatic Purchase Receipt allocation.",
            },
        ],
        "Material Request Item": [
            {
                "fieldname": "custom_material_spec",
                "label": "Material Spec",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_spec",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_material_grade",
                "label": "Material Grade",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_grade",
                "read_only": 1,
                "insert_after": "custom_material_spec",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_parent_item_group",
                "label": "Parent Item Group",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_parent_item_group",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_item_calculation_type",
                "label": "Item Calculation Type",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_item_calculation_type",
                "read_only": 1,
                "insert_after": "custom_parent_item_group",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_sec_qty",
                "label": "Sec Qty",
                "fieldtype": "Float",
                "insert_after": "uom",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_sec_uom",
                "label": "Sec UOM",
                "fieldtype": "Link",
                "options": "UOM",
                "fetch_from": "item_code.custom_secondary_uom",
                "read_only": 1,
                "insert_after": "custom_sec_qty",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_unit_weight",
                "label": "Unit Weight",
                "fieldtype": "Float",
                "fetch_from": "item_code.custom_unit_weight",
                "read_only": 1,
                "insert_after": "custom_sec_uom",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_thickness",
                "label": "Thickness",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:doc.custom_parent_item_group==='Plates'",
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_unit_weight",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_length",
                "label": "Length",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                "insert_after": "custom_thickness",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_width",
                "label": "Width",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:doc.custom_parent_item_group==='Plates'",
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_length",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_drawing",
                "label": "Drawing",
                "fieldtype": "Link",
                "options": "Drawing",
                "insert_after": "custom_width",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_duno_mark_no",
                "label": "DUNO/Mark No",
                "fieldtype": "Data",
                "insert_after": "custom_drawing",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_customer_drawing_number",
                "label": "Customer Drawing Number",
                "fieldtype": "Data",
                "insert_after": "custom_duno_mark_no",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_sales_order",
                "label": "Sales Order",
                "fieldtype": "Link",
                "options": "Sales Order",
                "insert_after": "custom_customer_drawing_number",
                "in_list_view": 0,
            },
        ],
    }
    create_custom_fields(custom_fields, update=True)


def create_material_request_client_script():
    if frappe.db.exists("Client Script", MR_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", MR_CLIENT_SCRIPT_NAME, "script", MR_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", MR_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": MR_CLIENT_SCRIPT_NAME,
            "dt": "Material Request",
            "view": "Form",
            "enabled": 1,
            "script": MR_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_rfq_custom_fields():
    custom_fields = {
        "Request for Quotation Item": [
            {
                "fieldname": "custom_material_spec",
                "label": "Material Spec",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_spec",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_material_grade",
                "label": "Material Grade",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_grade",
                "read_only": 1,
                "insert_after": "custom_material_spec",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_parent_item_group",
                "label": "Parent Item Group",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_item_calculation_type",
                "label": "Item Calculation Type",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "custom_parent_item_group",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_sec_qty",
                "label": "Sec Qty",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "qty",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_sec_uom",
                "label": "Sec UOM",
                "fieldtype": "Link",
                "options": "UOM",
                "read_only": 1,
                "insert_after": "custom_sec_qty",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_unit_weight",
                "label": "Unit Weight",
                "fieldtype": "Float",
                "read_only": 1,
                "insert_after": "custom_sec_uom",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_thickness",
                "label": "Thickness",
                "fieldtype": "Float",
                "read_only": 1,
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_unit_weight",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_length",
                "label": "Length",
                "fieldtype": "Float",
                "read_only": 1,
                "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                "insert_after": "custom_thickness",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_width",
                "label": "Width",
                "fieldtype": "Float",
                "read_only": 1,
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_length",
                "in_list_view": 1,
            },
        ],
    }
    create_custom_fields(custom_fields, update=True)


def create_rfq_client_script():
    if frappe.db.exists("Client Script", RFQ_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", RFQ_CLIENT_SCRIPT_NAME, "script", RFQ_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", RFQ_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": RFQ_CLIENT_SCRIPT_NAME,
            "dt": "Request for Quotation",
            "view": "Form",
            "enabled": 1,
            "script": RFQ_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_sq_custom_fields():
    custom_fields = {
        "Supplier Quotation Item": [
            {
                "fieldname": "custom_material_spec",
                "label": "Material Spec",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_spec",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_material_grade",
                "label": "Material Grade",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_material_grade",
                "read_only": 1,
                "insert_after": "custom_material_spec",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_parent_item_group",
                "label": "Parent Item Group",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_parent_item_group",
                "read_only": 1,
                "insert_after": "item_name",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_item_calculation_type",
                "label": "Item Calculation Type",
                "fieldtype": "Data",
                "fetch_from": "item_code.custom_item_calculation_type",
                "read_only": 1,
                "insert_after": "custom_parent_item_group",
                "in_list_view": 0,
            },
            {
                "fieldname": "custom_sec_qty",
                "label": "Sec Qty",
                "fieldtype": "Float",
                "insert_after": "uom",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_sec_uom",
                "label": "Sec UOM",
                "fieldtype": "Link",
                "options": "UOM",
                "fetch_from": "item_code.custom_secondary_uom",
                "read_only": 1,
                "insert_after": "custom_sec_qty",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_unit_weight",
                "label": "Unit Weight",
                "fieldtype": "Float",
                "fetch_from": "item_code.custom_unit_weight",
                "read_only": 1,
                "insert_after": "custom_sec_uom",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_thickness",
                "label": "Thickness",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:doc.custom_parent_item_group==='Plates'",
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_unit_weight",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_length",
                "label": "Length",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                "insert_after": "custom_thickness",
                "in_list_view": 1,
            },
            {
                "fieldname": "custom_width",
                "label": "Width",
                "fieldtype": "Float",
                "mandatory_depends_on": "eval:doc.custom_parent_item_group==='Plates'",
                "depends_on": "eval:doc.custom_parent_item_group === 'Plates'",
                "insert_after": "custom_length",
                "in_list_view": 1,
            },
        ],
    }
    create_custom_fields(custom_fields, update=True)


def create_sq_client_script():
    if frappe.db.exists("Client Script", SQ_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", SQ_CLIENT_SCRIPT_NAME, "script", SQ_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", SQ_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": SQ_CLIENT_SCRIPT_NAME,
            "dt": "Supplier Quotation",
            "view": "Form",
            "enabled": 1,
            "script": SQ_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_bom_custom_fields():
    # Frappe blocks Int→Data via its API; do it directly in DB if still Int.
    existing = frappe.db.get_value(
        "Custom Field",
        {"dt": "BOM Item", "fieldname": "custom_item_number"},
        "fieldtype",
    )
    if existing == "Int":
        frappe.db.sql(
            "UPDATE `tabCustom Field` SET fieldtype='Data' "
            "WHERE dt='BOM Item' AND fieldname='custom_item_number'"
        )
        frappe.db.commit()
        try:
            frappe.db.sql_ddl(
                "ALTER TABLE `tabBOM Item` MODIFY COLUMN custom_item_number VARCHAR(140)"
            )
        except Exception:
            pass  # column may already be VARCHAR on this site

    create_custom_fields(
        {
            "BOM": [
                {
                    "fieldname": "custom_drawing",
                    "fieldtype": "Link",
                    "label": "Drawing Reference",
                    "options": "Drawing",
                    "insert_after": "project",
                    "read_only": 1,
                    "no_copy": 1,
                    "print_hide": 1,
                },
                {
                    "fieldname": "custom_customer_drawing_number",
                    "fieldtype": "Data",
                    "label": "Cust Drawing Number",
                    "insert_after": "custom_drawing",
                    "read_only": 1,
                    "in_standard_filter": 1,
                    "no_copy": 1,
                },
                # A drawing BOM's quantity is the drawing's Cust Weight (Total) in Kg
                # (sep14 FG plan, D12); the piece count it stands for is carried here
                # as Qty (Nos), with both customer weights copied from the Drawing.
                {
                    "fieldname": "custom_sec_qty",
                    "fieldtype": "Float",
                    "label": "Qty (Nos)",
                    "insert_after": "quantity",
                    "read_only": 1,
                    "no_copy": 1,
                },
                {
                    "fieldname": "custom_sec_uom",
                    "fieldtype": "Link",
                    "label": "Sec UOM",
                    "options": "UOM",
                    "default": "Nos",
                    "insert_after": "custom_sec_qty",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_cust_weight_per_nos",
                    "fieldtype": "Float",
                    "label": "Cust Weight (per Nos)",
                    "insert_after": "custom_sec_uom",
                    "read_only": 1,
                    "no_copy": 1,
                    "precision": "3",
                },
                {
                    "fieldname": "custom_cust_weight_total",
                    "fieldtype": "Float",
                    "label": "Cust Weight (Total)",
                    "insert_after": "custom_cust_weight_per_nos",
                    "read_only": 1,
                    "no_copy": 1,
                    "precision": "3",
                },
            ],
            "BOM Item": [
                {
                    "fieldname": "custom_item_number",
                    "fieldtype": "Data",
                    "label": "Item Number",
                    "insert_after": "item_code",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_material_spec",
                    "fieldtype": "Data",
                    "label": "Material Spec",
                    # Mirrors the Item's own spec from here on, rather than relying on
                    # create_bom_from_drawing to carry it: a BOM built any other way
                    # used to arrive blank.
                    "fetch_from": "item_code.custom_material_spec",
                    "insert_after": "description",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_material_grade",
                    "label": "Material Grade",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_grade",
                    "read_only": 1,
                    "insert_after": "custom_material_spec",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_unit_weight",
                    "fieldtype": "Float",
                    "label": "Unit Weight",
                    "insert_after": "custom_material_spec",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_thickness",
                    "fieldtype": "Float",
                    "label": "Thickness",
                    "insert_after": "custom_unit_weight",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_length",
                    "fieldtype": "Float",
                    "label": "Length",
                    "insert_after": "custom_thickness",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_width",
                    "fieldtype": "Float",
                    "label": "Width",
                    "insert_after": "custom_length",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_sec_qty",
                    "fieldtype": "Float",
                    "label": "Sec Qty",
                    "insert_after": "uom",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_sec_uom",
                    "fieldtype": "Link",
                    "label": "Sec UOM",
                    "options": "UOM",
                    "insert_after": "custom_sec_qty",
                    "read_only": 1,
                },
            ],
        },
        update=True,
    )


def create_so_custom_fields():
    create_custom_fields(
        {
            "Sales Order": [
                {
                    "fieldname": "custom_tab_duno_mark_no",
                    "fieldtype": "Tab Break",
                    "label": "Drawing Import",
                    "insert_after": "pricing_rules",
                },
                {
                    "fieldname": "custom_bom_import_section",
                    "fieldtype": "Section Break",
                    "label": "BOM File",
                    "insert_after": "custom_tab_duno_mark_no",
                },
                {
                    "fieldname": "custom_bom_excel_file",
                    "fieldtype": "Attach",
                    "label": "BOM Excel File",
                    "insert_after": "custom_bom_import_section",
                    "description": "Upload the customer BOM Excel file.",
                },
                {
                    "fieldname": "custom_bom_action_btns",
                    "fieldtype": "HTML",
                    "label": "BOM Actions",
                    "insert_after": "custom_bom_excel_file",
                },
                # Summary of what was loaded, beside the file it came from. Read
                # straight off the staged rows in the browser -- no server call,
                # so it follows an edit in the grid immediately.
                {
                    "fieldname": "custom_bom_summary_col",
                    "fieldtype": "Column Break",
                    "insert_after": "custom_bom_action_btns",
                },
                {
                    "fieldname": "custom_bom_summary_html",
                    "fieldtype": "HTML",
                    "label": "Loaded Sheet Summary",
                    "insert_after": "custom_bom_summary_col",
                },
                {
                    "fieldname": "custom_drawing_list_section",
                    "fieldtype": "Section Break",
                    "label": "Drawing List",
                    "insert_after": "custom_bom_excel_file",
                },
                {
                    "fieldname": "custom_duno_items",
                    "fieldtype": "Table",
                    "label": "Drawing List",
                    "options": "Sales Order DUNO Item",
                    "insert_after": "custom_drawing_list_section",
                    "allow_on_submit": 1,
                },
                {
                    "fieldname": "custom_raw_materials_section",
                    "fieldtype": "Section Break",
                    "label": "Raw Materials",
                    "insert_after": "custom_duno_items",
                },
                {
                    "fieldname": "custom_rm_verify_btn",
                    "fieldtype": "HTML",
                    "label": "RM Verify Button",
                    "insert_after": "custom_raw_materials_section",
                },
                {
                    "fieldname": "custom_raw_materials_verified",
                    "fieldtype": "Check",
                    "label": "Raw Materials Verified",
                    "read_only": 1,
                    "hidden": 1,
                    "insert_after": "custom_rm_verify_btn",
                },
                {
                    "fieldname": "custom_so_raw_materials",
                    "fieldtype": "Table",
                    "label": "Raw Materials",
                    "options": "Sales Order Drawing Raw Material",
                    "insert_after": "custom_raw_materials_verified",
                    "allow_on_submit": 1,
                },
            ],
            # Finished goods are sold in Kg (the line's qty) but made, delivered and
            # invoiced by the piece, so every line also carries its piece count
            # (sep14 FG plan, D1). Delivered / Billed (Nos) are the running totals
            # the Delivery Note and Sales Invoice write back, so the next document
            # defaults to what is still pending in Nos, not in Kg.
            # Qty (Nos) sits right after Quantity and takes one grid column; Delivery
            # Date leaves the grid to pay for it (see create_fg_property_setters).
            "Sales Order Item": [
                {
                    "fieldname": "custom_sec_qty",
                    "fieldtype": "Float",
                    "label": "Qty (Nos)",
                    "insert_after": "qty",
                    "in_list_view": 1,
                    "columns": 1,
                    "description": "Number of finished pieces on this line. The Quantity is their total weight in Kg.",
                },
                {
                    "fieldname": "custom_sec_uom",
                    "fieldtype": "Link",
                    "label": "Sec UOM",
                    "options": "UOM",
                    "default": "Nos",
                    "read_only": 1,
                    "insert_after": "custom_sec_qty",
                },
                {
                    "fieldname": "custom_delivered_sec_qty",
                    "fieldtype": "Float",
                    "label": "Delivered (Nos)",
                    "read_only": 1,
                    "no_copy": 1,
                    "insert_after": "delivered_qty",
                    "description": "Pieces delivered against this line, net of returns.",
                },
                {
                    "fieldname": "custom_billed_sec_qty",
                    "fieldtype": "Float",
                    "label": "Billed (Nos)",
                    "read_only": 1,
                    "no_copy": 1,
                    "insert_after": "billed_amt",
                    "description": "Pieces invoiced against this line, net of credit notes.",
                },
            ],
        },
        update=True,
    )


def create_so_client_script():
    if frappe.db.exists("Client Script", SO_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", SO_CLIENT_SCRIPT_NAME, "script", SO_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", SO_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": SO_CLIENT_SCRIPT_NAME,
            "dt": "Sales Order",
            "view": "Form",
            "enabled": 1,
            "script": SO_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_bom_client_script():
    if frappe.db.exists("Client Script", BOM_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", BOM_CLIENT_SCRIPT_NAME, "script", BOM_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", BOM_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": BOM_CLIENT_SCRIPT_NAME,
            "dt": "BOM",
            "view": "Form",
            "enabled": 1,
            "script": BOM_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Production Plan — Subcontracting Plan tab + Process Planning table
# ─────────────────────────────────────────────────────────────────────────────

def create_production_plan_custom_fields():
    create_custom_fields(
        {
            # Material Request Plan Item's other custom fields predate setup.py and
            # live only in its customization export. These two are declared here so
            # they cannot drift: the export is re-synced on every migrate, but
            # setup.py is what runs last and settles any disagreement.
            "Material Request Plan Item": [
                {
                    "fieldname": "custom_material_spec",
                    "label": "Material Spec",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_spec",
                    "read_only": 1,
                    "insert_after": "item_name",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_material_grade",
                    "label": "Material Grade",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_grade",
                    "read_only": 1,
                    "insert_after": "custom_material_spec",
                    "in_list_view": 0,
                },
            ],
            "Production Plan Item": [
                {
                    "fieldname": "custom_material_spec",
                    "label": "Material Spec",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_spec",
                    "read_only": 1,
                    "insert_after": "item_code",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_material_grade",
                    "label": "Material Grade",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_grade",
                    "read_only": 1,
                    "insert_after": "custom_material_spec",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_customer_weight_kg",
                    "fieldtype": "Float",
                    "label": "Cust Weight (Total)",
                    "insert_after": "custom_customer_drawing_number",
                    "in_list_view": 1,
                    "columns": 1,
                },
                # The planner enters pieces; planned_qty (Kg) is derived from them
                # server-side by production_plan.apply_fg_nos (sep14 FG plan, D5/D26).
                # Qty (Nos) sits right after DUNO/Mark No so it lands inside the
                # grid's column budget -- this grid was already past it, and Item
                # Name leaves the row view to make room (it repeats the Item Code).
                # The Drawing field (custom/production_plan_item.json) now anchors on
                # custom_cust_weight_per_nos: two fields anchored on DUNO/Mark No
                # would be ordered by chance, and Material Planning follows Drawing.
                {
                    "fieldname": "custom_sec_qty",
                    "fieldtype": "Float",
                    "label": "Qty (Nos)",
                    "insert_after": "custom_duno_mark_no",
                    "in_list_view": 1,
                    "columns": 1,
                    "description": "Pieces of this drawing to make. Planned Qty (Kg) is calculated from it.",
                },
                {
                    "fieldname": "custom_sec_uom",
                    "fieldtype": "Link",
                    "label": "Sec UOM",
                    "options": "UOM",
                    "default": "Nos",
                    "read_only": 1,
                    "insert_after": "custom_sec_qty",
                },
                {
                    "fieldname": "custom_cust_weight_per_nos",
                    "fieldtype": "Float",
                    "label": "Cust Weight (per Nos)",
                    "read_only": 1,
                    "precision": "3",
                    "insert_after": "custom_sec_uom",
                },
                {
                    "fieldname": "custom_planned_rm_weight_kg",
                    "fieldtype": "Float",
                    "label": "Planned RM Weight (Kg)",
                    "insert_after": "custom_customer_weight_kg",
                    "read_only": 1,
                    "in_list_view": 1,
                    "columns": 1,
                },
            ],
            "Production Plan": [
                {
                    "fieldname": "custom_type",
                    "fieldtype": "Select",
                    "label": "Type",
                    "options": "\nInternal Job\nSupplier Job\nSupplier with Material",
                    "reqd": 1,
                    "insert_after": "naming_series",
                    "read_only_depends_on": "eval:!doc.__islocal",
                    "in_list_view": 1,
                    "in_standard_filter": 1,
                    "translatable": 0,
                },
                {
                    "fieldname": "custom_raw_material_warehouse",
                    "fieldtype": "Link",
                    "label": "Raw Material Warehouse",
                    "options": "Warehouse",
                    "insert_after": "po_items",
                    "read_only": 1,
                    "translatable": 0,
                },
                {
                    "fieldname": "custom_subcontracting_plan_tab",
                    "fieldtype": "Tab Break",
                    "label": "Work order plan",
                    "insert_after": "amended_from",
                },
                {
                    "fieldname": "custom_process_planning_section",
                    "fieldtype": "Section Break",
                    "label": "Process Planning",
                    "insert_after": "custom_subcontracting_plan_tab",
                },
                {
                    "fieldname": "custom_process_planning",
                    "fieldtype": "Table",
                    "label": "Process Planning",
                    "options": "Process Planning",
                    "insert_after": "custom_process_planning_section",
                },
                {
                    "fieldname": "custom_vendor_contractor_section",
                    "fieldtype": "Section Break",
                    "label": "Subcontractor",
                    "insert_after": "custom_process_planning",
                    "depends_on": "eval:doc.custom_process_planning && doc.custom_process_planning.some(r => r.work_type === 'Subcontractor')",
                },
                {
                    "fieldname": "custom_vendor_contractor",
                    "fieldtype": "Link",
                    "label": "Vendor/Contractor",
                    "options": "Supplier",
                    "insert_after": "custom_vendor_contractor_section",
                    "depends_on": "eval:doc.custom_process_planning && doc.custom_process_planning.some(r => r.work_type === 'Subcontractor')",
                    "mandatory_depends_on": "eval:doc.custom_process_planning && doc.custom_process_planning.some(r => r.work_type === 'Subcontractor')",
                },
                # Unconditional section (does NOT inherit the Subcontractor-only
                # depends_on above) -- Job work order + MIP are created for every
                # Production Plan Type, not only plans with a Subcontractor row.
                {
                    "fieldname": "custom_job_work_order_mip_section",
                    "fieldtype": "Section Break",
                    "label": "Job Work Order & Material Issue Plan",
                    "insert_after": "custom_vendor_contractor",
                    "depends_on": "eval:doc.docstatus === 1",
                },
                {
                    "fieldname": "custom_material_issue_plan",
                    "fieldtype": "Link",
                    "label": "Material Issue Plan",
                    "options": "Material Issue Plan",
                    "insert_after": "custom_job_work_order_mip_section",
                    "read_only": 1,
                },
                {
                    "fieldname": "custom_delete_job_work_order_mip_btn",
                    "fieldtype": "Button",
                    "label": "Delete Job work order and MIP",
                    "insert_after": "custom_material_issue_plan",
                },
            ],
        },
        update=True,
    )


PRODUCTION_PLAN_CLIENT_SCRIPT = """
frappe.ui.form.on("Production Plan", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		var ops = frm.doc.custom_process_planning || [];

		// Subcontracting Order is the single production-execution doctype for every
		// Production Plan Type (Internal Job / Supplier Job / Supplier with Material)
		// -- Work Order is no longer created from here at all (client change request
		// Phase 0.4/4.1). Process Planning rows can mix Subcontractor and Internal
		// Jobcard freely; Supplier Operation Entry executes each one regardless.
		//
		// Given as its own standalone toolbar button (not tucked inside "Create") per
		// client request, placed immediately before the "View" button. A single
		// click now creates BOTH the Job work order (Subcontracting Order) and its
		// Material Issue Plan together.
		if (ops.length) {
			var has_sub = ops.some(function(r) { return r.work_type === "Subcontractor"; });

			frm.remove_custom_button(__("Job work order & MIP"));
			var $job_btn = frm.add_custom_button(__("Job work order & MIP"), function() {
				if (has_sub && !frm.doc.custom_vendor_contractor) {
					frappe.msgprint(__("Please set Vendor/Contractor on this Production Plan before creating a Subcontracting Order."));
					return;
				}
				_pp_create_sco_and_mip(frm);
			});
			frm.change_custom_button_type(__("Job work order & MIP"), null, "primary");

			var $view_group = frm.page.get_inner_group_button(__("View"));
			if ($job_btn && $job_btn.length && $view_group && $view_group.length) {
				$job_btn.insertBefore($view_group);
			}
		}

		// ERPNext core still adds its own "Work Order / Subcontract PO" item under
		// Create when it finds pending items -- this app never creates a Work Order
		// from a Production Plan, so clicking it now just points the user at the
		// "Job work order" button above instead of proceeding. If nothing legitimate
		// (e.g. the native "Material Request" shortcut) is left in Create afterwards,
		// the whole dropdown is hidden too.
		frm.remove_custom_button(__("Work Order / Subcontract PO"), __("Create"));
		frm.add_custom_button(__("Work Order / Subcontract PO"), function() {
			frappe.msgprint(__('Use the "Job work order" button to create a Job work order for this Production Plan.'));
		}, __("Create"));

		var $create_group = frm.page.get_inner_group_button(__("Create"));
		if ($create_group && $create_group.length) {
			var other_items = $create_group.find(".dropdown-item").not(
				'[data-label="' + encodeURIComponent(__("Work Order / Subcontract PO")) + '"]'
			);
			if (other_items.length === 0) {
				$create_group.hide();
			} else {
				$create_group.show();
			}
		}
	},

	custom_delete_job_work_order_mip_btn(frm) {
		frappe.confirm(
			__("Delete the Job work order and Material Issue Plan created from this Production Plan? This cannot be undone."),
			function() {
				_pp_delete_sco_and_mip(frm);
			}
		);
	}
});

frappe.ui.form.on("Production Plan Item", {
	bom_no(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if (!row.bom_no || row.idx !== 1) return;
		frappe.call({
			method: "manufyxinvenzaerp.production_management.production_utils.get_routing_operations_for_bom",
			args: { bom_name: row.bom_no },
			callback: function(r) {
				if (!r.message || !r.message.length) return;
				frm.clear_table("custom_process_planning");
				r.message.forEach(function(op) {
					var child = frm.add_child("custom_process_planning");
					frappe.model.set_value(child.doctype, child.name, "operation_name", op.operation);
					frappe.model.set_value(child.doctype, child.name, "work_type", "Internal Jobcard");
				});
				frm.refresh_field("custom_process_planning");
			}
		});
	}
});

function _pp_create_sco_and_mip(frm) {
	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.subcontracting.create_sco_and_mip_from_production_plan",
		args: { pp_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Creating Job work order & Material Issue Plan…"),
		callback: function(r) {
			if (!r.message) return;
			var sco = r.message.sco, mip = r.message.mip, already = r.message.already_existed;
			var lines = [];
			if (sco) lines.push(__("Job work order: ") + '<a href="' + frappe.utils.get_form_link("Subcontracting Order", sco) + '">' + sco + "</a>");
			if (mip) lines.push(__("Material Issue Plan: ") + '<a href="' + frappe.utils.get_form_link("Material Issue Plan", mip) + '">' + mip + "</a>");
			frappe.msgprint({
				title: already ? __("Already Created") : __("Job work order & MIP Created"),
				message: lines.join("<br>") + (already ? "" : "<br><br>" + __("Set Supplier / Source / WIP Warehouses on the Job work order then submit.")),
				indicator: already ? "orange" : "green",
			});
			frm.reload_doc();
		}
	});
}

function _pp_delete_sco_and_mip(frm) {
	frappe.call({
		method: "manufyxinvenzaerp.subcontracting_management.subcontracting.delete_sco_and_mip_for_production_plan",
		args: { pp_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Deleting Job work order & Material Issue Plan…"),
		callback: function(r) {
			if (!r.message) return;
			frappe.show_alert({ message: __("Job work order and Material Issue Plan deleted."), indicator: "green" });
			frm.reload_doc();
		}
	});
}

/* Work Order is no longer created from a Production Plan -- Subcontracting Order
   handles every Type. The functions that made one were removed under the
   client's Phase 0.4/4.1 change request. */
""".strip()


def layout_production_plan_item_grid():
    """Spend the Production Plan Item grid's column budget deliberately.

    Same budget as everywhere else: grid.js walks the fields in order adding up their
    `columns`, and the first time the running total passes 11 it STOPS and drops that
    column and every one after it, silently. The total starts at 1, so the widths may
    add up to at most 10.

    This grid declared twelve columns needing twenty units, so it was being cut off
    mid-list -- Planned Qty, UOM, Finished Goods Warehouse and Planned Start Date never
    rendered at all, which is the behaviour SKILL.md records as still outstanding here.

    The layout below is the client's, and totals exactly 10:

        item_code 2 + custom_duno_mark_no 1 + custom_sec_qty 1
        + custom_material_planning 1 + custom_cust_weight_per_nos 1
        + custom_customer_weight_kg 1 + custom_rate_schedule 1
        + custom_rs_rate_per_kg 1 + sales_order 1

    BOM No, Customer Drawing No and Planned RM Weight come out of the ROW VIEW to pay
    for it, along with the four that were never visible anyway. Every one stays on the
    doctype and stays readable by expanding the row; nothing about planning changes.
    """
    widths = {
        "item_code": 2,
        "custom_duno_mark_no": 1,
        "custom_sec_qty": 1,
        "custom_material_planning": 1,
        "custom_cust_weight_per_nos": 1,
        "custom_customer_weight_kg": 1,
        "custom_rate_schedule": 1,
        "custom_rs_rate_per_kg": 1,
        "sales_order": 1,
    }
    for fieldname, columns in widths.items():
        frappe.make_property_setter({
            "doctype": "Production Plan Item",
            "fieldname": fieldname,
            "property": "in_list_view",
            "value": 1,
            "property_type": "Check",
        })
        frappe.make_property_setter({
            "doctype": "Production Plan Item",
            "fieldname": fieldname,
            "property": "columns",
            "value": columns,
            "property_type": "Int",
        })

    for fieldname in ("bom_no", "custom_customer_drawing_number",
                      "custom_planned_rm_weight_kg", "planned_qty", "stock_uom",
                      "warehouse", "planned_start_date"):
        frappe.make_property_setter({
            "doctype": "Production Plan Item",
            "fieldname": fieldname,
            "property": "in_list_view",
            "value": 0,
            "property_type": "Check",
        })


def create_production_plan_client_script():
    if frappe.db.exists("Client Script", PRODUCTION_PLAN_CLIENT_SCRIPT_NAME):
        frappe.db.set_value(
            "Client Script", PRODUCTION_PLAN_CLIENT_SCRIPT_NAME, "script", PRODUCTION_PLAN_CLIENT_SCRIPT
        )
        frappe.db.set_value("Client Script", PRODUCTION_PLAN_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": PRODUCTION_PLAN_CLIENT_SCRIPT_NAME,
            "dt": "Production Plan",
            "view": "Form",
            "enabled": 1,
            "script": PRODUCTION_PLAN_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


STOCK_ENTRY_CLIENT_SCRIPT = """
// M-bM-^TM-^@M-bM-^TM-^@ Consumable Entry M-bM-^TM-^@M-bM-^TM-^@M-bM-^TM-^@M-bM-^TM-^@
//
// Issuing consumables against a job -- welding rods, paint, gas -- rather than moving
// the job's own steel. The three fields are a chain: the Sales Order narrows which
// Production Plans can be picked, the plan names the Job Work Order, and that is what
// every weight rollup downstream already keys on.
//
// Each step clears what sits below it. Changing the order after picking a plan would
// otherwise leave a plan belonging to a different order, and a Job Work Order fetched
// from it -- a mismatch nobody would see, on a document that decides whose cost the
// consumables land on.

frappe.ui.form.on("Stock Entry", {
  custom_consumable_entry(frm) {
    if (frm.doc.custom_consumable_entry) {
      _se_mark_rows_consumable(frm);
    } else {
      // Only the questions are cleared, never the rows. A row may have been ticked
      // deliberately before any of this was switched on, and unticking somebody's
      // rows because a header field changed is not a decision this should make.
      frm.set_value("custom_consumable_sales_order", null);
      frm.set_value("custom_consumable_production_plan", null);
    }
  },

  custom_consumable_sales_order(frm) {
    frm.set_value("custom_consumable_production_plan", null);
  },

  custom_consumable_production_plan(frm) {
    if (!frm.doc.custom_consumable_production_plan) return;
    frappe.call({
      method: "manufyxinvenzaerp.production_management.stock_entry.get_job_work_order_for_production_plan",
      args: { production_plan: frm.doc.custom_consumable_production_plan },
      callback(r) {
        var found = r.message || {};
        if (!found.job_work_order) {
          frappe.msgprint({
            title: __("No Job Work Order"),
            message: __("No Job Work Order has been raised from {0} yet.",
                        [frm.doc.custom_consumable_production_plan]),
            indicator: "orange",
          });
          return;
        }
        // Assigned, not set_value'd. ERPNext's own subcontracting_order handler
        // fetches the order's raw materials for transfer, and a PP-flow order has no
        // supplied_items -- so setting the field the normal way answered with
        // "No item available for transfer." every time a plan was picked. Writing to
        // frm.doc and refreshing puts the value on the form without firing that.
        //
        // Both fields are written: custom_sco_ref is hidden but is still what 33
        // places in the app read, so leaving it behind would quietly break the weight
        // rollups this entry feeds.
        frm.doc.subcontracting_order = found.job_work_order;
        frm.doc.custom_sco_ref = found.job_work_order;
        frm.refresh_field("subcontracting_order");
        frm.refresh_field("custom_sco_ref");
        frm.dirty();
        if (found.count > 1) {
          frappe.msgprint({
            title: __("More Than One Job Work Order"),
            message: __("{0} has {1} Job Work Orders against it. The earliest, {2}, has been filled in — change it if that is not the one.",
                        [frm.doc.custom_consumable_production_plan, found.count, found.job_work_order]),
            indicator: "orange",
          });
        }
      },
    });
  },

  refresh(frm) {
    // The plan list cannot be a link filter: a plan's Sales Order lives on its child
    // rows, not on the plan, so the options are fetched and matched by name.
    frm.set_query("custom_consumable_production_plan", function() {
      return { query: "manufyxinvenzaerp.production_management.stock_entry.production_plan_query",
               filters: { sales_order: frm.doc.custom_consumable_sales_order || "" } };
    });
    _se_apply_consumption_type(frm);
  },

  stock_entry_type(frm) {
    _se_apply_consumption_type(frm);
  },
});

// "Material Consumption for Manufacture" IS a consumable entry -- that is the whole
// purpose of the type -- so the tick is set and locked rather than left as a question
// with only one right answer. Work Order goes with it: this flow reaches its job
// through Sales Order and Production Plan, and an empty Work Order field beside them
// only invites the wrong one to be filled in.
function _se_apply_consumption_type(frm) {
  var is_consumption = frm.doc.stock_entry_type === "Material Consumption for Manufacture";

  frm.set_df_property("work_order", "hidden", is_consumption ? 1 : 0);
  frm.set_df_property("custom_consumable_entry", "read_only", is_consumption ? 1 : 0);

  if (is_consumption && !frm.doc.custom_consumable_entry) {
    frm.set_value("custom_consumable_entry", 1);
  }
}

frappe.ui.form.on("Stock Entry Detail", {
  items_add(frm, cdt, cdn) {
    // A row added while the box is ticked arrives ticked.
    if (frm.doc.custom_consumable_entry) {
      frappe.model.set_value(cdt, cdn, "custom_is_consumable", 1);
    }
  },
});

function _se_mark_rows_consumable(frm) {
  var changed = 0;
  (frm.doc.items || []).forEach(function(row) {
    if (!row.custom_is_consumable) {
      frappe.model.set_value(row.doctype, row.name, "custom_is_consumable", 1);
      changed++;
    }
  });
  if (changed) {
    frm.refresh_field("items");
    frappe.show_alert({
      message: __("Marked {0} row(s) as consumable.", [changed]),
      indicator: "blue",
    }, 5);
  }
}

// Debounce helper
var _se_timers = {};
function se_debounce(key, fn, delay) {
\tclearTimeout(_se_timers[key]);
\t_se_timers[key] = setTimeout(fn, delay || 400);
}

frappe.ui.form.on("Stock Entry Detail", {
\titem_code(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (!row.item_code) return;

\t\t// Dismiss the "Add Batch Nos" dialog that ERPNext auto-opens for batch items —
\t\t// batches are auto-created on submit; the user must not fill them manually here.
\t\tif (frm.doc.stock_entry_type === "Material Receipt") {
\t\t\tvar _check = setInterval(function() {
\t\t\t\tif (cur_dialog && cur_dialog.get_title && cur_dialog.get_title() === __("Add Batch Nos")) {
\t\t\t\t\tcur_dialog.hide();
\t\t\t\t\tclearInterval(_check);
\t\t\t\t}
\t\t\t}, 50);
\t\t\tsetTimeout(function() { clearInterval(_check); }, 5000);
\t\t}

\t\tfrappe.db.get_value(
\t\t\t"Item", row.item_code,
\t\t\t["custom_parent_item_group", "custom_unit_weight", "custom_secondary_uom"],
\t\t\tfunction(values) {
\t\t\t\tif (!values) return;
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_parent_item_group", values.custom_parent_item_group || "");
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_unit_weight", values.custom_unit_weight || 0);
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_sec_uom", values.custom_secondary_uom || "");
\t\t\t}
\t\t);
\t},
\tbatch_no(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (!row.batch_no) return;
\t\tvar should_fetch = (
\t\t\tfrm.doc.stock_entry_type === "Material Issue" ||
\t\t\t(frm.doc.stock_entry_type === "Repack" && !row.is_finished_item)
\t\t);
\t\tif (!should_fetch) return;
\t\tfrappe.db.get_value(
\t\t\t"Batch", row.batch_no,
\t\t\t["custom_sec_qty", "custom_sec_uom", "custom_thickness", "custom_length", "custom_width"],
\t\t\tfunction(values) {
\t\t\t\tif (!values) return;
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_sec_qty", values.custom_sec_qty || 0);
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_sec_uom", values.custom_sec_uom || "");
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_thickness", values.custom_thickness || 0);
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_length", values.custom_length || 0);
\t\t\t\tfrappe.model.set_value(cdt, cdn, "custom_width", values.custom_width || 0);
\t\t\t\tse_debounce(cdn + "_calc", function() { se_calculate_qty(frm, cdt, cdn); });
\t\t\t}
\t\t);
\t},
\tcustom_sec_qty(frm, cdt, cdn) {
\t\tse_debounce(cdn + "_seq", function() { se_calculate_qty(frm, cdt, cdn); });
\t},
\tcustom_thickness(frm, cdt, cdn) {
\t\tse_debounce(cdn + "_thk", function() { se_calculate_qty(frm, cdt, cdn); });
\t},
\tcustom_length(frm, cdt, cdn) {
\t\tse_debounce(cdn + "_len", function() { se_calculate_qty(frm, cdt, cdn); });
\t},
\tcustom_width(frm, cdt, cdn) {
\t\tse_debounce(cdn + "_wid", function() { se_calculate_qty(frm, cdt, cdn); });
\t},
\tuom(frm, cdt, cdn) {
\t\tvar row = locals[cdt][cdn];
\t\tif (["Structurals", "Plates"].includes(row.custom_parent_item_group)) {
\t\t\tfrappe.show_alert({
\t\t\t\tmessage: __("Quantity is a calculated value. Recalculating…"),
\t\t\t\tindicator: "orange"
\t\t\t}, 5);
\t\t\tse_debounce(cdn + "_uom", function() { se_calculate_qty(frm, cdt, cdn); });
\t\t}
\t}
});

function se_calculate_qty(frm, cdt, cdn) {
\tvar row = locals[cdt][cdn];
\tvar group = row.custom_parent_item_group;
\tvar qty = null;
\tif (group === "Structurals") {
\t\tif (row.custom_length && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tqty = (row.custom_length / 1000) * row.custom_unit_weight * row.custom_sec_qty;
\t\t} else {
\t\t\tse_warn_missing_fields(row, group);
\t\t}
\t} else if (group === "Plates") {
\t\tif (row.custom_length && row.custom_width && row.custom_thickness && row.custom_unit_weight && row.custom_sec_qty) {
\t\t\tqty = (row.custom_length / 1000) * (row.custom_width / 1000) * row.custom_thickness * row.custom_unit_weight * row.custom_sec_qty;
\t\t} else {
\t\t\tse_warn_missing_fields(row, group);
\t\t}
\t}
\tif (qty !== null) {
\t\tfrappe.model.set_value(cdt, cdn, "qty", flt(qty, 3));
\t}
}

function se_warn_missing_fields(row, group) {
\tvar missing = [];
\tif (group === "Structurals") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t} else if (group === "Plates") {
\t\tif (!row.custom_length) missing.push("Length");
\t\tif (!row.custom_width) missing.push("Width");
\t\tif (!row.custom_thickness) missing.push("Thickness");
\t\tif (!row.custom_unit_weight) missing.push("Unit Weight");
\t\tif (!row.custom_sec_qty) missing.push("Sec Qty");
\t}
\tif (missing.length) {
\t\tfrappe.show_alert({
\t\t\tmessage: "Row " + row.idx + ": Missing for " + group + " formula: " + missing.join(", "),
\t\t\tindicator: "orange"
\t\t});
\t}
}
""".strip()


def create_stock_entry_custom_fields():
    create_custom_fields(
        {
            "Stock Entry Detail": [
                {
                    "fieldname": "custom_material_spec",
                    "label": "Material Spec",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_spec",
                    "read_only": 1,
                    "insert_after": "item_name",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_material_grade",
                    "label": "Material Grade",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_grade",
                    "read_only": 1,
                    "insert_after": "custom_material_spec",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_parent_item_group",
                    "fieldtype": "Data",
                    "label": "Parent Item Group",
                    "fetch_from": "item_code.custom_parent_item_group",
                    "read_only": 1,
                    "insert_after": "item_name",
                },
                {
                    "fieldname": "custom_unit_weight",
                    "fieldtype": "Float",
                    "label": "Unit Weight",
                    "fetch_from": "item_code.custom_unit_weight",
                    "read_only": 1,
                    "insert_after": "custom_parent_item_group",
                },
                {
                    "fieldname": "custom_sec_qty",
                    "fieldtype": "Float",
                    "label": "Sec Qty (Nos)",
                    "in_list_view": 1,
                    "insert_after": "custom_unit_weight",
                },
                {
                    "fieldname": "custom_sec_uom",
                    "fieldtype": "Link",
                    "options": "UOM",
                    "label": "Sec UOM",
                    "fetch_from": "item_code.custom_secondary_uom",
                    "read_only": 1,
                    "insert_after": "custom_sec_qty",
                },
                {
                    # On a finished-goods row of a Final Stock Entry: the raw material this
                    # entry consumed for that drawing, less the Kg booked as finished goods.
                    # Positive is weight that went in and did not come out -- burn, kerf,
                    # grinding. Negative means more was booked than was consumed, which is
                    # not a loss but a sign the Sales Order weight is understated.
                    #
                    # It is a figure, not a movement. The Manufacture entry has already
                    # consumed the steel; issuing it a second time would take it twice.
                    "fieldname": "custom_loss_kg",
                    "fieldtype": "Float",
                    "label": "Loss (Kg)",
                    "precision": "3",
                    "read_only": 1,
                    "in_list_view": 0,
                    "insert_after": "custom_sec_uom",
                },
                {
                    "fieldname": "custom_thickness",
                    "fieldtype": "Float",
                    "label": "Thickness (mm)",
                    "depends_on": "eval:doc.custom_parent_item_group=='Plates'",
                    "insert_after": "custom_sec_uom",
                },
                {
                    "fieldname": "custom_length",
                    "fieldtype": "Float",
                    "label": "Length (mm)",
                    "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                    "insert_after": "custom_thickness",
                },
                {
                    "fieldname": "custom_width",
                    "fieldtype": "Float",
                    "label": "Width (mm)",
                    "depends_on": "eval:doc.custom_parent_item_group=='Plates'",
                    "insert_after": "custom_length",
                },
                {
                    "fieldname": "custom_supplier",
                    "fieldtype": "Link",
                    "options": "Supplier",
                    "label": "Supplier",
                    "insert_after": "custom_width",
                },
                {
                    "fieldname": "custom_existing_supplier_invoice_no",
                    "fieldtype": "Data",
                    "label": "Existing Supplier Invoice No",
                    "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                    "insert_after": "custom_supplier",
                },
                {
                    "fieldname": "custom_existing_invoice_wt",
                    "fieldtype": "Float",
                    "label": "Existing Invoice Wt",
                    "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                    "insert_after": "custom_existing_supplier_invoice_no",
                },
                {
                    "fieldname": "custom_existing_inward_date",
                    "fieldtype": "Date",
                    "label": "Existing Inward Date",
                    "depends_on": "eval:['Structurals','Plates'].includes(doc.custom_parent_item_group)",
                    "insert_after": "custom_existing_invoice_wt",
                },
                {
                    "fieldname": "custom_is_consumable",
                    "fieldtype": "Check",
                    "label": "Consumable",
                    "in_list_view": 1,
                    "insert_after": "custom_existing_inward_date",
                    "description": "Mark this row as a consumable (welding rods, paint, etc.). "
                                   "Stock is deducted from the source warehouse on submission.",
                },
                {
                    "fieldname": "custom_drawing",
                    "label": "Drawing",
                    "fieldtype": "Link",
                    "options": "Drawing",
                    "insert_after": "custom_is_consumable",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_duno_mark_no",
                    "label": "DUNO/Mark No",
                    "fieldtype": "Data",
                    "insert_after": "custom_drawing",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_customer_drawing_number",
                    "label": "Customer Drawing Number",
                    "fieldtype": "Data",
                    "insert_after": "custom_duno_mark_no",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_sales_order",
                    "label": "Sales Order",
                    "fieldtype": "Link",
                    "options": "Sales Order",
                    "insert_after": "custom_customer_drawing_number",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_batch_remarks",
                    "label": "Batch Remarks",
                    "fieldtype": "Small Text",
                    "read_only": 1,
                    "insert_after": "custom_sales_order",
                    "description": "Synced from the batch's own Batch Remarks on every save "
                                   "(client change request Phase 6.3).",
                },
                {
                    "fieldname": "custom_source_mip_excess_row",
                    "label": "Source MIP Excess Row",
                    "fieldtype": "Data",
                    "hidden": 1,
                    "read_only": 1,
                    "insert_after": "custom_batch_remarks",
                    "description": "Row name of the SCO Excess Material Item this off-cut was returned "
                                   "from (set by create_mip_excess_return_entry) -- ERPNext copies "
                                   "same-named custom fields from a Stock Entry item onto the batch it "
                                   "auto-creates, which is how this reaches the Batch record itself for "
                                   "Excess Material Mapping to trace back to.",
                },
            ],
            "Stock Entry": [
                {
                    "fieldname": "custom_sco_ref",
                    "fieldtype": "Link",
                    "label": "Subcontracting Order (PP Flow)",
                    "options": "Subcontracting Order",
                    "read_only": 1,
                    "insert_after": "subcontracting_order",
                    "description": "PP-flow SCO link — used instead of subcontracting_order "
                                   "to avoid ERPNext supplied_items validation on send-to-subcontractor SEs.",
                },
                {
                    "fieldname": "custom_wo_ref",
                    "fieldtype": "Link",
                    "label": "Work Order (PP Flow)",
                    "options": "Work Order",
                    "read_only": 1,
                    "insert_after": "custom_sco_ref",
                    "description": "PP-flow WO link — used to track WO-linked SEs without "
                                   "triggering ERPNext's own work_order SE validation logic.",
                },
                {
                    "fieldname": "custom_mip_ref",
                    "fieldtype": "Link",
                    "label": "Material Issue Plan",
                    "options": "Material Issue Plan",
                    "read_only": 1,
                    "insert_after": "custom_wo_ref",
                    "description": "Set on transfer/CNC/excess-return entries created from a "
                                   "Material Issue Plan, alongside custom_sco_ref/custom_wo_ref "
                                   "so existing weight rollups keep working unchanged.",
                },
                {
                    "fieldname": "custom_mrs_number",
                    "fieldtype": "Data",
                    "label": "MRS Number",
                    "insert_after": "custom_mip_ref",
                    "depends_on": "eval:doc.subcontracting_order",
                },
                # Consumable Entry -- an entry issuing consumables (welding rods,
                # paint, gas) against a job rather than moving the job's own steel.
                # The three fields are a chain: the order narrows the plans, the plan
                # names the job work order, and the job work order is what every
                # weight rollup downstream already keys on.
                {
                    "fieldname": "custom_consumable_entry",
                    "fieldtype": "Check",
                    "label": "Consumable Entry",
                    "insert_after": "inspection_required",
                    "description": "Issuing consumables against a job. Ticking it marks every "
                                   "item row as a consumable and asks which job they are for.",
                },
                {
                    "fieldname": "custom_consumable_sales_order",
                    "fieldtype": "Link",
                    "label": "Sales Order",
                    "options": "Sales Order",
                    "insert_after": "custom_consumable_entry",
                    "depends_on": "eval:doc.custom_consumable_entry",
                    "mandatory_depends_on": "eval:doc.custom_consumable_entry",
                    "description": "Which order the consumables are being issued against.",
                },
                {
                    "fieldname": "custom_consumable_production_plan",
                    "fieldtype": "Link",
                    "label": "Production Plan",
                    "options": "Production Plan",
                    "insert_after": "custom_consumable_sales_order",
                    "depends_on": "eval:doc.custom_consumable_entry && doc.custom_consumable_sales_order",
                    "mandatory_depends_on": "eval:doc.custom_consumable_entry && doc.custom_consumable_sales_order",
                    "description": "Only plans made against the order above. Choosing one fills "
                                   "in its Job Work Order.",
                },
            ],
        },
        update=True,
    )


def hide_duplicate_sco_field():
    """Only one Job Work Order field on a Stock Entry, not two.

    `subcontracting_order` and `custom_sco_ref` hold the same value and sit next to
    each other, which is confusing on a form and worse in a report.

    The custom one goes. It exists for a reason that has since gone away: ERPNext's
    validate_subcontract_order used to throw when supplied_items was empty, so the
    flow avoided the core field. CustomStockEntry.validate_subcontract_order now
    returns early for a PP-flow order, which solves that properly. The core field
    also already reads as "Job work order" through the Translation, and is what
    ERPNext's own code keys on.

    Hidden, not deleted. Every Stock Entry this app makes writes both, and 33 places
    still read custom_sco_ref -- rewriting those and migrating submitted documents is
    its own piece of work, and would buy nothing a hidden field does not."""
    frappe.make_property_setter(
        {
            "doctype": "Stock Entry",
            "fieldname": "custom_sco_ref",
            "property": "hidden",
            "value": 1,
            "property_type": "Check",
        }
    )


def create_stock_entry_client_script():
    if frappe.db.exists("Client Script", STOCK_ENTRY_CLIENT_SCRIPT_NAME):
        frappe.db.set_value(
            "Client Script", STOCK_ENTRY_CLIENT_SCRIPT_NAME, "script", STOCK_ENTRY_CLIENT_SCRIPT
        )
        frappe.db.set_value("Client Script", STOCK_ENTRY_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": STOCK_ENTRY_CLIENT_SCRIPT_NAME,
            "dt": "Stock Entry",
            "view": "Form",
            "enabled": 1,
            "script": STOCK_ENTRY_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Subcontracting Management — Subcontracting Order custom fields + client scripts
# ─────────────────────────────────────────────────────────────────────────────

# Display-only doctype relabels, applied through the standard Translation doctype.
# Each renders everywhere Frappe wraps a string in __() -- breadcrumbs, form and list
# titles, the sidebar, print formats, global search -- while the doctype itself, its
# DocType name, every Link pointing at it and all backend code stay untouched.
#
# This is deliberately NOT a rename. Renaming Supplier Operation Entry would mean the
# SQL table, ~125 code references across 26 files, its child tables and the naming
# series on every existing record; a translation buys the same user-visible result for
# none of that risk (client change request T9).
DOCTYPE_LABEL_TRANSLATIONS = {
    "Subcontracting Order": "Job work order",
    "Supplier Operation Entry": "Operation Entry",
}


def create_doctype_label_translations():
    """Create/refresh the display-only relabels in DOCTYPE_LABEL_TRANSLATIONS.

    Idempotent: an existing row for the same source text is updated rather than
    duplicated, so this is safe to re-run on every migrate."""
    for source_text, translated_text in DOCTYPE_LABEL_TRANSLATIONS.items():
        existing = frappe.db.get_value(
            "Translation", {"source_text": source_text, "language": "en"}, "name"
        )
        if existing:
            frappe.db.set_value("Translation", existing, "translated_text", translated_text)
        else:
            frappe.get_doc(
                {
                    "doctype": "Translation",
                    "language": "en",
                    "source_text": source_text,
                    "translated_text": translated_text,
                }
            ).insert(ignore_permissions=True)
    frappe.db.commit()


def remove_sco_purchase_order_mandatory():
    """Remove mandatory from SCO fields that are not required in the PP → SCO flow."""
    for args in [
        {"doctype": "Subcontracting Order", "fieldname": "purchase_order", "property": "reqd", "value": 0, "property_type": "Check"},
        {"doctype": "Subcontracting Order", "fieldname": "service_items", "property": "reqd", "value": 0, "property_type": "Check"},
        {"doctype": "Subcontracting Order Item", "fieldname": "warehouse", "property": "reqd", "value": 0, "property_type": "Check"},
    ]:
        frappe.make_property_setter(args)
    frappe.db.commit()


def add_sco_working_status():
    """Add "Working" to the Job Work Order's Status options.

    A Production-Plan-flow Subcontracting Order has no Subcontracting Receipt and no
    Raw Materials Supplied table, so every status ERPNext can derive from those --
    Partially Received, Material Transferred -- is unreachable, and the order sat on
    "Open" from submit to finish. CustomSubcontractingOrder.update_status derives
    Open / Working / Completed from its operations instead, and "Working" has to be a
    valid option or the next ordinary save of the order fails Frappe's Select
    validation.

    The core options are kept as they are rather than trimmed: standard SCOs on this
    site still use them, and removing an option a saved document already holds would
    make that document unsaveable."""
    options = frappe.db.get_value(
        "DocField", {"parent": "Subcontracting Order", "fieldname": "status"}, "options"
    ) or ""
    existing = frappe.db.get_value(
        "Property Setter",
        {"doc_type": "Subcontracting Order", "field_name": "status", "property": "options"},
        "value",
    )
    current = existing or options
    if "Working" in (current or "").split("\n"):
        return

    frappe.make_property_setter(
        {
            "doctype": "Subcontracting Order",
            "fieldname": "status",
            "property": "options",
            "value": (current.rstrip("\n") + "\nWorking") if current else "Working",
            "property_type": "Text",
        }
    )
    frappe.db.commit()


def hide_sco_job_worker_warehouse():
    """Hide Job Worker Warehouse — CustomSubcontractingOrder._auto_set_supplier_warehouse
    (overrides.py) resolves it automatically from the Job Worker's dedicated Warehouse
    ('<Job Worker> - <Company Abbr>') on PP-flow SCOs, so the user no longer picks it.

    reqd is cleared before hidden is set: the core field ships with reqd=1 and no
    default, so setting hidden=1 first leaves it hidden-and-mandatory-without-default,
    which Frappe's DocType validation rejects outright (breaks fresh installs)."""
    frappe.make_property_setter(
        {
            "doctype": "Subcontracting Order",
            "fieldname": "supplier_warehouse",
            "property": "reqd",
            "value": 0,
            "property_type": "Check",
        }
    )
    frappe.make_property_setter(
        {
            "doctype": "Subcontracting Order",
            "fieldname": "supplier_warehouse",
            "property": "hidden",
            "value": 1,
            "property_type": "Check",
        }
    )
    frappe.db.commit()


def hide_sco_unused_tabs():
    """Hide the Job Work Order's 'Additional Costs' and 'Other Info' tabs.

    Neither is used on this site's flow. Additional Costs prices a subcontracting
    service the ERPNext way — via Subcontracting Receipt and supplied_items — and
    PP-flow orders have neither (see CustomSubcontractingOrder.update_status, which
    exists precisely because ERPNext's own status rules are unreachable here).
    Other Info carries printing settings and accounting dimensions nobody sets.

    Hidden, not removed: the fields and their data stay exactly where they are, so
    this is reversible by deleting two Property Setters, and any document that
    already carries a value in them keeps it.
    """
    for fieldname in ("tab_additional_costs", "tab_other_info"):
        frappe.make_property_setter(
            {
                "doctype": "Subcontracting Order",
                "fieldname": fieldname,
                "property": "hidden",
                "value": 1,
                "property_type": "Check",
            }
        )
    frappe.db.commit()


def hide_sco_amount_fields():
    """Hide 'Total Estimated Taxes' and 'Grand Total' on the Job Work Order.

    Both are ERPNext's own costing of a subcontracting order, and on this site's flow
    they say nothing true. A PP-flow order is priced per drawing in Kg through the
    Drawing Items table's rate/job work amount, not through the item rates and the tax
    table these two total up -- the Taxes table is not used, so Total Estimated Taxes
    reads 0 on every order, and Grand Total repeats a figure that does not include the
    job work being paid for.

    Hidden, not removed: same as hide_sco_unused_tabs, this is two Property Setters and
    deleting them brings the fields back with their data intact. Safe to hide outright
    because neither is reqd -- the reqd-before-hidden dance in
    hide_sco_job_worker_warehouse does not apply here (verified against the meta).
    """
    for fieldname in ("total_taxes", "base_grand_total"):
        frappe.make_property_setter(
            {
                "doctype": "Subcontracting Order",
                "fieldname": fieldname,
                "property": "hidden",
                "value": 1,
                "property_type": "Check",
            }
        )
    frappe.db.commit()


def make_sco_job_worker_conditional():
    """Job Worker (core field 'supplier') and its dependent 'supplier_name' (Job Worker
    Name, fetch_from supplier.supplier_name) are only meaningful when the SCO's
    Production Plan Type is Supplier Job / Supplier with Material -- an Internal Job
    plan has no custom_vendor_contractor to begin with (create_sco_from_production_plan
    sets supplier = pp.custom_vendor_contractor or "", which is blank for Internal Job),
    so the core reqd=1 on both fields wrongly blocked submit. Override reqd to 0 on both
    and use mandatory_depends_on instead, keyed off the new fetched
    custom_production_plan_type field, so both fields stay required for Supplier
    Job/Supplier with Material (and for any manually-created SCO with no linked
    Production Plan at all, where the blank string also fails the
    '!== "Internal Job"' check) but optional for Internal Job."""
    condition = 'eval:doc.custom_production_plan_type !== "Internal Job"'
    for fieldname in ("supplier", "supplier_name"):
        frappe.make_property_setter(
            {
                "doctype": "Subcontracting Order",
                "fieldname": fieldname,
                "property": "reqd",
                "value": 0,
                "property_type": "Check",
            }
        )
        frappe.make_property_setter(
            {
                "doctype": "Subcontracting Order",
                "fieldname": fieldname,
                "property": "mandatory_depends_on",
                "value": condition,
                "property_type": "Code",
            }
        )
    frappe.db.commit()


def create_sco_custom_fields():
    create_custom_fields(
        {
            "Subcontracting Order": [
                {
                    "fieldname": "custom_production_plan",
                    "fieldtype": "Link",
                    "label": "Production Plan",
                    "options": "Production Plan",
                    "read_only": 1,
                    "insert_after": "supplier",
                },
                {
                    "fieldname": "custom_production_plan_type",
                    "fieldtype": "Data",
                    "label": "Production Plan Type",
                    "fetch_from": "custom_production_plan.custom_type",
                    "read_only": 1,
                    "hidden": 1,
                    "insert_after": "custom_production_plan",
                    "description": "Drives whether Job Worker is mandatory (see make_sco_job_worker_conditional) -- Internal Job plans have no supplier, so the field is optional for them.",
                },
                {
                    "fieldname": "custom_work_order",
                    "fieldtype": "Link",
                    "label": "Work Order",
                    "options": "Work Order",
                    "read_only": 1,
                    "insert_after": "custom_production_plan_type",
                },
                {
                    "fieldname": "custom_all_ops_complete",
                    "fieldtype": "Check",
                    "label": "All Operations Complete",
                    "read_only": 1,
                    "insert_after": "custom_work_order",
                },
                {
                    "fieldname": "custom_supervisor",
                    "fieldtype": "Link",
                    "label": "Supervisor Name",
                    "options": "Employee",
                    "insert_after": "custom_all_ops_complete",
                },
                {
                    "fieldname": "custom_supervisor_mobile",
                    "fieldtype": "Data",
                    "label": "Mobile",
                    "fetch_from": "custom_supervisor.cell_number",
                    "read_only": 1,
                    "insert_after": "custom_supervisor",
                },
                {
                    # Warehouse fields moved to Material Issue Plan; the actual
                    # value used to compute this now comes from there (see
                    # subcontracting.py: _get_sco_transfer_warehouses).
                    "fieldname": "custom_cnc_transferred_weight_kg",
                    "fieldtype": "Float",
                    "label": "CNC Warehouse Qty (Kg)",
                    "read_only": 1,
                    "insert_after": "custom_supervisor_mobile",
                    "description": "Weight currently sitting in CNC warehouse awaiting transfer to supplier",
                    "allow_on_submit": 1,
                },
                {
                    "fieldname": "custom_section_drawings",
                    "fieldtype": "Section Break",
                    "label": "Drawing Details",
                    "insert_after": "custom_cnc_transferred_weight_kg",
                },
                {
                    "fieldname": "custom_drawing_items",
                    "fieldtype": "Table",
                    "label": "Drawing Items",
                    "options": "SCO Drawing Item",
                    "read_only": 1,
                    "insert_after": "custom_section_drawings",
                },
                {
                    "fieldname": "custom_section_weights",
                    "fieldtype": "Section Break",
                    "label": "Weight Summary",
                    "insert_after": "custom_drawing_items",
                },
                {
                    "fieldname": "custom_customer_weight_kg",
                    "fieldtype": "Float",
                    "label": "Cust Weight (Total)",
                    "read_only": 1,
                    "insert_after": "custom_section_weights",
                    "description": "Sum of customer-provided weight across all drawings",
                },
                {
                    "fieldname": "custom_total_weight_kg",
                    "fieldtype": "Float",
                    "label": "Planned RM Weight (Kg)",
                    "read_only": 1,
                    "insert_after": "custom_customer_weight_kg",
                    "description": "Sum of planned raw-material weight across all drawings",
                },
                {
                    "fieldname": "custom_mapped_weight_kg",
                    "fieldtype": "Float",
                    "label": "Mapped Weight (Kg)",
                    "read_only": 1,
                    "insert_after": "custom_total_weight_kg",
                    "description": "Reserved/mapped batch weight from Material Planning that will be transferred to the supplier",
                },
                {
                    "fieldname": "custom_excess_weight_kg",
                    "fieldtype": "Float",
                    "label": "Excess Weight (Kg)",
                    "read_only": 1,
                    "insert_after": "custom_mapped_weight_kg",
                    "description": "Over-mapped weight (mapped beyond planned) that the supplier must return",
                },
                {
                    "fieldname": "custom_excess_banner_html",
                    "fieldtype": "HTML",
                    "label": "Excess Banner",
                    "insert_after": "custom_excess_weight_kg",
                },
                {
                    "fieldname": "custom_transferred_weight_kg",
                    "fieldtype": "Float",
                    "label": "Transferred Weight (Kg)",
                    "read_only": 1,
                    "insert_after": "custom_excess_banner_html",
                    "description": "Weight actually transferred to supplier warehouse (updated on SE submit)",
                },
                {
                    "fieldname": "custom_operations_tab",
                    "fieldtype": "Tab Break",
                    "label": "Operations",
                    "insert_after": "letter_head",
                },
                {
                    "fieldname": "custom_operations_html",
                    "fieldtype": "HTML",
                    "label": "Operations Summary",
                    "insert_after": "custom_operations_tab",
                },
            ],
            # The Job Work Order's one item line is in Kg (sum of its Production Plan
            # rows' Planned Qty); the pieces it covers ride alongside as Qty (Nos)
            # (sep14 FG plan, A3 item 6).
            "Subcontracting Order Item": [
                {
                    "fieldname": "custom_material_spec",
                    "label": "Material Spec",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_spec",
                    "read_only": 1,
                    "insert_after": "item_name",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_material_grade",
                    "label": "Material Grade",
                    "fieldtype": "Data",
                    "fetch_from": "item_code.custom_material_grade",
                    "read_only": 1,
                    "insert_after": "custom_material_spec",
                    "in_list_view": 0,
                },
                {
                    "fieldname": "custom_sec_qty",
                    "fieldtype": "Float",
                    "label": "Qty (Nos)",
                    "read_only": 1,
                    "insert_after": "qty",
                },
                {
                    "fieldname": "custom_sec_uom",
                    "fieldtype": "Link",
                    "label": "Sec UOM",
                    "options": "UOM",
                    "default": "Nos",
                    "read_only": 1,
                    "insert_after": "custom_sec_qty",
                },
            ],
        },
        update=True,
    )


SCO_CLIENT_SCRIPT = """
frappe.ui.form.on("Subcontracting Order", {
\trefresh(frm) {
\t\t// Excess material banner — mirrors the Material Planning "Difference in Kg" notice
\t\tlet $bw = frm.fields_dict["custom_excess_banner_html"] && frm.fields_dict["custom_excess_banner_html"].$wrapper;
\t\tif ($bw) {
\t\t\tlet excess = flt(frm.doc.custom_excess_weight_kg);
\t\t\tif (excess > 0) {
\t\t\t\t$bw.html('<div style="margin-top:8px;padding:8px 12px;background:#f1f8e9;border-left:3px solid #66bb6a;border-radius:3px;font-size:12px;color:#33691e;"><b>Excess material (+' + flt(excess, 3).toFixed(3) + ' Kg):</b> This much extra is mapped versus planned. Ensure the supplier returns the excess quantity after the job.</div>');
\t\t\t} else if (frm.doc.custom_all_ops_complete) {
\t\t\t\t$bw.html("");
\t\t\t}
\t\t}

\t\t// ERPNext offers "Subcontracting Receipt" under Create on every submitted
\t\t// order. A Job Work Order raised from a Production Plan has no service items
\t\t// and no Raw Materials Supplied table to receive against, so that button can
\t\t// only lead to a broken receipt -- finished goods arrive through the Material
\t\t// Issue Plan's final Stock Entry instead. Runs after the standard controller's
\t\t// refresh, which is what added it.
\t\tfrm.remove_custom_button(__("Subcontracting Receipt"), __("Create"));

\t\tif (frm.doc.docstatus === 1 && frm.doc.custom_production_plan) {

\t\t\t// Straight to the Material Issue Plan for this order -- the two documents
\t\t\t// are worked on together and there is no link field either way. Placed
\t\t\t// before the Create group so it reads as navigation, not creation.
\t\t\tfrappe.db.get_value("Material Issue Plan",
\t\t\t\t{ subcontracting_order: frm.doc.name, docstatus: ["!=", 2] }, "name")
\t\t\t\t.then(function(r) {
\t\t\t\t\tvar mip = r && r.message && r.message.name;
\t\t\t\t\tif (!mip) return;
\t\t\t\t\tfrm.add_custom_button(__("Open MIP"), function() {
\t\t\t\t\t\tfrappe.set_route("Form", "Material Issue Plan", mip);
\t\t\t\t\t});
\t\t\t\t});

\t\t\tfrm.add_custom_button(__("Material Issue Plan"), function() {
\t\t\t\tfrappe.call({
\t\t\t\t\tmethod: "manufyxinvenzaerp.subcontracting_management.doctype.material_issue_plan.material_issue_plan.create_from_subcontracting_order",
\t\t\t\t\targs: { sco_name: frm.doc.name },
\t\t\t\t\tfreeze: true,
\t\t\t\t\tfreeze_message: __("Creating Material Issue Plan…"),
\t\t\t\t\tcallback: function(r) {
\t\t\t\t\t\tif (r.message) {
\t\t\t\t\t\t\tfrappe.set_route("Form", "Material Issue Plan", r.message);
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t});
\t\t\t}, __("Create"));

\t\t\t// "Make Final Stock Entry" moved to Material Issue Plan (see
\t\t\t// material_issue_plan.js's _add_final_stock_entry_button) -- the Return
\t\t\t// Excess Entry / stock-return workflow already lives there, so the
\t\t\t// finished-goods stock entry is created from the same place.

\t\t\t// Create one Supplier Operation Entry per subcontractor operation
\t\t\tif (frm.doc.custom_transferred_weight_kg) {
\t\t\t\tfrm.add_custom_button(__("Supplier Operation Entries"), function() {
\t\t\t\t\tfrappe.call({
\t\t\t\t\t\tmethod: "manufyxinvenzaerp.subcontracting_management.subcontracting.create_supplier_operation_entries",
\t\t\t\t\t\targs: { sco_name: frm.doc.name },
\t\t\t\t\t\tfreeze: true,
\t\t\t\t\t\tcallback: function(r) {
\t\t\t\t\t\t\tif (r.message && r.message.length) {
\t\t\t\t\t\t\t\tfrappe.msgprint({
\t\t\t\t\t\t\t\t\ttitle: __("Supplier Operation Entries Created"),
\t\t\t\t\t\t\t\t\tmessage: r.message.join(", "),
\t\t\t\t\t\t\t\t\tindicator: "green"
\t\t\t\t\t\t\t\t});
\t\t\t\t\t\t\t} else if (frm.doc.custom_all_ops_complete) {
\t\t\t\t\t\t\t\tfrappe.msgprint(__("All Supplier Operation Entries already exist."));
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\tfrm.reload_doc();
\t\t\t\t\t\t}
\t\t\t\t\t});
\t\t\t\t}, __("Create"));
\t\t\t}

\t\t}
\t},
});

""".strip()


SCO_OPS_SCRIPT_NAME = "Subcontracting Order-operations-summary"

SCO_OPS_SCRIPT = """
frappe.ui.form.on("Subcontracting Order", {
    refresh(frm) {
        render_soe_summary(frm);
    }
});

// What the job was meant to send, what it actually sent, and the gap -- directly
// above the operations table, because that is where the number matters and the two
// fields it is built from sit on a different tab entirely.
//
// SC-ORD-2026-00004 ran its whole operation chain on 10,315.918 Kg against a mapped
// 10,788.533: the 472.615 Kg of CNC material was never sent, op 1 took the short
// figure as its Available to Consume without comment, and the shortfall was only
// visible to somebody who thought to compare two fields on another tab. Nothing
// blocks a partial transfer -- it is a supported way to work -- so the fix is to
// state the gap where the operations are read, not to refuse the operations.
function transfer_gap_banner(frm) {
    var planned = flt(frm.doc.custom_mapped_weight_kg || 0);
    var sent = flt(frm.doc.custom_transferred_weight_kg || 0);
    var pending = flt(planned - sent);
    // Rounded before comparing: these are sums of 3-decimal weights, so a job that
    // sent everything lands a few millionths off zero and would read as pending.
    var short = Math.round(pending * 1000) / 1000 > 0;
    var tone = short
        ? { bg: '#fef2f2', line: '#fecaca', ink: '#b91c1c' }
        : { bg: '#f0fdf4', line: '#bbf7d0', ink: '#15803d' };

    function cell(label, value, ink) {
        return "<div style='flex:1 1 150px'>"
            + "<div style='font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em'>"
            + label + "</div>"
            + "<div style='font-size:16px;font-weight:600;" + (ink ? "color:" + ink : "") + "'>"
            + format_number(value, null, 3) + " <small style='font-weight:400'>Kg</small></div>"
            + "</div>";
    }

    return "<div style='display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;"
        + "border:1px solid " + tone.line + ";background:" + tone.bg + ";"
        + "border-radius:6px;padding:10px 14px;margin-bottom:10px'>"
        + cell("Total Planned to Transfer", planned, "")
        + cell("Transferred", sent, "")
        + cell(short ? "Not Yet Transferred" : "Fully Transferred", pending, tone.ink)
        + (short
            ? "<div style='flex:2 1 260px;font-size:11px;color:" + tone.ink + ";padding-top:14px'>"
              + "Operations below are running on the transferred weight only. Material still "
              + "in stores &mdash; CNC Process rows go out on their own transfer &mdash; will "
              + "not reach the supplier by finishing these operations.</div>"
            : "")
        + "</div>";
}

function render_soe_summary(frm) {
    var field = frm.get_field("custom_operations_html");
    if (!field) return;
    var $w = field.$wrapper;
    if (!frm.doc.name || frm.is_new()) {
        $w.html("<div class='text-muted'>Save and submit the Subcontracting Order to create operations.</div>");
        return;
    }
    frappe.call({
        method: "manufyxinvenzaerp.subcontracting_management.subcontracting.get_soe_summary",
        args: { sco_name: frm.doc.name },
        callback(r) {
            var rows = r.message || [];
            if (!rows.length) {
                // The banner shows here too, and this is the most useful moment for
                // it: before any operation exists is when an unsent leg can still be
                // sent without unwinding anything.
                $w.html(transfer_gap_banner(frm)
                    + "<div style='margin-bottom:8px'><button class='btn btn-xs btn-default sco-ops-refresh'>&#8635; Refresh</button></div>"
                    + "<div class='text-muted'>No Supplier Operation Entries created yet.</div>");
                $w.find(".sco-ops-refresh").on("click", function() { render_soe_summary(frm); });
                return;
            }
            var body = rows.map(function (d, idx) {
                var color = d.status === "Completed" ? "green"
                          : (d.status === "In Progress" ? "orange" : "gray");
                var submitted = d.docstatus === 1
                    ? "<span class='indicator green'>Submitted</span>"
                    : "<span class='indicator gray'>Draft</span>";
                var mfg     = flt(d.total_qty_to_mfg || 0);
                var avail   = flt(d.avail_nos || 0);
                var gross   = flt(d.avail_gross_nos || 0);
                var consumed = flt(d.total_completed_nos || 0);
                var diff    = flt(d.diff_nos || 0);
                var diff_color = diff < 0 ? "color:red" : (diff > 0 ? "color:orange" : "");
                var is_op1  = (d.sequence_id || 1) == 1;
                // What is left, with what arrived beside it: "nothing left" and
                // "nothing ever arrived" look identical otherwise. Negative means this
                // operation completed more pieces than it was handed.
                var avail_cell = is_op1
                    ? format_number(avail, null, 3) + " <small class='text-muted'>Kg</small>"
                    : "<span" + (avail < 0 ? " style='color:red'" : "") + ">"
                        + format_number(avail, null, 3) + "</span>"
                        + (consumed ? " <small class='text-muted'>of " + format_number(gross, null, 3) + "</small>" : "");
                return "<tr>"
                    + "<td class='text-center'>" + (d.sequence_id || "") + "</td>"
                    + "<td><a href='/app/supplier-operation-entry/" + encodeURIComponent(d.name) + "' style='color:#0ea5e9;text-decoration:underline;'>"
                        + frappe.utils.escape_html(d.operation || "") + "</a></td>"
                    + "<td><span class='indicator " + color + "'>" + (d.status || "") + "</span></td>"
                    + "<td class='text-right'>" + format_number(mfg, null, 3) + "</td>"
                    + "<td class='text-right'>" + avail_cell + "</td>"
                    + "<td class='text-right'>" + format_number(consumed, null, 3) + "</td>"
                    + "<td class='text-right' style='" + diff_color + "'>" + format_number(diff, null, 3) + "</td>"
                    + "<td class='text-center'>" + submitted + "</td>"
                    + "<td class='text-center'><button class='btn btn-xs btn-default sco-drw-btn' data-idx='" + idx + "' title='View Drawings'>&#128366;</button></td>"
                    + "</tr>";
            }).join("");
            var html = transfer_gap_banner(frm)
                + "<div style='margin-bottom:8px'><button class='btn btn-xs btn-default sco-ops-refresh'>&#8635; Refresh</button></div>"
                + "<table class='table table-bordered' style='margin-top:4px'>"
                + "<thead><tr>"
                + "<th class='text-center' style='width:60px'>Seq</th>"
                + "<th>Operation</th>"
                + "<th style='width:130px'>Status</th>"
                + "<th class='text-right'>Overall Qty (Nos)</th>"
                + "<th class='text-right'>Available to Consume (Nos)</th>"
                + "<th class='text-right'>Total Consumed (Nos)</th>"
                + "<th class='text-right'>Difference (Nos)</th>"
                + "<th class='text-center' style='width:110px'>Entry</th>"
                + "<th class='text-center' style='width:70px'>Drawings</th>"
                + "</tr></thead><tbody>" + body + "</tbody></table>"
                + "<div class='text-muted' style='margin-top:6px;font-size:11px'>"
                + "Op-1 Available = Transferred (Kg). Op-2+ Available = what is still left to consume, "
                + "with what arrived shown beside it. Difference = Overall Qty less Total Consumed &mdash; "
                + "what this operation still owes.</div>";
            $w.html(html);
            $w.find(".sco-ops-refresh").on("click", function() { render_soe_summary(frm); });
            $w.find(".sco-drw-btn").on("click", function() {
                var idx = parseInt($(this).data("idx"), 10);
                show_drawing_popup(rows[idx]);
            });
        }
    });
}

function show_drawing_popup(soe) {
    var drawings = soe.drawing_details || [];
    // Every piece count gets its weight beside it. Pieces alone cannot be reconciled
    // against anything else on the job -- the transfer, the operation totals and the
    // finished-goods entry are all in Kg -- so a popup that answered only in Nos left
    // the reader converting in their head against a per-piece weight held elsewhere.
    // Planned is the drawing's own weight, Transferred is what reached the supplier
    // for it, and Consumed comes from this operation's consumption log.
    var kg = function(v) {
        return "<td class='text-right text-muted'>" + format_number(flt(v || 0), null, 3) + "</td>";
    };
    var drw_rows = drawings.map(function(d) {
        return "<tr>"
            + "<td>" + frappe.utils.escape_html(d.drawing || "") + "</td>"
            + "<td>" + frappe.utils.escape_html(d.customer_drawing_number || "") + "</td>"
            + "<td class='text-right'>" + format_number(flt(d.qty_to_manufacture || 0), null, 3) + "</td>"
            + kg(d.planned_weight_kg)
            + kg(d.transferred_weight_kg)
            + "<td class='text-right'>" + format_number(flt(d.completed_qty_nos || 0), null, 3) + "</td>"
            + kg(d.consumed_kg)
            + "</tr>";
    }).join("");
    var content = !drawings.length
        ? "<div class='text-muted' style='padding:12px'>No drawings attached to this operation.</div>"
        : "<table class='table table-bordered table-condensed' style='margin:0'>"
            + "<thead><tr>"
            + "<th>Drawing</th><th>Cust Drawing No</th>"
            + "<th class='text-right'>Qty to Mfg (Nos)</th>"
            + "<th class='text-right'>Planned (Kg)</th>"
            + "<th class='text-right'>Transferred (Kg)</th>"
            + "<th class='text-right'>Completed (Nos)</th>"
            + "<th class='text-right'>Consumed (Kg)</th>"
            + "</tr></thead>"
            + "<tbody>" + drw_rows + "</tbody>"
            + "</table>";
    var dlg = new frappe.ui.Dialog({
        title: "Drawings — " + frappe.utils.escape_html(soe.operation || soe.name),
        fields: [{ fieldtype: "HTML", fieldname: "content" }],
    });
    dlg.fields_dict.content.$wrapper.html(content);
    dlg.show();
}
""".strip()


SOE_CLIENT_SCRIPT = """
frappe.ui.form.on("SOE Consumption Log", {
\tdrawing: function(frm, cdt, cdn) {
\t\t_sync_drawing_nos(frm);
\t\t_calc_consumption_weight_kg(frm, cdt, cdn);
\t},
\tqty_nos: function(frm, cdt, cdn) {
\t\t_sync_drawing_nos(frm);
\t\t_calc_consumption_weight_kg(frm, cdt, cdn);
\t},
\tconsumption_log_remove: function(frm) {
\t\t_sync_drawing_nos(frm);
\t},
\tconsumption_log_add: function(frm) {
\t\t_sync_drawing_nos(frm);
\t}
});

frappe.ui.form.on("Supplier Operation Entry", {
\tstatus: function(frm) {
\t\tif (frm.doc.status !== "Completed") {
\t\t\tfrm.__mfx_prev_status = frm.doc.status;
\t\t\treturn;
\t\t}
\t\tif (frm.doc.docstatus !== 0 || frm.is_new()) return;
\t\tif (frm._mfx_completing) return;

\t\tvar previous = frm.__mfx_prev_status ||
\t\t\t((frm.doc.consumption_log || []).length ? "In Progress" : "Open");
\t\tfunction restore_status() {
\t\t\tfrm._mfx_completing = false;
\t\t\tfrm.set_value("status", previous);
\t\t}
\t\tfrm._mfx_completing = true;
\t\tfrappe.call({
\t\t\tmethod: "manufyxinvenzaerp.subcontracting_management.subcontracting.check_soe_completion_before_confirm",
\t\t\targs: { doc: frm.doc },
\t\t\tfreeze: true,
\t\t\tfreeze_message: __("Validating operation…"),
\t\t\tcallback: function(r) {
\t\t\t\tif (!r.message || !r.message.ready) { restore_status(); return; }
\t\t\t\tfrappe.confirm(
\t\t\t\t\t__("Mark as complete and submit the Operation Entry?<br><br>Submitting passes its finished quantity to the next operation. It cannot be cancelled on its own afterwards — only by cancelling the whole Job Work Order."),
\t\t\t\t\tfunction() {
\t\t\t\t\t\t// Submit directly: savesubmit() would ask for a second confirmation.
\t\t\t\t\t\tfrm.save("Submit", function() { frm._mfx_completing = false; }, null, restore_status);
\t\t\t\t\t},
\t\t\t\t\trestore_status
\t\t\t\t);
\t\t\t},
\t\t\terror: restore_status,
\t\t});
\t},

\trefresh: function(frm) {
\t\tif (frm.doc.status !== "Completed") frm.__mfx_prev_status = frm.doc.status;
\t\t_sync_drawing_nos(frm);
\t\t// Filter drawing link in log to only drawings present in this SOE
\t\tvar valid_drawings = (frm.doc.drawing_details || []).map(function(r) {
\t\t\treturn r.drawing;
\t\t}).filter(Boolean);
\t\tif (valid_drawings.length) {
\t\t\tfrm.fields_dict.consumption_log.grid.update_docfield_property(
\t\t\t\t"drawing", "get_query", function() {
\t\t\t\t\treturn { filters: [["Drawing", "name", "in", valid_drawings]] };
\t\t\t\t}
\t\t\t);
\t\t}

\t\t// Testing convenience -- fills Consumption Log with one row per drawing at its
\t\t// full available quantity in one click, instead of adding rows one by one.
\t\t//
\t\t// Shown only where Manufyxinvenza Settings enables Auto Purchase, the same
\t\t// switch that reveals the Auto Purchase section on Material Planning. Both
\t\t// are shortcuts for testing rather than steps in the real process, and a
\t\t// button that fills a consumption log with every drawing at its full
\t\t// quantity is not one to leave in front of an operator on a live site.
\t\tif (frm.doc.docstatus === 0 && !frm.is_new()) {
\t\t\tfrappe.db.get_single_value("Manufyxinvenza Settings", "auto_purchase_from_material_planning")
\t\t\t\t.then(function(enabled) {
\t\t\t\t\tif (!enabled) return;
\t\t\t\t\tfrm.add_custom_button(__("Add All Drawing"), function() {
\t\t\t\t\t\t_add_all_drawing_to_log(frm);
\t\t\t\t\t}, __("Testing"));
\t\t\t\t});
\t\t}
\t}
});

function _add_all_drawing_to_log(frm) {
\tvar rows = frm.doc.drawing_details || [];
\tif (!rows.length) {
\t\tfrappe.msgprint(__("No drawings on this Supplier Operation Entry yet."));
\t\treturn;
\t}
\tvar added = 0;
\trows.forEach(function(row) {
\t\tif (!row.drawing) return;
\t\tvar qty = flt(row.available_to_consume_nos) || flt(row.qty_to_manufacture);
\t\tif (!qty) return;
\t\tvar log_row = frm.add_child("consumption_log", {
\t\t\tdate: frappe.datetime.get_today(),
\t\t\tdrawing: row.drawing,
\t\t\tqty_nos: qty,
\t\t});
\t\t_calc_consumption_weight_kg(frm, log_row.doctype, log_row.name);
\t\tadded++;
\t});
\tfrm.refresh_field("consumption_log");
\t_sync_drawing_nos(frm);
\tif (added) {
\t\tfrm.dirty();
\t\tfrappe.show_alert({ message: __("Added {0} drawing(s) to Consumption Log.", [added]), indicator: "green" }, 5);
\t} else {
\t\tfrappe.msgprint(__("Nothing to add -- no drawing has an available quantity yet."));
\t}
}

function _sync_drawing_nos(frm) {
\t// Sum qty_nos per drawing from the consumption log
\tvar byDrawing = {};
\t(frm.doc.consumption_log || []).forEach(function(r) {
\t\tif (r.drawing) {
\t\t\tbyDrawing[r.drawing] = (byDrawing[r.drawing] || 0) + flt(r.qty_nos);
\t\t}
\t});

\t// Push completed_qty_nos into each drawing_details row -- only when Inspection
\t// Mandatory is off. When it's on, completed_qty_nos only ever grows through an
\t// Inspection Entry's Accepted Qty (server-side, on submit) -- pushing the raw
\t// log total here would leak unreviewed quantity straight past QC the moment the
\t// form is saved. Mirrors subcontracting.validate_supplier_operation_entry.
\tif (!frm.doc.custom_inspection_mandatory) {
\t\t(frm.doc.drawing_details || []).forEach(function(row) {
\t\t\tvar completed = flt(byDrawing[row.drawing] || 0, 3);
\t\t\tfrappe.model.set_value(row.doctype, row.name, "completed_qty_nos", completed);
\t\t});
\t\tfrm.refresh_field("drawing_details");
\t}

\t// Auto-advance status
\tvar has_log = (frm.doc.consumption_log || []).some(function(r) { return flt(r.qty_nos) > 0; });
\tif (has_log && frm.doc.status === "Open") {
\t\tfrm.set_value("status", "In Progress");
\t}

\t// Op-2+: warn if any drawing exceeds available_to_consume_nos -- not meaningful
\t// when Inspection Mandatory is on, since rework can legitimately push the raw log
\t// total past "available" (the server no longer blocks that case either).
\tif ((frm.doc.sequence_id || 1) > 1 && !frm.doc.custom_inspection_mandatory) {
\t\tvar detailMap = {};
\t\t(frm.doc.drawing_details || []).forEach(function(r) {
\t\t\tif (r.drawing) detailMap[r.drawing] = flt(r.available_to_consume_nos);
\t\t});
\t\tvar exceeded = Object.keys(byDrawing).filter(function(d) {
\t\t\tvar avail = detailMap[d] || 0;
\t\t\treturn avail > 0 && byDrawing[d] > avail;
\t\t});
\t\tif (exceeded.length) {
\t\t\tfrappe.show_alert({
\t\t\t\tmessage: __("Completed Nos for some drawings exceeds available from the previous operation."),
\t\t\t\tindicator: "red"
\t\t\t}, 8);
\t\t}
\t}
}

function _calc_consumption_weight_kg(frm, cdt, cdn) {
\t// Total Weight (Kg) for a consumption log row = Qty (Nos) x the linked Drawing's
\t// per-piece weight (Drawing.total_weight / Drawing.no_of_qty_to_manufacture).
\t// This feeds total_consumed_kg (see subcontracting.py's Op-1 over-consume
\t// guard), which in turn seeds the NEXT operation's available_to_consume_kg --
\t// so it must be auto-derived, not left for the inspector to type by hand.
\t//
\t// The per-piece figure is now kept as well, in wt_per_pcs_kg. It was always
\t// computed here and thrown away, which left the log showing a row total with
\t// nothing to read it against: 1,790.089 Kg for 4 Nos beside a Transferred (Kg)
\t// of 6,846.680 on the drawing row looks like a mismatch until you know one is
\t// per-consumption and the other is the whole drawing.
\tvar row = locals[cdt][cdn];
\tif (!row.drawing || !flt(row.qty_nos)) {
\t\tfrappe.model.set_value(cdt, cdn, "wt_per_pcs_kg", 0);
\t\tfrappe.model.set_value(cdt, cdn, "weight_kg", 0);
\t\treturn;
\t}
\tfrappe.db.get_value("Drawing", row.drawing, ["total_weight", "no_of_qty_to_manufacture"]).then(function(r) {
\t\tvar d = r.message || {};
\t\tvar total_qty = flt(d.no_of_qty_to_manufacture);
\t\tvar weight_per_nos = total_qty ? flt(d.total_weight) / total_qty : 0;
\t\tfrappe.model.set_value(cdt, cdn, "wt_per_pcs_kg", flt(weight_per_nos, 3));
\t\t// Off the unrounded per-piece weight, not the rounded display value: rounding
\t\t// first and multiplying by the count carries the error up by that many pieces.
\t\tfrappe.model.set_value(cdt, cdn, "weight_kg", flt(weight_per_nos * flt(row.qty_nos), 3));
\t});
}
""".strip()


def create_sco_client_script():
    if frappe.db.exists("Client Script", SCO_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", SCO_CLIENT_SCRIPT_NAME, "script", SCO_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", SCO_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": SCO_CLIENT_SCRIPT_NAME,
            "dt": "Subcontracting Order",
            "view": "Form",
            "enabled": 1,
            "script": SCO_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_sco_ops_client_script():
    if frappe.db.exists("Client Script", SCO_OPS_SCRIPT_NAME):
        frappe.db.set_value("Client Script", SCO_OPS_SCRIPT_NAME, "script", SCO_OPS_SCRIPT)
        frappe.db.set_value("Client Script", SCO_OPS_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": SCO_OPS_SCRIPT_NAME,
            "dt": "Subcontracting Order",
            "view": "Form",
            "enabled": 1,
            "script": SCO_OPS_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_soe_client_script():
    if frappe.db.exists("Client Script", SOE_CLIENT_SCRIPT_NAME):
        frappe.db.set_value("Client Script", SOE_CLIENT_SCRIPT_NAME, "script", SOE_CLIENT_SCRIPT)
        frappe.db.set_value("Client Script", SOE_CLIENT_SCRIPT_NAME, "enabled", 1)
    else:
        frappe.get_doc({
            "doctype": "Client Script",
            "name": SOE_CLIENT_SCRIPT_NAME,
            "dt": "Supplier Operation Entry",
            "view": "Form",
            "enabled": 1,
            "script": SOE_CLIENT_SCRIPT,
        }).insert(ignore_permissions=True)
    frappe.db.commit()


def create_manufacturing_settings_custom_fields():
    create_custom_fields(
        {
            "Manufacturing Settings": [
                {
                    "fieldname": "custom_soe_log_trigger",
                    "fieldtype": "Select",
                    "label": "SOE Log Entry Allowed When",
                    "options": "Fully Transferred\nPartially Transferred",
                    "default": "Fully Transferred",
                    "insert_after": "make_serial_no_batch_from_work_order",
                    "description": (
                        "Fully Transferred: consumption log entries are blocked until all planned "
                        "weight for that drawing has been transferred to the supplier warehouse. "
                        "Partially Transferred: log entries are always allowed."
                    ),
                },
            ],
        },
        update=True,
    )


INSPECTION_OPERATIONS = ["Fitup Inspection", "Final Inspection"]


# ─── WO client script (mirrors SCO_CLIENT_SCRIPT) ─────────────────────────


# ─── WO operations summary script (mirrors SCO_OPS_SCRIPT) ───────────────


# ─── Job Card drawing consumption script (mirrors SOE_CLIENT_SCRIPT) ─────


# ─────────────────────────────────────────────────────────────────────────────
# Material Planning — Auto Purchase custom fields
# ─────────────────────────────────────────────────────────────────────────────

def create_material_planning_auto_purchase_fields():
    """Add supplier, warning, and button fields used by the Auto Purchase feature."""
    create_custom_fields(
        {
            "Material Planning": [
                {
                    "fieldname": "custom_auto_purchase_section",
                    "fieldtype": "Section Break",
                    "label": "Auto Purchase",
                    "insert_after": "consolidate_items",
                    "hidden": 1,
                },
                {
                    "fieldname": "custom_auto_purchase_warning",
                    "fieldtype": "HTML",
                    "options": (
                        '<div style="margin:6px 0 10px;padding:8px 14px;'
                        'background:#fff3cd;border-left:4px solid #e6a817;'
                        'border-radius:3px;font-size:12px;color:#7d4e00;">'
                        "<strong>&#9888; Testing Only</strong> &mdash; "
                        "Auto Purchase feature is only for testing purposes. "
                        "Not recommended to use in live or production environments."
                        "</div>"
                    ),
                    "insert_after": "custom_auto_purchase_section",
                },
                {
                    # Sits directly under the Consolidate Item table it acts on, and
                    # is hidden with the rest of this section unless Auto Purchase is
                    # switched on in Manufyxinvenza Settings -- same rule as the
                    # Supplier field below.
                    "fieldname": "custom_auto_suggest_dimensions_btn",
                    "fieldtype": "Button",
                    "label": "Auto Suggest Item Dimensions",
                    "insert_after": "custom_auto_purchase_warning",
                    "hidden": 1,
                    "description": (
                        "Fills each Consolidate Item with the largest size among the "
                        "requirements it covers, and the Sec Qty that matches the "
                        "required weight. Edit and save afterwards."
                    ),
                },
                {
                    "fieldname": "custom_auto_purchase_supplier",
                    "fieldtype": "Link",
                    "label": "Supplier (Auto Purchase)",
                    "options": "Supplier",
                    "insert_after": "custom_auto_suggest_dimensions_btn",
                    "hidden": 1,
                    "description": "Supplier for the auto-created Purchase Order.",
                },
                {
                    "fieldname": "custom_auto_purchase_btn",
                    "fieldtype": "Button",
                    "label": "Auto Purchase",
                    "insert_after": "custom_auto_purchase_supplier",
                },
            ],
        },
        update=True,
    )


def create_payment_request_custom_fields():
    """Payment Type classification, plus (for Supplier/Outward requests) a link to the
    customer Payment Entry funding this supplier payment, with live balance tracking."""
    create_custom_fields(
        {
            "Payment Request": [
                {
                    "fieldname": "custom_payment_type",
                    "label": "Payment Type",
                    "fieldtype": "Select",
                    "options": "Advance Payment\nBill Payment",
                    "insert_after": "party_account_currency",
                    "reqd": 1,
                    "in_standard_filter": 1,
                },
                {
                    "fieldname": "custom_source_of_funds_section",
                    "fieldtype": "Section Break",
                    "label": "Source of Funds",
                    "insert_after": "custom_payment_type",
                    "depends_on": "eval:doc.party_type=='Supplier'",
                },
                {
                    "fieldname": "custom_source_of_funds",
                    "label": "Source of Funds (Customer Payment Entry)",
                    "fieldtype": "Link",
                    "options": "Payment Entry",
                    "insert_after": "custom_source_of_funds_section",
                    "in_standard_filter": 1,
                    "description": "Search by customer name or reference no. Restricted to "
                                   "submitted customer receipts (Payment Entry: Receive).",
                },
                {
                    "fieldname": "custom_total_customer_payment",
                    "label": "Total Customer Payment",
                    "fieldtype": "Currency",
                    "fetch_from": "custom_source_of_funds.paid_amount",
                    "read_only": 1,
                    "insert_after": "custom_source_of_funds",
                },
                {
                    "fieldname": "custom_customer_payment_date",
                    "label": "Customer Payment Date",
                    "fieldtype": "Date",
                    "fetch_from": "custom_source_of_funds.posting_date",
                    "read_only": 1,
                    "insert_after": "custom_total_customer_payment",
                },
                {
                    "fieldname": "custom_source_of_funds_column_break",
                    "fieldtype": "Column Break",
                    "insert_after": "custom_customer_payment_date",
                },
                {
                    "fieldname": "custom_already_used_amount",
                    "label": "Already Used Amount",
                    "fieldtype": "Currency",
                    "read_only": 1,
                    "insert_after": "custom_source_of_funds_column_break",
                    "description": "Sum of grand_total across other Paid Payment Requests "
                                   "drawing from the same Source of Funds.",
                },
                {
                    "fieldname": "custom_balance_amount",
                    "label": "Balance Amount",
                    "fieldtype": "Currency",
                    "read_only": 1,
                    "insert_after": "custom_already_used_amount",
                },
                {
                    "fieldname": "custom_payment_entry_created",
                    "label": "Payment Entry Created",
                    "fieldtype": "Check",
                    "read_only": 1,
                    "insert_after": "custom_balance_amount",
                },
            ],
        },
        update=True,
    )


def create_fg_sales_custom_fields():
    """Delivery Note Item / Sales Invoice Item fields for finished goods by the piece.

    Finished goods leave in Kg but are counted in Nos, per drawing (sep14 FG plan,
    D8/D22/D23). The user types Qty (Nos) and the Kg is worked out from the drawing
    batch, so both documents need the piece count, its UOM and the drawing it
    belongs to on every FG row.

    The Sales Invoice fields use the SAME names as the Delivery Note ones on
    purpose: ERPNext's mapper copies same-named fields from row to row, so a
    Delivery Note -> Sales Invoice carries them across with no mapping code.

    custom_sec_uom doubles as the "this is an FG row" flag for the client:
    Quantity (Kg) is read-only wherever it is set (see create_fg_property_setters).
    That is why it has NO default here, unlike on the Sales Order Item -- a default
    would lock the Kg on every raw-material row too.

    Grid budget (see layout_purchase_receipt_item_grid for how it works): Qty (Nos)
    takes one column right after Quantity. On the Delivery Note, UOM leaves the row
    view to pay for it; on the Sales Invoice, Item narrows from 4 columns to 3.
    """
    create_custom_fields(
        {
            "Delivery Note Item": [
                {
                    "fieldname": "custom_sec_qty",
                    "fieldtype": "Float",
                    "label": "Qty (Nos)",
                    "insert_after": "qty",
                    "in_list_view": 1,
                    "columns": 1,
                    "description": "Pieces delivered. For finished goods the Quantity (Kg) is calculated from it.",
                },
                {
                    "fieldname": "custom_sec_uom",
                    "fieldtype": "Link",
                    "label": "Sec UOM",
                    "options": "UOM",
                    "read_only": 1,
                    "insert_after": "custom_sec_qty",
                },
                {
                    "fieldname": "custom_billed_sec_qty",
                    "fieldtype": "Float",
                    "label": "Billed (Nos)",
                    "read_only": 1,
                    "no_copy": 1,
                    "insert_after": "billed_amt",
                    "description": "Pieces of this row invoiced so far, net of credit notes.",
                },
                {
                    "fieldname": "custom_drawing",
                    "fieldtype": "Link",
                    "label": "Drawing",
                    "options": "Drawing",
                    "read_only": 1,
                    "insert_after": "batch_no",
                },
                {
                    "fieldname": "custom_duno_mark_no",
                    "fieldtype": "Data",
                    "label": "DUNO/Mark No",
                    "read_only": 1,
                    "insert_after": "custom_drawing",
                },
            ],
            "Sales Invoice Item": [
                {
                    "fieldname": "custom_sec_qty",
                    "fieldtype": "Float",
                    "label": "Qty (Nos)",
                    "insert_after": "qty",
                    "in_list_view": 1,
                    "columns": 1,
                    "description": "Pieces invoiced. For finished goods the Quantity (Kg) is calculated from it.",
                },
                {
                    "fieldname": "custom_sec_uom",
                    "fieldtype": "Link",
                    "label": "Sec UOM",
                    "options": "UOM",
                    "read_only": 1,
                    "insert_after": "custom_sec_qty",
                },
                {
                    "fieldname": "custom_drawing",
                    "fieldtype": "Link",
                    "label": "Drawing",
                    "options": "Drawing",
                    "read_only": 1,
                    "insert_after": "batch_no",
                },
                {
                    "fieldname": "custom_duno_mark_no",
                    "fieldtype": "Data",
                    "label": "DUNO/Mark No",
                    "read_only": 1,
                    "insert_after": "custom_drawing",
                },
            ],
        },
        update=True,
    )


def create_fg_property_setters():
    """Standard-field changes for finished goods in Kg / Nos (sep14 FG plan, section 4.1).

    - Production Plan Item.planned_qty is the Kg, calculated from Qty (Nos) by
      production_plan.apply_fg_nos, so it says so and is read-only on drawing rows.
    - Delivery Note / Sales Invoice Item.qty (Kg) is read-only on FG rows, which are
      the rows with custom_sec_uom set: the Nos is typed and the Kg follows from the
      batch (D8, D22, D23).
    - Item.opening_stock is hidden: it creates a Stock Reconciliation, and Stock
      Reconciliation is blocked on this site (D21).
    - Grid budget for the new Qty (Nos) columns: Sales Order Item drops Delivery Date
      from the row view (it is copied from the order's own Delivery Date and still
      editable in the row), Delivery Note Item drops UOM, Sales Invoice Item narrows
      Item from 4 columns to 3. Production Plan Item's Item Name leaves the row view
      too, but it is this app's own custom field, so that is set on the field itself
      in production_management/custom/production_plan_item.json.
    """
    for args in [
        {"doctype": "Production Plan Item", "fieldname": "planned_qty", "property": "label",
         "value": "Planned Qty (Kg)", "property_type": "Data"},
        {"doctype": "Production Plan Item", "fieldname": "planned_qty", "property": "read_only_depends_on",
         "value": "eval:doc.custom_drawing", "property_type": "Code"},
        {"doctype": "Delivery Note Item", "fieldname": "qty", "property": "read_only_depends_on",
         "value": "eval:doc.custom_sec_uom", "property_type": "Code"},
        {"doctype": "Sales Invoice Item", "fieldname": "qty", "property": "read_only_depends_on",
         "value": "eval:doc.custom_sec_uom", "property_type": "Code"},
        {"doctype": "Item", "fieldname": "opening_stock", "property": "hidden",
         "value": 1, "property_type": "Check"},
        {"doctype": "Sales Order Item", "fieldname": "delivery_date", "property": "in_list_view",
         "value": 0, "property_type": "Check"},
        {"doctype": "Delivery Note Item", "fieldname": "uom", "property": "in_list_view",
         "value": 0, "property_type": "Check"},
        {"doctype": "Sales Invoice Item", "fieldname": "item_code", "property": "columns",
         "value": 3, "property_type": "Int"},
    ]:
        frappe.make_property_setter(args)
    frappe.db.commit()


def set_fg_settings_defaults():
    """Give the two Finished Goods settings their defaults on a site that has never set them.

    A Single field added after the Settings were first saved has no row in
    tabSingles, and Frappe does not create one from the field's default:
    get_single_value then reads 0, and the Settings form shows 0 -- so saving the
    form for any other reason would quietly switch "Edit FG Stock Kg" off. Writing
    the default once, only where there is no row yet, makes the stored value, the
    form and the code agree. A value somebody has set is never touched.
    """
    for fieldname, value in (
        ("edit_fg_stock_kg", 1),
        ("fg_weight_difference_warning_percent", 5),
    ):
        if not frappe.db.sql(
            "SELECT 1 FROM `tabSingles` WHERE doctype=%s AND field=%s",
            ("Manufyxinvenza Settings", fieldname),
        ):
            frappe.db.set_single_value(
                "Manufyxinvenza Settings", fieldname, value, update_modified=False
            )
    frappe.db.commit()
