# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, rms
import frappe.defaults
from frappe import msgprint, _
from frappe.utils import cstr, flt, cint
from rms.stock.stock_ledger import update_entries_after
from rms.controllers.stock_controller import StockController
from rms.stock.utils import get_stock_balance

class EmptyStockReconciliationItemsError(frappe.ValidationError): pass

class StockReconciliation(StockController):
	def __init__(self, *args, **kwargs):
		super(StockReconciliation, self).__init__(*args, **kwargs)
		self.head_row = ["Item Code", "Warehouse", "Quantity"]

	def validate(self):
		self.validate_posting_time()
		self.remove_items_with_no_change()
		self.validate_data()
		self.set_total_qty_and_amount()

	def on_submit(self):
		self.update_stock_ledger()

	def on_cancel(self):
		self.delete_and_repost_sle()

	def remove_items_with_no_change(self):
		"""Remove items if qty or rate is not changed"""
		def _changed(item):
			qty = get_stock_balance(item.item_code, item.warehouse,
					self.posting_date, self.posting_time)
			if (item.qty==None or item.qty==qty):
				return False
			else:
				# set default as current rates
				if item.qty==None:
					item.qty = qty

				item.current_qty = qty
				return True

		items = filter(lambda d: _changed(d), self.items)

		if not items:
			frappe.throw(_("None of the items have any change in quantity."),
				EmptyStockReconciliationItemsError)

		elif len(items) != len(self.items):
			self.items = items
			for i, item in enumerate(self.items):
				item.idx = i + 1
			frappe.msgprint(_("Removed items with no change in quantity."))

	def validate_data(self):
		def _get_msg(row_num, msg):
			return _("Row # {0}: ").format(row_num+1) + msg

		self.validation_messages = []
		item_warehouse_combinations = []

		for row_num, row in enumerate(self.items):
			# find duplicates
			if [row.item_code, row.warehouse] in item_warehouse_combinations:
				self.validation_messages.append(_get_msg(row_num, _("Duplicate entry")))
			else:
				item_warehouse_combinations.append([row.item_code, row.warehouse])

			self.validate_item(row.item_code, row_num+1)

			# validate warehouse
			if not frappe.db.get_value("Warehouse", row.warehouse):
				self.validation_messages.append(_get_msg(row_num, _("Warehouse not found in the system")))

			# if both not specified
			if row.qty in ["", None]:
				self.validation_messages.append(_get_msg(row_num,
					_("Please specify the Quantity")))

			# do not allow negative quantity
			if flt(row.qty) < 0:
				self.validation_messages.append(_get_msg(row_num,
					_("Negative Quantity is not allowed")))

		# throw all validation messages
		if self.validation_messages:
			for msg in self.validation_messages:
				msgprint(msg)

			raise frappe.ValidationError(self.validation_messages)

	def validate_item(self, item_code, row_num):
		from rms.stock.doctype.item.item import validate_end_of_life, \
			validate_is_stock_item, validate_cancelled_item

		# using try except to catch all validation msgs and display together

		try:
			item = frappe.get_doc("Item", item_code)

			# end of life and stock item
			validate_end_of_life(item_code, item.end_of_life, item.disabled, verbose=0)
			validate_is_stock_item(item_code, item.is_stock_item, verbose=0)

			# docstatus should be < 2
			validate_cancelled_item(item_code, item.docstatus, verbose=0)

		except Exception as e:
			self.validation_messages.append(_("Row # ") + ("%d: " % (row_num)) + cstr(e))

	def update_stock_ledger(self):
		"""	find difference between current and expected entries
			and create stock ledger entries based on the difference"""
		from rms.stock.stock_ledger import get_previous_sle

		for row in self.items:
			previous_sle = get_previous_sle({
				"item_code": row.item_code,
				"warehouse": row.warehouse,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time
			})
			if previous_sle:
				if row.qty in ("", None):
					row.qty = previous_sle.get("qty_after_transaction", 0)

			if ((previous_sle and row.qty == previous_sle.get("qty_after_transaction"))
				or (not previous_sle and not row.qty)):
					continue

			self.insert_entries(row)

	def insert_entries(self, row):
		"""Insert Stock Ledger Entries"""
		args = frappe._dict({
			"doctype": "Stock Ledger Entry",
			"item_code": row.item_code,
			"warehouse": row.warehouse,
			"posting_date": self.posting_date,
			"posting_time": self.posting_time,
			"voucher_type": self.doctype,
			"voucher_no": self.name,
			"is_cancelled": "No",
			"qty_after_transaction": row.qty,
		})
		self.make_sl_entries([args])

	def delete_and_repost_sle(self):
		"""	Delete Stock Ledger Entries related to this voucher
			and repost future Stock Ledger Entries"""

		existing_entries = frappe.db.sql("""select distinct item_code, warehouse
			from `tabStock Ledger Entry` where voucher_type=%s and voucher_no=%s""",
			(self.doctype, self.name), as_dict=1)

		# delete entries
		frappe.db.sql("""delete from `tabStock Ledger Entry`
			where voucher_type=%s and voucher_no=%s""", (self.doctype, self.name))

		# repost future entries for selected item_code, warehouse
		for entries in existing_entries:
			update_entries_after({
				"item_code": entries.item_code,
				"warehouse": entries.warehouse,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time
			})

	def set_total_qty_and_amount(self):
		for d in self.get("items"):
			d.amount = flt(d.qty)
			d.current_amount = flt(d.current_qty)
			d.quantity_difference = flt(d.qty) - flt(d.current_qty)

	def get_items_for(self, warehouse):
		self.items = []
		for item in get_items(warehouse, self.posting_date, self.posting_time):
			self.append("items", item)

	def submit(self):
		if len(self.items) > 100:
			self.queue_action('submit')
		else:
			self._submit()

	def cancel(self):
		if len(self.items) > 100:
			self.queue_action('cancel')
		else:
			self._cancel()

@frappe.whitelist()
def get_items(warehouse, posting_date, posting_time):
	items = frappe.get_list("Bin", fields=["item_code"], filters={"warehouse": warehouse}, as_list=1)

	items += frappe.get_list("Item", fields=["name"], filters= {"is_stock_item": 1, "disabled": 0, "default_warehouse": warehouse},
			as_list=1)

	res = []
	for item in set(items):
		stock_bal = get_stock_balance(item[0], warehouse, posting_date, posting_time,
			with_valuation_rate=True)

		if frappe.db.get_value("Item",item[0],"disabled") == 0:

			res.append({
				"item_code": item[0],
				"warehouse": warehouse,
				"qty": stock_bal[0],
				"item_name": frappe.db.get_value('Item', item[0], 'item_name'),
				"current_qty": stock_bal[0]
			})

	return res

@frappe.whitelist()
def get_stock_balance_for(item_code, warehouse, posting_date, posting_time):
	frappe.has_permission("Stock Reconciliation", "write", throw = True)

	qty, rate = get_stock_balance(item_code, warehouse,
		posting_date, posting_time, with_valuation_rate=True)

	return {
		'qty': qty
	}
