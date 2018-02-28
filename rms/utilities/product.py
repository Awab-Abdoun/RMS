
from __future__ import unicode_literals

import frappe
from frappe.utils import cint, fmt_money, flt

def get_qty_in_stock(item_code, item_warehouse_field):
	in_stock, stock_qty = 0, ''
	template_item_code = frappe.db.get_value("Item", item_code)

	warehouse = frappe.db.get_value("Item", item_code, item_warehouse_field)
	if not warehouse and template_item_code and template_item_code != item_code:
		warehouse = frappe.db.get_value("Item", template_item_code, item_warehouse_field)

	if warehouse:
		stock_qty = frappe.db.sql("""select GREATEST(actual_qty - reserved_qty, 0) from tabBin where
			item_code=%s and warehouse=%s""", (item_code, warehouse))
		if stock_qty:
			in_stock = stock_qty[0][0] > 0 and 1 or 0

	return frappe._dict({"in_stock": in_stock, "stock_qty": stock_qty})
