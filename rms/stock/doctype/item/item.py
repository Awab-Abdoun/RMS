# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import rms
import json
import itertools
from frappe import msgprint, _
from frappe.utils import (cstr, flt, cint, getdate, now_datetime, formatdate,
	strip, get_timestamp, random_string)
from rms.setup.doctype.item_group.item_group import invalidate_cache_for
from frappe.utils.html_utils import clean_html
from frappe.model.document import Document

class DuplicateReorderRows(frappe.ValidationError): pass
class StockExistsForTemplate(frappe.ValidationError): pass

class Item(Document):
	def onload(self):
		super(Item, self).onload()

		self.set_onload('stock_exists', self.stock_ledger_created())

	def autoname(self):
		if frappe.db.get_default("item_naming_by")=="Naming Series":
			if self.variant_of:
				if not self.item_code:
					template_item_name = frappe.db.get_value("Item", self.variant_of, "item_name")
					self.item_code = make_variant_item_code(self.variant_of, template_item_name, self)
			else:
				from frappe.model.naming import make_autoname
				self.item_code = make_autoname(self.naming_series+'.#####')
		elif not self.item_code:
			msgprint(_("Item Code is mandatory because Item is not automatically numbered"), raise_exception=1)

		self.item_code = strip(self.item_code)
		self.name = self.item_code

	def before_insert(self):
		if not self.description:
			self.description = self.item_name

	def after_insert(self):
		'''set opening stock and item price'''

		if self.opening_stock:
			self.set_opening_stock()

	def validate(self):
		self.get_doc_before_save()

		super(Item, self).validate()

		if not self.item_name:
			self.item_name = self.item_code

		if not self.description:
			self.description = self.item_name

		self.validate_description()
		self.check_for_active_boms()
		self.update_bom_item_desc()

		if not self.get("__islocal"):
			self.old_item_group = frappe.db.get_value(self.doctype, self.name, "item_group")

	def on_update(self):
		invalidate_cache_for_item(self)

	def validate_description(self):
		'''Clean HTML description if set'''
		if cint(frappe.db.get_single_value('Stock Settings', 'clean_description_html')):
			self.description = clean_html(self.description)

	def set_opening_stock(self):
		'''set opening stock'''
		if not self.is_stock_item:
			return

		from rms.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		# default warehouse, or Stores
		default_warehouse = (self.default_warehouse
			or frappe.db.get_single_value('Stock Settings', 'default_warehouse')
			or frappe.db.get_value('Warehouse', {'warehouse_name': _('Stores')}))

		if default_warehouse:
			stock_entry = make_stock_entry(item_code=self.name, target=default_warehouse,
				qty=self.opening_stock)

			stock_entry.add_comment("Comment", _("Opening Stock"))

	def check_for_active_boms(self):
		if self.default_bom:
			bom_item = frappe.db.get_value("BOM", self.default_bom, "item")
			if bom_item not in (self.name, self.variant_of):
				frappe.throw(_("Default BOM ({0}) must be active for this item or its template").format(bom_item))

	def stock_ledger_created(self):
		if not hasattr(self, '_stock_ledger_created'):
			self._stock_ledger_created = len(frappe.db.sql("""select name from `tabStock Ledger Entry`
				where item_code = %s limit 1""", self.name))
		return self._stock_ledger_created

	def on_trash(self):
		super(Item, self).on_trash()
		frappe.db.sql("""delete from tabBin where item_code=%s""", self.item_code)

	def before_rename(self, old_name, new_name, merge=False):
		if self.item_name==old_name:
			frappe.db.set_value("Item", old_name, "item_name", new_name)

		if merge:
			# Validate properties before merging
			if not frappe.db.exists("Item", new_name):
				frappe.throw(_("Item {0} does not exist").format(new_name))

			field_list = ["is_stock_item"]
			new_properties = [cstr(d) for d in frappe.db.get_value("Item", new_name, field_list)]
			if new_properties != [cstr(self.get(fld)) for fld in field_list]:
				frappe.throw(_("To merge, following properties must be same for both items")
					+ ": \n" + ", ".join([self.meta.get_label(fld) for fld in field_list]))

	def after_rename(self, old_name, new_name, merge):
		if self.route:
			invalidate_cache_for_item(self)
			clear_cache(self.route)

		frappe.db.set_value("Item", new_name, "item_code", new_name)

		if merge:
			self.recalculate_bin_qty(new_name)

	def recalculate_bin_qty(self, new_name):
		from rms.stock.stock_balance import repost_stock
		frappe.db.auto_commit_on_many_writes = 1
		# existing_allow_negative_stock = frappe.db.get_value("Stock Settings", None, "allow_negative_stock")
		# frappe.db.set_value("Stock Settings", None, "allow_negative_stock", 1)

		repost_stock_for_warehouses = frappe.db.sql_list("""select distinct warehouse
			from tabBin where item_code=%s""", new_name)

		# Delete all existing bins to avoid duplicate bins for the same item and warehouse
		frappe.db.sql("delete from `tabBin` where item_code=%s", new_name)

		for warehouse in repost_stock_for_warehouses:
			repost_stock(new_name, warehouse)

		# frappe.db.set_value("Stock Settings", None, "allow_negative_stock", existing_allow_negative_stock)
		frappe.db.auto_commit_on_many_writes = 0

	def update_bom_item_desc(self):
		if self.is_new(): return

		if self.db_get('description') != self.description:
			frappe.db.sql("""
				update `tabBOM`
				set description = %s
				where item = %s and docstatus < 2
			""", (self.description, self.name))

			frappe.db.sql("""
				update `tabBOM Item`
				set description = %s
				where item_code = %s and docstatus < 2
			""", (self.description, self.name))

			frappe.db.sql("""
				update `tabBOM Explosion Item`
				set description = %s
				where item_code = %s and docstatus < 2
			""", (self.description, self.name))

def get_timeline_data(doctype, name):
	'''returns timeline data based on stock ledger entry'''
	out = {}
	items = dict(frappe.db.sql('''select posting_date, count(*)
		from `tabStock Ledger Entry` where item_code=%s
			and posting_date > date_sub(curdate(), interval 1 year)
			group by posting_date''', name))

	for date, count in items.iteritems():
		timestamp = get_timestamp(date)
		out.update({ timestamp: count })

	return out

def validate_end_of_life(item_code, end_of_life=None, disabled=None, verbose=1):
	if (not end_of_life) or (disabled is None):
		end_of_life, disabled = frappe.db.get_value("Item", item_code, ["end_of_life", "disabled"])

	if end_of_life and end_of_life!="0000-00-00" and getdate(end_of_life) <= now_datetime().date():
		msg = _("Item {0} has reached its end of life on {1}").format(item_code, formatdate(end_of_life))
		_msgprint(msg, verbose)

	if disabled:
		_msgprint(_("Item {0} is disabled").format(item_code), verbose)

def validate_is_stock_item(item_code, is_stock_item=None, verbose=1):
	if not is_stock_item:
		is_stock_item = frappe.db.get_value("Item", item_code, "is_stock_item")

	if is_stock_item != 1:
		msg = _("Item {0} is not a stock Item").format(item_code)

		_msgprint(msg, verbose)

def validate_cancelled_item(item_code, docstatus=None, verbose=1):
	if docstatus is None:
		docstatus = frappe.db.get_value("Item", item_code, "docstatus")

	if docstatus == 2:
		msg = _("Item {0} is cancelled").format(item_code)
		_msgprint(msg, verbose)

def invalidate_cache_for_item(doc):
	invalidate_cache_for(doc, doc.item_group)

def _msgprint(msg, verbose):
	if verbose:
		msgprint(msg, raise_exception=True)
	else:
		raise frappe.ValidationError(msg)
