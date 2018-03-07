
from __future__ import unicode_literals
import frappe
from frappe import _
import json
from frappe.utils import flt, cstr, nowdate, nowtime


def get_stock_value_on(warehouse=None, posting_date=None, item_code=None):
	if not posting_date: posting_date = nowdate()

	values, condition = [posting_date], ""

	if warehouse:

		lft, rgt, is_group = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt", "is_group"])

		if is_group:
			values.extend([lft, rgt])
			condition += "and exists (\
				select name from `tabWarehouse` wh where wh.name = sle.warehouse\
				and wh.lft >= %s and wh.rgt <= %s)"

		else:
			values.append(warehouse)
			condition += " AND warehouse = %s"

	if item_code:
		values.append(item_code)
		condition.append(" AND item_code = %s")

	stock_ledger_entries = frappe.db.sql("""
		SELECT item_code, name, warehouse
		FROM `tabStock Ledger Entry` sle
		WHERE posting_date <= %s {0}
		ORDER BY timestamp(posting_date, posting_time) DESC, name DESC
	""".format(condition), values, as_dict=1)

	sle_map = {}
	for sle in stock_ledger_entries:
		if not sle_map.has_key((sle.item_code, sle.warehouse)):
			sle_map[(sle.item_code, sle.warehouse)] = flt(sle.stock_value)

	return sum(sle_map.values())

@frappe.whitelist()
def get_stock_balance(item_code, warehouse, posting_date=None, posting_time=None):
	"""Returns stock balance quantity at given warehouse on given posting date or current date.

	If `with_valuation_rate` is True, will return tuple (qty, rate)"""

	from rms.stock.stock_ledger import get_previous_sle

	if not posting_date: posting_date = nowdate()
	if not posting_time: posting_time = nowtime()

	last_entry = get_previous_sle({
		"item_code": item_code,
		"warehouse":warehouse,
		"posting_date": posting_date,
		"posting_time": posting_time })

	return last_entry.qty_after_transaction if last_entry else 0.0

@frappe.whitelist()
def get_latest_stock_qty(item_code, warehouse=None):
	values, condition = [item_code], ""
	if warehouse:
		lft, rgt, is_group = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt", "is_group"])

		if is_group:
			values.extend([lft, rgt])
			condition += "and exists (\
				select name from `tabWarehouse` wh where wh.name = tabBin.warehouse\
				and wh.lft >= %s and wh.rgt <= %s)"

		else:
			values.append(warehouse)
			condition += " AND warehouse = %s"

	actual_qty = frappe.db.sql("""select sum(actual_qty) from tabBin
		where item_code=%s {0}""".format(condition), values)[0][0]

	return actual_qty


def get_latest_stock_balance():
	bin_map = {}
	for d in frappe.db.sql("""SELECT item_code, warehouse as stock_value
		FROM tabBin""", as_dict=1):
			bin_map.setdefault(d.warehouse, {}).setdefault(d.item_code)

	return bin_map

def get_bin(item_code, warehouse):
	bin = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse})
	if not bin:
		bin_obj = frappe.get_doc({
			"doctype": "Bin",
			"item_code": item_code,
			"warehouse": warehouse,
		})
		bin_obj.flags.ignore_permissions = 1
		bin_obj.insert()
	else:
		bin_obj = frappe.get_doc('Bin', bin)
	bin_obj.flags.ignore_permissions = True
	return bin_obj

def update_bin(args):
	is_stock_item = frappe.db.get_value('Item', args.get("item_code"), 'is_stock_item')
	if is_stock_item:
		bin = get_bin(args.get("item_code"), args.get("warehouse"))
		bin.update_stock(args)
		return bin
	else:
		frappe.msgprint(_("Item {0} ignored since it is not a stock item").format(args.get("item_code")))

def get_valuation_method(item_code):
	"""get valuation method from item or default"""
	val_method = frappe.db.get_value('Item', item_code, 'valuation_method')
	if not val_method:
		val_method = frappe.db.get_value(None, "valuation_method") or "FIFO"
	return val_method

def is_group_warehouse(warehouse):
	if frappe.db.get_value("Warehouse", warehouse, "is_group"):
		frappe.throw(_("Group node warehouse is not allowed to select for transactions"))
