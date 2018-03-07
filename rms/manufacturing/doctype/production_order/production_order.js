// Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
// For license information, please see license.txt

{% include 'rms/public/js/utils.js' %};
frappe.provide("rms.manufacturing");

frappe.ui.form.on('Production Order', {
	setup: function(frm) {
		frm.custom_make_buttons = {
			'Stock Entry': 'Make Stock Entry',
		}

		// Set query for BOM
		frm.set_query("bom_no", function() {
			if (frm.doc.production_item) {
				return{
					query: "rms.controllers.queries.bom",
					filters: {item: cstr(frm.doc.production_item)}
				}
			} else msgprint(__("Please enter Production Item first"));
		});

		// Set query for FG Item
		frm.set_query("production_item", function() {
			return {
				query: "rms.controllers.queries.item_query",
				filters:{
					'is_stock_item': 1,
				}
			}
		});

		// Set query for FG Item
		frm.set_query("project", function() {
			return{
				filters:[
					['Project', 'status', 'not in', 'Completed, Cancelled']
				]
			}
		});
	},

	onload: function(frm) {
		if (!frm.doc.status)
			frm.doc.status = 'Draft';

		frm.add_fetch("project", "project");

		if(frm.doc.__islocal) {
			frm.set_value({
				"actual_start_date": "",
				"actual_end_date": ""
			});
			rms.production_order.set_default_warehouse(frm);
		}

		// formatter for production order operation
		frm.set_indicator_formatter('operation',
			function(doc) { return (frm.doc.qty==doc.completed_qty) ? "green" : "orange" });
	},

	refresh: function(frm) {
		rms.toggle_naming_series();
		rms.production_order.set_custom_buttons(frm);
		frm.set_intro("");

		if (frm.doc.docstatus === 0 && !frm.doc.__islocal) {
			frm.set_intro(__("Submit this Production Order for further processing."));
		}

		if (frm.doc.docstatus===1) {
			frm.trigger('show_progress');
		}

	},

	show_progress: function(frm) {
		var bars = [];
		var message = '';
		var added_min = false;

		// produced qty
		var title = __('{0} items produced', [frm.doc.produced_qty]);
		bars.push({
			'title': title,
			'width': (frm.doc.produced_qty / frm.doc.qty * 100) + '%',
			'progress_class': 'progress-bar-success'
		});
		if (bars[0].width == '0%') {
			bars[0].width = '0.5%';
			added_min = 0.5;
		}
		message = title;

		// pending qty
		if(!frm.doc.skip_transfer){
			var pending_complete = frm.doc.material_transferred_for_manufacturing - frm.doc.produced_qty;
			if(pending_complete) {
				var title = __('{0} items in progress', [pending_complete]);
				bars.push({
					'title': title,
					'width': ((pending_complete / frm.doc.qty * 100) - added_min)  + '%',
					'progress_class': 'progress-bar-warning'
				})
				message = message + '. ' + title;
			}
		}
		frm.dashboard.add_progress(__('Status'), bars, message);
	},

	production_item: function(frm) {
		if (frm.doc.production_item) {
			frappe.call({
				method: "rms.manufacturing.doctype.production_order.production_order.get_item_details",
				args: {
					item: frm.doc.production_item,
					project: frm.doc.project
				},
				callback: function(r) {
					if(r.message) {
						rms.in_production_item_onchange = true;
						$.each(["description", "project", "bom_no"], function(i, field) {
							frm.set_value(field, r.message[field]);
						});

						if(r.message["set_scrap_wh_mandatory"]){
							frm.toggle_reqd("scrap_warehouse", true);
						}
						rms.in_production_item_onchange = false;
					}
				}
			});
		}
	},

	project: function(frm) {
		if(!rms.in_production_item_onchange) {
			frm.trigger("production_item");
		}
	},

	bom_no: function(frm) {
		return frm.call({
			doc: frm.doc,
			method: "get_items_and_operations_from_bom",
			callback: function(r) {
				if(r.message["set_scrap_wh_mandatory"]){
					frm.toggle_reqd("scrap_warehouse", true);
				}
			}
		});
	},

	use_multi_level_bom: function(frm) {
		if(frm.doc.bom_no) {
			frm.trigger("bom_no");
		}
	},

	qty: function(frm) {
		frm.trigger('bom_no');
	},

	before_submit: function(frm) {
		frm.toggle_reqd(["fg_warehouse", "wip_warehouse"], true);
		frm.fields_dict.required_items.grid.toggle_reqd("source_warehouse", true);
	},

});

frappe.ui.form.on("Production Order Item", {
	source_warehouse: function(frm, cdt, cdn) {
		var row = locals[cdt][cdn];
		if(!row.item_code) {
			frappe.throw(__("Please set the Item Code first"));
		} else if(row.source_warehouse) {
			frappe.call({
				"method": "rms.stock.utils.get_latest_stock_qty",
				args: {
					item_code: row.item_code,
					warehouse: row.source_warehouse
				},
				callback: function (r) {
					frappe.model.set_value(row.doctype, row.name,
						"available_qty_at_source_warehouse", r.message);
				}
			})
		}
	}
})

frappe.ui.form.on("Production Order Operation", {
	workstation: function(frm, cdt, cdn) {
		var d = locals[cdt][cdn];
		if (d.workstation) {
			frappe.call({
				"method": "frappe.client.get",
				args: {
					doctype: "Workstation",
					name: d.workstation
				},
				callback: function (data) {
					frappe.model.set_value(d.doctype, d.name);
				}
			})
		}
	},
});

rms.production_order = {
	set_custom_buttons: function(frm) {
		var doc = frm.doc;
		if (doc.docstatus === 1) {
			if (doc.status != 'Stopped' && doc.status != 'Completed') {
				frm.add_custom_button(__('Stop'), function() {
					rms.production_order.stop_production_order(frm, "Stopped");
				}, __("Status"));
			} else if (doc.status == 'Stopped') {
				frm.add_custom_button(__('Re-open'), function() {
					rms.production_order.stop_production_order(frm, "Resumed");
				}, __("Status"));
			}

			if(!frm.doc.skip_transfer){
				if ((flt(doc.material_transferred_for_manufacturing) < flt(doc.qty))
					&& frm.doc.status != 'Stopped') {
					frm.has_start_btn = true;
					var start_btn = frm.add_custom_button(__('Start'), function() {
						rms.production_order.make_se(frm, 'Material Transfer for Manufacture');
					});
					start_btn.addClass('btn-primary');
				}
			}

			if(!frm.doc.skip_transfer){
				if ((flt(doc.produced_qty) < flt(doc.material_transferred_for_manufacturing))
						&& frm.doc.status != 'Stopped') {
					frm.has_finish_btn = true;
					var finish_btn = frm.add_custom_button(__('Finish'), function() {
						rms.production_order.make_se(frm, 'Manufacture');
					});

					if(doc.material_transferred_for_manufacturing==doc.qty) {
						// all materials transferred for manufacturing, make this primary
						finish_btn.addClass('btn-primary');
					}
				}
			} else {
				if ((flt(doc.produced_qty) < flt(doc.qty)) && frm.doc.status != 'Stopped') {
					frm.has_finish_btn = true;
					var finish_btn = frm.add_custom_button(__('Finish'), function() {
						rms.production_order.make_se(frm, 'Manufacture');
					});
					finish_btn.addClass('btn-primary');
				}
			}
		}

	},

	set_default_warehouse: function(frm) {
		if (!(frm.doc.wip_warehouse || frm.doc.fg_warehouse)) {
			frappe.call({
				method: "rms.manufacturing.doctype.production_order.production_order.get_default_warehouse",
				callback: function(r) {
					if(!r.exe) {
						frm.set_value("wip_warehouse", r.message.wip_warehouse);
						frm.set_value("fg_warehouse", r.message.fg_warehouse)
					}
				}
			});
		}
	},

	make_se: function(frm, purpose) {
		if(!frm.doc.skip_transfer){
			var max = (purpose === "Manufacture") ?
				flt(frm.doc.material_transferred_for_manufacturing) - flt(frm.doc.produced_qty) :
				flt(frm.doc.qty) - flt(frm.doc.material_transferred_for_manufacturing);
		} else {
			var max = flt(frm.doc.qty) - flt(frm.doc.produced_qty);
		}

		max = flt(max, precision("qty"));
		frappe.prompt({fieldtype:"Float", label: __("Qty for {0}", [purpose]), fieldname:"qty",
			description: __("Max: {0}", [max]), 'default': max },
			function(data) {
				if(data.qty > max) {
					frappe.msgprint(__("Quantity must not be more than {0}", [max]));
					return;
				}
				frappe.call({
					method:"rms.manufacturing.doctype.production_order.production_order.make_stock_entry",
					args: {
						"production_order_id": frm.doc.name,
						"purpose": purpose,
						"qty": data.qty
					},
					callback: function(r) {
						var doclist = frappe.model.sync(r.message);
						frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
					}
				});
			}, __("Select Quantity"), __("Make"));
	},

	stop_production_order: function(frm, status) {
		frappe.call({
			method: "rms.manufacturing.doctype.production_order.production_order.stop_unstop",
			args: {
				production_order: frm.doc.name,
				status: status
			},
			callback: function(r) {
				if(r.message) {
					frm.set_value("status", r.message);
					frm.reload_doc();
				}
			}
		})
	}
}
