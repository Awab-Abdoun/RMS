# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import urllib
from frappe.utils import nowdate, cint, cstr
from frappe.utils.nestedset import NestedSet

class ItemGroup(NestedSet):
	nsm_parent_field = 'parent_item_group'

	def autoname(self):
		self.name = self.item_group_name

	def validate(self):
		super(ItemGroup, self).validate()
		self.make_route()

	def on_update(self):
		NestedSet.on_update(self)
		invalidate_cache_for(self)
		self.validate_name_with_item()
		self.validate_one_root()

	def make_route(self):
		'''Make website route'''
		if not self.route:
			self.route = ''
			if self.parent_item_group:
				parent_item_group = frappe.get_doc('Item Group', self.parent_item_group)

				# make parent route only if not root
				if parent_item_group.parent_item_group and parent_item_group.route:
					self.route = parent_item_group.route + '/'

			self.route += self.scrub(self.item_group_name)

			return self.route

	def on_trash(self):
		NestedSet.on_trash(self)

	def validate_name_with_item(self):
		if frappe.db.exists("Item", self.name):
			frappe.throw(frappe._("An item exists with same name ({0}), please change the item group name or rename the item").format(self.name), frappe.NameError)

def invalidate_cache_for(doc, item_group=None):
	if not item_group:
		item_group = doc.name

	for d in get_parent_item_groups(item_group):
		item_group_name = frappe.db.get_value("Item Group", d.get('name'))
		if item_group_name:
			clear_cache(frappe.db.get_value('Item Group', item_group_name, 'route'))
