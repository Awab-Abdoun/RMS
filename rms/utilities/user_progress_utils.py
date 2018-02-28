
import frappe, rms

import json
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def create_letterhead(args_data):
	args = json.loads(args_data)
	letterhead = args.get("letterhead")
	if letterhead:
		try:
			frappe.get_doc({
					"doctype":"Letter Head",
					"content":"""<div><img src="{0}" style='max-width: 100%%;'><br></div>""".format(letterhead),
					"letter_head_name": _("Standard"),
					"is_default": 1
			}).insert()
		except frappe.NameError:
			pass

def create_contact(contact, party_type, party):
	"""Create contact based on given contact name"""
	contact = contact	.split(" ")

	contact = frappe.get_doc({
		"doctype":"Contact",
		"first_name":contact[0],
		"last_name": len(contact) > 1 and contact[1] or ""
	})
	contact.append('links', dict(link_doctype=party_type, link_name=party))
	contact.insert()

@frappe.whitelist()
def create_items(args_data):
	args = json.loads(args_data)
	defaults = frappe.defaults.get_defaults()
	for i in xrange(1,4):
		item = args.get("item_" + str(i))
		if item:
			default_warehouse = ""
			default_warehouse = frappe.db.get_value("Warehouse", filters={
				"warehouse_name": _("Finished Goods")
			})

			try:
				frappe.get_doc({
					"doctype":"Item",
					"item_code": item,
					"item_name": item,
					"description": item,
					"is_stock_item": 1,
					"item_group": "Products",
					"default_warehouse": default_warehouse
				}).insert()

			except frappe.NameError:
				pass
