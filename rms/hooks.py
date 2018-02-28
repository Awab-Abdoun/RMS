# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as app_version
from frappe import _

app_name = "rms"
app_title = "Resource Management System"
app_publisher = "Awab Abdoun and Mohammed Elamged"
app_description = "Resource manangement for local bussiness in sudan"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "awab.abdoun@gmail.com"
app_license = "MIT"
source_link = "https://github.com/Awab-Abdoun/rms"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/rms/css/rms.css"
app_include_js = "/assets/rms/js/rms.js"

# include js, css files in header of web template
web_include_css = "/assets/rms/css/rms.css"
web_include_js = "/assets/rms/js/rms.js"

# include js in page
page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "rms.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "rms.install.before_install"
# after_install = "rms.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

notification_config = "rms.startup.notifications.get_notification_config"
treeviews = ['Warehouse', 'Item Group']
calendars = ["Task", "Production Order"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

dump_report_map = "rms.startup.report_data_map.data_map"

doc_events = {
	"Stock Entry": {
		"on_submit": "rms.stock.doctype.material_request.material_request.update_completed_and_requested_qty",
		"on_cancel": "rms.stock.doctype.material_request.material_request.update_completed_and_requested_qty"
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"rms.project.doctype.task.task.set_tasks_as_overdue",
	]
}

bot_parsers = [
	'rms.utilities.bot.FindItemBot',
]

# Testing
# -------

# before_tests = "rms.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "rms.event.get_events"
# }
