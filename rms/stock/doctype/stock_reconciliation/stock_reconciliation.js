// Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
// For license information, please see license.txt

frappe.provide("rms.stock");

frappe.ui.form.on('Stock Reconciliation', {
	onload: function(frm) {
		frm.add_fetch("item_code", "item_name", "item_name");

		// end of life
		frm.set_query("item_code", "items", function(doc, cdt, cdn) {
			return {
				query: "rms.controllers.queries.item_query",
				filters:{
					"is_stock_item": 1
				}
			}
		});
	},

	refresh: function(frm) {
		if(frm.doc.docstatus < 1) {
			frm.add_custom_button(__("Items"), function() {
				frm.events.get_items(frm);
			});
		}
	},

	get_items: function(frm) {
		frappe.prompt({label:"Warehouse", fieldtype:"Link", options:"Warehouse", reqd: 1},
			function(data) {
				frappe.call({
					method:"rms.stock.doctype.stock_reconciliation.stock_reconciliation.get_items",
					args: {
						warehouse: data.warehouse,
						posting_date: frm.doc.posting_date,
						posting_time: frm.doc.posting_time
					},
					callback: function(r) {
						var items = [];
						frm.clear_table("items");
						for(var i=0; i< r.message.length; i++) {
							var d = frm.add_child("items");
							$.extend(d, r.message[i]);
							if(!d.qty) d.qty = null;
						}
						frm.refresh_field("items");
					}
				});
			}
		, __("Get Items"), __("Update"));
	},

	set_valuation_rate_and_qty: function(frm, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);
		if(d.item_code && d.warehouse) {
			frappe.call({
				method: "rms.stock.doctype.stock_reconciliation.stock_reconciliation.get_stock_balance_for",
				args: {
					item_code: d.item_code,
					warehouse: d.warehouse,
					posting_date: frm.doc.posting_date,
					posting_time: frm.doc.posting_time
				},
				callback: function(r) {
					frappe.model.set_value(cdt, cdn, "qty", r.message.qty);
					frappe.model.set_value(cdt, cdn, "current_qty", r.message.qty);
				}
			});
		}
	},

	set_amount_quantity: function(doc, cdt, cdn) {
		var d = frappe.model.get_doc(cdt, cdn);
		if (d.qty) {
			frappe.model.set_value(cdt, cdn, "amount", flt(d.qty));
			frappe.model.set_value(cdt, cdn, "quantity_difference", flt(d.qty) - flt(d.current_qty));
		}
	}
});

frappe.ui.form.on("Stock Reconciliation Item", {
	warehouse: function(frm, cdt, cdn) {
		frm.events.set_valuation_rate_and_qty(frm, cdt, cdn);
	},
	item_code: function(frm, cdt, cdn) {
		frm.events.set_valuation_rate_and_qty(frm, cdt, cdn);
	},
	qty: function(frm, cdt, cdn) {
		frm.events.set_amount_quantity(frm, cdt, cdn);
	}

});

// rms.stock.StockReconciliation = rms.stock.StockController.extend({
// 	setup: function() {
// 		var me = this;
//
// 		this.setup_posting_date_time_check();
// 	},
//
// 	refresh: function() {
// 		if(this.frm.doc.docstatus==1) {
// 			this.show_stock_ledger();
// 		}
// 	},
//
// });
//
// cur_frm.cscript = new rms.stock.StockReconciliation({frm: cur_frm});
