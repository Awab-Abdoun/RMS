// Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
// For license information, please see license.txt

frappe.provide("rms.bom");

frappe.ui.form.on('BOM', {
	setup: function(frm) {
		frm.add_fetch("item", "description", "description");
		frm.add_fetch("item", "image", "image");
		frm.add_fetch("item", "item_name", "item_name");

		// );

		frm.set_query("item", function() {
			return {
				query: "rms.controllers.queries.item_query"
			};
		});

		frm.set_query("project", function() {
			return{
				filters:[
					['Project', 'status', 'not in', 'Completed, Cancelled']
				]
			};
		});

		frm.set_query("item_code", "items", function() {
			return {
				query: "rms.controllers.queries.item_query",
				filters: [["Item", "name", "!=", cur_frm.doc.item]]
			};
		});

		frm.set_query("bom_no", "items", function(doc, cdt, cdn) {
			var d = locals[cdt][cdn];
			return {
				filters: {
					'item': d.item_code,
					'is_active': 1,
					'docstatus': 1
				}
			};
		});
	},

	onload_post_render: function(frm) {
		frm.get_field("items").grid.set_multiple_add("item_code", "qty");
	},

	refresh: function(frm) {
		frm.toggle_enable("item", frm.doc.__islocal);
		toggle_operations(frm);

		if (!frm.doc.__islocal && frm.doc.docstatus<2) {
			frm.add_custom_button(__("Browse BOM"), function() {
				frappe.route_options = {
					"bom": frm.doc.name
				};
				frappe.set_route("Tree", "BOM");
			});
		}

		if(frm.doc.docstatus!=0) {
			frm.add_custom_button(__("Duplicate"), function() {
				frm.copy_doc();
			});
		}
	},

});

// rms.bom.BomController = rms.TransactionController.extend({
// 	item_code: function(doc, cdt, cdn){
// 		var scrap_items = false;
// 		var child = locals[cdt][cdn];
// 		if(child.doctype == 'BOM Scrap Item') {
// 			scrap_items = true;
// 		}

// 		if (child.bom_no) {
// 			child.bom_no = '';
// 		}

// 		get_bom_material_detail(doc, cdt, cdn, scrap_items);
// 	},
// });

// $.extend(cur_frm.cscript, new rms.bom.BomController({frm: cur_frm}));

cur_frm.cscript.bom_no	= function(doc, cdt, cdn) {
	get_bom_material_detail(doc, cdt, cdn, false);
};

cur_frm.cscript.is_default = function(doc) {
	if (doc.is_default) cur_frm.set_value("is_active", 1);
};

var get_bom_material_detail= function(doc, cdt, cdn, scrap_items) {
	var d = locals[cdt][cdn];
	if (d.item_code) {
		return frappe.call({
			doc: doc,
			method: "get_bom_material_detail",
			args: {
				'item_code': d.item_code,
				'bom_no': d.bom_no != null ? d.bom_no: '',
				"scrap_items": scrap_items,
				'qty': d.qty
			},
			callback: function(r) {
				d = locals[cdt][cdn];
				$.extend(d, r.message);
				refresh_field("items");
				refresh_field("scrap_items");
			},
			freeze: true
		});
	}
};

frappe.ui.form.on("BOM Operation", "operation", function(frm, cdt, cdn) {
	var d = locals[cdt][cdn];

	if(!d.operation) return;

	frappe.call({
		"method": "frappe.client.get",
		args: {
			doctype: "Operation",
			name: d.operation
		},
		callback: function (data) {
			if(data.message.description) {
				frappe.model.set_value(d.doctype, d.name, "description", data.message.description);
			}
			if(data.message.workstation) {
				frappe.model.set_value(d.doctype, d.name, "workstation", data.message.workstation);
			}
		}
	});
});

frappe.ui.form.on("BOM Operation", "workstation", function(frm, cdt, cdn) {
	var d = locals[cdt][cdn];

	frappe.call({
		"method": "frappe.client.get",
		args: {
			doctype: "Workstation",
			name: d.workstation
		},
	});
});

frappe.ui.form.on("BOM Item", "qty", function(frm, cdt, cdn) {
	var d = locals[cdt][cdn];
	d.stock_qty = d.qty;
	refresh_field("stock_qty", d.name, d.parentfield);
});

var toggle_operations = function(frm) {
	frm.toggle_display("operations_section", cint(frm.doc.with_operations) == 1);
};

frappe.ui.form.on("BOM", "with_operations", function(frm) {
	if(!cint(frm.doc.with_operations)) {
		frm.set_value("operations", []);
	}
	toggle_operations(frm);
});

cur_frm.cscript.image = function() {
	refresh_field("image_view");
};
