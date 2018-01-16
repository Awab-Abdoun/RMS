// Copyright (c) 2017, Awab Abdoun and Mohammed Elamged and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project", {
	setup: function(frm) {
		frm.set_indicator_formatter('title',
			function(doc) {
				let indicator = 'orange';
				if (doc.status == 'Overdue') {
					indicator = 'red';
				}
				else if (doc.status == 'Cancelled') {
					indicator = 'dark grey';
				}
				else if (doc.status == 'Closed') {
					indicator = 'green';
				}
				return indicator;
			}
		);
	},

	refresh: function(frm) {
		if(frm.doc.__islocal) {
			frm.web_link && frm.web_link.remove();
		} else {
			frm.add_web_link("/project?project=" + encodeURIComponent(frm.doc.name));

			if(frappe.model.can_read("Task")) {
				frm.add_custom_button(__("Gantt Chart"), function() {
					frappe.route_options = {"project": frm.doc.name};
					frappe.set_route("List", "Task", "Gantt");
				});
			}

			frm.trigger('show_dashboard');
		}
	},
	tasks_refresh: function(frm) {
		var grid = frm.get_field('tasks').grid;
		grid.wrapper.find('select[data-fieldname="status"]').each(function() {
			if($(this).val()==='Open') {
				$(this).addClass('input-indicator-open');
			} else {
				$(this).removeClass('input-indicator-open');
			}
		});
	}
});

frappe.ui.form.on("Project Task", {
	edit_task: function(frm, doctype, name) {
		var doc = frappe.get_doc(doctype, name);
		if(doc.task_id) {
			frappe.set_route("Form", "Task", doc.task_id);
		} else {
			frappe.msgprint(__("Save the document first."));
		}
	},
	status: function(frm, doctype, name) {
		frm.trigger('tasks_refresh');
	},
});
