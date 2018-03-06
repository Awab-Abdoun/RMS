
frappe.provide("rms.utils");

rms.utils.add_item = function(frm) {
	if(frm.is_new()) {
		var prev_route = frappe.get_prev_route();
		if(prev_route[1]==='Item' && !(frm.doc.items && frm.doc.items.length)) {
			// add row
			var item = frm.add_child('items');
			frm.refresh_field('items');

			// set item
			frappe.model.set_value(item.doctype, item.name, 'item_code', prev_route[2]);
		}
	}
}

rms.utils.get_contact_details = function(frm) {
	if(frm.updating_party_details) return;

	if(frm.doc["contact_person"]) {
		frappe.call({
			method: "frappe.contacts.doctype.contact.contact.get_contact_details",
			args: {contact: frm.doc.contact_person },
			callback: function(r) {
				if(r.message)
					frm.set_value(r.message);
			}
		})
	}
}

rms.utils.validate_mandatory = function(frm, label, value, trigger_on) {
	if(!value) {
		frm.doc[trigger_on] = "";
		refresh_field(trigger_on);
		frappe.msgprint(__("Please enter {0} first", [label]));
		return false;
	}
	return true;
}

rms.utils.get_shipping_address = function(frm, callback){
	frappe.call({
		method: "frappe.contacts.doctype.address.address.get_shipping_address",
		args: {company: frm.doc.company},
		callback: function(r){
			if(r.message){
				frm.set_value("shipping_address", r.message[0]) //Address title or name
				frm.set_value("shipping_address_display", r.message[1]) //Address to be displayed on the page
			}

			if(callback){
				return callback();
			}
		}
	});
}