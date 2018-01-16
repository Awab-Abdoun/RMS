from frappe import _

def get_data():
	return {
		'heatmap': True,
		'heatmap_message': _(''),
		'fieldname': 'project',
		'transactions': [
			{
				'label': _('Project'),
				'items': ['Task']
			},
			{
				'label': _('Material'),
				'items': ['BOM']
			},
		]
	}
