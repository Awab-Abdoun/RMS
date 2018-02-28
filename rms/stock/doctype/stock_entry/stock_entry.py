# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import frappe.defaults
from frappe import _
from frappe.utils import cstr, cint, flt, comma_or, getdate, nowdate, formatdate, format_time
from rms.stock.stock_ledger import get_previous_sle, NegativeStockError
from rms.stock.get_item_details import get_bin_details
from rms.manufacturing.doctype.bom.bom import validate_bom_no
import json

class DuplicateEntryForProductionOrderError(frappe.ValidationError): pass
class OperationsNotCompleteError(frappe.ValidationError): pass
class MaxSampleAlreadyRetainedError(frappe.ValidationError): pass

from rms.controllers.stock_controller import StockController

form_grid_templates = {
	"items": "templates/form_grid/stock_entry_grid.html"
}


class StockEntry(StockController):
	def get_feed(self):
		return _("From {0} to {1}").format(self.from_warehouse, self.to_warehouse)

	def onload(self):
		for item in self.get("items"):
			item.update(get_bin_details(item.item_code, item.s_warehouse))

	def validate(self):
		self.pro_doc = frappe._dict()
		if self.production_order:
			self.pro_doc = frappe.get_doc('Production Order', self.production_order)

		self.validate_posting_time()
		self.validate_purpose()
		self.validate_item()
		self.set_transfer_qty()
		self.validate_warehouse()
		self.validate_production_order()
		self.validate_bom()
		self.validate_finished_goods()
		self.validate_with_material_request()

		self.set_actual_qty()

	def on_submit(self):
		self.update_stock_ledger()
		self.update_production_order()

	def on_cancel(self):
		self.update_stock_ledger()
		self.update_production_order()

	def validate_purpose(self):
		valid_purposes = ["Material Issue", "Material Receipt", "Material Transfer", "Material Transfer for Manufacture",
			"Manufacture", "Repack"]
		if self.purpose not in valid_purposes:
			frappe.throw(_("Purpose must be one of {0}").format(comma_or(valid_purposes)))

	def set_transfer_qty(self):
		for item in self.get("items"):
			if not flt(item.qty):
				frappe.throw(_("Row {0}: Qty is mandatory").format(item.idx))
			item.transfer_qty = flt(flt(item.qty),
				self.precision("transfer_qty", item))

	def validate_item(self):
		stock_items = self.get_stock_items()
		for item in self.get("items"):
			if item.item_code not in stock_items:
				frappe.throw(_("{0} is not a stock Item").format(item.item_code))

			item_details = self.get_item_details(frappe._dict(
				{"item_code": item.item_code,
				"project": self.project, 's_warehouse': item.s_warehouse}),
				for_update=True)

			if not item.transfer_qty and item.qty:
				item.transfer_qty = item.qty

	def get_stock_items(self):
		stock_items = []
		item_codes = list(set(item.item_code for item in self.get("items")))
		if item_codes:
			stock_items = [r[0] for r in frappe.db.sql("""select name
				from `tabItem` where name in (%s) and is_stock_item=1""" % \
				(", ".join((["%s"]*len(item_codes))),), item_codes)]

		return stock_items

	def validate_warehouse(self):
		"""perform various (sometimes conditional) validations on warehouse"""

		source_mandatory = ["Material Issue", "Material Transfer", "Subcontract", "Material Transfer for Manufacture"]
		target_mandatory = ["Material Receipt", "Material Transfer", "Subcontract", "Material Transfer for Manufacture"]

		validate_for_manufacture_repack = any([d.bom_no for d in self.get("items")])

		if self.purpose in source_mandatory and self.purpose not in target_mandatory:
			self.to_warehouse = None
			for d in self.get('items'):
				d.t_warehouse = None
		elif self.purpose in target_mandatory and self.purpose not in source_mandatory:
			self.from_warehouse = None
			for d in self.get('items'):
				d.s_warehouse = None

		for d in self.get('items'):
			if not d.s_warehouse and not d.t_warehouse:
				d.s_warehouse = self.from_warehouse
				d.t_warehouse = self.to_warehouse

			if not (d.s_warehouse or d.t_warehouse):
				frappe.throw(_("Atleast one warehouse is mandatory"))

			if self.purpose in source_mandatory and not d.s_warehouse:
				if self.from_warehouse:
					d.s_warehouse = self.from_warehouse
				else:
					frappe.throw(_("Source warehouse is mandatory for row {0}").format(d.idx))

			if self.purpose in target_mandatory and not d.t_warehouse:
				if self.to_warehouse:
					d.t_warehouse = self.to_warehouse
				else:
					frappe.throw(_("Target warehouse is mandatory for row {0}").format(d.idx))

			if self.purpose in ["Manufacture", "Repack"]:
				if validate_for_manufacture_repack:
					if d.bom_no:
						d.s_warehouse = None

						if not d.t_warehouse:
							frappe.throw(_("Target warehouse is mandatory for row {0}").format(d.idx))

						elif self.pro_doc and (cstr(d.t_warehouse) != self.pro_doc.fg_warehouse and cstr(d.t_warehouse) != self.pro_doc.scrap_warehouse):
							frappe.throw(_("Target warehouse in row {0} must be same as Production Order").format(d.idx))

					else:
						d.t_warehouse = None
						if not d.s_warehouse:
							frappe.throw(_("Source warehouse is mandatory for row {0}").format(d.idx))

			if cstr(d.s_warehouse) == cstr(d.t_warehouse) and not self.purpose == "Material Transfer for Manufacture":
				frappe.throw(_("Source and target warehouse cannot be same for row {0}").format(d.idx))

	def validate_production_order(self):
		if self.purpose in ("Manufacture", "Material Transfer for Manufacture"):
			# check if production order is entered

			if self.purpose=="Manufacture" and self.production_order:
				if not self.fg_completed_qty:
					frappe.throw(_("For Quantity (Manufactured Qty) is mandatory"))
				self.check_if_operations_completed()
				self.check_duplicate_entry_for_production_order()
		elif self.purpose != "Material Transfer":
			self.production_order = None

	def check_if_operations_completed(self):
		"""Check if Time Sheets are completed against before manufacturing to capture operating costs."""
		prod_order = frappe.get_doc("Production Order", self.production_order)

		for d in prod_order.get("operations"):
			total_completed_qty = flt(self.fg_completed_qty) + flt(prod_order.produced_qty)
			if total_completed_qty > flt(d.completed_qty):
				frappe.throw(_("Row #{0}: Operation {1} is not completed for {2} qty of finished goods in Production Order # {3}. Please update operation status")
					.format(d.idx, d.operation, total_completed_qty, self.production_order), OperationsNotCompleteError)

	def check_duplicate_entry_for_production_order(self):
		other_ste = [t[0] for t in frappe.db.get_values("Stock Entry",  {
			"production_order": self.production_order,
			"purpose": self.purpose,
			"docstatus": ["!=", 2],
			"name": ["!=", self.name]
		}, "name")]

		if other_ste:
			production_item, qty = frappe.db.get_value("Production Order",
				self.production_order, ["production_item", "qty"])
			args = other_ste + [production_item]
			fg_qty_already_entered = frappe.db.sql("""select sum(transfer_qty)
				from `tabStock Entry Detail`
				where parent in (%s)
					and item_code = %s
					and ifnull(s_warehouse,'')='' """ % (", ".join(["%s" * len(other_ste)]), "%s"), args)[0][0]

			if fg_qty_already_entered >= qty:
				frappe.throw(_("Stock Entries already created for Production Order ")
					+ self.production_order + ":" + ", ".join(other_ste), DuplicateEntryForProductionOrderError)

	def set_actual_qty(self):
		for d in self.get('items'):
			previous_sle = get_previous_sle({
				"item_code": d.item_code,
				"warehouse": d.s_warehouse or d.t_warehouse,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time
			})

			# get actual stock at source warehouse
			d.actual_qty = previous_sle.get("qty_after_transaction") or 0

			# validate qty during submit
			if d.docstatus==1 and d.s_warehouse and d.actual_qty < d.transfer_qty:
				frappe.throw(_("Row {0}: Qty not available for {4} in warehouse {1} at posting time of the entry ({2} {3})").format(d.idx,
					frappe.bold(d.s_warehouse), formatdate(self.posting_date),
					format_time(self.posting_time), frappe.bold(d.item_code))
					+ '<br><br>' + _("Available qty is {0}, you need {1}").format(frappe.bold(d.actual_qty),
						frappe.bold(d.transfer_qty)),
					NegativeStockError, title=_('Insufficient Stock'))

	def get_stock_and_rate(self):
		self.set_production_order_details()
		self.set_transfer_qty()
		self.set_actual_qty()

	def validate_bom(self):
		for d in self.get('items'):
			if d.bom_no and (d.t_warehouse != getattr(self, "pro_doc", frappe._dict()).scrap_warehouse):
				validate_bom_no(d.item_code, d.bom_no)

	def validate_finished_goods(self):
		"""validation: finished good quantity should be same as manufacturing quantity"""
		items_with_target_warehouse = []
		for d in self.get('items'):
			if d.bom_no and flt(d.transfer_qty) != flt(self.fg_completed_qty) and (d.t_warehouse != getattr(self, "pro_doc", frappe._dict()).scrap_warehouse):
				frappe.throw(_("Quantity in row {0} ({1}) must be same as manufactured quantity {2}"). \
					format(d.idx, d.transfer_qty, self.fg_completed_qty))

			if self.production_order and self.purpose == "Manufacture" and d.t_warehouse:
				items_with_target_warehouse.append(d.item_code)

		if self.production_order and self.purpose == "Manufacture":
			production_item = frappe.db.get_value("Production Order",
				self.production_order, "production_item")
			if production_item not in items_with_target_warehouse:
				frappe.throw(_("Finished Item {0} must be entered for Manufacture type entry")
					.format(production_item))

	def update_stock_ledger(self):
		sl_entries = []

		# make sl entries for source warehouse first, then do for target warehouse
		for d in self.get('items'):
			if cstr(d.s_warehouse):
				sl_entries.append(self.get_sl_entries(d, {
					"warehouse": cstr(d.s_warehouse),
					"actual_qty": -flt(d.transfer_qty)
				}))

		for d in self.get('items'):
			if cstr(d.t_warehouse):
				sl_entries.append(self.get_sl_entries(d, {
					"warehouse": cstr(d.t_warehouse),
					"actual_qty": flt(d.transfer_qty)
				}))

		# On cancellation, make stock ledger entry for
		# target warehouse first, to update serial no values properly

			# if cstr(d.s_warehouse) and self.docstatus == 2:
			# 	sl_entries.append(self.get_sl_entries(d, {
			# 		"warehouse": cstr(d.s_warehouse),
			# 		"actual_qty": -flt(d.transfer_qty),
			# 		"incoming_rate": 0
			# 	}))

		if self.docstatus == 2:
			sl_entries.reverse()

		self.make_sl_entries(sl_entries, self.amended_from)

	def update_production_order(self):
		def _validate_production_order(pro_doc):
			if flt(pro_doc.docstatus) != 1:
				frappe.throw(_("Production Order {0} must be submitted").format(self.production_order))

			if pro_doc.status == 'Stopped':
				frappe.throw(_("Transaction not allowed against stopped Production Order {0}").format(self.production_order))

		if self.production_order:
			pro_doc = frappe.get_doc("Production Order", self.production_order)
			_validate_production_order(pro_doc)
			pro_doc.run_method("update_status")
			if self.fg_completed_qty:
				pro_doc.run_method("update_production_order_qty")
				if self.purpose == "Manufacture":
					pro_doc.run_method("update_planned_qty")

	def get_item_details(self, args=None, for_update=False):
		item = frappe.db.sql("""select description, image, item_name,
				item_group
			from `tabItem`
			where name = %s
				and disabled=0
				and (end_of_life is null or end_of_life='0000-00-00' or end_of_life > %s)""",
			(args.get('item_code'), nowdate()), as_dict = 1)
		if not item:
			frappe.throw(_("Item {0} is not active or end of life has been reached").format(args.get("item_code")))

		item = item[0]

		ret = frappe._dict({
			'description'		  	: item.description,
			'image'					: item.image,
			'item_name' 		  	: item.item_name,
			'qty'					: 0,
			'transfer_qty'			: 0,
			'actual_qty'			: 0
		})

		args['posting_date'] = self.posting_date
		args['posting_time'] = self.posting_time

		stock_and_rate = get_warehouse_details(args) if args.get('warehouse') else {}
		ret.update(stock_and_rate)

		return ret

	def get_items(self):
		self.set('items', [])
		self.validate_production_order()

		if not self.posting_date or not self.posting_time:
			frappe.throw(_("Posting date and posting time is mandatory"))

		self.set_production_order_details()

		if self.bom_no:
			if self.purpose in ["Material Issue", "Material Transfer", "Manufacture", "Repack",
					"Subcontract", "Material Transfer for Manufacture"]:
				if self.production_order and self.purpose == "Material Transfer for Manufacture":
					item_dict = self.get_pending_raw_materials()
					if self.to_warehouse and self.pro_doc:
						for item in item_dict.values():
							item["to_warehouse"] = self.pro_doc.wip_warehouse
					self.add_to_stock_entry_detail(item_dict)

				elif self.production_order and self.purpose == "Manufacture":
					self.get_transfered_raw_materials()

				else:
					if not self.fg_completed_qty:
						frappe.throw(_("Manufacturing Quantity is mandatory"))

					item_dict = self.get_bom_raw_materials(self.fg_completed_qty)
					for item in item_dict.values():
						if self.pro_doc and not self.pro_doc.skip_transfer:
							item["from_warehouse"] = self.pro_doc.wip_warehouse

						item["to_warehouse"] = self.to_warehouse if self.purpose=="Subcontract" else ""

					self.add_to_stock_entry_detail(item_dict)

					scrap_item_dict = self.get_bom_scrap_material(self.fg_completed_qty)
					for item in scrap_item_dict.values():
						if self.pro_doc and self.pro_doc.scrap_warehouse:
							item["to_warehouse"] = self.pro_doc.scrap_warehouse
					self.add_to_stock_entry_detail(scrap_item_dict, bom_no=self.bom_no)

			# add finished goods item
			if self.purpose in ("Manufacture", "Repack"):
				self.load_items_from_bom()

		self.set_actual_qty()

	def set_production_order_details(self):
		if not getattr(self, "pro_doc", None):
			self.pro_doc = frappe._dict()

		if self.production_order:
			# common validations
			if not self.pro_doc:
				self.pro_doc = frappe.get_doc('Production Order', self.production_order)

			if self.pro_doc:
				self.bom_no = self.pro_doc.bom_no
			else:
				# invalid production order
				self.production_order = None

	def load_items_from_bom(self):
		if self.production_order:
			item_code = self.pro_doc.production_item
			to_warehouse = self.pro_doc.fg_warehouse
		else:
			item_code = frappe.db.get_value("BOM", self.bom_no, "item")
			to_warehouse = self.to_warehouse

		item = frappe.db.get_value("Item", item_code, ["item_name",
			"description", "name", "default_warehouse"], as_dict=1)

		if not self.production_order and not to_warehouse:
			# in case of BOM
			to_warehouse = item.default_warehouse

		self.add_to_stock_entry_detail({
			item.name: {
				"to_warehouse": to_warehouse,
				"from_warehouse": "",
				"qty": self.fg_completed_qty,
				"item_name": item.item_name,
				"description": item.description
			}
		}, bom_no = self.bom_no)

	def get_bom_raw_materials(self, qty):
		from rms.manufacturing.doctype.bom.bom import get_bom_items_as_dict

		# item dict = { item_code: {qty, description, stock_uom} }
		item_dict = get_bom_items_as_dict(self.bom_no, qty=qty,
			fetch_exploded = self.use_multi_level_bom)

		for item in item_dict.values():
			# if source warehouse presents in BOM set from_warehouse as bom source_warehouse
			item.from_warehouse = self.from_warehouse or item.source_warehouse or item.default_warehouse
		return item_dict

	def get_bom_scrap_material(self, qty):
		from rms.manufacturing.doctype.bom.bom import get_bom_items_as_dict

		# item dict = { item_code: {qty, description, stock_uom} }
		item_dict = get_bom_items_as_dict(self.bom_no, qty=qty,
			fetch_exploded = 0, fetch_scrap_items = 1)

		for item in item_dict.values():
			item.from_warehouse = ""
		return item_dict

	def get_transfered_raw_materials(self):
		transferred_materials = frappe.db.sql("""
			select
				item_name, item_code, sum(qty) as qty, sed.t_warehouse as warehouse,
				description
			from `tabStock Entry` se,`tabStock Entry Detail` sed
			where
				se.name = sed.parent and se.docstatus=1 and se.purpose='Material Transfer for Manufacture'
				and se.production_order= %s and ifnull(sed.t_warehouse, '') != ''
			group by sed.item_code, sed.t_warehouse
		""", self.production_order, as_dict=1)

		materials_already_backflushed = frappe.db.sql("""
			select
				item_code, sed.s_warehouse as warehouse, sum(qty) as qty
			from
				`tabStock Entry` se, `tabStock Entry Detail` sed
			where
				se.name = sed.parent and se.docstatus=1 and se.purpose='Manufacture'
				and se.production_order= %s and ifnull(sed.s_warehouse, '') != ''
			group by sed.item_code, sed.s_warehouse
		""", self.production_order, as_dict=1)

		backflushed_materials= {}
		for d in materials_already_backflushed:
			backflushed_materials.setdefault(d.item_code,[]).append({d.warehouse: d.qty})

		po_qty = frappe.db.sql("""select qty, produced_qty, material_transferred_for_manufacturing from
			`tabProduction Order` where name=%s""", self.production_order, as_dict=1)[0]
		manufacturing_qty = flt(po_qty.qty)
		produced_qty = flt(po_qty.produced_qty)
		trans_qty = flt(po_qty.material_transferred_for_manufacturing)

		for item in transferred_materials:
			qty= item.qty

			if trans_qty and manufacturing_qty > (produced_qty + flt(self.fg_completed_qty)):
				qty = (qty/trans_qty) * flt(self.fg_completed_qty)

			elif backflushed_materials.get(item.item_code):
				for d in backflushed_materials.get(item.item_code):
					if d.get(item.warehouse):
						qty-= d.get(item.warehouse)

			if qty > 0:
				self.add_to_stock_entry_detail({
					item.item_code: {
						"from_warehouse": item.warehouse,
						"to_warehouse": "",
						"qty": qty,
						"item_name": item.item_name,
						"description": item.description
					}
				})

	def get_pending_raw_materials(self):
		"""
			issue (item quantity) that is pending to issue or desire to transfer,
			whichever is less
		"""
		item_dict = self.get_pro_order_required_items()
		max_qty = flt(self.pro_doc.qty)
		for item, item_details in item_dict.items():
			pending_to_issue = flt(item_details.required_qty) - flt(item_details.transferred_qty)
			desire_to_transfer = flt(self.fg_completed_qty) * flt(item_details.required_qty) / max_qty

			if desire_to_transfer <= pending_to_issue:
				item_dict[item]["qty"] = desire_to_transfer
			elif pending_to_issue > 0:
				item_dict[item]["qty"] = pending_to_issue
			else:
				item_dict[item]["qty"] = 0

		# delete items with 0 qty
		for item in item_dict.keys():
			if not item_dict[item]["qty"]:
				del item_dict[item]

		# show some message
		if not len(item_dict):
			frappe.msgprint(_("""All items have already been transferred for this Production Order."""))

		return item_dict

	def get_pro_order_required_items(self):
		item_dict = frappe._dict()
		pro_order = frappe.get_doc("Production Order", self.production_order)
		if not frappe.db.get_value("Warehouse", pro_order.wip_warehouse, "is_group"):
			wip_warehouse = pro_order.wip_warehouse
		else:
			wip_warehouse = None

		for d in pro_order.get("required_items"):
			if flt(d.required_qty) > flt(d.transferred_qty):
				item_row = d.as_dict()
				if d.source_warehouse and not frappe.db.get_value("Warehouse", d.source_warehouse, "is_group"):
					item_row["from_warehouse"] = d.source_warehouse

				item_row["to_warehouse"] = wip_warehouse
				item_dict.setdefault(d.item_code, item_row)

		return item_dict

	def add_to_stock_entry_detail(self, item_dict, bom_no=None):
		for d in item_dict:
			se_child = self.append('items')
			se_child.s_warehouse = item_dict[d].get("from_warehouse")
			se_child.t_warehouse = item_dict[d].get("to_warehouse")
			se_child.item_code = cstr(d)
			se_child.item_name = item_dict[d]["item_name"]
			se_child.description = item_dict[d]["description"]
			se_child.qty = flt(item_dict[d]["qty"], se_child.precision("qty"))

			if se_child.s_warehouse==None:
				se_child.s_warehouse = self.from_warehouse
			if se_child.t_warehouse==None:
				se_child.t_warehouse = self.to_warehouse

			# in stock uom
			se_child.transfer_qty = flt(item_dict[d]["qty"], se_child.precision("qty"))

			# to be assigned for finished item
			se_child.bom_no = bom_no

	def validate_with_material_request(self):
		for item in self.get("items"):
			if item.material_request:
				mreq_item = frappe.db.get_value("Material Request Item",
					{"name": item.material_request_item, "parent": item.material_request},
					["item_code", "warehouse", "idx"], as_dict=True)
				if mreq_item.item_code != item.item_code or \
				mreq_item.warehouse != (item.s_warehouse if self.purpose== "Material Issue" else item.t_warehouse):
					frappe.throw(_("Item or Warehouse for row {0} does not match Material Request").format(item.idx),
						frappe.MappingMismatchError)

@frappe.whitelist()
def get_production_order_details(production_order):
	production_order = frappe.get_doc("Production Order", production_order)
	pending_qty_to_produce = flt(production_order.qty) - flt(production_order.produced_qty)

	return {
		"from_bom": 1,
		"bom_no": production_order.bom_no,
		"use_multi_level_bom": production_order.use_multi_level_bom,
		"wip_warehouse": production_order.wip_warehouse,
		"fg_warehouse": production_order.fg_warehouse,
		"fg_completed_qty": pending_qty_to_produce
	}

@frappe.whitelist()
def get_warehouse_details(args):
	if isinstance(args, basestring):
		args = json.loads(args)

	args = frappe._dict(args)

	ret = {}
	if args.warehouse and args.item_code:
		args.update({
			"posting_date": args.posting_date,
			"posting_time": args.posting_time,
		})
		ret = {
			"actual_qty" : get_previous_sle(args).get("qty_after_transaction") or 0
		}
	return ret
