
import frappe, rms
from frappe.utils import cint, flt

@frappe.whitelist()
def make_stock_entry(**args):
	'''Helper function to make a Stock Entry

	:item_code: Item to be moved
	:qty: Qty to be moved
	:from_warehouse: Optional
	:to_warehouse: Optional
	:posting_date: Optional
	:posting_time: Optional
	:do_not_save: Optional flag
	:do_not_submit: Optional flag
	'''

	s = frappe.new_doc("Stock Entry")
	args = frappe._dict(args)

	if args.posting_date or args.posting_time:
		s.set_posting_time = 1

	if args.posting_date:
		s.posting_date = args.posting_date
	if args.posting_time:
		s.posting_time = args.posting_time

	# map names
	if args.from_warehouse:
		args.source = args.from_warehouse
	if args.to_warehouse:
		args.target = args.to_warehouse
	if args.item_code:
		args.item = args.item_code

	if isinstance(args.qty, basestring):
		if '.' in args.qty:
			args.qty = flt(args.qty)
		else:
			args.qty = cint(args.qty)

	# purpose
	if not args.purpose:
		if args.source and args.target:
			s.purpose = "Material Transfer"
		elif args.source:
			s.purpose = "Material Issue"
		else:
			s.purpose = "Material Receipt"
	else:
		s.purpose = args.purpose

	s.append("items", {
		"item_code": args.item,
		"s_warehouse": args.source,
		"t_warehouse": args.target,
		"qty": args.qty
	})

	if not args.do_not_save:
		s.insert()
		if not args.do_not_submit:
			s.submit()
	return s
