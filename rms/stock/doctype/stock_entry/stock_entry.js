// Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
// For license information, please see license.txt

frappe.provide("rms.stock");
frappe.provide("rms.stock_entry");

frappe.ui.form.on('Stock Entry', {
	setup: function(frm) {
		frm.set_query('production_order', function() {
			return {
				filters: [
					['Production Order', 'docstatus', '=', 1],
					['Production Order', 'qty', '>','`tabProduction Order`.produced_qty']
				]
			}
		});

	},
	refresh: function(frm) {
		if(!frm.doc.docstatus) {
			frm.add_custom_button(__('Make Material Request'), function() {
				frappe.model.with_doctype('Material Request', function() {
					var mr = frappe.model.get_new_doc('Material Request');
					var items = frm.get_field('items').grid.get_selected_children();
					if(!items.length) {
						items = frm.doc.items;
					}
					items.forEach(function(item) {
						var mr_item = frappe.model.add_child(mr, 'items');
						mr_item.item_code = item.item_code;
						mr_item.item_name = item.item_name;
						mr_item.item_group = item.item_group;
						mr_item.description = item.description;
						mr_item.image = item.image;
						mr_item.qty = item.qty;
						mr_item.warehouse = item.s_warehouse;
						mr_item.required_date = frappe.datetime.nowdate();
					});
					frappe.set_route('Form', 'Material Request', mr.name);
				});
			});
		}
	},

	purpose: function(frm) {
		frm.fields_dict.items.grid.refresh();
		frm.cscript.toggle_related_fields(frm.doc);
	},

	get_warehouse_details: function(frm, cdt, cdn, callback) {
		var child = locals[cdt][cdn];
		if(!child.bom_no) {
			frappe.call({
				method: "rms.stock.doctype.stock_entry.stock_entry.get_warehouse_details",
				args: {
					"args": {
						'item_code': child.item_code,
						'warehouse': cstr(child.s_warehouse) || cstr(child.t_warehouse),
						'transfer_qty': child.transfer_qty,
						'qty': child.s_warehouse ? -1* child.transfer_qty : child.transfer_qty,
						'posting_date': frm.doc.posting_date,
						'posting_time': frm.doc.posting_time
					}
				},
				callback: function(r) {
					if (!r.exc) {
						$.extend(child, r.message);

					}
        
					if (callback) {
						callback();
					}
				}
			});
		}
	},
})

frappe.ui.form.on('Stock Entry Detail', {
	s_warehouse: function(frm, cdt, cdn) {
		frm.events.get_warehouse_details(frm, cdt, cdn);
	},

	t_warehouse: function(frm, cdt, cdn) {
		frm.events.get_warehouse_details(frm, cdt, cdn);
	},

	item_code: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		if(d.item_code) {
			var args = {
				'item_code'			: d.item_code,
				'warehouse'			: cstr(d.s_warehouse) || cstr(d.t_warehouse),
				'transfer_qty'		: d.transfer_qty,
				'bom_no'			: d.bom_no,
				'qty'				: d.qty
			};
			return frappe.call({
				doc: frm.doc,
				method: "get_item_details",
				args: args,
				callback: function(r) {
					if(r.message) {
						var d = locals[cdt][cdn];
						$.each(r.message, function(k, v) {
							d[k] = v;
						});
						refresh_field("items");
					}
				}
			});
		}
	},

});

// rms.stock.StockEntry = rms.stock.StockController.extend({
// 	setup: function() {
// 		var me = this;
//
// 		this.setup_posting_date_time_check();
//
// 		this.frm.fields_dict.bom_no.get_query = function() {
// 			return {
// 				filters:{
// 					"docstatus": 1,
// 					"is_active": 1
// 				}
// 			};
// 		};
//
// 		this.frm.fields_dict.items.grid.get_field('item_code').get_query = function() {
// 			return rms.queries.item({is_stock_item: 1});
// 		};
//
// 		// this.frm.set_query("purchase_order", function() {
// 		// 	return {
// 		// 		"filters": {
// 		// 			"docstatus": 1,
// 		// 			"is_subcontracted": "Yes"
// 		// 		}
// 		// 	};
// 		// });
//
// 		this.frm.set_indicator_formatter('item_code',
// 			function(doc) { return (doc.qty<=doc.actual_qty) ? "green" : "orange" })
//
// 		// this.frm.add_fetch("purchase_order");
// 	},
//
// 	refresh: function() {
// 		var me = this;
// 		rms.toggle_naming_series();
// 		this.toggle_related_fields(this.frm.doc);
// 		this.toggle_enable_bom();
// 		this.show_stock_ledger();
// 		if (this.frm.doc.docstatus===1) {
// 			this.show_general_ledger();
// 		}
// 		rms.utils.add_item(this.frm);
// 	},
//
// 	on_submit: function() {
// 		this.clean_up();
// 	},
//
// 	after_cancel: function() {
// 		this.clean_up();
// 	},
//
// 	clean_up: function() {
// 		// Clear Production Order record from locals, because it is updated via Stock Entry
// 		if(this.frm.doc.production_order &&
// 				in_list(["Manufacture", "Material Transfer for Manufacture"], this.frm.doc.purpose)) {
// 			frappe.model.remove_from_locals("Production Order",
// 				this.frm.doc.production_order);
// 		}
// 	},
//
// 	get_items: function() {
// 		var me = this;
// 		if(!this.frm.doc.fg_completed_qty || !this.frm.doc.bom_no)
// 			frappe.throw(__("BOM and Manufacturing Quantity are required"));
//
// 		if(this.frm.doc.production_order || this.frm.doc.bom_no) {
// 			// if production order / bom is mentioned, get items
// 			return this.frm.call({
// 				doc: me.frm.doc,
// 				method: "get_items",
// 				callback: function(r) {
// 					if(!r.exc) refresh_field("items");
// 				}
// 			});
// 		}
// 	},
//
// 	production_order: function() {
// 		var me = this;
// 		this.toggle_enable_bom();
// 		if(!me.frm.doc.production_order) {
// 			return;
// 		}
//
// 		return frappe.call({
// 			method: "rms.stock.doctype.stock_entry.stock_entry.get_production_order_details",
// 			args: {
// 				production_order: me.frm.doc.production_order
// 			},
// 			callback: function(r) {
// 				if (!r.exc) {
// 					$.each(["from_bom", "bom_no", "fg_completed_qty", "use_multi_level_bom"], function(i, field) {
// 						me.frm.set_value(field, r.message[field]);
// 					})
//
// 					if (me.frm.doc.purpose == "Material Transfer for Manufacture" && !me.frm.doc.to_warehouse)
// 						me.frm.set_value("to_warehouse", r.message["wip_warehouse"]);
//
//
// 					if (me.frm.doc.purpose == "Manufacture") {
// 						if (!me.frm.doc.from_warehouse) me.frm.set_value("from_warehouse", r.message["wip_warehouse"]);
// 						if (!me.frm.doc.to_warehouse) me.frm.set_value("to_warehouse", r.message["fg_warehouse"]);
// 					}
// 					me.get_items()
// 				}
// 			}
// 		});
// 	},
//
// 	toggle_enable_bom: function() {
// 		this.frm.toggle_enable("bom_no", !!!this.frm.doc.production_order);
// 	},
//
// 	items_add: function(doc, cdt, cdn) {
// 		var row = frappe.get_doc(cdt, cdn);
// 		this.frm.script_manager.copy_from_first_row("items", row);
//
// 		if(!row.s_warehouse) row.s_warehouse = this.frm.doc.from_warehouse;
// 		if(!row.t_warehouse) row.t_warehouse = this.frm.doc.to_warehouse;
// 	},
//
// 	source_mandatory: ["Material Issue", "Material Transfer", "Subcontract", "Material Transfer for Manufacture"],
// 	target_mandatory: ["Material Receipt", "Material Transfer", "Subcontract", "Material Transfer for Manufacture"],
//
// 	from_warehouse: function(doc) {
// 		var me = this;
// 		this.set_warehouse_if_different("s_warehouse", doc.from_warehouse, function(row) {
// 			return me.source_mandatory.indexOf(me.frm.doc.purpose)!==-1;
// 		});
// 	},
//
// 	to_warehouse: function(doc) {
// 		var me = this;
// 		this.set_warehouse_if_different("t_warehouse", doc.to_warehouse, function(row) {
// 			return me.target_mandatory.indexOf(me.frm.doc.purpose)!==-1;
// 		});
// 	},
//
// 	set_warehouse_if_different: function(fieldname, value, condition) {
// 		var changed = false;
// 		for (var i=0, l=(this.frm.doc.items || []).length; i<l; i++) {
// 			var row = this.frm.doc.items[i];
// 			if (row[fieldname] != value) {
// 				if (condition && !condition(row)) {
// 					continue;
// 				}
//
// 				frappe.model.set_value(row.doctype, row.name, fieldname, value, "Link");
// 				changed = true;
// 			}
// 		}
// 		refresh_field("items");
// 	},
//
// 	toggle_related_fields: function(doc) {
// 		this.frm.toggle_enable("from_warehouse", doc.purpose!='Material Receipt');
// 		this.frm.toggle_enable("to_warehouse", doc.purpose!='Material Issue');
//
// 		this.frm.fields_dict["items"].grid.set_column_disp("s_warehouse", doc.purpose!='Material Receipt');
// 		this.frm.fields_dict["items"].grid.set_column_disp("t_warehouse", doc.purpose!='Material Issue');
//
// 		this.frm.cscript.toggle_enable_bom();
//
// 		// if (doc.purpose == 'Subcontract') {
// 		// 	doc.customer = doc.customer_name = doc.customer_address =
// 		// 		doc.delivery_note_no = doc.sales_invoice_no = null;
// 		// } else {
// 		// 	doc.customer = doc.customer_name = doc.customer_address =
// 		// 		doc.delivery_note_no = doc.sales_invoice_no = doc.supplier =
// 		// 		doc.supplier_name = doc.supplier_address = doc.purchase_receipt_no =
// 		// 		doc.address_display = null;
// 		// }
//
// 		if(doc.purpose == "Material Receipt") {
// 			this.frm.set_value("from_bom", 0);
// 		}
//
// 	},
//
// });
//
// $.extend(cur_frm.cscript, new rms.stock.StockEntry({frm: cur_frm}));
