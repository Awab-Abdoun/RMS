# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from frappe import _

def get_data():
	return [
		{
			"module_name": "Item",
			"_doctype": "Item",
			"color": "#f39c12",
			"icon": "octicon octicon-package",
			"type": "link",
			"link": "List/Item"
		},
		{
			"module_name": "Project",
			"_doctype": "Project",
			"color": "#8e44ad",
			"icon": "octicon octicon-rocket",
			"type": "link",
			"link": "List/Project"
		},
		{
			"module_name": "Task",
			"_doctype": "Task",
			"color": "#8e44ad",
			"icon": "octicon octicon-rocket",
			"type": "link",
			"link": "List/Task"
		},
		{
			"module_name": "BOM",
			"_doctype": "BOM",
			"color": "#7f8c8d",
			"icon": "octicon octicon-tools",
			"type": "link",
			"link": "List/BOM"
		},
		{
			"module_name": "Production Order",
			"_doctype": "Production Order",
			"color": "#7f8c8d",
			"icon": "octicon octicon-tools",
			"type": "link",
			"link": "List/Production Order"
		},
		{
			"module_name": "Stock",
			"color": "#f39c12",
			"icon": "fa fa-truck",
			"icon": "octicon octicon-package",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Project",
			"color": "#8e44ad",
			"icon": "fa fa-puzzle-piece",
			"icon": "octicon octicon-rocket",
			"type": "module",
			"hidden": 1
		},
		{
			"module_name": "Manufacturing",
			"color": "#7f8c8d",
			"icon": "fa fa-cogs",
			"icon": "octicon octicon-tools",
			"type": "module",
			"hidden": 0
		},
	]
