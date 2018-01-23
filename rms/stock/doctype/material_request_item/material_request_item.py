# -*- coding: utf-8 -*-
# Copyright (c) 2018, Awab Abdoun and Mohammed Elamged and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class MaterialRequestItem(Document):
	pass

def on_doctype_update():
	frappe.db.add_index("Material Request Item", ["item_code", "warehouse"])
