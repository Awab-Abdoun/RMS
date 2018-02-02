from frappe import _


def get_data():
	return {
		'fieldname': 'material_request',
		'transactions': [
			{
				'label': _('Manufacturing'),
				'items': ['Production Order']
			}
		]
	}
