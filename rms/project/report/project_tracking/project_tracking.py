# Copyright (c) 2013, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _

def execute(filters=None):
	columns = get_columns()
	proj_details = get_project_details()

	data = []
	for project in proj_details:
		data.append([project.name,
			project.project_name, project.status,
			project.expected_start_date,
			project.expected_end_date])

	return columns, data

def get_columns():
	return [_("Project Id") + ":Link/Project:140",
		_("Project Name") + "::120", _("Project Status") + "::120",
		_("Project Start Date") + ":Date:120", _("Completion Date") + ":Date:120"]

def get_project_details():
	return frappe.db.sql(""" select name, project_name, status,
		expected_start_date, expected_end_date from tabProject where docstatus < 2""", as_dict=1)
