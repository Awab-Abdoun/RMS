// Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
// For license information, please see license.txt

frappe.ui.form.on("Warehouse", {
	refresh: function(frm) {
		frm.toggle_display('warehouse_name', frm.doc.__islocal);

		frm.add_custom_button(__("Stock Balance"), function() {
			frappe.set_route("query-report", "Stock Balance", {"warehouse": frm.doc.name});
		});

		if (cint(frm.doc.is_group) == 1) {
			frm.add_custom_button(__('Group to Non-Group'),
				function() { convert_to_group_or_ledger(frm); }, 'fa fa-retweet', 'btn-default')
		} else if (cint(frm.doc.is_group) == 0) {
			if(frm.doc.__onload && frm.doc.__onload.account) {
				frm.add_custom_button(__("General Ledger"), function() {
					frappe.route_options = {

					}
					frappe.set_route("query-report", "General Ledger");
				});
			}

			frm.add_custom_button(__('Non-Group to Group'),
				function() { convert_to_group_or_ledger(frm); }, 'fa fa-retweet', 'btn-default')
		}

		frm.toggle_enable(['is_group'], false);

		frm.fields_dict['parent_warehouse'].get_query = function(doc) {
			return {
				filters: {
					"is_group": 1,
				}
			}
		}
	}
});

function convert_to_group_or_ledger(frm){
	frappe.call({
		method:"rms.stock.doctype.warehouse.warehouse.convert_to_group_or_ledger",
		args: {
			docname: frm.doc.name,
			is_group: frm.doc.is_group
		},
		callback: function(){
			frm.refresh();
		}

	})
}
