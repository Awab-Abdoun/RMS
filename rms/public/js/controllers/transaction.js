
{% include 'rms/public/js/controllers/stock_controller.js' %};
{% include 'rms/public/js/utils/party.js' %};
{% include 'rms/public/js/queries.js' %};
{% include 'rms/public/js/utils.js' %};

frappe.provide("rms.stock");

rms.TransactionController = rms.stock.StockController.extend({

	item_code: function(doc, cdt, cdn, from_barcode) {
		var me = this;
		var item = frappe.get_doc(cdt, cdn);

		if(item.item_code) {
				return this.frm.call({
					method: "rms.stock.get_item_details.get_item_details",
					child: item,
					args: {
						args: {
						item_code: item.item_code,
						warehouse: item.warehouse,
						doctype: me.frm.doc.doctype,
						name: me.frm.doc.name,
						project: item.project || me.frm.doc.project,
						qty: item.qty || 1,
						stock_qty: item.stock_qty,
					}
				},
			});
		}
	}

});
