
from __future__ import unicode_literals
import frappe
from frappe import _, throw
from frappe.utils import flt, cint, add_days, cstr
import json
from frappe.model.meta import get_field_precision


@frappe.whitelist()
def get_item_details(args):
	"""
		args = {
			"item_code": "",
			"warehouse": None,
			"doctype": "",
			"name": "",
			"is_subcontracted": "Yes" / "No",
			"project": ""
		}
	"""
	args = process_args(args)
	item_doc = frappe.get_doc("Item", args.item_code)
	item = item_doc

	validate_item_details(args, item)

	out = get_basic_details(args, item)

	if out.get("warehouse"):
		out.update(get_bin_details(args.item_code, out.warehouse))

	# update args with out, if key or value not exists
	for key, value in out.iteritems():
		if args.get(key) is None:
			args[key] = value

	if args.transaction_date and item.lead_time_days:
		out.schedule_date = out.lead_time_date = add_days(args.transaction_date,
			item.lead_time_days)

	if args.get("is_subcontracted") == "Yes":
		out.bom = args.get('bom') or get_default_bom(args.item_code)

	get_gross_profit(out)

	return out

def process_args(args):
	if isinstance(args, basestring):
		args = json.loads(args)

	args = frappe._dict(args)

	set_transaction_type(args)
	return args


@frappe.whitelist()
def get_item_code():

	return item_code


def validate_item_details(args, item):

	from rms.stock.doctype.item.item import validate_end_of_life
	validate_end_of_life(item.name, item.end_of_life, item.disabled)

def get_basic_details(args, item):
	"""
	:param args: {
			"item_code": "",
			"warehouse": None,
			"doctype": "",
			"name": "",
			"is_subcontracted": "Yes" / "No",
			"project": "",
			warehouse: "",
			update_stock: "",
			company: "",
			project: "",
			qty: "",
			stock_qty: ""
		}
	:param item: `item_code` of Item object
	:return: frappe._dict
	"""

	if not item:
		item = frappe.get_doc("Item", args.get("item_code"))

	warehouse = item.default_warehouse or args.warehouse

	material_request_type = ''
	if args.get('doctype') == "Material Request":
		material_request_type = frappe.db.get_value('Material Request',
			args.get('name'), 'material_request_type')

	out = frappe._dict({
		"item_code": item.name,
		"item_name": item.item_name,
		"description": cstr(item.description).strip(),
		"image": cstr(item.image).strip(),
		"warehouse": warehouse,
		"qty": args.qty or 1.0,
		"stock_qty": args.qty or 1.0
	})

	for fieldname in ("item_name", "item_group"):
		out[fieldname] = item.get(fieldname)

	return out

@frappe.whitelist()
def get_projected_qty(item_code, warehouse):
	return {"projected_qty": frappe.db.get_value("Bin",
		{"item_code": item_code, "warehouse": warehouse}, "projected_qty")}

@frappe.whitelist()
def get_bin_details(item_code, warehouse):
	return frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse},
			["projected_qty", "actual_qty"], as_dict=True) \
			or {"projected_qty": 0, "actual_qty": 0}

@frappe.whitelist()
def get_bin_details_and_serial_nos(item_code, warehouse, stock_qty=None):
	bin_details_and_serial_nos = {}
	bin_details_and_serial_nos.update(get_bin_details(item_code, warehouse))
	if stock_qty > 0:
		bin_details_and_serial_nos.update(get_serial_no_details(item_code, warehouse, stock_qty))
	return bin_details_and_serial_nos

@frappe.whitelist()
def get_default_bom(item_code=None):
	if item_code:
		bom = frappe.db.get_value("BOM", {"docstatus": 1, "is_default": 1, "is_active": 1, "item": item_code})
		if bom:
			return bom
