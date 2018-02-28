# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt, getdate, add_days, formatdate
from frappe.model.document import Document
from datetime import date

exclude_from_linked_with = True

class StockLedgerEntry(Document):
	def validate(self):
		self.flags.ignore_submit_comment = True
		self.validate_mandatory()
		self.validate_item()
		self.scrub_posting_time()
		self.block_transactions_against_group_warehouse()

	def on_submit(self):
		self.actual_amt_check()

	#check for item quantity available in stock
	def actual_amt_check(self):
		batch_bal_after_transaction = flt(frappe.db.sql("""select sum(actual_qty)
			from `tabStock Ledger Entry`
			where warehouse=%s and item_code=%s""", 
			(self.warehouse, self.item_code))[0][0])
    
		if batch_bal_after_transaction < 0:
			frappe.throw(_("Stock balance will become negative {0} for Item {1} at Warehouse {2}")
				.format(batch_bal_after_transaction, self.item_code, self.warehouse))

	def validate_mandatory(self):
		mandatory = ['warehouse','voucher_type','voucher_no']
		for k in mandatory:
			if not self.get(k):
				frappe.throw(_("{0} is required").format(self.meta.get_label(k)))

		if self.voucher_type != "Stock Reconciliation" and not self.actual_qty:
			frappe.throw(_("Actual Qty is mandatory"))

	def validate_item(self):
		item_det = frappe.db.sql("""select name, docstatus,
			is_stock_item
			from tabItem where name=%s""", self.item_code, as_dict=True)

		if not item_det:
			frappe.throw(_("Item {0} not found").format(self.item_code))

		item_det = item_det[0]

		if item_det.is_stock_item != 1:
			frappe.throw(_("Item {0} must be a stock Item").format(self.item_code))

	def scrub_posting_time(self):
		if not self.posting_time or self.posting_time == '00:0':
			self.posting_time = '00:00'

	def block_transactions_against_group_warehouse(self):
		from rms.stock.utils import is_group_warehouse
		is_group_warehouse(self.warehouse)

def on_doctype_update():
	if not frappe.db.sql("""show index from `tabStock Ledger Entry`
		where Key_name="posting_sort_index" """):
		frappe.db.commit()
		frappe.db.sql("""alter table `tabStock Ledger Entry`
			add index posting_sort_index(posting_date, posting_time, name)""")

	frappe.db.add_index("Stock Ledger Entry", ["voucher_no", "voucher_type"])
