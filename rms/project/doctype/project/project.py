# -*- coding: utf-8 -*-
# Copyright (c) 2017, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe

from frappe.utils import flt, getdate, get_url
from frappe import _

from frappe.model.document import Document
from rms.controllers.queries import get_filters_cond
from frappe.desk.reportview import get_match_cond

class Project(Document):
	def get_feed(self):
		return '{0}: {1}'.format(_(self.status), self.project_name)

	def onload(self):
		"""Load project tasks for quick view"""
		if not self.get('__unsaved') and not self.get("tasks"):
			self.load_tasks()

	def __setup__(self):
		self.onload()

	def load_tasks(self):
		"""Load `tasks` from the database"""
		self.tasks = []
		for task in self.get_tasks():
			task_map = {
				"title": task.subject,
				"status": task.status,
				"start_date": task.exp_start_date,
				"end_date": task.exp_end_date,
				"description": task.description,
				"task_id": task.name,
				"task_weight": task.task_weight
			}

			self.map_custom_fields(task, task_map)

			self.append("tasks", task_map)

	def get_tasks(self):
		if self.name is None:
			return {}
		else:
			return frappe.get_all("Task", "*", {"project": self.name}, order_by="exp_start_date asc")

	def validate(self):
		self.validate_project_name()
		self.validate_dates()
		self.validate_weights()
		self.sync_tasks()
		self.tasks = []

	def validate_project_name(self):
		if self.get("__islocal") and frappe.db.exists("Project", self.project_name):
			frappe.throw(_("Project {0} already exists").format(self.project_name))

	def validate_dates(self):
		if self.expected_start_date and self.expected_end_date:
			if getdate(self.expected_end_date) < getdate(self.expected_start_date):
				frappe.throw(_("Expected End Date can not be less than Expected Start Date"))

	def validate_weights(self):
		sum = 0
		for task in self.tasks:
			if task.task_weight > 0:
				sum = sum + task.task_weight
		if sum > 0 and sum != 1:
			frappe.throw(_("Total of all task weights should be 1. Please adjust weights of all Project tasks accordingly"))

	def sync_tasks(self):
		"""sync tasks and remove table"""
		if self.flags.dont_sync_tasks: return
		task_names = []
		for t in self.tasks:
			if t.task_id:
				task = frappe.get_doc("Task", t.task_id)
			else:
				task = frappe.new_doc("Task")
				task.project = self.name
			task.update({
				"subject": t.title,
				"status": t.status,
				"exp_start_date": t.start_date,
				"exp_end_date": t.end_date,
				"description": t.description,
				"task_weight": t.task_weight
			})

			self.map_custom_fields(t, task)

			task.flags.ignore_links = True
			task.flags.from_project = True
			task.flags.ignore_feed = True
			task.save(ignore_permissions = True)
			task_names.append(task.name)

		# delete
		for t in frappe.get_all("Task", ["name"], {"project": self.name, "name": ("not in", task_names)}):
			frappe.delete_doc("Task", t.name)

	def map_custom_fields(self, source, target):
		project_task_custom_fields = frappe.get_all("Custom Field", {"dt": "Project Task"}, "fieldname")

		for field in project_task_custom_fields:
			target.update({
				field.fieldname: source.get(field.fieldname)
			})

	def update_project(self):
		self.update_percent_complete()
		self.flags.dont_sync_tasks = True
		self.save(ignore_permissions = True)

	def update_percent_complete(self):
		total = frappe.db.sql("""select count(name) from tabTask where project=%s""", self.name)[0][0]
		if not total and self.percent_complete:
			self.percent_complete = 0
		if (self.percent_complete_method == "Task Completion" and total > 0) or (not self.percent_complete_method and total > 0):
			completed = frappe.db.sql("""select count(name) from tabTask where
				project=%s and status in ('Closed', 'Cancelled')""", self.name)[0][0]
			self.percent_complete = flt(flt(completed) / total * 100, 2)

	def on_update(self):
		self.load_tasks()
		self.sync_tasks()
		self.update_dependencies_on_duplicated_project()

	def update_dependencies_on_duplicated_project(self):
		if self.flags.dont_sync_tasks: return
		if not self.copied_from:
			self.copied_from = self.name

		if self.name != self.copied_from and self.get('__unsaved'):
			# duplicated project
			dependency_map = {}
			for task in self.tasks:
				_task = frappe.db.get_value(
					'Task',
					{"subject": task.title, "project": self.copied_from},
					['name', 'depends_on_tasks'],
					as_dict=True
				)

				if _task is None:
					continue

				name = _task.name
				depends_on_tasks = _task.depends_on_tasks

				depends_on_tasks = [x for x in depends_on_tasks.split(',') if x]
				dependency_map[task.title] = [ x['subject'] for x in frappe.get_list(
					'Task Depends On', {"parent": name}, ['subject'])]

			for key, value in dependency_map.iteritems():
				task_name = frappe.db.get_value('Task', {"subject": key, "project": self.name })
				task_doc = frappe.get_doc('Task', task_name)

				for dt in value:
					dt_name = frappe.db.get_value('Task', {"subject": dt, "project": self.name })
					task_doc.append('depends_on', {"task": dt_name})
				task_doc.save()

def get_project_list(doctype, txt, filters, limit_start, limit_page_length=20, order_by="modified"):
	return frappe.db.sql('''select distinct project.*
		from tabProject project, `tabProject User` project_user
		where
			(project_user.user = %(user)s
			and project_user.parent = project.name)
			or project.owner = %(user)s
			order by project.modified desc
			limit {0}, {1}
		'''.format(limit_start, limit_page_length),
			{'user':frappe.session.user},
			as_dict=True,
			update={'doctype':'Project'})

def get_list_context(context=None):
	return {
		"show_sidebar": True,
		"show_search": True,
		'no_breadcrumbs': True,
		"title": _("Project"),
		"get_list": get_project_list,
		"row_template": "templates/includes/project/project_row.html"
	}
