
from __future__ import unicode_literals
import frappe
from frappe.desk.reportview import get_match_cond, get_filters_cond
from frappe.utils import nowdate
from collections import defaultdict

def item_query(doctype, txt, searchfield, start, page_len, filters, as_dict=False):
	conditions = []

	return frappe.db.sql("""select tabItem.name, tabItem.item_group, tabItem.image,
		if(length(tabItem.item_name) > 40,
			concat(substr(tabItem.item_name, 1, 40), "..."), item_name) as item_name,
		if(length(tabItem.description) > 40, \
			concat(substr(tabItem.description, 1, 40), "..."), description) as decription
		from tabItem
		where tabItem.docstatus < 2
			and tabItem.disabled=0
			and (tabItem.end_of_life > %(today)s or ifnull(tabItem.end_of_life, '0000-00-00')='0000-00-00')
			and (tabItem.`{key}` LIKE %(txt)s
				or tabItem.item_group LIKE %(txt)s
				or tabItem.item_name LIKE %(txt)s
				or tabItem.description LIKE %(txt)s)
			{fcond} {mcond}
		order by
			if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),
			if(locate(%(_txt)s, item_name), locate(%(_txt)s, item_name), 99999),
			idx desc,
			name, item_name
		limit %(start)s, %(page_len)s """.format(
			key=searchfield,
			fcond=get_filters_cond(doctype, filters, conditions).replace('%', '%%'),
			mcond=get_match_cond(doctype).replace('%', '%%')),
			{
				"today": nowdate(),
				"txt": "%%%s%%" % txt,
				"_txt": txt.replace("%", ""),
				"start": start,
				"page_len": page_len
			}, as_dict=as_dict)

def bom(doctype, txt, searchfield, start, page_len, filters):
	conditions = []

	return frappe.db.sql("""select tabBOM.name, tabBOM.item
		from tabBOM
		where tabBOM.docstatus=1
			and tabBOM.is_active=1
			and tabBOM.`{key}` like %(txt)s
			{fcond} {mcond}
		order by
			if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),
			idx desc, name
		limit %(start)s, %(page_len)s """.format(
			fcond=get_filters_cond(doctype, filters, conditions),
			mcond=get_match_cond(doctype),
			key=frappe.db.escape(searchfield)),
		{
			'txt': "%%%s%%" % frappe.db.escape(txt),
			'_txt': txt.replace("%", ""),
			'start': start or 0,
			'page_len': page_len or 20
		})

def get_project_name(doctype, txt, searchfield, start, page_len, filters):
	cond = ''
	if filters.get('customer'):
		cond = '(`tabProject`.customer = "' + filters['customer'] + '" or ifnull(`tabProject`.customer,"")="") and'

	return frappe.db.sql("""select `tabProject`.name from `tabProject`
		where `tabProject`.status not in ("Completed", "Cancelled")
			and {cond} `tabProject`.name like %(txt)s {match_cond}
		order by
			if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),
			idx desc,
			`tabProject`.name asc
		limit {start}, {page_len}""".format(
			cond=cond,
			match_cond=get_match_cond(doctype),
			start=start,
			page_len=page_len), {
				"txt": "%{0}%".format(txt),
				"_txt": txt.replace('%', '')
			})

@frappe.whitelist()
def warehouse_query(doctype, txt, searchfield, start, page_len, filters):
	# Should be used when item code is passed in filters.
	conditions, bin_conditions = [], []
	filter_dict = get_doctype_wise_filters(filters)

	sub_query = """ select round(`tabBin`.actual_qty, 2) from `tabBin`
		where `tabBin`.warehouse = `tabWarehouse`.name
		{bin_conditions} """.format(
		bin_conditions=get_filters_cond(doctype, filter_dict.get("Bin"),
			bin_conditions, ignore_permissions=True))

	query = """select `tabWarehouse`.name,
		CONCAT_WS(" : ", "Actual Qty", ifnull( ({sub_query}), 0) ) as actual_qty
		from `tabWarehouse`
		where
		   `tabWarehouse`.`{key}` like '{txt}'
			{fcond} {mcond}
		order by
			`tabWarehouse`.name desc
		limit
			{start}, {page_len}
		""".format(
			sub_query=sub_query,
			key=frappe.db.escape(searchfield),
			fcond=get_filters_cond(doctype, filter_dict.get("Warehouse"), conditions),
			mcond=get_match_cond(doctype),
			start=start,
			page_len=page_len,
			txt=frappe.db.escape('%{0}%'.format(txt))
		)

	return frappe.db.sql(query)


def get_doctype_wise_filters(filters):
	# Helper function to seperate filters doctype_wise
	filter_dict = defaultdict(list)
	for row in filters:
		filter_dict[row[0]].append(row)
	return filter_dict
