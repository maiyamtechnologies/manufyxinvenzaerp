const FORMULA_GROUPS = ["Structurals", "Plates"];

// Must match fg_stock.FG_PARENT_ITEM_GROUP -- the server refuses an FG item set up
// any other way (item.validate_fg_configuration), so what this file fills in here
// is the same set-up that validation demands, not a separate opinion about it.
const FG_GROUP = "Finished Goods";

const TRANSACTION_LOCKED_FIELDS = [
	"custom_parent_item_group",
	"stock_uom",
	"custom_unit_weight",
	"custom_secondary_uom",
	"custom_batch_prefix",
];

// Locked once SET (item.py _LOCK_ONCE_SET, which is what actually refuses the save):
// a blank one can still be filled in on an Item already in use, a set one cannot change.
const LOCK_ONCE_SET_FIELDS = ["custom_material_spec", "custom_material_grade"];

function set_calculation_type(frm) {
	const group = frm.doc.custom_parent_item_group;
	if (FORMULA_GROUPS.includes(group)) {
		frm.set_value("custom_item_calculation_type", "Formula Weight Calculation");
	} else if (group) {
		frm.set_value("custom_item_calculation_type", "Normal Weight Calculation");
	}
}

function set_default_uoms(frm) {
	const group = frm.doc.custom_parent_item_group;
	if (FORMULA_GROUPS.includes(group) || group === FG_GROUP) {
		// Finished goods are stocked in Kg and counted in Nos, same as the formula
		// groups: every FG figure downstream is Kg on the ledger with the piece
		// count beside it. Filled in on selection rather than left for the user to
		// guess, because the only other way to learn it was to save and be refused.
		frm.set_value("stock_uom", "Kg");
		frm.set_value("custom_secondary_uom", "Nos");
	} else if (group === "Nuts and Bolts") {
		frm.set_value("stock_uom", "Nos");
		frm.set_value("custom_secondary_uom", "Kg");
	}
}

function apply_batch_ui(frm) {
	const has_batch = !!frm.doc.has_batch_no;
	const is_formula_group = FORMULA_GROUPS.includes(frm.doc.custom_parent_item_group);
	const is_fg = frm.doc.custom_parent_item_group === FG_GROUP;

	// Never shown for finished goods: their batches are named and filled by
	// fg_stock.get_or_create_fg_batch (FG-<Sales Order>-<DUNO>), so there is no
	// abbreviation to pick. Cleared as well as hidden -- a value left behind from
	// a group the item used to be in would still be submitted, and the server
	// refuses a finished-goods item whose abbreviation is not blank
	// (validate_fg_configuration), which from behind a hidden field reads as a
	// refusal with no cause on screen.
	frm.toggle_display("custom_batch_prefix", has_batch && !is_fg);
	if (is_fg && frm.doc.custom_batch_prefix) {
		frm.set_value("custom_batch_prefix", "");
	}

	if (has_batch && is_formula_group) {
		frm.set_value("create_new_batch", 1);
		frm.set_df_property("create_new_batch", "read_only", 1);
		frm.toggle_display("batch_number_series", false);
	} else {
		frm.set_df_property("create_new_batch", "read_only", 0);
		frm.toggle_display("batch_number_series", true);
	}
}

function lock_transacted_fields(frm) {
	if (frm.is_new()) return;
	frappe.call({
		method: "manufyxinvenzaerp.item_management.item.has_item_transactions",
		args: { item_code: frm.doc.name },
		callback(r) {
			if (r.message) {
				TRANSACTION_LOCKED_FIELDS.forEach(field => {
					frm.set_df_property(field, "read_only", 1);
				});
				LOCK_ONCE_SET_FIELDS.forEach(field => {
					if (frm.doc[field]) frm.set_df_property(field, "read_only", 1);
				});
			}
		},
	});
}

function lock_item_group_filter(frm) {
	const field = frm.fields_dict["item_group"];

	// Null out df.link_filters so Frappe's apply_link_field_filters()
	// never fires and never resets our get_query when the dropdown opens
	field.df.link_filters = null;

	// Use a getter so ERPNext's set_query("item_group", ...) calls in
	// refresh handlers are silently swallowed and cannot override us
	Object.defineProperty(field, "get_query", {
		get() {
			return function () {
				const filters = [["Item Group", "is_group", "=", 0]];
				if (frm.doc.custom_parent_item_group) {
					filters.push([
						"Item Group",
						"parent_item_group",
						"=",
						frm.doc.custom_parent_item_group,
					]);
				}
				return { filters };
			};
		},
		set() {},
		configurable: true,
		enumerable: true,
	});
}

function make_unit_weight_mand_based_on_item_group(frm) {
	const reqd = ["Nuts and Bolts", "Plates", "Structurals"].includes(frm.doc.custom_parent_item_group)
		? 1
		: 0;
	frm.set_df_property("custom_unit_weight", "reqd", reqd);
}

frappe.ui.form.on("Item", {
	refresh(frm) {
		frm.set_df_property("custom_item_calculation_type", "read_only", 1);
		frm.set_query("custom_parent_item_group", () => ({ filters: { is_group: 1 } }));
		lock_item_group_filter(frm);
		apply_batch_ui(frm);
		make_unit_weight_mand_based_on_item_group(frm);
		lock_transacted_fields(frm);
	},

	custom_parent_item_group(frm) {
		set_calculation_type(frm);
		set_default_uoms(frm);
		frm.set_value("item_group", "");
		apply_batch_ui(frm);
		make_unit_weight_mand_based_on_item_group(frm);
	},

	has_batch_no(frm) {
		apply_batch_ui(frm);
	},
});
