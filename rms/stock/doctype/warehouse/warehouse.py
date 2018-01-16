# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, rms
from frappe.utils import cint, validate_email_add
from frappe import throw, _
from frappe.utils.nestedset import NestedSet
from rms.stock import get_warehouse_account

class Warehouse(NestedSet):
	nsm_parent_field = 'parent_warehouse'

	def autoname(self):
		self.name = self.warehouse_name

	def validate(self):
		if self.email_id:
			validate_email_add(self.email_id, True)

	def on_update(self):
		self.update_nsm_model()

	def update_nsm_model(self):
		frappe.utils.nestedset.update_nsm(self)

	def on_trash(self):
		# delete bin
		bins = frappe.db.sql("select * from `tabBin` where warehouse = %s",
			self.name, as_dict=1)
		for d in bins:
			if d['actual_qty'] or d['reserved_qty'] or d['ordered_qty'] or \
					d['indented_qty'] or d['projected_qty'] or d['planned_qty']:
				throw(_("Warehouse {0} can not be deleted as quantity exists for Item {1}").format(self.name, d['item_code']))
			else:
				frappe.db.sql("delete from `tabBin` where name = %s", d['name'])

		if self.check_if_sle_exists():
			throw(_("Warehouse can not be deleted as stock ledger entry exists for this warehouse."))

		if self.check_if_child_exists():
			throw(_("Child warehouse exists for this warehouse. You can not delete this warehouse."))

		self.update_nsm_model()

	def check_if_sle_exists(self):
		return frappe.db.sql("""select name from `tabStock Ledger Entry`
			where warehouse = %s limit 1""", self.name)

	def check_if_child_exists(self):
		return frappe.db.sql("""select name from `tabWarehouse`
			where parent_warehouse = %s limit 1""", self.name)

	def before_rename(self, old_name, new_name, merge=False):
		super(Warehouse, self).before_rename(old_name, new_name, merge)

		if merge:
			if not frappe.db.exists("Warehouse", new_warehouse):
				frappe.throw(_("Warehouse {0} does not exist").format(new_warehouse))

		return new_warehouse

	def after_rename(self, old_name, new_name, merge=False):
		super(Warehouse, self).after_rename(old_name, new_name, merge)

		new_warehouse_name = new_name
		self.db_set("warehouse_name", new_warehouse_name)

		if merge:
			self.recalculate_bin_qty(new_name)

	def recalculate_bin_qty(self, new_name):
		from rms.stock.stock_balance import repost_stock
		frappe.db.auto_commit_on_many_writes = 1
		existing_allow_negative_stock = frappe.db.get_value("Stock Settings", None, "allow_negative_stock")
		frappe.db.set_value("Stock Settings", None, "allow_negative_stock", 1)

		repost_stock_for_items = frappe.db.sql_list("""select distinct item_code
			from tabBin where warehouse=%s""", new_name)

		# Delete all existing bins to avoid duplicate bins for the same item and warehouse
		frappe.db.sql("delete from `tabBin` where warehouse=%s", new_name)

		for item_code in repost_stock_for_items:
			repost_stock(item_code, new_name)

		frappe.db.set_value("Stock Settings", None, "allow_negative_stock", existing_allow_negative_stock)
		frappe.db.auto_commit_on_many_writes = 0

	def convert_to_group_or_ledger(self):
		if self.is_group:
			self.convert_to_ledger()
		else:
			self.convert_to_group()

	def convert_to_ledger(self):
		if self.check_if_child_exists():
			frappe.throw(_("Warehouses with child nodes cannot be converted to ledger"))
		elif self.check_if_sle_exists():
			throw(_("Warehouses with existing transaction can not be converted to ledger."))
		else:
			self.is_group = 0
			self.save()
			return 1

	def convert_to_group(self):
		if self.check_if_sle_exists():
			throw(_("Warehouses with existing transaction can not be converted to group."))
		else:
			self.is_group = 1
			self.save()
			return 1

@frappe.whitelist()
def get_children(doctype, parent=None, is_root=False):
	from rms.stock.utils import get_stock_value_on

	if is_root:
		parent = ""

	warehouses = frappe.db.sql("""select name as value,
		is_group as expandable
		from `tabWarehouse`
		where docstatus < 2
		and ifnull(`parent_warehouse`,'') = %s
		order by name""", (parent), as_dict=1)

	# return warehouses
	for wh in warehouses:
		wh["balance"] = get_stock_value_on(warehouse=wh.value)
	return warehouses

@frappe.whitelist()
def add_node():
	from frappe.desk.treeview import make_tree_args
	args = make_tree_args(**frappe.form_dict)

	if cint(args.is_root):
		args.parent_warehouse = None

	frappe.get_doc(args).insert()

@frappe.whitelist()
def convert_to_group_or_ledger():
	args = frappe.form_dict
	return frappe.get_doc("Warehouse", args.docname).convert_to_group_or_ledger()