
frappe.provide('rms');

// add toolbar icon
$(document).bind('toolbar_setup', function() {
	frappe.app.name = "rms";

	frappe.help_feedback_link = '<p><a class="text-muted" \
		href="https://discuss.rms.com">Feedback</a></p>'


	// $('.navbar-home').html('<img class="rms-icon" src="'+
	// 		frappe.urllib.get_base_url()+'/assets/rms/images/erp-icon.svg" />');

	$('[data-link="docs"]').attr("href", "https://frappe.github.io/rms/")
	$('[data-link="issues"]').attr("href", "https://github.com/frappe/rms/issues")


	// default documentation goes to rms
	// $('[data-link-type="documentation"]').attr('data-path', '/rms/manual/index');

	// additional help links for rms
	var $help_menu = $('.dropdown-help ul .documentation-links');

	$('<li><a data-link-type="forum" href="https://discuss.rms.com" \
		target="_blank">'+__('User Forum')+'</a></li>').insertBefore($help_menu);
	$('<li><a href="https://gitter.im/frappe/rms" \
		target="_blank">'+__('Chat')+'</a></li>').insertBefore($help_menu);
	$('<li><a href="https://github.com/frappe/rms/issues" \
		target="_blank">'+__('Report an Issue')+'</a></li>').insertBefore($help_menu);

});



// doctypes created via tree
$.extend(frappe.create_routes, {
	"Item Group": "Tree/Item Group"
});

// preferred modules for breadcrumbs
$.extend(frappe.breadcrumbs.preferred, {
	"Item Group": "Stock"
});
