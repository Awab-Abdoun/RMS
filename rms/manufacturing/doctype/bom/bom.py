# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, rms
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt
from frappe import _

from operator import itemgetter

form_grid_templates = {
	"items": "templates/form_grid/item_grid.html"
}

class BOM(Document):
	def autoname(self):
		names = frappe.db.sql_list("""select name from `tabBOM` where item=%s""", self.item)

		if names:
			# name can be BOM/ITEM/001, BOM/ITEM/001-1, BOM-ITEM-001, BOM-ITEM-001-1

			# split by item
			names = [name.split(self.item)[-1][1:] for name in names]

			# split by (-) if cancelled
			names = [cint(name.split('-')[-1]) for name in names]

			idx = max(names) + 1
		else:
			idx = 1

		self.name = 'BOM-' + self.item + ('-%.3i' % idx)

	def validate(self):
		# self.route = frappe.scrub(self.name).replace('_', '-')
		self.clear_operations()
		self.validate_main_item()
		self.update_stock_qty()
		self.set_bom_material_details()
		self.validate_materials()
		self.validate_operations()

	def get_context(self, context):
		context.parents = [{'name': 'boms', 'title': _('All BOMs') }]

	def on_update(self):
		self.check_recursion()
		self.update_stock_qty()
		self.update_exploded_items()

	def on_submit(self):
		self.manage_default_bom()

	def on_cancel(self):
		frappe.db.set(self, "is_active", 0)
		frappe.db.set(self, "is_default", 0)

		# check if used in any other bom
		self.validate_bom_links()
		self.manage_default_bom()

	def on_update_after_submit(self):
		self.validate_bom_links()
		self.manage_default_bom()

	def get_item_det(self, item_code):
		item = frappe.db.sql("""select name, item_name, docstatus, description, image,
			default_bom
			from `tabItem` where name=%s""", item_code, as_dict = 1)

		if not item:
			frappe.throw(_("Item: {0} does not exist in the system").format(item_code))

		return item

	def validate_rm_item(self, item):
		if (item[0]['name'] in [it.item_code for it in self.items]) and item[0]['name'] == self.item:
			frappe.throw(_("BOM #{0}: Raw material cannot be same as main Item").format(self.name))

	def set_bom_material_details(self):
		for item in self.get("items"):
			ret = self.get_bom_material_detail({
				"item_code": item.item_code,
				"item_name": item.item_name,
				"bom_no": item.bom_no,
				"stock_qty": item.stock_qty
			})
			for r in ret:
				if not item.get(r):
					item.set(r, ret[r])

	def get_bom_material_detail(self, args=None):
		""" Get raw material details like desc """
		if not args:
			args = frappe.form_dict.get('args')

		if isinstance(args, basestring):
			import json
			args = json.loads(args)

		item = self.get_item_det(args['item_code'])
		self.validate_rm_item(item)

		args['bom_no'] = args['bom_no'] or item and cstr(item[0]['default_bom']) or ''
		args.update(item[0])

		ret_item = {
			 'item_name'	: item and args['item_name'] or '',
			 'description'  : item and args['description'] or '',
			 'image'		: item and args['image'] or '',
			 'bom_no'		: args['bom_no'],
			 'qty'			: args.get("qty") or args.get("stock_qty") or 1,
			 'stock_qty'	: args.get("qty") or args.get("stock_qty") or 1
		}
		return ret_item

	def manage_default_bom(self):
		""" Uncheck others if current one is selected as default,
			update default bom in item master
		"""
		if self.is_default and self.is_active:
			from frappe.model.utils import set_default
			set_default(self, "item")
			item = frappe.get_doc("Item", self.item)
			if item.default_bom != self.name:
				item.default_bom = self.name
				item.save(ignore_permissions = True)
		else:
			frappe.db.set(self, "is_default", 0)
			item = frappe.get_doc("Item", self.item)
			if item.default_bom == self.name:
				item.default_bom = None
				item.save(ignore_permissions = True)

	def clear_operations(self):
		if not self.with_operations:
			self.set('operations', [])

	def validate_main_item(self):
		""" Validate main FG item"""
		item = self.get_item_det(self.item)
		if not item:
			frappe.throw(_("Item {0} does not exist in the system or has expired").format(self.item))
		else:
			ret = frappe.db.get_value("Item", self.item, ["description", "item_name"])
			self.description = ret[0]
			self.item_name= ret[1]

		if not self.quantity:
			frappe.throw(_("Quantity should be greater than 0"))

	def update_stock_qty(self):
		for m in self.get('items'):
			if m.qty:
				m.stock_qty = flt(m.qty)
			# if not m.uom and m.stock_uom:
			# 	m.uom = m.stock_uom
			# 	m.qty = m.stock_qty

	def validate_materials(self):
		""" Validate raw material entries """

		def get_duplicates(lst):
			seen = set()
			seen_add = seen.add
			for item in lst:
				if item.item_code in seen or seen_add(item.item_code):
					yield item

		if not self.get('items'):
			frappe.throw(_("Raw Materials cannot be blank."))
		check_list = []
		for m in self.get('items'):
			if m.bom_no:
				validate_bom_no(m.item_code, m.bom_no)
			if flt(m.qty) <= 0:
				frappe.throw(_("Quantity required for Item {0} in row {1}").format(m.item_code, m.idx))
			check_list.append(m)

		duplicate_items = list(get_duplicates(check_list))
		if duplicate_items:
			li = []
			for i in duplicate_items:
				li.append("{0} on row {1}".format(i.item_code, i.idx))
			duplicate_list = '<br>' + '<br>'.join(li)

			frappe.throw(_("Same item has been entered multiple times. {0}").format(duplicate_list))

	def check_recursion(self):
		""" Check whether recursion occurs in any bom"""

		check_list = [['parent', 'bom_no', 'parent'], ['bom_no', 'parent', 'child']]
		for d in check_list:
			bom_list, count = [self.name], 0
			while (len(bom_list) > count ):
				boms = frappe.db.sql(" select %s from `tabBOM Item` where %s = %s " %
					(d[0], d[1], '%s'), cstr(bom_list[count]))
				count = count + 1
				for b in boms:
					if b[0] == self.name:
						frappe.throw(_("BOM recursion: {0} cannot be parent or child of {2}").format(b[0], self.name))
					if b[0]:
						bom_list.append(b[0])

	def update_cost_and_exploded_items(self, bom_list=[]):
		bom_list = self.traverse_tree(bom_list)
		for bom in bom_list:
			bom_obj = frappe.get_doc("BOM", bom)
			bom_obj.on_update()

		return bom_list

	def traverse_tree(self, bom_list=None):
		def _get_children(bom_no):
			return [cstr(d[0]) for d in frappe.db.sql("""select bom_no from `tabBOM Item`
				where parent = %s and ifnull(bom_no, '') != ''""", bom_no)]

		count = 0
		if not bom_list:
			bom_list = []

		if self.name not in bom_list:
			bom_list.append(self.name)

		while(count < len(bom_list)):
			for child_bom in _get_children(bom_list[count]):
				if child_bom not in bom_list:
					bom_list.append(child_bom)
			count += 1
		bom_list.reverse()
		return bom_list

	def update_exploded_items(self):
		""" Update Flat BOM, following will be correct data"""
		self.get_exploded_items()
		self.add_exploded_items()

	def get_exploded_items(self):
		""" Get all raw materials including items from child bom"""
		self.cur_exploded_items = {}
		for d in self.get('items'):
			if d.bom_no:
				self.get_child_exploded_items(d.bom_no, d.stock_qty)
			else:
				self.add_to_cur_exploded_items(frappe._dict({
					'item_code'		: d.item_code,
					'item_name'		: d.item_name,
					'source_warehouse': d.source_warehouse,
					'description'	: d.description,
					'image'			: d.image,
				}))

	def add_to_cur_exploded_items(self, args):
		if self.cur_exploded_items.get(args.item_code):
			self.cur_exploded_items[args.item_code]["stock_qty"] += args.stock_qty
		else:
			self.cur_exploded_items[args.item_code] = args

	def get_child_exploded_items(self, bom_no, stock_qty):
		""" Add all items from Flat BOM of child BOM"""
		# Did not use qty_consumed_per_unit in the query, as it leads to rounding loss
		child_fb_items = frappe.db.sql("""select bom_item.item_code, bom_item.item_name,
			bom_item.description, bom_item.source_warehouse,
			bom_item.stock_qty,
			bom_item.stock_qty / ifnull(bom.quantity, 1) as qty_consumed_per_unit
			from `tabBOM Explosion Item` bom_item, tabBOM bom
			where bom_item.parent = bom.name and bom.name = %s and bom.docstatus = 1""", bom_no, as_dict = 1)

		for d in child_fb_items:
			self.add_to_cur_exploded_items(frappe._dict({
				'item_code'				: d['item_code'],
				'item_name'				: d['item_name'],
				'source_warehouse'		: d['source_warehouse'],
				'description'			: d['description'],
				'stock_qty'				: d['qty_consumed_per_unit'] * stock_qty,
			}))

	def add_exploded_items(self):
		"Add items to Flat BOM table"
		frappe.db.sql("""delete from `tabBOM Explosion Item` where parent=%s""", self.name)
		self.set('exploded_items', [])

		for d in sorted(self.cur_exploded_items, key=itemgetter(0)):
			ch = self.append('exploded_items', {})
			for i in self.cur_exploded_items[d].keys():
				ch.set(i, self.cur_exploded_items[d][i])
			ch.amount = flt(ch.stock_qty)
			ch.qty_consumed_per_unit = flt(ch.stock_qty) / flt(self.quantity)
			ch.docstatus = self.docstatus
			ch.db_insert()

	def validate_bom_links(self):
		if not self.is_active:
			act_pbom = frappe.db.sql("""select distinct bom_item.parent from `tabBOM Item` bom_item
				where bom_item.bom_no = %s and bom_item.docstatus = 1
				and exists (select * from `tabBOM` where name = bom_item.parent
					and docstatus = 1 and is_active = 1)""", self.name)

			if act_pbom and act_pbom[0][0]:
				frappe.throw(_("Cannot deactivate or cancel BOM as it is linked with other BOMs"))

	def validate_operations(self):
		if self.with_operations and not self.get('operations'):
			frappe.throw(_("Operations cannot be left blank"))

		if self.with_operations:
			for d in self.operations:
				if not d.description:
					d.description = frappe.db.get_value('Operation', d.operation, 'description')

def get_list_context(context):
	context.title = _("Bill of Materials")
	# context.introduction = _('Boms')

def get_bom_items_as_dict(bom, qty=1, fetch_exploded=1, fetch_scrap_items=0):
	item_dict = {}

	# Did not use qty_consumed_per_unit in the query, as it leads to rounding loss
	query = """select
				bom_item.item_code,
				item.item_name,
				sum(bom_item.stock_qty/ifnull(bom.quantity, 1)) * %(qty)s as qty,
				item.description,
				item.image,
				item.default_warehouse
				{select_columns}
			from
				`tab{table}` bom_item, `tabBOM` bom, `tabItem` item
			where
				bom_item.docstatus < 2
				and bom.name = %(bom)s
				and bom_item.parent = bom.name
				and item.name = bom_item.item_code
				and is_stock_item = 1
				{where_conditions}
				group by item_code
				order by idx"""

	if fetch_exploded:
		query = query.format(table="BOM Explosion Item",
			where_conditions="",
			select_columns = ", bom_item.source_warehouse, (Select idx from `tabBOM Item` where item_code = bom_item.item_code and parent = %(parent)s ) as idx")
		items = frappe.db.sql(query, { "parent": bom, "qty": qty,	"bom": bom }, as_dict=True)
	elif fetch_scrap_items:
		query = query.format(table="BOM Scrap Item", where_conditions="", select_columns=", bom_item.idx")
		items = frappe.db.sql(query, { "qty": qty, "bom": bom }, as_dict=True)
	else:
		query = query.format(table="BOM Item", where_conditions="",
			select_columns = ", bom_item.source_warehouse, bom_item.idx")
		items = frappe.db.sql(query, { "qty": qty, "bom": bom }, as_dict=True)

	for item in items:
		if item_dict.has_key(item.item_code):
			item_dict[item.item_code]["qty"] += flt(item.qty)
		else:
			item_dict[item.item_code] = item

	return item_dict

@frappe.whitelist()
def get_bom_items(bom, qty=1, fetch_exploded=1):
	items = get_bom_items_as_dict(bom, qty, fetch_exploded).values()
	items.sort(lambda a, b: a.item_code > b.item_code and 1 or -1)
	return items

def validate_bom_no(item, bom_no):
	"""Validate BOM No of sub-contracted items"""
	bom = frappe.get_doc("BOM", bom_no)
	if not bom.is_active:
		frappe.throw(_("BOM {0} must be active").format(bom_no))
	if bom.docstatus != 1:
		if not getattr(frappe.flags, "in_test", False):
			frappe.throw(_("BOM {0} must be submitted").format(bom_no))
	if item and not (bom.item.lower() == item.lower() or \
		bom.item.lower() == cstr(frappe.db.get_value("Item", item)).lower()):
		frappe.throw(_("BOM {0} does not belong to Item {1}").format(bom_no, item))

@frappe.whitelist()
def get_children(doctype, parent=None, is_tree=False):
	if not parent:
		frappe.msgprint(_('Please select a BOM'))
		return

	if frappe.form_dict.parent:
		return frappe.db.sql("""select
			bom_item.item_code,
			bom_item.bom_no as value,
			bom_item.stock_qty,
			if(ifnull(bom_item.bom_no, "")!="", 1, 0) as expandable,
			item.image,
			item.description
			from `tabBOM Item` bom_item, tabItem item
			where bom_item.parent=%s
			and bom_item.item_code = item.name
			order by bom_item.idx
			""", frappe.form_dict.parent, as_dict=True)

def get_boms_in_bottom_up_order(bom_no=None):
	def _get_parent(bom_no):
		return frappe.db.sql_list("""select distinct parent from `tabBOM Item`
			where bom_no = %s and docstatus=1""", bom_no)

	count = 0
	bom_list = []
	if bom_no:
		bom_list.append(bom_no)
	else:
		# get all leaf BOMs
		bom_list = frappe.db.sql_list("""select name from `tabBOM` bom where docstatus=1
			and not exists(select bom_no from `tabBOM Item`
				where parent=bom.name and ifnull(bom_no, '')!='')""")

	while(count < len(bom_list)):
		for child_bom in _get_parent(bom_list[count]):
			if child_bom not in bom_list:
				bom_list.append(child_bom)
		count += 1

	return bom_list
