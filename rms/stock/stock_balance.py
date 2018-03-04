
from __future__ import print_function, unicode_literals
import frappe

from frappe.utils import flt, cstr, nowdate, nowtime
from rms.stock.utils import update_bin
from rms.stock.stock_ledger import update_entries_after

def repost(only_actual=False, only_bin=False):
	"""
	Repost everything!
	"""
	frappe.db.auto_commit_on_many_writes = 1

	for d in frappe.db.sql("""select distinct item_code, warehouse from
		(select item_code, warehouse from tabBin
		union
		select item_code, warehouse from `tabStock Ledger Entry`) a"""):
			try:
				repost_stock(d[0], d[1], only_actual, only_bin)
				frappe.db.commit()
			except:
				frappe.db.rollback()

	frappe.db.auto_commit_on_many_writes = 0

def repost_stock(item_code, warehouse, only_actual=False, only_bin=False):
	if not only_bin:
		repost_actual_qty(item_code, warehouse)

	if item_code and warehouse and not only_actual:
		qty_dict = {
			# "reserved_qty": get_reserved_qty(item_code, warehouse),
			"indented_qty": get_indented_qty(item_code, warehouse),
			# "ordered_qty": get_ordered_qty(item_code, warehouse),
			"planned_qty": get_planned_qty(item_code, warehouse)
		}
		if only_bin:
			qty_dict.update({
				"actual_qty": get_balance_qty_from_sle(item_code, warehouse)
			})

		update_bin_qty(item_code, warehouse, qty_dict)

def repost_actual_qty(item_code, warehouse):
	try:
		update_entries_after({ "item_code": item_code, "warehouse": warehouse })
	except:
		pass

def get_balance_qty_from_sle(item_code, warehouse):
	balance_qty = frappe.db.sql("""select qty_after_transaction from `tabStock Ledger Entry`
		where item_code=%s and warehouse=%s and is_cancelled='No'
		order by posting_date desc, posting_time desc, name desc
		limit 1""", (item_code, warehouse))

	return flt(balance_qty[0][0]) if balance_qty else 0.0

# def get_reserved_qty(item_code, warehouse):
# 	reserved_qty = frappe.db.sql("""
# 		select
# 			# sum(dnpi_qty * ((so_item_qty - so_item_delivered_qty) / so_item_qty))
# 		from
# 			(
# 				(select
# 					qty as dnpi_qty,
# 					(
# 						select qty from `tabSales Order Item`
# 						where name = dnpi.parent_detail_docname
# 						and (delivered_by_supplier is null or delivered_by_supplier = 0)
# 					) as so_item_qty,
# 					(
# 						select delivered_qty from `tabSales Order Item`
# 						where name = dnpi.parent_detail_docname
# 						and delivered_by_supplier = 0
# 					) as so_item_delivered_qty,
# 					parent, name
# 				from
# 				(
# 					select qty, parent_detail_docname, parent, name
# 					from `tabPacked Item` dnpi_in
# 					where item_code = %s and warehouse = %s
# 					and parenttype="Sales Order"
# 					and item_code != parent_item
# 					and exists (select * from `tabSales Order` so
# 					where name = dnpi_in.parent and docstatus = 1 and status != 'Closed')
# 				) dnpi)
# 			union
# 				(select stock_qty as dnpi_qty, qty as so_item_qty,
# 					delivered_qty as so_item_delivered_qty, parent, name
# 				from `tabSales Order Item` so_item
# 				where item_code = %s and warehouse = %s
# 				and (so_item.delivered_by_supplier is null or so_item.delivered_by_supplier = 0)
# 				and exists(select * from `tabSales Order` so
# 					where so.name = so_item.parent and so.docstatus = 1
# 					and so.status != 'Closed'))
# 			) tab
# 		where
# 			so_item_qty >= so_item_delivered_qty
# 	""", (item_code, warehouse, item_code, warehouse))
#
# 	return flt(reserved_qty[0][0]) if reserved_qty else 0

def get_indented_qty(item_code, warehouse):
	indented_qty = frappe.db.sql("""select sum(mr_item.qty - mr_item.ordered_qty)
		from `tabMaterial Request Item` mr_item, `tabMaterial Request` mr
		where mr_item.item_code=%s and mr_item.warehouse=%s
		and mr_item.qty > mr_item.ordered_qty and mr_item.parent=mr.name
		and mr.status!='Stopped' and mr.docstatus=1""", (item_code, warehouse))

	return flt(indented_qty[0][0]) if indented_qty else 0

# def get_ordered_qty(item_code, warehouse):
# 	ordered_qty = frappe.db.sql("""
# 		select sum((po_item.qty - po_item.received_qty)*po_item.conversion_factor)
# 		from `tabPurchase Order Item` po_item, `tabPurchase Order` po
# 		where po_item.item_code=%s and po_item.warehouse=%s
# 		and po_item.qty > po_item.received_qty and po_item.parent=po.name
# 		and po.status not in ('Closed', 'Delivered') and po.docstatus=1
# 		and po_item.delivered_by_supplier = 0""", (item_code, warehouse))
#
# 	return flt(ordered_qty[0][0]) if ordered_qty else 0

def get_planned_qty(item_code, warehouse):
	planned_qty = frappe.db.sql("""
		select sum(qty - produced_qty) from `tabProduction Order`
		where production_item = %s and fg_warehouse = %s and status not in ("Stopped", "Completed")
		and docstatus=1 and qty > produced_qty""", (item_code, warehouse))

	return flt(planned_qty[0][0]) if planned_qty else 0


def update_bin_qty(item_code, warehouse, qty_dict=None):
	from rms.stock.utils import get_bin
	bin = get_bin(item_code, warehouse)
	mismatch = False
	for fld, val in qty_dict.items():
		if flt(bin.get(fld)) != flt(val):
			bin.set(fld, flt(val))
			mismatch = True

	if mismatch:
		bin.projected_qty = (flt(bin.actual_qty) + flt(bin.ordered_qty) +
			flt(bin.indented_qty) + flt(bin.planned_qty) - flt(bin.reserved_qty)
			- flt(bin.reserved_qty_for_production))

		bin.save()

def repost_all_stock_vouchers():
	vouchers = frappe.db.sql("""select distinct voucher_type, voucher_no
		from `tabStock Ledger Entry` sle
		where sle.warehouse in (%s)
		order by posting_date, posting_time, name""" %
		', '.join(['%s']*len(warehouses_with_account)), tuple(warehouses_with_account))

	rejected = []
	i = 0
	for voucher_type, voucher_no in vouchers:
		i+=1
		print(i, "/", len(vouchers), voucher_type, voucher_no)
		try:
			for dt in ["Stock Ledger Entry", "GL Entry"]:
				frappe.db.sql("""delete from `tab%s` where voucher_type=%s and voucher_no=%s"""%
					(dt, '%s', '%s'), (voucher_type, voucher_no))

			doc = frappe.get_doc(voucher_type, voucher_no)

			doc.update_stock_ledger()
			doc.make_gl_entries(repost_future_gle=False)
			frappe.db.commit()
		except Exception as e:
			print(frappe.get_traceback())
			rejected.append([voucher_type, voucher_no])
			frappe.db.rollback()

	print(rejected)
