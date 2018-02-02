# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import json
from frappe import _
from frappe.utils import flt, get_datetime, getdate, date_diff, cint, nowdate
from rms.manufacturing.doctype.bom.bom import validate_bom_no, get_bom_items_as_dict
from dateutil.relativedelta import relativedelta
from rms.stock.doctype.item.item import validate_end_of_life
from rms.stock.stock_balance import get_planned_qty, update_bin_qty
from frappe.utils.csvutils import getlink
from rms.stock.utils import get_bin, get_latest_stock_qty

class OverProductionError(frappe.ValidationError): pass
class StockOverProductionError(frappe.ValidationError): pass
class OperationTooLongError(frappe.ValidationError): pass

form_grid_templates = {
	"operations": "templates/form_grid/production_order_grid.html"
}

class ProductionOrder(Document):
	def validate(self):
		self.validate_production_item()
		if self.bom_no:
			validate_bom_no(self.production_item, self.bom_no)

		self.set_default_warehouse()
		self.validate_qty()
		self.validate_operation_time()
		self.status = self.get_status()

		if not self.get("required_items"):
			self.set_required_items()
		else:
			self.set_available_qty()

	def set_default_warehouse(self):
		if not self.wip_warehouse:
			self.wip_warehouse = frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")
		if not self.fg_warehouse:
			self.fg_warehouse = frappe.db.get_single_value("Manufacturing Settings", "default_fg_warehouse")

	def update_status(self, status=None):
		'''Update status of production order if unknown'''
		if status != "Stopped":
			status = self.get_status(status)

		if status != self.status:
			self.db_set("status", status)

		self.update_required_items()

		return status

	def get_status(self, status=None):
		'''Return the status based on stock entries against this production order'''
		if not status:
			status = self.status

		if self.docstatus==0:
			status = 'Draft'
		elif self.docstatus==1:
			if status != 'Stopped':
				stock_entries = frappe._dict(frappe.db.sql("""select purpose, sum(fg_completed_qty)
					from `tabStock Entry` where production_order=%s and docstatus=1
					group by purpose""", self.name))

				status = "Not Started"
				if stock_entries:
					status = "In Process"
					produced_qty = stock_entries.get("Manufacture")
					if flt(produced_qty) == flt(self.qty):
						status = "Completed"
		else:
			status = 'Cancelled'

		return status

	def update_production_order_qty(self):
		"""Update **Manufactured Qty** and **Material Transferred for Qty** in Production Order
			based on Stock Entry"""

		for purpose, fieldname in (("Manufacture", "produced_qty"),
			("Material Transfer for Manufacture", "material_transferred_for_manufacturing")):
			qty = flt(frappe.db.sql("""select sum(fg_completed_qty)
				from `tabStock Entry` where production_order=%s and docstatus=1
				and purpose=%s""", (self.name, purpose))[0][0])

			if qty > self.qty:
				frappe.throw(_("{0} ({1}) cannot be greater than planned quantity ({2}) in Production Order {3}").format(\
					self.meta.get_label(fieldname), qty, self.qty, self.name), StockOverProductionError)

			self.db_set(fieldname, qty)

	def on_submit(self):

		if not self.wip_warehouse:
			frappe.throw(_("Work-in-Progress Warehouse is required before Submit"))
		if not self.fg_warehouse:
			frappe.throw(_("For Warehouse is required before Submit"))

		self.update_reserved_qty_for_production()
		self.update_completed_qty_in_material_request()
		self.update_planned_qty()

	def on_cancel(self):
		self.validate_cancel()

		frappe.db.set(self,'status', 'Cancelled')
		self.update_completed_qty_in_material_request()
		self.update_planned_qty()
		self.update_reserved_qty_for_production()

	def validate_cancel(self):
		if self.status == "Stopped":
			frappe.throw(_("Stopped Production Order cannot be cancelled, Unstop it first to cancel"))

		# Check whether any stock entry exists against this Production Order
		stock_entry = frappe.db.sql("""select name from `tabStock Entry`
			where production_order = %s and docstatus = 1""", self.name)
		if stock_entry:
			frappe.throw(_("Cannot cancel because submitted Stock Entry {0} exists").format(stock_entry[0][0]))

	def update_planned_qty(self):
		update_bin_qty(self.production_item, self.fg_warehouse, {
			"planned_qty": get_planned_qty(self.production_item, self.fg_warehouse)
		})

		if self.material_request:
			mr_obj = frappe.get_doc("Material Request", self.material_request)
			mr_obj.update_requested_qty([self.material_request_item])

	def update_completed_qty_in_material_request(self):
		if self.material_request:
			frappe.get_doc("Material Request", self.material_request).update_completed_qty([self.material_request_item])

	def set_production_order_operations(self):
		"""Fetch operations from BOM and set in 'Production Order'"""
		self.set('operations', [])

		if not self.bom_no:
				return

		if self.use_multi_level_bom:
			bom_list = frappe.get_doc("BOM", self.bom_no).traverse_tree()
		else:
			bom_list = [self.bom_no]

		operations = frappe.db.sql("""
			select
				operation, description, workstation, idx,
				time_in_mins,
				"Pending" as status, parent as bom
			from
				`tabBOM Operation`
			where
				 parent in (%s) order by idx
		"""	% ", ".join(["%s"]*len(bom_list)), tuple(bom_list), as_dict=1)

		self.set('operations', operations)
		self.calculate_time()

	def calculate_time(self):
		bom_qty = frappe.db.get_value("BOM", self.bom_no, "quantity")

		for d in self.get("operations"):
			d.time_in_mins = flt(d.time_in_mins) / flt(bom_qty) * flt(self.qty)

	def get_operations_data(self, data):
		return {
			'from_time': get_datetime(data.planned_start_time),
			'hours': data.time_in_mins / 60.0,
			'to_time': get_datetime(data.planned_end_time),
			'project': self.project,
			'operation': data.operation,
			'operation_id': data.name,
			'workstation': data.workstation,
			'completed_qty': flt(self.qty) - flt(data.completed_qty)
		}

	def set_start_end_time_for_workstation(self, data, index):
		"""Set start and end time for given operation. If first operation, set start as
		`planned_start_date`, else add time diff to end time of earlier operation."""

		if index == 0:
			data.planned_start_time = self.planned_start_date
		else:
			data.planned_start_time = get_datetime(self.operations[index-1].planned_end_time)\
								+ get_mins_between_operations()

		data.planned_end_time = get_datetime(data.planned_start_time) + relativedelta(minutes = data.time_in_mins)

		if data.planned_start_time == data.planned_end_time:
			frappe.throw(_("Capacity Planning Error"))

	def update_operation_status(self):
		for d in self.get("operations"):
			if not d.completed_qty:
				d.status = "Pending"
			elif flt(d.completed_qty) < flt(self.qty):
				d.status = "Work in Progress"
			elif flt(d.completed_qty) == flt(self.qty):
				d.status = "Completed"
			else:
				frappe.throw(_("Completed Qty can not be greater than 'Qty to Manufacture'"))

	def set_actual_dates(self):
		self.actual_start_date = None
		self.actual_end_date = None
		if self.get("operations"):
			actual_start_dates = [d.actual_start_time for d in self.get("operations") if d.actual_start_time]
			if actual_start_dates:
				self.actual_start_date = min(actual_start_dates)

			actual_end_dates = [d.actual_end_time for d in self.get("operations") if d.actual_end_time]
			if actual_end_dates:
				self.actual_end_date = max(actual_end_dates)

	def validate_production_item(self):
		if self.production_item:
			validate_end_of_life(self.production_item)

	def validate_qty(self):
		if not self.qty > 0:
			frappe.throw(_("Quantity to Manufacture must be greater than 0."))

	def validate_operation_time(self):
		for d in self.operations:
			if not d.time_in_mins > 0:
				frappe.throw(_("Operation Time must be greater than 0 for Operation {0}".format(d.operation)))

	def update_required_items(self):
		'''
		update bin reserved_qty_for_production
		called from Stock Entry for production, after submit, cancel
		'''
		if self.docstatus==1:
			# calculate transferred qty based on submitted stock entries
			self.update_transaferred_qty_for_required_items()

			# update in bin
			self.update_reserved_qty_for_production()

	def update_reserved_qty_for_production(self, items=None):
		'''update reserved_qty_for_production in bins'''
		for d in self.required_items:
			if d.source_warehouse:
				stock_bin = get_bin(d.item_code, d.source_warehouse)
				stock_bin.update_reserved_qty_for_production()

	def get_items_and_operations_from_bom(self):
		self.set_required_items()
		self.set_production_order_operations()

		return check_if_scrap_warehouse_mandatory(self.bom_no)

	def set_available_qty(self):
		for d in self.get("required_items"):
			if d.source_warehouse:
				d.available_qty_at_source_warehouse = get_latest_stock_qty(d.item_code, d.source_warehouse)

			if self.wip_warehouse:
				d.available_qty_at_wip_warehouse = get_latest_stock_qty(d.item_code, self.wip_warehouse)

	def set_required_items(self):
		'''set required_items for production to keep track of reserved qty'''
		self.required_items = []
		if self.bom_no and self.qty:
			item_dict = get_bom_items_as_dict(self.bom_no, qty=self.qty,
				fetch_exploded = self.use_multi_level_bom)

			for item in sorted(item_dict.values(), key=lambda d: d['idx']):
				self.append('required_items', {
					'item_code': item.item_code,
					'item_name': item.item_name,
					'description': item.description,
					'required_qty': item.qty,
					'source_warehouse': item.source_warehouse or item.default_warehouse
				})

			self.set_available_qty()

	def update_transaferred_qty_for_required_items(self):
		'''update transferred qty from submitted stock entries for that item against
			the production order'''

		for d in self.required_items:
			transferred_qty = frappe.db.sql('''select sum(qty)
				from `tabStock Entry` entry, `tabStock Entry Detail` detail
				where
					entry.production_order = %s
					and entry.purpose = "Material Transfer for Manufacture"
					and entry.docstatus = 1
					and detail.parent = entry.name
					and detail.item_code = %s''', (self.name, d.item_code))[0][0]

			d.db_set('transferred_qty', transferred_qty, update_modified = False)


@frappe.whitelist()
def get_item_details(item, project = None):
	res = frappe.db.sql("""
		select description
		from `tabItem`
		where disabled=0
			and (end_of_life is null or end_of_life='0000-00-00' or end_of_life > %s)
			and name=%s
	""", (nowdate(), item), as_dict=1)

	if not res:
		return {}

	res = res[0]

	filters = {"item": item, "is_default": 1}

	if project:
		filters = {"item": item, "project": project}

	res["bom_no"] = frappe.db.get_value("BOM", filters = filters)

	if not res["bom_no"]:
		if project:
			res = get_item_details(item)
			frappe.msgprint(_("Default BOM not found for Item {0} and Project {1}").format(item, project))
		else:
			frappe.throw(_("Default BOM for {0} not found").format(item))

	res['project'] = project or frappe.db.get_value('BOM', res['bom_no'], 'project')
	res.update(check_if_scrap_warehouse_mandatory(res["bom_no"]))

	return res

@frappe.whitelist()
def check_if_scrap_warehouse_mandatory(bom_no):
	res = {"set_scrap_wh_mandatory": False }
	if bom_no:
		bom = frappe.get_doc("BOM", bom_no)

		if len(bom.scrap_items) > 0:
			res["set_scrap_wh_mandatory"] = True

	return res

@frappe.whitelist()
def set_production_order_ops(name):
	po = frappe.get_doc('Production Order', name)
	po.set_production_order_operations()
	po.save()

@frappe.whitelist()
def make_stock_entry(production_order_id, purpose, qty=None):
	production_order = frappe.get_doc("Production Order", production_order_id)
	if not frappe.db.get_value("Warehouse", production_order.wip_warehouse, "is_group") \
			and not production_order.skip_transfer:
		wip_warehouse = production_order.wip_warehouse
	else:
		wip_warehouse = None

	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.purpose = purpose
	stock_entry.production_order = production_order_id
	stock_entry.from_bom = 1
	stock_entry.bom_no = production_order.bom_no
	stock_entry.use_multi_level_bom = production_order.use_multi_level_bom
	stock_entry.fg_completed_qty = qty or (flt(production_order.qty) - flt(production_order.produced_qty))

	if purpose=="Material Transfer for Manufacture":
		stock_entry.to_warehouse = wip_warehouse
		stock_entry.project = production_order.project
	else:
		stock_entry.from_warehouse = wip_warehouse
		stock_entry.to_warehouse = production_order.fg_warehouse
		stock_entry.project = production_order.project

	stock_entry.get_items()
	return stock_entry.as_dict()

@frappe.whitelist()
def get_default_warehouse():
	wip_warehouse = frappe.db.get_single_value("Manufacturing Settings",
		"default_wip_warehouse")
	fg_warehouse = frappe.db.get_single_value("Manufacturing Settings",
		"default_fg_warehouse")
	return {"wip_warehouse": wip_warehouse, "fg_warehouse": fg_warehouse}

@frappe.whitelist()
def stop_unstop(production_order, status):
	""" Called from client side on Stop/Unstop event"""

	if not frappe.has_permission("Production Order", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	pro_order = frappe.get_doc("Production Order", production_order)
	pro_order.update_status(status)
	pro_order.update_planned_qty()
	frappe.msgprint(_("Production Order has been {0}").format(status))
	pro_order.notify_update()

	return pro_order.status
