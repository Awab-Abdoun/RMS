from __future__ import unicode_literals
import frappe

install_docs = [
	{"doctype":"Role", "role_name":"Stock Manager", "name":"Stock Manager"},
	{"doctype":"Item Group", "item_group_name":"All Item Groups", "is_group": 1},
	{"doctype":"Item Group", "item_group_name":"Default",
		"parent_item_group":"All Item Groups", "is_group": 0},
]
