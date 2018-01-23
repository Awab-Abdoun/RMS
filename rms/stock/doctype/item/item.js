// Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
// For license information, please see license.txt

frappe.provide("rms.item");

frappe.ui.form.on('Item', {
	setup: function(frm) {
		frm.add_fetch('attribute', 'numeric_values', 'numeric_values');
		frm.add_fetch('attribute', 'from_range', 'from_range');
		frm.add_fetch('attribute', 'to_range', 'to_range');
		frm.add_fetch('attribute', 'increment', 'increment');
	},
	onload: function(frm) {
		rms.item.setup_queries(frm);
		if (frm.doc.variant_of){
			frm.fields_dict["attributes"].grid.set_column_disp("attribute_value", true);
		}

	},

	refresh: function(frm) {
		if(frm.doc.is_stock_item) {
			frm.add_custom_button(__("Balance"), function() {
				frappe.route_options = {
					"item_code": frm.doc.name
				}
				frappe.set_route("query-report", "Stock Balance");
			}, __("View"));
			frm.add_custom_button(__("Ledger"), function() {
				frappe.route_options = {
					"item_code": frm.doc.name
				}
				frappe.set_route("query-report", "Stock Ledger");
			}, __("View"));
			frm.add_custom_button(__("Projected"), function() {
				frappe.route_options = {
					"item_code": frm.doc.name
				}
				frappe.set_route("query-report", "Stock Projected Qty");
			}, __("View"));
		}

		if(!frm.doc.is_fixed_asset) {
			rms.item.make_dashboard(frm);
		}

		// clear intro
		frm.set_intro();

		if (frappe.defaults.get_default("item_naming_by")!="Naming Series") {
			frm.toggle_display("naming_series", false);
		} else {
			rms.toggle_naming_series();
		}

		frm.add_custom_button(__('Duplicate'), function() {
			var new_item = frappe.model.copy_doc(frm.doc);
			if(new_item.item_name===new_item.item_code) {
				new_item.item_name = null;
			}
			if(new_item.description===new_item.description) {
				new_item.description = null;
			}
			frappe.set_route('Form', 'Item', new_item.name);
		});
	},

	validate: function(frm){
		rms.item.weight_to_validate(frm);
	},

	image: function() {
		refresh_field("image_view");
	},

	page_name: frappe.utils.warn_page_name_change,

	item_code: function(frm) {
		if(!frm.doc.item_name)
			frm.set_value("item_name", frm.doc.item_code);
		if(!frm.doc.description)
			frm.set_value("description", frm.doc.item_code);
	},

	is_stock_item: function(frm) {
		if(!frm.doc.is_stock_item) {

		}
	},

	copy_from_item_group: function(frm) {
		return frm.call({
			doc: frm.doc,
			method: "copy_specification_from_item_group"
		});
	},

});

frappe.ui.form.on('Item Reorder', {
	reorder_levels_add: function(frm, cdt, cdn) {
		var row = frappe.get_doc(cdt, cdn);
		var type = frm.doc.default_material_request_type
		row.material_request_type = (type == 'Material Transfer')? 'Transfer' : type;
	}
})

$.extend(rms.item, {
	setup_queries: function(frm) {

		frm.fields_dict['item_group'].get_query = function(doc, cdt, cdn) {
			return {
				filters: [
					['Item Group', 'docstatus', '!=', 2]
				]
			}
		}

		frm.fields_dict['default_warehouse'].get_query = function(doc) {
			return {
				filters: { "is_group": 0 }
			}
		}

		frm.fields_dict.reorder_levels.grid.get_field("warehouse_group").get_query = function(doc, cdt, cdn) {
			return {
				filters: { "is_group": 1 }
			}
		}

		frm.fields_dict.reorder_levels.grid.get_field("warehouse").get_query = function(doc, cdt, cdn) {
			var d = locals[cdt][cdn];

			var filters = {
				"is_group": 0
			}

			if (d.parent_warehouse) {
				filters.extend({"parent_warehouse": d.warehouse_group})
			}

			return {
				filters: filters
			}
		}

	},

	make_dashboard: function(frm) {
		if(frm.doc.__islocal)
			return;

		// Show Stock Levels only if is_stock_item
		if (frm.doc.is_stock_item) {
			frappe.require('assets/js/item-dashboard.min.js', function() {
				var section = frm.dashboard.add_section('<h5 style="margin-top: 0px;">\
					<a href="#stock-balance">' + __("Stock Levels") + '</a></h5>');
				rms.item.item_dashboard = new rms.stock.ItemDashboard({
					parent: section,
					item_code: frm.doc.name
				});
				rms.item.item_dashboard.refresh();
			});
		}
	},

	weight_to_validate: function(frm){
		if((frm.doc.nett_weight || frm.doc.gross_weight)) {
			frappe.msgprint(__('Weight is mentioned'));
			frappe.validated = 0;
		}
	}
});
