
from __future__ import unicode_literals

import frappe, rms
from frappe import _
from frappe.utils import cint, flt, cstr, now
from rms.stock.utils import get_valuation_method
import json

# future reposting
class NegativeStockError(frappe.ValidationError): pass

_exceptions = frappe.local('stockledger_exceptions')
# _exceptions = []

def make_sl_entries(sl_entries, is_amended=None):
	if sl_entries:
		from rms.stock.utils import update_bin

		cancel = True if sl_entries[0].get("is_cancelled") == "Yes" else False
		if cancel:
			set_as_cancel(sl_entries[0].get('voucher_no'), sl_entries[0].get('voucher_type'))

		for sle in sl_entries:
			sle_id = None
			if sle.get('is_cancelled') == 'Yes':
				sle['actual_qty'] = -flt(sle['actual_qty'])

			if sle.get("actual_qty") or sle.get("voucher_type")=="Stock Reconciliation":
				sle_id = make_entry(sle)

			args = sle.copy()
			args.update({
				"sle_id": sle_id,
				"is_amended": is_amended
			})
			update_bin(args)

		if cancel:
			delete_cancelled_entry(sl_entries[0].get('voucher_type'), sl_entries[0].get('voucher_no'))

def set_as_cancel(voucher_type, voucher_no):
	frappe.db.sql("""update `tabStock Ledger Entry` set is_cancelled='Yes',
		modified=%s, modified_by=%s
		where voucher_no=%s and voucher_type=%s""",
		(now(), frappe.session.user, voucher_type, voucher_no))

def make_entry(args):
	args.update({"doctype": "Stock Ledger Entry"})
	sle = frappe.get_doc(args)
	sle.flags.ignore_permissions = 1
	sle.insert()
	sle.submit()
	return sle.name

def delete_cancelled_entry(voucher_type, voucher_no):
	frappe.db.sql("""delete from `tabStock Ledger Entry`
		where voucher_type=%s and voucher_no=%s""", (voucher_type, voucher_no))

class update_entries_after(object):
	"""
		update qty after transaction
		from the current time-bucket onwards

		:param args: args as dict

			args = {
				"item_code": "ABC",
				"warehouse": "XYZ",
				"posting_date": "2012-12-12",
				"posting_time": "12:00"
			}
	"""
	def __init__(self, args, verbose=1):
		from frappe.model.meta import get_field_precision

		self.exceptions = []
		self.verbose = verbose

		self.args = args
		for key, value in args.iteritems():
			setattr(self, key, value)

		self.previous_sle = self.get_sle_before_datetime()
		self.previous_sle = self.previous_sle[0] if self.previous_sle else frappe._dict()

		for key in ("qty_after_transaction"):
			setattr(self, key, flt(self.previous_sle.get(key)))

		self.stock_queue = json.loads(self.previous_sle.stock_queue or "[]")
		self.valuation_method = get_valuation_method(self.item_code)
		self.stock_value_difference = 0.0
		self.qty_after_transaction = 0.0
		self.build()

	def build(self):
		# includes current entry!
		entries_to_fix = self.get_sle_after_datetime()

		for sle in entries_to_fix:
			self.process_sle(sle)

		if self.exceptions:
			self.raise_exceptions()

		self.update_bin()

	def update_bin(self):
		# update bin
		bin_name = frappe.db.get_value("Bin", {
			"item_code": self.item_code,
			"warehouse": self.warehouse
		})

		if not bin_name:
			bin_doc = frappe.get_doc({
				"doctype": "Bin",
				"item_code": self.item_code,
				"warehouse": self.warehouse
			})
			bin_doc.insert(ignore_permissions=True)
		else:
			bin_doc = frappe.get_doc("Bin", bin_name)

		bin_doc.update({
			"actual_qty": self.qty_after_transaction
		})
		bin_doc.flags.via_stock_ledger_entry = True

		bin_doc.save(ignore_permissions=True)

	def process_sle(self, sle):
		# self.qty_after_transaction = sle.qty_after_transaction
		# self.qty_after_transaction += flt(sle.actual_qty)
		# self.stock_value = flt(self.qty_after_transaction)

		# if not self.validate_negative_stock(sle):
		# 	self.qty_after_transaction += flt(sle.actual_qty)
		# 	return
			
		if sle.voucher_type=="Stock Reconciliation":
			# assert
			self.qty_after_transaction = sle.qty_after_transaction
			self.stock_queue = [[self.qty_after_transaction]]
		else:
			if self.valuation_method == "Moving Average":
				self.get_moving_average_values(sle)
				self.qty_after_transaction += flt(sle.actual_qty)
				self.stock_value = flt(self.qty_after_transaction)
			else:
				self.get_fifo_values(sle)
				self.qty_after_transaction += flt(sle.actual_qty)

		# update current sle
		sle.qty_after_transaction = self.qty_after_transaction
		# sle.stock_value = self.stock_value
		sle.stock_queue = json.dumps(self.stock_queue)
		sle.doctype="Stock Ledger Entry"
		frappe.get_doc(sle).db_update()

	def validate_negative_stock(self, sle):
		"""
			validate negative stock for entries current datetime onwards
			will not consider cancelled entries
		"""
		diff = self.qty_after_transaction + flt(sle.actual_qty)

		if diff < 0 and abs(diff) > 0.0001:
			# negative stock!
			exc = sle.copy().update({"diff": diff})
			self.exceptions.append(exc)
			return False
		else:
			return True

	def get_moving_average_values(self, sle):
		actual_qty = flt(sle.actual_qty)
		new_stock_qty = flt(self.qty_after_transaction) + actual_qty
		if new_stock_qty >= 0:
			if actual_qty > 0:
				if flt(self.qty_after_transaction) <= 0:
					pass
				else:
					new_stock_value = (self.qty_after_transaction) + (actual_qty)
					self.valuation_rate = new_stock_value / new_stock_qty

	def get_fifo_values(self, sle):
		actual_qty = flt(sle.actual_qty)

		if actual_qty > 0:
			if not self.stock_queue:
				self.stock_queue.append([0, 0])

			self.stock_queue[-1][0] += actual_qty

			if self.stock_queue[-1][0] > 0:
				self.stock_queue.append([actual_qty])
			else:
				qty = self.stock_queue[-1][0] + actual_qty
				self.stock_queue[-1] = [qty]
		else:
			qty_to_pop = abs(actual_qty)
			while qty_to_pop:
				if not self.stock_queue:
					# Get valuation rate from last sle if exists or from valuation rate field in item master
					self.stock_queue.append([0])
				index = None
				if index == None:
					new_stock_qty = sum((d[0] for d in self.stock_queue)) - qty_to_pop
					break

	def get_sle_before_datetime(self):
		"""get previous stock ledger entry before current time-bucket"""
		return get_stock_ledger_entries(self.args, "<", "desc", "limit 1", for_update=False)

	def get_sle_after_datetime(self):
		"""get Stock Ledger Entries after a particular datetime, for reposting"""
		return get_stock_ledger_entries(self.previous_sle or frappe._dict({
				"item_code": self.args.get("item_code"), "warehouse": self.args.get("warehouse") }),
			">", "asc", for_update=True)

	def raise_exceptions(self):
		deficiency = min(e["diff"] for e in self.exceptions)

		if ((self.exceptions[0]["voucher_type"], self.exceptions[0]["voucher_no"]) in
			frappe.local.flags.currently_saving):

			msg = _("{0} units of {1} needed in {2} to complete this transaction.").format(
				abs(deficiency), frappe.get_desk_link('Item', self.item_code),
				frappe.get_desk_link('Warehouse', self.warehouse))
		else:
			msg = _("{0} units of {1} needed in {2} on {3} {4} for {5} to complete this transaction.").format(
				abs(deficiency), frappe.get_desk_link('Item', self.item_code),
				frappe.get_desk_link('Warehouse', self.warehouse),
				self.exceptions[0]["posting_date"], self.exceptions[0]["posting_time"],
				frappe.get_desk_link(self.exceptions[0]["voucher_type"], self.exceptions[0]["voucher_no"]))

		if self.verbose:
			frappe.throw(msg, NegativeStockError, title='Insufficent Stock')
		else:
			raise NegativeStockError(msg)

def get_previous_sle(args, for_update=False):
	"""
		get the last sle on or before the current time-bucket,
		to get actual qty before transaction, this function
		is called from various transaction like stock entry, reco etc

		args = {
			"item_code": "ABC",
			"warehouse": "XYZ",
			"posting_date": "2012-12-12",
			"posting_time": "12:00",
			"sle": "name of reference Stock Ledger Entry"
		}
	"""
	args["name"] = args.get("sle", None) or ""
	sle = get_stock_ledger_entries(args, "<=", "desc", "limit 1", for_update=for_update)
	return sle and sle[0] or {}

def get_stock_ledger_entries(previous_sle, operator=None, order="desc", limit=None, for_update=False, debug=False):
	"""get stock ledger entries filtered by specific posting datetime conditions"""
	conditions = "timestamp(posting_date, posting_time) {0} timestamp(%(posting_date)s, %(posting_time)s)".format(operator)
	if not previous_sle.get("posting_date"):
		previous_sle["posting_date"] = "1900-01-01"
	if not previous_sle.get("posting_time"):
		previous_sle["posting_time"] = "00:00"

	if operator in (">", "<=") and previous_sle.get("name"):
		conditions += " and name!=%(name)s"

	return frappe.db.sql("""select *, timestamp(posting_date, posting_time) as "timestamp" from `tabStock Ledger Entry`
		where item_code = %%(item_code)s
		and warehouse = %%(warehouse)s
		and ifnull(is_cancelled, 'No')='No'
		and %(conditions)s
		order by timestamp(posting_date, posting_time) %(order)s, name %(order)s
		%(limit)s %(for_update)s""" % {
			"conditions": conditions,
			"limit": limit or "",
			"for_update": for_update and "for update" or "",
			"order": order
		}, previous_sle, as_dict=1, debug=debug)
