# -*- coding: utf-8 -*-
# Copyright (c) 2017, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe import _

class ProjectType(Document):
	def on_trash(self):
		if self.name == "External":
			frappe.throw(_("You cannot delete Project Type 'External'"))
